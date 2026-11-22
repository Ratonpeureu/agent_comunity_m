# services/social/social_publishers.py
import asyncio
import json
import os
import re
import urllib.parse
from datetime import datetime, timedelta

import httpx
from pathlib import Path
from agent.services.social.social_config import OAUTH_BASE, UPLOAD_DIR

GRAPH_V = os.getenv("META_GRAPH_VERSION", "v24.0")
GRAPH = f"https://graph.facebook.com/{GRAPH_V}"
LI = "https://api.linkedin.com"
LI_VERSION = os.getenv("LINKEDIN_VERSION", "202606")
TT = "https://open.tiktokapis.com"


class PublishError(Exception):
    pass


def _is_video(url: str) -> bool:
    return url.lower().split("?")[0].endswith((".mp4", ".mov"))



async def _media_bytes(http, url: str) -> bytes:
    """Lit le fichier directement sur le disque s'il est local, sinon le télécharge."""
    m = re.search(r"/uploads/social/([^/?#]+)$", (url or "").split("?")[0])
    if m:
        p = Path(UPLOAD_DIR) / m.group(1)
        if p.is_file():
            return p.read_bytes()
    r = await http.get(url)
    r.raise_for_status()
    return r.content


def _compose(p: dict) -> str:
    parts = [(p.get("contenu") or "").strip()]
    if p.get("lien") and p["plateforme"] in ("facebook", "linkedin"):
        parts.append(p["lien"])
    tags = " ".join(t if t.startswith("#") else f"#{t}" for t in (p.get("hashtags") or []))
    if tags:
        parts.append(tags)
    return "\n\n".join(x for x in parts if x)


# ═════════════════════════ META ═════════════════════════
async def _graph(http, method, path, token, **params):
    params["access_token"] = token
    if method == "GET":
        r = await http.get(f"{GRAPH}/{path}", params=params)
    else:
        r = await http.post(f"{GRAPH}/{path}", data=params)
    data = r.json() if r.content else {}
    if r.status_code >= 400 or "error" in data:
        raise PublishError(f"Meta API : {data.get('error', {}).get('message', r.text[:300])}")
    return data


async def _pub_facebook(http, p, c):
    page, tok = c["page_id"], c["page_access_token"]
    text, media = _compose(p), p.get("media_urls") or []
    if not media:
        d = await _graph(http, "POST", f"{page}/feed", tok, message=text)
    
    elif _is_video(media[0]):
        r = await http.post(f"https://graph-video.facebook.com/{GRAPH_V}/{page}/videos",
                            data={"file_url": media[0], "description": text, "access_token": tok})
        d = r.json() if r.content else {}
        if r.status_code >= 400 or "error" in d:
            raise PublishError(f"Meta API : {d.get('error', {}).get('message', r.text[:300])}")

    elif len(media) == 1:
        d = await _graph(http, "POST", f"{page}/photos", tok, url=media[0], caption=text)
        d["id"] = d.get("post_id") or d["id"]
    else:
        ids = []
        for u in media[:10]:
            r = await _graph(http, "POST", f"{page}/photos", tok, url=u, published="false")
            ids.append(r["id"])
        att = {f"attached_media[{i}]": json.dumps({"media_fbid": m}) for i, m in enumerate(ids)}
        d = await _graph(http, "POST", f"{page}/feed", tok, message=text, **att)
    return {"external_id": d["id"], "external_url": f"https://www.facebook.com/{d['id']}"}


async def _ig_wait(http, cid, tok):
    for _ in range(40):
        d = await _graph(http, "GET", cid, tok, fields="status_code")
        st = d.get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise PublishError(f"Instagram : conteneur en erreur ({st})")
        await asyncio.sleep(4)
    raise PublishError("Instagram : délai de traitement du média dépassé")


