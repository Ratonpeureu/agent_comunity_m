# services/social/social_agent_service.py
import asyncio
import difflib
import hashlib
import json
import logging
import math
import os
import re
import textwrap
import uuid
from datetime import datetime, timedelta
from urllib.parse import urljoin, urlparse
import random
from collections import Counter
import httpx
from bs4 import BeautifulSoup
from sqlalchemy import update as sa_update
from sqlmodel import select

from agent.db import (
    SocialAccount, SocialAccountSnapshot, SocialBrand, SocialIdea, SocialJob, SocialMetric,
    SocialPost, SocialReport, SocialStyleSample, get_celery_session,
)
from agent.services.llm_client.llm_client import LLMClient
from agent.services.llm_client import llm_usage

from agent.services.serper_client import serper_news
from agent.services.social import social_analytics as an
from agent.services.social import social_gateway as pub
from agent.services.social import social_video as video
from agent.services.social.social_config import (
    PLATFORMS, norm_format,PUBLIC_BASE_URL, SPECS, UPLOAD_DIR, dec, enc, to_local, utcnow,
)
from agent.services.social import social_assets as assets
from agent.services.social import social_montage as montage
from agent.services.social import social_unsplash as stock
logger = logging.getLogger("social_agent")

DEFAULT_CONFIG = {
    "validation_requise": True,
    "autopilot_actif": False,
    "autopilot_publication_directe": False,
    "plateformes_actives": list(PLATFORMS),
    "cadence_hebdo": {"linkedin": 3, "facebook": 3, "instagram": 3, "tiktok": 2},
    "max_par_jour_par_plateforme": 1,
    "visuel_defaut": "carte",            # carte | image_ia | aucun
    "couleurs": {"primaire": "#1B3A6B", "secondaire": "#2E5FA3", "texte": "#FFFFFF"},
    "langue": "fr",
    "utm": True,
    "brief_manuel": "",                  # à remplir si le site est un SPA peu lisible
    "mode_visuel": "auto",                # auto | aucun (aucun = pas de visuel hors Instagram/TikTok)
    "utiliser_captures": True,
    "autoriser_captures_sensibles": False,  # False = exclut les captures avec données perso non floutées
    "logo_asset_id": None,                # id du logo dans assets (sinon détecté automatiquement)
    "carrousel_max_slides": 5,
    "video_tiktok": True,          # TikTok = vidéo animée avec musique
    "video_voix_off": False,       # voix off gratuite (edge-tts)
    "video_duree_cible": 22,
    "varier_montages": True,
    "video_voix_off": True,
}


def cfg(brand: SocialBrand) -> dict:
    c = {**DEFAULT_CONFIG, **(brand.config or {})}
    c["couleurs"] = {**DEFAULT_CONFIG["couleurs"], **(c.get("couleurs") or {})}
    return c


# ═════════════════════════ LLM ═════════════════════════
_client = None


def _llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client


async def llm_json(user: str, system: str, temperature: float = 0.5, max_tokens: int = 4000) -> dict:
    last = None
    for wait in (0, 8, 25):
        if wait:
            await asyncio.sleep(wait)
        try:
            r = await asyncio.to_thread(_llm().chat_json, user_message=user, system_prompt=system,
                                        temperature=temperature, max_tokens=max_tokens, retries=2)
            if isinstance(r, dict) and "erreur" in r and "raw" in r:
                last = RuntimeError("Réponse LLM non parseable")
                continue
            return r
        except (llm_usage.BudgetExceeded, llm_usage.KeysUnavailable):
            raise
        except RuntimeError as e:  # 429, timeout...
            last = e
    raise last


# ═════════════════════════ MARQUE ═════════════════════════
async def get_or_create_brand(slug: str | None = None) -> SocialBrand:
    slug = slug or os.getenv("SOCIAL_BRAND_SLUG", "rhmanager")
    async with get_celery_session() as s:
        b = (await s.execute(select(SocialBrand).where(SocialBrand.slug == slug))).scalar_one_or_none()
        if not b:
            b = SocialBrand(slug=slug, nom=slug, site_url=os.getenv("SOCIAL_BRAND_SITE", PUBLIC_BASE_URL),
                            config=DEFAULT_CONFIG)
            s.add(b)
            await s.commit()
            await s.refresh(b)
        return b


async def get_brand(brand_id: str) -> SocialBrand:
    async with get_celery_session() as s:
        b = await s.get(SocialBrand, brand_id)
        if not b:
            raise ValueError("Marque introuvable")
        return b


_KW = ("a-propos", "about", "fonction", "feature", "tarif", "pricing", "solution", "service", "produit",
       "blog", "contact", "paie", "recrut", "ecole", "nagora")
_UA = {"User-Agent": "Mozilla/5.0 (compatible; RHManagerBrandBot/1.0; +https://localhost)"}


async def scrape_site(urls: list[str], max_pages: int = 8) -> list[dict]:
    pages, seen = [], set()
    domain = urlparse(urls[0]).netloc
    origin = f"{urlparse(urls[0]).scheme}://{domain}"
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=_UA) as http:
        queue = list(urls)
        try:
            sm = await http.get(f"{origin}/sitemap.xml")
            if sm.status_code == 200:
                locs = re.findall(r"<loc>(.*?)</loc>", sm.text)
                locs.sort(key=lambda l: 0 if any(k in l.lower() for k in _KW) else 1)
                queue += locs[:8]
        except Exception:
            pass
        while queue and len(pages) < max_pages:
            u = queue.pop(0)
            if u in seen:
                continue
            seen.add(u)
            try:
                r = await http.get(u)
            except Exception:
                continue
            if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
                continue
            soup = BeautifulSoup(r.text, "html.parser")

            def meta(**kw):
                t = soup.find("meta", attrs=kw)
                return (t.get("content") or "").strip() if t else ""

            info = {"url": str(r.url), "title": soup.title.get_text(strip=True) if soup.title else "",
                    "description": meta(name="description") or meta(property="og:description"),
                    "og_image": meta(property="og:image"), "theme_color": meta(name="theme-color")}
            links = [urljoin(str(r.url), a["href"]).split("#")[0] for a in soup.find_all("a", href=True)]
            links = [l for l in dict.fromkeys(links) if urlparse(l).netloc == domain and l not in seen]
            links.sort(key=lambda l: 0 if any(k in l.lower() for k in _KW) else 1)
            queue.extend(links[:10])
            info["titres"] = [h.get_text(strip=True) for h in soup.find_all(["h1", "h2", "h3"])][:15]
            for t in soup(["script", "style", "nav", "footer", "noscript", "svg"]):
                t.decompose()
            info["texte"] = " ".join(soup.get_text(" ", strip=True).split())[:2500]
            pages.append(info)
    return pages


SYSTEM_ANALYST = ("Tu es un directeur de marque et stratège social media senior. Tu analyses une marque à partir "
                  "de son site et d'exemples, et tu produis un profil exploitable. N'invente aucun fait absent des "
                  "sources. Réponds uniquement en JSON strict.")


