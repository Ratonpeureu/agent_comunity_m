"""Page /setup : configuration complète au premier démarrage (et ensuite, protégée par le mot de passe admin)."""
import asyncio
import html
import os

from cryptography.fernet import Fernet
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
import secrets

from agent.bootstrap import hash_password, is_configured, read_config, verify_password, write_config

router = APIRouter()

# (clé, libellé, secret ?, aide)
SECTIONS = [
    ("Application", "Adresse publique et réseau.", [
        ("PUBLIC_BASE_URL", "URL publique (https://...) *", False, "Utilisée pour les liens des médias que les réseaux téléchargent. Doit être joignable depuis Internet."),
        ("SOCIAL_OAUTH_REDIRECT_BASE", "Base des retours OAuth", False, "Vide = identique à l'URL publique."),
        ("PORT", "Port interne", False, "Doit correspondre au mapping du docker-compose. Défaut 8080."),
        ("SOCIAL_TZ", "Fuseau horaire", False, "Ex : Africa/Dakar"),
    ]),
    ("Marque", "Identité de la marque gérée.", [
        ("SOCIAL_BRAND_SLUG", "Identifiant (slug)", False, "Ex : ma-marque"),
        ("SOCIAL_BRAND_NAME", "Nom affiché", False, ""),
        ("SOCIAL_BRAND_SITE", "Site web de la marque", False, "https://..."),
        ("SOCIAL_FICHE_TECHNIQUE", "Chemin de la fiche technique (YAML)", False, "Défaut : /data/fiche_technique.yaml"),
    ]),
    ("Intelligence artificielle", "Rédaction, analyse et vision.", [
        ("GROQ_API_KEY", "Clé Groq (texte)", True, "console.groq.com"),
        ("GROQ_API_KEY_FACTURE", "Clé Groq (vision) : vide = clé ci-dessus", True, ""),
        ("LLM_BASE_URL", "URL de l'API LLM compatible OpenAI", False, "Défaut : https://api.groq.com/openai/v1"),
        ("LLM_MODEL", "Modèle texte", False, "Défaut : llama-3.3-70b-versatile"),
        ("GROQ_VISION_MODEL", "Modèle vision", False, "Analyse des captures"),
        ("SERPER_API_KEY", "Clé Serper (actualités)", True, "Optionnel"),
        ("POLLINATIONS_API_KEY", "Clé Pollinations", True, "Optionnel"),
    ]),
    ("Médias", "Photos libres et voix.", [
        ("UNSPLASH_ACCESS_KEY", "Unsplash : Access Key", True, "Optionnel"),
        ("UNSPLASH_APP_NAME", "Unsplash : nom de l'app", False, ""),
        ("PEXELS_API_KEY", "Pexels : clé", True, "Optionnel"),
        ("SOCIAL_VOICE", "Voix off (edge-tts)", False, "Défaut : fr-FR-DeniseNeural"),
        ("SOCIAL_FONT_BOLD", "Police grasse (chemin)", False, "Optionnel"),
        ("SOCIAL_FONT_REGULAR", "Police normale (chemin)", False, "Optionnel"),
    ]),
    ("Publication via QPost (TikTok, Instagram)", "Méthode la plus simple pour TikTok.", [
        ("QPOST_API_KEY", "Clé API QPost", True, "qpost.dev > API Keys"),
        ("QPOST_BASE_URL", "URL QPost", False, "Défaut : https://qpost.dev"),
        ("QPOST_TIKTOK_PRIVACY", "Visibilité TikTok", False, "PUBLIC_TO_EVERYONE, SELF_ONLY..."),
    ]),
    ("OAuth (optionnel : la connexion manuelle par jeton est recommandée)", "À remplir seulement si vous voulez les boutons « Connecter ».", [
        ("META_APP_ID", "Meta : App ID", False, ""),
        ("META_APP_SECRET", "Meta : App Secret", True, ""),
        ("META_GRAPH_VERSION", "Meta : version Graph", False, "Ex : v24.0"),
        ("META_PAGE_ID", "Meta : ID de Page imposé", False, ""),
        ("META_SCOPES", "Meta : scopes", False, "pages_show_list,pages_manage_posts,pages_read_engagement,business_management"),
        ("INSTAGRAM_APP_ID", "Instagram : App ID", False, ""),
        ("INSTAGRAM_APP_SECRET", "Instagram : App Secret", True, ""),
        ("INSTAGRAM_SCOPES", "Instagram : scopes", False, "instagram_business_basic,instagram_business_content_publish"),
        ("LINKEDIN_CLIENT_ID", "LinkedIn : Client ID", False, ""),
        ("LINKEDIN_CLIENT_SECRET", "LinkedIn : Client Secret", True, ""),
        ("LINKEDIN_VERSION", "LinkedIn : version API (AAAAMM)", False, ""),
        ("LINKEDIN_SCOPES", "LinkedIn : scopes", False, "openid profile w_member_social"),
        ("LINKEDIN_ORG_ID", "LinkedIn : ID de Page", False, "Optionnel"),
        ("X_CLIENT_ID", "X : Client ID", False, ""),
        ("X_CLIENT_SECRET", "X : Client Secret", True, ""),
        ("X_SCOPES", "X : scopes", False, "tweet.read tweet.write users.read media.write offline.access"),
        ("TIKTOK_CLIENT_KEY", "TikTok : Client Key", False, ""),
        ("TIKTOK_CLIENT_SECRET", "TikTok : Client Secret", True, ""),
        ("TIKTOK_SCOPES", "TikTok : scopes", False, "user.info.basic,video.publish,video.upload"),
    ]),
]
ALL_KEYS = [k for _, _, fields in SECTIONS for k, *_ in fields]
SECRET_KEYS = {k for _, _, fields in SECTIONS for k, _, s, _ in fields if s}