async def _pub_instagram(http, p, c):
    ig, tok = c["ig_user_id"], c["access_token"]
    media = p.get("media_urls") or []
    if not media:
        raise PublishError("Instagram exige au moins un visuel")
    cap = _compose(p)
    if len(media) == 1:
        if _is_video(media[0]):
            cont = await _graph(http, "POST", f"{ig}/media", tok, media_type="REELS", video_url=media[0], caption=cap)
        else:
            cont = await _graph(http, "POST", f"{ig}/media", tok, image_url=media[0], caption=cap)
    else:
        kids = []
        for u in media[:10]:
            k = await _graph(http, "POST", f"{ig}/media", tok, image_url=u, is_carousel_item="true")
            kids.append(k["id"])
        cont = await _graph(http, "POST", f"{ig}/media", tok, media_type="CAROUSEL",
                            children=",".join(kids), caption=cap)
    await _ig_wait(http, cont["id"], tok)
    pub = await _graph(http, "POST", f"{ig}/media_publish", tok, creation_id=cont["id"])
    link = await _graph(http, "GET", pub["id"], tok, fields="permalink")
    return {"external_id": pub["id"], "external_url": link.get("permalink")}


# ═════════════════════════ LINKEDIN ═════════════════════════
_LI_RESERVED = re.compile(r"([\\|{}@\[\]()<>#*_~])")


def _li_text(text: str) -> str:
    out, last = [], 0
    for m in re.finditer(r"#(\w+)", text):
        out.append(_LI_RESERVED.sub(r"\\\1", text[last:m.start()]))
        out.append("{hashtag|\\#|%s}" % m.group(1))
        last = m.end()
    out.append(_LI_RESERVED.sub(r"\\\1", text[last:]))
    return "".join(out)


def _li_headers(tok):
    return {"Authorization": f"Bearer {tok}", "LinkedIn-Version": LI_VERSION,
            "X-Restli-Protocol-Version": "2.0.0", "Content-Type": "application/json"}


async def _li_upload_image(http, tok, owner, url):
    r = await http.post(f"{LI}/rest/images?action=initializeUpload", headers=_li_headers(tok),
                        json={"initializeUploadRequest": {"owner": owner}})
    if r.status_code >= 400:
        raise PublishError(f"LinkedIn upload init : {r.text[:300]}")
    v = r.json()["value"]
    img = await http.get(url)
    img.raise_for_status()
    up = await http.put(v["uploadUrl"], content=img.content, headers={"Authorization": f"Bearer {tok}"})
    if up.status_code >= 400:
        raise PublishError(f"LinkedIn upload : {up.text[:300]}")
    return v["image"]


