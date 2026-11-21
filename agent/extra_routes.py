"""Routes ajoutées : montage visuel (job), connexion par jeton (méthode simple), diagnostic."""
import os
import shutil
import time
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel

from agent.db import SocialPost, get_celery_session
from agent.routes.hoock_admin import get_current_admin
from agent.routes.hoock_admin_social import _job
from agent.services.social import social_agent_service as svc
from agent.services.social import social_gateway as pub
from agent.services.social import social_publishers as legacy
from agent.services.social.social_config import PUBLIC_BASE_URL

router = APIRouter(prefix="/admin/social", tags=["Social – extras"], dependencies=[Depends(get_current_admin)])


# ═════════════ Montage visuel ═════════════
@router.post("/visual/{post_id}")
async def visual(post_id: str, body: dict = Body(...)):
    patch = {k: v for k, v in body.items() if v is not None and v != ""}
    patch["manual"] = True                       # choix explicite de l'utilisateur : jamais écrasé au hasard
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
    if not p:
        raise HTTPException(404, "Post introuvable")
    if p.statut in ("publie", "publication"):
        raise HTTPException(409, "Post déjà publié")
    if patch.get("template") == "video":
        return await _job("rebuild_visual", {"post_id": post_id, "patch": patch})   # long : en arrière-plan
    try:
        return await svc.rebuild_visual(post_id, patch)
    except ValueError as e:
        raise HTTPException(409, str(e))


