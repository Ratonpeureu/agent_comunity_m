# services/social/social_montage2.py
import hashlib
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps

from agent.services.social import social_montage as m

TEMPLATES = {"tilt", "glass", "duo", "checklist", "quote", "bold"}
STYLES = ("aurora", "dark", "mesh", "light", "aurora", "dark")


def _seed(x) -> int:
    return int(hashlib.md5(str(x).encode()).hexdigest()[:8], 16)


def style_colors(pal, style):
    if style == "light":
        acc = pal["s"] if m._lum(pal["s"]) < 0.6 else pal["p"]
        return {"bg": (244, 246, 251), "fg": (17, 22, 38), "fg2": (88, 98, 124), "acc": acc}
    bg = m._mix(pal["p"], (0, 0, 0), 0.72 if style == "dark" else 0.35)
    return {"bg": bg, "fg": (255, 255, 255), "fg2": m._mix((255, 255, 255), pal["p"], 0.22), "acc": pal["accent"]}


def with_style(ctx, sc):
    acc = sc["acc"]
    pal = {**ctx["pal"], "txt": sc["fg"], "txt2": sc["fg2"], "accent": acc,
           "on_accent": (255, 255, 255) if m._lum(acc) < 0.55 else (20, 24, 32)}
    return {**ctx, "pal": pal}


def background(size, pal, style, seed):
    W, H = size
    rnd = random.Random(_seed(seed))
    sc = style_colors(pal, style)
    q = 4 if W * H > 900_000 else 1
    w, h = max(1, W // q), max(1, H // q)
    cv = Image.new("RGBA", (w, h), sc["bg"] + (255,))
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cols = ([(pal["accent"], 70), (pal["s"], 60)] if style == "light"
            else [(pal["accent"], 150), (pal["s"], 190), (m._mix(pal["accent"], (255, 255, 255), .35), 90)])
    for i in range(5 if style == "mesh" else 3):
        col, al = cols[i % len(cols)]
        r = int(max(w, h) * rnd.uniform(.28, .55))
        cx, cy = int(rnd.uniform(-.1, 1.1) * w), int(rnd.uniform(-.1, 1.1) * h)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col + (al,))
    cv.alpha_composite(layer.filter(ImageFilter.GaussianBlur(max(2, int(max(w, h) * .12)))))
    if q > 1:
        cv = cv.resize((W, H), Image.BICUBIC)
    g = Image.fromarray(np.random.default_rng(_seed(seed)).normal(128, 20, (H, W)).clip(0, 255).astype("uint8"), "L")
    cv.alpha_composite(Image.merge("RGBA", (g, g, g, Image.new("L", (W, H), 9))))
    return cv


# ── primitives ─────────────────────────────────────────────────────────
def draw_title(cv, x, y, text, width, max_h, size, sc, s, highlight=True):
    f, lines, lh = m._fit(text or "", width, max_h, int(size * s), int(34 * s))
    d = ImageDraw.Draw(cv)
    for i, ln in enumerate(lines):
        last = i == len(lines) - 1
        if highlight and last and " " in ln:
            head, word = ln.rsplit(" ", 1)
            d.text((x, y), head + " ", font=f, fill=sc["fg"])
            d.text((x + f.getlength(head + " "), y), word, font=f, fill=sc["acc"])
        else:
            d.text((x, y), ln, font=f, fill=sc["acc"] if (highlight and last) else sc["fg"])
        y += lh
    return y


def draw_sub(cv, x, y, text, width, sc, s, size=36):
    if not text:
        return y
    f, ls, lh = m._fit(text, width, int(190 * s), int(size * s), int(22 * s), bold=False)
    d = ImageDraw.Draw(cv)
    y += int(14 * s)
    for ln in ls:
        d.text((x, y), ln, font=f, fill=sc["fg2"])
        y += lh
    return y


def frame_shot(img, kind, bw, bh, url, s):
    a = img.width / img.height
    if kind == "auto":
        kind = "mobile" if a < .8 else "web"
    if kind == "web":
        fw = int(min(bw, bh / (1 / a + .032)))
        fr = m._chrome(img.resize((max(1, fw), max(1, int(fw / a))), Image.LANCZOS), fw / 1440, url)
        rad = int(16 * fw / 1440 + 8)
    elif kind == "mobile":
        sh = int(min(bh / 1.03, bw / (a + .03)))
        fr = m._phone(img.resize((max(1, int(sh * a)), max(1, sh)), Image.LANCZOS), sh / 1000)
        rad = int(sh * .045)
    else:
        fw = int(min(bw, bh * a))
        fr = img.resize((max(1, fw), max(1, int(fw / a))), Image.LANCZOS).convert("RGBA")
        rad = int(14 * s)
    return m._round(fr, rad)


