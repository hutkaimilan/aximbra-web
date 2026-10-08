"""Modellhívás a videós agentnek: Claude, Gemini (ingyenes szint) vagy OpenAI.

A kimenetet a hívó JSON-ként olvassa, ezért itt csak egy szöveget adunk
vissza, és egy tűrő JSON-kiemelőt.

Claude fizetős: ha elfogy a keret vagy tartósan túlterhelt, és van Gemini
kulcs, a hívás a Geminire esik vissza. Így az ütemezett gyártás nem áll le
egy lemerült egyenleg miatt, csak gyengébb modellel megy tovább — ezt a
napló jelzi.
"""
import logging
import json
import os
import re

import httpx

import stop

TIMEOUT = 180
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1")
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-opus-5-5")
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
# A rendezői JSON 5–9 jelenettel, poszttal együtt bőven belefér.
ANTHROPIC_MAX_TOKENS = 8000

logger = logging.getLogger(__name__)


class LLMError(RuntimeError):
    pass


class _Fallback(LLMError):
    """Claude-hiba, amin a Gemini átsegít: elfogyott egyenleg, tartós túlterhelés."""


def provider() -> str:
    p = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if p in ("anthropic", "gemini", "openai"):
        return p
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "gemini" if os.environ.get("GEMINI_API_KEY") else "openai"


def engine_name() -> str:
    """A felületnek: melyik modell rendez."""
    return {"anthropic": ANTHROPIC_MODEL, "gemini": GEMINI_MODEL, "openai": OPENAI_MODEL}[provider()]


def available() -> bool:
    return any(os.environ.get(k, "").strip() for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "OPENAI_API_KEY"))


def _anthropic(prompt: str) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise LLMError("nincs beállítva az ANTHROPIC_API_KEY")
    head = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    body = {"model": ANTHROPIC_MODEL, "max_tokens": ANTHROPIC_MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}]}
    for attempt in range(4):
        try:
            r = httpx.post(ANTHROPIC_URL, headers=head, json=body, timeout=TIMEOUT)
        except httpx.HTTPError as e:
            raise _Fallback(f"a Claude nem érhető el ({type(e).__name__})") from e
        if r.status_code in (429, 529, 503):
            # A retry-after megmondja, mennyit várjunk; felülről korlátozzuk,
            # hogy egy gyártás ne ragadjon itt percekig.
            try:
                wait = float(r.headers.get("retry-after") or 0)
            except ValueError:
                wait = 0
            stop.sleep(min(60, wait or 10 * (attempt + 1)))
            continue
        if r.status_code >= 400:
            msg = r.text[:300]
            if "credit balance" in msg.lower() or r.status_code in (401, 402, 403):
                raise _Fallback(f"Claude: {'elfogyott az egyenleg' if 'credit' in msg.lower() else 'érvénytelen kulcs'}")
            raise LLMError(f"Claude hiba ({r.status_code}): {msg[:200]}")
        data = r.json()
        text = "".join(c.get("text", "") for c in data.get("content") or [] if c.get("type") == "text")
        if data.get("stop_reason") == "max_tokens":
            logger.warning("a Claude válasza a tokenkorlátnál megszakadt")
        return text
    raise _Fallback("a Claude többszöri várakozás után is túlterhelt")


def _gemini(prompt: str, media_parts: list | None = None) -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise LLMError("nincs beállítva a GEMINI_API_KEY")
    body = {"contents": [{"role": "user", "parts": [*(media_parts or []), {"text": prompt}]}]}
    for attempt in range(5):
        try:
            # Fejlécben küldjük, így a kulcs nem kerül bele az URL-be (naplókba).
            r = httpx.post(GEMINI_URL.format(model=GEMINI_MODEL), headers={"x-goog-api-key": key},
                           json=body, timeout=TIMEOUT)
        except httpx.HTTPError as e:
            raise LLMError(f"a Gemini nem érhető el ({type(e).__name__})") from e
        if r.status_code == 429:
            if "perday" in r.text.lower() or "per day" in r.text.lower():
                raise LLMError("insufficient_quota: elfogyott a Gemini napi ingyenes kerete")
            stop.sleep(min(60, 15 * (attempt + 1)))
            continue
        if r.status_code == 503:
            stop.sleep(min(60, 10 * (attempt + 1)))
            continue
        if r.status_code >= 400:
            raise LLMError(f"Gemini hiba ({r.status_code}): {r.text[:200]}")
        parts = ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts)
    raise LLMError("a Gemini percenkénti kerete többszöri várakozás után is tele volt")


def _openai(prompt: str) -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise LLMError("nincs beállítva az OPENAI_API_KEY")
    try:
        r = httpx.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {key}"},
                       json={"model": OPENAI_MODEL, "input": prompt}, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise LLMError(f"az OpenAI nem érhető el ({type(e).__name__})") from e
    if r.status_code == 429 and "insufficient_quota" in r.text:
        raise LLMError("insufficient_quota: elfogyott az OpenAI-keret")
    if r.status_code >= 400:
        raise LLMError(f"OpenAI hiba ({r.status_code})")
    out = r.json().get("output") or []
    return "".join(c.get("text", "") for o in out for c in (o.get("content") or []) if c.get("type") == "output_text")


def _ask(prompt: str) -> str:
    p = provider()
    if p == "anthropic":
        try:
            return _anthropic(prompt)
        except _Fallback as e:
            if not os.environ.get("GEMINI_API_KEY", "").strip():
                raise
            logger.warning("%s — ez a hívás a Geminin megy", e)
            return _gemini(prompt)
    return _gemini(prompt) if p == "gemini" else _openai(prompt)


def extract_json(text: str):
    """Az első érvényes JSON tömb vagy objektum a szövegből."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1).strip()
    order = sorted((("[", "]"), ("{", "}")), key=lambda p: (text.find(p[0]) == -1, text.find(p[0])))
    for opener, closer in order:
        start, end = text.find(opener), text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError("a modell nem adott értelmezhető JSON-t")


def ask_about_media(prompt: str, data: bytes, mime: str) -> str:
    """Egy kép vagy rövid videó megnézése (Gemini, a fájl a kérésben utazik).
    Más szolgáltatónál nincs ilyen út: ott a hívó üres választ kap, és a
    média leírás nélkül marad."""
    if provider() != "gemini":
        raise LLMError("a média megnézése csak Geminivel megy")
    import base64
    part = {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}}
    return _gemini(prompt, [part])
