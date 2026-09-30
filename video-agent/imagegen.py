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
SIZES = {"9:16": (768, 1344), "1:1": (1024, 1024), "16:9": (1344, 768)}
# Ingyenes tartalék, kulcs nélkül. Vízjelet tesz a képre, ezért csak akkor
# hívjuk, ha a Geminire nincs keret, és a felületen jelezzük is.
FREE_URL = "https://image.pollinations.ai/prompt/{prompt}"


def free_on() -> bool:
    return (os.environ.get("FREE_IMAGEGEN") or "1").strip().lower() not in ("0", "false", "no")


def gemini_on() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def available() -> bool:
    return gemini_on() or free_on()


def engine() -> str:
    """Amelyikkel próbálkozunk. Hogy melyik szállított ténylegesen, azt a
    kész kép leírása mondja meg: a Gemininek lehet kulcsa keret nélkül."""
    return "gemini" if gemini_on() else "free" if free_on() else ""


def _free(prompt: str, aspect: str) -> bytes | None:
    from urllib.parse import quote
    w, h = SIZES.get(aspect, SIZES["9:16"])
    try:
        r = httpx.get(FREE_URL.format(prompt=quote(f"{GUARD}{prompt.strip()[:500]}", safe="")),
                      params={"width": w, "height": h, "nologo": "true"},
                      timeout=180, follow_redirects=True)
    except httpx.HTTPError:
        return None
    if r.status_code >= 400 or not r.content.startswith(b"\xff\xd8"):
        logger.info("ingyenes képgenerálás nem sikerült: %s", r.status_code)
        return None
    return r.content


def generate(prompt: str, aspect: str = "9:16") -> tuple[bytes, str] | None:
    """A kész kép és az őt előállító motor neve, vagy None."""
    def fallback():
        raw = _free(prompt, aspect) if free_on() else None
        return (raw, "free") if raw else None

    if not prompt.strip():
        return None
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return fallback()
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
        logger.info("Gemini képgenerálás nem elérhető: %s %s", r.status_code, r.text[:160])
        return fallback()
    for part in ((r.json().get("candidates") or [{}])[0].get("content") or {}).get("parts") or []:
        data = (part.get("inlineData") or part.get("inline_data") or {}).get("data")
        if data:
            try:
                return base64.b64decode(data), "gemini"
            except ValueError:
                break
    return fallback()


def generate_into_library(prompt: str, aspect: str, name: str) -> dict | None:
    """Generált kép a médiatárba; onnantól ugyanúgy használható, mint a feltöltött."""
    out = generate(prompt, aspect)
    if not out:
        return None
    raw, eng = out
    try:
        # A vízjeles, ingyenes forrást külön jelöljük, hogy a felületen látszódjon.
        return media.add_image(raw, name=name, note=prompt[:200],
                               source="generated" if eng == "gemini" else "generated-free")
    except media.MediaError as e:
        logger.info("generált kép mentése nem sikerült: %s", e)
        return None
