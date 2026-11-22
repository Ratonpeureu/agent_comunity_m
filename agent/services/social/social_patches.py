"""Correctifs appliqués au démarrage (aucun fichier d'origine à modifier)."""
import asyncio
import hashlib
import os
import random
import re

from agent.services.social import social_agent_service as svc
from agent.services.social import social_assets as assets
from agent.services.social import social_montage as montage
from agent.services.social import social_unsplash as stock
from agent.services.social.social_config import PUBLIC_BASE_URL, SPECS

_done = False


# ───────────────────────── 1. finalize_spec ─────────────────────────
def finalize_spec(spec, platform: str, text: str, catalog: dict, cfg: dict | None = None, stats: dict | None = None,
                  stock_ok: bool = False, visuel_requis: bool = False) -> dict:
    cfg = cfg or {}
    spec = dict(spec or {})
    manual = bool(spec.get("manual"))          # l'utilisateur a choisi : on respecte son choix
    tpl = spec.get("template") or {"carte": "carte", "image_ia": "photo_overlay", "aucun": "aucun"}.get(spec.get("type"))
    if tpl == "split":
        tpl = "capture_cadree"
    allow = bool(cfg.get("autoriser_captures_sensibles"))
    use_caps = cfg.get("utiliser_captures", True)
    usable = {i: a for i, a in catalog.items() if assets.eligible(a, allow)}
    no_visual_mode = cfg.get("mode_visuel") == "aucun" and not manual
    if (tpl == "aucun" or no_visual_mode) and not visuel_requis:
        return {"template": "aucun", "asset_ids": []}
    if tpl == "aucun":
        tpl = None

    # ── plateformes : la vidéo n'est plus transformée en carrousel ──
    if platform == "tiktok":
        if tpl not in ("video", "carrousel", "photo_overlay"):
            tpl = "video" if cfg.get("video_tiktok", True) else "carrousel"

    rnd = random.Random(hashlib.md5(f"{platform}|{text or 'x'}".encode()).hexdigest())
    if (not manual and cfg.get("varier_montages", True) and tpl in (None, "capture_cadree")
            and platform != "tiktok"):
        tpl = rnd.choice(assets.VARIETY)

    excl = set()
    ids = [i for i in (spec.get("asset_ids") or []) if i in usable]
    if spec.get("reshuffle"):
        excl, ids = set(ids), []
    slides = [dict(sl) for sl in (spec.get("slides") or []) if isinstance(sl, dict) and sl.get("asset_id") in usable]
    uq = (spec.get("unsplash_query") or "").strip()

    if use_caps and not ids and not slides and tpl not in ("carte", "photo_overlay", "quote"):
        k = 5 if tpl in ("carrousel", "video") else 2 if tpl == "duo" else 1
        short = [a for a in assets.shortlist(f"{text[:300]} {spec.get('titre_carte') or ''}", platform, k + 2,
                                             stats, allow, excl) if a["id"] in usable]
        ids = [a["id"] for a in short[:k]]
    if not tpl:
        tpl = "capture_cadree" if (ids or slides) else ("photo_overlay" if stock_ok and uq else "carte")
    if tpl not in assets.TEMPLATES:
        tpl = "capture_cadree" if ids else "carte"

    if tpl == "carrousel":
        if len(slides) < 2 and len(ids) >= 2:
            slides = [{"asset_id": i} for i in ids]
        if len(slides) < 2:
            if slides and not ids:
                ids = [slides[0]["asset_id"]]
            slides, tpl = [], ("capture_cadree" if ids else "carte")
    if tpl == "video":
        if not ids and slides:
            ids = [sl["asset_id"] for sl in slides]
        if ids:
            ids, slides = ids[:5], []
        else:
            tpl = "photo_overlay" if (stock_ok and uq) else "carte"
    if tpl in ("capture_cadree", "capture_zoom", "tilt", "glass", "bold") and not ids:
        tpl = "photo_overlay" if (stock_ok and uq) else "carte"
    if tpl == "duo":
        if len(ids) < 2:
            extra = [a["id"] for a in assets.shortlist(text[:300], platform, 4, stats, allow, set(ids)) if a["id"] in usable]
            ids = (ids + extra)[:2]
        tpl = "duo" if len(ids) >= 2 else ("tilt" if ids else "carte")
    if tpl == "photo_overlay" and not (stock_ok and uq):
        tpl = "capture_cadree" if ids else "carte"
    if tpl == "capture_zoom" and ids and not usable[ids[0]].get("zone_focus"):
        tpl = "capture_cadree"

    if tpl == "carrousel":
        slides = slides[:int(cfg.get("carrousel_max_slides", 5))]
        ids = [sl["asset_id"] for sl in slides]
        for sl in slides:
            a = usable[sl["asset_id"]]
            lm = (a.get("legendes_montage") or [{}])[0]
            sl["titre"] = sl.get("titre") or lm.get("titre") or a.get("titre_court", "")
            sl["sous_titre"] = sl.get("sous_titre") or lm.get("sous_titre", "")
    elif tpl not in ("duo", "video"):
        ids, slides = ids[:1], []

    first = usable.get(ids[0]) if ids else None
    lm = ((first or {}).get("legendes_montage") or [{}])[0]
    badge = spec.get("badge") or str((first or {}).get("module") or "").replace("_", " ")
    if badge.lower() in ("autre", "marque"):
        badge = ""
    points = [str(p)[:70] for p in (spec.get("points") or []) if p][:4] or \
             [str(p)[:70] for p in ((first or {}).get("fonctionnalites_visibles") or [])[:4]]
    return {"template": tpl, "asset_ids": ids,
            "titre_carte": (spec.get("titre_carte") or lm.get("titre") or (first or {}).get("titre_court") or "")[:90],
            "sous_titre": (spec.get("sous_titre") or lm.get("sous_titre") or "")[:140],
            "badge": badge[:24], "unsplash_query": uq[:80], "slides": slides, "ratio": spec.get("ratio"),
            "points": points, "style": spec.get("style")}