async def _li_upload_video(http, tok, owner, url):
    data = await _media_bytes(http, url)
    r = await http.post(f"{LI}/rest/videos?action=initializeUpload", headers=_li_headers(tok),
                        json={"initializeUploadRequest": {"owner": owner, "fileSizeBytes": len(data),
                                                          "uploadCaptions": False, "uploadThumbnail": False}})
    if r.status_code >= 400:
        raise PublishError(f"LinkedIn vidéo (init) {r.status_code} : {r.text[:300]}")
    v = r.json()["value"]
    etags = []
    for part in v.get("uploadInstructions", []):
        chunk = data[part["firstByte"]:part["lastByte"] + 1]
        up = await http.put(part["uploadUrl"], content=chunk,
                            headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/octet-stream"})
        if up.status_code >= 400:
            raise PublishError(f"LinkedIn vidéo (envoi) {up.status_code} : {up.text[:300]}")
        etags.append(up.headers.get("etag", ""))
    fin = await http.post(f"{LI}/rest/videos?action=finalizeUpload", headers=_li_headers(tok),
                          json={"finalizeUploadRequest": {"video": v["video"], "uploadToken": v.get("uploadToken", ""),
                                                          "uploadedPartIds": etags}})
    if fin.status_code >= 400:
        raise PublishError(f"LinkedIn vidéo (finalisation) {fin.status_code} : {fin.text[:300]}")
    urn = urllib.parse.quote(v["video"], safe="")
    for _ in range(30):                              # attend la fin du traitement côté LinkedIn
        s = await http.get(f"{LI}/rest/videos/{urn}", headers=_li_headers(tok))
        st = (s.json() if s.status_code == 200 else {}).get("status")
        if st == "AVAILABLE":
            break
        if st == "PROCESSING_FAILED":
            raise PublishError("LinkedIn : traitement de la vidéo en échec")
        await asyncio.sleep(5)
    return v["video"]


async def _pub_linkedin(http, p, c):
    tok, author = c["access_token"], str(c.get("author_urn", "")).strip()
    if not re.match(r"^urn:li:(organization|person):[A-Za-z0-9_-]+$", author):
        raise PublishError(f"LinkedIn : author_urn invalide « {author[:60]} » — corrige LINKEDIN_ORG_ID dans .env puis reconnecte LinkedIn")

    allmedia = p.get("media_urls") or []
    videos = [m for m in allmedia if _is_video(m)]
    media = [m for m in allmedia if not _is_video(m)]
    body = {
        "author": author, "commentary": _li_text(_compose(p)), "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False,
    }
    if videos:
        title = ((p.get("contenu") or "").strip().splitlines() or ["Vidéo"])[0][:80]
        body["content"] = {"media": {"id": await _li_upload_video(http, tok, author, videos[0]), "title": title}}
    elif len(media) == 1:
        body["content"] = {"media": {"id": await _li_upload_image(http, tok, author, media[0]), "altText": "visuel"}}
    elif len(media) > 1:
        ids = [await _li_upload_image(http, tok, author, u) for u in media[:20]]
        body["content"] = {"multiImage": {"images": [{"id": i, "altText": "visuel"} for i in ids]}}
    r = await http.post(f"{LI}/rest/posts", headers=_li_headers(tok), json=body)
    if r.status_code >= 400:
        raise PublishError(f"LinkedIn API {r.status_code} : {r.text[:300]}")
    urn = r.headers.get("x-restli-id", "")
    return {"external_id": urn, "external_url": f"https://www.linkedin.com/feed/update/{urn}"}


# ═════════════════════════ TIKTOK ═════════════════════════
def _tt_headers(tok):
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json; charset=UTF-8"}


async def _pub_tiktok(http, p, c):
    tok = c["access_token"]
    media = p.get("media_urls") or []
    if not media:
        raise PublishError("TikTok exige une vidéo (.mp4) ou des photos : ajoute un média au post")
    title = (p.get("contenu") or "").strip().splitlines()[0][:90] if p.get("contenu") else ""
    tags = " ".join(t if t.startswith("#") else f"#{t}" for t in (p.get("hashtags") or []))
    desc = f"{(p.get('contenu') or '').strip()} {tags}".strip()[:4000]
    privacy = c.get("privacy_level", "SELF_ONLY")  # SELF_ONLY tant que l'app n'est pas auditée
    if _is_video(media[0]):
        url = f"{TT}/v2/post/publish/video/init/"
        body = {"post_info": {"title": desc[:2200], "privacy_level": privacy, "disable_comment": False},
                "source_info": {"source": "PULL_FROM_URL", "video_url": media[0]}}
    else:
        url = f"{TT}/v2/post/publish/content/init/"
        body = {"post_info": {"title": title, "description": desc, "privacy_level": privacy,
                              "disable_comment": False, "auto_add_music": True},
                "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": 0, "photo_images": media[:35]},
                "post_mode": c.get("post_mode", "DIRECT_POST"), "media_type": "PHOTO"}
    r = await http.post(url, headers=_tt_headers(tok), json=body)
    d = r.json()
    if r.status_code >= 400 or d.get("error", {}).get("code") not in (None, "ok"):
        raise PublishError(f"TikTok : {d.get('error', {}).get('message', r.text[:300])}")
    pid = d["data"]["publish_id"]
    public_id = None
    for _ in range(20):
        await asyncio.sleep(5)
        s = await http.post(f"{TT}/v2/post/publish/status/fetch/", headers=_tt_headers(tok), json={"publish_id": pid})
        sd = s.json().get("data", {})
        st = sd.get("status")
        if st == "PUBLISH_COMPLETE":
            ids = sd.get("publicaly_available_post_id") or []
            public_id = str(ids[0]) if ids else None
            break
        if st == "FAILED":
            raise PublishError(f"TikTok : échec ({sd.get('fail_reason')})")
    return {"external_id": public_id or pid, "external_url": None}


async def publish(platform: str, post: dict, creds: dict) -> dict:
    fn = {"facebook": _pub_facebook, "instagram": _pub_instagram,
          "linkedin": _pub_linkedin, "tiktok": _pub_tiktok}[platform]
    try:
        async with httpx.AsyncClient(timeout=90) as http:
            return await fn(http, post, creds)
    except httpx.HTTPError as e:
        raise PublishError(f"Réseau : {e}")


# ═════════════════════════ MÉTRIQUES ═════════════════════════
async def _try_insight(http, post_id, tok, metric):
    try:
        d = await _graph(http, "GET", f"{post_id}/insights", tok, metric=metric)
        return (d.get("data") or [{}])[0].get("values", [{}])[0].get("value")
    except PublishError:
        return None