async def analyze_brand(brand_id: str) -> dict:
    brand = await get_brand(brand_id)
    c = cfg(brand)
    async with get_celery_session() as s:
        await s.execute(sa_update(SocialBrand).where(SocialBrand.id == brand_id).values(statut_analyse="en_cours", erreur_analyse=None))
        await s.commit()
    try:
        pages = await scrape_site([brand.site_url] + list(brand.urls_supplementaires or []))
        corpus = "\n\n".join(f"[{p['url']}] {p['title']} | {p['description']}\nTitres: {' / '.join(p['titres'])}\n{p['texte']}"
                             for p in pages)[:14000]
        async with get_celery_session() as s:
            samples = (await s.execute(select(SocialStyleSample).where(SocialStyleSample.brand_id == brand_id)
                                       .order_by(SocialStyleSample.poids.desc()).limit(12))).scalars().all()
        ex = "\n---\n".join(x.texte[:600] for x in samples)
        user = f"""SITE ({brand.site_url}) — contenu collecté :
{corpus or "(site illisible — s'appuyer sur le brief)"}

BRIEF MANUEL DE L'ADMIN : {c.get('brief_manuel') or '(aucun)'}
EXEMPLES DE POSTS DE LA MARQUE :
{ex or '(aucun)'}

Produis ce JSON :
{{
 "nom": "nom de la marque",
 "identite": {{"mission": "", "proposition_valeur": "", "produits_services": [""], "public_cible": [""],
   "personas": [{{"nom": "", "besoins": "", "douleurs": ""}}], "differenciateurs": [""], "valeurs": [""],
   "secteurs": ["3 requêtes d'actualité pertinentes pour surveiller le secteur, en français"],
   "marche": "zone géographique", "concurrents_probables": [""], "langues": ["fr"]}},
 "ton": {{"persona": "qui parle", "adjectifs": ["4-6"], "formalite": "tutoiement|vouvoiement + niveau",
   "emojis": "usage et exemples", "longueur_phrases": "", "vocabulaire_favori": [""], "mots_a_eviter": [""],
   "structures_accroche": ["modèles d'accroches typiques"], "types_cta": [""], "humour": "oui/non/dosage"}},
 "piliers": [{{"code": "slug", "titre": "", "description": "", "poids": 0-100}}],
 "hashtags_marque": ["#..."],
 "sujets_interdits": [""],
 "couleurs": {{"primaire": "#hex", "secondaire": "#hex"}},
 "style_guide": "guide éditorial de 250-400 mots, impératif, que n'importe quel rédacteur peut appliquer pour écrire comme la marque"
}}
Les 4-6 piliers doivent totaliser un poids de 100."""
        r = await llm_json(user, SYSTEM_ANALYST, temperature=0.3, max_tokens=5000)
        theme = next((p["theme_color"] for p in pages if p.get("theme_color")), None)
        newcfg = dict(brand.config or {})
        colors = {**cfg(brand)["couleurs"], **{k: v for k, v in (r.get("couleurs") or {}).items() if re.match(r"^#[0-9a-fA-F]{6}$", str(v))}}
        if theme and re.match(r"^#[0-9a-fA-F]{6}$", theme) and "couleurs" not in (brand.config or {}):
            colors["primaire"] = theme
        newcfg["couleurs"] = colors
        identite = r.get("identite") or {}
        identite["hashtags_marque"] = r.get("hashtags_marque") or []
        identite["sujets_interdits"] = r.get("sujets_interdits") or []
        async with get_celery_session() as s:
            b = await s.get(SocialBrand, brand_id)
            b.nom = r.get("nom") or b.nom
            b.identite, b.ton, b.piliers = identite, r.get("ton") or {}, r.get("piliers") or []
            b.style_guide = r.get("style_guide") or ""
            b.config = newcfg
            b.statut_analyse, b.derniere_analyse, b.updated_at = "pret", utcnow(), utcnow()
            await s.commit()
        warn = "Site peu lisible : complète le brief manuel." if len(corpus) < 800 else None
        return {"pages_lues": len(pages), "piliers": len(r.get("piliers") or []), "avertissement": warn}
    except Exception as e:
        async with get_celery_session() as s:
            await s.execute(sa_update(SocialBrand).where(SocialBrand.id == brand_id).values(statut_analyse="erreur", erreur_analyse=str(e)[:1000]))
            await s.commit()
        raise


async def refresh_tone(brand_id: str) -> dict:
    """Réapprend le ton à partir des échantillons (manuels, éditions admin, posts performants)."""
    brand = await get_brand(brand_id)
    async with get_celery_session() as s:
        samples = (await s.execute(select(SocialStyleSample).where(SocialStyleSample.brand_id == brand_id)
                                   .order_by(SocialStyleSample.poids.desc(), SocialStyleSample.created_at.desc()).limit(25))).scalars().all()
    if len(samples) < 3:
        raise ValueError("Ajoute au moins 3 exemples de posts pour affiner le ton")
    ex = "\n---\n".join(f"[{x.plateforme or 'général'} | {x.source}] {x.texte[:700]}" for x in samples)
    user = f"""Ton actuel : {json.dumps(brand.ton, ensure_ascii=False)}
Guide actuel : {brand.style_guide}

Voici de VRAIS posts de la marque (les 'edit_admin' sont des corrections de l'admin = signal le plus fiable,
les 'post_performant' ont bien marché) :
{ex}

Mets à jour le profil de ton pour coller exactement à cette voix. JSON :
{{"ton": {{"persona":"","adjectifs":[],"formalite":"","emojis":"","longueur_phrases":"","vocabulaire_favori":[],
"mots_a_eviter":[],"structures_accroche":[],"types_cta":[],"humour":""}}, "style_guide": "250-400 mots", "changements": ["ce qui a évolué"]}}"""
    r = await llm_json(user, SYSTEM_ANALYST, temperature=0.3)
    async with get_celery_session() as s:
        b = await s.get(SocialBrand, brand_id)
        b.ton, b.style_guide, b.updated_at = r.get("ton") or b.ton, r.get("style_guide") or b.style_guide, utcnow()
        await s.commit()
    return {"changements": r.get("changements", []), "echantillons": len(samples)}


async def add_style_sample(brand_id, texte, plateforme=None, source="manuel", poids=1.0) -> bool:
    h = hashlib.sha1(texte.strip().encode()).hexdigest()
    async with get_celery_session() as s:
        if (await s.execute(select(SocialStyleSample.id).where(SocialStyleSample.brand_id == brand_id,
                                                               SocialStyleSample.texte_hash == h))).first():
            return False
        s.add(SocialStyleSample(brand_id=brand_id, texte=texte.strip(), plateforme=plateforme,
                                source=source, poids=poids, texte_hash=h))
        await s.commit()
    return True


async def brand_context(brand: SocialBrand, platform: str | None = None, n_samples: int = 5) -> str:
    async with get_celery_session() as s:
        samples = (await s.execute(select(SocialStyleSample).where(SocialStyleSample.brand_id == brand.id)
                                   .order_by(SocialStyleSample.poids.desc(), SocialStyleSample.created_at.desc()).limit(40))).scalars().all()
    samples.sort(key=lambda x: (x.plateforme != platform, -x.poids))
    ex = "\n---\n".join(x.texte[:600] for x in samples[:n_samples])
    learn = "\n".join(f"- {a.get('texte')}" for a in (brand.apprentissages or [])[-10:])
    return f"""MARQUE : {brand.nom} ({brand.site_url})
IDENTITÉ : {json.dumps(brand.identite, ensure_ascii=False)[:2500]}
TON : {json.dumps(brand.ton, ensure_ascii=False)[:1200]}
GUIDE ÉDITORIAL : {brand.style_guide[:2200]}
PILIERS : {json.dumps(brand.piliers, ensure_ascii=False)[:800]}
APPRENTISSAGES (ce qui marche / ne marche pas pour cette audience) :
{learn or '(pas encore)'}
EXEMPLES DE LA VOIX DE LA MARQUE :
{ex or '(aucun exemple)'}"""


# ═════════════════════════ IDÉES ═════════════════════════
SYSTEM_STRATEGE = ("Tu proposes des idées de publications STRICTEMENT fondées sur les captures réelles et les actualités fournies. "
                   "Interdit d'inventer : chiffres, clients, témoignages, fonctionnalités, événements, dates, offres. "
                   "Ce qui n'est pas dans les données fournies n'existe pas. JSON strict uniquement.")


def _tpl(s: str, **kw) -> str:
    for k, v in kw.items():
        s = s.replace(f"<<{k}>>", str(v))
    return s


def _asset_facts(a: dict) -> list[str]:
    out = []
    for k in ("fonctionnalites_visibles", "benefices", "problemes_resolus", "elements_ui"):
        out += [str(x) for x in (a.get(k) or [])]
    out += [a.get("titre_court") or "", a.get("ecran") or ""]
    return [x.strip() for x in out if x and x.strip()]


def _fact_supported(fact: str, pool: set) -> bool:
    t = assets.tokens(fact)
    return bool(t) and len(t & pool) / len(t) >= 0.7


def _idea_assets(just: str) -> list[str]:
    m = re.search(r"Captures utilisées\s*:\s*(.+)", just or "")
    return [x.strip() for x in m.group(1).split(",") if x.strip()] if m else []


_IDEAS_PROMPT = """<<CTX>>

THÉMATIQUE IMPOSÉE : <<THEME>>
PLATEFORMES ACTIVES : <<PLATS>>
CODES DE PILIERS AUTORISÉS : <<PILIERS>>

CAPTURES RÉELLES (seule matière autorisée pour parler du produit) :
<<CATALOG>>

ACTUALITÉS RÉELLES DU SECTEUR (optionnel, n'utilise une actualité que si elle sert directement l'idée ; sinon ignore-les) :
<<TRENDS>>

IDÉES DÉJÀ UTILISÉES (ne pas répéter) : <<PAST>>

Propose <<NB>> idées. Pour CHAQUE idée :
- "asset_ids" : 1 à 3 identifiants pris UNIQUEMENT dans la liste de captures ci-dessus ;
- "faits_utilises" : 2 à 4 éléments COPIÉS TEXTUELLEMENT des « fonctions » ou « bénéfices » des captures choisies ;
- aucune date, aucun événement, aucun chiffre, aucun nom de client qui ne figure pas dans les données ;
- "source_tendance_url" : une URL de la liste des actualités, sinon null.
Varie modules, objectifs et formats. Privilégie les captures les moins utilisées.
JSON : {"idees":[{"titre":"","angle":"","accroche":"","pilier":"code","objectif":"notoriete|engagement|conversion|autorite",
"format_conseille":"texte|image|carrousel|video","plateformes_conseillees":["linkedin"],"asset_ids":[""],
"faits_utilises":[""],"source_tendance_url":null}]}"""


