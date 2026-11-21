# services/social/social_analytics.py
import random
import statistics as st
from datetime import datetime, timedelta, timezone

from sqlmodel import select

from agent.db import (
    SocialAccountSnapshot, SocialMetric, SocialPost, get_celery_session,
)
from agent.services.social.social_config import (
    DEFAULT_ER, TZ, local_to_utc, prior_score, to_local, utcnow,
)


# ── Features d'un post ────────────────────────────────────────────────────────
def _hour_bucket(h: int) -> str:
    return "matin" if 5 <= h < 11 else "midi" if h < 14 else "apres_midi" if h < 18 else "soir" if h < 23 else "nuit"


def post_features(p: dict) -> dict:
    n = len(p.get("contenu") or "")
    nh = len(p.get("hashtags") or [])
    when = p.get("published_at") or p.get("scheduled_at")
    loc = to_local(when) if when else None
    return {
        "pilier": p.get("pilier") or "?",
        "format": p.get("format") or "texte",
        "longueur": "court" if n < 200 else "moyen" if n < 700 else "long",
        "hashtags": "0" if nh == 0 else "1-3" if nh <= 3 else "4-8" if nh <= 8 else "9+",
        "media": "oui" if p.get("media_urls") else "non",
        "heure": _hour_bucket(loc.hour) if loc else "?",
        "jour": ("semaine" if loc.weekday() < 5 else "weekend") if loc else "?",
        "visuel": ((p.get("visuel_spec") or {}).get("template") or "aucun"),
    }


# ── Historique (posts publiés + dernière métrique) ────────────────────────────
async def load_history(brand_id: str, platform: str | None = None, days: int = 365) -> list[dict]:
    since = utcnow() - timedelta(days=days)
    async with get_celery_session() as s:
        q = select(SocialPost).where(SocialPost.brand_id == brand_id, SocialPost.statut == "publie",
                                     SocialPost.published_at >= since)
        if platform:
            q = q.where(SocialPost.plateforme == platform)
        posts = (await s.execute(q)).scalars().all()
        if not posts:
            return []
        ms = (await s.execute(select(SocialMetric).where(SocialMetric.post_id.in_([p.id for p in posts]))
                              .order_by(SocialMetric.collecte_le.desc()))).scalars().all()
    latest = {}
    for m in ms:
        latest.setdefault(m.post_id, m)
    out = []
    for p in posts:
        m = latest.get(p.id)
        out.append({
            "id": p.id, "plateforme": p.plateforme, "pilier": p.pilier, "format": p.format, "contenu": p.contenu,
            "hashtags": p.hashtags, "media_urls": p.media_urls, "published_at": p.published_at,
            "external_url": p.external_url,
            "er": m.engagement_rate if m else None, "score": m.engagement_score if m else None,
            "impressions": m.impressions if m else 0, "reach": m.reach if m else 0,
            "likes": m.likes if m else 0, "comments": m.comments if m else 0,
            "shares": m.shares if m else 0, "saves": m.saves if m else 0, "clicks": m.clicks if m else 0,
            "visuel_spec": p.visuel_spec,
        })
    return out


def _mean(xs):
    return st.mean(xs) if xs else None


# ── Grille de créneaux (prior bayésien + données propres) ─────────────────────
async def _grid(brand_id: str, platform: str) -> dict:
    hist = [h for h in await load_history(brand_id, platform) if h["er"] is not None]
    gm = _mean([h["er"] for h in hist])
    by_h, by_d = {}, {}
    for h in hist:
        loc = to_local(h["published_at"])
        by_h.setdefault(loc.hour, []).append(h["er"])
        by_d.setdefault(loc.weekday(), []).append(h["er"])
    grid = {}
    for wd in range(7):
        for hr in range(6, 23):
            prior = prior_score(platform, wd, hr)
            emps, n = [], 0
            if gm:
                for grp in (by_h.get(hr), by_d.get(wd)):
                    if grp:
                        emps.append(min(1.0, (_mean(grp) / gm) / 2))
                n = min(len(by_h.get(hr, [])), len(by_d.get(wd, []))) if len(emps) == 2 else 0
            if emps and n:
                emp = (emps[0] * emps[1]) ** 0.5
                score = (n * emp + 3 * prior) / (n + 3)
            else:
                score = prior
            grid[(wd, hr)] = (round(score, 3), n)
    return grid


