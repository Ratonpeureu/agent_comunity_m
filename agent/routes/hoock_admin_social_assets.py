# routes/hoock_admin_social_assets.py
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlmodel import select

from agent.db import SocialPost, get_celery_session
from agent.routes.hoock_admin import get_current_admin
from agent.routes.hoock_admin_social import _job
from agent.services.social import social_agent_service as svc
from agent.services.social import social_assets as assets
from agent.services.social import social_unsplash as stock
from agent.services.social.social_config import PLATFORMS, PUBLIC_BASE_URL, UPLOAD_DIR

router = APIRouter(prefix="/admin/social/assets", tags=["Admin – Social Branding Assets"],
                   dependencies=[Depends(get_current_admin)])

_SLIM = ("id", "fichier", "type_image", "module", "ecran", "titre_court", "description", "hashtags", "mots_cles",
         "appareil", "orientation", "dimensions", "qualite", "exclu", "donnees_personnelles_visibles",
         "plateformes_recommandees", "analyse_le", "modele", "notes_admin")


def _slim(a: dict, usage: dict) -> dict:
    return {**{k: a.get(k) for k in _SLIM}, "usage_30j": usage.get(a["id"], 0),
            "sensible_non_masque": assets._sensitive_unblurred(a)}


# ═════════ Catalogue ═════════
@router.get("")
async def list_assets(module: Optional[str] = None, q: Optional[str] = None, include_excluded: bool = True):
    b = await svc.get_or_create_brand()
    usage = (await assets.asset_report(b.id))["usage_30j"]
    items = assets.list_assets(include_excluded=include_excluded)
    if module:
        items = [a for a in items if a.get("module") == module]
    if q:
        qt = assets.tokens(q)
        items = sorted(items, key=lambda a: -len(qt & assets.tokens(" ".join(
            [a.get("titre_court", ""), a.get("description", ""), " ".join(a.get("mots_cles") or [])]))))
    return [_slim(a, usage) for a in items]


@router.get("/modules")
async def modules():
    b = await svc.get_or_create_brand()
    stats = await assets.asset_report(b.id)
    return {"resume": assets.modules_summary(stats), "par_module": stats["par_module"], "usage_30j": stats["usage_30j"]}


@router.get("/report")
async def report():
    b = await svc.get_or_create_brand()
    return await assets.asset_report(b.id)


@router.get("/diagnostic")
async def diagnostic():
    b = await svc.get_or_create_brand()
    return assets.diagnostic(bool(svc.cfg(b).get("autoriser_captures_sensibles")))


# ═════════ Médiathèque : tout ce que le système a utilisé ou produit ═════════
_IMG, _VID, _AUD = {".jpg", ".jpeg", ".png", ".webp"}, {".mp4", ".mov"}, {".mp3", ".wav", ".m4a", ".ogg", ".aac"}


def _iso(ts: float) -> str:
    return datetime.utcfromtimestamp(ts).isoformat(timespec="seconds")


