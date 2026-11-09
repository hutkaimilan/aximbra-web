"""A nyelvi modell: magyaráz és válaszol, de nem dönt és nem számol.

Minden szám, amit a modell kap, a piaci adatból és a naplóból jön; a prompt
megtiltja, hogy mást írjon. Ha a modell nem elérhető, az értesítés attól még
kimegy — a magyarázat elmarad, a kötés adatai nem.

Szolgáltató: LLM_PROVIDER=gemini|openai; ha nincs megadva, a Gemini, ha van
kulcsa (ugyanúgy, mint a sales-agentben).
"""
from __future__ import annotations

import json
import logging
import os
import re
import time

import httpx

logger = logging.getLogger(__name__)

TIMEOUT = 60
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
OPENAI_MODEL = os.environ.get("TRADING_OPENAI_MODEL", "gpt-4.1-mini")

CHAT_PERSONA = (
    "Te Milán személyes trader-botja vagy, és vele beszélgetsz a saját alkalmazásában. Milán teljesen kezdő a "
    "tőzsdében. Tegeződj, beszélj természetesen és röviden, mint egy jó barát, aki ért a piacokhoz. "
    "Pontosan arra válaszolj, amit kérdez: köszönésre köszönj és mondd el egy-két mondatban a lényeget; "
    "konkrét kérdésre konkrétan. Szakszót csak magyarázattal használj. "
    "Csak a kapott adatokban szereplő számokat használd, semmit ne találj ki. Ne ismételgesd minden üzenetben a "
    "figyelmeztetéseket és a szabályokat — csak akkor említsd őket, ha a kérdéshez tartoznak. "
    "Ha azt kérdezi, mi lesz az árral, mondd meg őszintén, hogy biztosan nem tudod, de mondd el, mit látsz most "
    "és mit csinál a bot. Ha olyat kér, amit a bot nem tud, mondd meg, és javasolj megoldást. "
    "Két játékpénzes számlát kezelsz: a kriptó-számlát a Binance demón (BTC, ETH) és a világpiaci számlát "
    "(részvények, indexek, olaj, arany, kripto). Ha Milán a pénzről, a befektetésekről vagy az állapotról kérdez, "
    "mindkettőről beszélj. Azt, hogy játékpénz, elég ritkán megemlíteni, ő tudja. A régebbi válaszaid stílusát ne "
    "másold, ha azok hosszúak vagy ismétlődők voltak. "
    "Ha Milán hírt, tippet vagy véleményt oszt meg (pl. 'a demokraták nyertek'), keresd meg a kapcsolódó híreket "
    "az adatokban, mondd el egyszerűen, mely piacokra és merre hathat általában (bizonytalanságot jelezve), és mondd "
    "meg, hogy az AI-kereskedő ezt a következő percben figyelembe veszi a döntésénél. "
    "Formázás: rövid bekezdések, ha kell, egyszerű felsorolás; Markdown-csillagokat ne használj."
)

PERSONA = (
    "Tapasztalt, fegyelmezett kriptó-bróker vagy, aki a megbízójának magyarul, tömören és őszintén "
    "számol be. Szabályok: (1) csak a megadott számokat használhatod, árat vagy százalékot nem találhatsz "
    "ki; (2) a kockázatot mindig megnevezed, hozamot nem ígérsz; (3) ez papírkereskedés, nem valódi pénz; "
    "(4) ha valamit nem tudsz az adatokból, kimondod; (5) a kockázati szabályokat (stop, pozícióméret, "
    "napi limit) a rendszer kódja határozza meg, azokon nem változtathatsz, legfeljebb elmagyarázod őket."
)


class LLMError(RuntimeError):
    pass


