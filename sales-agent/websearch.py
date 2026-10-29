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
import threading
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx

import verify

logger = logging.getLogger(__name__)

TAVILY_URL = "https://api.tavily.com/search"
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
DOMAIN_RE = re.compile(r"\b((?:[a-z0-9-]+\.)+(?:hu|com|sk|ro|eu|io|ai|net|org))\b", re.I)


def tavily_on() -> bool:
    return bool(os.environ.get("TAVILY_API_KEY", "").strip())


def _tavily(query: str, n: int, include_domains: list[str] | None = None) -> list[dict]:
    key = os.environ.get("TAVILY_API_KEY", "").strip()
    body = {"api_key": key, "query": query, "max_results": n, "search_depth": "basic",
            "include_raw_content": False}
    if include_domains:
        body["include_domains"] = include_domains
    try:
        r = httpx.post(TAVILY_URL, timeout=30, headers={"Authorization": f"Bearer {key}"}, json=body)
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


def search(query: str, n: int = 4, include_domains: list[str] | None = None) -> list[dict]:
    """`include_domains` esetén csak Tavily jön szóba: a Gemini-ág összefoglal,
    nem találatlistát ad, tehát domainre nem szűrhető. Üres lista jobb, mint egy
    máshonnan származó találat, amit a hívó linkedines profilnak hinne."""
    query = (query or "").strip()[:300]
    if not query:
        return []
    if tavily_on():
        hits = _tavily(query, n, include_domains)
        if hits:
            return hits
    return [] if include_domains else _gemini_grounded(query)


# ---- cégkeresés -------------------------------------------------------------
# A kutatás a valódi találatokból választ cégeket. A Tavily havi 1000 ingyenes
# keresése közös a tanácsadóval és a LinkedIn-kereséssel, ezért a kutatás napi
# kerete külön korlátozott (TAVILY_RESEARCH_DAILY, alapból 18 ≈ 540/hó; a LinkedIn napi köre ~260/hó). A
# számláló a folyamatban él: újraindítás után nullázódik, ami legfeljebb egy
# napnyi keret duplázása – a szolgáltatás nem alszik el, ritkán indul újra.

_budget_lock = threading.Lock()
_budget = {"day": "", "used": 0}

# Cégjegyzékek, közösségi oldalak, állásportálok: nem egy cég saját oldala.
DIRECTORY_HOSTS = (
    "facebook.", "linkedin.", "instagram.", "youtube.", "twitter.", "tiktok.", "wikipedia.",
    "google.", "booking.", "tripadvisor.", "yelp.", "europages.", "kompass.", "cylex", "opten.",
    "ceginformacio.", "nemzeticegtar.", "e-cegjegyzek.", "cegkereso", "aranyoldalak.",
    "infobel.", "firmy.", "finstat.", "zlatestranky.", "listafirme.", "risco.", "termene.", "poslovna.",
    "bizi.si", "companieshouse.", "endole.", "yell.", "solocheck.", "societe.com", "pappers.", "pagesjaunes.",
    "indeed.", "profession.hu", "cvonline.", "jobs.", "glassdoor.", "trustpilot.", "goldenpages.", "clutch.",
    "kununu.", "dnb.com", "zoominfo.", "crunchbase.", "bloomberg.", "reddit.", "medium.com", "gov.", ".gov",
)


_li_budget = {"day": "", "used": 0}


def _grant(book: dict, want: int, env: str, default: int) -> int:
    try:
        cap = max(0, int(os.environ.get(env, str(default))))
    except ValueError:
        cap = default
    today = datetime.now(timezone.utc).date().isoformat()
    with _budget_lock:
        if book["day"] != today:
            book.update(day=today, used=0)
        grant = max(0, min(want, cap - book["used"]))
        book["used"] += grant
        return grant


def research_budget(want: int) -> int:
    """Ennyi keresést kaphat most a kutatás (0, ha elfogyott a napi keret)."""
    return _grant(_budget, want, "TAVILY_RESEARCH_DAILY", 18)


def linkedin_budget(want: int) -> int:
    """A LinkedIn napi körének kerete (TAVILY_LINKEDIN_DAILY, alapból 12 ≈ 260/hó
    hétköznapokon). A kutatás 18-cal együtt ~800/hó: marad a tanácsadónak is."""
    return _grant(_li_budget, want, "TAVILY_LINKEDIN_DAILY", 12)


def is_directory(url: str) -> bool:
    host = urlparse(url or "").netloc.lower().removeprefix("www.")
    return not host or any(d in host for d in DIRECTORY_HOSTS)


def company_hits(query: str, n: int = 10) -> list[dict]:
    """Tavily-találatok, a cégjegyzékek és közösségi oldalak nélkül.
    A Gemini-ágat szándékosan kihagyja: az összefoglal, nem cégoldalakat ad."""
    if not tavily_on():
        return []
    return [h for h in _tavily(query, n) if not is_directory(h["url"])]


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
