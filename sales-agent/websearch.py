"""Webes keresés a tanácsadónak.

Két út, ebben a sorrendben:
1. Tavily (TAVILY_API_KEY): keresőmotor API, havi 1000 ingyenes kereséssel,
   kártya nélkül. Találatot és a talált oldal szövegét is visszaadja.
2. Gemini + Google Search: ha a kulcsnak van rá kerete. Az ingyenes szinten
   gyakran nincs; ilyenkor csendben kimarad, nem hiba.

Ha egyik sem ad eredményt, a tanácsadó a saját tudásából és a kérdésben
szereplő linkekből dolgozik, és ezt ki is mondja.
"""
from __future__ import annotations

import logging
import os
import re

import httpx

import verify

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
DOMAIN_RE = re.compile(r"\b((?:[a-z0-9-]+\.)+(?:hu|com|sk|ro|eu|io|ai|net|org))\b", re.I)


def tavily_on() -> bool:
    return bool(os.environ.get("TAVILY_API_KEY", "").strip())


def _tavily(query: str, n: int) -> list[dict]:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    try:
        r = httpx.post(TAVILY_URL, timeout=30, headers={"Authorization": f"Bearer {key}"},
                       json={"api_key": key, "query": query, "max_results": n, "search_depth": "basic",
                             "include_raw_content": False})
    except httpx.HTTPError as e:
        logger.warning("tavily nem érhető el: %s", type(e).__name__)
        return []
    if r.status_code >= 400:
        logger.warning("tavily hiba: %s", r.status_code)
        return []
    out = []
    for x in (r.json().get("results") or [])[:n]:
        url = x.get("url") or ""
        if url.startswith("http"):
            out.append({"title": (x.get("title") or url)[:200], "url": url,
                        "text": re.sub(r"\s+", " ", x.get("content") or "")[:1500]})
    return out


def _gemini_grounded(query: str) -> list[dict]:
    """A Gemini keres a Google-ben és összefoglal. Keret nélkül üres lista."""
    import llm
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key or llm.provider() != "gemini":
        return []
    body = {"contents": [{"role": "user", "parts": [{"text":
            f"Search the web and summarise, factually and briefly, what it says about: {query}"}]}],
            "tools": [{"google_search": {}}]}
    try:
        r = httpx.post(llm.GEMINI_URL.format(model=llm.GEMINI_MODEL), headers={"x-goog-api-key": key},
                       json=body, timeout=60)
    except httpx.HTTPError:
        return []
    if r.status_code >= 400:  # jellemzően 429: az ingyenes kulcsnak nincs keresési kerete
        return []
    cand = (r.json().get("candidates") or [{}])[0]
    text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts") or [])
    chunks = (cand.get("groundingMetadata") or {}).get("groundingChunks") or []
    links = [c.get("web") or {} for c in chunks]
    if not text.strip():
        return []
    first = next((l for l in links if l.get("uri")), {})
    return [{"title": f"Google-keresés: {query}", "url": first.get("uri", ""), "text": text[:2500],
             "links": [{"title": l.get("title", ""), "url": l.get("uri", "")} for l in links if l.get("uri")][:5]}]


def search(query: str, n: int = 4) -> list[dict]:
    query = (query or "").strip()[:300]
    if not query:
        return []
    if tavily_on():
        hits = _tavily(query, n)
        if hits:
            return hits
    return _gemini_grounded(query)


def urls_in(text: str) -> list[str]:
    """A kérdésben szereplő linkek és domainek (pl. „aximbra.hu”)."""
    found = [u.rstrip(".,;:") for u in URL_RE.findall(text or "")]
    for d in DOMAIN_RE.findall(text or ""):
        if not any(d.lower() in u.lower() for u in found):
            found.append("https://" + d.lower())
    seen, out = set(), []
    for u in found:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out[:4]


def read_page(url: str) -> dict | None:
    text = verify.fetch_text(url)
    if not text or len(text.strip()) < 80:
        return None
    return {"title": url, "url": url, "text": re.sub(r"\s+", " ", text)[:3000]}