async def generate_ideas(brand_id: str, nb: int = 8, thematique: str | None = None, avec_tendances: bool = True) -> dict:
    brand = await get_brand(brand_id)
    c = cfg(brand)
    stats = await assets.asset_report(brand_id)
    usage = stats.get("usage_30j") or {}
    allow = bool(c.get("autoriser_captures_sensibles"))
    catalog = {a["id"]: a for a in assets.list_assets() if assets.eligible(a, allow)}
    if not catalog:
        raise ValueError("Aucune capture exploitable : analyse tes captures et vérifie les zones floutées (onglet Médiathèque).")
    per_mod, pool = Counter(), []
    for a in sorted(catalog.values(), key=lambda a: (usage.get(a["id"], 0), random.random())):
        mod = a.get("module") or "autre"
        if per_mod[mod] >= 3:
            continue
        per_mod[mod] += 1
        pool.append(a)
        if len(pool) >= 30:
            break
    cat_txt = "\n".join(
        f"[{a['id']}] module={a.get('module')} | écran={a.get('ecran') or a.get('titre_court')} | "
        f"fonctions: {'; '.join((a.get('fonctionnalites_visibles') or [])[:6])} | "
        f"bénéfices: {'; '.join((a.get('benefices') or [])[:4])} | utilisée {usage.get(a['id'], 0)}× en 30 j" for a in pool)
    trends = [t for t in (await _trends(brand) if avec_tendances else []) if t.get("lien")]
    links = {t["lien"] for t in trends}
    since = utcnow() - timedelta(days=90)
    async with get_celery_session() as s:
        past = (await s.execute(select(SocialIdea.titre).where(SocialIdea.brand_id == brand_id,
                                                               SocialIdea.created_at >= since))).scalars().all()
    codes = [p.get("code") for p in (brand.piliers or []) if p.get("code")]
    user = _tpl(_IDEAS_PROMPT, CTX=await brand_context(brand), THEME=thematique or "libre",
                PLATS=c["plateformes_actives"], PILIERS=codes or "(libre)", CATALOG=cat_txt,
                TRENDS=json.dumps(trends[:10], ensure_ascii=False)[:2500] if trends else "(aucune)",
                PAST=json.dumps(past[-40:], ensure_ascii=False), NB=nb)
    r = await llm_json(user, SYSTEM_STRATEGE, temperature=0.3, max_tokens=4500)
    mod_er, mean = stats.get("par_module") or {}, stats.get("er_moyen")
    created, rejected = [], 0
    async with get_celery_session() as s:
        known = list(past)
        for i in r.get("idees", []):
            t = (i.get("titre") or "").strip()
            ids = [x for x in (i.get("asset_ids") or []) if x in catalog][:3]
            faits = [f for f in (i.get("faits_utilises") or []) if isinstance(f, str) and f.strip()]
            if not t or not ids or not faits:
                rejected += 1
                continue
            pool_t = set().union(*[assets.tokens(" ".join(_asset_facts(catalog[x]))) for x in ids])
            if not all(_fact_supported(f, pool_t) for f in faits):
                rejected += 1                       # un « fait » absent des captures = idée rejetée
                continue
            if any(difflib.SequenceMatcher(None, t.lower(), k.lower()).ratio() > 0.75 for k in known):
                continue
            known.append(t)
            url = i.get("source_tendance_url")
            url = url if url in links else None
            plats = [p for p in (i.get("plateformes_conseillees") or []) if p in c["plateformes_actives"]] or c["plateformes_actives"][:2]
            mod = catalog[ids[0]].get("module")
            sc = 50.0
            if mod_er.get(mod) and mean:
                sc += 30 * max(-1.0, min(1.0, mod_er[mod]["er_moyen"] / mean - 1))
            sc -= 8 * sum(usage.get(x, 0) for x in ids) / len(ids)
            just = ("Fondée sur : " + "; ".join(catalog[x].get("titre_court") or x for x in ids)
                    + ". Faits utilisés : " + " ; ".join(faits) + "\n\nCaptures utilisées : " + ", ".join(ids))
            idea = SocialIdea(brand_id=brand_id, titre=t, angle=i.get("angle", ""), accroche=i.get("accroche", ""),
                              pilier=i.get("pilier") if i.get("pilier") in codes else "",
                              objectif=i.get("objectif", "engagement"), format_conseille=i.get("format_conseille", "texte"),
                              plateformes=plats, justification=just, source_tendance_url=url,
                              urgence="actualite" if url else "evergreen",
                              score_potentiel=float(max(5, min(95, sc))))
            s.add(idea)
            created.append(idea)
        await s.commit()
        ids_out = [x.id for x in created]
    return {"idees_creees": len(ids_out), "ids": ids_out, "idees_rejetees_non_sourcees": rejected}


async def _trends(brand: SocialBrand) -> list[dict]:
    queries = (brand.identite or {}).get("secteurs") or ["RH Sénégal", "paie Sénégal", "recrutement Dakar"]
    out = []
    for q in queries[:3]:
        try:
            for n in (await serper_news(q, num=5)) or []:
                out.append({"titre": n.get("title"), "source": n.get("source"), "date": n.get("date"),
                            "lien": n.get("link"), "extrait": (n.get("snippet") or "")[:160]})
        except Exception as e:
            logger.warning("serper_news a échoué : %s", e)
    return out[:12]




# ═════════════════════════ VISUELS ═════════════════════════
def _hex(c: str) -> tuple:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _render_card_sync(path, titre, sous_titre, marque, couleurs, size):
    from PIL import Image, ImageDraw, ImageFont
    W, H = size
    p, s2 = _hex(couleurs["primaire"]), _hex(couleurs["secondaire"])
    img = Image.new("RGB", size, p)
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(p[i] + (s2[i] - p[i]) * t) for i in range(3)))

    def font(sz):
        for f in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"):
            try:
                return ImageFont.truetype(f, sz)
            except Exception:
                pass
        return ImageFont.load_default(size=sz)

    txt = _hex(couleurs.get("texte", "#FFFFFF"))
    big, mid, small = font(int(W * .075)), font(int(W * .036)), font(int(W * .03))
    margin = int(W * .09)
    d.rectangle([margin, int(H * .2), margin + int(W * .12), int(H * .2) + 10], fill=txt)
    lines = textwrap.wrap(titre, width=max(10, int(W / (W * .075) * 1.75)))
    y = int(H * .28)
    for ln in lines[:6]:
        d.text((margin, y), ln, font=big, fill=txt)
        y += int(W * .095)
    if sous_titre:
        y += int(W * .03)
        for ln in textwrap.wrap(sous_titre, width=max(16, int(W / (W * .036) * 1.7)))[:4]:
            d.text((margin, y), ln, font=mid, fill=tuple(min(255, c + 0) for c in txt))
            y += int(W * .05)
    d.text((margin, H - int(H * .09)), marque, font=small, fill=txt)
    img.save(path, "PNG")



_SIZES = {"instagram": (1080, 1350), "tiktok": (1080, 1920), "linkedin": (1200, 627),
          "facebook": (1200, 630), "x": (1200, 675)}

async def build_visual(spec: dict | None, platform: str, brand: SocialBrand) -> str | None:
    c = cfg(brand)
    kind = (spec or {}).get("type") or c["visuel_defaut"]
    if kind == "aucun" and not SPECS[platform]["visuel_requis"]:
        return None
    if kind == "aucun":
        kind = "carte"
    name = f"{uuid.uuid4().hex}.png"
    path = os.path.join(UPLOAD_DIR, name)
    if kind == "image_ia" and (spec or {}).get("prompt_image"):
        w, h = _SIZES[platform]
        from urllib.parse import quote
        url = f"https://image.pollinations.ai/prompt/{quote(spec['prompt_image'][:400])}?width={w}&height={h}&nologo=true&model=flux"
        headers = {"Authorization": f"Bearer {os.getenv('POLLINATIONS_API_KEY')}"} if os.getenv("POLLINATIONS_API_KEY") else {}
        try:
            async with httpx.AsyncClient(timeout=90, follow_redirects=True) as http:
                r = await http.get(url, headers=headers)
            if r.status_code == 200 and r.headers.get("content-type", "").startswith("image"):
                with open(path, "wb") as f:
                    f.write(r.content)
                return f"{PUBLIC_BASE_URL}/uploads/social/{name}"
        except Exception as e:
            logger.warning("Pollinations KO, repli sur carte : %s", e)
    titre = (spec or {}).get("titre_carte") or brand.nom
    await asyncio.to_thread(_render_card_sync, path, titre, (spec or {}).get("sous_titre", ""),
                            brand.nom, c["couleurs"], _SIZES[platform])
    return f"{PUBLIC_BASE_URL}/uploads/social/{name}"


