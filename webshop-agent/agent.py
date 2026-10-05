"""Webshop ügyfélszolgálati agent: vásárlói levélből választervezet.

Lépések:
1. Kiolvassa a levélből a rendelésszámot és a nyelvet, és megállapítja, mit kér
   a vásárló (rendelés állapota, visszaküldés, számla, termékkérdés, panasz).
2. Megkeresi a rendelést a webshopban.
3. ADATVÉDELEM: rendelésadatot csak akkor ír bele, ha a levél arról az e-mail-
   címről jött, amelyikkel a rendelést leadták. Különben azonosítást kér.
4. Megírja a választ. A modell csak a rendelés tényeit és a bolt szabályait
   használhatja; a kész szövegben minden számot visszaellenőrzünk, és ha olyan
   szám szerepel benne, ami nincs a tényekben, a sablonválaszt adjuk helyette.
5. Semmi nem megy ki magától: ez csak tervezet, ember hagyja jóvá.
"""
from __future__ import annotations

import json
import logging
import os
import re

import httpx

from connectors import DEMO_POLICY, Order, Shop, ShopError

logger = logging.getLogger(__name__)

INTENTS = ("order_status", "return", "invoice", "product", "complaint", "other")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MAX_IN = 6000

ORDER_RE = re.compile(r"(?:#|\b(?:rendel[ée]s(?:sz[aá]m)?|order|bestellung|nr\.?|no\.?|sz\.?)\s*[:#]?\s*)?\b([A-Z]{2,4}-\d{3,10}|\d{4,10})\b", re.I)
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

KEYWORDS = {
    "order_status": ["hol a", "hol tart", "mikor érkez", "csomag", "szállít", "where is", "tracking", "delivery", "wo ist", "paket", "lieferung", "versand"],
    "return": ["visszaküld", "csere", "elállás", "visszautal", "return", "refund", "exchange", "rücksend", "umtausch", "erstattung"],
    "invoice": ["számla", "invoice", "rechnung"],
    "complaint": ["panasz", "sérült", "hibás", "rossz termék", "elégedetlen", "damaged", "broken", "wrong item", "complaint", "beschädigt", "falsch", "beschwerde"],
    "product": ["raktáron", "készlet", "melyik", "ajánl", "in stock", "recommend", "which", "vorrätig", "empfehl"],
}

LANG_HINTS = {
    "hu": ["szia", "kedves", "üdv", "köszön", "rendel", "csomag", "hol", "mikor", "tisztelt", "számla"],
    "de": ["hallo", "guten", "danke", "bestellung", "paket", "wo ist", "sehr geehrte", "rechnung", "bitte"],
    "en": ["hello", "hi ", "dear", "thanks", "order", "where", "parcel", "please", "invoice"],
}

STATUS_TEXT = {
    "hu": {"received": "beérkezett, feldolgozásra vár", "processing": "feldolgozás alatt van, hamarosan feladjuk",
           "shipped": "feladtuk", "delivered": "kézbesítve", "cancelled": "törölve", "refunded": "visszatérítve",
           "on_hold": "függőben van", "unknown": "feldolgozás alatt"},
    "en": {"received": "received and awaiting processing", "processing": "being prepared and will ship soon",
           "shipped": "shipped", "delivered": "delivered", "cancelled": "cancelled", "refunded": "refunded",
           "on_hold": "on hold", "unknown": "being processed"},
    "de": {"received": "eingegangen und wartet auf Bearbeitung", "processing": "in Bearbeitung und wird bald versendet",
           "shipped": "versendet", "delivered": "zugestellt", "cancelled": "storniert", "refunded": "erstattet",
           "on_hold": "zurückgestellt", "unknown": "in Bearbeitung"},
}


def detect_lang(text: str) -> str:
    low = " " + (text or "").lower() + " "
    if re.search(r"[őű]", low):
        return "hu"
    if re.search(r"[äß]", low):
        return "de"
    score = {k: sum(w in low for w in v) for k, v in LANG_HINTS.items()}
    best = max(score, key=score.get)
    return best if score[best] else "en"


def extract(text: str) -> dict:
    nums = []
    for m in ORDER_RE.finditer(text or ""):
        n = m.group(1)
        if len(re.sub(r"\D", "", n)) >= 4 and n not in nums and not re.fullmatch(r"(19|20)\d{2}", n):
            nums.append(n)
    return {"order_numbers": nums[:3], "emails": EMAIL_RE.findall(text or "")[:3]}