async def best_times(brand_id: str, platform: str, top: int = 6) -> list[dict]:
    grid = await _grid(brand_id, platform)
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    items = sorted(grid.items(), key=lambda kv: kv[1][0], reverse=True)[:top]
    return [{"jour": jours[wd], "weekday": wd, "heure": hr, "score": sc, "observations": n,
             "source": "données propres + prior" if n else "prior sectoriel"} for (wd, hr), (sc, n) in items]


async def suggest_slots(brand_id: str, platform: str, n: int = 1, max_per_day: int = 1,
                        horizon: int = 21, after: datetime | None = None) -> list[dict]:
    now = max(after or utcnow(), utcnow()) + timedelta(minutes=45)
    grid = await _grid(brand_id, platform)
    async with get_celery_session() as s:
        rows = (await s.execute(select(SocialPost.scheduled_at).where(
            SocialPost.brand_id == brand_id, SocialPost.plateforme == platform,
            SocialPost.statut.in_(("a_valider", "programme", "publication")),
            SocialPost.scheduled_at >= now - timedelta(days=1)))).scalars().all()
    per_day = {}
    for r in rows:
        d = to_local(r).date()
        per_day[d] = per_day.get(d, 0) + 1
    base = to_local(now)
    cands = []
    for off in range(horizon):
        day = (base + timedelta(days=off)).date()
        if per_day.get(day, 0) >= max_per_day:
            continue
        best = None
        for h in range(6, 23):
            dt_local = datetime(day.year, day.month, day.day, h, random.randint(0, 20), tzinfo=TZ)
            if local_to_utc(dt_local) < now:
                continue
            sc, nobs = grid[(day.weekday(), h)]
            if best is None or sc > best[0]:
                best = (sc, nobs, dt_local)
        if best:
            cands.append((best[0] - 0.01 * off, best))
    cands.sort(key=lambda c: c[0], reverse=True)
    chosen = sorted([c[1] for c in cands[:n]], key=lambda b: b[2])
    jours = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    out = []
    for sc, nobs, dtl in chosen:
        src = f"{nobs} observations propres" if nobs else "prior sectoriel (pas encore assez de données)"
        out.append({"scheduled_at": local_to_utc(dtl), "score": sc,
                    "justification": f"{jours[dtl.weekday()].capitalize()} {dtl.hour}h{dtl.minute:02d} : "
                                     f"créneau {'fort' if sc >= .7 else 'correct'} sur {platform} "
                                     f"(score {sc:.2f}, {src})."})
    return out


# ── Prédiction de performance ────────────────────────────────────────────────
def _multiplier(hist, feat_name, value, gm):
    grp = [h["er"] for h in hist if post_features(h).get(feat_name) == value]
    if not grp or not gm:
        return 1.0
    ratio = _mean(grp) / gm
    w = len(grp) / (len(grp) + 5)
    return max(0.5, min(2.0, 1 + w * (ratio - 1)))


async def predict(brand_id: str, post: dict, llm_quality: float | None = None) -> dict:
    plat = post["plateforme"]
    hist = [h for h in await load_history(brand_id, plat) if h["er"] is not None]
    gm = _mean([h["er"] for h in hist])
    base = st.median([h["er"] for h in hist]) if len(hist) >= 3 else DEFAULT_ER.get(plat, 0.02)
    feat = post_features(post)
    facteurs, mult = [], 1.0
    if len(hist) >= 5:
        for name, val in feat.items():
            if val == "?":
                continue
            m = _multiplier(hist, name, val, gm)
            if abs(m - 1) > 0.05:
                facteurs.append({"critere": name, "valeur": val, "multiplicateur": round(m, 2)})
            mult *= m
    er = base * max(0.3, min(3.0, mult))
    conf = min(1.0, len(hist) / 30)
    pct = (sum(1 for h in hist if h["er"] <= er) / len(hist) * 100) if len(hist) >= 5 else 50.0
    w_hist = conf * 0.5
    score = (1 - w_hist) * (llm_quality if llm_quality is not None else 55.0) + w_hist * pct
    return {"er_predit": round(er, 4), "er_bas": round(er * .6, 4), "er_haut": round(er * 1.6, 4),
            "confiance": round(conf, 2), "percentile_historique": round(pct, 1),
            "qualite_llm": llm_quality, "score_global": round(score, 1),
            "nb_posts_reference": len(hist), "facteurs": facteurs}


