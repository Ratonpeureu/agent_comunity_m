# services/social/social_gateway.py
import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta

import httpx

from agent.services.social import social_publishers as legacy
from agent.services.social.social_config import OAUTH_BASE
from agent.services.social.social_publishers import GRAPH, PublishError, _compose, _graph, _is_video, _media_bytes


logger = logging.getLogger("social_gateway")
IG = "https://graph.instagram.com"
IG_V = os.getenv("INSTAGRAM_GRAPH_VERSION", os.getenv("META_GRAPH_VERSION", "v24.0"))
XAPI = "https://api.x.com"
QBASE = os.getenv("QPOST_BASE_URL", "https://qpost.dev").rstrip("/")


def _redirect(p: str) -> str:
    return f"{OAUTH_BASE}/admin/social/oauth/{p}/callback"


def _now() -> int:
    return int(time.time())


def _exp(seconds) -> datetime:
    return datetime.utcnow() + timedelta(seconds=int(seconds))


def configured() -> dict:
    e = os.getenv
    return {
        "facebook": bool(e("META_APP_ID") and e("META_APP_SECRET")),
        "instagram": bool(e("INSTAGRAM_APP_ID") and e("INSTAGRAM_APP_SECRET")),
        "linkedin": bool(e("LINKEDIN_CLIENT_ID") and e("LINKEDIN_CLIENT_SECRET")),
        "x": bool(e("X_CLIENT_ID")),
        "qpost": bool(_qkey()),
    }


# ═════════════════════ FACEBOOK (Pages uniquement) ═════════════════════
async def _meta_pages(http, tok) -> list:
    found = {}
    d = await _graph(http, "GET", "me/accounts", tok, fields="id,name,access_token", limit=100)
    for p in d.get("data", []):
        found[p["id"]] = p
    if not found:   # Pages gérées via un portefeuille Business (nouvelle expérience Pages)
        try:
            biz = await _graph(http, "GET", "me/businesses", tok, fields="id,name", limit=50)
            for b in biz.get("data", []):
                for edge in ("owned_pages", "client_pages"):
                    try:
                        r = await _graph(http, "GET", f"{b['id']}/{edge}", tok, fields="id,name,access_token", limit=100)
                        for p in r.get("data", []):
                            if p.get("access_token"):
                                found[p["id"]] = p
                    except PublishError:
                        pass
        except PublishError:
            pass
    return list(found.values())


async def _fb_token_state(http, token: str) -> tuple[bool, int]:
    """(valide, expires_at) via /debug_token. expires_at = 0 → jeton sans expiration (Page)."""
    app = f"{os.getenv('META_APP_ID')}|{os.getenv('META_APP_SECRET')}"
    try:
        r = await http.get(f"{GRAPH}/debug_token", params={"input_token": token, "access_token": app})
        d = r.json().get("data") or {}
        return bool(d.get("is_valid", True)), int(d.get("expires_at") or 0)
    except Exception:
        return True, 0