CSS = """
*{box-sizing:border-box}body{margin:0;background:#f6f7f9;color:#12151c;font:14px/1.5 -apple-system,'Segoe UI',Roboto,Inter,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:40px 20px 120px}
h1{font-size:22px;margin:0 0 4px;letter-spacing:-.3px}p.lead{color:#5b6475;margin:0 0 28px}
.card{background:#fff;border:1px solid #e3e6ec;border-radius:12px;padding:22px;margin-bottom:18px}
.card h2{font-size:15px;margin:0 0 2px}.card p.d{color:#5b6475;margin:0 0 16px;font-size:13px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}@media(max-width:700px){.grid{grid-template-columns:1fr}}
label{display:flex;flex-direction:column;gap:5px;font-weight:600;font-size:12.5px;color:#2b3242}
label small{font-weight:400;color:#7a8396}
input{border:1px solid #d5d9e2;border-radius:8px;padding:9px 11px;font:inherit;background:#fff}
input:focus{outline:2px solid #c7d2fe;border-color:#4f46e5}
.bar{position:fixed;left:0;right:0;bottom:0;background:#fff;border-top:1px solid #e3e6ec;padding:14px 20px;display:flex;justify-content:center}
button{background:#12151c;color:#fff;border:0;border-radius:8px;padding:11px 22px;font-weight:600;font-size:14px;cursor:pointer}
.err{background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;border-radius:8px;padding:10px 14px;margin-bottom:16px}
.ok{background:#f0fdf4;color:#166534;border:1px solid #bbf7d0;border-radius:8px;padding:10px 14px}
details summary{cursor:pointer;font-weight:600}
"""


def _page(body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><html lang='fr'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
                        f"<title>Configuration</title><style>{CSS}</style></head><body><div class='wrap'>{body}</div></body></html>", status)


def _gate(error: str = "") -> HTMLResponse:
    e = f"<div class='err'>{html.escape(error)}</div>" if error else ""
    return _page(f"<h1>Configuration</h1><p class='lead'>Saisissez le mot de passe administrateur pour modifier la configuration.</p>{e}"
                 "<form method='post' action='/setup' class='card'><input type='hidden' name='action' value='unlock'>"
                 "<label>Mot de passe<input type='password' name='current_password' required autofocus></label>"
                 "<div style='margin-top:14px'><button>Continuer</button></div></form>", 401 if error else 200)


