"""Configuration de l'application (ancienne page /setup) : lecture masquée, écriture, test d'URL, redémarrage, compte admin."""
import asyncio
import os
import time
from typing import List
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agent.bootstrap import BOOT_ID, hash_password, read_config, verify_password, write_config
from agent.config_schema import FIELDS, SECTIONS
from agent.routes.hoock_admin import get_current_admin
from agent.services.llm_client import llm_usage

router = APIRouter(prefix="/admin/social/config", tags=["Admin – Configuration"],
                   dependencies=[Depends(get_current_admin)])
_pw_fail: list = []


def _is_url(v: str) -> bool:
    u = urlparse(v)
    return u.scheme in ("http", "https") and bool(u.netloc)


def _validate(f: dict, v: str) -> str:
    if "\n" in v or "\r" in v:
        raise HTTPException(422, f"{f['label']} : une seule ligne attendue")
    if f["kind"] == "url":
        if not _is_url(v):
            raise HTTPException(422, f"{f['label']} : URL invalide (https://…)")
        return v.rstrip("/")
    if f["key"] == "PORT" and not (v.isdigit() and 1 <= int(v) <= 65535):
        raise HTTPException(422, "Port invalide (1 à 65535)")
    if f["key"] == "SOCIAL_TZ":
        try:
            ZoneInfo(v)
        except Exception:
            raise HTTPException(422, "Fuseau horaire inconnu (ex : Africa/Dakar)")
    if f["kind"] == "select" and f["options"] and v not in f["options"]:
        raise HTTPException(422, f"{f['label']} : valeur non autorisée")
    return v


@router.get("")
async def get_config():
    cfg = read_config()
    sections = []
    for s in SECTIONS:
        fields = []
        for f in s["fields"]:
            v = str(cfg.get(f["key"], "") or "")
            secret = f["kind"] == "secret"
            fields.append({**f, "secret": secret, "set": bool(v), "value": "" if secret else v,
                           "last4": v[-4:] if secret and len(v) >= 12 else ""})
        sections.append({"id": s["id"], "title": s["title"], "desc": s["desc"], "fields": fields})
    return {"sections": sections, "admin": {"username": os.getenv("ADMIN_USERNAME", "admin")}}


class ConfigBody(BaseModel):
    values: dict = {}
    clear: List[str] = []


@router.put("")
async def put_config(b: ConfigBody):
    cfg = read_config()
    changed: list = []
    for k, raw in b.values.items():
        f = FIELDS.get(k)
        if not f:
            raise HTTPException(422, f"Paramètre inconnu : {k}")
        v = str(raw or "").strip()
        if f["kind"] == "secret":
            if v and cfg.get(k) != v:
                cfg[k] = v
                changed.append(k)
            continue                                   # secret vide = conservé
        if not v:
            if k in cfg:
                cfg.pop(k)
                changed.append(k)
            continue
        v = _validate(f, v)
        if cfg.get(k) != v:
            cfg[k] = v
            changed.append(k)
    for k in b.clear:
        if k not in FIELDS:
            raise HTTPException(422, f"Paramètre inconnu : {k}")
        if k in cfg:
            cfg.pop(k)
            if k not in changed:
                changed.append(k)
    if not str(cfg.get("PUBLIC_BASE_URL") or "").strip():
        raise HTTPException(422, "L'URL publique est obligatoire.")
    if not changed:
        return {"ok": True, "changed": [], "restart_required": []}
    write_config(cfg)
    for k in changed:                                  # effet immédiat pour tout ce qui est lu à chaque appel
        if cfg.get(k):
            os.environ[k] = str(cfg[k])
        else:
            os.environ.pop(k, None)
    llm_usage._ENV_BAD.clear()                         # une clé corrigée est de nouveau essayée
    llm_usage._ENV_ERR.clear()
    return {"ok": True, "changed": changed, "restart_required": [k for k in changed if FIELDS[k]["restart"]]}


class UrlBody(BaseModel):
    url: str = ""


@router.post("/check-url")
async def check_url(b: UrlBody):
    url = (b.url or os.getenv("PUBLIC_BASE_URL", "")).strip().rstrip("/")
    if not _is_url(url):
        raise HTTPException(422, "URL invalide (https://…)")
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as http:
            r = await http.get(f"{url}/health")
    except httpx.HTTPError as e:
        return {"ok": False, "https": url.startswith("https://"), "ms": 0, "erreur": f"Injoignable depuis le serveur : {e}"}
    ms = int((time.time() - t0) * 1000)
    try:
        j = r.json()
    except Exception:
        j = {}
    if r.status_code != 200:
        return {"ok": False, "https": url.startswith("https://"), "ms": ms, "erreur": f"Le serveur répond {r.status_code} sur /health"}
    if j.get("boot") != BOOT_ID:
        return {"ok": False, "https": url.startswith("https://"), "ms": ms,
                "erreur": "L'adresse répond, mais ce n'est pas cette application (autre serveur ou ancien conteneur)."}
    return {"ok": True, "https": url.startswith("https://"), "ms": ms, "erreur": ""}


@router.post("/restart")
async def restart():
    asyncio.get_running_loop().call_later(1.2, os._exit, 0)    # Docker (restart: unless-stopped) relance l'app
    return {"ok": True}


class AdminBody(BaseModel):
    current_password: str
    username: str = ""
    new_password: str = ""


@router.put("/admin")
async def put_admin(b: AdminBody):
    now = time.time()
    _pw_fail[:] = [t for t in _pw_fail if now - t < 60]
    if len(_pw_fail) >= 5:
        raise HTTPException(429, "Trop d'essais, réessaie dans une minute")
    cfg = read_config()
    ok = await asyncio.to_thread(verify_password, b.current_password, cfg.get("ADMIN_PASSWORD_HASH", ""))
    if not ok:
        _pw_fail.append(now)
        raise HTTPException(403, "Mot de passe actuel incorrect")     # 403 : un 401 déconnecterait l'interface
    user = b.username.strip()
    if user:
        if len(user) < 3:
            raise HTTPException(422, "Identifiant trop court (3 caractères minimum)")
        cfg["ADMIN_USERNAME"] = user
    if b.new_password:
        if len(b.new_password) < 8:
            raise HTTPException(422, "Le mot de passe doit contenir au moins 8 caractères")
        cfg["ADMIN_PASSWORD_HASH"] = await asyncio.to_thread(hash_password, b.new_password)
    write_config(cfg)
    os.environ["ADMIN_USERNAME"] = cfg.get("ADMIN_USERNAME", "admin")
    os.environ["ADMIN_PASSWORD_HASH"] = cfg["ADMIN_PASSWORD_HASH"]
    return {"ok": True, "username": cfg.get("ADMIN_USERNAME", "admin")}