# services/social/social_assets.py
import base64
import hashlib
import io
import json
import logging
import os
import random
import re
import shutil
import time
import unicodedata
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
import fcntl
import yaml
from PIL import Image

logger = logging.getLogger("social_assets")

BRANDING_DIR = Path(os.getenv("SOCIAL_BRANDING_DIR", "/app/data/branding_rh_manager"))
PHOTOS_DIR = BRANDING_DIR / "photos"
ASSETS_DIR = BRANDING_DIR / "assets"
FICHE_PATH = Path(os.getenv("SOCIAL_FICHE_TECHNIQUE", "/app/data/fiche_technique_agent.yaml"))

VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "qwen/qwen3.8-27b")
IMG_EXT = {".png", ".jpg", ".jpeg", ".webp"}
PLATFORMS = ("facebook", "instagram", "linkedin", "tiktok","x")
LANDSCAPE = {"linkedin", "facebook"}
TEMPLATES = {"capture_cadree", "capture_zoom", "photo_overlay", "carte", "carrousel", "aucun",
             "tilt", "glass", "duo", "checklist", "quote", "bold", "video"}
MANUAL_KEYS = ("exclu", "notes_admin")
EDITABLE = {"module", "ecran", "titre_court", "description", "fonctionnalites_visibles", "mots_cles", "hashtags",
            "angles_posts", "legendes_montage", "zone_focus", "zones_sensibles", "donnees_personnelles_visibles",
            "plateformes_recommandees", "exclu", "notes_admin", "public_cible", "benefices", "problemes_resolus",
            "type_image"}

_cache = {"stamp": None, "items": []}


# ═════════════════════════ UTILITAIRES ═════════════════════════
def _ensure_dirs():
    PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)


def _sha1(b: bytes) -> str:
    return hashlib.sha1(b).hexdigest()


def _strip_accents(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))


def slugify(t, max_len: int = 60) -> str:
    t = _strip_accents(str(t or "")).lower()
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t[:max_len].strip("-")


_STOP = set("le la les un une des de du et en pour par sur avec dans au aux ce ces sa son ses est sont qui que quoi "
            "the and for with your you vos votre notre nos plus tout tous cette cet etre avoir faire".split())


def tokens(t) -> set:
    out = set()
    for w in re.findall(r"[a-z0-9]{3,}", _strip_accents(str(t or "")).lower()):
        if w not in _STOP:
            out.add(w[:6])          # racinisation grossière (bulletin/bulletins)
    return out


def _flatten(img: Image.Image) -> Image.Image:
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        bg.alpha_composite(rgba)
        return bg.convert("RGB")
    return img.convert("RGB")


def _fiche_excerpt(limit: int = 4500) -> str:
    try:
        return FICHE_PATH.read_text("utf-8")[:limit]
    except Exception:
        return "(fiche technique indisponible)"


def _palette(img: Image.Image, n: int = 4) -> list:
    try:
        q = img.resize((96, 96)).quantize(colors=n)
        pal = q.getpalette() or []
        cols = sorted(q.getcolors() or [], reverse=True)
        return ["#%02x%02x%02x" % tuple(pal[i * 3:i * 3 + 3]) for _, i in cols[:n]]
    except Exception:
        return []


# ═════════════════════════ ANALYSE VISION (Groq) ═════════════════════════
VISION_INTRO = """Tu analyses UNE image du dossier de marque d'un éditeur de logiciel (RH Manager / Nagora : SIRH, paie, pointage, congés, recrutement, école, comptabilité, signature, visio, gouvernance IT...). Cette analyse alimente un agent qui rédige des posts pour les réseaux sociaux : sois factuel et précis.

RÈGLES
- Décris UNIQUEMENT ce qui est réellement visible. Si un texte est illisible, ne le devine pas.
- N'invente aucun chiffre, nom de personne ou fonctionnalité qui ne soit pas visible à l'écran (ou documenté dans la fiche technique ci-dessous).
- Les coordonnées (x, y, w, h) sont en POURCENTAGE de l'image (0-100), origine en haut à gauche.
- zone_focus : la région la plus parlante pour un zoom marketing (tableau, graphique, formulaire...). Si l'image entière est pertinente, mets x=0,y=0,w=100,h=100.
- zones_sensibles : encadre tout nom/prénom de personne, visage, salaire, téléphone, email, adresse, numéro d'identité ou de compte lisibles. Si rien : [].
- Réponds avec UN SEUL objet JSON, sans texte autour."""