@router.get("/media")
async def media(limit: int = Query(600, le=2000)):
    b = await svc.get_or_create_brand()
    usage = (await assets.asset_report(b.id))["usage_30j"]
    items: list[dict] = []

    # 1) Captures et logos de marque (fichiers privés → chargés en blob côté front)
    for a in assets.list_assets(include_excluded=True):
        is_logo = a.get("type_image") == "logo"
        items.append({"id": f"asset:{a['id']}", "kind": "logo" if is_logo else "capture", "title": a.get("titre_court") or a["id"],
                      "description": a.get("description") or "", "module": a.get("module"), "tags": a.get("hashtags") or [],
                      "private_path": f"/admin/social/assets/{a['id']}/file", "url": None, "poster": None,
                      "created_at": a.get("analyse_le"), "size": None, "post": None,
                      "usage_30j": usage.get(a["id"], 0), "sensible": assets._sensitive_unblurred(a), "exclu": bool(a.get("exclu"))})

    # 2) Posts → pour relier chaque fichier généré à son post
    async with get_celery_session() as s:
        posts = (await s.execute(select(SocialPost).where(SocialPost.brand_id == b.id)
                                 .order_by(SocialPost.created_at.desc()).limit(800))).scalars().all()
    by_file: dict[str, SocialPost] = {}
    for p in posts:
        for u in p.media_urls or []:
            by_file.setdefault(u.rsplit("/", 1)[-1], p)

    def post_info(p):
        if not p:
            return None
        sp = p.visuel_spec or {}
        return {"id": p.id, "plateforme": p.plateforme, "statut": p.statut, "template": sp.get("template"),
                "extrait": (p.contenu or "")[:200], "erreur_montage": sp.get("erreur_montage")}

    # 3) Fichiers générés (montages, vidéos), photos libres, pistes audio
    base = Path(UPLOAD_DIR)
    files = []
    for sub, d in (("", base), ("_stock", base / "_stock"), ("_music", base / "_music")):
        if d.is_dir():
            for f in d.iterdir():
                if f.is_file() and not f.name.startswith("."):
                    st = f.stat()
                    files.append((sub, f, st.st_mtime, st.st_size))
    files.sort(key=lambda t: t[2], reverse=True)
    for sub, f, mt, size in files[:limit]:
        ext = f.suffix.lower()
        url = f"{PUBLIC_BASE_URL}/uploads/social/{sub + '/' if sub else ''}{f.name}"
        p = by_file.get(f.name)
        if f.name.endswith("_cover.jpg"):
            continue
        if sub == "_stock" and ext in _IMG:
            kind, title, desc = "stock", f.stem.replace("_", " "), "Photo libre de droits téléchargée pour un montage"
        elif ext in _AUD:
            kind, title, desc = "audio", f.stem, "Piste musicale générée pour les vidéos"
        elif ext in _VID:
            kind, title = "video", (p.visuel_spec or {}).get("titre_carte") if p else None
            desc = (p.contenu or "")[:160] if p else "Vidéo générée"
        elif ext in _IMG:
            kind, title = "montage", ((p.visuel_spec or {}).get("titre_carte") if p else None)
            desc = (p.contenu or "")[:160] if p else "Visuel généré"
        else:
            continue
        poster = f"{PUBLIC_BASE_URL}/uploads/social/{f.stem}_cover.jpg" if kind == "video" and (base / f"{f.stem}_cover.jpg").exists() else None
        items.append({"id": f"file:{sub}/{f.name}", "kind": kind, "title": title or f.stem, "description": desc,
                      "module": None, "tags": [], "private_path": None, "url": url, "poster": poster,
                      "created_at": _iso(mt), "size": size, "post": post_info(p)})
    counts: dict[str, int] = {}
    for it in items:
        counts[it["kind"]] = counts.get(it["kind"], 0) + 1
    return {"items": items, "counts": counts}


class SearchBody(BaseModel):
    texte: str
    plateforme: Optional[str] = None
    k: int = 8


@router.post("/search")
async def search_assets(body: SearchBody):
    b = await svc.get_or_create_brand()
    stats = await assets.asset_report(b.id)
    c = svc.cfg(b)
    items = assets.shortlist(body.texte, body.plateforme, body.k, stats, c.get("autoriser_captures_sensibles", False))
    return [_slim(a, stats["usage_30j"]) for a in items]


@router.get("/stock/search")
async def stock_search(query: str, orientation: str = Query("landscape", pattern="^(landscape|portrait|squarish)$")):
    if not stock.available():
        raise HTTPException(409, "Configure UNSPLASH_ACCESS_KEY (ou PEXELS_API_KEY)")
    res = await stock.search(query, orientation, 12)
    return [{k: r.get(k) for k in ("source", "id", "thumb", "author", "page_url", "alt")} for r in res]


