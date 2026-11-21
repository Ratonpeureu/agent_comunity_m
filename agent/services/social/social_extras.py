"""Extras : prompts éditables à chaud, options vidéo par post, routes /admin/social/prompts."""
import json
import re

from fastapi import APIRouter, Body, Depends, HTTPException

from agent.bootstrap import DATA_DIR
from agent.routes.hoock_admin import get_current_admin
from agent.services.social import social_agent_service as svc
from agent.services.social import social_assets as assets
from agent.services.social import social_video as video
from agent.services.social.social_config import SPECS

router = APIRouter(prefix="/admin/social", tags=["Social – prompts"], dependencies=[Depends(get_current_admin)])
STORE = DATA_DIR / "prompts.json"
_REG: dict = {}          # key -> dict(label, group, help, get, set, default)
_done = False


def _mod_entry(key, label, group, mod, attr, help_=""):
    _REG[key] = {"label": label, "group": group, "help": help_, "get": lambda: getattr(mod, attr),
                 "set": lambda v: setattr(mod, attr, v)}


def _spec_entry(plat):
    _REG[f"brief_{plat}"] = {"label": f"Consignes de format : {plat}", "group": "Formats par réseau",
                             "help": "Longueur, ton, hashtags, structure attendue pour ce réseau.",
                             "get": lambda: SPECS[plat]["brief"], "set": lambda v: SPECS[plat].__setitem__("brief", v)}


def _markers(t: str) -> set:
    return set(re.findall(r"<<[A-Z_]+>>", t or ""))


def _load() -> dict:
    try:
        return json.loads(STORE.read_text("utf-8"))
    except Exception:
        return {}


def _save(d: dict):
    STORE.write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")


# ───────── options vidéo par post ─────────
_PASS = ("voix", "sous_titres", "duree_cible")


def _wrap_finalize():
    base = assets.finalize_spec

    def fs(spec, platform, text, catalog, cfg=None, stats=None, stock_ok=False, visuel_requis=False):
        out = base(spec, platform, text, catalog, cfg, stats, stock_ok, visuel_requis)
        for k in _PASS:
            if spec and spec.get(k) is not None:
                out[k] = spec[k]
        return out
    assets.finalize_spec = fs


def _wrap_video():
    orig = video.build_video

    async def build_video(spec, platform, brand, cfg, text, llm_json, script=""):
        c = dict(cfg)
        for k_spec, k_cfg in (("voix", "video_voix_off"), ("sous_titres", "video_sous_titres"), ("duree_cible", "video_duree_cible")):
            if spec.get(k_spec) is not None:
                c[k_cfg] = spec[k_spec]
        return await orig(spec, platform, brand, c, text, llm_json, script)
    video.build_video = build_video


def apply():
    """À appeler APRÈS social_patches.apply()."""
    global _done
    if _done:
        return
    _done = True
    _mod_entry("system_writer", "Rédacteur : consigne système", "Rédaction", svc, "SYSTEM_WRITER", "Règles absolues du community manager (anti-invention, interdits de style).")
    _mod_entry("write_prompt", "Rédacteur : modèle de prompt", "Rédaction", svc, "_WRITE_PROMPT", "Conservez les marqueurs <<CTX>>, <<TITRE>>, <<FAITS>>... et le schéma JSON final.")
    _mod_entry("system_strategist", "Idées : consigne système", "Idées", svc, "SYSTEM_STRATEGE")
    _mod_entry("ideas_prompt", "Idées : modèle de prompt", "Idées", svc, "_IDEAS_PROMPT", "Conservez les marqueurs <<...>> et le schéma JSON final.")
    _mod_entry("system_analyst", "Analyse de marque : consigne système", "Marque", svc, "SYSTEM_ANALYST")
    _mod_entry("vision_intro", "Vision : consigne d'analyse des captures", "Captures", assets, "VISION_INTRO")
    _mod_entry("system_video", "Vidéo : consigne du réalisateur", "Vidéo", video, "SYSTEM_VIDEO")
    for p in SPECS:
        _spec_entry(p)
    saved = _load()
    for k, e in _REG.items():
        e["default"] = e["get"]()
        if k in saved and isinstance(saved[k], str) and saved[k].strip():
            e["set"](saved[k])
    _wrap_finalize()
    _wrap_video()


@router.get("/prompts")
async def list_prompts():
    saved = _load()
    return [{"key": k, "label": e["label"], "group": e["group"], "help": e["help"], "default": e["default"],
             "value": e["get"](), "modifie": k in saved} for k, e in _REG.items()]


@router.put("/prompts/{key}")
async def put_prompt(key: str, body: dict = Body(...)):
    e = _REG.get(key)
    if not e:
        raise HTTPException(404, "Prompt inconnu")
    v = str(body.get("value", "")).strip()
    if len(v) < 20:
        raise HTTPException(422, "Texte trop court")
    missing = _markers(e["default"]) - _markers(v)
    if missing:
        raise HTTPException(422, "Marqueurs obligatoires absents : " + ", ".join(sorted(missing)))
    e["set"](v)
    d = _load()
    d[key] = v
    _save(d)
    return {"ok": True}


@router.delete("/prompts/{key}")
async def reset_prompt(key: str):
    e = _REG.get(key)
    if not e:
        raise HTTPException(404, "Prompt inconnu")
    e["set"](e["default"])
    d = _load()
    d.pop(key, None)
    _save(d)
    return {"ok": True}