VISION_SCHEMA = """{
 "type_image": "capture_logiciel | logo | schema | illustration | photo | autre",
 "slug_nom": "3 à 6 mots français en kebab-case sans accents qui décrivent l'écran (ex: paie-bulletin-validation-signature)",
 "module": "paie|pointage|conges|recrutement|ecole|comptabilite|facturation|documents|signature|planning|organigramme|gouvernance_it|visio|messagerie|reporting|parametres|tableau_de_bord|marque|autre",
 "ecran": "intitulé de l'écran ou de la vue",
 "titre_court": "5 à 8 mots",
 "description": "3 à 5 phrases factuelles",
 "fonctionnalites_visibles": ["..."],
 "elements_ui": ["tableaux, graphiques, boutons, filtres... réellement visibles"],
 "texte_visible": ["libellés importants lisibles, 12 max"],
 "public_cible": ["DRH, comptable, directeur d'école..."],
 "problemes_resolus": ["..."],
 "benefices": ["..."],
 "mots_cles": ["8 à 14 mots-clés français"],
 "hashtags": ["#...", "5 à 8 hashtags pertinents"],
 "angles_posts": [{"pilier": "", "accroche": "", "legende_courte": ""}],
 "legendes_montage": [{"titre": "max 8 mots percutants", "sous_titre": "max 14 mots"}],
 "zone_focus": {"x": 0, "y": 0, "w": 100, "h": 100},
 "zones_sensibles": [{"x": 0, "y": 0, "w": 0, "h": 0, "nature": "nom|visage|salaire|telephone|email|adresse|identifiant"}],
 "donnees_personnelles_visibles": false,
 "appareil": "ordinateur|mobile|tablette|n/a",
 "plateformes_recommandees": ["linkedin", "facebook", "instagram", "tiktok"],
 "lisibilite": 0,
 "esthetique": 0,
 "utilisable_social": true
}
Donne 3 angles_posts et 3 legendes_montage."""



def _client(exclude=()):
    from groq import Groq
    from agent.services.llm_client import llm_usage as U
    kid, key = U.pick_key("vision", exclude)
    if not key:
        raise RuntimeError("Aucune clé Groq disponible (Paramètres › Clés API ou Configuration)")
    c = Groq(api_key=key)
    c._kid = kid
    return c

def _encode(path: Path):
    img = Image.open(path)
    img.load()
    w, h = img.size
    rgb = _flatten(img)
    side, data = 1600, b""
    for q in (85, 75, 65, 55, 45):
        im = rgb.copy()
        im.thumbnail((side, side))
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q)
        data = buf.getvalue()
        if len(data) < 2_800_000:      # limite Groq : 4 Mo en base64
            break
        side = int(side * 0.8)
    return "data:image/jpeg;base64," + base64.b64encode(data).decode(), w, h, rgb


def _call_vision(client, data_url: str, prompt: str) -> str:
    import groq
    from agent.services.llm_client import llm_usage as U
    model = U.model_for("vision", VISION_MODEL)
    messages = [{"role": "user", "content": [{"type": "text", "text": prompt},
                                              {"type": "image_url", "image_url": {"url": data_url}}]}]
    variants = [{"response_format": {"type": "json_object"}}, {}]
    last, tried = None, set()
    for extra in variants:
        for retry in range(4):
            U.check_budget()
            kid = getattr(client, "_kid", "env")
            t0 = time.time()
            try:
                r = client.chat.completions.create(model=model, messages=messages, temperature=0.2,
                                                   max_completion_tokens=3000, stream=False, **extra)
                u = getattr(r, "usage", None)
                U.record("vision", kid, model, getattr(u, "prompt_tokens", 0) or 0,
                         getattr(u, "completion_tokens", 0) or 0, True, 200, int((time.time() - t0) * 1000))
                return r.choices[0].message.content or ""
            except groq.RateLimitError as e:
                last = e
                U.record("vision", kid, model, 0, 0, False, 429, int((time.time() - t0) * 1000), str(e))
                if U.classify_error(429, str(e)) == "exhausted":
                    U.mark_key(kid, "epuise", str(e)[:200], 3600)
                    tried.add(kid)
                    client = _client(tried)
                    continue
                time.sleep(15 * (retry + 1))
            except (groq.AuthenticationError, groq.PermissionDeniedError) as e:
                last = e
                U.record("vision", kid, model, 0, 0, False, 401, int((time.time() - t0) * 1000), str(e))
                U.mark_key(kid, "invalide", str(e)[:200])
                tried.add(kid)
                client = _client(tried)
                continue
            except groq.BadRequestError as e:      # option non supportée → variante suivante
                last = e
                break
            except (groq.APIStatusError, groq.APIConnectionError) as e:
                last = e
                U.record("vision", kid, model, 0, 0, False, getattr(e, "status_code", 0) or 0,
                         int((time.time() - t0) * 1000), str(e))
                time.sleep(5)
    raise RuntimeError(f"Groq vision a échoué ({model}) : {last}")