# ═════════════════════════ RÉDACTION ═════════════════════════
SYSTEM_WRITER = ("Tu es le community manager de la marque. Tu écris dans sa voix. "
                 "RÈGLE ABSOLUE : tu n'écris QUE des informations présentes dans « FAITS AUTORISÉS » ou dans l'identité fournie. "
                 "Interdit d'inventer : chiffres, pourcentages, durées, clients, témoignages, fonctionnalités, offres, événements, dates. "
                 "Si un fait manque, tu parles d'un autre aspect, tu n'improvises pas. "
                 "Interdits de style : « Dans un monde où », « À l'ère de », « Découvrez », exclamations en rafale. "
                 "Réponds uniquement en JSON strict.")
def _clean_tags(tags, max_n):
    out = []
    for t in tags or []:
        t = "#" + re.sub(r"[^\w]", "", str(t).lstrip("#"))
        if len(t) > 2 and t.lower() not in [x.lower() for x in out]:
            out.append(t)
    return out[:max_n]


def _truncate(text, mx):
    if len(text) <= mx:
        return text
    cut = text[:mx]
    m = max(cut.rfind(". "), cut.rfind("\n"))
    return (cut[:m + 1] if m > mx * .6 else cut).strip()


async def _fit_text(text: str, limit: int) -> str:
    """Réécrit plus court (sans rien ajouter) au lieu de couper en plein milieu."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    for _ in range(2):
        try:
            r = await llm_json(
                f"Raccourcis ce texte à {limit} caractères MAXIMUM (espaces inclus). Garde le sens, le ton et les phrases "
                f"complètes. N'ajoute aucune information. JSON : {{\"contenu\":\"\"}}\n\n{text}",
                "Tu raccourcis sans rien inventer ni ajouter. JSON strict.", temperature=0.2, max_tokens=1500)
            t = (r.get("contenu") or "").strip()
            if t:
                text = t
                if len(text) <= limit:
                    return text
        except Exception:
            break
    return _truncate(text, limit)


def post_dict(p: SocialPost) -> dict:
    iso = lambda d: d.isoformat() if d else None
    return {"id": p.id, "brand_id": p.brand_id, "idea_id": p.idea_id, "groupe_id": p.groupe_id, "variante": p.variante,
            "plateforme": p.plateforme, "format": p.format, "contenu": p.contenu, "hashtags": p.hashtags,
            "media_urls": p.media_urls, "lien": p.lien, "pilier": p.pilier, "visuel_spec": p.visuel_spec,
            "script_video": p.script_video, "statut": p.statut, "scheduled_at": iso(p.scheduled_at),
            "published_at": iso(p.published_at), "external_id": p.external_id, "external_url": p.external_url,
            "prediction": p.prediction, "horaire_justification": p.horaire_justification, "erreur": p.erreur,
            "nb_tentatives": p.nb_tentatives, "genere_par_ia": p.genere_par_ia, "rejet_motif": p.rejet_motif,
            "created_at": iso(p.created_at)}


def _lien_utm(brand: SocialBrand, platform: str, c: dict) -> str:
    if not c.get("utm"):
        return brand.site_url
    sep = "&" if "?" in brand.site_url else "?"
    return f"{brand.site_url}{sep}utm_source={platform}&utm_medium=social&utm_campaign={brand.slug}"

_BAN = ("dans un monde où", "à l'ère de", "à l’ère de", "découvrez")
_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_HOOKS = ["une question sur un irritant réel du métier", "un constat concret tiré de la capture",
          "un mini-scénario du quotidien, sans personnage ni chiffre inventé", "un avant/après purement qualitatif",
          "une erreur fréquente à éviter", "une fonctionnalité en une phrase puis son bénéfice"]

_WRITE_PROMPT = """<<CTX>>

IDÉE
Titre: <<TITRE>> | Angle: <<ANGLE>> | Pilier: <<PILIER>> | Objectif: <<OBJ>>
<<INSTR>>

FAITS AUTORISÉS (seule matière pour parler du produit ; aucun autre chiffre ni fonctionnalité) :
<<FAITS>>

CAPTURES UTILISABLES : <<CAT>>

NE PAS RESSEMBLER À CES POSTS RÉCENTS (autres accroches, autre structure) :
<<RECENT>>

PLATEFORMES : une version NATIVE et DIFFÉRENTE par plateforme (angle, accroche, structure), pas un copier-coller.
<<SPECS>>

Visuel : template parmi capture_cadree, tilt, glass, duo, checklist (points = fonctions visibles, copiées), bold, quote,
capture_zoom, carrousel, photo_overlay (unsplash_query en ANGLAIS 2-4 mots), carte, video (TikTok), aucun. Varie d'une plateforme à l'autre.
titre_carte ≤ 8 mots et différent de la 1ère ligne. X : aucun lien. Le champ "contenu" ne contient PAS les hashtags.
<<RETRY>>
JSON : {"posts":[{"plateforme":"","contenu":"","hashtags":[""],"format":"texte|image|carrousel|video","inclure_lien":true,
"visuel":{"template":"","asset_ids":[""],"titre_carte":"","sous_titre":"","badge":"","points":[""],"unsplash_query":"","slides":[]},
"script_video":null,"auto_evaluation":{"accroche":0,"clarte":0,"cta":0,"adequation_marque":0}}]}"""


def _nums(t: str) -> set:
    return {n.replace(",", ".") for n in _NUM.findall(t or "")}


def _problem(text: str, ok_nums: set, recent: list[str]) -> str | None:
    low = (text or "").lower()
    if len(low.strip()) < 40:
        return "trop court"
    if any(b in low for b in _BAN):
        return "formule interdite"
    bad = _nums(text) - ok_nums - {"2026"}
    if bad:
        return f"chiffres absents des sources : {sorted(bad)}"
    for r in recent:
        if difflib.SequenceMatcher(None, low[:300], r.lower()[:300]).ratio() > 0.55:
            return "trop proche d'un post existant"
    return None


async def _recent_posts(brand_id: str, plat: str, n: int = 25) -> list[str]:
    async with get_celery_session() as s:
        rows = (await s.execute(select(SocialPost.contenu).where(SocialPost.brand_id == brand_id, SocialPost.plateforme == plat)
                                .order_by(SocialPost.created_at.desc()).limit(n))).scalars().all()
    return [r for r in rows if r]


_FORMAT_RULES = {
    "video": "FORMAT IMPOSÉ : VIDÉO verticale animée → visuel.template=\"video\" ; remplis script_video (CHAÎNE de texte : "
             "accroche ≤7 mots, 3-4 scènes courtes, voix off ≤70 mots, CTA).",
    "carrousel": "FORMAT IMPOSÉ : CARROUSEL → visuel.template=\"carrousel\" avec 3 à 5 asset_ids utilisables ; script_video=null.",
    "image": "FORMAT IMPOSÉ : IMAGE UNIQUE → un template d'image unique (jamais video ni carrousel) ; script_video=null.",
    "texte": "FORMAT IMPOSÉ : TEXTE SEUL → visuel.template=\"aucun\" ; script_video=null.",
}


def _enforce_format(d: dict, fmt: str) -> dict:
    """Force le format choisi par l'admin, quoi que le LLM ait renvoyé."""
    vis = dict(d.get("visuel") or {})
    tpl = vis.get("template")
    if fmt == "video":
        vis["template"], vis["slides"] = "video", []
    elif fmt == "carrousel":
        vis["template"], vis["slides"] = "carrousel", []
    elif fmt == "texte":
        vis = {"template": "aucun", "asset_ids": []}
    elif tpl in (None, "", "video", "carrousel", "aucun"):
        vis["template"] = "capture_cadree"
    d["visuel"], d["format"] = vis, fmt
    if fmt != "video":
        d["script_video"] = None
    return d