def _form(cfg: dict, configured: bool, current_pw: str = "", error: str = "") -> HTMLResponse:
    e = f"<div class='err'>{html.escape(error)}</div>" if error else ""
    cur = f"<input type='hidden' name='current_password' value='{html.escape(current_pw)}'>" if configured else ""
    parts = [f"<h1>{'Configuration' if configured else 'Premier démarrage'}</h1>",
             "<p class='lead'>Renseignez les valeurs puis enregistrez. L'application redémarre automatiquement. "
             "Les clés secrètes déjà enregistrées ne sont pas réaffichées : laissez le champ vide pour les conserver. "
             "Les prompts de rédaction se modifient ensuite dans l'onglet « Prompts » de l'interface.</p>", e,
             f"<form method='post' action='/setup'><input type='hidden' name='action' value='save'>{cur}"]
    u = html.escape(cfg.get("ADMIN_USERNAME", "admin"))
    parts.append("<div class='card'><h2>Compte administrateur</h2><p class='d'>Identifiants de connexion à l'interface.</p><div class='grid'>"
                 f"<label>Identifiant<input name='ADMIN_USERNAME' value='{u}' required></label>"
                 f"<label>Mot de passe {'(vide = inchangé)' if configured else '*'}<small>8 caractères minimum</small>"
                 f"<input type='password' name='ADMIN_PASSWORD' {'' if configured else 'required'} autocomplete='new-password'></label></div></div>")
    for title, desc, fields in SECTIONS:
        inner = []
        for k, label, secret, hint in fields:
            val = cfg.get(k, "")
            if secret:
                ph = "défini, laisser vide pour conserver" if val else ""
                inner.append(f"<label>{html.escape(label)}<small>{html.escape(hint)}</small><input type='password' name='{k}' placeholder='{ph}' autocomplete='off'></label>")
            else:
                inner.append(f"<label>{html.escape(label)}<small>{html.escape(hint)}</small><input name='{k}' value='{html.escape(str(val))}'></label>")
        opened = "open" if title in ("Application", "Marque", "Intelligence artificielle") else ""
        parts.append(f"<div class='card'><details {opened}><summary>{html.escape(title)}</summary><p class='d' style='margin-top:6px'>{html.escape(desc)}</p><div class='grid'>{''.join(inner)}</div></details></div>")
    parts.append("<div class='bar'><button>Enregistrer et redémarrer</button></div></form>")
    return _page("".join(parts))


@router.get("/setup")
async def setup_get():
    if is_configured():
        return _gate()
    return _form(read_config(), False)


@router.post("/setup")
async def setup_post(request: Request):
    form = await request.form()
    cfg = read_config()
    configured = is_configured()
    pw_cur = str(form.get("current_password", ""))
    if configured:
        if not verify_password(pw_cur, cfg.get("ADMIN_PASSWORD_HASH", "")):
            return _gate("Mot de passe incorrect")
        if form.get("action") == "unlock":
            return _form(cfg, True, pw_cur)

    new_pw = str(form.get("ADMIN_PASSWORD", ""))
    if new_pw:
        if len(new_pw) < 8:
            return _form(cfg, configured, pw_cur, "Le mot de passe doit contenir au moins 8 caractères.")
        cfg["ADMIN_PASSWORD_HASH"] = hash_password(new_pw)
    cfg["ADMIN_USERNAME"] = str(form.get("ADMIN_USERNAME", "admin")).strip() or "admin"

    for k in ALL_KEYS:
        v = str(form.get(k, "")).strip()
        if k in SECRET_KEYS and not v:
            continue                      # secret laissé vide = conservé
        if v:
            cfg[k] = v
        else:
            cfg.pop(k, None)

    cfg["PUBLIC_BASE_URL"] = str(cfg.get("PUBLIC_BASE_URL", "")).rstrip("/")
    if not cfg.get("ADMIN_PASSWORD_HASH"):
        return _form(cfg, configured, pw_cur, "Un mot de passe administrateur est obligatoire.")
    if not cfg.get("PUBLIC_BASE_URL"):
        return _form(cfg, configured, pw_cur, "L'URL publique est obligatoire.")
    cfg.setdefault("SOCIAL_FERNET_KEY", Fernet.generate_key().decode())
    cfg.setdefault("ADMIN_JWT_SECRET_KEY", secrets.token_hex(32))
    write_config(cfg)

    asyncio.get_running_loop().call_later(1.5, os._exit, 0)     # Docker (restart: unless-stopped) relance avec la nouvelle config
    return _page("<h1>Configuration enregistrée</h1><div class='ok'>Redémarrage en cours. Cette page se rechargera automatiquement.</div>"
                 "<script>(function p(){setTimeout(function(){fetch('/health').then(function(r){return r.json()})"
                 ".then(function(j){if(j.configured){location.href='/'}else{p()}}).catch(p)},1500)})()</script>")