def guess_intent(text: str) -> str:
    low = (text or "").lower()
    for intent in ("complaint", "return", "invoice", "order_status", "product"):
        if any(k in low for k in KEYWORDS[intent]):
            return intent
    return "other"


# ---- sablonválaszok: modell nélkül is működik, és ez a biztonsági háló --------

GREET = {"hu": "Kedves {name}!", "en": "Dear {name},", "de": "Guten Tag {name},"}
GREET_ANON = {"hu": "Kedves Vásárlónk!", "en": "Hello,", "de": "Guten Tag,"}
SIGN = {"hu": "Üdvözlettel:\n{shop} ügyfélszolgálat", "en": "Best regards,\n{shop} customer service",
        "de": "Mit freundlichen Grüßen\n{shop} Kundenservice"}


def _greet(lang, order):
    name = (order.name.split()[-1] if order and order.name else "")
    if lang == "hu" and order and order.name:
        name = order.name  # magyarul a teljes név a szokás: Kovács Anna
    return (GREET[lang].format(name=name) if name else GREET_ANON[lang])


def template_reply(lang: str, intent: str, order: Order | None, verified: bool, shop: str) -> str:
    st = STATUS_TEXT[lang]
    lines = [_greet(lang, order if verified else None), ""]
    if not order:
        lines.append({"hu": "Köszönjük a megkeresést! Hogy utána tudjunk nézni, kérjük, írja meg a rendelésszámát és a rendeléskor megadott e-mail-címet.",
                      "en": "Thank you for getting in touch. To look into this, please send us your order number and the email address used for the order.",
                      "de": "Vielen Dank für Ihre Nachricht. Damit wir nachsehen können, senden Sie uns bitte Ihre Bestellnummer und die bei der Bestellung verwendete E-Mail-Adresse."}[lang])
    elif not verified:
        lines.append({"hu": "Köszönjük a megkeresést! Adatvédelmi okokból a rendelés részleteit csak a rendeléskor megadott e-mail-címre tudjuk elküldeni. Kérjük, írjon arról a címről, vagy adja meg azt.",
                      "en": "Thank you for your message. For data protection reasons we can only share order details with the email address used for the order. Please write from that address or tell us which one it was.",
                      "de": "Vielen Dank für Ihre Nachricht. Aus Datenschutzgründen können wir Bestelldetails nur an die bei der Bestellung verwendete E-Mail-Adresse senden. Bitte schreiben Sie uns von dieser Adresse."}[lang])
    else:
        lines.append({"hu": f"A(z) {order.number} számú rendelése jelenleg: {st.get(order.status, st['unknown'])}.",
                      "en": f"Your order {order.number} is currently {st.get(order.status, st['unknown'])}.",
                      "de": f"Ihre Bestellung {order.number} ist derzeit {st.get(order.status, st['unknown'])}."}[lang])
        if order.status == "shipped" and (order.tracking_number or order.tracking_url):
            lines.append({"hu": f"Futár: {order.carrier or '-'}, csomagszám: {order.tracking_number or '-'}.",
                          "en": f"Carrier: {order.carrier or '-'}, tracking number: {order.tracking_number or '-'}.",
                          "de": f"Versanddienst: {order.carrier or '-'}, Sendungsnummer: {order.tracking_number or '-'}."}[lang])
            if order.tracking_url:
                lines.append({"hu": "Csomagkövetés: ", "en": "Track your parcel: ", "de": "Sendungsverfolgung: "}[lang] + order.tracking_url)
        if intent in ("return", "invoice", "complaint"):
            lines.append({"hu": "A kérését továbbítottuk a kollégáknak, hamarosan személyesen is válaszolunk.",
                          "en": "We have passed your request to our team and will get back to you personally shortly.",
                          "de": "Wir haben Ihr Anliegen an unser Team weitergeleitet und melden uns in Kürze persönlich."}[lang])
    lines += ["", SIGN[lang].format(shop=shop)]
    return "\n".join(lines)


# ---- modell ---------------------------------------------------------------------

def _gemini(prompt: str) -> str | None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}}
    try:
        r = httpx.post(GEMINI_URL.format(model=GEMINI_MODEL), headers={"x-goog-api-key": key}, json=body, timeout=60)
        if r.status_code >= 400:
            logger.warning("gemini hiba: %s %s", r.status_code, r.text[:200])
            return None
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
        logger.warning("gemini nem válaszolt: %s", e)
        return None