def extract_json(text: str):
    """Az első érvényes JSON tömb vagy objektum a szövegből (a modell néha szöveget ír köré)."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1).strip()
    for opener, closer in sorted((("[", "]"), ("{", "}")), key=lambda p: (text.find(p[0]) == -1, text.find(p[0]))):
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise ValueError("a modell nem adott értelmezhető JSON-t")


class LLM:
    def __init__(self, provider: str, key: str, client: httpx.Client | None = None, fallback: "LLM | None" = None):
        self.provider = provider
        self._key = key
        self.client = client or httpx.Client(timeout=TIMEOUT)
        self.fallback = fallback

    @classmethod
    def from_env(cls) -> "LLM | None":
        wanted = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
        gemini = os.environ.get("GEMINI_API_KEY", "").strip()
        openai = "" if os.environ.get("LLM_FALLBACK", "on").lower() == "off" else os.environ.get("OPENAI_API_KEY", "").strip()
        gem = cls("gemini", gemini) if gemini else None
        oai = cls("openai", openai) if openai else None
        order = [oai, gem] if wanted == "openai" else [gem, oai]
        chain = [x for x in order if x]
        if not chain:
            return None
        chain[0].fallback = chain[1] if len(chain) > 1 else None   # a másik szolgáltató tartaléknak
        return chain[0]

    def ask(self, prompt: str, system: str | None = None, models: list[str] | None = None,
            timeout: float | None = None) -> str:
        """models: a Gemini-modellek sorrendje erre a hívásra (pl. a chat a gyorsakat kéri);
        timeout: modellenkénti időkorlát másodpercben."""
        try:
            return self._ask_once(prompt, system, models, timeout)
        except LLMError as first:
            if self.fallback is None:
                raise
            logger.warning("a(z) %s modell nem válaszolt (%s), tartalék: %s", self.provider, first, self.fallback.provider)
            return self.fallback._ask_once(prompt, system, None, timeout)

    def _ask_once(self, prompt: str, system: str | None = None, models: list[str] | None = None,
                  timeout: float | None = None) -> str:
        """Gemininél a modelllista elemein megy végig: túlterhelésnél a következő jön."""
        models = models or [m.strip() for m in os.environ.get("GEMINI_MODELS", "").split(",") if m.strip()] or [GEMINI_MODEL]
        if self.provider != "gemini":
            models = [None]
        last = None
        for model in models:
            try:
                return self._ask_model(prompt, model, system, timeout)
            except LLMError as e:
                last = e
                logger.warning("modell %s: %s", model, str(e)[:120])
        raise last

    def _ask_model(self, prompt: str, model: str | None, system: str | None = None,
                   timeout: float | None = None) -> str:
        tries = 1 if timeout else 2
        for attempt in range(tries):
            try:
                r = self._request(prompt, model, system, timeout)
            except httpx.HTTPError as e:
                raise LLMError(f"a modell nem érhető el ({type(e).__name__})") from None
            if r.status_code in (429, 500, 502, 503) and attempt < tries - 1:
                time.sleep(3)
                continue
            if r.status_code == 429:
                quota = "quota" in r.text.lower() or "exhausted" in r.text.lower()
                raise LLMError(f"{'elfogyott a keret' if quota else 'túl sok kérés'} (HTTP 429): {r.text[:160]}")
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

    def models(self) -> list[str]:
        """A kulccsal elérhető Gemini-modellek (diagnosztika)."""
        if self.provider != "gemini":
            return []
        try:
            r = self.client.get("https://generativelanguage.googleapis.com/v1beta/models",
                                headers={"x-goog-api-key": self._key}, params={"pageSize": 200})
            return [m["name"].removeprefix("models/") for m in r.json().get("models", [])
                    if "generateContent" in m.get("supportedGenerationMethods", [])]
        except (httpx.HTTPError, ValueError, KeyError):
            return []

    def _request(self, prompt: str, model: str | None = None, system: str | None = None,
                 timeout: float | None = None) -> httpx.Response:
        kw = {"timeout": timeout} if timeout else {}
        if self.provider == "gemini":
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model or GEMINI_MODEL}:generateContent"
            body = {"systemInstruction": {"parts": [{"text": system or PERSONA}]},
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}]}
            return self.client.post(url, headers={"x-goog-api-key": self._key}, json=body, **kw)
        body = {"model": OPENAI_MODEL,
                "messages": [{"role": "system", "content": system or PERSONA},
                             {"role": "user", "content": prompt}]}
        return self.client.post("https://api.openai.com/v1/chat/completions",
                                headers={"Authorization": f"Bearer {self._key}"}, json=body, **kw)

    def _text(self, data: dict) -> str:
        if self.provider == "gemini":
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts)
        return data["choices"][0]["message"]["content"] or ""
