# routes/hoock_admin_social.py
import os
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import RedirectResponse
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlmodel import select

from agent.db import (
    SocialAccount, SocialBrand, SocialIdea, SocialJob, SocialPost, SocialReport,
    SocialStyleSample, get_celery_session,
)
from agent.routes.hoock_admin import ADMIN_SECRET_KEY, ALGORITHM, get_current_admin
from agent.services.social import social_agent_service as svc
from agent.services.social import social_analytics as an
from agent.services.social import social_gateway as pub
from agent.services.social.social_config import PLATFORMS, PUBLIC_BASE_URL, SPECS, UPLOAD_DIR, dec, local_to_utc

router = APIRouter(prefix="/admin/social", tags=["Admin – Social Media Agent"],
                   dependencies=[Depends(get_current_admin)])
public_router = APIRouter(prefix="/admin/social", tags=["Admin – Social OAuth callback"])


def _plat(p: str) -> str:
    if p not in PLATFORMS:
        raise HTTPException(422, f"Plateforme invalide : {PLATFORMS}")
    return p


async def _brand() -> SocialBrand:
    return await svc.get_or_create_brand()


async def _job(kind: str, params: dict) -> dict:
    from agent.tasks.social.social_task import social_job_task
    async with get_celery_session() as s:
        j = SocialJob(kind=kind, params=params)
        s.add(j)
        await s.commit()
        jid = j.id
    social_job_task.delay(jid, kind, params)
    return {"job_id": jid, "statut": "en_attente"}


def _iso(d):
    return d.isoformat() if d else None


# ═════════════ JOBS ═════════════
@router.get("/jobs/{job_id}")
async def job_status(job_id: str):
    async with get_celery_session() as s:
        j = await s.get(SocialJob, job_id)
    if not j:
        raise HTTPException(404, "Job introuvable")
    statut, erreur = j.statut, j.erreur
    if statut in ("en_attente", "en_cours") and j.created_at and datetime.utcnow() - j.created_at > timedelta(minutes=20):
        statut, erreur = "echec", "Traitement interrompu (délai dépassé) : le worker ne l'a pas terminé"
    return {"id": j.id, "kind": j.kind, "statut": statut, "resultat": j.resultat, "erreur": erreur,
            "created_at": _iso(j.created_at), "finished_at": _iso(j.finished_at)}
            
# ═════════════ MARQUE ═════════════
class BrandBody(BaseModel):
    nom: Optional[str] = None
    site_url: Optional[str] = None
    urls_supplementaires: Optional[List[str]] = None
    config: Optional[dict] = None
    identite: Optional[dict] = None
    ton: Optional[dict] = None
    style_guide: Optional[str] = None
    piliers: Optional[List[dict]] = None


def _brand_out(b: SocialBrand) -> dict:
    return {"id": b.id, "slug": b.slug, "nom": b.nom, "site_url": b.site_url, "urls_supplementaires": b.urls_supplementaires,
            "identite": b.identite, "ton": b.ton, "style_guide": b.style_guide, "piliers": b.piliers,
            "apprentissages": b.apprentissages, "config": svc.cfg(b), "statut_analyse": b.statut_analyse,
            "erreur_analyse": b.erreur_analyse, "derniere_analyse": _iso(b.derniere_analyse)}


@router.get("/brand")
async def get_brand():
    return _brand_out(await _brand())


@router.put("/brand")
async def update_brand(body: BrandBody):
    b = await _brand()
    async with get_celery_session() as s:
        row = await s.get(SocialBrand, b.id)
        for k, v in body.dict(exclude_none=True).items():
            if k == "config":
                row.config = {**(row.config or {}), **v}
            else:
                setattr(row, k, v)
        row.updated_at = datetime.utcnow()
        await s.commit()
        await s.refresh(row)
        return _brand_out(row)


@router.post("/brand/analyze")
async def analyze_brand():
    b = await _brand()
    return await _job("analyze_brand", {"brand_id": b.id})


@router.post("/brand/tone/refresh")
async def refresh_tone():
    b = await _brand()
    return await _job("refresh_tone", {"brand_id": b.id})


