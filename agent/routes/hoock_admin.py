"""Authentification admin unique (identifiant + mot de passe définis au premier démarrage)."""
import os
import secrets
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from agent.bootstrap import verify_password

ADMIN_SECRET_KEY = os.getenv("ADMIN_JWT_SECRET_KEY") or secrets.token_hex(32)
ALGORITHM = "HS256"
EXPIRE_MIN = int(os.getenv("ADMIN_TOKEN_EXPIRE_MINUTES", "1440"))
oauth2_scheme_admin = OAuth2PasswordBearer(tokenUrl="/admin/login")
router = APIRouter(prefix="/admin", tags=["Admin"])
_attempts: dict = {}


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/login")
async def admin_login(body: LoginBody, request: Request):
    ip = request.client.host if request.client else "?"
    now = time.time()
    recent = [t for t in _attempts.get(ip, []) if now - t < 60]
    if len(recent) >= 8:
        raise HTTPException(429, "Trop de tentatives, réessaie dans une minute")
    ok = (body.username == os.getenv("ADMIN_USERNAME", "admin")
          and verify_password(body.password, os.getenv("ADMIN_PASSWORD_HASH", "")))
    if not ok:
        _attempts[ip] = recent + [now]
        raise HTTPException(401, "Identifiants incorrects")
    token = jwt.encode({"sub": "admin", "username": body.username,
                        "exp": datetime.utcnow() + timedelta(minutes=EXPIRE_MIN)},
                       ADMIN_SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "token_type": "bearer", "admin_id": "admin", "username": body.username}


async def get_current_admin(token: str = Depends(oauth2_scheme_admin)):
    try:
        p = jwt.decode(token, ADMIN_SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session invalide ou expirée",
                            headers={"WWW-Authenticate": "Bearer"})
    return SimpleNamespace(id=p.get("sub", "admin"), username=p.get("username", "admin"))