# ── Synthèse de performance ──────────────────────────────────────────────────
def _slope(xs):
    n = len(xs)
    if n < 4:
        return 0.0
    mx, my = (n - 1) / 2, st.mean(xs)
    den = sum((i - mx) ** 2 for i in range(n))
    return sum((i - mx) * (x - my) for i, x in enumerate(xs)) / den if den else 0.0


def _group(hist, keyfn):
    g = {}
    for h in hist:
        if h["er"] is not None:
            g.setdefault(keyfn(h), []).append(h["er"])
    return {k: {"n": len(v), "er_moyen": round(st.mean(v), 4)} for k, v in g.items()}


async def performance_summary(brand_id: str, days: int = 30) -> dict:
    hist_all = await load_history(brand_id, None, days * 2)
    cutoff = utcnow() - timedelta(days=days)
    cur = [h for h in hist_all if h["published_at"] >= cutoff]
    prev = [h for h in hist_all if h["published_at"] < cutoff]
    cur_er = [h["er"] for h in cur if h["er"] is not None]
    prev_er = [h["er"] for h in prev if h["er"] is not None]
    delta = None
    if cur_er and prev_er and st.mean(prev_er):
        delta = round((st.mean(cur_er) - st.mean(prev_er)) / st.mean(prev_er) * 100, 1)

    ranked = sorted([h for h in cur if h["score"] is not None], key=lambda h: h["score"], reverse=True)
    slim = lambda h: {"id": h["id"], "plateforme": h["plateforme"], "pilier": h["pilier"], "er": h["er"],
                      "score": h["score"], "extrait": (h["contenu"] or "")[:120], "url": h["external_url"]}

    trend, anomalies = {}, []
    for plat in {h["plateforme"] for h in cur}:
        series = [h["er"] for h in sorted(hist_all, key=lambda x: x["published_at"])
                  if h["plateforme"] == plat and h["er"] is not None][-20:]
        sl = _slope(series)
        trend[plat] = "hausse" if sl > 0.0005 else "baisse" if sl < -0.0005 else "stable"
        if len(series) >= 6:
            mu, sd = st.mean(series), st.pstdev(series) or 1e-9
            for h in cur:
                if h["plateforme"] == plat and h["er"] is not None:
                    z = (h["er"] - mu) / sd
                    if z > 2 or z < -1.5:
                        anomalies.append({"post_id": h["id"], "plateforme": plat, "z": round(z, 2),
                                          "type": "surperformance" if z > 0 else "sous-performance"})
    return {
        "periode_jours": days, "nb_posts": len(cur), "er_moyen": round(st.mean(cur_er), 4) if cur_er else None,
        "evolution_er_vs_periode_precedente_pct": delta,
        "totaux": {k: sum(h[k] for h in cur) for k in ("impressions", "reach", "likes", "comments", "shares", "saves", "clicks")},
        "par_plateforme": _group(cur, lambda h: h["plateforme"]),
        "par_pilier": _group(cur, lambda h: h["pilier"] or "?"),
        "par_format": _group(cur, lambda h: h["format"]),
        "par_visuel": _group(cur, lambda h: (h.get("visuel_spec") or {}).get("template") or "aucun"),
        "par_tranche_horaire": _group(cur, lambda h: post_features(h)["heure"]),
        "tendance": trend, "anomalies": anomalies,
        "top_posts": [slim(h) for h in ranked[:5]], "flop_posts": [slim(h) for h in ranked[-3:]] if len(ranked) > 5 else [],
        "croissance": await growth(brand_id, days),
    }


async def growth(brand_id: str, days: int = 30) -> dict:
    since = (utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    async with get_celery_session() as s:
        rows = (await s.execute(select(SocialAccountSnapshot).where(
            SocialAccountSnapshot.brand_id == brand_id, SocialAccountSnapshot.jour >= since)
            .order_by(SocialAccountSnapshot.jour))).scalars().all()
    by = {}
    for r in rows:
        by.setdefault(r.plateforme, []).append(r)
    out = {}
    for plat, lst in by.items():
        first, last = lst[0].followers, lst[-1].followers
        nd = max(1, (datetime.strptime(lst[-1].jour, "%Y-%m-%d") - datetime.strptime(lst[0].jour, "%Y-%m-%d")).days)
        per_day = (last - first) / nd
        out[plat] = {"followers": last, "delta": last - first,
                     "delta_pct": round((last - first) / first * 100, 2) if first else None,
                     "par_jour": round(per_day, 2), "projection_30j": round(last + per_day * 30),
                     "serie": [{"jour": r.jour, "followers": r.followers} for r in lst]}
    return out