async def _oauth_facebook(code: str) -> list:
    base = {"client_id": os.getenv("META_APP_ID"), "client_secret": os.getenv("META_APP_SECRET")}
    async with httpx.AsyncClient(timeout=40) as http:
        r = await http.get(f"{GRAPH}/oauth/access_token", params={**base, "redirect_uri": _redirect("facebook"), "code": code})
        short = r.json()
        if "access_token" not in short:
            raise PublishError("Meta OAuth : " + str(short.get("error", {}).get("message", short))[:200])
        r = await http.get(f"{GRAPH}/oauth/access_token",
                           params={**base, "grant_type": "fb_exchange_token", "fb_exchange_token": short["access_token"]})
        ll = r.json()
        if "access_token" not in ll:       # plus de repli silencieux sur le jeton court
            raise PublishError("Meta : échange vers un jeton longue durée refusé : "
                               + str(ll.get("error", {}).get("message", ll))[:200])
        pages = await _meta_pages(http, ll["access_token"])
        wanted = os.getenv("META_PAGE_ID")
        if wanted:
            pages = [p for p in pages if p["id"] == wanted] or pages
        if not pages:
            perms = (await _graph(http, "GET", "me/permissions", ll["access_token"])).get("data", [])
            ok = ", ".join(x["permission"] for x in perms if x.get("status") == "granted") or "aucune"
            ko = ", ".join(x["permission"] for x in perms if x.get("status") != "granted") or "aucune"
            raise PublishError("Facebook ne publie que sur une PAGE. Aucune Page trouvée : crée-en une, reconnecte-toi et "
                               f"COCHE-la dans la fenêtre Meta. Accordées : {ok}. Refusées : {ko}.")
        page = pages[0]
        valid, exp = await _fb_token_state(http, page["access_token"])
        if not valid:
            raise PublishError("Meta a renvoyé un jeton de Page invalide : reconnecte-toi.")
        if exp and exp - _now() < 7 * 86400:
            raise PublishError("Meta a renvoyé un jeton de Page à durée courte : vérifie que META_APP_ID / META_APP_SECRET "
                               "sont ceux de l'app utilisée pour la connexion, puis reconnecte-toi.")
        return [{"plateforme": "facebook", "nom": page["name"], "identifiant": page["id"],
                 "expire_le": datetime.utcfromtimestamp(exp) if exp else None,
                 "creds": {"page_id": page["id"], "page_access_token": page["access_token"], "exp_ts": exp}}]


# ═════════════════════ INSTAGRAM LOGIN (sans Page) ═════════════════════
def _ig_url(state: str) -> str:
    if not os.getenv("INSTAGRAM_APP_ID"):
        raise PublishError("INSTAGRAM_APP_ID manquant dans le .env")
    q = {"client_id": os.getenv("INSTAGRAM_APP_ID"), "redirect_uri": _redirect("instagram"), "response_type": "code",
         "scope": os.getenv("INSTAGRAM_SCOPES", "instagram_business_basic,instagram_business_content_publish"), "state": state}
    return "https://www.instagram.com/oauth/authorize?" + urllib.parse.urlencode(q)


async def _igcall(http, method, path, tok, **params):
    params["access_token"] = tok
    url = f"{IG}/{IG_V}/{path}"
    r = await (http.get(url, params=params) if method == "GET" else http.post(url, data=params))
    d = r.json() if r.content else {}
    if r.status_code >= 400 or "error" in d:
        raise PublishError("Instagram API : " + str((d.get("error") or {}).get("message") or r.text[:300]))
    return d


async def _oauth_instagram(code: str) -> list:
    code = code.split("#")[0]
    async with httpx.AsyncClient(timeout=40) as http:
        r = await http.post("https://api.instagram.com/oauth/access_token", data={
            "client_id": os.getenv("INSTAGRAM_APP_ID"), "client_secret": os.getenv("INSTAGRAM_APP_SECRET"),
            "grant_type": "authorization_code", "redirect_uri": _redirect("instagram"), "code": code})
        d = r.json()
        if isinstance(d.get("data"), list) and d["data"]:
            d = d["data"][0]
        if "access_token" not in d:
            raise PublishError("Instagram OAuth : " + str(d.get("error_message") or d.get("error") or d)[:250])
        short = d["access_token"]
        r = await http.get(f"{IG}/access_token", params={"grant_type": "ig_exchange_token",
                           "client_secret": os.getenv("INSTAGRAM_APP_SECRET"), "access_token": short})
        ll = r.json()
        tok, exp = ll.get("access_token", short), int(ll.get("expires_in", 5184000))
        me = await _igcall(http, "GET", "me", tok, fields="user_id,username,account_type")
        if str(me.get("account_type", "")).upper() == "PERSONAL":
            raise PublishError("Compte Instagram personnel : passe-le en compte Professionnel/Créateur "
                               "(Instagram → Paramètres → Type de compte, gratuit), puis reconnecte.")
        igid = str(me.get("user_id") or d.get("user_id") or me.get("id"))
        return [{"plateforme": "instagram", "nom": me.get("username", ""), "identifiant": igid, "expire_le": _exp(exp),
                 "creds": {"login": "instagram", "access_token": tok, "ig_user_id": igid,
                           "exp_ts": _now() + exp, "obtained_at": _now()}}]


