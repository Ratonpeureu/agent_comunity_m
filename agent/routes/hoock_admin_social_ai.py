"""Paramètres IA : consommation réelle, budgets, clés API (rotation), modèles et tarifs."""
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agent.routes.hoock_admin import get_current_admin
from agent.services.llm_client import llm_usage as U

router = APIRouter(prefix="/admin/social/ai", tags=["Admin – IA & budget"], dependencies=[Depends(get_current_admin)])


class KeyBody(BaseModel):
    label: str = ""
    key: str
    expire_le: Optional[str] = None


class KeyPatch(BaseModel):
    label: Optional[str] = None
    expire_le: Optional[str] = None
    statut: Optional[str] = None      # actif | desactive


class SettingsBody(BaseModel):
    budget: Optional[dict] = None
    prix: Optional[dict] = None
    modeles: Optional[dict] = None
    retention_jours: Optional[int] = None


@router.get("/overview")
async def overview():
    return await asyncio.to_thread(U.overview)


@router.put("/settings")
async def put_settings(b: SettingsBody):
    try:
        await asyncio.to_thread(U.set_settings, b.budget, b.prix, b.modeles, b.retention_jours)
    except (ValueError, TypeError) as e:
        raise HTTPException(422, f"Valeur invalide : {e}")
    return {"ok": True}


@router.get("/models")
async def models():
    try:
        return await asyncio.to_thread(U.list_models)
    except (U.KeysUnavailable, RuntimeError) as e:
        raise HTTPException(409, str(e))


@router.post("/keys")
async def add_key(b: KeyBody):
    try:
        return await asyncio.to_thread(U.add_key, b.label, b.key, b.expire_le)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.patch("/keys/{kid}")
async def patch_key(kid: str, b: KeyPatch):
    if kid.startswith("env"):
        raise HTTPException(409, "Clé de configuration : modifie-la dans Paramètres › Configuration")
    try:
        return await asyncio.to_thread(U.patch_key, kid, b.dict(exclude_unset=True))
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.delete("/keys/{kid}")
async def delete_key(kid: str):
    if kid.startswith("env"):
        raise HTTPException(409, "Clé de configuration : modifie-la dans Paramètres › Configuration")
    await asyncio.to_thread(U.del_key, kid)
    return {"ok": True}


@router.post("/keys/{kid}/test")
async def test_key(kid: str):
    try:
        return await asyncio.to_thread(U.test_key, kid)
    except KeyError as e:
        raise HTTPException(404, str(e))