"""Suivi réel de la consommation IA (Groq / compatible OpenAI), budgets et pool de clés avec rotation."""
import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
DB_PATH = DATA_DIR / "social.db"
STORE = DATA_DIR / "ai_settings.json"
_lock = threading.RLock()
_ready = False
_RL: dict = {}        # dernières limites Groq mesurées, par clé
_ENV_BAD: dict = {}   # clés du /setup temporairement écartées (timestamp de fin)
_ENV_ERR: dict = {}

DEFAULTS = {
    "keys": [],
    "budget": {"tokens_jour": 0, "tokens_mois": 0, "requetes_jour": 0, "cout_mois_usd": 0.0,
               "bloquer": True, "alerte_pct": 80},
    "prix": {"llama-3.3-70b-versatile": {"in": 0.59, "out": 0.79}},     # $ par million de tokens, éditable
    "modeles": {"texte": "", "vision": ""},
    "retention_jours": 90,
}


class BudgetExceeded(RuntimeError):
    pass


class KeysUnavailable(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _n(x) -> str:
    return f"{int(x):,}".replace(",", " ")


def _base() -> str:
    return (os.getenv("LLM_BASE_URL") or "https://api.groq.com/openai/v1").rstrip("/")


# ═════════════ Base SQLite (synchrone, même fichier que l'app) ═════════════
def _conn():
    global _ready
    c = sqlite3.connect(str(DB_PATH), timeout=30)
    c.execute("PRAGMA busy_timeout=30000")
    if not _ready:
        with _lock:
            if not _ready:
                DATA_DIR.mkdir(parents=True, exist_ok=True)
                c.execute("""CREATE TABLE IF NOT EXISTS llm_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, day TEXT, month TEXT, key_id TEXT, model TEXT,
                    kind TEXT, prompt_tokens INTEGER DEFAULT 0, completion_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0, ok INTEGER DEFAULT 1, status INTEGER DEFAULT 200,
                    ms INTEGER DEFAULT 0, error TEXT)""")
                c.execute("CREATE INDEX IF NOT EXISTS ix_llm_usage_day ON llm_usage(day)")
                c.execute("CREATE INDEX IF NOT EXISTS ix_llm_usage_month ON llm_usage(month)")
                c.commit()
                _ready = True
    return c


def _q(sql, args=()):
    with closing(_conn()) as c:
        return c.execute(sql, args).fetchall()


def _x(sql, args=()):
    with closing(_conn()) as c:
        c.execute(sql, args)
        c.commit()


# ═════════════ Réglages (fichier JSON, clés chiffrées Fernet) ═════════════
def load() -> dict:
    with _lock:
        try:
            raw = json.loads(STORE.read_text("utf-8"))
        except Exception:
            raw = {}
    out = json.loads(json.dumps(DEFAULTS))
    out["keys"] = raw.get("keys") or []
    for s in ("budget", "modeles"):
        out[s].update(raw.get(s) or {})
    if isinstance(raw.get("prix"), dict):
        out["prix"] = raw["prix"]
    out["retention_jours"] = int(raw.get("retention_jours") or 90)
    return out


def save(d: dict):
    with _lock:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STORE.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False, indent=2), "utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        tmp.replace(STORE)


def _fernet():
    from cryptography.fernet import Fernet
    k = os.getenv("SOCIAL_FERNET_KEY")
    if not k:
        raise RuntimeError("SOCIAL_FERNET_KEY non configurée")
    return Fernet(k.encode())


def _dec(k: dict):
    try:
        return _fernet().decrypt(k["enc"].encode()).decode()
    except Exception:
        return None