class SampleBody(BaseModel):
    texte: str
    plateforme: Optional[str] = None


@router.post("/brand/style-samples")
async def add_sample(body: SampleBody):
    b = await _brand()
    ok = await svc.add_style_sample(b.id, body.texte, body.plateforme, "manuel", 2.0)
    return {"ajoute": ok}


@router.get("/brand/style-samples")
async def list_samples():
    b = await _brand()
    async with get_celery_session() as s:
        rows = (await s.execute(select(SocialStyleSample).where(SocialStyleSample.brand_id == b.id)
                                .order_by(SocialStyleSample.created_at.desc()).limit(100))).scalars().all()
    return [{"id": r.id, "plateforme": r.plateforme, "texte": r.texte, "source": r.source, "poids": r.poids,
             "created_at": _iso(r.created_at)} for r in rows]


@router.delete("/brand/style-samples/{sample_id}")
async def delete_sample(sample_id: str):
    async with get_celery_session() as s:
        r = await s.get(SocialStyleSample, sample_id)
        if r:
            await s.delete(r)
            await s.commit()
    return {"ok": True}


# ═════════════ COMPTES & OAUTH ═════════════
class CredsBody(BaseModel):
    credentials: dict
    nom: Optional[str] = ""


@router.get("/accounts")
async def list_accounts():
    b = await _brand()
    async with get_celery_session() as s:
        rows = (await s.execute(select(SocialAccount).where(SocialAccount.brand_id == b.id))).scalars().all()
    have = {r.plateforme: r for r in rows}
    return [{"plateforme": p, "connecte": p in have, "nom": have[p].nom_affichage if p in have else None,
             "statut": have[p].statut if p in have else None, "expire_le": _iso(have[p].expire_le) if p in have else None,
             "erreur": have[p].derniere_erreur if p in have else None} for p in PLATFORMS]


@router.put("/accounts/{platform}")
async def set_account_manual(platform: str, body: CredsBody):
    """Connexion manuelle (tokens collés). facebook: {page_id,page_access_token} · instagram: {ig_user_id,access_token}
    linkedin: {access_token,author_urn} · tiktok: {access_token,refresh_token,privacy_level,post_mode}"""
    _plat(platform)
    b = await _brand()
    try:
        nom = await pub.verify(platform, body.credentials)
    except Exception as e:
        raise HTTPException(400, f"Identifiants invalides : {e}")
    return await svc.upsert_account(b.id, platform, body.nom or nom, None, body.credentials)


@router.post("/accounts/{platform}/test")
async def test_account(platform: str):
    b = await _brand()
    try:
        _, creds = await svc._account_creds(b.id, _plat(platform))
        return {"ok": True, "compte": await pub.verify(platform, creds)}
    except Exception as e:
        return {"ok": False, "erreur": str(e)}


@router.delete("/accounts/{platform}")
async def delete_account(platform: str):
    b = await _brand()
    async with get_celery_session() as s:
        a = (await s.execute(select(SocialAccount).where(SocialAccount.brand_id == b.id,
                                                         SocialAccount.plateforme == _plat(platform)))).scalar_one_or_none()
        if a:
            await s.delete(a)
            await s.commit()
    return {"ok": True}


@router.get("/oauth/{platform}/url")
async def oauth_url(platform: str, admin=Depends(get_current_admin)):
    _plat(platform)
    state = jwt.encode({"sub": admin.id, "p": platform, "exp": datetime.utcnow() + timedelta(minutes=10)},
                       ADMIN_SECRET_KEY, algorithm=ALGORITHM)
    try:
        return {"url": pub.oauth_url(platform, state)}
    except pub.PublishError as e:
        raise HTTPException(409, str(e))


