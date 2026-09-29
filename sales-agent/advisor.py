"""A tanácsadó: értékesítési és marketing kérdésekre válaszol, szükség
esetén a weben is utánanéz, és a saját értékesítési adatainkból dolgozik.

Egy kérdés útja: (1) a modell eldönti, kell-e keresni, és mire; (2) keresés
és a kérdésben szereplő linkek beolvasása; (3) válasz a forrásokkal.
Ha a keresés nem elérhető, a válasz akkor is elkészül, forrás nélkül.
"""
from __future__ import annotations

import json
import logging
import re

import llm
import playbook
import websearch

logger = logging.getLogger(__name__)

MAX_QUESTION = 4000
HISTORY_TURNS = 10


def _history(store) -> str:
    rows = store.advisor_history(HISTORY_TURNS)
    return "\n\n".join(f"{'Milán' if r['role'] == 'user' else 'Tanácsadó'}: {r['content'][:1500]}" for r in rows)


def _context(store, lead_id: int | None) -> str:
    t = store.stats()["total"]
    lines = [f"Összesen kiment {t['sent']} levél, válaszolt {t['replied']}, érdeklődik {t['interested']}, vázlat vár {t['drafts']}."]
    sent = [l for l in store.list() if l["status"] == "sent"][:40]
    if sent:
        lines.append("Kiküldött megkeresések (cég, iparág, ország, igény, válasz):")
        lines += [f"- {l['company']} | {l.get('sector') or '?'} | {l['country']} | {l['pain']} | {l['reply_kind']}" for l in sent]
    if lead_id:
        l = store.get(lead_id)
        if l:
            lines.append(f"""
A KÉRDÉS EHHEZ A CÉGHEZ TARTOZIK: {l['company']} ({l.get('town') or ''}, {l['country']}), {l.get('website') or ''}
Iparág: {l.get('sector') or '?'}; ajánlott agent: {playbook.PAINS.get(l['pain'], l['pain'])}
Tény az oldalukról: „{l.get('observation') or ''}”
Elküldött levél: {l.get('subject') or ''}
{(l.get('body') or '')[:2500]}
Válaszuk ({l['reply_kind']}): {(l.get('reply_text') or '-')[:2500]}""")
    return "\n".join(lines)


def _queries(question: str, history: str) -> list[str]:
    try:
        data = llm.extract_json(llm._ask(playbook.advisor_plan_prompt(question, history)))
    except llm.LLMError as e:
        if "insufficient_quota" in str(e):
            raise
        return []
    qs = data.get("queries") if isinstance(data, dict) else None
    return [str(q).strip() for q in (qs or []) if str(q).strip()][:3]


def _clean(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text or "")
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)
    return text.strip()


def ask(store, question: str, lead_id: int | None = None) -> dict:
    question = (question or "").strip()[:MAX_QUESTION]
    if not question:
        raise ValueError("üres kérdés")
    history = _history(store)

    sources: list[dict] = []
    seen: set[str] = set()

    def add(items):
        for s in items:
            key = s.get("url") or s.get("title")
            if key and key not in seen and len(sources) < 10:
                seen.add(key)
                sources.append(s)

    urls = websearch.urls_in(question)
    # „aximbráról”, „aximbrának”: a toldalék ékezetes, ezért csak a tőre nézünk.
    if "aximbr" in question.lower() and not any("aximbra.hu" in u for u in urls):
        urls.append("https://aximbra.hu")
    add(filter(None, (websearch.read_page(u) for u in urls)))

    queries = _queries(question, history)
    for q in queries:
        add(websearch.search(q))

    answer = _clean(llm._ask(playbook.advisor_prompt(question, history, _context(store, lead_id), sources, bool(queries))))
    if not answer:
        raise llm.LLMError("a tanácsadó nem adott választ")

    refs = []
    for s in sources:
        refs.append({"title": s["title"], "url": s["url"]})
        refs += s.get("links") or []
    refs = [r for r in refs if r.get("url")][:12]
    store.advisor_add("user", question)
    store.advisor_add("assistant", answer, json.dumps(refs, ensure_ascii=False))
    return {"answer": answer, "sources": refs, "queries": queries}
