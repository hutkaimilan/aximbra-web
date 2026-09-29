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
    "support": "customer service agent that answers routine customer emails from the company's own documents, with sources, and hands everything else to staff",
    "documents": "document analyser that reads contracts, invoices and delivery notes and extracts the fields staff re-type by hand today",
    "compliance": "NIS2 compliance agent that continuously collects the evidence an audit asks for (who can access what, when backups ran, where MFA is missing); it produces evidence, it does not protect against attacks",
    "email": "email triage for shared inboxes: sorts, prioritises and routes incoming mail by morning so staff only has to answer",
    "phone": "telephone AI that answers overflow calls and records the caller's request for staff",
    "leads": "lead qualifier that ranks incoming quote requests: urgent, serious, just comparing prices",
}
PAIN_KEYS = tuple(PAINS)

_GENERIC_PS = {
    "hu": "Ui.: Élő demók az aximbra.hu-n, regisztráció nélkül kipróbálhatók.",
    "other": "tell them live demos are on {site}, no sign-up needed.",
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
    "support": _GENERIC_PS,
    "documents": _GENERIC_PS,
    "compliance": _GENERIC_PS,
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
    "logistics": {
        "hu": "logisztika / szállítmányozás",
        "pain": "Shipment status questions, delivery notes and CMR documents flood a shared inbox; staff re-type data between systems.",
        "signals": "hiring several customer service or dispatcher staff, new warehouse or route, published email response times",
        "value": "status questions answered from their own system data, delivery documents read into structured fields",
    },
    "manufacturing": {
        "hu": "gyártás",
        "pain": "Orders, delivery notes and supplier invoices are re-keyed by hand; NIS2 now covers many manufacturers and the audit evidence is scattered.",
        "signals": "hiring data entry / back-office staff, new plant or line, sector in NIS2 scope, EU-funded expansion",
        "value": "documents read into the ERP fields automatically; NIS2 evidence collected continuously",
    },
    "healthcare": {
        "hu": "magánklinika-hálózat",
        "pain": "Several locations, one call centre; appointment and results questions swamp phone and email, receptionist turnover is high.",
        "signals": "hiring receptionists or call-centre staff, new clinic opening, reviews about unreachable phones",
        "value": "overflow calls answered, routine patient emails answered from their own policies, the rest routed",
    },
    "automotive": {
        "hu": "autókereskedés / márkaszerviz",
        "pain": "Service bookings and sales enquiries come in by phone, email and web; slow answers lose customers to the next dealer.",
        "signals": "hiring service advisors or call-centre staff, new showroom, busy-line notices",
        "value": "enquiries ranked and answered, overflow calls taken, service bookings recorded",
    },
    "finance": {
        "hu": "biztosítási / pénzügyi közvetítő",
        "pain": "Claims, contracts and client documents arrive by email; staff read and re-type the same fields all day.",
        "signals": "hiring back-office or claims staff, NIS2/DORA pressure, growth announcements",
        "value": "contracts and claims read into the fields they need, every value traceable to its source line",
    },
    "property": {
        "hu": "ingatlankezelés / társasházkezelés",
        "pain": "Tenants and owners email and call about the same few issues; urgent faults drown in routine questions.",
        "signals": "hiring customer service or property administrators, stated response times, portfolio growth",
        "value": "the shared inbox sorted by urgency every morning, routine questions answered from their own house rules",
    },
    "ecommerce": {
        "hu": "nagyobb webshop / kereskedelem",
        "pain": "Order, delivery and returns emails pile up in season; the customer service team grows every Q4.",
        "signals": "hiring seasonal customer service staff, stated 1–3 day email response times",
        "value": "routine order and returns questions answered with sources, urgent ones first",
    },
    "hospitality": {
        "hu": "szállodalánc / hotel",
        "pain": "Group, event and availability enquiries by email and phone at all hours; sales staff answer the same questions repeatedly.",
        "signals": "hiring reservation or sales staff, new property, event season",
        "value": "enquiries ranked and drafted by morning, overflow calls answered",
    },
    "energy": {
        "hu": "energetika / közmű-szolgáltató",
        "pain": "Directly in NIS2 scope; audits need continuous evidence, and customer mail volume is high.",
        "signals": "NIS2 scope, hiring compliance or IT security roles, customer service expansion",
        "value": "NIS2 evidence collected continuously; customer mail sorted and routed",
    },
    "it_services": {
        "hu": "IT-szolgáltató",
        "pain": "Tickets and alerts arrive faster than the team triages them; NIS2 makes them part of their clients' supply-chain audits.",
        "signals": "hiring helpdesk or NOC staff, NIS2 supply-chain requirements from clients",
        "value": "tickets and alerts triaged, known issues handled, NIS2 evidence kept ready",
    },
}

SIGNAL_TYPES = ("job_ad", "review", "notice", "opening", "none")


def site_for(lead: dict) -> str:
    """Magyar változathoz a magyar oldal, akárhol van a cég."""
    return "aximbra.hu" if lead["lang"] == "hu" else COUNTRIES[lead["country"]]["site"]


