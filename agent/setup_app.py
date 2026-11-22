"""Premier démarrage uniquement. Une fois l'app configurée, tout se gère dans Paramètres › Configuration."""
import asyncio
import html
import os
import secrets
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from agent.bootstrap import hash_password, is_configured, read_config, write_config

router = APIRouter()
SETTINGS_URL = "/social-agent/settings?tab=config"

CSS = """
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:radial-gradient(1200px 600px at 10% -10%,#e0e7ff 0,transparent 60%),radial-gradient(900px 500px at 100% 0,#fce7f3 0,transparent 55%),#f6f7fb;
color:#12151c;font:14px/1.55 Inter,-apple-system,'Segoe UI',Roboto,sans-serif;-webkit-font-smoothing:antialiased}
.wrap{max-width:560px;margin:0 auto;padding:48px 20px 64px}
.logo{width:44px;height:44px;border-radius:12px;background:#12151c;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:20px;margin-bottom:18px}
h1{font-size:26px;letter-spacing:-.5px;margin:0 0 6px}
p.lead{color:#5b6475;margin:0 0 26px}
.card{background:#fff;border:1px solid #e6e8ee;border-radius:16px;padding:22px;margin-bottom:16px;box-shadow:0 1px 2px rgba(16,24,40,.04),0 12px 32px rgba(16,24,40,.05)}
.card h2{font-size:12px;letter-spacing:.07em;text-transform:uppercase;color:#667085;margin:0 0 14px}
label{display:block;font-weight:600;font-size:12.5px;color:#2b3242;margin-bottom:14px}
label:last-child{margin-bottom:0}
label small{display:block;font-weight:400;color:#7a8396;margin-top:2px}
input{width:100%;margin-top:6px;border:1px solid #d5d9e2;border-radius:10px;padding:10px 12px;font:inherit;background:#fff;transition:.15s}
input:focus{outline:0;border-color:#12151c;box-shadow:0 0 0 3px rgba(18,21,28,.08)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media(max-width:560px){.row{grid-template-columns:1fr}}
.pw{position:relative}
.pw button{position:absolute;right:8px;top:14px;border:0;background:#eef0f5;color:#344054;border-radius:7px;padding:4px 9px;font-size:12px;font-weight:600;cursor:pointer;width:auto}
button.go{width:100%;background:#12151c;color:#fff;border:0;border-radius:12px;padding:13px;font-weight:700;font-size:15px;cursor:pointer;transition:.15s}
button.go:hover{background:#2b3242}
button.go:disabled{opacity:.6;cursor:wait}
.err{background:#fef2f2;color:#b91c1c;border:1px solid #fecaca;border-radius:12px;padding:11px 14px;margin-bottom:16px;font-weight:600}
.ok{background:#f0fdf4;color:#166534;border:1px solid #bbf7d0;border-radius:12px;padding:12px 14px}
.hint{color:#667085;font-size:12.5px;text-align:center;margin-top:14px}
.spin{width:34px;height:34px;border:3px solid #d5d9e2;border-top-color:#12151c;border-radius:50%;animation:s .8s linear infinite;margin:6px auto 18px}
@keyframes s{to{transform:rotate(360deg)}}
"""

JS = """
var f=document.getElementById('f'),b=document.getElementById('go'),e=document.getElementById('err');
document.querySelectorAll('[data-eye]').forEach(function(x){x.addEventListener('click',function(){
  var i=document.getElementById(x.dataset.eye);i.type=i.type==='password'?'text':'password';x.textContent=i.type==='password'?'Afficher':'Masquer';});});
f.addEventListener('submit',function(ev){
  if(f.elements['ADMIN_PASSWORD'].value!==f.elements['CONFIRM'].value){ev.preventDefault();e.textContent='Les deux mots de passe ne correspondent pas.';e.hidden=false;return;}
  b.disabled=true;b.textContent='Enregistrement…';});
"""