@public_router.get("/oauth/{platform}/callback")
async def oauth_callback(platform: str, code: str = "", state: str = "", error: str = "", error_description: str = ""):
    from urllib.parse import quote
    back = f"{PUBLIC_BASE_URL}/admin/social"
    fail = lambda m: RedirectResponse(f"{back}?oauth_error={quote(str(m)[:700])}")
    if error or not code:
        return fail(error_description or error or "annulé")
    try:
        payload = jwt.decode(state, ADMIN_SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("p") != platform:
            raise JWTError("plateforme incohérente")
    except JWTError:
        return fail("state invalide ou expiré (relance la connexion)")
    try:
        b = await svc.get_or_create_brand()
        for a in await pub.oauth_exchange(platform, code, state):
            await svc.upsert_account(b.id, a["plateforme"], a["nom"], a["identifiant"], a["creds"], a["expire_le"])
    except Exception as e:
        return fail(e)
    return RedirectResponse(f"{back}?connected={platform}")


# ═════════════ IDÉES ═════════════
class IdeasBody(BaseModel):
    nb: int = 8
    thematique: Optional[str] = None
    avec_tendances: bool = True


def _idea_out(i: SocialIdea) -> dict:
    return {"id": i.id, "titre": i.titre, "angle": i.angle, "accroche": i.accroche, "pilier": i.pilier, "objectif": i.objectif,
            "format_conseille": i.format_conseille, "plateformes": i.plateformes, "justification": i.justification,
            "source_tendance_url": i.source_tendance_url, "urgence": i.urgence, "score_potentiel": i.score_potentiel,
            "statut": i.statut, "created_at": _iso(i.created_at)}


@router.post("/ideas/generate")
async def generate_ideas(body: IdeasBody):
    b = await _brand()
    return await _job("generate_ideas", {"brand_id": b.id, **body.dict()})


@router.get("/ideas")
async def list_ideas(statut: Optional[str] = None, limit: int = Query(50, le=200)):
    b = await _brand()
    async with get_celery_session() as s:
        q = select(SocialIdea).where(SocialIdea.brand_id == b.id)
        if statut:
            q = q.where(SocialIdea.statut == statut)
        rows = (await s.execute(q.order_by(SocialIdea.score_potentiel.desc(), SocialIdea.created_at.desc()).limit(limit))).scalars().all()
    return [_idea_out(i) for i in rows]


class IdeaPatch(BaseModel):
    statut: Optional[str] = None       # accepte | rejete
    motif_rejet: Optional[str] = None




@router.patch("/ideas/{idea_id}")
async def patch_idea(idea_id: str, body: IdeaPatch):
    async with get_celery_session() as s:
        i = await s.get(SocialIdea, idea_id)
        if not i:
            raise HTTPException(404, "Idée introuvable")
        if body.statut in ("accepte", "rejete", "propose"):
            i.statut = body.statut
        i.motif_rejet = body.motif_rejet or i.motif_rejet
        await s.commit()
        await s.refresh(i)
        return _idea_out(i)


class WriteBody(BaseModel):
    plateformes: Optional[List[str]] = None
    instruction: str = ""


@router.post("/ideas/{idea_id}/write")
async def write_from_idea(idea_id: str, body: WriteBody):
    return await _job("write_posts", {"idea_id": idea_id, "plateformes": body.plateformes, "instruction": body.instruction})


# ═════════════ POSTS ═════════════
@router.get("/posts")
async def list_posts(statut: Optional[str] = None, plateforme: Optional[str] = None,
                     limit: int = Query(50, le=200), offset: int = 0):
    b = await _brand()
    async with get_celery_session() as s:
        q = select(SocialPost).where(SocialPost.brand_id == b.id)
        if statut:
            q = q.where(SocialPost.statut == statut)
        if plateforme:
            q = q.where(SocialPost.plateforme == plateforme)
        rows = (await s.execute(q.order_by(SocialPost.created_at.desc()).limit(limit).offset(offset))).scalars().all()
    return [svc.post_dict(p) for p in rows]


@router.get("/posts/{post_id}")
async def get_post(post_id: str):
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
    if not p:
        raise HTTPException(404, "Post introuvable")
    return svc.post_dict(p)


class PostCreate(BaseModel):
    plateforme: str
    contenu: str
    hashtags: List[str] = []
    media_urls: List[str] = []
    lien: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    format: str = "texte"


@router.post("/posts")
async def create_post(body: PostCreate):
    b = await _brand()
    _plat(body.plateforme)
    when = local_to_utc(body.scheduled_at) if body.scheduled_at else None
    async with get_celery_session() as s:
        p = SocialPost(brand_id=b.id, plateforme=body.plateforme, contenu=body.contenu, hashtags=body.hashtags,
                       media_urls=body.media_urls, lien=body.lien, format=body.format, statut="a_valider",
                       scheduled_at=when, genere_par_ia=False)
        s.add(p)
        await s.commit()
        await s.refresh(p)
        out = svc.post_dict(p)
    pred = await an.predict(b.id, out, None)
    async with get_celery_session() as s:
        p = await s.get(SocialPost, out["id"])
        p.prediction = pred
        await s.commit()
    return {**out, "prediction": pred}


class PostPatch(BaseModel):
    contenu: Optional[str] = None
    hashtags: Optional[List[str]] = None
    lien: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    script_video: Optional[str] = None


@router.patch("/posts/{post_id}")
async def patch_post(post_id: str, body: PostPatch):
    f = body.dict(exclude_none=True)
    if "scheduled_at" in f:
        f["scheduled_at"] = local_to_utc(f["scheduled_at"])  # naïf = heure locale Dakar
    try:
        return await svc.update_post(post_id, f)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.delete("/posts/{post_id}")
async def delete_post(post_id: str):
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        if not p:
            raise HTTPException(404, "Post introuvable")
        if p.statut == "publication":
            raise HTTPException(409, "Publication en cours")
        await s.delete(p)
        await s.commit()
    return {"ok": True}


@router.post("/posts/{post_id}/media")
async def upload_media(post_id: str, file: UploadFile = File(...)):
    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp", "mp4", "mov"):
        raise HTTPException(422, "Formats : jpg, png, webp, mp4, mov")
    data = await file.read()
    if len(data) > (200 if ext in ("mp4", "mov") else 15) * 1024 * 1024:
        raise HTTPException(413, "Fichier trop volumineux")
    name = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(UPLOAD_DIR, name), "wb") as f:
        f.write(data)
    url = f"{PUBLIC_BASE_URL}/uploads/social/{name}"
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        if not p:
            raise HTTPException(404, "Post introuvable")
        p.media_urls = [*(p.media_urls or []), url]
        await s.commit()
    return {"url": url}