async def _pub_ig(http, p, c):
    tok, ig = c["access_token"], c["ig_user_id"]
    media = p.get("media_urls") or []
    if not media:
        raise PublishError("Instagram exige au moins un visuel")
    cap = _compose(p)
    if len(media) == 1:
        if _is_video(media[0]):
            cont = await _igcall(http, "POST", f"{ig}/media", tok, media_type="REELS", video_url=media[0], caption=cap)
        else:
            cont = await _igcall(http, "POST", f"{ig}/media", tok, image_url=media[0], caption=cap)
    else:
        kids = []
        for u in media[:10]:
            kids.append((await _igcall(http, "POST", f"{ig}/media", tok, image_url=u, is_carousel_item="true"))["id"])
        cont = await _igcall(http, "POST", f"{ig}/media", tok, media_type="CAROUSEL", children=",".join(kids), caption=cap)
    for _ in range(60):
        st = (await _igcall(http, "GET", cont["id"], tok, fields="status_code")).get("status_code")
        if st == "FINISHED":
            break
        if st in ("ERROR", "EXPIRED"):
            raise PublishError(f"Instagram : traitement du média en erreur ({st})")
        await asyncio.sleep(4)
    pub = await _igcall(http, "POST", f"{ig}/media_publish", tok, creation_id=cont["id"])
    link = await _igcall(http, "GET", pub["id"], tok, fields="permalink")
    return {"external_id": pub["id"], "external_url": link.get("permalink")}


async def _try_ig_insight(http, pid, tok, metric):
    try:
        d = await _igcall(http, "GET", f"{pid}/insights", tok, metric=metric)
        return (d.get("data") or [{}])[0].get("values", [{}])[0].get("value")
    except PublishError:
        return None


# ═════════════════════ X (OAuth2 PKCE) ═════════════════════
def _x_verifier(state: str) -> str:
    h = hashlib.sha256((os.getenv("SOCIAL_FERNET_KEY", "") + state).encode()).digest()
    return base64.urlsafe_b64encode(h).decode().rstrip("=")


def _x_url(state: str) -> str:
    if not os.getenv("X_CLIENT_ID"):
        raise PublishError("X_CLIENT_ID manquant dans le .env")
    ch = base64.urlsafe_b64encode(hashlib.sha256(_x_verifier(state).encode()).digest()).decode().rstrip("=")
    q = {"response_type": "code", "client_id": os.getenv("X_CLIENT_ID"), "redirect_uri": _redirect("x"),
         "scope": os.getenv("X_SCOPES", "tweet.read tweet.write users.read media.write offline.access"),
         "state": state, "code_challenge": ch, "code_challenge_method": "S256"}
    return "https://x.com/i/oauth2/authorize?" + urllib.parse.urlencode(q)


async def _x_token(http, data: dict) -> dict:
    cid, sec = os.getenv("X_CLIENT_ID"), os.getenv("X_CLIENT_SECRET")
    kw = {"auth": (cid, sec)} if sec else {}
    if not sec:
        data = {**data, "client_id": cid}
    r = await http.post(f"{XAPI}/2/oauth2/token", data=data, **kw)
    d = r.json()
    if "access_token" not in d:
        raise PublishError("X OAuth : " + str(d.get("error_description") or d.get("error") or d)[:250])
    return d


async def _oauth_x(code: str, state: str) -> list:
    async with httpx.AsyncClient(timeout=40) as http:
        d = await _x_token(http, {"grant_type": "authorization_code", "code": code, "redirect_uri": _redirect("x"),
                                  "code_verifier": _x_verifier(state)})
        me = await http.get(f"{XAPI}/2/users/me", headers={"Authorization": f"Bearer {d['access_token']}"})
        u = (me.json().get("data") or {})
        exp = int(d.get("expires_in", 7200))
        return [{"plateforme": "x", "nom": "@" + u.get("username", "x"), "identifiant": u.get("id"), "expire_le": _exp(exp),
                 "creds": {"access_token": d["access_token"], "refresh_token": d.get("refresh_token"),
                           "user_id": u.get("id"), "username": u.get("username"), "exp_ts": _now() + exp}}]