# ───────────────────────── 2. render_visual (style + points transmis) ─────────────────────────
async def render_visual(spec: dict, platform: str, brand, cfg: dict) -> dict:
    catalog = {a["id"]: a for a in assets.list_assets(include_excluded=True)}
    size = montage.size_for(platform, spec.get("ratio"))
    spec = dict(spec)
    tpl = spec["template"]
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
           "credit": photo["credit"] if photo else None, "logo": str(logo) if logo else None,
           "points": spec.get("points") or [], "style": spec.get("style") or None}      # ← manquaient
    names = await asyncio.to_thread(montage._render_sync, job)
    final = dict(spec)
    if photo:
        final["credits"] = [photo["credit"]]
        final["stock"] = {"source": photo["source"], "id": photo["id"], "url": photo["page_url"]}
    return {"urls": [f"{PUBLIC_BASE_URL}/uploads/social/{n}" for n in names], "spec": final}


# ───────────────────────── 3. Application ─────────────────────────
def apply():
    global _done
    if _done:
        return
    _done = True
    assets.finalize_spec = finalize_spec
    montage.render_visual = render_visual
    svc.JOB_HANDLERS["rebuild_visual"] = lambda **kw: svc.rebuild_visual(kw["post_id"], kw.get("patch"))

    SPECS["tiktok"]["brief"] = (
        "TikTok : légende ≤150 caractères, très directe, 3-5 hashtags. Le format (vidéo verticale animée ou carrousel "
        "photo) est imposé par la ligne FORMAT IMPOSÉ. Pour une vidéo : script_video = accroche choc ≤7 mots, "
        "3-4 scènes courtes, voix off ≤70 mots, CTA final.")

    name = os.getenv("SOCIAL_BRAND_NAME") or os.getenv("SOCIAL_BRAND_SLUG") or "la marque"
    site = os.getenv("SOCIAL_BRAND_SITE", "")
    assets.VISION_INTRO = f"""Tu analyses UNE image du dossier de marque de « {name} » ({site}). Cette analyse alimente un agent qui rédige des posts pour les réseaux sociaux : sois factuel et précis.

RÈGLES
- Décris UNIQUEMENT ce qui est réellement visible. Si un texte est illisible, ne le devine pas.
- N'invente aucun chiffre, nom de personne ou fonctionnalité qui ne soit pas visible à l'écran (ou documenté dans la fiche technique ci-dessous).
- Les coordonnées (x, y, w, h) sont en POURCENTAGE de l'image (0-100), origine en haut à gauche.
- zone_focus : la région la plus parlante pour un zoom marketing (tableau, graphique, formulaire...). Si l'image entière est pertinente, mets x=0,y=0,w=100,h=100.
- zones_sensibles : encadre tout nom/prénom de personne, visage, salaire, téléphone, email, adresse, numéro d'identité ou de compte lisibles. Si rien : [].
- Réponds avec UN SEUL objet JSON, sans texte autour."""
    assets.VISION_SCHEMA = re.sub(
        r'"module": "[^"]*"',
        '"module": "mot-clé court en minuscules, sans accents, qui désigne la fonction/section du produit montrée '
        '(ex: facturation, tableau_de_bord, messagerie) ; \'marque\' pour un logo ; \'autre\' sinon"',
        assets.VISION_SCHEMA, count=1)