def with_shadow(rgba, blur, alpha=140, dy=0):
    pad = int(blur * 3)
    out = Image.new("RGBA", (rgba.width + 2 * pad, rgba.height + 2 * pad), (0, 0, 0, 0))
    black = Image.new("RGBA", rgba.size, (0, 0, 0, 255))
    black.putalpha(rgba.getchannel("A").point(lambda v: int(v * alpha / 255)))
    sh = Image.new("RGBA", out.size, (0, 0, 0, 0))
    sh.alpha_composite(black, (pad, pad + dy))
    out.alpha_composite(sh.filter(ImageFilter.GaussianBlur(blur)))
    out.alpha_composite(rgba, (pad, pad))
    return out, pad


def _coeffs(dst, src):
    A, B = [], []
    for (xd, yd), (xs, ys) in zip(dst, src):
        A.append([xd, yd, 1, 0, 0, 0, -xs * xd, -xs * yd]); B.append(xs)
        A.append([0, 0, 0, xd, yd, 1, -ys * xd, -ys * yd]); B.append(ys)
    return np.linalg.solve(np.array(A, float), np.array(B, float))


def tilted(fr, k=1.0, rot=-5.0):
    w, h = fr.size
    pad = int(max(w, h) * .06)
    dst = [(pad, pad), (pad + w, pad + .10 * h * k), (pad + w, pad + h - .10 * h * k), (pad, pad + h)]
    c = _coeffs(dst, [(0, 0), (w, 0), (w, h), (0, h)])
    out = fr.transform((w + 2 * pad, h + 2 * pad), Image.PERSPECTIVE, tuple(c), Image.BICUBIC)
    return out.rotate(rot, resample=Image.BICUBIC, expand=True) if rot else out


def card(shot, bw, bh, ctx, k=0.0, rot=0.0):
    fr = frame_shot(shot["img"], shot["kind"], bw, bh, ctx["url"], ctx["s"])
    if k or rot:
        fr = tilted(fr, k, rot)
    return with_shadow(fr, int(28 * ctx["s"]), 150, int(18 * ctx["s"]))[0]


def put(cv, layer, box):
    x0, y0, x1, y1 = [int(v) for v in box]
    bw, bh = max(1, x1 - x0), max(1, y1 - y0)
    if layer.width > bw or layer.height > bh:
        layer = ImageOps.contain(layer, (bw, bh), Image.LANCZOS)
    x, y = x0 + (bw - layer.width) // 2, y0 + (bh - layer.height) // 2
    m._over(cv, layer, (x, y))
    return x, y, layer.width, layer.height


def _head(cv, ctx, c2, sc, x, y, width, max_h, size):
    s = ctx["s"]
    if ctx.get("badge"):
        y = m._badge(cv, c2, ctx["badge"], x, y) + int(26 * s)
    y = draw_title(cv, x, y, ctx.get("titre"), width, max_h, size, sc, s)
    return draw_sub(cv, x, y, ctx.get("sous"), width, sc, s)