async def fetch_metrics(platform: str, post: dict, creds: dict) -> dict:
    """Retourne un dict normalisé : impressions, reach, video_views, likes, comments, shares, saves, clicks."""
    pid = post["external_id"]
    m = dict(impressions=0, reach=0, video_views=0, likes=0, comments=0, shares=0, saves=0, clicks=0)
    async with httpx.AsyncClient(timeout=40) as http:
        if platform == "facebook":
            tok = creds["page_access_token"]
            d = await _graph(http, "GET", pid, tok,
                             fields="shares,reactions.summary(true).limit(0),comments.summary(true).limit(0)")
            m["likes"] = d.get("reactions", {}).get("summary", {}).get("total_count", 0)
            m["comments"] = d.get("comments", {}).get("summary", {}).get("total_count", 0)
            m["shares"] = (d.get("shares") or {}).get("count", 0)
            m["impressions"] = await _try_insight(http, pid, tok, "post_media_view") or 0
            m["reach"] = await _try_insight(http, pid, tok, "post_total_media_view_unique") or 0
            m["clicks"] = await _try_insight(http, pid, tok, "post_clicks") or 0
        elif platform == "instagram":
            tok = creds["access_token"]
            d = await _graph(http, "GET", pid, tok, fields="like_count,comments_count")
            m["likes"], m["comments"] = d.get("like_count", 0), d.get("comments_count", 0)
            for key, metric in (("reach", "reach"), ("impressions", "views"),
                                ("saves", "saved"), ("shares", "shares")):
                m[key] = await _try_insight(http, pid, tok, metric) or 0
        elif platform == "linkedin":
            h = _li_headers(creds["access_token"])
            r = await http.get(f"{LI}/rest/socialActions/{urllib.parse.quote(pid, safe='')}", headers=h)
            if r.status_code == 200:
                d = r.json()
                m["likes"] = d.get("likesSummary", {}).get("totalLikes", 0)
                m["comments"] = d.get("commentsSummary", {}).get("aggregatedTotalComments", 0)
            org = creds["author_urn"] if "organization" in creds.get("author_urn", "") else None
            if org:
                q = (f"{LI}/rest/organizationalEntityShareStatistics?q=organizationalEntity"
                     f"&organizationalEntity={urllib.parse.quote(org, safe='')}"
                     f"&shares=List({urllib.parse.quote(pid, safe='')})")
                s = await http.get(q, headers=h)
                if s.status_code == 200 and s.json().get("elements"):
                    t = s.json()["elements"][0].get("totalShareStatistics", {})
                    m.update(impressions=t.get("impressionCount", 0), reach=t.get("uniqueImpressionsCount", 0),
                             clicks=t.get("clickCount", 0), shares=t.get("shareCount", m["shares"]))
        elif platform == "tiktok" and str(pid).isdigit():
            r = await http.post(f"{TT}/v2/video/query/?fields=id,like_count,comment_count,share_count,view_count",
                                headers=_tt_headers(creds["access_token"]), json={"filters": {"video_ids": [pid]}})
            vids = r.json().get("data", {}).get("videos", [])
            if vids:
                v = vids[0]
                m.update(likes=v.get("like_count", 0), comments=v.get("comment_count", 0),
                         shares=v.get("share_count", 0), video_views=v.get("view_count", 0))
    return {k: int(v or 0) for k, v in m.items()}


async def fetch_followers(platform: str, creds: dict) -> dict | None:
    async with httpx.AsyncClient(timeout=30) as http:
        try:
            if platform == "facebook":
                d = await _graph(http, "GET", creds["page_id"], creds["page_access_token"],
                                 fields="followers_count,fan_count")
                return {"followers": d.get("followers_count") or d.get("fan_count") or 0, "media_count": None}
            if platform == "instagram":
                d = await _graph(http, "GET", creds["ig_user_id"], creds["access_token"],
                                 fields="followers_count,media_count")
                return {"followers": d.get("followers_count", 0), "media_count": d.get("media_count")}
            if platform == "linkedin" and "organization" in creds.get("author_urn", ""):
                org = urllib.parse.quote(creds["author_urn"], safe="")
                r = await http.get(f"{LI}/rest/networkSizes/{org}?edgeType=COMPANY_FOLLOWED_BY_MEMBER",
                                   headers=_li_headers(creds["access_token"]))
                if r.status_code == 200:
                    return {"followers": r.json().get("firstDegreeSize", 0), "media_count": None}
            if platform == "tiktok":
                r = await http.get(f"{TT}/v2/user/info/?fields=follower_count,video_count",
                                   headers=_tt_headers(creds["access_token"]))
                u = r.json().get("data", {}).get("user", {})
                if u:
                    return {"followers": u.get("follower_count", 0), "media_count": u.get("video_count")}
        except Exception:
            return None
    return None


