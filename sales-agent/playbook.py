"""Az értékesítési szabálykönyv: kinek írunk, milyen nyelven, milyen levelet.

Minden, ami a levél tartalmát meghatározza, itt van egy helyen, hogy a
kutató, a levélíró és az ellenőrző ugyanabból a szabályból dolgozzon.
"""

# Ausztria és Németország szándékosan nincs itt: ott a kéretlen üzleti
# e-mail cégeknek is jogsértő (AT: TKG 2021 174. §, DE: UWG 7. §).
COUNTRIES = {
    "HU": {"name": "Magyarország", "lang": "hu", "site": "aximbra.hu"},
    "SK": {"name": "Szlovákia", "lang": "sk", "site": "aximbra.hu/sk"},
    "RO": {"name": "Románia", "lang": "ro", "site": "aximbra.hu/ro"},
    "HR": {"name": "Horvátország", "lang": "hr", "site": "aximbra.hu/en"},
    "SI": {"name": "Szlovénia", "lang": "sl", "site": "aximbra.hu/en"},
}

# A domain végződése alapján is kizárunk: egy .at cím akkor is osztrák cég,
# ha a modell tévedésből magyarnak mondja.
BLOCKED_TLDS = (".at", ".de")

LANG_NAMES = {
    "hu": "Hungarian", "sk": "Slovak", "ro": "Romanian",
    "hr": "Croatian", "sl": "Slovenian",
}

PAINS = {
    "phone": "telephone AI receptionist that answers when nobody can and writes down the booking/appointment/callback details",
    "email": "email triage tool that sorts the incoming mail by morning so staff only has to answer",
    "leads": "lead qualifier that ranks incoming quote requests: urgent, serious, just browsing",
}

DEMO_PS = {
    "phone": {
        "hu": "Ui.: Ha kíváncsi, milyen egy ilyen hívás: az aximbra.hu-n beírja a számát, és a mi telefonos AI-nk 10 másodpercen belül felhívja.",
        "other": "tell them that on {site} they can type in their phone number and our AI calls them within 10 seconds; the demo AI speaks English.",
    },
    "email": {
        "hu": "Ui.: Egy mintapostafiókon ki is próbálható az aximbra.hu-n.",
        "other": "tell them it can be tried on a sample mailbox on {site}.",
    },
    "leads": {
        "hu": "Ui.: Egy minta-érdeklődőn ki is próbálható az aximbra.hu-n.",
        "other": "tell them it can be tried on a sample lead on {site}.",
    },
}

OPT_OUT = {
    "hu": "Ha nem aktuális, egy „nem” válasz elég, többet nem írok.",
    "sk": "Ak to momentálne nie je aktuálne, stačí krátke „nie“ — viac vám nenapíšem.",
    "ro": "Dacă acum nu este de actualitate, un simplu „nu” este suficient — nu vă mai scriu.",
    "hr": "Ako vam to trenutačno nije zanimljivo, dovoljan je kratak „ne” — neću vam više pisati.",
    "sl": "Če vam to trenutno ni zanimivo, zadošča kratek »ne« — ne bom vam več pisal.",
}

SIGNATURE = {
    "hu": "Hutkai Milán · AXIMBRA · {site}",
    "other": "Milán Hutkai · AXIMBRA · {site}",
}

FOLLOW_UP = {
    "hu": "Jó napot!\n\nCsak azért írok még egyszer, hátha elsikkadt az előző levelem. Ha nem aktuális, egy „nem” válasz elég, és többet nem írok.\n\nHutkai Milán · AXIMBRA · aximbra.hu",
    "sk": "Dobrý deň,\n\npíšem ešte raz, keby sa môj predchádzajúci e-mail stratil. Ak to nie je aktuálne, stačí krátke „nie“ a viac vám nenapíšem.\n\nMilán Hutkai · AXIMBRA · aximbra.hu/sk",
    "ro": "Bună ziua,\n\nVă mai scriu o dată, în caz că mesajul meu anterior s-a pierdut. Dacă nu este de actualitate, un simplu „nu” este suficient și nu vă mai scriu.\n\nMilán Hutkai · AXIMBRA · aximbra.hu/ro",
    "hr": "Poštovani,\n\npišem još jednom, za slučaj da se moja prethodna poruka izgubila. Ako vam nije zanimljivo, dovoljan je kratak „ne” i neću vam više pisati.\n\nMilán Hutkai · AXIMBRA · aximbra.hu/en",
    "sl": "Pozdravljeni,\n\npišem še enkrat, za primer, da se je moje prejšnje sporočilo izgubilo. Če vam ni zanimivo, zadošča kratek »ne« in vam ne bom več pisal.\n\nMilán Hutkai · AXIMBRA · aximbra.hu/en",
}

MAX_WORDS = 110  # a törzs + aláírás + ui. + leiratkozás együtt; maga az üzenet 75 alatt

