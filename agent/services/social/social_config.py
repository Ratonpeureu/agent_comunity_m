# services/social/social_config.py
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from cryptography.fernet import Fernet

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://rhmanager.site").rstrip("/")
OAUTH_BASE = os.getenv("SOCIAL_OAUTH_REDIRECT_BASE", os.getenv("API_BASE", PUBLIC_BASE_URL)).rstrip("/")
UPLOAD_DIR = "/app/uploads/social"
try:
    os.makedirs(UPLOAD_DIR, exist_ok=True)
except OSError:
    pass

TZ = ZoneInfo(os.getenv("SOCIAL_TZ", "Africa/Dakar"))


PLATFORMS = ("facebook", "instagram", "linkedin", "x", "tiktok")



SPECS = {
    "linkedin": {
        "max": 3000, "hashtags": 3, "visuel_requis": False,
        "brief": "LinkedIn : 900-1100 caractères, 1ère ligne = accroche forte (avant le 'voir plus'), "
                 "paragraphes de 1-2 lignes, ton expert mais humain, 1 enseignement concret, question ou CTA final, "
                 "3 hashtags max",
    },
    "facebook": {
        "max": 5000, "hashtags": 3, "visuel_requis": False,
        "brief": "Facebook : 250-600 caractères, ton chaleureux et conversationnel, émotion/utilité immédiate, "
                 "question pour déclencher les commentaires, 1-3 emojis, 0-3 hashtags.",
    },
    "instagram": {
        "max": 2200, "hashtags": 10, "visuel_requis": True,
        "brief": "Instagram : légende 100-200 caractères, 1ère ligne accrocheuse (premiers caractères visibles), "
                 "storytelling court, CTA 'enregistre/partage/commente', lien en bio (jamais d'URL cliquable), "
                 "6-10 hashtags ciblés, emojis modérés. Visuel obligatoire.",
    },
    "tiktok": {
        "max": 150, "hashtags": 5, "visuel_requis": True,
        "brief": "TikTok (carrousel photo) : légende ≤150 caractères, très directe, 3-5 hashtags. Visuel = carrousel de 3 à 5 images "
                "(template carrousel, slides avec titre court). script_video = null.",
    },
}

# ── Priors de créneaux (démarrage à froid) : poids jour × poids heure ─────────
_PRIOR_DAYS = {
    "linkedin":  [.90, 1.0, 1.0, .95, .60, .15, .10],
    "facebook":  [.70, .70, .75, .80, .85, .90, .85],
    "instagram": [.75, .75, .75, .80, .85, .90, .85],
    "tiktok":    [.70, .70, .75, .80, .90, 1.0, 1.0],
}
_PRIOR_HOURS = {
    "linkedin":  {7: .7, 8: 1, 9: .9, 10: .7, 12: .9, 13: .7, 17: .8, 18: .5},
    "facebook":  {7: .5, 12: .8, 13: .8, 18: .7, 19: .95, 20: 1, 21: .9, 22: .5},
    "instagram": {8: .4, 12: .9, 13: .8, 18: .8, 19: 1, 20: .95, 21: .8},
    "tiktok":    {12: .5, 18: .7, 19: .9, 20: 1, 21: 1, 22: .8},
}
DEFAULT_ER = {"linkedin": 0.03, "facebook": 0.015, "instagram": 0.03, "tiktok": 0.05}

SPECS["x"] = {
    "max": 280, "hashtags": 2, "visuel_requis": True,
    "brief": "X : ≤ 270 caractères, UNE idée, accroche directe dès les 5 premiers mots, ton incisif, "
             "0-2 hashtags, AUCUN lien (un lien multiplie le coût de publication par 13).",
}
_PRIOR_DAYS["x"] = [.9, 1.0, 1.0, .95, .85, .5, .4]
_PRIOR_HOURS["x"] = {7: .6, 8: .8, 9: .7, 12: 1, 13: .8, 17: .8, 18: .9, 20: .7}
DEFAULT_ER["x"] = 0.02

def prior_score(platform: str, weekday: int, hour: int) -> float:
    d = _PRIOR_DAYS.get(platform, [.7] * 7)[weekday]
    return d * _PRIOR_HOURS.get(platform, {}).get(hour, .12)


# ── Temps ─────────────────────────────────────────────────────────────────────
def utcnow() -> datetime:
    return datetime.utcnow()


def to_local(dt):
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(TZ)


def local_to_utc(dt_local: datetime) -> datetime:
    if dt_local.tzinfo is None:
        dt_local = dt_local.replace(tzinfo=TZ)
    return dt_local.astimezone(timezone.utc).replace(tzinfo=None)


# ── Chiffrement des tokens ────────────────────────────────────────────────────
def _fernet() -> Fernet:
    key = os.getenv("SOCIAL_FERNET_KEY")
    if not key:
        raise RuntimeError("SOCIAL_FERNET_KEY non configurée")
    return Fernet(key.encode())


def enc(data: dict) -> bytes:
    return _fernet().encrypt(json.dumps(data).encode())


def dec(blob: bytes) -> dict:
    return json.loads(_fernet().decrypt(blob).decode())





# ── Formats de publication par réseau ─────────────────────────────────────────
FORMATS = ("texte", "image", "carrousel", "video")
ALLOWED_FORMATS = {
    "linkedin": FORMATS,
    "facebook": FORMATS,
    "instagram": ("image", "carrousel", "video"),
    "x": ("image", "video"),
    "tiktok": ("video", "carrousel"),
}
DEFAULT_FORMAT = {"tiktok": "video"}          # les autres réseaux : None = l'IA choisit


def norm_format(platform: str, fmt=None):
    allowed = ALLOWED_FORMATS.get(platform, FORMATS)
    f = (fmt or "").strip().lower()
    if not f:
        return DEFAULT_FORMAT.get(platform)
    if f in allowed:
        return f
    return "image" if "image" in allowed else allowed[0]