async def _write_for_platforms(brand: SocialBrand, idea: dict, plats: list[str], instruction: str = "",
                               formats: dict | None = None) -> list[dict]:
    formats = formats or {}
    c = cfg(brand)
    allow = c.get("autoriser_captures_sensibles", False)
    catalog = {a["id"]: a for a in assets.list_assets()}
    allowed = [i for i in (idea.get("asset_ids") or []) if i in catalog and assets.eligible(catalog[i], allow)]
    stats = await assets.asset_report(brand.id) if c.get("utiliser_captures", True) else None
    qtxt = " ".join(str(idea.get(k) or "") for k in ("titre", "angle", "accroche")) + " " + instruction
    if not allowed and stats is not None:
        allowed = [a["id"] for a in assets.shortlist(qtxt, plats[0], 3, stats, allow)]
    items = [catalog[i] for i in allowed]
    facts = sorted({f for a in items for f in _asset_facts(a)})
    ctx = await brand_context(brand, plats[0])
    ground = " ".join(facts) + " " + assets._fiche_excerpt(2500) + " " + json.dumps(brand.identite or {}, ensure_ascii=False) \
        + " " + (idea.get("angle") or "") + " " + (idea.get("accroche") or "")
    ok_nums = _nums(ground)
    recents = {p: await _recent_posts(brand.id, p) for p in plats}
    hooks = random.sample(_HOOKS, k=len(_HOOKS))
    good: dict[str, dict] = {}
    why: dict[str, str] = {}
    todo = list(plats)
    for attempt in range(2):
        todo = [p for p in plats if p not in good]
        if not todo:
            break
        specs = "\n".join(f"- {p}: {SPECS[p]['brief']} Accroche imposée : {hooks[plats.index(p) % len(hooks)]}. "
                          f"{_FORMAT_RULES.get(formats.get(p), '')}" for p in todo)
        recent_txt = "\n".join(f"- {r[:110]}" for p in todo for r in recents[p][:6]) or "(aucun)"
        retry = ("CORRECTION : tes versions précédentes ont été refusées : " + json.dumps(why, ensure_ascii=False)) if why else ""
        user = _tpl(_WRITE_PROMPT, CTX=ctx, TITRE=idea.get("titre"), ANGLE=idea.get("angle"), PILIER=idea.get("pilier"),
                    OBJ=idea.get("objectif"), INSTR=(f"INSTRUCTION SPÉCIALE : {instruction}" if instruction else ""),
                    FAITS="\n".join(f"- {f}" for f in facts) or "(aucun fait : reste général, sans détail produit)",
                    CAT=", ".join(allowed) or "(aucune)", RECENT=recent_txt, SPECS=specs, RETRY=retry)
        r = await llm_json(user, SYSTEM_WRITER, temperature=0.6, max_tokens=5500)
        logger.warning("LLM: %s", str(r)[:800])
        for d in r.get("posts", []):
            p = (d.get("plateforme") or "").strip().lower()
            if p not in todo:
                why[p or "(vide)"] = f"plateforme invalide {d.get('plateforme')!r}; attendu: {todo}"
                continue
            if p in good:
                continue
            d["plateforme"] = p
            pb = _problem(d.get("contenu", ""), ok_nums, recents[p])
            if pb:
                why[p] = pb
            else:
                good[p] = d
                why.pop(p, None)

    if not good:
        raise ValueError(f"Aucun post valide : {why or f'le LLM n’a renvoyé aucun post pour {todo}'}")
    drafts = []
    for idx, p in enumerate(plats):
        d = good.get(p)
        if not d:
            logger.warning("Post %s écarté : %s", p, why.get(p))
            continue
        fmt = formats.get(p)
        vis = dict(d.get("visuel") or {})
        ids = [i for i in (vis.get("asset_ids") or []) if i in allowed]
        if not ids and allowed:
            ids = [allowed[idx % len(allowed)]]
        if fmt in ("carrousel", "video") and len(ids) < 3 and c.get("utiliser_captures", True):
            extra = [a["id"] for a in assets.shortlist(qtxt, p, 6, stats or {}, allow, set(ids))]
            ids = (ids + extra)[:5]
        vis["asset_ids"] = ids
        d["visuel"] = vis
        if fmt:
            _enforce_format(d, fmt)
        drafts.append(d)
    return drafts



def _script_text(v) -> str | None:
    """Le LLM renvoie parfois script_video en dict/liste : on le convertit en texte lisible."""
    if not v:
        return None
    if isinstance(v, str):
        return v.strip() or None

    def fmt(x):
        return x if isinstance(x, str) else json.dumps(x, ensure_ascii=False)

    if isinstance(v, dict):
        parts = []
        for k, val in v.items():
            label = str(k).replace("_", " ").capitalize()
            if isinstance(val, (list, tuple)):
                parts.append(f"{label} :\n" + "\n".join(f"- {fmt(x)}" for x in val))
            else:
                parts.append(f"{label} : {fmt(val)}")
        return "\n\n".join(parts)
    if isinstance(v, (list, tuple)):
        return "\n".join(f"- {fmt(x)}" for x in v)
    return str(v)


async def render_spec(spec, plat, brand, c, text="", script=""):
    if spec["template"] == "video":
        return await video.build_video(spec, plat, brand, c, text, llm_json, script)
    return await montage.render_visual(spec, plat, brand, c)

async def _persist_posts(brand, c, idea, drafts, groupe_id, variante=None, auto_publish=False) -> list[SocialPost]:
    created = []
    catalog = {a["id"]: a for a in assets.list_assets()}
    stats = await assets.asset_report(brand.id)
    stock_ok = stock.available()
    for _d in drafts:
        _d["script_video"] = _script_text(_d.get("script_video"))
    brand_tags = list((brand.identite or {}).get("hashtags_marque") or [])

    async def _vis(d):
        plat = d["plateforme"]
        spec = assets.finalize_spec(d.get("visuel"), plat, d.get("contenu", ""), catalog, c, stats,
                                    stock_ok=stock_ok, visuel_requis=SPECS[plat]["visuel_requis"])
        if spec["template"] == "aucun":
            return {"urls": [], "spec": spec}
        try:
            return await render_spec(spec, plat, brand, c, d.get("contenu", ""), d.get("script_video") or "")
        except Exception as e:
            logger.exception("Montage %s (%s) KO", plat, spec["template"])
            if spec["template"] == "video":           # pas de repli trompeur : l'erreur reste visible
                return {"urls": [], "spec": {**spec, "erreur_montage": str(e)[:300]}}
            fb = {**spec, "template": "capture_cadree" if spec.get("asset_ids") else "carte", "slides": [],
                  "erreur_montage": str(e)[:300]}
            try:
                return await montage.render_visual(fb, plat, brand, c)
            except Exception:
                return await montage.render_visual({**fb, "template": "carte", "asset_ids": []}, plat, brand, c)

    results = await asyncio.gather(*[_vis(d) for d in drafts], return_exceptions=True)
    for d, res in zip(drafts, results):
        plat = d["plateforme"]
        sp = SPECS[plat]
        if isinstance(res, Exception):
            logger.warning("Visuel %s abandonné : %s", plat, res)
            res = {"urls": [], "spec": d.get("visuel") or {}}
        spec_final = res["spec"]
        # hashtags : rédacteur (60 %) + 1 hashtag de marque + hashtags des captures + reste du rédacteur
        w = list(d.get("hashtags") or [])
        k = max(1, round(sp["hashtags"] * 0.6))
        a_tags = [t for i in (spec_final.get("asset_ids") or []) for t in (catalog.get(i, {}).get("hashtags") or [])]
        tags = _clean_tags(w[:k] + brand_tags[:1] + a_tags + w[k:], sp["hashtags"])
        tag_len = len(" ".join(tags)) + 2 if tags else 0
        limit = sp["max"] if plat == "tiktok" else max(60, sp["max"] - tag_len)
        text = await _fit_text((d.get("contenu") or "").strip(), limit)
        ev = d.get("auto_evaluation") or {}
        q = None
        if ev:
            vals = [float(v) for v in ev.values() if isinstance(v, (int, float))]
            q = max(0, min(100, sum(vals) / len(vals) - 10)) if vals else None
        post = SocialPost(brand_id=brand.id, idea_id=idea["id"] if idea.get("id") else None, groupe_id=groupe_id,
                          variante=variante, plateforme=plat, format=d.get("format", "texte"), contenu=text,
                          contenu_original_ia=text, hashtags=tags, media_urls=res["urls"],
                          lien=_lien_utm(brand, plat, c) if d.get("inclure_lien") and plat in ("facebook", "linkedin") else None,
                          pilier=idea.get("pilier", ""), visuel_spec=spec_final, script_video=d.get("script_video"),
                          statut="a_valider")
        pd = post_dict(post)
        pd["published_at"], pd["scheduled_at"] = None, utcnow() + timedelta(days=1)
        slot = await an.suggest_slots(brand.id, plat, 1, c["max_par_jour_par_plateforme"])
        if slot:
            post.scheduled_at, post.horaire_justification = slot[0]["scheduled_at"], slot[0]["justification"]
            pd["scheduled_at"] = post.scheduled_at
        post.prediction = await an.predict(brand.id, pd, q)
        if auto_publish and post.scheduled_at and (not sp["visuel_requis"] or post.media_urls):
            post.statut = "programme"
            post.validated_by, post.validated_at = "autopilot", utcnow()
        async with get_celery_session() as s:
            s.add(post)
            await s.commit()
            await s.refresh(post)
        created.append(post)
    return created



