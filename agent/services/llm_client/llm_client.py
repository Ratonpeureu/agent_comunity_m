import json
import os
import re
import time

import httpx


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
    def __init__(self):
        self.key = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_KEY_FACTURE")
        self.base = (os.getenv("LLM_BASE_URL") or "https://api.groq.com/openai/v1").rstrip("/")
        self.model = os.getenv("LLM_MODEL") or os.getenv("GROQ_MODEL_FACTURE") or "llama-3.3-70b-versatile"

    def _call(self, messages, temperature, max_tokens, json_mode, retries):
        if not self.key:
            raise RuntimeError("Clé IA manquante : renseigne GROQ_API_KEY dans les Réglages.")
        payload = {"model": self.model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        last = ""
        for attempt in range(retries + 1):
            try:
                r = httpx.post(f"{self.base}/chat/completions", json=payload, timeout=120,
                               headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
            except httpx.HTTPError as e:
                last = str(e)
                time.sleep(4 * (attempt + 1))
                continue
            if r.status_code == 200:
                return r.json()["choices"][0]["message"].get("content") or ""
            last = f"{r.status_code} {r.text[:300]}"
            if r.status_code == 400 and "response_format" in payload:
                payload.pop("response_format", None)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                wait = float(r.headers.get("retry-after") or 8 * (attempt + 1))
                time.sleep(min(wait, 40))
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