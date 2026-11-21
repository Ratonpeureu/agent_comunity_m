# agent/main.py
from agent.bootstrap import BOOT_ID, DATA_DIR, is_configured, load_config

load_config()                 # ← AVANT tout import applicatif (les services lisent os.environ à l'import)
CONFIGURED = is_configured()

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from agent.setup_app import router as setup_router

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("social_app")
STATIC = Path(os.getenv("STATIC_DIR", "/app/static"))
UPLOAD_ROOT = DATA_DIR / "uploads"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

if CONFIGURED:
    from sqlalchemy import update as sa_update
    from sqlmodel import select

    from agent import scheduler
    from agent.extra_routes import router as extra_router
    from agent.db import SocialJob, get_celery_session, init_db
    from agent.routes.hoock_admin import router as admin_router
    from agent.routes.hoock_admin_social import public_router as social_public_router
    from agent.routes.hoock_admin_social import router as social_router
    from agent.routes.hoock_admin_social_assets import router as social_assets_router
    from agent.routes.hoock_admin_social_connect import router as social_connect_router
    from agent.services.social import social_agent_service as svc
    from agent.services.social import social_assets as assets
    from agent.services.social import social_patches
    from agent.services.social.social_config import utcnow

    social_patches.apply()
    from agent.services.social import social_extras
    social_extras.apply()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if CONFIGURED:
        await init_db()
        async with get_celery_session() as s:
            rows = (await s.execute(select(SocialJob).where(SocialJob.statut.in_(("en_attente", "en_cours"))))).scalars().all()
            for j in rows:
                j.statut, j.erreur, j.finished_at = "echec", "Interrompu par un redémarrage du conteneur", utcnow()
            await s.commit()
        brand = await svc.get_or_create_brand()
        name = os.getenv("SOCIAL_BRAND_NAME")
        if name and brand.nom == brand.slug:
            async with get_celery_session() as s:
                await s.execute(sa_update(type(brand)).where(type(brand).id == brand.id).values(nom=name))
                await s.commit()
        app.state.sched = asyncio.create_task(scheduler.run_forever())
        app.state.scan = asyncio.create_task(asyncio.to_thread(assets.scan_once, 60))
        log.info("Agent social prêt — %s", os.getenv("PUBLIC_BASE_URL"))
    else:
        log.warning("Premier démarrage : ouvre /setup pour configurer l'application")
    yield
    for t in ("sched", "scan"):
        task = getattr(app.state, t, None)
        if task:
            task.cancel()


app = FastAPI(title="Agent Social", version="1.0.0", lifespan=lifespan)
app.include_router(setup_router)

if CONFIGURED:
    app.include_router(admin_router)
    app.include_router(social_router)
    app.include_router(social_public_router)
    app.include_router(social_assets_router)
    app.include_router(social_connect_router)
    app.include_router(extra_router)
    app.include_router(social_extras.router)
    app.mount("/uploads", StaticFiles(directory=str(UPLOAD_ROOT)), name="uploads")


@app.get("/health")
async def health():
    return {"status": "ok", "boot": BOOT_ID, "configured": CONFIGURED}


def _safe(base: Path, sub: str):
    try:
        p = (base / sub).resolve()
        if p.is_file() and p.is_relative_to(base.resolve()):
            return p
    except Exception:
        pass
    return None


@app.get("/{full_path:path}")
async def spa(full_path: str):
    if not CONFIGURED:
        return RedirectResponse("/setup")
    if full_path.rstrip("/") == "admin/social" or not full_path.startswith(("api/", "admin/", "uploads/")):
        f = _safe(STATIC, full_path) if full_path else None
        if f:
            return FileResponse(str(f))
        idx = STATIC / "index.html"
        if idx.exists():
            return FileResponse(str(idx))
    raise HTTPException(404, "Introuvable")