async def write_posts(idea_id: str, plateformes: list[str] | None = None, instruction: str = "",
                      auto_publish: bool = False, formats: dict | None = None) -> dict:
    async with get_celery_session() as s:
        idea = await s.get(SocialIdea, idea_id)
        if not idea:
            raise ValueError("Idée introuvable")
        brand = await s.get(SocialBrand, idea.brand_id)
        idea_d = {"id": idea.id, "titre": idea.titre, "angle": idea.angle, "accroche": idea.accroche,
                  "pilier": idea.pilier, "objectif": idea.objectif, "format_conseille": idea.format_conseille,
                  "asset_ids": _idea_assets(idea.justification)}
        plats = [p for p in (plateformes or idea.plateformes or []) if p in PLATFORMS]
    if not plats:
        raise ValueError("Aucune plateforme valide")
    

    c = cfg(brand)
    defaults = c.get("formats_defaut") or {}
    fm = {p: norm_format(p, (formats or {}).get(p) or defaults.get(p)) for p in plats}
    drafts = await _write_for_platforms(brand, idea_d, plats, instruction, fm)

    posts = await _persist_posts(brand, c, idea_d, drafts, uuid.uuid4().hex, auto_publish=auto_publish)
    async with get_celery_session() as s:
        await s.execute(sa_update(SocialIdea).where(SocialIdea.id == idea_id).values(statut="redige"))
        await s.commit()
    return {"posts_crees": len(posts), "ids": [p.id for p in posts]}


async def regenerate_post(post_id: str, instruction: str) -> dict:
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        if not p:
            raise ValueError("Post introuvable")
        brand = await s.get(SocialBrand, p.brand_id)
        idea = {"id": p.idea_id, "titre": (p.contenu or "")[:80], "angle": p.contenu, "pilier": p.pilier,
                "objectif": "engagement", "format_conseille": p.format,"asset_ids": (p.visuel_spec or {}).get("asset_ids")}
        plat = p.plateforme
    drafts = await _write_for_platforms(brand, idea, [plat], f"Réécris ce post : {instruction}\nVersion actuelle :\n{idea['angle']}")
    if not drafts:
        raise ValueError("Réécriture vide")
    d = drafts[0]
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        p.contenu = await _fit_text(d.get("contenu", p.contenu), SPECS[plat]["max"] - 40)
        p.hashtags = _clean_tags(d.get("hashtags"), SPECS[plat]["hashtags"])
        p.script_video = _script_text(d.get("script_video")) or p.script_video
        p.updated_at = utcnow()
        await s.commit()
        await s.refresh(p)
        return post_dict(p)


async def rebuild_visual(post_id: str, patch: dict | None = None) -> dict:
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        if not p:
            raise ValueError("Post introuvable")
        if p.statut in ("publie", "publication"):
            raise ValueError("Post déjà publié")
        brand = await s.get(SocialBrand, p.brand_id)
        plat, text, script, spec0 = p.plateforme, p.contenu or "", p.script_video or "", dict(p.visuel_spec or {})
    spec0.update({k: v for k, v in (patch or {}).items() if v not in (None, "")})
    c = cfg(brand)
    catalog = {a["id"]: a for a in assets.list_assets()}
    stats = await assets.asset_report(brand.id)
    spec = assets.finalize_spec(spec0, plat, text, catalog, c, stats, stock_ok=stock.available(),
                                visuel_requis=SPECS[plat]["visuel_requis"])
    media = []
    if spec["template"] != "aucun":
        res = await render_spec(spec, plat, brand, c, text, script)
        media, spec = res["urls"], res["spec"]
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        p.media_urls, p.visuel_spec, p.updated_at = media, spec, utcnow()
        await s.commit()
        await s.refresh(p)
        return post_dict(p)


async def preview_visual(spec: dict, plateforme: str) -> dict:
    brand = await get_or_create_brand()
    c = cfg(brand)
    catalog = {a["id"]: a for a in assets.list_assets()}
    stats = await assets.asset_report(brand.id)
    fs = assets.finalize_spec(spec, plateforme, spec.get("titre_carte", ""), catalog, c, stats,
                              stock_ok=stock.available(), visuel_requis=True)
    return await render_spec(fs, plateforme, brand, c, spec.get("titre_carte", ""))


async def make_variants(post_id: str, n: int = 2) -> dict:
    """Variantes A/B de l'accroche pour tester ce qui performe."""
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        brand = await s.get(SocialBrand, p.brand_id)
        base = post_dict(p)
    c = cfg(brand)
    user = f"""{await brand_context(brand, base['plateforme'])}
Post original ({base['plateforme']}) :
{base['contenu']}

Crée {n} variantes A/B qui testent des ACCROCHES différentes (question, chiffre sourcé du texte, histoire, contre-intuition)
avec le même fond et les mêmes faits. JSON : {{"variantes":[{{"label":"B","hypothese":"ce qu'on teste","contenu":""}}]}}"""
    r = await llm_json(user, SYSTEM_WRITER, temperature=0.5)
    ids = []
    gid = base["groupe_id"] or uuid.uuid4().hex
    for v in r.get("variantes", [])[:n]:
        pd = {**base, "contenu": _truncate(v["contenu"], SPECS[base["plateforme"]]["max"])}
        slot = await an.suggest_slots(brand.id, base["plateforme"], 1, c["max_par_jour_par_plateforme"], after=datetime.utcnow() + timedelta(days=2))
        async with get_celery_session() as s:
            np_ = SocialPost(brand_id=brand.id, idea_id=base["idea_id"], groupe_id=gid, variante=v.get("label", "B"),
                             plateforme=base["plateforme"], format=base["format"], contenu=pd["contenu"],
                             contenu_original_ia=pd["contenu"], hashtags=base["hashtags"], media_urls=base["media_urls"],
                             lien=base["lien"], pilier=base["pilier"], statut="a_valider",
                             scheduled_at=slot[0]["scheduled_at"] if slot else None,
                             horaire_justification=f"Variante A/B — {v.get('hypothese', '')}")
            s.add(np_)
            await s.commit()
            ids.append(np_.id)
    return {"variantes": ids}


async def score_post(post_id: str) -> dict:
    """Critique approfondie + prédiction chiffrée."""
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        brand = await s.get(SocialBrand, p.brand_id)
        pd = post_dict(p)
    user = f"""{await brand_context(brand, pd['plateforme'])}
Évalue ce post {pd['plateforme']} comme un directeur éditorial exigeant :
{pd['contenu']}
Hashtags: {pd['hashtags']}
JSON : {{"accroche":0-100,"clarte":0-100,"cta":0-100,"adequation_marque":0-100,"risques":[""],"ameliorations":[""],"version_amelioree":""}}"""
    r = await llm_json(user, "Tu es un directeur éditorial strict. JSON strict uniquement.", temperature=0.3)
    vals = [float(r[k]) for k in ("accroche", "clarte", "cta", "adequation_marque") if isinstance(r.get(k), (int, float))]
    q = sum(vals) / len(vals) if vals else None
    pred = await an.predict(brand.id, pd, q)
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        p.prediction = pred
        await s.commit()
    return {"critique": r, "prediction": pred}


async def reply_suggestions(brand_id: str, plateforme: str, commentaire: str, contexte_post: str = "") -> dict:
    brand = await get_brand(brand_id)
    user = f"""{await brand_context(brand, plateforme)}
Post : {contexte_post[:600]}
Commentaire reçu sur {plateforme} : « {commentaire} »
Donne 3 réponses dans la voix de la marque (courtes, utiles, jamais défensives ; si critique ou plainte → désescalade et passage en privé).
JSON : {{"type_commentaire":"question|compliment|critique|spam|lead","reponses":["","",""],"action_recommandee":""}}"""
    return await llm_json(user, SYSTEM_WRITER, temperature=0.6, max_tokens=1500)


