"""A nyelvi modell: magyaráz és válaszol, de nem dönt és nem számol.

Minden szám, amit a modell kap, a piaci adatból és a naplóból jön; a prompt
megtiltja, hogy mást írjon. Ha a modell nem elérhető, az értesítés attól még
kimegy — a magyarázat elmarad, a kötés adatai nem.

Szolgáltató: LLM_PROVIDER=gemini|openai; ha nincs megadva, a Gemini, ha van
kulcsa (ugyanúgy, mint a sales-agentben).
"""
from __future__ import annotations

import logging
import os
import time

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = 60
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
OPENAI_MODEL = os.environ.get("TRADING_OPENAI_MODEL", "gpt-4.1-mini")

PERSONA = (
    "Tapasztalt, fegyelmezett kriptó-bróker vagy, aki a megbízójának magyarul, tömören és őszintén "
    "számol be. Szabályok: (1) csak a megadott számokat használhatod, árat vagy százalékot nem találhatsz "
    "ki; (2) a kockázatot mindig megnevezed, hozamot nem ígérsz; (3) ez papírkereskedés, nem valódi pénz; "
    "(4) ha valamit nem tudsz az adatokból, kimondod; (5) a kockázati szabályokat (stop, pozícióméret, "
    "napi limit) a rendszer kódja határozza meg, azokon nem változtathatsz, legfeljebb elmagyarázod őket."
)


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, provider: str, key: str, client: httpx.Client | None = None):
        self.provider = provider
        self._key = key
        self.client = client or httpx.Client(timeout=TIMEOUT)

    @classmethod
    def from_env(cls) -> "LLM | None":
        wanted = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
        gemini = os.environ.get("GEMINI_API_KEY", "").strip()
        openai = os.environ.get("OPENAI_API_KEY", "").strip()
        if wanted == "openai" and openai:
            return cls("openai", openai)
        if wanted == "gemini" and gemini:
            return cls("gemini", gemini)
        if not wanted:
            if gemini:
                return cls("gemini", gemini)
            if openai:
                return cls("openai", openai)
        return None

    def ask(self, prompt: str) -> str:
        for attempt in range(2):
            try:
                r = self._request(prompt)
            except httpx.HTTPError as e:
                raise LLMError(f"a modell nem érhető el ({type(e).__name__})") from None
            if r.status_code in (429, 500, 502, 503) and attempt == 0:
                time.sleep(5)
                continue
            if r.status_code >= 400:
                raise LLMError(f"modellhiba (HTTP {r.status_code}): {r.text[:200]}")
            try:
                text = self._text(r.json())
            except (ValueError, KeyError, IndexError, TypeError):
                raise LLMError("értelmezhetetlen modellválasz") from None
            if not text.strip():
                raise LLMError("üres modellválasz")
            return text.strip()
        raise LLMError("a modell túlterhelt, később újra")

    def _request(self, prompt: str) -> httpx.Response:
        if self.provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
            body = {"systemInstruction": {"parts": [{"text": PERSONA}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}]}
            return self.client.post(url, headers={"x-goog-api-key": self._key}, json=body)
        body = {"model": OPENAI_MODEL,
                "messages": [{"role": "system", "content": PERSONA}, {"role": "user", "content": prompt}]}
        return self.client.post("https://api.openai.com/v1/chat/completions",
                                headers={"Authorization": f"Bearer {self._key}"}, json=body)

    def _text(self, data: dict) -> str:
        if self.provider == "gemini":
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        return data["choices"][0]["message"]["content"] or ""
