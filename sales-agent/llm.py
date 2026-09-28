"""A három modellhívás: cégkeresés (webes kereséssel), levélírás, válasz
besorolása. Mindhárom JSON-t kér, és mindhárom túléli, ha a modell mégis
szöveget ír köré.
"""
import json
import logging
import os
import re

from openai import OpenAI

import playbook

logger = logging.getLogger(__name__)

RESEARCH_MODEL = os.environ.get("SALES_RESEARCH_MODEL", "gpt-4.1")
WRITE_MODEL = os.environ.get("SALES_WRITE_MODEL", "gpt-4.1")
TIMEOUT = 180


class LLMError(RuntimeError):
    pass


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
    for opener, closer in (("[", "]"), ("{", "}")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError("a modell nem adott értelmezhető JSON-t")


def research(country: str, count: int, exclude_domains: list[str], focus: str = "") -> list[dict]:
    resp = _client().responses.create(
        model=RESEARCH_MODEL,
        tools=[{"type": "web_search", "user_location": {"type": "approximate", "country": country}}],
        input=playbook.research_prompt(country, count, exclude_domains, focus),
    )
    data = extract_json(resp.output_text)
    if isinstance(data, dict):
        data = data.get("items") or data.get("companies") or [data]
    if not isinstance(data, list):
        raise LLMError("a kutatás nem listát adott")
    return [d for d in data if isinstance(d, dict)]


def compose(lead: dict) -> dict:
    resp = _client().responses.create(model=WRITE_MODEL, input=playbook.compose_prompt(lead))
    data = extract_json(resp.output_text)
    if not isinstance(data, dict) or not data.get("body"):
        raise LLMError("a levélíró nem adott levelet")
    body = data["body"].strip()
    # A leiratkozó mondat kötelező: ha a modell kihagyta, a kód teszi hozzá.
    opt = playbook.OPT_OUT[lead["lang"]]
    if opt not in body:
        body = body.rstrip() + "\n\n" + opt
    return {"subject": (data.get("subject") or "").strip(), "body": body}


def critique(lead: dict, subject: str, body: str) -> dict:
    """Második kör: egy szigorú bíráló pontoz, és ha kell, átírja."""
    resp = _client().responses.create(model=WRITE_MODEL, input=playbook.critique_prompt(lead, subject, body))
    data = extract_json(resp.output_text)
    if not isinstance(data, dict):
        raise LLMError("a bíráló nem adott értékelést")
    try:
        score = max(0, min(10, int(data.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    return {"score": score, "issues": [str(i) for i in (data.get("issues") or [])][:6],
            "subject": (data.get("subject") or subject).strip(), "body": (data.get("body") or body).strip()}


def classify(original: str, reply: str) -> dict:
    resp = _client().responses.create(model=WRITE_MODEL, input=playbook.classify_prompt(original, reply))
    data = extract_json(resp.output_text)
    kind = data.get("kind") if isinstance(data, dict) else None
    if kind not in ("no", "interested", "auto", "other"):
        kind = "other"
    return {"kind": kind, "suggestion": (data.get("suggestion") or "") if kind == "interested" else ""}