# ═════════════════════════ CYCLE DE VIE DES POSTS ═════════════════════════
async def update_post(post_id: str, fields: dict) -> dict:
    allowed = {"contenu", "hashtags", "lien", "scheduled_at", "format", "script_video", "media_urls"}
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        if not p:
            raise ValueError("Post introuvable")
        if p.statut in ("publie", "publication"):
            raise ValueError("Post déjà publié ou en cours de publication")
        old = p.contenu
        for k, v in fields.items():
            if k in allowed and v is not None:
                setattr(p, k, v)
        p.updated_at = utcnow()
        edited = "contenu" in fields and fields["contenu"] and fields["contenu"].strip() != (old or "").strip()
        brand_id, plat, newtext, ia = p.brand_id, p.plateforme, p.contenu, p.genere_par_ia
        await s.commit()
        await s.refresh(p)
        out = post_dict(p)
    if edited and ia:   # l'édition de l'admin est le meilleur signal de style
        await add_style_sample(brand_id, newtext, plat, "edit_admin", 2.0)
    return out


async def validate_post(post_id: str, admin: str, scheduled_at: datetime | None = None) -> dict:
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        if not p or p.statut not in ("brouillon", "a_valider", "echec", "rejete"):
            raise ValueError("Post non validable dans son état actuel")
        brand = await s.get(SocialBrand, p.brand_id)
        when = scheduled_at or p.scheduled_at
        plat, bid = p.plateforme, p.brand_id
        media = list(p.media_urls or [])
    if SPECS[plat]["visuel_requis"] and not media:
        raise ValueError(f"{plat} exige un visuel/vidéo : ajoute un média avant de valider")
    if not when or when < utcnow() + timedelta(minutes=2):
        slot = await an.suggest_slots(bid, plat, 1, cfg(brand)["max_par_jour_par_plateforme"])
        when = slot[0]["scheduled_at"]
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        p.statut, p.scheduled_at, p.validated_by, p.validated_at = "programme", when, admin, utcnow()
        p.erreur, p.nb_tentatives, p.updated_at = None, 0, utcnow()
        await s.commit()
        await s.refresh(p)
        return post_dict(p)


async def reject_post(post_id: str, motif: str, admin: str) -> dict:
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        if not p:
            raise ValueError("Post introuvable")
        p.statut, p.rejet_motif, p.updated_at = "rejete", motif, utcnow()
        brand = await s.get(SocialBrand, p.brand_id)
        learn = list(brand.apprentissages or [])
        learn.append({"date": utcnow().isoformat(), "type": "rejet_admin",
                      "texte": f"Post {p.plateforme} rejeté : {motif}"})
        brand.apprentissages = learn[-40:]
        await s.commit()
        await s.refresh(p)
        return post_dict(p)


async def _account_creds(brand_id: str, platform: str) -> tuple[SocialAccount, dict]:
    async with get_celery_session() as s:
        a = (await s.execute(select(SocialAccount).where(SocialAccount.brand_id == brand_id,
                                                         SocialAccount.plateforme == platform))).scalar_one_or_none()
    if not a:
        raise pub.PublishError(f"Aucun compte {platform} connecté")
    if a.statut == "expire":
        raise pub.PublishError(f"Compte {platform} expiré : reconnecte-le")
    creds = dec(a.credentials_chiffrees)
    try:
        creds2, exp, changed = await pub.ensure_fresh(platform, creds)
    except Exception as e:
        logger.warning("Renouvellement %s impossible : %s", platform, e)
        creds2, exp, changed = creds, None, False
    if changed:
        async with get_celery_session() as s:
            row = await s.get(SocialAccount, a.id)
            row.credentials_chiffrees, row.expire_le, row.statut, row.derniere_erreur = enc(creds2), exp, "actif", None
            await s.commit()
    return a, creds2


async def claim_due_posts(limit: int = 10) -> list[str]:
    now = utcnow()
    async with get_celery_session() as s:
        await s.execute(sa_update(SocialPost).where(SocialPost.statut == "publication",
                                                    SocialPost.updated_at < now - timedelta(minutes=15))
                        .values(statut="programme"))
        ids = (await s.execute(select(SocialPost.id).where(SocialPost.statut == "programme", SocialPost.scheduled_at <= now)
                               .order_by(SocialPost.scheduled_at).limit(limit))).scalars().all()
        claimed = []
        for i in ids:
            r = await s.execute(sa_update(SocialPost).where(SocialPost.id == i, SocialPost.statut == "programme")
                                .values(statut="publication", updated_at=now))
            if r.rowcount:
                claimed.append(i)
        await s.commit()
    return claimed


async def publish_post(post_id: str, force: bool = False) -> dict:
    async with get_celery_session() as s:
        p = await s.get(SocialPost, post_id)
        if not p:
            raise ValueError("Post introuvable")
        if force:
            p.statut = "publication"
            await s.commit()
        pd = post_dict(p)
        nb = p.nb_tentatives
    try:
        acc, creds = await _account_creds(pd["brand_id"], pd["plateforme"])
        res = await pub.publish(pd["plateforme"], pd, creds)
        async with get_celery_session() as s:
            p = await s.get(SocialPost, post_id)
            p.statut, p.published_at, p.external_id, p.external_url = "publie", utcnow(), res["external_id"], res.get("external_url")
            p.erreur, p.updated_at = None, utcnow()
            await s.commit()
        return {"ok": True, **res}
    except Exception as e:
        msg = str(e)[:900]
        logger.warning("Publication %s échouée : %s", post_id, msg)
        auth_err = any(k in msg.lower() for k in ("oauth", "token", "expired", "401", "invalid_grant", "expiré"))
        async with get_celery_session() as s:
            p = await s.get(SocialPost, post_id)
            p.nb_tentatives, p.erreur, p.updated_at = nb + 1, msg, utcnow()
            if auth_err or p.nb_tentatives >= 3 or "exige" in msg or "invalid" in msg.lower():
                p.statut = "echec"
            else:
                p.statut, p.scheduled_at = "programme", utcnow() + timedelta(minutes=5 * (2 ** nb))
            if auth_err:
                await s.execute(sa_update(SocialAccount).where(SocialAccount.brand_id == p.brand_id,
                                                               SocialAccount.plateforme == p.plateforme)
                                .values(statut="expire" if auth_err else "erreur", derniere_erreur=msg))
            await s.commit()
        return {"ok": False, "erreur": msg}


# ═════════════════════════ MÉTRIQUES & SUIVI ═════════════════════════
async def _latest_followers(brand_id, platform) -> int | None:
    async with get_celery_session() as s:
        r = (await s.execute(select(SocialAccountSnapshot).where(SocialAccountSnapshot.brand_id == brand_id,
                                                                  SocialAccountSnapshot.plateforme == platform)
                             .order_by(SocialAccountSnapshot.jour.desc()).limit(1))).scalar_one_or_none()
    return r.followers if r else None


async def collect_metrics(force: bool = False) -> dict:
    now = utcnow()
    async with get_celery_session() as s:
        posts = (await s.execute(select(SocialPost).where(SocialPost.statut == "publie", SocialPost.external_id != None,  # noqa
                                                          SocialPost.published_at >= now - timedelta(days=45)))).scalars().all()
        last = {}
        if posts:
            rows = (await s.execute(select(SocialMetric.post_id, SocialMetric.collecte_le).where(
                SocialMetric.post_id.in_([p.id for p in posts])).order_by(SocialMetric.collecte_le.desc()))).all()
            for pid, t in rows:
                last.setdefault(pid, t)
    done = fail = 0
    creds_cache = {}
    for p in posts:
        age = (now - p.published_at).total_seconds() / 3600
        interval = 3 if age < 48 else 12 if age < 168 else 24
        if not force and p.id in last and (now - last[p.id]).total_seconds() / 3600 < interval - 0.5:
            continue
        try:
            key = (p.brand_id, p.plateforme)
            if key not in creds_cache:
                creds_cache[key] = (await _account_creds(*key))[1]
            raw = await pub.fetch_metrics(p.plateforme, post_dict(p), creds_cache[key])
            fol = await _latest_followers(p.brand_id, p.plateforme)
            inter = raw["likes"] + raw["comments"] + raw["shares"] + raw["saves"]
            denom = raw["reach"] or raw["impressions"] or raw["video_views"] or fol
            async with get_celery_session() as s:
                s.add(SocialMetric(post_id=p.id, brand_id=p.brand_id, plateforme=p.plateforme, age_heures=round(age, 1),
                                   engagement_score=raw["likes"] + 2 * raw["comments"] + 3 * raw["shares"] + 2 * raw["saves"] + .5 * raw["clicks"],
                                   engagement_rate=round(inter / denom, 5) if denom else None, brut=raw, **raw))
                await s.commit()
            done += 1
        except Exception as e:
            fail += 1
            logger.warning("Métriques post %s : %s", p.id, e)
    return {"collectes": done, "echecs": fail}


