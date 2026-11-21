# services/social/social_montage.py
import asyncio
import logging
import os
import re
import uuid

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

from agent.services.social import social_assets as assets
from agent.services.social import social_unsplash as stock
from agent.services.social.social_config import PUBLIC_BASE_URL, UPLOAD_DIR

logger = logging.getLogger("social_montage")

PLATFORM_SIZE = {"instagram": (1080, 1350), "tiktok": (1080, 1920), "linkedin": (1200, 627),
                 "facebook": (1200, 630), "x": (1200, 675)}

RATIO_SIZE = {"carre": (1080, 1080), "portrait": (1080, 1350), "paysage": (1200, 630)}


def size_for(platform: str, ratio: str | None):
    if ratio in RATIO_SIZE:
        if platform in ("linkedin", "facebook") or (platform == "instagram" and ratio != "paysage"):
            return RATIO_SIZE[ratio]
    return PLATFORM_SIZE.get(platform, (1200, 630))


# ═════════════════════════ POLICES / COULEURS ═════════════════════════
_FONTS: dict = {}


def _font_candidates(bold: bool) -> list:
    c = [os.getenv("SOCIAL_FONT_BOLD" if bold else "SOCIAL_FONT_REGULAR")]
    fdir = assets.BRANDING_DIR / "fonts"
    if fdir.exists():
        files = sorted(fdir.glob("*.[to]tf"))
        c += [str(f) for f in files if ("bold" in f.name.lower()) == bold] + [str(f) for f in files]
    c += ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
          "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"]
    return [x for x in c if x]


def _font(size, bold: bool = True):
    key = (int(size), bold)
    if key in _FONTS:
        return _FONTS[key]
    f = None
    for c in _font_candidates(bold):
        try:
            f = ImageFont.truetype(c, int(size))
            break
        except Exception:
            continue
    if f is None:
        f = ImageFont.load_default(size=int(size))
    _FONTS[key] = f
    return f


def _rgb(h, default=(27, 58, 107)):
    try:
        h = str(h).lstrip("#")
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return default


def _lum(c):
    return (0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]) / 255


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _pal(couleurs: dict) -> dict:
    p, s = _rgb(couleurs.get("primaire", "#1B3A6B")), _rgb(couleurs.get("secondaire", "#2E5FA3"))
    if _lum(p) > 0.55:
        p = _mix(p, (0, 0, 0), 0.55)
    if _lum(s) > 0.6:
        s = _mix(s, (0, 0, 0), 0.45)
    accent = _mix(s, (255, 255, 255), 0.35)
    return {"p": p, "s": s, "accent": accent, "on_accent": (255, 255, 255) if _lum(accent) < 0.55 else (20, 24, 32),
            "txt": (255, 255, 255), "txt2": _mix((255, 255, 255), p, 0.18)}


# ═════════════════════════ PRIMITIVES ═════════════════════════
def _flatten(img):
    return assets._flatten(img)


def _over(cv, layer, pos):
    x, y = int(pos[0]), int(pos[1])
    sx, sy, dx, dy = max(0, -x), max(0, -y), max(0, x), max(0, y)
    w, h = min(layer.width - sx, cv.width - dx), min(layer.height - sy, cv.height - dy)
    if w > 0 and h > 0:
        cv.alpha_composite(layer.crop((sx, sy, sx + w, sy + h)), (dx, dy))


def _round(img, r):
    img = img.convert("RGBA")
    m = Image.new("L", img.size, 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, img.width - 1, img.height - 1], radius=max(1, int(r)), fill=255)
    img.putalpha(ImageChops.multiply(img.getchannel("A"), m))
    return img


def _shadow(cv, xy, size, rad, blur=26, alpha=120, dy=14):
    x, y = xy
    w, h = size
    pad = int(blur * 3)
    layer = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle([pad, pad, pad + w, pad + h], radius=int(rad), fill=(0, 0, 0, alpha))
    _over(cv, layer.filter(ImageFilter.GaussianBlur(blur)), (x - pad, y - pad + dy))


