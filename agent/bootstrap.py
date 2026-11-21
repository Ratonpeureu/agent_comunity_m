"""Charge /data/config.json dans os.environ AVANT tout import applicatif."""
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
CONFIG_PATH = DATA_DIR / "config.json"
BOOT_ID = secrets.token_hex(4)


def read_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text("utf-8"))
    except Exception:
        return {}


def write_config(values: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(values, ensure_ascii=False, indent=2), "utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    tmp.replace(CONFIG_PATH)


def load_config() -> dict:
    (DATA_DIR / "uploads" / "social").mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "branding" / "photos").mkdir(parents=True, exist_ok=True)
    vals = read_config()
    for k, v in vals.items():
        if v not in (None, ""):
            os.environ[k] = str(v)
    os.environ.setdefault("SOCIAL_BRANDING_DIR", str(DATA_DIR / "branding"))
    os.environ.setdefault("SOCIAL_FICHE_TECHNIQUE", str(DATA_DIR / "fiche_technique.yaml"))
    return vals


def is_configured() -> bool:
    v = read_config()
    return bool(v.get("ADMIN_PASSWORD_HASH") and v.get("SOCIAL_FERNET_KEY") and v.get("PUBLIC_BASE_URL"))


def hash_password(pw: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
    return f"pbkdf2${salt}${h}"


def verify_password(pw: str, stored: str) -> bool:
    try:
        _, salt, h = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), 200_000).hex()
        return hmac.compare_digest(calc, h)
    except Exception:
        return False