async def snapshot_followers() -> dict:
    day = utcnow().strftime("%Y-%m-%d")
    n = 0
    async with get_celery_session() as s:
        accs = (await s.execute(select(SocialAccount).where(SocialAccount.statut == "actif"))).scalars().all()
    for a in accs:
        try:
            f = await pub.fetch_followers(a.plateforme, dec(a.credentials_chiffrees))
            if not f:
                continue
            async with get_celery_session() as s:
                ex = (await s.execute(select(SocialAccountSnapshot).where(
                    SocialAccountSnapshot.brand_id == a.brand_id, SocialAccountSnapshot.plateforme == a.plateforme,
                    SocialAccountSnapshot.jour == day))).scalar_one_or_none()
                if ex:
                    ex.followers, ex.media_count = f["followers"], f["media_count"]
                else:
                    s.add(SocialAccountSnapshot(brand_id=a.brand_id, plateforme=a.plateforme, jour=day,
                                                followers=f["followers"], media_count=f["media_count"]))
                await s.commit()
                n += 1
        except Exception as e:
            logger.warning("Snapshot %s : %s", a.plateforme, e)
    return {"snapshots": n}


async def refresh_tokens() -> dict:
    n = 0
    async with get_celery_session() as s:
        accs = (await s.execute(select(SocialAccount).where(SocialAccount.plateforme.in_(("linkedin", "x", "instagram"))))).scalars().all()
    for a in accs:
        try:
            creds, new = dec(a.credentials_chiffrees), None
            if a.plateforme == "linkedin":
                if a.expire_le and a.expire_le > utcnow() + timedelta(days=7):
                    continue
                r = await pub.refresh_credentials("linkedin", creds)
                new = (r[0], r[1]) if r else None
            else:
                c2, exp, ch = await pub.ensure_fresh(a.plateforme, creds)
                new = (c2, exp) if ch else None
            async with get_celery_session() as s:
                row = await s.get(SocialAccount, a.id)
                if new:
                    row.credentials_chiffrees, row.expire_le, row.statut, row.derniere_erreur = enc(new[0]), new[1], "actif", None
                    n += 1
                elif row.expire_le and row.expire_le < utcnow():
                    row.statut, row.derniere_erreur = "expire", "Token expiré — reconnecte le compte"
                await s.commit()
        except Exception as e:
            logger.warning("Refresh %s : %s", a.plateforme, e)
    return {"rafraichis": n}



async def upsert_account(brand_id, plateforme, nom, identifiant, creds, expire_le=None) -> dict:
    async with get_celery_session() as s:
        a = (await s.execute(select(SocialAccount).where(SocialAccount.brand_id == brand_id,
                                                         SocialAccount.plateforme == plateforme))).scalar_one_or_none()
        if a:
            a.nom_affichage, a.identifiant_externe, a.credentials_chiffrees = nom, identifiant, enc(creds)
            a.expire_le, a.statut, a.derniere_erreur, a.updated_at = expire_le, "actif", None, utcnow()
        else:
            a = SocialAccount(brand_id=brand_id, plateforme=plateforme, nom_affichage=nom, identifiant_externe=identifiant,
                              credentials_chiffrees=enc(creds), expire_le=expire_le)
            s.add(a)
        await s.commit()
        await s.refresh(a)
        return {"id": a.id, "plateforme": a.plateforme, "nom": a.nom_affichage, "statut": a.statut}


# ═════════════════════════ RAPPORT & AUTOPILOT ═════════════════════════
async def weekly_report(brand_id: str, days: int = 30) -> dict:
    brand = await get_brand(brand_id)
    faits = await an.performance_summary(brand_id, days)
    if not faits["nb_posts"]:
        return {"message": "Pas encore de posts publiés sur la période"}
    bt = {p: (await an.best_times(brand_id, p, 3)) for p in PLATFORMS}
    user = f"""{await brand_context(brand)}
DONNÉES RÉELLES (ne cite que ces chiffres) :
{json.dumps(faits, ensure_ascii=False, default=str)[:6000]}
MEILLEURS CRÉNEAUX PAR PLATEFORME : {json.dumps(bt, ensure_ascii=False)}

Analyse comme un head of social. JSON :
{{"resume":"3 phrases","ce_qui_marche":[""],"ce_qui_ne_marche_pas":[""],"recommandations":[{{"action":"","impact_attendu":"","priorite":"haute|moyenne|basse"}}],
"hypotheses_a_tester":[""],"cadence_recommandee":{{"linkedin":0,"facebook":0,"instagram":0,"tiktok":0}},
"apprentissages_a_retenir":["règles courtes et actionnables pour les prochains posts"]}}"""
    a = await llm_json(user, "Tu es head of social media data-driven. N'invente aucun chiffre. JSON strict.", temperature=0.3, max_tokens=3500)
    async with get_celery_session() as s:
        s.add(SocialReport(brand_id=brand_id, periode_debut=(utcnow() - timedelta(days=days)).strftime("%Y-%m-%d"),
                           periode_fin=utcnow().strftime("%Y-%m-%d"), faits=json.loads(json.dumps(faits, default=str)), analyse=a))
        b = await s.get(SocialBrand, brand_id)
        learn = list(b.apprentissages or [])
        known = [x["texte"] for x in learn]
        for t in a.get("apprentissages_a_retenir", []):
            if not any(difflib.SequenceMatcher(None, t.lower(), k.lower()).ratio() > .8 for k in known):
                learn.append({"date": utcnow().isoformat(), "type": "rapport", "texte": t})
        b.apprentissages = learn[-40:]
        await s.commit()
    for t in faits["top_posts"][:3]:      # boucle d'apprentissage : les meilleurs posts deviennent des références de style
        async with get_celery_session() as s:
            p = await s.get(SocialPost, t["id"])
        if p:
            await add_style_sample(brand_id, p.contenu, p.plateforme, "post_performant", 1.5)
    return {"analyse": a, "nb_posts": faits["nb_posts"]}


async def autopilot_weekly(brand_id: str) -> dict:
    brand = await get_brand(brand_id)
    c = cfg(brand)
    try:
        await weekly_report(brand_id, 30)
        brand = await get_brand(brand_id)
    except Exception as e:
        logger.warning("Rapport autopilot ignoré : %s", e)
    async with get_celery_session() as s:
        connected = set((await s.execute(select(SocialAccount.plateforme).where(
            SocialAccount.brand_id == brand_id, SocialAccount.statut == "actif"))).scalars().all())
    quota = {p: n for p, n in c["cadence_hebdo"].items() if p in c["plateformes_actives"] and (p in connected or not connected)}
    if not quota:
        return {"message": "Aucune plateforme active"}
    ideas = await generate_ideas(brand_id, nb=max(quota.values()) + 2)
    direct = (not c["validation_requise"]) and c["autopilot_publication_directe"]
    created = 0
    for iid in ideas["ids"]:
        if all(v <= 0 for v in quota.values()):
            break
        async with get_celery_session() as s:
            idea = await s.get(SocialIdea, iid)
        plats = [p for p in idea.plateformes if quota.get(p, 0) > 0] or [p for p, v in quota.items() if v > 0][:2]
        try:
            r = await write_posts(iid, plats, auto_publish=direct)
            for p in plats:
                quota[p] -= 1
            created += r["posts_crees"]
        except Exception as e:
            logger.warning("Autopilot idée %s : %s", iid, e)
    return {"idees": len(ideas["ids"]), "posts_crees": created, "publication_directe": direct}


# ═════════════════════════ JOBS ═════════════════════════
async def job_update(job_id: str, **vals):
    async with get_celery_session() as s:
        j = await s.get(SocialJob, job_id)
        for k, v in vals.items():
            setattr(j, k, v)
        if vals.get("statut") in ("termine", "echec"):
            j.finished_at = utcnow()
        await s.commit()


JOB_HANDLERS = {
    "analyze_brand": analyze_brand,
    "refresh_tone": refresh_tone,
    "generate_ideas": generate_ideas,
    "write_posts": write_posts,
    "regenerate_post": regenerate_post,
    "make_variants": make_variants,
    "score_post": score_post,
    "weekly_report": weekly_report,
    "autopilot": autopilot_weekly,
    "sync_metrics": lambda **kw: collect_metrics(force=True),
}


JOB_HANDLERS.update({
    "analyze_assets": lambda **kw: asyncio.to_thread(assets.analyze_folder, **kw),
    "reanalyze_asset": lambda **kw: asyncio.to_thread(assets.reanalyze, **kw),
    "preview_visual": lambda **kw: preview_visual(kw["spec"], kw["plateforme"]),
    
})