# ═════════ Ajout / analyse ═════════
@router.post("/upload")
async def upload(files: List[UploadFile] = File(...), analyze: bool = True):
    saved = []
    for f in files:
        data = await f.read()
        if len(data) > 12 * 1024 * 1024:
            raise HTTPException(413, f"{f.filename} dépasse 12 Mo")
        try:
            saved.append(assets.save_upload(f.filename or "upload.png", data))
        except ValueError as e:
            raise HTTPException(422, str(e))
    job = await _job("analyze_assets", {"move": True, "force": False, "max_images": 20}) if analyze else None
    return {"enregistres": saved, "job": job}


class AnalyzeBody(BaseModel):
    move: Optional[bool] = None
    force: bool = False
    max_images: Optional[int] = 15


@router.post("/analyze")
async def analyze(body: AnalyzeBody = AnalyzeBody()):
    return await _job("analyze_assets", body.dict())


# ═════════ Montage ═════════
class PreviewBody(BaseModel):
    plateforme: str = "instagram"
    template: Optional[str] = None
    asset_ids: List[str] = []
    titre_carte: str = ""
    sous_titre: str = ""
    badge: str = ""
    unsplash_query: str = ""
    slides: List[dict] = []
    ratio: Optional[str] = None


class RebuildBody(BaseModel):
    template: Optional[str] = None
    asset_ids: Optional[List[str]] = None
    titre_carte: Optional[str] = None
    sous_titre: Optional[str] = None
    badge: Optional[str] = None
    unsplash_query: Optional[str] = None
    slides: Optional[List[dict]] = None
    ratio: Optional[str] = None
    reshuffle: bool = False


@router.post("/preview")
async def preview(body: PreviewBody):
    if body.plateforme not in PLATFORMS:
        raise HTTPException(422, f"Plateforme invalide : {PLATFORMS}")
    spec = body.dict(exclude={"plateforme"}, exclude_none=True)
    if body.template == "video":
        return await _job("preview_visual", {"spec": spec, "plateforme": body.plateforme})
    return await svc.preview_visual(spec, body.plateforme)


@router.post("/rebuild/{post_id}")
async def rebuild(post_id: str, body: RebuildBody):
    try:
        return await svc.rebuild_visual(post_id, body.dict(exclude_none=True))
    except ValueError as e:
        raise HTTPException(409, str(e))


# ═════════ Une capture (après les routes statiques) ═════════
@router.get("/{asset_id}")
async def get_asset(asset_id: str):
    a = assets.get_asset(asset_id)
    if not a:
        raise HTTPException(404, "Capture introuvable")
    return a


@router.get("/{asset_id}/file")
async def get_file(asset_id: str):
    a = assets.get_asset(asset_id)
    if not a:
        raise HTTPException(404, "Capture introuvable")
    p = assets.asset_path(a)
    if not p.is_file():
        raise HTTPException(404, f"Fichier absent sur le disque : {p}")
    return FileResponse(str(p), headers={"Cache-Control": "private, max-age=3600"})


class AssetPatch(BaseModel):
    module: Optional[str] = None
    ecran: Optional[str] = None
    titre_court: Optional[str] = None
    description: Optional[str] = None
    fonctionnalites_visibles: Optional[List[str]] = None
    mots_cles: Optional[List[str]] = None
    hashtags: Optional[List[str]] = None
    angles_posts: Optional[List[dict]] = None
    legendes_montage: Optional[List[dict]] = None
    zone_focus: Optional[dict] = None
    zones_sensibles: Optional[List[dict]] = None
    donnees_personnelles_visibles: Optional[bool] = None
    plateformes_recommandees: Optional[List[str]] = None
    exclu: Optional[bool] = None
    notes_admin: Optional[str] = None
    type_image: Optional[str] = None


@router.patch("/{asset_id}")
async def patch_asset(asset_id: str, body: AssetPatch):
    try:
        return assets.update_asset(asset_id, body.dict(exclude_none=True))
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/{asset_id}/reanalyze")
async def reanalyze(asset_id: str):
    if not assets.get_asset(asset_id):
        raise HTTPException(404, "Capture introuvable")
    return await _job("reanalyze_asset", {"asset_id": asset_id})


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str):
    try:
        assets.delete_asset(asset_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"ok": True}