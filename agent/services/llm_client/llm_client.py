import json
import os
import re
import time

import httpx

from agent.services.llm_client import llm_usage as U


def _extract_json(text: str):
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S)
    text = re.sub(r"```(?:json)?", "", text).strip()
    a = text.find("{")
    if a < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[a:])
        return obj if isinstance(obj, dict) else None
    except ValueError:
        b = text.rfind("}")
        if b > a:
            try:
                return json.loads(text[a:b + 1])
            except ValueError:
                return None
    return None


class LLMClient:
    """Texte : pool de clés (rotation auto), budgets, journal de consommation réelle."""

    def _call(self, messages, temperature, max_tokens, json_mode, retries):
        base = (os.getenv("LLM_BASE_URL") or "https://api.groq.com/openai/v1").rstrip("/")
        model = U.model_for("texte")
        payload = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        U.check_budget()
        tried: set = set()
        last, attempt = "", 0
        while True:
            kid, key = U.pick_key("texte", tried)
            if not key:
                raise U.KeysUnavailable("Aucune clé IA disponible (épuisées, invalides, expirées ou absentes). "
                                        "Ajoute une clé dans Paramètres. Dernière erreur : " + (last or "aucune"))
            t0 = time.time()
            try:
                r = httpx.post(f"{base}/chat/completions", json=payload, timeout=120,
                               headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
            except httpx.HTTPError as e:
                last = str(e)
                U.record("texte", kid, model, 0, 0, False, 0, int((time.time() - t0) * 1000), last)
                attempt += 1
                if attempt > retries:
                    break
                time.sleep(4 * attempt)
                continue
            ms = int((time.time() - t0) * 1000)
            U.note_headers(kid, r.headers)
            if r.status_code == 200:
                data = r.json()
                u = data.get("usage") or {}
                U.record("texte", kid, model, u.get("prompt_tokens", 0), u.get("completion_tokens", 0), True, 200, ms)
                return data["choices"][0]["message"].get("content") or ""
            last = f"{r.status_code} {r.text[:300]}"
            U.record("texte", kid, model, 0, 0, False, r.status_code, ms, last)
            if r.status_code == 400 and "response_format" in payload:
                payload.pop("response_format", None)
                continue
            cls = U.classify_error(r.status_code, r.text, r.headers)
            if cls == "invalid":
                U.mark_key(kid, "invalide", last)
                tried.add(kid)
                continue
            if cls == "exhausted":
                U.mark_key(kid, "epuise", last, U.reset_seconds(r.headers))
                tried.add(kid)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                attempt += 1
                if attempt > retries:
                    break
                time.sleep(min(U.retry_after(r.headers) or 8 * attempt, 40))
                continue
            break
        raise RuntimeError(f"LLM indisponible : {last}")

    def chat_json(self, user_message: str, system_prompt: str = "", temperature: float = 0.3,
                  max_tokens: int = 2000, retries: int = 2) -> dict:
        msgs = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + \
               [{"role": "user", "content": user_message}]
        text = self._call(msgs, temperature, max_tokens, True, retries)
        obj = _extract_json(text)
        return obj if obj is not None else {"erreur": "JSON illisible", "raw": text}