# ── modèles ────────────────────────────────────────────────────────────
def t_tilt(ctx, shots, style, seed):
    W, H, s, mg = ctx["W"], ctx["H"], ctx["s"], ctx["m"]
    sc = style_colors(ctx["pal"], style)
    c2, cv, land = with_style(ctx, sc), background((W, H), ctx["pal"], style, seed), ctx["W"] / ctx["H"] > 1.3
    if land:
        _head(cv, ctx, c2, sc, mg, mg, int(W * .40) - mg, int(H * .5), 64)
        put(cv, card(shots[0], int(W * .55), int(H * .82), c2, 1.0, -4), (W * .38, mg // 2, W, H - mg // 2))
        m._footer_left(cv, c2, mg, H - mg)
    else:
        y = _head(cv, ctx, c2, sc, mg, mg, W - 2 * mg, int(H * .24), 86)
        foot = int(120 * s)
        put(cv, card(shots[0], W - mg, int(H * .58), c2, 1.0, -4), (0, y + int(20 * s), W, H - foot))
        m._footer(cv, c2, H - foot // 2)
    m._credit(cv, c2)
    return cv


def t_glass(ctx, shots, style, seed):
    W, H, s, mg = ctx["W"], ctx["H"], ctx["s"], ctx["m"]
    sc = style_colors(ctx["pal"], "dark")
    c2, land = with_style(ctx, sc), W / H > 1.3
    base = ImageOps.fit(shots[0]["img"].convert("RGB"), (W, H), Image.LANCZOS).filter(ImageFilter.GaussianBlur(int(36 * s))).convert("RGBA")
    base.alpha_composite(Image.new("RGBA", (W, H), ctx["pal"]["p"] + (180,)))
    cv = base
    box = (mg, mg, int(W * .5), H - mg) if land else (mg, int(mg * 1.2), W - mg, int(H * .40))
    gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(gl).rounded_rectangle(box, radius=int(36 * s), fill=(255, 255, 255, 36), outline=(255, 255, 255, 110), width=2)
    cv.alpha_composite(gl)
    pad = int(40 * s)
    _head(cv, ctx, c2, sc, box[0] + pad, box[1] + pad, box[2] - box[0] - 2 * pad, int((box[3] - box[1]) * .6), 70 if land else 80)
    if land:
        put(cv, card(shots[0], int(W * .46), int(H * .8), c2, .6, -3), (W * .5, 0, W, H))
        m._footer_left(cv, c2, mg, H - mg)
    else:
        foot = int(120 * s)
        put(cv, card(shots[0], W - mg, int(H * .52), c2, .6, -3), (0, int(H * .38), W, H - foot))
        m._footer(cv, c2, H - foot // 2)
    m._credit(cv, c2)
    return cv


def t_duo(ctx, shots, style, seed):
    W, H, s, mg = ctx["W"], ctx["H"], ctx["s"], ctx["m"]
    sc = style_colors(ctx["pal"], style)
    c2, cv, land = with_style(ctx, sc), background((W, H), ctx["pal"], style, seed), W / H > 1.3
    if land:
        _head(cv, ctx, c2, sc, mg, mg, int(W * .34) - mg, int(H * .5), 58)
        put(cv, card(shots[0], int(W * .46), int(H * .62), c2, .6, -3), (W * .30, mg // 2, W * .80, H * .78))
        put(cv, card(shots[1], int(W * .46), int(H * .62), c2, .6, 3), (W * .52, H * .22, W, H))
        m._footer_left(cv, c2, mg, H - mg)
    else:
        y = _head(cv, ctx, c2, sc, mg, mg, W - 2 * mg, int(H * .22), 80)
        foot, y1 = int(120 * s), H - int(120 * s)
        y0 = y + int(20 * s)
        put(cv, card(shots[0], int(W * .70), int(H * .44), c2, .6, -4), (0, y0, W * .74, y1))
        put(cv, card(shots[1], int(W * .70), int(H * .44), c2, .6, 4), (W * .26, y0 + (y1 - y0) * .24, W, y1 + int(10 * s)))
        m._footer(cv, c2, H - foot // 2)
    return cv


def t_checklist(ctx, shots, style, seed):
    pts = (ctx.get("points") or [])[:4]
    if not pts and shots:
        return t_tilt(ctx, shots, style, seed)
    W, H, s, mg = ctx["W"], ctx["H"], ctx["s"], ctx["m"]
    sc = style_colors(ctx["pal"], style)
    c2, cv, land = with_style(ctx, sc), background((W, H), ctx["pal"], style, seed), W / H > 1.3
    width = int(W * .46) - mg if land else W - 2 * mg
    y = _head(cv, ctx, c2, sc, mg, mg, width, int(H * .26), 64 if land else 76) + int(24 * s)
    d = ImageDraw.Draw(cv)
    r = int(24 * s)
    row = int((84 if land else 96) * s)
    for p in pts:
        cx, cy = mg + r, y + row // 2 - int(6 * s)
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=sc["acc"])
        d.line([(cx - r * .45, cy), (cx - r * .1, cy + r * .38), (cx + r * .52, cy - r * .36)], fill=c2["pal"]["on_accent"], width=max(3, int(r * .28)))
        f, ls, lh = m._fit(p, width - 2 * r - int(20 * s), row, int(40 * s), int(22 * s), bold=False)
        ty = cy - (len(ls) * lh) // 2
        for ln in ls[:2]:
            d.text((mg + 2 * r + int(18 * s), ty), ln, font=f, fill=sc["fg"])
            ty += lh
        y += row
    if shots:
        if land:
            put(cv, card(shots[0], int(W * .5), int(H * .8), c2, .8, -3), (W * .46, 0, W, H))
        else:
            im = card(shots[0], W - mg, int(H * .5), c2, .8, -3)
            im = ImageOps.contain(im, (W, int(H * .5)), Image.LANCZOS)
            m._over(cv, im, ((W - im.width) // 2, min(H - int(H * .22), y + int(20 * s))))
    if land:
        m._footer_left(cv, c2, mg, H - mg)
    else:
        m._footer(cv, c2, H - int(60 * s))
    return cv


def t_quote(ctx, shots, style, seed):
    W, H, s, mg = ctx["W"], ctx["H"], ctx["s"], ctx["m"]
    style = style if style != "light" else "dark"
    sc = style_colors(ctx["pal"], style)
    c2, cv, land = with_style(ctx, sc), background((W, H), ctx["pal"], style, seed), W / H > 1.3
    gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(gl).text((mg, int(mg * (.1 if land else .6))), "“", font=m._font(int(420 * s)), fill=sc["acc"] + (95,))
    cv.alpha_composite(gl)
    y = int(H * (.26 if land else .30))
    y = draw_title(cv, mg, y, ctx.get("titre"), W - 2 * mg, int(H * .42), 78 if not land else 56, sc, s, highlight=False)
    y += int(30 * s)
    ImageDraw.Draw(cv).text((mg, y), f"— {ctx['brand']}", font=m._font(int(36 * s)), fill=sc["acc"])
    m._footer(cv, c2, H - int(70 * s))
    return cv


def t_bold(ctx, shots, style, seed):
    W, H, s, mg = ctx["W"], ctx["H"], ctx["s"], ctx["m"]
    style = style if style != "light" else "aurora"
    sc = style_colors(ctx["pal"], style)
    c2, cv, land = with_style(ctx, sc), background((W, H), ctx["pal"], style, seed), W / H > 1.3
    img, foc = shots[0]["img"], shots[0].get("focus")
    crop = m._crop_focus(img, foc) if foc else img.crop((0, 0, img.width, int(img.height * .55)))
    if land:
        y = mg
        if ctx.get("badge"):
            y = m._badge(cv, c2, ctx["badge"], mg, y) + int(20 * s)
        draw_title(cv, mg, y, ctx.get("titre"), int(W * .50) - mg, int(H * .62), 110, sc, s)
        tw, th = int(W * .42), int(H * .74)
        strip = m._round(ImageOps.fit(crop.convert("RGB"), (tw, th), Image.LANCZOS), int(26 * s))
        put(cv, with_shadow(strip, int(24 * s), 150, int(14 * s))[0], (W * .52, 0, W, H))
        m._footer_left(cv, c2, mg, H - mg)
    else:
        y = mg
        if ctx.get("badge"):
            y = m._badge(cv, c2, ctx["badge"], mg, y) + int(24 * s)
        draw_title(cv, mg, y, ctx.get("titre"), W - 2 * mg, int(H * .46), 150, sc, s)
        foot = int(120 * s)
        sh_h = int(H * .30)
        strip = m._round(ImageOps.fit(crop.convert("RGB"), (W - 2 * mg, sh_h), Image.LANCZOS), int(28 * s))
        sh = with_shadow(strip, int(24 * s), 150, int(14 * s))[0]
        m._over(cv, sh, ((W - sh.width) // 2, H - foot - sh_h - int(40 * s)))
        m._footer(cv, c2, H - foot // 2)
    return cv


_FN = {"tilt": t_tilt, "glass": t_glass, "duo": t_duo, "checklist": t_checklist, "quote": t_quote, "bold": t_bold}


def render(tpl, ctx, shots, job):
    seed = f"{ctx.get('titre')}|{tpl}|{len(shots)}"
    style = job.get("style") or random.Random(_seed(seed)).choice(STYLES)
    if tpl in ("tilt", "glass", "duo", "bold") and not shots:
        return m.t_carte(ctx)
    if tpl == "duo" and len(shots) < 2:
        tpl = "tilt"
    return _FN[tpl](ctx, shots, style, seed)