def _parse_json(text: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    text = re.sub(r"```(?:json)?", "", text)
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("JSON introuvable dans la réponse")
    return json.loads(text[a:b + 1])


def _truthy(v, default=True) -> bool:
    if v is None:
        return default
    return str(v).strip().lower() not in ("false", "0", "non", "no", "none", "")


def _build_item(m: dict, w: int, h: int, rgb: Image.Image) -> dict:
    def L(key, n=20):
        v = m.get(key)
        return [str(x).strip() for x in v if str(x).strip()][:n] if isinstance(v, list) else []

    def box(b):
        try:
            x, y, bw, bh = (float(b[k]) for k in ("x", "y", "w", "h"))
        except Exception:
            return None
        x, y = max(0.0, min(99.0, x)), max(0.0, min(99.0, y))
        bw, bh = max(1.0, min(100 - x, bw)), max(1.0, min(100 - y, bh))
        return {"x": round(x, 1), "y": round(y, 1), "w": round(bw, 1), "h": round(bh, 1)}

    def num(k, d=60):
        try:
            return max(0, min(100, int(float(m.get(k, d)))))
        except Exception:
            return d

    focus = box(m.get("zone_focus") or {})
    if focus and focus["w"] >= 85 and focus["h"] >= 85:
        focus = None
    zones = []
    for z in m.get("zones_sensibles") or []:
        b = box(z) if isinstance(z, dict) else None
        if b:
            b["nature"] = str(z.get("nature", "autre"))[:20]
            zones.append(b)
    tags = []
    for t in L("hashtags", 12):
        t = "#" + re.sub(r"[^\w]", "", t.lstrip("#"))
        if len(t) > 2 and t.lower() not in [x.lower() for x in tags]:
            tags.append(t)
    ori = "paysage" if w / h > 1.15 else "portrait" if h / w > 1.15 else "carre"
    appareil = str(m.get("appareil") or "ordinateur").split("|")[0].strip().lower()
    if ori == "portrait" and w / h < 0.8:
        appareil = "mobile"
    return {
        "type_image": str(m.get("type_image") or "capture_logiciel").split("|")[0].strip().lower(),
        "slug_nom": slugify(m.get("slug_nom") or ""),
        "module": str(m.get("module") or "autre").split("|")[0].strip().lower(),
        "ecran": str(m.get("ecran") or "").strip(),
        "titre_court": str(m.get("titre_court") or "").strip(),
        "description": str(m.get("description") or "").strip(),
        "fonctionnalites_visibles": L("fonctionnalites_visibles"),
        "elements_ui": L("elements_ui"),
        "texte_visible": L("texte_visible", 12),
        "public_cible": L("public_cible", 8),
        "problemes_resolus": L("problemes_resolus", 8),
        "benefices": L("benefices", 8),
        "mots_cles": L("mots_cles", 14),
        "hashtags": tags[:10],
        "angles_posts": [{"pilier": str(a.get("pilier", "")), "accroche": str(a.get("accroche", "")),
                          "legende_courte": str(a.get("legende_courte", ""))}
                         for a in (m.get("angles_posts") or []) if isinstance(a, dict)][:4],
        "legendes_montage": [{"titre": str(a.get("titre", ""))[:80], "sous_titre": str(a.get("sous_titre", ""))[:140]}
                             for a in (m.get("legendes_montage") or []) if isinstance(a, dict)][:4],
        "zone_focus": focus,
        "zones_sensibles": zones,
        "donnees_personnelles_visibles": _truthy(m.get("donnees_personnelles_visibles"), False) or bool(zones),
        "appareil": appareil,
        "plateformes_recommandees": [p for p in L("plateformes_recommandees") if p in PLATFORMS],
        "qualite": {"lisibilite": num("lisibilite"), "esthetique": num("esthetique"),
                    "utilisable_social": _truthy(m.get("utilisable_social"), True)},
        "dimensions": {"largeur": w, "hauteur": h},
        "orientation": ori,
        "couleurs_dominantes": _palette(rgb),
    }


def analyze_image(path, client=None) -> dict:
    """Analyse une image avec le modèle vision et retourne les métadonnées structurées."""
    client = client or _client()
    path = Path(path)
    data_url, w, h, rgb = _encode(path)
    prompt = (f"{VISION_INTRO}\n\nSCHÉMA JSON À REMPLIR :\n{VISION_SCHEMA}\n\n"
              f"FICHE TECHNIQUE DU PRODUIT (référence pour les noms de modules et fonctionnalités) :\n{_fiche_excerpt()}\n\n"
              f"Nom de fichier d'origine (indice faible) : {path.name}\nDimensions : {w}x{h}px")
    last = None
    for _ in range(2):
        raw = _call_vision(client, data_url, prompt)
        try:
            return _build_item(_parse_json(raw), w, h, rgb)
        except Exception as e:
            last = e
    raise RuntimeError(f"Réponse vision non exploitable : {last}")


# ═════════════════════════ CATALOGUE (fichiers .yml) ═════════════════════════
def _write_yaml(item: dict):
    _ensure_dirs()
    p = ASSETS_DIR / f"{item['id']}.yml"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(yaml.safe_dump(item, allow_unicode=True, sort_keys=False, width=110, default_flow_style=False), "utf-8")
    tmp.replace(p)
    _cache["stamp"] = None

def list_assets(include_excluded: bool = False) -> list:
    _ensure_dirs()
    ymls = sorted(ASSETS_DIR.glob("*.yml"))
    stamp = (ASSETS_DIR.stat().st_mtime_ns, tuple((y.name, y.stat().st_mtime_ns) for y in ymls))
    if _cache["stamp"] != stamp:
        items = []
        for y in ymls:
            try:
                d = yaml.safe_load(y.read_text("utf-8")) or {}
            except Exception:
                logger.warning("YAML illisible : %s", y.name)
                continue
            d.setdefault("id", y.stem)
            if not (ASSETS_DIR / str(d.get("fichier", ""))).is_file():
                continue
            items.append(d)
        _cache.update(stamp=stamp, items=items)
    return [d for d in _cache["items"] if include_excluded or not d.get("exclu")]


def get_asset(asset_id: str, include_excluded: bool = True):
    return next((a for a in list_assets(include_excluded) if a["id"] == asset_id), None)


def asset_path(item: dict) -> Path:
    return ASSETS_DIR / item["fichier"]


def find_logo(cfg: dict | None = None):
    items = list_assets(include_excluded=True)
    wanted = (cfg or {}).get("logo_asset_id")
    if wanted:
        it = next((a for a in items if a["id"] == wanted), None)
        if it:
            return asset_path(it)
    for it in items:
        if it.get("type_image") == "logo":
            return asset_path(it)
    for p in list(PHOTOS_DIR.glob("*[Ll]ogo*")) + list(ASSETS_DIR.glob("*logo*")):
        if p.suffix.lower() in IMG_EXT:
            return p
    return None


def update_asset(asset_id: str, patch: dict) -> dict:
    it = get_asset(asset_id)
    if not it:
        raise ValueError("Capture introuvable")
    for k, v in patch.items():
        if k in EDITABLE:
            it[k] = v
    _write_yaml(it)
    return it


def delete_asset(asset_id: str):
    it = get_asset(asset_id)
    if not it:
        raise ValueError("Capture introuvable")
    asset_path(it).unlink(missing_ok=True)
    (ASSETS_DIR / f"{it['id']}.yml").unlink(missing_ok=True)
    _cache["stamp"] = None


def save_upload(filename: str, data: bytes) -> str:
    _ensure_dirs()
    ext = Path(filename or "").suffix.lower()
    if ext not in IMG_EXT:
        raise ValueError("Formats acceptés : png, jpg, webp")
    stem = slugify(Path(filename).stem) or "upload"
    name, n = f"{stem}{ext}", 2
    while (PHOTOS_DIR / name).exists():
        name = f"{stem}-{n}{ext}"
        n += 1
    (PHOTOS_DIR / name).write_bytes(data)
    return name


def _unique_slug(base: str, sha: str) -> str:
    base = slugify(base) or "capture"
    slug, n = base, 2
    while (ASSETS_DIR / f"{slug}.yml").exists():
        try:
            if (yaml.safe_load((ASSETS_DIR / f"{slug}.yml").read_text("utf-8")) or {}).get("sha1") == sha:
                return slug
        except Exception:
            pass
        slug = f"{base}-{n:02d}"
        n += 1
    return slug


def analyze_folder(move=None, force: bool = False, max_images: int | None = None, pause: float = 2.0) -> dict:
    """Analyse les nouvelles images de photos/, les renomme selon leur contenu et écrit un .yml par image.
    Idempotent (empreinte SHA-1) : relancer ne retraite que les nouveautés."""
    _ensure_dirs()
    if move is None:
        move = os.getenv("SOCIAL_ASSETS_MOVE", "0") == "1"
    index = {a.get("sha1"): a for a in list_assets(include_excluded=True)}
    files = sorted(p for p in PHOTOS_DIR.iterdir()
                   if p.is_file() and p.suffix.lower() in IMG_EXT and not p.name.startswith("."))
    stats = {"nouvelles": 0, "deja_analysees": 0, "erreurs": [], "restantes": 0, "details": []}
    client = None
    for p in files:
        try:
            sha = _sha1(p.read_bytes())
        except Exception as e:
            stats["erreurs"].append({"fichier": p.name, "erreur": str(e)[:200]})
            continue
        known = index.get(sha)
        if known and not force:
            stats["deja_analysees"] += 1
            if move and (ASSETS_DIR / known["fichier"]).exists():
                p.unlink(missing_ok=True)
            continue
        if max_images and stats["nouvelles"] >= max_images:
            stats["restantes"] += 1
            continue
        try:
            client = client or _client()
            item = analyze_image(p, client)
        except Exception as e:
            logger.warning("Analyse %s : %s", p.name, e)
            stats["erreurs"].append({"fichier": p.name, "erreur": str(e)[:300]})
            continue
        proposed = item.pop("slug_nom", "") or f"{item['module']}-{slugify(item['ecran'])}"
        if known:
            slug, fichier = known["id"], known["fichier"]
            for k in MANUAL_KEYS:
                if k in known:
                    item[k] = known[k]
        else:
            slug = _unique_slug(proposed, sha)
            fichier = f"{slug}{p.suffix.lower()}"
        dest = ASSETS_DIR / fichier
        if not dest.exists():
            (shutil.move if move else shutil.copy2)(str(p), str(dest))
        elif move and p.exists():
            p.unlink()
        full = {"id": slug, "fichier": fichier, "original": p.name, "sha1": sha, **item,
                "exclu": item.get("exclu", False), "notes_admin": item.get("notes_admin", ""),
                "analyse_le": datetime.utcnow().isoformat(timespec="seconds"), "modele": VISION_MODEL}
        _write_yaml(full)
        index[sha] = full
        stats["nouvelles"] += 1
        stats["details"].append({"original": p.name, "id": slug})
        time.sleep(pause)        # ménage les limites de débit du plan gratuit
    return stats


def reanalyze(asset_id: str) -> dict:
    it = get_asset(asset_id)
    if not it:
        raise ValueError("Capture introuvable")
    meta = analyze_image(asset_path(it))
    meta.pop("slug_nom", None)
    for k in MANUAL_KEYS:
        if k in it:
            meta[k] = it[k]
    full = {"id": it["id"], "fichier": it["fichier"], "original": it.get("original"), "sha1": it.get("sha1"), **meta,
            "exclu": it.get("exclu", False), "notes_admin": it.get("notes_admin", ""),
            "analyse_le": datetime.utcnow().isoformat(timespec="seconds"), "modele": VISION_MODEL}
    _write_yaml(full)
    return {"id": it["id"], "ok": True}



def scan_once(max_images: int = 40) -> dict:
    """Analyse les nouvelles captures. Un seul scan à la fois, même avec plusieurs workers."""
    _ensure_dirs()
    lock = open(BRANDING_DIR / ".scan.lock", "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        return {"message": "Un scan est déjà en cours"}
    try:
        return analyze_folder(move=False, force=False, max_images=max_images)
    finally:
        fcntl.flock(lock, fcntl.LOCK_UN)
        lock.close()


def diagnostic(allow_sensitive: bool = False) -> dict:
    ymls = list(ASSETS_DIR.glob("*.yml"))
    items = list_assets(include_excluded=True)
    known = {a.get("sha1") for a in items}
    reasons = Counter()
    for a in items:
        if a.get("exclu"):
            reasons["exclue_manuellement"] += 1
        elif a.get("type_image") == "logo":
            reasons["logo"] += 1
        elif (a.get("qualite") or {}).get("utilisable_social") is False:
            reasons["jugee_inutilisable_par_ia"] += 1
        elif _sensitive_unblurred(a) and not allow_sensitive:
            reasons["donnees_perso_sans_zone_floutee"] += 1
        else:
            reasons["utilisable"] += 1
    pending = 0
    for p in PHOTOS_DIR.iterdir():
        if p.is_file() and p.suffix.lower() in IMG_EXT and not p.name.startswith("."):
            try:
                if _sha1(p.read_bytes()) not in known:
                    pending += 1
            except Exception:
                pass
    return {"assets_dir": str(ASSETS_DIR), "photos_dir": str(PHOTOS_DIR), "yml": len(ymls), "valides": len(items),
            "orphelins": len(ymls) - len(items), "photos_a_analyser": pending, "raisons": dict(reasons),
            "modele": VISION_MODEL}
# ═════════════════════════ PRÉSÉLECTION ═════════════════════════
_FIELDS = (("mots_cles", 3), ("module", 3), ("titre_court", 2), ("ecran", 2), ("fonctionnalites_visibles", 2),
           ("benefices", 1), ("problemes_resolus", 1), ("public_cible", 1), ("description", 1), ("texte_visible", 1))


def _flat(v) -> str:
    return " ".join(map(str, v)) if isinstance(v, list) else str(v or "")


def _sensitive_unblurred(a: dict) -> bool:
    return bool(a.get("donnees_personnelles_visibles")) and not a.get("zones_sensibles")


def eligible(a: dict, allow_sensitive: bool = False) -> bool:
    if a.get("exclu") or a.get("type_image") == "logo":
        return False
    if (a.get("qualite") or {}).get("utilisable_social") is False:
        return False
    if not allow_sensitive and _sensitive_unblurred(a):
        return False
    return True

def shortlist(text: str, platform: str | None = None, k: int = 8, stats: dict | None = None,
              allow_sensitive: bool = False, exclude=()) -> list:
    qt = tokens(text)
    stats = stats or {}
    usage, perf, mean = stats.get("usage_30j") or {}, stats.get("par_asset") or {}, stats.get("er_moyen")
    scored = []
    for a in list_assets():
        if a["id"] in exclude or not eligible(a, allow_sensitive):
            continue
        sc = 0.0
        for key, w in _FIELDS:
            sc += w * len(qt & tokens(_flat(a.get(key))))
        q = a.get("qualite") or {}
        sc *= 0.7 + 0.6 * ((q.get("lisibilite", 60) + q.get("esthetique", 60)) / 200)
        if platform and platform in (a.get("plateformes_recommandees") or []):
            sc += 1
        sc /= 1 + 1.0 * usage.get(a["id"], 0)          # anti-répétition renforcée
        p = perf.get(a["id"])
        if p and p["n"] >= 2 and mean:
            sc *= 1 + 0.3 * max(-1.0, min(1.0, p["er_moyen"] / mean - 1))
        sc += random.random() * 1.2                     # étale le choix même sans correspondance lexicale
        scored.append((sc, a))
    scored.sort(key=lambda t: t[0], reverse=True)
    out, per_mod = [], Counter()
    for _, a in scored:                                 # max 2 par module tant qu'on n'a pas k résultats
        m = a.get("module") or "autre"
        if per_mod[m] >= 2:
            continue
        per_mod[m] += 1
        out.append(a)
        if len(out) >= k:
            break
    if len(out) < k:
        out += [a for _, a in scored if a not in out][:k - len(out)]
    return out

def prompt_catalog(items: list, stats: dict | None = None) -> str:
    usage = (stats or {}).get("usage_30j") or {}
    lines = []
    for a in items:
        lines.append(
            f"[{a['id']}] module={a.get('module')} | écran={a.get('ecran') or a.get('titre_court')} | "
            f"{a.get('orientation', '')}/{a.get('appareil', '')} | fonctions: {'; '.join((a.get('fonctionnalites_visibles') or [])[:5])} | "
            f"bénéfices: {'; '.join((a.get('benefices') or [])[:3])} | hashtags: {' '.join((a.get('hashtags') or [])[:5])} | "
            f"zoom_possible={'oui' if a.get('zone_focus') else 'non'} | utilisée {usage.get(a['id'], 0)}× en 30j")
    return "\n".join(lines)


def modules_summary(stats: dict | None = None) -> str:
    usage = (stats or {}).get("usage_30j") or {}
    perf = (stats or {}).get("par_module") or {}
    mods = {}
    for a in list_assets():
        if not eligible(a, False) and not eligible(a, True):
            continue
        m = mods.setdefault(a.get("module") or "autre", {"n": 0, "u": 0})
        m["n"] += 1
        m["u"] += usage.get(a["id"], 0)
    if not mods:
        return "(aucune capture analysée)"
    out = []
    for name, v in sorted(mods.items(), key=lambda kv: kv[1]["u"]):
        er = perf.get(name, {}).get("er_moyen")
        out.append(f"- {name} : {v['n']} capture(s), {v['u']} utilisation(s)/30j"
                   f"{', ER ' + str(er) if er is not None else ''}{' ← jamais utilisé' if v['u'] == 0 else ''}")
    return "\n".join(out)


# ═════════════════════════ STATS D'USAGE & PERFORMANCE ═════════════════════════
async def asset_report(brand_id: str) -> dict:
    """Usage 30 j + engagement moyen par capture / module / template de montage."""
    from sqlmodel import select
    from agent.db import SocialMetric, SocialPost, get_celery_session

    catalog = {a["id"]: a for a in list_assets(include_excluded=True)}
    now = datetime.utcnow()
    async with get_celery_session() as s:
        posts = (await s.execute(select(SocialPost).where(
            SocialPost.brand_id == brand_id, SocialPost.statut != "rejete",
            SocialPost.created_at >= now - timedelta(days=365)))).scalars().all()
        pub_ids = [p.id for p in posts if p.statut == "publie"]
        latest = {}
        if pub_ids:
            ms = (await s.execute(select(SocialMetric).where(SocialMetric.post_id.in_(pub_ids))
                                  .order_by(SocialMetric.collecte_le.desc()))).scalars().all()
            for m in ms:
                latest.setdefault(m.post_id, m)
    usage, per_asset, per_mod, per_tpl, all_er = Counter(), {}, {}, {}, []
    for p in posts:
        spec = p.visuel_spec or {}
        ids = spec.get("asset_ids") or []
        if p.created_at >= now - timedelta(days=30):
            for a in ids:
                usage[a] += 1
        m = latest.get(p.id)
        if p.statut == "publie" and m and m.engagement_rate is not None:
            er = m.engagement_rate
            all_er.append(er)
            per_tpl.setdefault(spec.get("template") or "aucun", []).append(er)
            for a in ids:
                per_asset.setdefault(a, []).append(er)
                per_mod.setdefault(catalog.get(a, {}).get("module", "?"), []).append(er)

    def agg(d):
        return {k: {"n": len(v), "er_moyen": round(sum(v) / len(v), 4)} for k, v in d.items()}

    return {"usage_30j": dict(usage), "par_asset": agg(per_asset), "par_module": agg(per_mod),
            "par_template": agg(per_tpl), "er_moyen": round(sum(all_er) / len(all_er), 4) if all_er else None}


# ═════════════════════════ SPEC VISUELLE FINALE ═════════════════════════


VARIETY = ["capture_cadree", "tilt", "tilt", "glass", "bold", "checklist", "duo"]


def finalize_spec(spec, platform: str, text: str, catalog: dict, cfg: dict | None = None, stats: dict | None = None,
                  stock_ok: bool = False, visuel_requis: bool = False) -> dict:
    cfg = cfg or {}
    spec = dict(spec or {})
    tpl = spec.get("template") or {"carte": "carte", "image_ia": "photo_overlay", "aucun": "aucun"}.get(spec.get("type"))
    if tpl == "split":
        tpl = "capture_cadree"
    allow = bool(cfg.get("autoriser_captures_sensibles"))
    use_caps = cfg.get("utiliser_captures", True)
    usable = {i: a for i, a in catalog.items() if eligible(a, allow)}
    if (tpl == "aucun" or cfg.get("mode_visuel") == "aucun") and not visuel_requis:
        return {"template": "aucun", "asset_ids": []}
    if tpl == "aucun":
        tpl = None
    if tpl == "video":
        tpl = "carrousel"
    if platform == "tiktok" and tpl not in ("carrousel", "photo_overlay"):
        tpl = "carrousel"
    rnd = random.Random(hashlib.md5(f"{platform}|{text or 'x'}".encode()).hexdigest())
    if cfg.get("varier_montages", True) and tpl in (None, "capture_cadree") and platform != "tiktok":
        tpl = rnd.choice(VARIETY)
    excl = set()
    ids = [i for i in (spec.get("asset_ids") or []) if i in usable]
    if spec.get("reshuffle"):
        excl, ids = set(ids), []
    slides = [dict(sl) for sl in (spec.get("slides") or []) if isinstance(sl, dict) and sl.get("asset_id") in usable]
    uq = (spec.get("unsplash_query") or "").strip()

    if use_caps and not ids and not slides and tpl not in ("carte", "photo_overlay", "quote"):
        k = 5 if tpl == "carrousel" else 2 if tpl == "duo" else 1
        short = [a for a in shortlist(f"{text[:300]} {spec.get('titre_carte') or ''}", platform, k + 2, stats, allow, excl)
                 if a["id"] in usable]
        ids = [a["id"] for a in short[:k]]
    if not tpl:
        tpl = "capture_cadree" if (ids or slides) else ("photo_overlay" if stock_ok and uq else "carte")
    if tpl not in TEMPLATES:
        tpl = "capture_cadree" if ids else "carte"

    if tpl == "carrousel":
        if len(slides) < 2 and len(ids) >= 2:
            slides = [{"asset_id": i} for i in ids]
        if len(slides) < 2:
            if slides and not ids:
                ids = [slides[0]["asset_id"]]
            slides, tpl = [], ("capture_cadree" if ids else "carte")
    if tpl == "video":
        if not ids and slides:
            ids = [sl["asset_id"] for sl in slides]
        if ids:
            ids, slides = ids[:5], []
        else:
            tpl = "photo_overlay" if (stock_ok and uq) else "carte"
    if tpl in ("capture_cadree", "capture_zoom", "tilt", "glass", "bold") and not ids:
        tpl = "photo_overlay" if (stock_ok and uq) else "carte"
    if tpl == "duo":
        if len(ids) < 2:
            extra = [a["id"] for a in shortlist(text[:300], platform, 4, stats, allow, set(ids)) if a["id"] in usable]
            ids = (ids + extra)[:2]
        tpl = "duo" if len(ids) >= 2 else ("tilt" if ids else "carte")
    if tpl == "photo_overlay" and not (stock_ok and uq):
        tpl = "capture_cadree" if ids else "carte"
    if tpl == "capture_zoom" and ids and not usable[ids[0]].get("zone_focus"):
        tpl = "capture_cadree"

    if tpl == "carrousel":
        slides = slides[:int(cfg.get("carrousel_max_slides", 5))]
        ids = [sl["asset_id"] for sl in slides]
        for sl in slides:
            a = usable[sl["asset_id"]]
            lm = (a.get("legendes_montage") or [{}])[0]
            sl["titre"] = sl.get("titre") or lm.get("titre") or a.get("titre_court", "")
            sl["sous_titre"] = sl.get("sous_titre") or lm.get("sous_titre", "")
    elif tpl not in ("duo", "video"):
        ids, slides = ids[:1], []

    first = usable.get(ids[0]) if ids else None
    lm = ((first or {}).get("legendes_montage") or [{}])[0]
    badge = spec.get("badge") or str((first or {}).get("module") or "").replace("_", " ")
    if badge.lower() in ("autre", "marque"):
        badge = ""
    points = [str(p)[:70] for p in (spec.get("points") or []) if p][:4] or [str(p)[:70] for p in ((first or {}).get("fonctionnalites_visibles") or [])[:4]]
    return {"template": tpl, "asset_ids": ids,
            "titre_carte": (spec.get("titre_carte") or lm.get("titre") or (first or {}).get("titre_court") or "")[:90],
            "sous_titre": (spec.get("sous_titre") or lm.get("sous_titre") or "")[:140],
            "badge": badge[:24], "unsplash_query": uq[:80], "slides": slides, "ratio": spec.get("ratio"),
            "points": points, "style": spec.get("style")}

