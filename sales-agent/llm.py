"""A három modellhívás: cégkeresés (webes kereséssel), levélírás, válasz
besorolása. Mindhárom JSON-t kér, és mindhárom túléli, ha a modell mégis
szöveget ír köré.
"""
import json
import logging
import os
import re
import time

import httpx
from openai import OpenAI

import playbook

logger = logging.getLogger(__name__)

RESEARCH_MODEL = os.environ.get("SALES_RESEARCH_MODEL", "gpt-4.1")
WRITE_MODEL = os.environ.get("SALES_WRITE_MODEL", "gpt-4.1")
TIMEOUT = 180


class LLMError(RuntimeError):
    pass


GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def provider() -> str:
    """LLM_PROVIDER=gemini|openai; ha nincs megadva, a Gemini, ha van kulcsa."""
    p = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if p in ("gemini", "openai"):
        return p
    return "gemini" if os.environ.get("GEMINI_API_KEY") else "openai"


def _gemini(prompt: str, search: bool) -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise LLMError("nincs beállítva a GEMINI_API_KEY")
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
    if search:
        body["tools"] = [{"google_search": {}}]
    # Az ingyenes szint percenkénti korlátja gyorsan betelik: ilyenkor várunk
    # és újrapróbáljuk. A napi keret kifogyása viszont végleges aznapra.
    for attempt in range(5):
        try:
            # Fejlécben küldjük: így a régi (AIza…) és az új (AQ.…) kulcsformátum is működik,
            # és a kulcs nem kerül bele az URL-be (naplókba).
            r = httpx.post(GEMINI_URL.format(model=GEMINI_MODEL), headers={"x-goog-api-key": key},
                           json=body, timeout=TIMEOUT)
        except httpx.HTTPError as e:
            raise LLMError(f"a Gemini nem érhető el ({type(e).__name__})") from e
        if r.status_code == 429:
            text = r.text
            if "PerDay" in text or "per day" in text.lower():
                raise LLMError("insufficient_quota: elfogyott a Gemini napi ingyenes kerete")
            time.sleep(min(60, 15 * (attempt + 1)))
            continue
        if r.status_code == 503:  # túlterhelt modell: átmeneti
            time.sleep(min(60, 10 * (attempt + 1)))
            continue
        if r.status_code >= 400:
            raise LLMError(f"Gemini hiba ({r.status_code}): {r.text[:200]}")
        data = r.json()
        parts = ((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
        return "".join(p.get("text", "") for p in parts)
    raise LLMError("a Gemini percenkénti kerete többszöri várakozás után is tele volt")


def _ask(prompt: str, search: bool = False, country: str | None = None, model: str | None = None) -> str:
    if provider() == "gemini":
        return _gemini(prompt, search)
    kwargs = {"model": model or WRITE_MODEL, "input": prompt}
    if search:
        kwargs["tools"] = [{"type": "web_search", "user_location": {"type": "approximate", "country": country}}]
    return _client().responses.create(**kwargs).output_text


def _client() -> OpenAI:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise LLMError("nincs beállítva az OPENAI_API_KEY")
    return OpenAI(api_key=key, timeout=TIMEOUT, max_retries=2)


def extract_json(text: str):
    """Az első érvényes JSON tömb vagy objektum a szövegből."""
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.+?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1).strip()
    # Amelyik zárójel előbb jön, az a külső szerkezet: egy objektumon belüli
    # lista nem lehet a válasz.
    order = sorted((("[", "]"), ("{", "}")), key=lambda p: (text.find(p[0]) == -1, text.find(p[0])))
    for opener, closer in order:
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError("a modell nem adott értelmezhető JSON-t")


def paragraphs(body: str) -> str:
    """Minden sor külön bekezdés, egy üres sorral: telefonon így olvasható."""
    lines = [l.strip() for l in (body or "").replace("\r", "").split("\n")]
    return "\n\n".join(l for l in lines if l)


def can_search() -> bool:
    """Webes keresés csak az OpenAI-úton van; az ingyenes Gemini nem ad rá keretet."""
    mode = (os.environ.get("RESEARCH_MODE") or "").strip().lower()
    if mode in ("crawl", "search"):
        return mode == "search"
    return provider() == "openai"


def _research_crawl(country: str, count: int, exclude_domains: list[str], focus: str) -> list[dict]:
    """Keresés webes keresőeszköz nélkül: a modell ismert cégeket sorol fel,
    a program maga tölti le az oldalukat, és a modell a letöltött szövegből
    választ tényt és címet. Az ellenőrzés utána ugyanaz, mint máskor."""
    import verify
    listed = extract_json(_ask(playbook.list_prompt(country, count * 2, exclude_domains, focus)))
    if isinstance(listed, dict):
        listed = listed.get("items") or listed.get("companies") or []
    known = set(exclude_domains)
    out = []
    for c in [x for x in listed if isinstance(x, dict)][: count * 2]:
        site = (c.get("website") or "").strip()
        if not site.startswith("http"):
            site = "https://" + site.lstrip("/")
        from store import domain_of
        if not site or domain_of(site) in known:
            continue
        pages = verify.crawl_site(site)
        emails = verify.role_emails(pages, site)
        if not emails:
            continue
        bundle = "\n\n".join(f"URL: {u}\n{re.sub(chr(92) + 's+', ' ', t)[:2500]}" for u, t in pages)[:9000]
        try:
            fact = extract_json(_ask(playbook.fact_prompt(c, bundle, [e for e, _ in emails])))
        except LLMError:
            continue
        if not isinstance(fact, dict) or fact.get("skip"):
            continue
        email = (fact.get("email") or emails[0][0]).lower()
        email_url = dict(emails).get(email) or emails[0][1]
        out.append({**c, "website": site, "country": country, **fact, "email": email, "email_url": email_url})
        if len(out) >= count:
            break
    return out


def research(country: str, count: int, exclude_domains: list[str], focus: str = "") -> list[dict]:
    if not can_search():
        return _research_crawl(country, count, exclude_domains, focus)
    data = extract_json(_ask(playbook.research_prompt(country, count, exclude_domains, focus),
                             search=True, country=country, model=RESEARCH_MODEL))
    if isinstance(data, dict):
        data = data.get("items") or data.get("companies") or [data]
    if not isinstance(data, list):
        raise LLMError("a kutatás nem listát adott")
    return [d for d in data if isinstance(d, dict)]


def compose(lead: dict) -> dict:
    data = extract_json(_ask(playbook.compose_prompt(lead)))
    if not isinstance(data, dict) or not data.get("body"):
        raise LLMError("a levélíró nem adott levelet")
    body = paragraphs(data["body"])
    # A leiratkozó mondat kötelező: ha a modell kihagyta, a kód teszi hozzá.
    opt = playbook.OPT_OUT[lead["lang"]]
    if opt not in body:
        body = body.rstrip() + "\n\n" + opt
    return {"subject": (data.get("subject") or "").strip(), "body": body}


def critique(lead: dict, subject: str, body: str) -> dict:
    """Második kör: egy szigorú bíráló pontoz, és ha kell, átírja."""
    data = extract_json(_ask(playbook.critique_prompt(lead, subject, body)))
    if not isinstance(data, dict):
        raise LLMError("a bíráló nem adott értékelést")
    try:
        score = max(0, min(10, int(data.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    return {"score": score, "issues": [str(i) for i in (data.get("issues") or [])][:6],
            "subject": (data.get("subject") or subject).strip(), "body": paragraphs(data.get("body") or body)}


def classify(original: str, reply: str) -> str:
    data = extract_json(_ask(playbook.classify_prompt(original, reply)))
    kind = data.get("kind") if isinstance(data, dict) else None
    return kind if kind in ("no", "interested", "auto", "other") else "other"


def draft_reply(original: str, reply: str, slots: list[str], lang: str) -> str:
    data = extract_json(_ask(playbook.reply_prompt(original, reply, slots, lang)))
    body = (data.get("body") if isinstance(data, dict) else "") or ""
    if not body.strip():
        raise LLMError("a válaszíró nem adott szöveget")
    return paragraphs(body)