def research_prompt(country: str, count: int, exclude_domains: list[str], focus: str = "") -> str:
    c = COUNTRIES[country]
    excl = ", ".join(exclude_domains[:300]) or "none"
    sectors = "\n".join(f"- {k}: pain = {v['pain']} Buying signals = {v['signals']}." for k, v in SECTORS.items())
    focus_line = f"\nPrioritise these sectors, they reply best so far: {focus}. Still include 1–2 from others to keep learning." if focus else ""
    pains = "\n".join(f"- {k}: {v}" for k, v in PAINS.items())
    return f"""You are a senior B2B sales researcher. Find {count} MID-SIZED to LARGE PRIVATE companies in {c['name']} ({country}), roughly 50–1000 employees, that need what we sell RIGHT NOW.

What we sell (AI agents built into the company's own systems):
{pains}

Sector knowledge:
{sectors}
{focus_line}
Method, like an expert SDR:
1. Start from BUYING SIGNALS, strongest first: the company is hiring several customer service, back-office, data entry, receptionist or dispatcher people at once (their own careers page, or job sites like profession.hu, jobs.hu, cvonline, profesia.sk, ejobs.ro, moj-posao.net, mojedelo.com); the company is in NIS2 scope (energy, transport, logistics, manufacturing of critical products, health, digital providers, waste, food production) and 50+ staff; a new site, plant or clinic; published slow response times.
2. Then quote one sentence word for word (original language) from a page that shows the pain: their own site or careers page, or the job ad itself. It must describe the pain or the workload (hiring for repetitive work, stated response times, overload, many documents, compliance obligation). A generic slogan does NOT qualify.
3. Score fit 0–100: signal strength (active hiring for the repetitive role = strongest), company size (50–1000 ideal), how directly one of our agents removes the pain, and whether a decision can be made locally (a local HQ, not a foreign group's branch).

Exclude: micro businesses under 20 staff, restaurants, cafés, beauty salons, small repair shops, public institutions, state-owned companies, hospitals run by the state, schools, military, multinationals whose decisions are made abroad, and these domains: {excl}.
The email address must be printed on the company's own website (contact page, footer or imprint) and must be a company role address (info@, office@, ugyfelszolgalat@, sales@, kapcsolat@, iroda@ …). Never a private person's address, never a guessed one.

Answer ONLY with a JSON array, no prose, each item:
{{"company": "...", "town": "...", "country": "{country}", "sector": "{'|'.join(SECTORS)}", "website": "https://...", "email": "...", "email_url": "https://... (page where the email is printed)", "observation": "exact sentence copied from their site", "observation_url": "https://...", "pain": "{'|'.join(PAINS)}", "signal": "{'|'.join(SIGNAL_TYPES)}", "signal_note": "one line: what the signal is, e.g. '3 ügyfélszolgálati munkatársat keresnek a karrieroldalukon, 2026-09'", "signal_url": "https://... or empty", "score": 0-100, "score_reason": "one line"}}
Write "score_reason" and "signal_note" in Hungarian, short and plain (the owner reads them on his phone).
Leave out anything you cannot verify. Fewer strong leads beat more weak ones."""


def compose_prompt(lead: dict) -> str:
    lang = lead["lang"]
    site = site_for(lead)
    ps = DEMO_PS[lead["pain"]]["hu" if lang == "hu" else "other"].format(site=site)
    sig = SIGNATURE["hu" if lang == "hu" else "other"].format(site=site)
    sec = SECTORS.get(lead.get("sector") or "", {})
    signal = (lead.get("signal_note") or "").strip()
    return f"""You are an expert cold-email writer for mid-sized and large companies in Central Europe, writing to the person who owns the process (operations, customer service, finance or IT lead). Write one email ENTIRELY in {LANG_NAMES[lang]} — every sentence, the subject, the P.S. — to {lead['company']} ({lead.get('town') or ''}).

Facts you may use (and nothing else):
- Their website says: "{lead['observation']}"
{f'- Buying signal found: {signal}' if signal else ''}
- Their sector's real pain: {sec.get('pain', 'n/a')}
- What we offer: a {PAINS[lead['pain']]}. Concretely: {sec.get('value', PAINS[lead['pain']])}. Built by Milán Hutkai, AXIMBRA.

Proven structure (observation → consequence question → one-line offer → interest question), plain text, formal register, parts separated by one empty line:
1. Greeting ("Jó napot!" in Hungarian, the normal formal greeting otherwise).
2. One sentence with the specific observation ("Láttam, hogy három ügyfélszolgálati munkatársat keresnek." / "Az oldalukon azt írják, hogy…").
3. One question about the business consequence for THEM (headcount that grows with volume, hours spent re-typing, audit evidence scattered). Concrete, no jargon.
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
Write the "issues" in Hungarian, each under 15 words (the owner reads them on his phone).
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
Classify the reply as one of: "no" (not interested, unsubscribe, stop, hostile), "interested" (wants info, price, a call, asks any question about the offer), "auto" (out-of-office or automatic reply), "other".
Answer ONLY with JSON: {{"kind": "no|interested|auto|other"}}"""


def reply_prompt(original: str, reply: str, slots: list[str], lang: str) -> str:
    slot_lines = "\n".join(f"- {s}" for s in slots) or "- (no free slot found: ask them which day suits them)"
    tz_note = " Times are Budapest time (CET/CEST); Romania is one hour ahead, so give their local time too." if lang == "ro" else ""
    return f"""You are Milán Hutkai, founder of AXIMBRA (a small AI agent studio). A business replied with interest to your cold email. Write the answer in the SAME language they wrote in.

Your email:
---
{original[:1500]}
---
Their reply:
---
{reply[:3000]}
---
Rules:
- Answer exactly what they asked, briefly and honestly. If they ask about price: e-mail rendező 150 000–400 000 Ft; érdeklődő-minősítő 400 000–1 200 000 Ft; the telephone AI and anything custom is priced after a 20-minute assessment. Never invent other prices, clients or results.
- Propose a 20-minute call and offer exactly these times (convert the date format naturally into their language):{tz_note}
{slot_lines}
- Ask them to reply with the one that suits them, or suggest another.
- Under 110 words, warm but not salesy, no emojis. Sign "Hutkai Milán · AXIMBRA · aximbra.hu".
Answer ONLY with JSON: {{"body": "..."}}"""