# Iparági tudás: mi fáj nekik valójában, milyen jel mutatja, hogy most fáj,
# és melyik mondat szól a saját nyelvükön. A kutató és a levélíró is ebből dolgozik.
SECTORS = {
    "restaurant": {
        "hu": "étterem",
        "pain": "Evening and weekend rush: the phone rings while every hand is serving; missed calls are lost tables that book elsewhere within minutes.",
        "signals": "phone-only or same-day phone-only booking, limited phone hours, reviews saying nobody answers, hiring a host/waiter who also takes calls",
        "value": "the AI picks up during the rush and writes down name, party size, time and phone number",
    },
    "dental": {
        "hu": "fogászat / magánrendelő",
        "pain": "Staff are chairside during treatment; the phone rings out and new patients call the next clinic. Receptionist turnover is high.",
        "signals": "appointments only by phone, 'we call you back' after online requests, hiring a receptionist/assistant, reviews about unreachable phone",
        "value": "the AI answers during treatment and writes down who wants to come, when and why",
    },
    "auto": {
        "hu": "autószerviz",
        "pain": "Mechanics are under the car; calls go unanswered or the callback starts with a second interrogation about make, model and fault.",
        "signals": "booking only by phone, 'if busy we call back', overbooked notices, seasonal tyre-change rush",
        "value": "the AI answers and writes down make, model, fault and callback number",
    },
    "beauty": {
        "hu": "szépségszalon / fodrász",
        "pain": "Hands are busy with clients; bookings and rescheduling calls interrupt work or get missed.",
        "signals": "booking only by phone or Messenger, 'we call you back', one-person salons with long hours",
        "value": "the AI takes the booking or rescheduling while hands are busy",
    },
    "hospitality": {
        "hu": "szállás / panzió",
        "pain": "Enquiries arrive by phone and email at all hours; answering the same questions about availability and prices eats the day.",
        "signals": "stated email reply times, 'call us for availability', event/group enquiries only by phone",
        "value": "enquiries are sorted and answered drafts are ready by morning; the phone AI takes availability questions",
    },
    "trades": {
        "hu": "szerelő / kivitelező / klíma",
        "pain": "Quote requests pile up in season; nobody knows which caller is urgent, serious, or just comparing prices.",
        "signals": "callback within 24/48 hours promises, seasonal backlog notices, long quote forms",
        "value": "the lead qualifier ranks every request: urgent, serious, just browsing",
    },
    "webshop": {
        "hu": "webshop / kereskedés",
        "pain": "Order, delivery and warranty emails mix in one inbox; urgent ones drown under routine questions.",
        "signals": "stated email reply times (1–3 working days), email-first customer service, busy-line notices",
        "value": "the email triage sorts the inbox by morning so staff only has to answer",
    },
}

SIGNAL_TYPES = ("job_ad", "review", "notice", "opening", "none")


def research_prompt(country: str, count: int, exclude_domains: list[str], focus: str = "") -> str:
    c = COUNTRIES[country]
    excl = ", ".join(exclude_domains[:300]) or "none"
    sectors = "\n".join(f"- {k}: pain = {v['pain']} Buying signals = {v['signals']}." for k, v in SECTORS.items())
    focus_line = f"\nPrioritise these sectors, they reply best so far: {focus}. Still include 1–2 from others to keep learning." if focus else ""
    return f"""You are a senior B2B sales researcher. Find {count} small or medium PRIVATE businesses in {c['name']} ({country}) that need what we sell RIGHT NOW.

What we sell: a telephone AI receptionist, an email triage tool, and a lead qualifier — built for small businesses.

Sector knowledge:
{sectors}
{focus_line}
Method, like an expert SDR:
1. Start from BUYING SIGNALS, strongest first: a current job ad for a receptionist / customer service / booking person (search job sites like profession.hu, jobs.hu, cvonline, profesia.sk, ejobs.ro, moj-posao.net, mojedelo.com); public reviews complaining that nobody answers the phone; a notice on their site about overload, busy lines or limited phone hours; a new location opening.
2. Then confirm on the business's OWN WEBSITE a sentence that states the pain (quote it word for word, original language). The quoted sentence must itself describe the pain: bookings only by phone, busy line / call back, limited phone hours, replies take days, overload. A generic promise ("we repair within 24 hours", "we reply as soon as possible") or a complaints page does NOT qualify.
3. If the site says phone lines are often busy or unreachable, the pain is "phone", even if it also mentions email.
4. Score fit 0–100: signal strength (job ad/review = strongest), how clearly the pain is stated, size (5–50 staff ideal), whether our tool removes the pain directly.

Exclude: public institutions, state hospitals, schools, military, big chains, franchises with central call centers, businesses already solving the exact pain with online booking, and these domains: {excl}.
The email address must be printed on the business's own website (contact page, footer or imprint). Prefer generic addresses (info@, office@, hello@, recepcio@, a business gmail shown on the site). Never guess an address.

Answer ONLY with a JSON array, no prose, each item:
{{"company": "...", "town": "...", "country": "{country}", "sector": "{'|'.join(SECTORS)}", "website": "https://...", "email": "...", "email_url": "https://... (page where the email is printed)", "observation": "exact sentence copied from their site", "observation_url": "https://...", "pain": "phone|email|leads", "signal": "{'|'.join(SIGNAL_TYPES)}", "signal_note": "one line: what the signal is, e.g. 'recepciós álláshirdetés a profession.hu-n, 2026-09'", "signal_url": "https://... or empty", "score": 0-100, "score_reason": "one line"}}
Leave out anything you cannot verify. Fewer strong leads beat more weak ones."""