class MediaRemove(BaseModel):
    url: str


@router.post("/posts/{post_id}/media/remove")
async def remove_media(post_id: str, body: MediaRemove):
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        if not p:
            raise HTTPException(404, "Post introuvable")
        p.media_urls = [u for u in (p.media_urls or []) if u != body.url]
        await s.commit()
    return {"ok": True}


class ValidateBody(BaseModel):
    scheduled_at: Optional[datetime] = None   # heure locale (Dakar) si naïf


@router.post("/posts/{post_id}/validate")
async def validate_post(post_id: str, body: ValidateBody = ValidateBody(), admin=Depends(get_current_admin)):
    try:
        when = local_to_utc(body.scheduled_at) if body.scheduled_at else None
        return await svc.validate_post(post_id, admin.username, when)
    except ValueError as e:
        raise HTTPException(409, str(e))


class RejectBody(BaseModel):
    motif: str = ""


@router.post("/posts/{post_id}/reject")
async def reject_post(post_id: str, body: RejectBody, admin=Depends(get_current_admin)):
    try:
        return await svc.reject_post(post_id, body.motif, admin.username)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/posts/{post_id}/unschedule")
async def unschedule(post_id: str):
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        if not p or p.statut != "programme":
            raise HTTPException(409, "Post non programmé")
        p.statut = "a_valider"
        await s.commit()
        return svc.post_dict(p)


@router.post("/posts/{post_id}/publish-now")
async def publish_now(post_id: str, admin=Depends(get_current_admin)):
    from agent.tasks.social.social_task import social_publish_post_task
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        if not p or p.statut in ("publie", "publication"):
            raise HTTPException(409, "Post non publiable")
        if SPECS[p.plateforme]["visuel_requis"] and not p.media_urls:
            raise HTTPException(422, f"{p.plateforme} exige un média")
        p.statut, p.validated_by, p.validated_at = "publication", admin.username, datetime.utcnow()
        await s.commit()
    social_publish_post_task.delay(post_id, False)
    return {"statut": "publication"}


