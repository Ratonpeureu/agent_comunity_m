# routes/hoock_admin_social_connect.py
from fastapi import APIRouter, Depends, HTTPException

from agent.routes.hoock_admin import get_current_admin
from agent.services.social import social_agent_service as svc
from agent.services.social import social_gateway as pub
from agent.services.social.social_config import OAUTH_BASE

router = APIRouter(prefix="/admin/social/connect", tags=["Admin – Social connexions"],
                   dependencies=[Depends(get_current_admin)])


@router.get("/status")
async def status():
    return {"configure": pub.configured(),
            "redirects": {p: f"{OAUTH_BASE}/admin/social/oauth/{p}/callback" for p in ("facebook", "instagram", "linkedin", "x")}}


@router.get("/qpost/accounts")
async def qpost_accounts():
    try:
        return await pub.qpost_accounts()
    except pub.PublishError as e:
        raise HTTPException(409, str(e))


@router.get("/qpost/tools")
async def qpost_tools():
    """Schéma réel des outils QPost (pour vérifier le format de `platforms`)."""
    try:
        return await pub.qpost_tools()
    except pub.PublishError as e:
        raise HTTPException(409, str(e))


@router.post("/qpost/sync")
async def qpost_sync(platforms: str = "tiktok"):
    wanted = [p.strip() for p in platforms.split(",") if p.strip() in ("tiktok", "instagram")]
    try:
        accs = await pub.qpost_accounts()
    except pub.PublishError as e:
        raise HTTPException(409, str(e))
    brand = await svc.get_or_create_brand()
    done, missing = [], []
    for p in wanted:
        a = next((x for x in accs if x["platform"] == p), None)
        if not a:
            missing.append(p)
            continue
        await svc.upsert_account(brand.id, p, a["name"], a.get("id"), {"via": "qpost", "qpost_id": a.get("id")})
        done.append(p)
    return {"synchronises": done, "absents": missing}