# ═════════════ Diagnostic ═════════════
@router.get("/system")
async def system():
    try:
        import edge_tts  # noqa: F401
        et = True
    except Exception:
        et = False
    return {
        "ffmpeg": bool(shutil.which("ffmpeg")), "edge_tts": et,
        "llm": bool(os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY")),
        "public_base_url": PUBLIC_BASE_URL, "public_https": PUBLIC_BASE_URL.startswith("https://"),
        "unsplash": bool(os.getenv("UNSPLASH_ACCESS_KEY") or os.getenv("PEXELS_API_KEY")),
        "qpost": bool(os.getenv("QPOST_API_KEY") or os.getenv("QPOST_API")),
        "serper": bool(os.getenv("SERPER_API_KEY")), "meta_app": bool(os.getenv("META_APP_ID") and os.getenv("META_APP_SECRET")),
    }


# ═════════════ Connexion par jeton ═════════════
class FBBody(BaseModel):
    user_token: str = ""
    page_token: str = ""
    page_id: str = ""


@router.post("/manual/facebook")
async def manual_facebook(b: FBBody):
    brand = await svc.get_or_create_brand()
    pid = b.page_id.strip() or os.getenv("META_PAGE_ID", "").strip()
    note = None
    try:
        async with httpx.AsyncClient(timeout=40) as http:
            if b.page_token.strip():
                if not pid:
                    raise HTTPException(422, "Indique l'ID de la Page avec son jeton.")
                creds = {"page_id": pid, "page_access_token": b.page_token.strip(), "exp_ts": 0}
            else:
                tok = b.user_token.strip()
                if not tok:
                    raise HTTPException(422, "Colle un jeton d'accès.")
                app_id, secret = os.getenv("META_APP_ID"), os.getenv("META_APP_SECRET")
                if app_id and secret:
                    r = await http.get(f"{legacy.GRAPH}/oauth/access_token", params={
                        "grant_type": "fb_exchange_token", "client_id": app_id, "client_secret": secret,
                        "fb_exchange_token": tok})
                    d = r.json()
                    if d.get("access_token"):
                        tok = d["access_token"]
                    else:
                        note = "Échange vers un jeton longue durée refusé : " + str(d.get("error", {}).get("message", ""))[:160]
                else:
                    note = ("Sans META_APP_ID / META_APP_SECRET dans les Réglages, le jeton de Page expirera au bout "
                            "d'environ 1 h. Ajoute-les puis reconnecte.")
                try:
                    pages = await pub._meta_pages(http, tok)
                except pub.PublishError as e:
                    raise HTTPException(400, f"{e} — si c'est déjà un jeton de Page, utilise l'option « jeton de Page ».")
                if not pages:
                    raise HTTPException(409, "Aucune Page trouvée : coche ta Page dans la fenêtre d'autorisation Meta "
                                             "(permissions pages_show_list, pages_manage_posts).")
                page = next((p for p in pages if p["id"] == pid), None) if pid else (pages[0] if len(pages) == 1 else None)
                if page is None:
                    return {"ok": False, "message": "Plusieurs Pages : choisis la bonne.",
                            "pages": [{"id": p["id"], "name": p["name"]} for p in pages]}
                creds = {"page_id": page["id"], "page_access_token": page["access_token"], "exp_ts": 0}
        nom = await pub.verify("facebook", creds)
    except pub.PublishError as e:
        raise HTTPException(400, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Réseau : {e}")
    await svc.upsert_account(brand.id, "facebook", nom, creds["page_id"], creds)
    return {"ok": True, "nom": nom, "avertissement": note}


class TokBody(BaseModel):
    access_token: str


@router.post("/manual/instagram")
async def manual_instagram(b: TokBody):
    brand = await svc.get_or_create_brand()
    tok = b.access_token.strip()
    if not tok:
        raise HTTPException(422, "Colle le jeton Instagram.")
    exp = 5184000
    try:
        async with httpx.AsyncClient(timeout=40) as http:
            secret = os.getenv("INSTAGRAM_APP_SECRET")
            if secret:
                try:
                    r = await http.get(f"{pub.IG}/access_token", params={
                        "grant_type": "ig_exchange_token", "client_secret": secret, "access_token": tok})
                    d = r.json()
                    if d.get("access_token"):
                        tok, exp = d["access_token"], int(d.get("expires_in", exp))
                except Exception:
                    pass
            me = await pub._igcall(http, "GET", "me", tok, fields="user_id,username,account_type")
    except pub.PublishError as e:
        raise HTTPException(400, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Réseau : {e}")
    if str(me.get("account_type", "")).upper() == "PERSONAL":
        raise HTTPException(409, "Compte personnel : passe-le en compte Professionnel ou Créateur (gratuit), puis régénère le jeton.")
    igid = str(me.get("user_id") or me.get("id"))
    now = int(time.time())
    creds = {"login": "instagram", "access_token": tok, "ig_user_id": igid, "exp_ts": now + exp, "obtained_at": now}
    await svc.upsert_account(brand.id, "instagram", me.get("username", ""), igid, creds, datetime.utcnow() + timedelta(seconds=exp))
    return {"ok": True, "nom": me.get("username", "")}


@router.post("/manual/instagram-from-facebook")
async def manual_instagram_from_facebook():
    brand = await svc.get_or_create_brand()
    try:
        _, fb = await svc._account_creds(brand.id, "facebook")
    except pub.PublishError as e:
        raise HTTPException(409, f"Connecte d'abord Facebook ({e})")
    try:
        async with httpx.AsyncClient(timeout=40) as http:
            d = await pub._graph(http, "GET", fb["page_id"], fb["page_access_token"],
                                 fields="instagram_business_account{id,username}")
    except pub.PublishError as e:
        raise HTTPException(400, str(e))
    ig = d.get("instagram_business_account")
    if not ig:
        raise HTTPException(409, "Aucun compte Instagram Professionnel n'est lié à cette Page Facebook.")
    creds = {"ig_user_id": ig["id"], "access_token": fb["page_access_token"]}
    await svc.upsert_account(brand.id, "instagram", ig.get("username", ""), ig["id"], creds)
    return {"ok": True, "nom": ig.get("username", "")}


class LIBody(BaseModel):
    access_token: str
    org_id: str = ""


@router.post("/manual/linkedin")
async def manual_linkedin(b: LIBody):
    brand = await svc.get_or_create_brand()
    tok = b.access_token.strip()
    try:
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.get(f"{legacy.LI}/v2/userinfo", headers={"Authorization": f"Bearer {tok}"})
    except httpx.HTTPError as e:
        raise HTTPException(502, f"Réseau : {e}")
    if r.status_code != 200:
        raise HTTPException(400, f"LinkedIn a refusé le jeton ({r.status_code}). Scopes requis : openid profile w_member_social.")
    ui = r.json()
    org = "".join(ch for ch in b.org_id if ch.isdigit())
    urn = f"urn:li:organization:{org}" if org else f"urn:li:person:{ui.get('sub')}"
    creds = {"access_token": tok, "refresh_token": None, "author_urn": urn}
    await svc.upsert_account(brand.id, "linkedin", ui.get("name", ""), urn, creds, datetime.utcnow() + timedelta(days=59))
    return {"ok": True, "nom": ui.get("name", ""), "urn": urn}