async def verify(platform: str, creds: dict) -> str:
    """Retourne un libellé de compte si l'accès fonctionne, sinon lève PublishError."""
    async with httpx.AsyncClient(timeout=30) as http:
        if platform == "facebook":
            d = await _graph(http, "GET", creds["page_id"], creds["page_access_token"], fields="name")
            return d.get("name", "")
        if platform == "instagram":
            d = await _graph(http, "GET", creds["ig_user_id"], creds["access_token"], fields="username")
            return d.get("username", "")
        if platform == "linkedin":
            r = await http.get(f"{LI}/v2/userinfo", headers={"Authorization": f"Bearer {creds['access_token']}"})
            if r.status_code != 200:
                raise PublishError(f"LinkedIn : {r.text[:200]}")
            return r.json().get("name", "")
        if platform == "tiktok":
            r = await http.get(f"{TT}/v2/user/info/?fields=display_name", headers=_tt_headers(creds["access_token"]))
            u = r.json().get("data", {}).get("user")
            if not u:
                raise PublishError(f"TikTok : {r.text[:200]}")
            return u.get("display_name", "")
    raise PublishError("Plateforme inconnue")


# ═════════════════════════ REFRESH TOKENS ═════════════════════════
async def refresh_credentials(platform: str, creds: dict) -> tuple[dict, datetime | None] | None:
    async with httpx.AsyncClient(timeout=30) as http:
        if platform == "tiktok" and creds.get("refresh_token"):
            r = await http.post(f"{TT}/v2/oauth/token/", data={
                "client_key": os.getenv("TIKTOK_CLIENT_KEY"), "client_secret": os.getenv("TIKTOK_CLIENT_SECRET"),
                "grant_type": "refresh_token", "refresh_token": creds["refresh_token"]})
            d = r.json()
            if "access_token" not in d:
                return None
            creds = {**creds, "access_token": d["access_token"], "refresh_token": d.get("refresh_token", creds["refresh_token"])}
            return creds, datetime.utcnow() + timedelta(seconds=int(d.get("expires_in", 86400)))
        if platform == "linkedin" and creds.get("refresh_token"):
            r = await http.post("https://www.linkedin.com/oauth/v2/accessToken", data={
                "grant_type": "refresh_token", "refresh_token": creds["refresh_token"],
                "client_id": os.getenv("LINKEDIN_CLIENT_ID"), "client_secret": os.getenv("LINKEDIN_CLIENT_SECRET")})
            d = r.json()
            if "access_token" not in d:
                return None
            creds = {**creds, "access_token": d["access_token"], "refresh_token": d.get("refresh_token", creds["refresh_token"])}
            return creds, datetime.utcnow() + timedelta(seconds=int(d.get("expires_in", 5184000)))
    return None


# ═════════════════════════ OAUTH ═════════════════════════
def _redirect(platform):
    return f"{OAUTH_BASE}/admin/social/oauth/{platform}/callback"


def oauth_url(platform: str, state: str) -> str:
    if platform in ("facebook", "instagram"):
        q = {"client_id": os.getenv("META_APP_ID"), "redirect_uri": _redirect("facebook"), "state": state,
             "scope": os.getenv("META_SCOPES", ""), "response_type": "code"}
        return f"https://www.facebook.com/{GRAPH_V}/dialog/oauth?{urllib.parse.urlencode(q)}"
    if platform == "linkedin":
        q = {"response_type": "code", "client_id": os.getenv("LINKEDIN_CLIENT_ID"), "redirect_uri": _redirect("linkedin"),
             "state": state, "scope": os.getenv("LINKEDIN_SCOPES", "openid profile w_member_social")}
        return f"https://www.linkedin.com/oauth/v2/authorization?{urllib.parse.urlencode(q)}"
    if platform == "tiktok":
        q = {"client_key": os.getenv("TIKTOK_CLIENT_KEY"), "response_type": "code", "redirect_uri": _redirect("tiktok"),
             "state": state, "scope": os.getenv("TIKTOK_SCOPES", "user.info.basic,video.publish,video.upload")}
        return f"https://www.tiktok.com/v2/auth/authorize/?{urllib.parse.urlencode(q)}"
    raise PublishError("Plateforme inconnue")