async def _x_upload(http, tok, url):
    img = await http.get(url)
    img.raise_for_status()
    r = await http.post(f"{XAPI}/2/media/upload", headers={"Authorization": f"Bearer {tok}"},
                        data={"media_category": "tweet_image"}, files={"media": ("visuel.jpg", img.content, "image/jpeg")})
    try:
        d = r.json()
    except Exception:
        d = {}
    mid = (d.get("data") or {}).get("id") or d.get("media_id_string")
    if r.status_code >= 400 or not mid:
        raise PublishError(f"X upload média {r.status_code} : {r.text[:250]}")
    return str(mid)

async def _x_upload_video(http, tok, url):
    data = await _media_bytes(http, url)
    h = {"Authorization": f"Bearer {tok}"}
    r = await http.post(f"{XAPI}/2/media/upload/initialize", headers=h,
                        json={"media_type": "video/mp4", "total_bytes": len(data), "media_category": "tweet_video"})
    d = r.json() if r.content else {}
    mid = (d.get("data") or {}).get("id")
    if r.status_code >= 400 or not mid:
        raise PublishError(f"X vidéo (init) {r.status_code} : {r.text[:250]}")
    CH = 4 * 1024 * 1024
    for i in range(0, len(data), CH):
        a = await http.post(f"{XAPI}/2/media/upload/{mid}/append", headers=h, data={"segment_index": str(i // CH)},
                            files={"media": ("chunk.mp4", data[i:i + CH], "application/octet-stream")})
        if a.status_code >= 400:
            raise PublishError(f"X vidéo (envoi) {a.status_code} : {a.text[:250]}")
    f = await http.post(f"{XAPI}/2/media/upload/{mid}/finalize", headers=h)
    if f.status_code >= 400:
        raise PublishError(f"X vidéo (finalisation) {f.status_code} : {f.text[:250]}")
    info = ((f.json() if f.content else {}).get("data") or {}).get("processing_info")
    for _ in range(40):
        if not info or info.get("state") == "succeeded":
            break
        if info.get("state") == "failed":
            raise PublishError("X : traitement de la vidéo en échec " + str(info.get("error", ""))[:150])
        await asyncio.sleep(min(int(info.get("check_after_secs", 3)), 10))
        s = await http.get(f"{XAPI}/2/media/upload", headers=h, params={"command": "STATUS", "media_id": mid})
        info = ((s.json() if s.content else {}).get("data") or {}).get("processing_info")
    return str(mid)


async def _pub_x(http, p, c):
    tok = c["access_token"]
    body = (p.get("contenu") or "").strip()
    tags = " ".join(t if t.startswith("#") else f"#{t}" for t in (p.get("hashtags") or [])[:2])
    room = 280 - (len(tags) + 2 if tags else 0)
    if len(body) > room:
        body = body[:room - 1].rstrip() + "…"
    payload = {"text": body + (f"\n\n{tags}" if tags else "")}
    media = p.get("media_urls") or []
    videos = [u for u in media if _is_video(u)]
    images = [u for u in media if not _is_video(u)][:4]
    if videos:
        payload["media"] = {"media_ids": [await _x_upload_video(http, tok, videos[0])]}   # erreur explicite, pas de repli
    elif images:
        try:
            payload["media"] = {"media_ids": [await _x_upload(http, tok, u) for u in images]}
        except PublishError as e:
            logger.warning("X : post sans image (%s)", e)
    r = await http.post(f"{XAPI}/2/tweets", headers={"Authorization": f"Bearer {tok}"}, json=payload)
    d = r.json() if r.content else {}
    if r.status_code == 402:
        raise PublishError("X : crédits insuffisants — recharge dans developer.x.com → Billing")
    if r.status_code >= 400 or "data" not in d:
        raise PublishError(f"X API {r.status_code} : {str(d.get('detail') or d.get('title') or r.text)[:300]}")
    tid = d["data"]["id"]
    return {"external_id": tid, "external_url": f"https://x.com/{c.get('username') or 'i/web'}/status/{tid}"}

# ═════════════════════ QPOST (TikTok, Instagram…) ═════════════════════
def _qkey():
    return os.getenv("QPOST_API_KEY") or os.getenv("QPOST_API")


def _walk(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from _walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk(v)


def _find(o, keys):
    for d in _walk(o):
        for k in keys:
            v = d.get(k)
            if isinstance(v, (str, int, float)) and v != "":
                return v
    return None


async def _qrpc(method: str, params: dict | None = None, timeout: float = 120) -> dict:
    key = _qkey()
    if not key:
        raise PublishError("QPOST_API_KEY non configurée dans le .env")
    headers = {"x-api-key": key, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    body = {"jsonrpc": "2.0", "id": secrets.token_hex(4), "method": method, "params": params or {}}
    async with httpx.AsyncClient(timeout=timeout) as http:
        r = await http.post(f"{QBASE}/mcp", headers=headers, json=body)
    if r.status_code in (401, 403):
        raise PublishError("QPost : clé API refusée")
    msg = None
    if "text/event-stream" in r.headers.get("content-type", ""):
        for line in r.text.splitlines():
            if line.startswith("data:"):
                try:
                    j = json.loads(line[5:].strip())
                except Exception:
                    continue
                if "result" in j or "error" in j:
                    msg = j
                    break
    else:
        try:
            msg = r.json()
        except Exception:
            msg = None
    if not msg:
        raise PublishError(f"QPost : réponse illisible ({r.status_code}) {r.text[:200]}")
    if "error" in msg:
        raise PublishError("QPost : " + str(msg["error"].get("message", msg["error"]))[:400])
    return msg["result"]


async def qpost_call(tool: str, args: dict, timeout: float = 120):
    res = await _qrpc("tools/call", {"name": tool, "arguments": args}, timeout)
    txt = "\n".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
    if res.get("isError"):
        raise PublishError("QPost : " + txt[:400])
    if res.get("structuredContent"):
        return res["structuredContent"]
    try:
        return json.loads(txt)
    except Exception:
        return {"text": txt}


async def qpost_tools():
    return (await _qrpc("tools/list")).get("tools", [])


async def qpost_accounts() -> list:
    res = await qpost_call("list_connected_accounts", {})
    out, seen = [], set()
    for d in _walk(res):
        plat = str(d.get("platform") or d.get("provider") or d.get("type") or "").lower()
        if plat in ("tiktok", "instagram", "youtube"):
            key = (plat, str(d.get("id") or d.get("username") or d.get("name")))
            if key in seen:
                continue
            seen.add(key)
            out.append({"platform": plat, "id": d.get("id"), "status": str(d.get("status") or "connecté"),
                        "name": d.get("displayName") or d.get("username") or d.get("name") or plat})
    return out


_QP_SHAPE = {"i": 0}


def _qp_shapes(platform: str) -> list:
    meta = {"privacyLevel": os.getenv("QPOST_TIKTOK_PRIVACY", "PUBLIC_TO_EVERYONE")} if platform == "tiktok" else {}
    return [[{"platform": platform, **({"metadata": meta} if meta else {})}], [{"platform": platform}],
            [platform], {platform: meta}]


async def _pub_qpost(p):
    platform = p["plateforme"]
    media = p.get("media_urls") or []
    if not media:
        raise PublishError(f"{platform} via QPost exige une vidéo ou des images")
    args = {"caption": _compose(p)[:2200]}
    if _is_video(media[0]):
        args.update(mediaKind="video", mediaUrl=media[0])
    elif len(media) == 1:
        args.update(mediaKind="image", mediaUrl=media[0])
    else:
        args.update(mediaKind="image", imageUrls=media[:10])
    if platform == "tiktok":
        args["title"] = ((p.get("contenu") or "").strip().splitlines() or [""])[0][:90]
    shapes, res, last = _qp_shapes(platform), None, None
    order = [_QP_SHAPE["i"]] + [i for i in range(len(shapes)) if i != _QP_SHAPE["i"]]
    for i in order:
        try:
            res = await qpost_call("create_post", {**args, "platforms": shapes[i]})
            _QP_SHAPE["i"] = i
            break
        except PublishError as e:
            last = e
            if not any(k in str(e).lower() for k in ("platform", "invalid", "validation", "expected", "schema", "required")):
                raise
    if res is None:
        raise last
    pid = _find(res, ("id", "postId", "post_id"))
    if not pid:
        raise PublishError(f"QPost : id de post introuvable dans {str(res)[:200]}")
    info = {}
    for _ in range(14):      # suit le statut ~2 min : TikTok peut échouer après coup
        await asyncio.sleep(8)
        try:
            info = await qpost_call("get_post", {"id": str(pid)})
        except PublishError:
            continue
        s = json.dumps(info).lower()
        if '"failed"' in s or '"error"' in s and '"status": "error' in s:
            raise PublishError("QPost : échec de publication — " + str(_find(info, ("error", "errorMessage", "failReason", "message")))[:250])
        if any(k in s for k in ('"published"', '"success"', '"completed"', '"posted"')):
            break
    return {"external_id": str(pid), "external_url": _find(info, ("url", "publicUrl", "permalink", "postUrl"))}


async def _metrics_qpost(post):
    d = await qpost_call("get_post_stats", {"id": str(post["external_id"])})
    g = lambda *k: int(_find(d, k) or 0)
    return dict(impressions=g("impressions"), reach=g("reach"), video_views=g("views", "viewCount", "plays"),
                likes=g("likes", "likeCount"), comments=g("comments", "commentCount"),
                shares=g("shares", "shareCount"), saves=g("saves", "favorites"), clicks=0)


# ═════════════════════ API PUBLIQUE (même interface que social_publishers) ═════════════════════
async def publish(platform: str, post: dict, creds: dict) -> dict:
    try:
        if creds.get("via") == "qpost":
            return await _pub_qpost(post)
        async with httpx.AsyncClient(timeout=90) as http:
            if platform == "x":
                return await _pub_x(http, post, creds)
            if platform == "instagram" and creds.get("login") == "instagram":
                return await _pub_ig(http, post, creds)
        return await legacy.publish(platform, post, creds)
    except httpx.HTTPError as e:
        raise PublishError(f"Réseau : {e}")


async def fetch_metrics(platform: str, post: dict, creds: dict) -> dict:
    if creds.get("via") == "qpost":
        return await _metrics_qpost(post)
    m = dict(impressions=0, reach=0, video_views=0, likes=0, comments=0, shares=0, saves=0, clicks=0)
    if platform == "x":
        async with httpx.AsyncClient(timeout=30) as http:
            r = await http.get(f"{XAPI}/2/tweets/{post['external_id']}", params={"tweet.fields": "public_metrics"},
                               headers={"Authorization": f"Bearer {creds['access_token']}"})
        pm = (r.json().get("data") or {}).get("public_metrics", {})
        m.update(likes=pm.get("like_count", 0), comments=pm.get("reply_count", 0),
                 shares=pm.get("retweet_count", 0) + pm.get("quote_count", 0),
                 impressions=pm.get("impression_count", 0), saves=pm.get("bookmark_count", 0))
        return {k: int(v or 0) for k, v in m.items()}
    if platform == "instagram" and creds.get("login") == "instagram":
        async with httpx.AsyncClient(timeout=30) as http:
            tok, pid = creds["access_token"], post["external_id"]
            d = await _igcall(http, "GET", pid, tok, fields="like_count,comments_count")
            m["likes"], m["comments"] = d.get("like_count", 0), d.get("comments_count", 0)
            for key, metric in (("reach", "reach"), ("impressions", "views"), ("saves", "saved"), ("shares", "shares")):
                m[key] = await _try_ig_insight(http, pid, tok, metric) or 0
        return {k: int(v or 0) for k, v in m.items()}
    return await legacy.fetch_metrics(platform, post, creds)


async def fetch_followers(platform: str, creds: dict):
    if creds.get("via") == "qpost":
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as http:
            if platform == "x":
                r = await http.get(f"{XAPI}/2/users/me", params={"user.fields": "public_metrics"},
                                   headers={"Authorization": f"Bearer {creds['access_token']}"})
                pm = (r.json().get("data") or {}).get("public_metrics", {})
                return {"followers": pm.get("followers_count", 0), "media_count": pm.get("tweet_count")}
            if platform == "instagram" and creds.get("login") == "instagram":
                d = await _igcall(http, "GET", "me", creds["access_token"], fields="followers_count,media_count")
                return {"followers": d.get("followers_count", 0), "media_count": d.get("media_count")}
    except Exception:
        return None
    return await legacy.fetch_followers(platform, creds)


async def verify(platform: str, creds: dict) -> str:
    if creds.get("via") == "qpost":
        accs = [a for a in await qpost_accounts() if a["platform"] == platform]
        if not accs:
            raise PublishError(f"{platform} n'est plus connecté dans QPost")
        return accs[0]["name"]
    async with httpx.AsyncClient(timeout=30) as http:
        if platform == "x":
            r = await http.get(f"{XAPI}/2/users/me", headers={"Authorization": f"Bearer {creds['access_token']}"})
            u = r.json().get("data")
            if not u:
                raise PublishError(f"X : {r.text[:200]}")
            return "@" + u.get("username", "")
        if platform == "instagram" and creds.get("login") == "instagram":
            return (await _igcall(http, "GET", "me", creds["access_token"], fields="username")).get("username", "")
    return await legacy.verify(platform, creds)


async def ensure_fresh(platform: str, creds: dict):
    """Retourne (creds, expire_le|None, changé). Appelé avant chaque publication."""
    if creds.get("via") == "qpost":
        return creds, None, False
    now = _now()
    async with httpx.AsyncClient(timeout=30) as http:
        if platform == "x" and creds.get("refresh_token") and creds.get("exp_ts", 0) - now < 300:
            d = await _x_token(http, {"grant_type": "refresh_token", "refresh_token": creds["refresh_token"]})
            exp = int(d.get("expires_in", 7200))
            return ({**creds, "access_token": d["access_token"], "refresh_token": d.get("refresh_token", creds["refresh_token"]),
                     "exp_ts": now + exp}, _exp(exp), True)
        if (platform == "instagram" and creds.get("login") == "instagram"
                and creds.get("exp_ts", 0) - now < 7 * 86400 and now - creds.get("obtained_at", 0) > 86400):
            r = await http.get(f"{IG}/refresh_access_token", params={"grant_type": "ig_refresh_token", "access_token": creds["access_token"]})
            d = r.json()
            if d.get("access_token"):
                exp = int(d.get("expires_in", 5184000))
                return ({**creds, "access_token": d["access_token"], "exp_ts": now + exp, "obtained_at": now}, _exp(exp), True)
    return creds, None, False


async def refresh_credentials(platform: str, creds: dict):
    return await legacy.refresh_credentials(platform, creds)


def oauth_url(platform: str, state: str) -> str:
    if platform == "instagram":
        return _ig_url(state)
    if platform == "x":
        return _x_url(state)
    if platform == "tiktok":
        raise PublishError("TikTok se connecte dans QPost (qpost.dev), puis « Synchroniser depuis QPost ».")
    return legacy.oauth_url(platform, state)


async def oauth_exchange(platform: str, code: str, state: str = "") -> list:
    if platform == "facebook":
        return await _oauth_facebook(code)
    if platform == "instagram":
        return await _oauth_instagram(code)
    if platform == "x":
        return await _oauth_x(code, state)
    return await legacy.oauth_exchange(platform, code)