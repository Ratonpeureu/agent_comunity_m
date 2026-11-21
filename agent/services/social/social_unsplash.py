# services/social/social_unsplash.py
import logging
import os
import random
import re
import time
from pathlib import Path

import httpx

from agent.services.social.social_config import UPLOAD_DIR

logger = logging.getLogger("social_stock")
CACHE_DIR = Path(UPLOAD_DIR) / "_stock"
UNS = "https://api.unsplash.com"
TTL = 6 * 3600
_mem: dict = {}


def available() -> bool:
    return bool(os.getenv("UNSPLASH_ACCESS_KEY") or os.getenv("PEXELS_API_KEY"))


async def _unsplash(http, q, orient, n):
    key = os.getenv("UNSPLASH_ACCESS_KEY")
    if not key:
        return []
    r = await http.get(f"{UNS}/search/photos", headers={"Authorization": f"Client-ID {key}", "Accept-Version": "v1"},
                       params={"query": q, "orientation": orient, "per_page": n, "content_filter": "high",
                               "order_by": "relevant"})
    if r.status_code != 200:
        logger.warning("Unsplash %s : %s", r.status_code, r.text[:160])
        return []
    ref = f"?utm_source={os.getenv('UNSPLASH_APP_NAME', 'rhmanager')}&utm_medium=referral"
    out = []
    for p in r.json().get("results", []):
        out.append({"source": "unsplash", "id": p["id"],
                    "url": re.sub(r"w=\d+", "w=1800", p["urls"]["regular"]), "thumb": p["urls"]["small"],
                    "dl": p["links"].get("download_location"), "author": p["user"]["name"],
                    "author_url": p["user"]["links"]["html"] + ref, "page_url": p["links"]["html"] + ref,
                    "alt": p.get("alt_description") or ""})
    return out


async def _pexels(http, q, orient, n):
    key = os.getenv("PEXELS_API_KEY")
    if not key:
        return []
    r = await http.get("https://api.pexels.com/v1/search", headers={"Authorization": key},
                       params={"query": q, "orientation": "square" if orient == "squarish" else orient, "per_page": n})
    if r.status_code != 200:
        logger.warning("Pexels %s : %s", r.status_code, r.text[:160])
        return []
    return [{"source": "pexels", "id": str(p["id"]), "url": p["src"]["large2x"], "thumb": p["src"]["medium"],
             "dl": None, "author": p["photographer"], "author_url": p.get("photographer_url", ""),
             "page_url": p["url"], "alt": p.get("alt") or ""} for p in r.json().get("photos", [])]


async def search(query: str, orientation: str = "landscape", n: int = 12) -> list:
    q = (query or "").strip()
    if not q or not available():
        return []
    key = (q.lower(), orientation)
    hit = _mem.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as http:
        res = await _unsplash(http, q, orientation, n) or await _pexels(http, q, orientation, n)
    if res:
        _mem[key] = (time.time(), res)
    return res


async def fetch_photo(query: str, orientation: str = "landscape", pick_from: int = 6) -> dict | None:
    """Télécharge une photo pertinente (variée) et retourne son chemin local + crédit."""
    results = await search(query, orientation)
    if not results:
        return None
    ch = random.choice(results[:pick_from])
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{ch['source']}_{ch['id']}.jpg"
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as http:
            if not path.exists():
                r = await http.get(ch["url"])
                r.raise_for_status()
                path.write_bytes(r.content)
            if ch.get("dl"):     # exigé par les conditions de l'API Unsplash : signaler l'usage
                try:
                    await http.get(ch["dl"], headers={"Authorization": f"Client-ID {os.getenv('UNSPLASH_ACCESS_KEY')}"})
                except Exception:
                    pass
    except Exception as e:
        logger.warning("Téléchargement photo : %s", e)
        return None
    return {**ch, "path": str(path),
            "credit": f"Photo : {ch['author']} / {'Unsplash' if ch['source'] == 'unsplash' else 'Pexels'}"}