def _prompt(text, lang, intent, facts, policy, shop, verified):
    return f"""You are the customer service assistant of the web shop "{shop}". Write a reply DRAFT that a human will approve.

Customer message:
\"\"\"{text}\"\"\"

Reply language: {lang} ({'Hungarian' if lang == 'hu' else 'German' if lang == 'de' else 'English'}). In Hungarian and German use the polite form (Ön / Sie).
Detected request: {intent}
Order facts (the ONLY order data you may use; empty means none may be shared): {json.dumps(facts, ensure_ascii=False)}
Customer identity verified for this order: {verified}
Shop policy (the ONLY rules you may state): {policy}

Rules:
- Never invent dates, amounts, tracking numbers, delivery times or promises that are not in the facts or the policy.
- If not verified or no order found, ask for the order number and the email used for the order; share no order details.
- Returns, invoices, complaints: answer what the policy covers, then say a colleague will follow up personally.
- Be warm, concrete and short: 3–6 sentences. Greet, answer, close. Sign as "{shop}" customer service.
- Also return "intent" (one of {", ".join(INTENTS)}) and "needs_human": true for complaints, angry customers or anything the facts/policy cannot answer.

Return JSON only: {{"intent": "...", "needs_human": true|false, "subject": "...", "body": "..."}}"""


def _numbers(s: str) -> set[str]:
    return {re.sub(r"\D", "", m) for m in re.findall(r"\d[\d .,:/-]*\d|\d", s or "") if len(re.sub(r"\D", "", m)) >= 2}


def grounded(body: str, facts: dict, policy: str, text: str) -> bool:
    """Minden legalább kétjegyű szám a válaszban szerepel-e a tényekben, a szabályzatban vagy a vásárló levelében."""
    allowed = _numbers(json.dumps(facts, ensure_ascii=False)) | _numbers(policy) | _numbers(text)
    for n in _numbers(body):
        if n not in allowed and not any(n in a for a in allowed):
            return False
    return True


def reply(shop: Shop, from_email: str, subject: str, text: str, shop_name: str = "ŐRLŐ",
          policy: dict | None = None) -> dict:
    text = (text or "")[:MAX_IN]
    full = f"{subject or ''}\n{text}"
    lang = detect_lang(full)
    found = extract(full)
    intent = guess_intent(full)
    policy_text = (policy or DEMO_POLICY).get(lang) or (policy or DEMO_POLICY).get("en", "")

    order, verified, lookup_error = None, False, ""
    try:
        for n in found["order_numbers"]:
            hits = shop.find(number=n)
            if hits:
                order = hits[0]
                break
        if not order and from_email:
            hits = shop.find(email=from_email)
            if hits:
                order = sorted(hits, key=lambda o: o.created, reverse=True)[0]
    except ShopError as e:
        lookup_error = str(e)
    if order:
        verified = bool(from_email) and order.email.lower() == from_email.strip().lower()

    facts = order.facts() if (order and verified) else {}
    out = {"lang": lang, "intent": intent, "order_numbers": found["order_numbers"],
           "order": facts or None, "order_found": bool(order), "verified": verified,
           "needs_human": intent in ("complaint", "other") or bool(lookup_error), "engine": "template",
           "lookup_error": lookup_error}

    raw = _gemini(_prompt(text, lang, intent, facts, policy_text, shop_name, verified))
    data = None
    if raw:
        try:
            data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
        except (AttributeError, ValueError):
            data = None
    if data and data.get("body") and grounded(data["body"], facts, policy_text, full):
        out.update(engine="ai", subject=(data.get("subject") or "").strip()[:150], body=data["body"].strip())
        if data.get("intent") in INTENTS:
            out["intent"] = data["intent"]
        out["needs_human"] = bool(data.get("needs_human")) or out["needs_human"]
    else:
        if data and data.get("body"):
            out["note"] = "A modell válaszában ellenőrizetlen szám volt, ezért a sablonválaszt adjuk."
        out["subject"] = {"hu": "Re: ", "en": "Re: ", "de": "AW: "}[lang] + (subject or "").strip()[:140]
        out["body"] = template_reply(lang, out["intent"], order, verified, shop_name)
    return out