async def oauth_exchange(platform: str, code: str) -> list[dict]:
    """Retourne une liste de comptes : {plateforme, nom, identifiant, creds, expire_le}."""
    async with httpx.AsyncClient(timeout=40) as http:
        if platform in ("facebook", "instagram"):
            base = {"client_id": os.getenv("META_APP_ID"), "client_secret": os.getenv("META_APP_SECRET")}
            r = await http.get(f"{GRAPH}/oauth/access_token", params={**base, "redirect_uri": _redirect("facebook"), "code": code})
            short = r.json()
            if "access_token" not in short:
                raise PublishError(f"Meta OAuth : {short}")
            r = await http.get(f"{GRAPH}/oauth/access_token", params={**base, "grant_type": "fb_exchange_token",
                                                                      "fb_exchange_token": short["access_token"]})
            long_tok = r.json().get("access_token", short["access_token"])
            pages = await _graph(http, "GET", "me/accounts", long_tok,
                                 fields="id,name,access_token,instagram_business_account{id,username}")
            lst = pages.get("data", [])
            wanted = os.getenv("META_PAGE_ID")
            page = next((p for p in lst if p["id"] == wanted), None) if wanted else (lst[0] if lst else None)
            if not page:
                raise PublishError("Aucune Page Facebook accessible avec ce compte")
            out = [{"plateforme": "facebook", "nom": page["name"], "identifiant": page["id"], "expire_le": None,
                    "creds": {"page_id": page["id"], "page_access_token": page["access_token"]}}]
            ig = page.get("instagram_business_account")
            if ig:
                out.append({"plateforme": "instagram", "nom": ig.get("username", ""), "identifiant": ig["id"], "expire_le": None,
                            "creds": {"ig_user_id": ig["id"], "access_token": page["access_token"]}})
            return out
        if platform == "linkedin":
            r = await http.post("https://www.linkedin.com/oauth/v2/accessToken", data={
                "grant_type": "authorization_code", "code": code, "redirect_uri": _redirect("linkedin"),
                "client_id": os.getenv("LINKEDIN_CLIENT_ID"), "client_secret": os.getenv("LINKEDIN_CLIENT_SECRET")})
            d = r.json()
            if "access_token" not in d:
                raise PublishError(f"LinkedIn OAuth : {d}")
            u = await http.get(f"{LI}/v2/userinfo", headers={"Authorization": f"Bearer {d['access_token']}"})
            ui = u.json()
            org = re.sub(r"\D", "", (os.getenv("LINKEDIN_ORG_ID") or "").split("#")[0])
            urn = f"urn:li:organization:{org}" if org else f"urn:li:person:{ui.get('sub')}"
            return [{"plateforme": "linkedin", "nom": ui.get("name", ""), "identifiant": urn,
                     "expire_le": datetime.utcnow() + timedelta(seconds=int(d.get("expires_in", 5184000))),
                     "creds": {"access_token": d["access_token"], "refresh_token": d.get("refresh_token"), "author_urn": urn}}]
        if platform == "tiktok":
            r = await http.post(f"{TT}/v2/oauth/token/", data={
                "client_key": os.getenv("TIKTOK_CLIENT_KEY"), "client_secret": os.getenv("TIKTOK_CLIENT_SECRET"),
                "code": code, "grant_type": "authorization_code", "redirect_uri": _redirect("tiktok")})
            d = r.json()
            if "access_token" not in d:
                raise PublishError(f"TikTok OAuth : {d}")
            return [{"plateforme": "tiktok", "nom": "TikTok", "identifiant": d.get("open_id"),
                     "expire_le": datetime.utcnow() + timedelta(seconds=int(d.get("expires_in", 86400))),
                     "creds": {"access_token": d["access_token"], "refresh_token": d.get("refresh_token"),
                               "open_id": d.get("open_id"), "privacy_level": "SELF_ONLY", "post_mode": "DIRECT_POST"}}]
    raise PublishError("Plateforme inconnue")