"""Modellhívás a videós agentnek: Gemini (ingyenes szint) vagy OpenAI.

A kimenetet a hívó JSON-ként olvassa, ezért itt csak egy szöveget adunk
vissza, és egy tűrő JSON-kiemelőt.
"""
import json
import os
import re
import time

import httpx

TIMEOUT = 180
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1")


class LLMError(RuntimeError):
    pass


def provider() -> str:
    p = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if p in ("gemini", "openai"):
        return p
    return "gemini" if os.environ.get("GEMINI_API_KEY") else "openai"


def _gemini(prompt: str) -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise LLMError("nincs beállítva a GEMINI_API_KEY")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
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
            time.sleep(min(60, 15 * (attempt + 1)))
            continue
        if r.status_code == 503:
            time.sleep(min(60, 10 * (attempt + 1)))
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
    return _gemini(prompt) if provider() == "gemini" else _openai(prompt)


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