def compose_prompt(lead: dict) -> str:
    lang = lead["lang"]
    site = COUNTRIES[lead["country"]]["site"]
    ps = DEMO_PS[lead["pain"]]["hu" if lang == "hu" else "other"].format(site=site)
    sig = SIGNATURE["hu" if lang == "hu" else "other"].format(site=site)
    sec = SECTORS.get(lead.get("sector") or "", {})
    signal = (lead.get("signal_note") or "").strip()
    return f"""You are an expert cold-email writer for small-business B2B in Central Europe. Write one email in {LANG_NAMES[lang]} to {lead['company']} ({lead.get('town') or ''}).

Facts you may use (and nothing else):
- Their website says: "{lead['observation']}"
{f'- Buying signal found: {signal}' if signal else ''}
- Their sector's real pain: {sec.get('pain', 'n/a')}
- What we offer: a {PAINS[lead['pain']]}. Concretely: {sec.get('value', PAINS[lead['pain']])}. Built by Milán Hutkai, AXIMBRA.

Proven structure (observation → consequence question → one-line offer → interest question), plain text, formal register, parts separated by one empty line:
1. Greeting ("Jó napot!" in Hungarian, the normal formal greeting otherwise).
2. One sentence restating what their site says ("Az oldalukon azt írják, hogy…"). If there is a job-ad signal, you may mention it instead ("Láttam, hogy recepcióst keresnek.").
3. One question about the concrete consequence for THEM (lost bookings, the next clinic/service gets the call, a second round of questions at callback). Make them picture the moment.
4. One sentence: "Építettem egy …" / "I built a …" — our tool in their exact situation, naming what it writes down or sorts.
5. The question "Would this be interesting for you?" in {LANG_NAMES[lang]}.
6. Signature line exactly: {sig}
7. A postscript (P.S.) in {LANG_NAMES[lang]}: {ps}
8. Last line exactly: {OPT_OUT[lang]}

Rules: parts 1–5 together under 75 words. You-focused, not we-focused. No prices, no links, no hype ("revolutionary", "cutting-edge"), no urgency, no claims about clients or results, no emojis, no flattery.
Subject: 3–5 words about THEIR situation, lowercase except the first word, no punctuation tricks.

Answer ONLY with JSON: {{"subject": "...", "body": "..."}}"""


def critique_prompt(lead: dict, subject: str, body: str) -> str:
    return f"""You are a demanding cold-email reviewer. Review this {LANG_NAMES[lead['lang']]} email to {lead['company']}.

Subject: {subject}
---
{body}
---
Their website says: "{lead['observation']}"

Score 0–10 against: (a) the first lines are specific to THIS business, not generic; (b) exactly one consequence question the reader can picture; (c) the offer is one concrete sentence; (d) parts before the signature under 75 words; (e) no hype, no price, no link, no flattery, no claims about clients; (f) natural, native {LANG_NAMES[lead['lang']]} a local business owner would not find odd; (g) signature, P.S. and the last opt-out line kept exactly.
If the score is below 9, rewrite it fixing every issue, keeping the same structure and the signature, P.S. and opt-out line unchanged.
Answer ONLY with JSON: {{"score": 0-10, "issues": ["..."], "subject": "...", "body": "..."}}"""


def classify_prompt(original: str, reply: str) -> str:
    return f"""We sent this cold email:
---
{original[:1500]}
---
They replied:
---
{reply[:3000]}
---
Classify the reply as one of: "no" (not interested, unsubscribe, stop, hostile), "interested" (wants info, price, call, asks a question), "auto" (out-of-office or automatic reply), "other".
If "interested", also draft a short answer in the same language: answer exactly what they asked, propose a 20-minute call, never state a price that is not one of: e-mail rendező 150 000–400 000 Ft, érdeklődő-minősítő 400 000–1 200 000 Ft; for the phone AI say the price comes after a 20-minute assessment. Sign "Hutkai Milán · AXIMBRA · aximbra.hu".
Answer ONLY with JSON: {{"kind": "no|interested|auto|other", "suggestion": "..."}}"""
