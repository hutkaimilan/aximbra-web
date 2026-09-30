"""Képgenerálás a videókhoz: háttér, illusztráció, jelenetkép.

A Gemini képmodelljét hívja. Ha a kulcsnak nincs rá kerete, None jön
vissza, és a videó képgenerálás nélkül készül el — nem áll meg miatta.

Ember arcát nem generáltatjuk valódi személyről: a prompt kifejezetten
elkéri, hogy felismerhető valódi személy ne legyen a képen.
"""
from __future__ import annotations

import base64
import logging
import os
import time

import httpx

import llm
import media

logger = logging.getLogger(__name__)

MODEL = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image")
GUARD = ("No recognisable real person, no celebrity, no logo of another company, no readable text. ")


def available() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def generate(prompt: str, aspect: str = "9:16") -> bytes | None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key or not prompt.strip():
        return None
    shape = {"9:16": "vertical 9:16", "1:1": "square 1:1", "16:9": "wide 16:9"}.get(aspect, "vertical 9:16")
    text = f"{GUARD}A {shape} image for a short business video. {prompt.strip()[:600]}"
    body = {"contents": [{"role": "user", "parts": [{"text": text}]}]}
    for attempt in range(3):
        try:
            r = httpx.post(llm.GEMINI_URL.format(model=MODEL), headers={"x-goog-api-key": key},
                           json=body, timeout=120)
        except httpx.HTTPError:
            return None
        if r.status_code == 429 and "per day" not in r.text.lower() and "perday" not in r.text.lower():
            time.sleep(min(60, 20 * (attempt + 1)))
            continue
        break
    if r.status_code >= 400:
        logger.info("képgenerálás nem elérhető: %s %s", r.status_code, r.text[:160])
        return None
    for part in ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or []:
        data = (part.get("inlineData") or part.get("inline_data") or {}).get("data")
        if data:
            try:
                return base64.b64decode(data)
            except ValueError:
                return None
    return None


def generate_into_library(prompt: str, aspect: str, name: str) -> dict | None:
    """Generált kép a médiatárba; onnantól ugyanúgy használható, mint a feltöltött."""
    raw = generate(prompt, aspect)
    if not raw:
        return None
    try:
        return media.add_image(raw, name=name, note=prompt[:200], source="generated")
    except media.MediaError as e:
        logger.info("generált kép mentése nem sikerült: %s", e)
        return None