def _date(v):
    v = (v or "").strip() if isinstance(v, str) else v
    if not v:
        return None
    try:
        datetime.strptime(v, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Date invalide (format AAAA-MM-JJ)")
    return v


def _pub(k: dict) -> dict:
    return {"id": k["id"], "label": k.get("label", ""), "last4": k.get("last4", ""), "statut": k.get("statut", "actif"),
            "expire_le": k.get("expire_le"), "reset_at": k.get("reset_at"), "erreur": k.get("erreur"),
            "source": "pool", "rl": _RL.get(k["id"])}


def _refresh(d: dict) -> bool:
    ch, now = False, _now()
    today = now.strftime("%Y-%m-%d")
    for k in d["keys"]:
        if k.get("statut") == "epuise" and k.get("reset_at"):
            try:
                if now >= datetime.fromisoformat(k["reset_at"]):
                    k["statut"], k["erreur"], k["reset_at"], ch = "actif", None, None, True
            except ValueError:
                pass
        if k.get("expire_le") and k["expire_le"] < today and k.get("statut") in ("actif", "epuise"):
            k["statut"], k["erreur"], ch = "expire", "Date d'expiration dépassée", True
    return ch


# ═════════════ Clés ═════════════
def _env(kind: str):
    g = os.getenv
    if kind == "vision":
        v = g("GROQ_API_KEY_FACTURE")
        if v:
            return "env_vision", v
        v = g("GROQ_API_KEY")
        return ("env", v) if v else (None, None)
    v = g("LLM_API_KEY") or g("GROQ_API_KEY") or g("GROQ_API_KEY_FACTURE")
    return ("env", v) if v else (None, None)


def env_keys() -> list:
    out, seen = [], set()
    for kind in ("texte", "vision"):
        kid, s = _env(kind)
        if s and kid not in seen:
            seen.add(kid)
            bad = _ENV_BAD.get(kid, 0) > time.time()
            out.append({"id": kid, "label": "Clé de configuration" + (" (vision)" if kid == "env_vision" else ""),
                        "last4": s[-4:], "statut": "invalide" if bad else "actif", "expire_le": None, "reset_at": None,
                        "erreur": _ENV_ERR.get(kid) if bad else None, "source": "setup", "rl": _RL.get(kid)})
    return out


def pick_key(kind: str = "texte", exclude=()):
    with _lock:
        d = load()
        if _refresh(d):
            save(d)
        for k in d["keys"]:
            if k["id"] in exclude or k.get("statut") != "actif":
                continue
            s = _dec(k)
            if s:
                return k["id"], s
    kid, s = _env(kind)
    if s and kid not in exclude and _ENV_BAD.get(kid, 0) < time.time():
        return kid, s
    return None, None


def secret_of(kid: str):
    if kid in ("env", "env_vision"):
        return _env("vision" if kid == "env_vision" else "texte")[1]
    for k in load()["keys"]:
        if k["id"] == kid:
            return _dec(k)
    return None


def mark_key(kid: str, statut: str, err: str = "", reset_s=None):
    if kid.startswith("env"):
        _ENV_BAD[kid] = time.time() + (reset_s or (31536000 if statut == "invalide" else 3600))
        _ENV_ERR[kid] = (err or "")[:300]
        return
    with _lock:
        d = load()
        for k in d["keys"]:
            if k["id"] == kid:
                k["statut"], k["erreur"] = statut, (err or "")[:300]
                k["reset_at"] = (_now() + timedelta(seconds=reset_s or 3600)).isoformat(timespec="seconds") if statut == "epuise" else None
        save(d)


def add_key(label: str, secret: str, expire_le=None) -> dict:
    secret = (secret or "").strip()
    if len(secret) < 20:
        raise ValueError("Clé trop courte")
    with _lock:
        d = load()
        if any(_dec(k) == secret for k in d["keys"]):
            raise ValueError("Cette clé est déjà enregistrée")
        k = {"id": uuid.uuid4().hex[:10], "label": (label or "").strip() or f"Clé …{secret[-4:]}",
             "enc": _fernet().encrypt(secret.encode()).decode(), "last4": secret[-4:], "statut": "actif",
             "expire_le": _date(expire_le), "reset_at": None, "erreur": None,
             "cree_le": _now().isoformat(timespec="seconds")}
        d["keys"].append(k)
        save(d)
        return _pub(k)


def patch_key(kid: str, f: dict) -> dict:
    with _lock:
        d = load()
        today = _now().strftime("%Y-%m-%d")
        for k in d["keys"]:
            if k["id"] != kid:
                continue
            if "label" in f and (f["label"] or "").strip():
                k["label"] = f["label"].strip()
            if "expire_le" in f:
                k["expire_le"] = _date(f["expire_le"])
                if k.get("statut") == "expire" and (not k["expire_le"] or k["expire_le"] >= today):
                    k["statut"], k["erreur"] = "actif", None
            if f.get("statut") in ("actif", "desactive"):
                k["statut"] = f["statut"]
                if f["statut"] == "actif":
                    k["erreur"], k["reset_at"] = None, None
            save(d)
            return _pub(k)
    raise KeyError("Clé introuvable")


def del_key(kid: str):
    with _lock:
        d = load()
        d["keys"] = [k for k in d["keys"] if k["id"] != kid]
        save(d)


def model_for(kind: str, default=None) -> str:
    m = (load()["modeles"].get(kind) or "").strip()
    if m:
        return m
    if kind == "texte":
        return os.getenv("LLM_MODEL") or os.getenv("GROQ_MODEL_FACTURE") or "llama-3.3-70b-versatile"
    return default or os.getenv("GROQ_VISION_MODEL") or ""


# ═════════════ Erreurs, en-têtes, enregistrement ═════════════
def classify_error(status: int, text: str = "", headers=None) -> str:
    t = (text or "").lower()
    if status in (401, 403):
        return "invalid"
    if status == 402:
        return "exhausted"
    if status == 429 and any(x in t for x in ("per day", "(tpd)", "(rpd)", "quota", "billing", "insufficient")):
        return "exhausted"
    return "transient"


def retry_after(headers) -> float:
    try:
        return float((headers or {}).get("retry-after") or 0)
    except (TypeError, ValueError):
        return 0.0


def reset_seconds(headers) -> int:
    return int(min(86400, max(60, retry_after(headers) or 3600)))


def rl_of(h) -> dict:
    names = ("limit-requests", "limit-tokens", "remaining-requests", "remaining-tokens", "reset-requests", "reset-tokens")
    rl = {n.replace("-", "_"): h.get("x-ratelimit-" + n) for n in names}
    if any(rl.values()):
        rl["ts"] = int(time.time())
    return rl


def note_headers(kid: str, h):
    rl = rl_of(h)
    if rl.get("ts"):
        _RL[kid] = rl


def record(kind, kid, model, pt=0, ct=0, ok=True, status=200, ms=0, error=""):
    n = _now()
    try:
        _x("INSERT INTO llm_usage(ts,day,month,key_id,model,kind,prompt_tokens,completion_tokens,total_tokens,ok,status,ms,error)"
           " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
           (n.isoformat(timespec="seconds"), n.strftime("%Y-%m-%d"), n.strftime("%Y-%m"), kid, model, kind,
            int(pt or 0), int(ct or 0), int(pt or 0) + int(ct or 0), 1 if ok else 0, int(status), int(ms),
            (error or "")[:300]))
    except Exception:
        pass


def purge(days=None):
    days = days or load()["retention_jours"]
    cut = (_now() - timedelta(days=days)).strftime("%Y-%m-%d")
    _x("DELETE FROM llm_usage WHERE day < ?", (cut,))


# ═════════════ Agrégats & budgets ═════════════
def _cost(col: str, value: str, prix: dict):
    assert col in ("day", "month")
    total, unknown = 0.0, []
    for m, p, c in _q(f"SELECT model,SUM(prompt_tokens),SUM(completion_tokens) FROM llm_usage WHERE {col}=? AND ok=1 GROUP BY model", (value,)):
        if not (p or c):
            continue
        pr = prix.get(m)
        if not pr:
            unknown.append(m)
            continue
        total += (p or 0) * float(pr.get("in", 0)) / 1e6 + (c or 0) * float(pr.get("out", 0)) / 1e6
    return round(total, 4), unknown


def totals(col: str, value: str, prix=None) -> dict:
    assert col in ("day", "month")
    r = _q(f"SELECT COALESCE(SUM(prompt_tokens),0),COALESCE(SUM(completion_tokens),0),COALESCE(SUM(ok),0),COALESCE(SUM(1-ok),0)"
           f" FROM llm_usage WHERE {col}=?", (value,))[0]
    out = {"prompt": r[0], "completion": r[1], "tokens": r[0] + r[1], "requetes": r[2], "erreurs": r[3]}
    if prix is not None:
        out["cout_usd"], out["modeles_sans_prix"] = _cost(col, value, prix)
    return out


def check_budget():
    d = load()
    b = d["budget"]
    if not b.get("bloquer", True):
        return
    now = _now()
    day, month = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")
    lt, lm, lr, lc = (int(b.get("tokens_jour") or 0), int(b.get("tokens_mois") or 0),
                      int(b.get("requetes_jour") or 0), float(b.get("cout_mois_usd") or 0))
    if lt or lr:
        td = totals("day", day)
        if lt and td["tokens"] >= lt:
            raise BudgetExceeded(f"Limite quotidienne de tokens atteinte ({_n(td['tokens'])}/{_n(lt)}). Modifie-la dans Paramètres.")
        if lr and td["requetes"] >= lr:
            raise BudgetExceeded(f"Limite quotidienne de requêtes atteinte ({_n(td['requetes'])}/{_n(lr)}). Modifie-la dans Paramètres.")
    if lm and totals("month", month)["tokens"] >= lm:
        raise BudgetExceeded(f"Limite mensuelle de tokens atteinte (plafond {_n(lm)}). Modifie-la dans Paramètres.")
    if lc and _cost("month", month, d["prix"])[0] >= lc:
        raise BudgetExceeded(f"Budget mensuel atteint ({lc:.2f} $ estimés). Modifie-le dans Paramètres.")


def overview() -> dict:
    d = load()
    if _refresh(d):
        save(d)
    try:
        purge(d["retention_jours"])
    except Exception:
        pass
    now = _now()
    day, month = now.strftime("%Y-%m-%d"), now.strftime("%Y-%m")
    td, tm = totals("day", day), totals("month", month, d["prix"])
    b = d["budget"]
    gauges = {}

    def g(name, used, lim):
        if lim and float(lim) > 0:
            gauges[name] = {"used": used, "limit": lim, "pct": round(used / float(lim) * 100, 1)}
    g("tokens_jour", td["tokens"], b["tokens_jour"])
    g("tokens_mois", tm["tokens"], b["tokens_mois"])
    g("requetes_jour", td["requetes"], b["requetes_jour"])
    g("cout_mois_usd", tm["cout_usd"], b["cout_mois_usd"])

    labels = {k["id"]: k.get("label", k["id"]) for k in d["keys"]}
    labels.update({"env": "Clé de configuration", "env_vision": "Clé de configuration (vision)"})
    since = (now - timedelta(days=29)).strftime("%Y-%m-%d")
    rows = {r[0]: (r[1], r[2]) for r in _q("SELECT day,SUM(total_tokens),SUM(ok) FROM llm_usage WHERE day>=? GROUP BY day", (since,))}
    serie = []
    for i in range(30):
        dd = (now - timedelta(days=29 - i)).strftime("%Y-%m-%d")
        t, r = rows.get(dd, (0, 0))
        serie.append({"jour": dd, "tokens": t or 0, "requetes": r or 0})

    par_modele = []
    for m, r, p, c in _q("SELECT model,SUM(ok),SUM(prompt_tokens),SUM(completion_tokens) FROM llm_usage WHERE month=? GROUP BY model ORDER BY SUM(total_tokens) DESC", (month,)):
        pr = d["prix"].get(m)
        par_modele.append({"modele": m, "requetes": r or 0, "prompt": p or 0, "completion": c or 0, "tokens": (p or 0) + (c or 0),
                           "cout_usd": round((p or 0) * float(pr["in"]) / 1e6 + (c or 0) * float(pr["out"]) / 1e6, 4) if pr else None})
    par_cle = [{"cle": labels.get(k, k), "tokens": t or 0, "requetes": r or 0, "erreurs": e or 0}
               for k, t, r, e in _q("SELECT key_id,SUM(total_tokens),SUM(ok),SUM(1-ok) FROM llm_usage WHERE month=? GROUP BY key_id ORDER BY 2 DESC", (month,))]
    derniers = [{"ts": r[0], "kind": r[1], "modele": r[2], "cle": labels.get(r[3], r[3]), "tokens": r[4], "ok": bool(r[5]),
                 "status": r[6], "ms": r[7], "erreur": r[8]}
                for r in _q("SELECT ts,kind,model,key_id,total_tokens,ok,status,ms,error FROM llm_usage ORDER BY id DESC LIMIT 25")]

    pool, envk = [_pub(k) for k in d["keys"]], env_keys()
    alertes = []
    usable = [k for k in pool + envk if k["statut"] == "actif"]
    if not usable:
        alertes.append({"niveau": "err", "texte": "Aucune clé API utilisable : les appels IA vont échouer. Ajoute ou réactive une clé."})
    seuil = int(b.get("alerte_pct") or 80)
    for name, gg in gauges.items():
        if gg["pct"] >= 100:
            alertes.append({"niveau": "err", "texte": f"Limite atteinte : {name.replace('_', ' ')} ({gg['pct']} %)."
                            + (" Les appels IA sont bloqués." if b.get("bloquer", True) else "")})
        elif gg["pct"] >= seuil:
            alertes.append({"niveau": "warn", "texte": f"{name.replace('_', ' ')} à {gg['pct']} % de la limite."})
    today, in7 = now.strftime("%Y-%m-%d"), (now + timedelta(days=7)).strftime("%Y-%m-%d")
    for k in pool:
        if k["statut"] in ("invalide", "expire", "epuise"):
            alertes.append({"niveau": "warn" if k["statut"] == "epuise" else "err", "texte": f"Clé « {k['label']} » : {k['statut']}. {k.get('erreur') or ''}".strip()})
        elif k["expire_le"] and today <= k["expire_le"] <= in7:
            alertes.append({"niveau": "warn", "texte": f"Clé « {k['label']} » expire le {k['expire_le']}."})
    for k in envk:
        if k["statut"] != "actif":
            alertes.append({"niveau": "err", "texte": f"{k['label']} refusée : {k.get('erreur') or 'invalide'}."})

    return {"budget": b, "prix": d["prix"], "retention_jours": d["retention_jours"],
            "modeles": {**d["modeles"], "texte_effectif": model_for("texte"), "vision_effectif": model_for("vision")},
            "usage": {"jour": td, "mois": tm}, "limites": gauges, "alertes": alertes, "serie": serie,
            "par_modele": par_modele, "par_cle": par_cle, "derniers": derniers, "cles": pool, "env": envk}


def set_settings(budget=None, prix=None, modeles=None, retention=None):
    with _lock:
        d = load()
        if budget is not None:
            b = d["budget"]
            for k in ("tokens_jour", "tokens_mois", "requetes_jour"):
                if k in budget:
                    b[k] = max(0, int(float(budget[k] or 0)))
            if "cout_mois_usd" in budget:
                b["cout_mois_usd"] = max(0.0, float(budget["cout_mois_usd"] or 0))
            if "alerte_pct" in budget:
                b["alerte_pct"] = min(100, max(1, int(float(budget["alerte_pct"] or 80))))
            if "bloquer" in budget:
                b["bloquer"] = bool(budget["bloquer"])
        if prix is not None:
            clean = {}
            for m, v in prix.items():
                m = str(m).strip()
                if m:
                    clean[m] = {"in": max(0.0, float(v.get("in", 0) or 0)), "out": max(0.0, float(v.get("out", 0) or 0))}
            d["prix"] = clean
        if modeles is not None:
            for k in ("texte", "vision"):
                if k in modeles:
                    d["modeles"][k] = str(modeles[k] or "").strip()
        if retention is not None:
            d["retention_jours"] = max(7, min(3650, int(retention)))
        save(d)


# ═════════════ Appels réels vers Groq : test de clé, liste des modèles ═════════════
def _ping(secret: str, kid: str) -> dict:
    model = model_for("texte")
    t0 = time.time()
    try:
        r = httpx.post(f"{_base()}/chat/completions", timeout=30,
                       headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
                       json={"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1})
    except httpx.HTTPError as e:
        return {"ok": False, "status": 0, "ms": int((time.time() - t0) * 1000), "erreur": f"Réseau : {e}", "modele": model, "rl": None}
    ms = int((time.time() - t0) * 1000)
    note_headers(kid, r.headers)
    out = {"ok": r.status_code == 200, "status": r.status_code, "ms": ms, "modele": model, "rl": _RL.get(kid),
           "retry_after": reset_seconds(r.headers)}
    if r.status_code == 200:
        u = (r.json().get("usage") or {})
        record("test", kid, model, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), True, 200, ms)
    else:
        try:
            out["erreur"] = (r.json().get("error") or {}).get("message") or r.text[:300]
        except Exception:
            out["erreur"] = r.text[:300]
        record("test", kid, model, 0, 0, False, r.status_code, ms, out["erreur"])
    return out


def test_key(kid: str) -> dict:
    sec = secret_of(kid)
    if not sec:
        raise KeyError("Clé introuvable")
    res = _ping(sec, kid)
    if res["ok"]:
        if kid.startswith("env"):
            _ENV_BAD.pop(kid, None)
        else:
            with _lock:
                d = load()
                for k in d["keys"]:
                    if k["id"] == kid and k.get("statut") in ("epuise", "invalide"):
                        k["statut"], k["erreur"], k["reset_at"] = "actif", None, None
                save(d)
    else:
        cls = classify_error(res["status"], res.get("erreur", ""))
        if cls == "invalid":
            mark_key(kid, "invalide", res.get("erreur", ""))
        elif cls == "exhausted":
            mark_key(kid, "epuise", res.get("erreur", ""), res.get("retry_after"))
    return res


def list_models() -> list:
    kid, sec = pick_key("texte")
    if not sec:
        raise KeysUnavailable("Aucune clé API disponible")
    r = httpx.get(f"{_base()}/models", headers={"Authorization": f"Bearer {sec}"}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"Groq {r.status_code} : {r.text[:200]}")
    note_headers(kid, r.headers)
    items = [{"id": m.get("id"), "owned_by": m.get("owned_by"), "context_window": m.get("context_window"),
              "active": m.get("active", True)} for m in r.json().get("data", [])]
    return sorted(items, key=lambda x: x["id"] or "")