@router.post("/posts/{post_id}/regenerate")
async def regenerate(post_id: str, body: RejectBody):
    return await _job("regenerate_post", {"post_id": post_id, "instruction": body.motif or "améliore l'accroche"})


@router.post("/posts/{post_id}/variants")
async def variants(post_id: str, n: int = 2):
    return await _job("make_variants", {"post_id": post_id, "n": min(n, 3)})


@router.post("/posts/{post_id}/score")
async def score(post_id: str):
    return await _job("score_post", {"post_id": post_id})


class ReplyBody(BaseModel):
    plateforme: str
    commentaire: str
    contexte_post: str = ""


@router.post("/reply-suggestions")
async def reply_suggestions(body: ReplyBody):
    b = await _brand()
    return await svc.reply_suggestions(b.id, _plat(body.plateforme), body.commentaire, body.contexte_post)


# ═════════════ CALENDRIER ═════════════
@router.get("/calendar")
async def calendar(date_from: Optional[datetime] = None, date_to: Optional[datetime] = None):
    b = await _brand()
    d1 = date_from or datetime.utcnow() - timedelta(days=7)
    d2 = date_to or datetime.utcnow() + timedelta(days=30)
    async with get_celery_session() as s:
        rows = (await s.execute(select(SocialPost).where(
            SocialPost.brand_id == b.id, SocialPost.scheduled_at >= d1, SocialPost.scheduled_at <= d2,
            SocialPost.statut.in_(("a_valider", "programme", "publication", "publie", "echec"))
        ).order_by(SocialPost.scheduled_at))).scalars().all()
    return [svc.post_dict(p) for p in rows]


# ═════════════ ANALYTICS & IA PRÉDICTIVE ═════════════
@router.get("/analytics/overview")
async def overview(days: int = Query(30, ge=7, le=365)):
    b = await _brand()
    return await an.performance_summary(b.id, days)


@router.get("/analytics/best-times")
async def best_times(platform: str, top: int = 8):
    b = await _brand()
    return await an.best_times(b.id, _plat(platform), top)


@router.get("/analytics/growth")
async def growth(days: int = 60):
    b = await _brand()
    return await an.growth(b.id, days)


class PredictBody(BaseModel):
    plateforme: str
    contenu: str
    hashtags: List[str] = []
    media_urls: List[str] = []
    pilier: str = ""
    format: str = "texte"
    scheduled_at: Optional[datetime] = None


@router.post("/analytics/predict")
async def predict(body: PredictBody):
    b = await _brand()
    d = body.dict()
    d["scheduled_at"] = local_to_utc(body.scheduled_at) if body.scheduled_at else None
    d["published_at"] = None
    return await an.predict(b.id, d, None)


@router.get("/analytics/slots")
async def slots(platform: str, n: int = 3):
    b = await _brand()
    r = await an.suggest_slots(b.id, _plat(platform), n, svc.cfg(b)["max_par_jour_par_plateforme"])
    return [{**x, "scheduled_at": x["scheduled_at"].isoformat()} for x in r]


@router.post("/analytics/sync")
async def sync_metrics():
    return await _job("sync_metrics", {})


@router.post("/analytics/reports/generate")
async def generate_report(days: int = 30):
    b = await _brand()
    return await _job("weekly_report", {"brand_id": b.id, "days": days})


@router.get("/analytics/reports")
async def list_reports(limit: int = 10):
    b = await _brand()
    async with get_celery_session() as s:
        rows = (await s.execute(select(SocialReport).where(SocialReport.brand_id == b.id)
                                .order_by(SocialReport.created_at.desc()).limit(limit))).scalars().all()
    return [{"id": r.id, "periode_debut": r.periode_debut, "periode_fin": r.periode_fin, "analyse": r.analyse,
             "faits": r.faits, "created_at": _iso(r.created_at)} for r in rows]


# ═════════════ AUTOPILOT ═════════════
@router.post("/autopilot/run")
async def autopilot_run():
    b = await _brand()
    return await _job("autopilot", {"brand_id": b.id})