def _base(size, pal):
    W, H = size
    mask = Image.linear_gradient("L").resize(size)
    cv = Image.composite(Image.new("RGB", size, pal["s"]), Image.new("RGB", size, pal["p"]), mask).convert("RGBA")
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(glow)
    r = int(max(W, H) * 0.45)
    d.ellipse([W - r * 0.8, -r * 0.6, W + r * 0.4, r * 0.6], fill=pal["accent"] + (60,))
    d.ellipse([-r * 0.5, H - r * 0.5, r * 0.6, H + r * 0.5], fill=pal["accent"] + (35,))
    _over(cv, glow.filter(ImageFilter.GaussianBlur(int(max(W, H) * 0.06))), (0, 0))
    return cv


def _wrap(font, text, max_w):
    lines, cur = [], ""
    for w in str(text).split():
        t = f"{cur} {w}".strip()
        if font.getlength(t) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _fit(text, max_w, max_h, max_size, min_size=22, bold=True, spacing=1.15):
    size = int(max_size)
    while size >= int(min_size):
        f = _font(size, bold)
        lines, lh = _wrap(f, text, max_w), int(size * spacing)
        if len(lines) * lh <= max_h and all(f.getlength(l) <= max_w for l in lines):
            return f, lines, lh
        size -= 2
    f = _font(int(min_size), bold)
    lh = int(min_size * spacing)
    return f, _wrap(f, text, max_w)[:max(1, int(max_h // lh))], lh


def _draw_lines(d, x, y, lines, font, lh, fill):
    for ln in lines:
        d.text((x, y), ln, font=font, fill=fill)
        y += lh
    return y


def _blur_zones(img, zones):
    W, H = img.size
    for z in zones or []:
        try:
            x, y, w, h = z["x"] / 100 * W, z["y"] / 100 * H, z["w"] / 100 * W, z["h"] / 100 * H
        except Exception:
            continue
        pad = int(min(W, H) * 0.006)
        box = (max(0, int(x) - pad), max(0, int(y) - pad), min(W, int(x + w) + pad), min(H, int(y + h) + pad))
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            continue
        reg = img.crop(box)
        small = reg.resize((max(1, reg.width // 14), max(1, reg.height // 14)))
        img.paste(small.resize(reg.size, Image.NEAREST).filter(ImageFilter.GaussianBlur(4)), box)


def _prep_shot(a: dict) -> dict:
    img = Image.open(a["path"])
    img.load()
    img = _flatten(img)
    img.thumbnail((2400, 2400), Image.LANCZOS)
    _blur_zones(img, a.get("zones"))
    return {"img": img, "focus": a.get("focus"), "kind": "mobile" if a.get("appareil") == "mobile" else "auto"}


def _chrome(img, sc, url):
    bar = max(24, int(46 * sc))
    out = Image.new("RGBA", (img.width, img.height + bar), (243, 244, 246, 255))
    d = ImageDraw.Draw(out)
    r = max(4, int(7 * sc))
    for i, col in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        cx, cy = int(24 * sc) + i * int(22 * sc), bar // 2
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (255,))
    x0, x1 = int(110 * sc), img.width - int(30 * sc)
    d.rounded_rectangle([x0, int(bar * 0.22), x1, int(bar * 0.78)], radius=int(bar * 0.28), fill=(255, 255, 255, 255))
    d.text((x0 + int(16 * sc), bar // 2), url, font=_font(max(10, int(17 * sc)), False), fill=(105, 112, 124, 255), anchor="lm")
    out.paste(img.convert("RGBA"), (0, bar))
    return out


def _phone(scr, sc):
    b = max(6, int(15 * sc))
    out = Image.new("RGBA", (scr.width + 2 * b, scr.height + 2 * b), (0, 0, 0, 0))
    ImageDraw.Draw(out).rounded_rectangle([0, 0, out.width - 1, out.height - 1], radius=int(54 * sc), fill=(17, 19, 24, 255))
    _over(out, _round(scr.convert("RGBA"), int(40 * sc)), (b, b))
    return out


def _place(cv, img, box, s, kind="auto", url=""):
    """Insère une capture cadrée (navigateur / téléphone / simple) centrée dans box, avec ombre."""
    bx0, by0, bx1, by1 = box
    bw, bh = max(10, bx1 - bx0), max(10, by1 - by0)
    aspect = img.width / img.height
    if kind == "auto":
        kind = "mobile" if aspect < 0.8 else "web"
    if kind == "web":
        fw = int(min(bw, bh / (1 / aspect + 0.032)))
        framed = _chrome(img.resize((fw, max(1, int(fw / aspect))), Image.LANCZOS), fw / 1440, url)
        rad = int(16 * fw / 1440 + 8)
    elif kind == "mobile":
        sh = int(min(bh / 1.03, bw / (aspect + 0.03)))
        framed = _phone(img.resize((max(1, int(sh * aspect)), sh), Image.LANCZOS), sh / 1000)
        rad = int(sh * 0.045)
    else:
        fw = int(min(bw, bh * aspect))
        framed = img.resize((fw, max(1, int(fw / aspect))), Image.LANCZOS).convert("RGBA")
        rad = int(14 * s)
    framed = _round(framed, rad)
    x, y = bx0 + (bw - framed.width) // 2, by0 + (bh - framed.height) // 2
    _shadow(cv, (x, y), framed.size, rad, blur=int(26 * s), alpha=130, dy=int(16 * s))
    _over(cv, framed, (x, y))
    return x, y, framed.width, framed.height


def _badge(cv, ctx, text, x, y):
    s = ctx["s"]
    f, t = _font(int(23 * s)), str(text).upper()
    px, h = int(22 * s), int(46 * s)
    layer = Image.new("RGBA", (int(f.getlength(t) + 2 * px) + 2, h + 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle([0, 0, layer.width - 1, h], radius=h // 2, fill=ctx["pal"]["accent"] + (255,))
    d.text((px, h // 2), t, font=f, fill=ctx["pal"]["on_accent"], anchor="lm")
    _over(cv, layer, (x, y))
    return y + h


def _logo_pill(ctx, h):
    lg = ctx.get("logo")
    if lg is None:
        return None
    pad = int(h * 0.18)
    inner = ImageOps.contain(lg, (int(h * 4.5), h))
    pill = Image.new("RGBA", (inner.width + 2 * pad, inner.height + 2 * pad), (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle([0, 0, pill.width - 1, pill.height - 1], radius=int(h * 0.25), fill=(255, 255, 255, 255))
    pill.alpha_composite(inner, (pad, pad))
    return pill


def _footer(cv, ctx, y_mid):
    s, m, d = ctx["s"], ctx["m"], ImageDraw.Draw(cv)
    pill = _logo_pill(ctx, int(50 * s))
    if pill:
        _over(cv, pill, (m, y_mid - pill.height // 2))
    else:
        d.text((m, y_mid), ctx["brand"], font=_font(int(30 * s)), fill=ctx["pal"]["txt"], anchor="lm")
    if ctx.get("site"):
        d.text((cv.width - m, y_mid), ctx["site"], font=_font(int(26 * s), False), fill=ctx["pal"]["txt2"], anchor="rm")


def _footer_left(cv, ctx, x, y_bottom):
    s, d = ctx["s"], ImageDraw.Draw(cv)
    d.text((x, y_bottom), ctx["site"], font=_font(int(22 * s), False), fill=ctx["pal"]["txt2"], anchor="ld")
    y = y_bottom - int(40 * s)
    pill = _logo_pill(ctx, int(44 * s))
    if pill:
        _over(cv, pill, (x, y - pill.height))
    else:
        d.text((x, y), ctx["brand"], font=_font(int(28 * s)), fill=ctx["pal"]["txt"], anchor="ld")


def _credit(cv, ctx):
    if ctx.get("credit"):
        ImageDraw.Draw(cv).text((cv.width - ctx["m"], cv.height - int(16 * ctx["s"])), ctx["credit"],
                                font=_font(int(16 * ctx["s"]), False), fill=(205, 208, 214), anchor="rd")


def _head_block(cv, ctx, y, width, max_h, max_size=84, badge=True):
    d, s, m = ImageDraw.Draw(cv), ctx["s"], ctx["m"]
    if badge and ctx.get("badge"):
        y = _badge(cv, ctx, ctx["badge"], m, y) + int(28 * s)
    f, lines, lh = _fit(ctx.get("titre") or "", width, max_h, int(max_size * s), int(40 * s))
    y = _draw_lines(d, m, y, lines, f, lh, ctx["pal"]["txt"])
    if ctx.get("sous"):
        y += int(12 * s)
        f2, l2, lh2 = _fit(ctx["sous"], width, int(ctx["H"] * 0.1), int(36 * s), int(22 * s), bold=False)
        y = _draw_lines(d, m, y, l2, f2, lh2, ctx["pal"]["txt2"])
    return y


def _crop_focus(img, z):
    W, H = img.size
    x0, y0 = (z["x"] - 3) / 100 * W, (z["y"] - 3) / 100 * H
    x1, y1 = (z["x"] + z["w"] + 3) / 100 * W, (z["y"] + z["h"] + 3) / 100 * H
    if x1 - x0 < W * 0.35:
        cx = (x0 + x1) / 2
        x0, x1 = cx - W * 0.175, cx + W * 0.175
    if y1 - y0 < H * 0.35:
        cy = (y0 + y1) / 2
        y0, y1 = cy - H * 0.175, cy + H * 0.175
    return img.crop((max(0, int(x0)), max(0, int(y0)), min(W, int(x1)), min(H, int(y1))))


# ═════════════════════════ TEMPLATES ═════════════════════════
def t_carte(ctx):
    W, H, s, m = ctx["W"], ctx["H"], ctx["s"], ctx["m"]
    cv = _base((W, H), ctx["pal"])
    d = ImageDraw.Draw(cv)
    land = W / H > 1.3
    y = int(H * (0.18 if land else 0.2))
    if ctx.get("badge"):
        y = _badge(cv, ctx, ctx["badge"], m, y) + int(30 * s)
    else:
        d.rounded_rectangle([m, y, m + int(W * 0.12), y + int(10 * s)], radius=5, fill=ctx["pal"]["accent"])
        y += int(46 * s)
    f, lines, lh = _fit(ctx.get("titre") or ctx["brand"], W - 2 * m, int(H * 0.45), int(96 * s), int(40 * s))
    y = _draw_lines(d, m, y, lines, f, lh, ctx["pal"]["txt"])
    if ctx.get("sous"):
        y += int(18 * s)
        f2, l2, lh2 = _fit(ctx["sous"], W - 2 * m, int(H * 0.16), int(40 * s), int(24 * s), bold=False)
        _draw_lines(d, m, y, l2, f2, lh2, ctx["pal"]["txt2"])
    _footer(cv, ctx, H - int(70 * s))
    return cv


def t_capture(ctx):
    W, H, s, m = ctx["W"], ctx["H"], ctx["s"], ctx["m"]
    cv = _base((W, H), ctx["pal"])
    sh = ctx["shots"][0]
    if W / H > 1.3:                                    # paysage : texte à gauche, capture à droite
        col = int(W * 0.40)
        _head_block(cv, ctx, m, col - m - int(16 * s), int(H * 0.5), 64)
        _place(cv, sh["img"], (col, m, W - int(m * 0.6), H - m), s, sh["kind"], ctx["url"])
        _footer_left(cv, ctx, m, H - m)
    else:
        y = _head_block(cv, ctx, m, W - 2 * m, int(H * 0.2), 84)
        foot = int(120 * s)
        _place(cv, sh["img"], (m, y + int(34 * s), W - m, H - foot), s, sh["kind"], ctx["url"])
        _footer(cv, ctx, H - foot // 2)
    _credit(cv, ctx)
    return cv


def t_zoom(ctx):
    W, H, s, m = ctx["W"], ctx["H"], ctx["s"], ctx["m"]
    cv = _base((W, H), ctx["pal"])
    sh, z = ctx["shots"][0], ctx["shots"][0]["focus"]
    crop = _crop_focus(sh["img"], z)
    if W / H > 1.3:
        col = int(W * 0.40)
        _head_block(cv, ctx, m, col - m - int(16 * s), int(H * 0.5), 64)
        _place(cv, crop, (col, m, W - int(m * 0.6), H - m), s, "plain")
        _footer_left(cv, ctx, m, H - m)
    else:
        y = _head_block(cv, ctx, m, W - 2 * m, int(H * 0.2), 84)
        foot = int(120 * s)
        x, yy, w, h = _place(cv, crop, (m, y + int(34 * s), W - m, H - foot - int(30 * s)), s, "plain")
        iw = int(w * 0.38)
        th = sh["img"].resize((iw, max(1, int(iw * sh["img"].height / sh["img"].width))), Image.LANCZOS).convert("RGBA")
        ImageDraw.Draw(th).rectangle(
            [int(z["x"] / 100 * th.width), int(z["y"] / 100 * th.height),
             int((z["x"] + z["w"]) / 100 * th.width), int((z["y"] + z["h"]) / 100 * th.height)],
            outline=ctx["pal"]["accent"] + (255,), width=max(3, int(4 * s)))
        bd = int(6 * s)
        card = Image.new("RGBA", (th.width + 2 * bd, th.height + 2 * bd), (255, 255, 255, 255))
        card.alpha_composite(th, (bd, bd))
        card = _round(card, int(12 * s))
        px, py = x + int(18 * s), yy + h - card.height - int(18 * s)
        _shadow(cv, (px, py), card.size, int(12 * s), blur=int(14 * s), alpha=140, dy=int(8 * s))
        _over(cv, card, (px, py))
        _footer(cv, ctx, H - foot // 2)
    return cv


def t_photo(ctx):
    W, H, s, m = ctx["W"], ctx["H"], ctx["s"], ctx["m"]
    ph = ImageOps.fit(_flatten(ctx["photo"]), (W, H), Image.LANCZOS, centering=(0.5, 0.4)).convert("RGBA")
    ramp = Image.linear_gradient("L").resize((W, H)).point(lambda v: int(110 + (240 - 110) * v / 255))
    veil = Image.new("RGBA", (W, H), ctx["pal"]["p"] + (255,))
    veil.putalpha(ramp)
    ph.alpha_composite(veil)
    cv, sh, land = ph, (ctx["shots"][0] if ctx["shots"] else None), W / H > 1.3
    y = m
    if ctx.get("badge"):
        y = _badge(cv, ctx, ctx["badge"], m, y)
    if land:
        _head_block(cv, ctx, int(H * 0.30), int(W * 0.5) - m, int(H * 0.4), 64, badge=False)
        if sh:
            _place(cv, sh["img"], (int(W * 0.55), m, W - int(m * 0.6), H - m), s, sh["kind"], ctx["url"])
        _footer_left(cv, ctx, m, H - m)
    elif sh:
        _place(cv, sh["img"], (m, y + int(30 * s), W - m, int(H * 0.56)), s, sh["kind"], ctx["url"])
        _head_block(cv, ctx, int(H * 0.60), W - 2 * m, int(H * 0.22), 76, badge=False)
        _footer(cv, ctx, H - int(70 * s))
    else:
        _head_block(cv, ctx, int(H * 0.5), W - 2 * m, int(H * 0.3), 92, badge=False)
        _footer(cv, ctx, H - int(70 * s))
    _credit(cv, ctx)
    return cv


# ═════════════════════════ RENDU ═════════════════════════
M2_TEMPLATES = {"tilt", "glass", "duo", "checklist", "quote", "bold"}


def _render_sync(job: dict) -> list:
    W, H = job["size"]
    land = W / H > 1.3
    s = min(W / 1080, H / 630)
    m = int((52 if land else 70) * s)
    logo = None
    if job.get("logo"):
        try:
            logo = _flatten(Image.open(job["logo"])).convert("RGBA")
        except Exception:
            logo = None
    shots = {}
    for a in job["assets"]:
        try:
            shots[a["id"]] = _prep_shot(a)
        except Exception as e:
            logger.warning("Capture %s illisible : %s", a["id"], e)
    domain = re.sub(r"^https?://(www\.)?", "", job["site"] or "").strip("/")
    base = {"W": W, "H": H, "s": s, "m": m, "pal": _pal(job["couleurs"]), "brand": job["brand"], "site": domain,
            "url": domain or "app", "logo": logo, "credit": job.get("credit"),
            "titre": job.get("titre"), "sous": job.get("sous"), "badge": job.get("badge"),
            "points": job.get("points") or []}
    tpl = job["template"]
    ordered = [shots[i] for i in (job["asset_ids"] or []) if i in shots]
    first = ordered[0] if ordered else None
    photo = Image.open(job["photo"]) if job.get("photo") else None
    imgs = []
    if tpl == "carrousel":
        slides = [sl for sl in job["slides"] if sl["asset_id"] in shots][:8]
        n = len(slides)
        imgs.append(t_carte({**base, "sous": job.get("sous") or "Glisse pour découvrir →"}))
        for i, sl in enumerate(slides, 1):
            imgs.append(t_capture({**base, "titre": sl.get("titre"), "sous": sl.get("sous_titre"),
                                   "badge": f"{i:02d} / {n:02d}", "shots": [shots[sl["asset_id"]]]}))
        imgs.append(t_carte({**base, "titre": job.get("cta") or f"Découvrez {job['brand']}", "sous": domain, "badge": None}))
    elif tpl == "photo_overlay" and photo is not None:
        imgs.append(t_photo({**base, "photo": photo, "shots": [first] if first else []}))
    elif tpl in M2_TEMPLATES:
        from agent.services.social import social_montage2 as m2     # import tardif (évite le cycle)
        imgs.append(m2.render(tpl, base, ordered, job))
    elif tpl == "capture_zoom" and first and first.get("focus"):
        imgs.append(t_zoom({**base, "shots": [first]}))
    elif tpl in ("capture_cadree", "capture_zoom") and first:
        imgs.append(t_capture({**base, "shots": [first]}))
    else:
        imgs.append(t_carte(base))
    names = []
    for im in imgs:
        name = f"{uuid.uuid4().hex}.jpg"
        im.convert("RGB").save(os.path.join(UPLOAD_DIR, name), "JPEG", quality=92, optimize=True, subsampling=0)
        names.append(name)
    return names


async def render_visual(spec: dict, platform: str, brand, cfg: dict) -> dict:
    """spec = sortie de assets.finalize_spec. Retourne {"urls": [...], "spec": spec_final}."""
    catalog = {a["id"]: a for a in assets.list_assets(include_excluded=True)}
    size = size_for(platform, spec.get("ratio"))
    tpl, spec = spec["template"], dict(spec)
    photo = None
    if tpl == "photo_overlay":
        r = size[0] / size[1]
        orient = "portrait" if r < 0.9 else "squarish" if r < 1.1 else "landscape"
        photo = await stock.fetch_photo(spec.get("unsplash_query", ""), orient)
        if not photo:
            tpl = "capture_cadree" if spec.get("asset_ids") else "carte"
            spec["template"] = tpl
    ids = list(spec.get("asset_ids") or [])
    job_assets = []
    for i in ids:
        a = catalog.get(i)
        if a:
            job_assets.append({"id": i, "path": str(assets.asset_path(a)), "zones": a.get("zones_sensibles") or [],
                               "focus": a.get("zone_focus"), "appareil": a.get("appareil")})
    logo = assets.find_logo(cfg)
    job = {"template": tpl, "size": size, "platform": platform, "couleurs": cfg["couleurs"], "brand": brand.nom,
           "site": brand.site_url, "asset_ids": ids, "assets": job_assets, "slides": spec.get("slides") or [],
           "titre": spec.get("titre_carte"), "sous": spec.get("sous_titre"), "badge": spec.get("badge"),
           "cta": spec.get("cta_titre"), "photo": photo["path"] if photo else None,
           "credit": photo["credit"] if photo else None, "logo": str(logo) if logo else None}
    names = await asyncio.to_thread(_render_sync, job)
    final = dict(spec)
    if photo:
        final["credits"] = [photo["credit"]]
        final["stock"] = {"source": photo["source"], "id": photo["id"], "url": photo["page_url"]}
    return {"urls": [f"{PUBLIC_BASE_URL}/uploads/social/{n}" for n in names], "spec": final}