def _page(body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse("<!doctype html><html lang='fr'><head><meta charset='utf-8'>"
                        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                        f"<title>Agent Social : configuration</title><style>{CSS}</style></head>"
                        f"<body><div class='wrap'>{body}</div></body></html>", status)


def _form(v: dict, error: str = "") -> HTMLResponse:
    def val(k, d=""):
        return html.escape(str(v.get(k) or d))
    e = f"<div class='err'>{html.escape(error)}</div>" if error else ""
    body = f"""<div class='logo'>S</div><h1>Bienvenue sur Agent Social</h1>
<p class='lead'>Quelques informations pour démarrer. Tout le reste (réseaux, budgets, clés supplémentaires, modèles…) se règle ensuite dans <b>Paramètres › Configuration</b>.</p>
{e}<div class='err' id='err' hidden></div>
<form id='f' method='post' action='/setup'>
<div class='card'><h2>Compte administrateur</h2>
<label>Identifiant<input name='ADMIN_USERNAME' value='{val("ADMIN_USERNAME", "admin")}' required minlength='3' autocomplete='username'></label>
<div class='row'>
<label class='pw'>Mot de passe<small>8 caractères minimum</small><input id='p1' type='password' name='ADMIN_PASSWORD' required minlength='8' autocomplete='new-password'><button type='button' data-eye='p1'>Afficher</button></label>
<label class='pw'>Confirmation<small>&nbsp;</small><input id='p2' type='password' name='CONFIRM' required minlength='8' autocomplete='new-password'><button type='button' data-eye='p2'>Afficher</button></label>
</div></div>
<div class='card'><h2>Application</h2>
<label>URL publique<small>Adresse HTTPS d'accès à l'application, utilisée pour les liens des médias que les réseaux téléchargent.</small>
<input name='PUBLIC_BASE_URL' value='{val("PUBLIC_BASE_URL")}' placeholder='https://mon-domaine.com' required></label>
<div class='row'>
<label>Nom de la marque<input name='SOCIAL_BRAND_NAME' value='{val("SOCIAL_BRAND_NAME")}'></label>
<label>Site de la marque<input name='SOCIAL_BRAND_SITE' value='{val("SOCIAL_BRAND_SITE")}' placeholder='https://…'></label>
</div></div>
<div class='card'><h2>Intelligence artificielle</h2>
<label>Clé API Groq<small>Optionnelle ici : tu pourras ajouter plusieurs clés avec bascule automatique dans Paramètres › Clés API. Clé à créer sur console.groq.com.</small>
<input name='GROQ_API_KEY' type='password' autocomplete='off' placeholder='gsk_…'></label></div>
<button class='go' id='go'>Enregistrer et démarrer</button>
<p class='hint'>L'application redémarre automatiquement après l'enregistrement.</p>
</form><script>{JS}</script>"""
    return _page(body, 422 if error else 200)


def _waiting() -> HTMLResponse:
    return _page("<div class='logo'>S</div><div class='card' style='text-align:center'><div class='spin'></div>"
                 "<h1 style='font-size:20px'>Configuration enregistrée</h1>"
                 "<p class='lead' style='margin:0'>Redémarrage en cours, cette page se rechargera automatiquement.</p></div>"
                 "<script>(function p(){setTimeout(function(){fetch('/health').then(function(r){return r.json()})"
                 ".then(function(j){if(j.configured){location.href='/'}else{p()}}).catch(p)},1500)})()</script>")


@router.get("/setup")
async def setup_get(request: Request):
    if is_configured():
        return RedirectResponse(SETTINGS_URL)
    cfg = read_config()
    cfg.setdefault("PUBLIC_BASE_URL", str(request.base_url).rstrip("/"))
    return _form(cfg)


@router.post("/setup")
async def setup_post(request: Request):
    if is_configured():
        return _page("<div class='logo'>S</div><h1>Déjà configurée</h1>"
                     f"<p class='lead'>Utilise <a href='{SETTINGS_URL}'>Paramètres › Configuration</a>.</p>", 403)
    form = await request.form()
    keys = ("ADMIN_USERNAME", "PUBLIC_BASE_URL", "SOCIAL_BRAND_NAME", "SOCIAL_BRAND_SITE", "GROQ_API_KEY")
    v = {k: str(form.get(k, "")).strip() for k in keys}
    pw, conf = str(form.get("ADMIN_PASSWORD", "")), str(form.get("CONFIRM", ""))
    url = v["PUBLIC_BASE_URL"].rstrip("/")
    u = urlparse(url)
    if len(v["ADMIN_USERNAME"] or "admin") < 3:
        return _form(v, "Identifiant trop court (3 caractères minimum).")
    if len(pw) < 8:
        return _form(v, "Le mot de passe doit contenir au moins 8 caractères.")
    if pw != conf:
        return _form(v, "Les deux mots de passe ne correspondent pas.")
    if u.scheme not in ("http", "https") or not u.netloc:
        return _form(v, "URL publique invalide (https://mon-domaine.com).")
    cfg = read_config()
    cfg.update({"ADMIN_USERNAME": v["ADMIN_USERNAME"] or "admin", "PUBLIC_BASE_URL": url,
                "ADMIN_PASSWORD_HASH": await asyncio.to_thread(hash_password, pw)})
    for k in ("SOCIAL_BRAND_NAME", "SOCIAL_BRAND_SITE", "GROQ_API_KEY"):
        if v[k]:
            cfg[k] = v[k]
    cfg.setdefault("SOCIAL_FERNET_KEY", Fernet.generate_key().decode())
    cfg.setdefault("ADMIN_JWT_SECRET_KEY", secrets.token_hex(32))
    write_config(cfg)
    asyncio.get_running_loop().call_later(1.5, os._exit, 0)
    return _waiting()