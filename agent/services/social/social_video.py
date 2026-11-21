# services/social/social_video.py
import asyncio
import logging
import math
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from PIL import Image, ImageDraw

from agent.services.social import social_assets as assets
from agent.services.social import social_montage as m
from agent.services.social import social_montage2 as m2
from agent.services.social import social_music as music
from agent.services.social.social_config import PUBLIC_BASE_URL, UPLOAD_DIR

logger = logging.getLogger("social_video")
W, H, TRANS = 1080, 1920, 0.38
FPS = int(os.getenv("SOCIAL_VIDEO_FPS", "24"))
TYPES = ("hook", "capture", "zoom", "cta")
MOODS = ("energique", "inspirant", "calme", "corporate")
SYSTEM_VIDEO = ("Tu es réalisateur de vidéos courtes verticales (TikTok / Reels) pour une marque B2B. Rythme vif, phrases "
                "ultra courtes. Tu n'inventes aucun chiffre ni fonctionnalité absente des captures fournies. JSON strict uniquement.")


def cl(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def eo(t):
    t = cl(t)
    return 1 - (1 - t) ** 3


def eb(t):
    t = cl(t)
    c1 = 1.70158
    return 1 + (c1 + 1) * (t - 1) ** 3 + c1 * (t - 1) ** 2


def _fade(layer, a):
    if a >= .995:
        return layer
    out = layer.copy()
    out.putalpha(layer.getchannel("A").point([int(i * a) for i in range(256)]))
    return out


def _paste(fr, layer, x, y, a=1.0):
    if a <= .01:
        return
    L = _fade(layer, a)
    fr.paste(L, (int(x), int(y)), L)


def pill(text, fill, fg, size, px=34, py=18):
    f = m._font(size)
    w, h = int(f.getlength(text)) + 2 * px, size + 2 * py
    L = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=h // 2, fill=tuple(fill) + (255,))
    d.text((w // 2, h // 2), text, font=f, fill=fg, anchor="mm")
    return L


def lines_layers(text, width, max_h, size, min_size, fill, bold=True, align="left"):
    f, lines, lh = m._fit(text or "", width, max_h, size, min_size, bold=bold)
    out = []
    for ln in lines:
        L = Image.new("RGBA", (width, int(lh * 1.3)), (0, 0, 0, 0))
        d = ImageDraw.Draw(L)
        x = 0 if align == "left" else int((width - f.getlength(ln)) / 2)
        d.text((x + 3, 7), ln, font=f, fill=(0, 0, 0, 90))
        d.text((x, 4), ln, font=f, fill=fill)
        out.append(L)
    return out, lh


def blit(fr, layers, x, y, lh, t, d0=.12, step=.13, rise=46):
    for k, L in enumerate(layers):
        a = eo((t - d0 - step * k) / .42)
        _paste(fr, L, x, y + k * lh + (1 - a) * rise, a)


# ═════════════════════ PLAN (LLM) ═════════════════════
def _fallback(text, ids, catalog, brand, cta):
    first = (text.strip().splitlines() or [brand])[0][:60]
    sc = [{"type": "hook", "asset_id": None, "titre": first, "sous_titre": "", "dur": 3.0}]
    for i in ids[:4]:
        a = catalog[i]
        lm = (a.get("legendes_montage") or [{}])[0]
        sc.append({"type": "capture", "asset_id": i, "titre": lm.get("titre") or a.get("titre_court", ""),
                   "sous_titre": lm.get("sous_titre", ""), "dur": 3.6})
    sc.append({"type": "cta", "asset_id": None, "titre": cta or f"Découvrez {brand}", "sous_titre": "", "dur": 3.0})
    return {"musique": "energique", "scenes": sc, "voix_off": "", "cta": cta}


async def make_plan(llm_json, brand, text, script, ids, catalog, cible, voix):
    cat = "\n".join(f"[{i}] {catalog[i].get('titre_court')} | module={catalog[i].get('module')} | "
                    f"visible: {'; '.join((catalog[i].get('fonctionnalites_visibles') or [])[:5])}" for i in ids)
    user = f"""Marque : {brand.nom} — {brand.site_url}
Post : {text[:900]}
Script proposé : {(script or '')[:700]}
CAPTURES DISPONIBLES :
{cat}
Durée cible : {cible}s. Écris TOUJOURS le champ voix_off : texte parlé et sous-titré (≤ 70 mots, phrases courtes de 4 à 8 mots, naturelles, sans emoji).
JSON : {{"musique":"energique|inspirant|calme|corporate","cta":"≤6 mots",
"voix_off":"","scenes":[{{"type":"hook|capture|zoom|cta","asset_id":"id ou null","titre":"≤7 mots percutants","sous_titre":"≤12 mots","duree":2.5}}]}}
Règles : scène 1 = hook (accroche choc), 3 à 5 scènes capture/zoom avec UNIQUEMENT les asset_id ci-dessus, dernière = cta."""
    try:
        raw = await llm_json(user, SYSTEM_VIDEO, temperature=0.7, max_tokens=1800)
    except Exception as e:
        logger.warning("Plan vidéo LLM KO : %s", e)
        raw = {}
    cta = str(raw.get("cta") or "")[:50]
    scenes = []
    for s in (raw.get("scenes") or [])[:7]:
        if not isinstance(s, dict):
            continue
        typ = s.get("type") if s.get("type") in TYPES else "capture"
        aid = s.get("asset_id") if s.get("asset_id") in ids else None
        if typ in ("capture", "zoom") and not aid:
            aid = ids[len([x for x in scenes if x["type"] in ("capture", "zoom")]) % len(ids)] if ids else None
            typ = typ if aid else "hook"
        if typ == "zoom" and not catalog.get(aid, {}).get("zone_focus"):
            typ = "capture"
        try:
            dur = float(s.get("duree") or 3.2)
        except (TypeError, ValueError):
            dur = 3.2
        scenes.append({"type": typ, "asset_id": aid, "titre": str(s.get("titre") or "")[:70],
                       "sous_titre": str(s.get("sous_titre") or "")[:120], "dur": cl(dur, 2.2, 4.8)})
    voix_off = str(raw.get("voix_off") or "")[:600]
    mood = raw.get("musique") if raw.get("musique") in MOODS else "energique"
    if len(scenes) < 3 or scenes[0]["type"] != "hook":
        plan = _fallback(text, ids, catalog, brand.nom, cta)
        plan["voix_off"], plan["musique"] = voix_off, mood
        return plan
    if scenes[-1]["type"] != "cta":
        scenes.append({"type": "cta", "asset_id": None, "titre": cta or f"Découvrez {brand.nom}", "sous_titre": "", "dur": 3.0})
    return {"musique": mood, "scenes": scenes, "voix_off": voix_off, "cta": cta}


def _scale(scenes, target):
    nominal = sum(s["dur"] for s in scenes) - TRANS * (len(scenes) - 1)
    k = cl(target / max(nominal, 1), .7, 1.5)
    for s in scenes:
        s["dur"] = round(max(2.0, s["dur"] * k), 2)


def _probe(path) -> float:
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
                           capture_output=True, text=True, timeout=30)
        return float(r.stdout.strip())
    except Exception:
        return 0.0


# ═════════════════════ RENDU ═════════════════════
def _prep(sc, i, shot, ctx, style, seed):
    s, typ = ctx["s"], sc["type"]
    if typ in ("capture", "zoom") and not shot:
        typ = "hook"
    col = m2.style_colors(ctx["pal"], style)
    fg, fg2 = col["fg"] + (255,), col["fg2"] + (255,)
    on_acc = (255, 255, 255) if m._lum(col["acc"]) < .55 else (20, 24, 32)
    p = {"type": typ, "dur": sc["dur"], "col": col,
         "bg": m2.background((W, H), ctx["pal"], style, f"{seed}-{i}").convert("RGB")}
    if typ == "hook":
        tl, lh = lines_layers(sc["titre"], W - 200, int(H * .4), int(124 * s), 60, fg, align="center")
        y0 = (H - len(tl) * lh) // 2 - 80
        p.update(tl=tl, lh=lh, tx=100, ty=y0, bar_y=y0 - 46, pill=pill(ctx["brand"].upper(), col["acc"], on_acc, 34))
        if sc.get("sous_titre"):
            p["sl"], p["slh"] = lines_layers(sc["sous_titre"], W - 240, 300, int(46 * s), 28, fg2, bold=False, align="center")
            p["sy"] = y0 + len(tl) * lh + 30
    elif typ == "cta":
        tl, lh = lines_layers(sc["titre"], W - 200, int(H * .3), int(104 * s), 56, fg, align="center")
        p.update(tl=tl, lh=lh, tx=100, ty=int(H * .40))
        p["logo"] = (m._logo_pill({"logo": ctx["logo"]}, 120) if ctx["logo"] is not None
                     else pill(ctx["brand"], (255, 255, 255), (20, 24, 32), 56))
        p["site"] = pill(ctx["site"] or ctx["brand"], col["acc"], on_acc, 46)
    else:
        img, kind = shot["img"], shot["kind"]
        if typ == "zoom" and shot.get("focus"):
            img, kind = m._crop_focus(img, shot["focus"]), "plain"
        fr = m2.frame_shot(img, kind, W - 140, int(H * .46), ctx["url"], s)
        p["card"] = m2.with_shadow(fr, int(30 * s), 150, int(20 * s))[0]
        tl, lh = lines_layers(sc["titre"], W - 160, int(H * .2), int(88 * s), 48, fg)
        p.update(tl=tl, lh=lh, tx=80, ty=250)
        if sc.get("badge"):
            p["pill"] = pill(str(sc["badge"]).upper(), col["acc"], on_acc, 30, 28, 14)
        if sc.get("sous_titre"):
            p["sl"], p["slh"] = lines_layers(sc["sous_titre"], W - 160, 200, int(40 * s), 26, fg2, bold=False)
            p["sy"] = 250 + len(tl) * lh + 8
    return p


def _scene(p, t):
    fr, d, typ = p["bg"].copy(), p["dur"], p["type"]
    if typ == "hook":
        _paste(fr, p["pill"], (W - p["pill"].width) // 2, int(H * .2), eo(t / .4))
        bw = int(eo((t - .35) / .5) * (W - 360))
        if bw > 0:
            ImageDraw.Draw(fr).rounded_rectangle([180, p["bar_y"], 180 + bw, p["bar_y"] + 14], radius=7, fill=p["col"]["acc"])
        blit(fr, p["tl"], p["tx"], p["ty"], p["lh"], t)
        if "sl" in p:
            blit(fr, p["sl"], 120, p["sy"], p["slh"], t, d0=.5)
    elif typ == "cta":
        lg = p["logo"]
        a = eo(t / .4)
        sc = .8 + .2 * eb(t / .6)
        lg2 = lg.resize((max(1, int(lg.width * sc)), max(1, int(lg.height * sc))), Image.BILINEAR)
        _paste(fr, lg2, (W - lg2.width) // 2, int(H * .24), a)
        blit(fr, p["tl"], p["tx"], p["ty"], p["lh"], t, d0=.25)
        st = p["site"]
        pulse = 1 + .035 * math.sin(t * 5)
        s2 = st.resize((int(st.width * pulse), int(st.height * pulse)), Image.BILINEAR)
        _paste(fr, s2, (W - s2.width) // 2, int(H * .64), eo((t - .7) / .4))
    else:
        card = p["card"]
        tin = eb(t / .55)
        scale = (.82 + .18 * tin) * (1 + .07 * t / d)
        im = card.resize((max(1, int(card.width * scale)), max(1, int(card.height * scale))), Image.BILINEAR)
        cx, cy = W // 2, int(H * .60)
        _paste(fr, im, cx - im.width // 2, cy - im.height // 2 + (1 - cl(tin, 0, 1)) * 90 - 18 * t / d, eo(t / .35))
        if "pill" in p:
            _paste(fr, p["pill"], 80, 170, eo(t / .3))
        blit(fr, p["tl"], p["tx"], p["ty"], p["lh"], t)
        if "sl" in p:
            blit(fr, p["sl"], 80, p["sy"], p["slh"], t, d0=.45)
    return fr


def _transition(a, b, k, style):
    e = eo(k)
    if style == "slide":
        c = Image.new("RGB", (W, H))
        c.paste(a, (0, -int(e * H)))
        c.paste(b, (0, H - int(e * H)))
        return c
    if style == "push":
        c = Image.new("RGB", (W, H))
        c.paste(a, (-int(e * W), 0))
        c.paste(b, (W - int(e * W), 0))
        return c
    return Image.blend(a, b, e)


# ═════════════════════ SOUS-TITRES ═════════════════════
def _chunk(marks, n=5):
    out, buf = [], []

    def flush():
        if buf:
            out.append((buf[0][0], buf[-1][1], " ".join(b[2] for b in buf)))
        buf.clear()
    for s, e, t in marks:
        words = t.split()
        if len(words) > n:
            flush()
            step = (e - s) / max(1, len(words))
            for i in range(0, len(words), n):
                seg = words[i:i + n]
                out.append((s + i * step, s + (i + len(seg)) * step, " ".join(seg)))
        else:
            buf.append((s, e, t))
            if len(buf) >= n or t.endswith((".", "!", "?")):
                flush()
    flush()
    return out


def _synthetic_subs(text: str, total: float, lead=.7, tail=1.3):
    """Sous-titres sans voix : le texte est réparti sur la durée de la vidéo."""
    words = (text or "").split()
    if not words:
        return []
    chunks, buf = [], []
    for w in words:
        buf.append(w)
        if len(buf) >= 5 or (len(buf) >= 3 and w.endswith((".", "!", "?", ","))):
            chunks.append(buf)
            buf = []
    if buf:
        chunks.append(buf)
    per = max(2.0, total - lead - tail) / len(words)
    t, out = lead, []
    for c in chunks:
        dur = per * len(c)
        out.append((t, t + dur, " ".join(c)))
        t += dur
    return out


async def _tts(text, path):
    try:
        import edge_tts
        voice = os.getenv("SOCIAL_VOICE", "fr-FR-DeniseNeural")
        try:
            com = edge_tts.Communicate(text, voice, boundary="WordBoundary")
        except TypeError:
            com = edge_tts.Communicate(text, voice)
        marks = []
        with open(path, "wb") as f:
            async for ch in com.stream():
                if ch["type"] == "audio":
                    f.write(ch["data"])
                elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                    marks.append((ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7, ch["text"]))
        return path, _chunk(marks)
    except Exception as e:
        logger.warning("Voix off indisponible : %s", e)
        return None


def _caption_layer(text):
    f, lines, lh = m._fit(text, W - 220, 300, 54, 34)
    h = len(lines) * lh + 40
    L = Image.new("RGBA", (W - 120, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    d.rounded_rectangle([0, 0, L.width - 1, h - 1], radius=28, fill=(0, 0, 0, 185))
    y = 20
    for ln in lines:
        d.text((L.width // 2, y + lh // 2), ln, font=f, fill=(255, 255, 255, 255), anchor="mm")
        y += lh
    return L


def _finish(fr, g, total, ctx, wm, cap=None):
    ImageDraw.Draw(fr).rectangle([0, 0, int(W * g / total), 8], fill=ctx["pal"]["accent"])
    fr.paste(wm, (60, 130), wm)
    if cap is not None:
        fr.paste(cap, (60, int(H * 0.78)), cap)
    return fr


def _render(job):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg est absent du conteneur")
    pal = m._pal(job["couleurs"])
    logo = None
    if job.get("logo"):
        try:
            logo = m._flatten(Image.open(job["logo"])).convert("RGBA")
        except Exception:
            pass
    domain = re.sub(r"^https?://(www\.)?", "", job["site"] or "").strip("/")
    ctx = {"pal": pal, "brand": job["brand"], "site": domain, "url": domain or "app", "logo": logo, "s": W / 1080}
    shots = {}
    for a in job["assets"]:
        try:
            shots[a["id"]] = m._prep_shot(a)
        except Exception as e:
            logger.warning("Capture %s illisible : %s", a["id"], e)
    styles = ["aurora", "dark", "mesh"]
    prep = [_prep(sc, i, shots.get(sc.get("asset_id")), ctx, styles[i % 3], job["seed"]) for i, sc in enumerate(job["scenes"])]
    starts, t = [], 0.0
    for i, p in enumerate(prep):
        starts.append(t)
        t += p["dur"] - (TRANS if i < len(prep) - 1 else 0)
    total = starts[-1] + prep[-1]["dur"]
    wm = pill(ctx["brand"], (0, 0, 0), (255, 255, 255), 26, 22, 10)
    wm.putalpha(wm.getchannel("A").point(lambda v: int(v * .45)))
    trans = ["fade", "slide", "push"]
    caps = [(s, e, _caption_layer(tx)) for s, e, tx in (job.get("subs") or []) if s < total]

    ci = min(1, len(prep) - 1)
    _finish(_scene(prep[ci], min(1.5, prep[ci]["dur"] - .1)), 1.5, total, ctx, wm).save(job["cover"], "JPEG", quality=90)

    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-stream_loop", "-1", "-i", str(job["audio"])]
    fo = max(0, total - 1.4)
    if job.get("voice"):
        cmd += ["-i", str(job["voice"]), "-filter_complex",
                f"[1:a]volume=0.22,afade=t=in:st=0:d=.6,afade=t=out:st={fo:.2f}:d=1.4[mu];"
                f"[2:a]adelay=400|400,volume=1.15[vo];[mu][vo]amix=inputs=2:duration=longest:normalize=0[aout]",
                "-map", "0:v", "-map", "[aout]"]
    else:
        cmd += ["-map", "0:v", "-map", "1:a", "-af", f"afade=t=in:st=0:d=.6,afade=t=out:st={fo:.2f}:d=1.4"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "160k", "-t", f"{total:.2f}", "-movflags", "+faststart", str(job["out"])]
    errf = tempfile.TemporaryFile()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=errf)
    try:
        for n in range(int(total * FPS)):
            g = n / FPS
            i = max(k for k in range(len(prep)) if starts[k] <= g)
            cur = _scene(prep[i], g - starts[i])
            if i > 0 and g < starts[i] + TRANS:
                prev = _scene(prep[i - 1], g - starts[i - 1])
                cur = _transition(prev, cur, (g - starts[i]) / TRANS, trans[i % 3])
            cap = next((L for s, e, L in caps if s <= g < e), None)
            proc.stdin.write(_finish(cur, g, total, ctx, wm, cap).tobytes())
    except BrokenPipeError:
        pass
    finally:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.wait(timeout=300)
        except subprocess.TimeoutExpired:
            proc.kill()
            raise RuntimeError("ffmpeg : délai dépassé")
    if proc.returncode != 0:
        errf.seek(0)
        raise RuntimeError("ffmpeg : " + (errf.read().decode(errors="ignore")[-400:] or "échec"))
    return total


async def build_video(spec, platform, brand, cfg, text, llm_json, script=""):
    catalog = {a["id"]: a for a in assets.list_assets()}
    ids = [i for i in (spec.get("asset_ids") or []) if i in catalog][:5]
    if not ids:
        raise RuntimeError("Vidéo : aucune capture exploitable")
    cible = int(cl(int(cfg.get("video_duree_cible", 22)), 12, 40))
    voix = bool(cfg.get("video_voix_off"))
    want_subs = cfg.get("video_sous_titres", True)
    plan = await make_plan(llm_json, brand, text, script, ids, catalog, cible, voix)
    for sc in plan["scenes"]:
        a = catalog.get(sc.get("asset_id") or "")
        if a and sc["type"] in ("capture", "zoom"):
            sc["badge"] = str(a.get("module") or "").replace("_", " ")
            if not sc["titre"]:
                sc["titre"] = (a.get("legendes_montage") or [{}])[0].get("titre") or a.get("titre_court", "")
    if not plan.get("voix_off"):
        plan["voix_off"] = ". ".join(s["titre"] for s in plan["scenes"] if s.get("titre"))[:600]

    name = uuid.uuid4().hex
    out, cover = Path(UPLOAD_DIR) / f"{name}.mp4", Path(UPLOAD_DIR) / f"{name}_cover.jpg"

    voice, subs = None, []
    if voix and plan["voix_off"]:
        vp = Path(UPLOAD_DIR) / f"{name}_voice.mp3"
        res = await _tts(plan["voix_off"], vp)
        if res:
            vd = await asyncio.to_thread(_probe, vp)
            if vd > 3:
                voice = vp
                subs = [(s + .4, e + .4, tx) for s, e, tx in res[1]]
                cible = int(cl(vd + 1.2, 12, 45))

    _scale(plan["scenes"], cible)
    total_est = sum(s["dur"] for s in plan["scenes"]) - TRANS * (len(plan["scenes"]) - 1)
    if not want_subs:
        subs = []
    elif not subs:
        subs = _synthetic_subs(plan["voix_off"], total_est)       # sous-titres même sans voix off

    seed = int(name[:6], 16)
    audio = await asyncio.to_thread(music.make_track, total_est + 2, plan["musique"], seed)
    job_assets = []
    for i in ids:
        a = catalog[i]
        job_assets.append({"id": i, "path": str(assets.asset_path(a)), "zones": a.get("zones_sensibles") or [],
                           "focus": a.get("zone_focus"), "appareil": a.get("appareil")})
    logo = assets.find_logo(cfg)
    job = {"couleurs": cfg["couleurs"], "brand": brand.nom, "site": brand.site_url, "assets": job_assets,
           "scenes": plan["scenes"], "audio": audio, "voice": voice, "subs": subs, "out": out, "cover": cover,
           "seed": name, "logo": str(logo) if logo else None}

    total = await asyncio.to_thread(_render, job)
    if voice:
        Path(voice).unlink(missing_ok=True)
    final = {**spec, "template": "video", "asset_ids": ids,
             "cover": f"{PUBLIC_BASE_URL}/uploads/social/{name}_cover.jpg",
             "musique": plan["musique"], "duree": round(total, 1), "sous_titres": bool(subs), "voix": bool(voice),
             "scenes": [{k: sc.get(k) for k in ("type", "titre", "asset_id")} for sc in plan["scenes"]]}
    return {"urls": [f"{PUBLIC_BASE_URL}/uploads/social/{name}.mp4"], "spec": final}