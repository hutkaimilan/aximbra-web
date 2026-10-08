"""Az értékesítési szabálykönyv: kinek írunk, milyen nyelven, milyen levelet.

Minden, ami a levél tartalmát meghatározza, itt van egy helyen, hogy a
kutató, a levélíró és az ellenőrző ugyanabból a szabályból dolgozzon.
"""

# Az oldal nyelvei: magyar, angol, német, spanyol, francia, olasz, román,
# szlovák, kínai. Csak oda írunk, ahol cégnek kéretlen üzleti e-mailt
# leiratkozási lehetőséggel küldeni szabad:
#  - Ausztria és Németország soha (AT: TKG 2021 174. §, DE: UWG 7. §),
#    Svájc és Liechtenstein sem (CH: UWG 3. cikk o) pont) — így a német nyelv kimarad.
#  - Spanyolország nem: az LSSI 21. cikke cégeknek is előzetes hozzájárulást kér.
#  - Olaszország nem: a Garante szerint cégeknek is hozzájárulás kell (Codice privacy 130.).
#  - Kínai nyelvterület nem: más jogrend, nem a piacunk.
#  - Egyesült Királyság (PECR: cégeknek szabad), Írország (cégeknek szabad
#    leiratkozással), Franciaország (CNIL: a szakmájához kapcsolódó ajánlat szabad),
#    Belgium (csak személytelen céges cím, pl. info@ — mi amúgy is csak ilyenre írunk).
COUNTRIES = {
    "HU": {"name": "Magyarország", "lang": "hu", "site": "aximbra.hu"},
    "SK": {"name": "Szlovákia", "lang": "sk", "site": "aximbra.hu/sk"},
    "RO": {"name": "Románia", "lang": "ro", "site": "aximbra.hu/ro"},
    "HR": {"name": "Horvátország", "lang": "hr", "site": "aximbra.hu/en"},
    "SI": {"name": "Szlovénia", "lang": "sl", "site": "aximbra.hu/en"},
    "GB": {"name": "Egyesült Királyság", "lang": "en", "site": "aximbra.hu/en"},
    "IE": {"name": "Írország", "lang": "en", "site": "aximbra.hu/en"},
    "FR": {"name": "Franciaország", "lang": "fr", "site": "aximbra.hu/fr"},
    "BE": {"name": "Belgium (francia nyelvű rész: Vallónia, Brüsszel)", "lang": "fr", "site": "aximbra.hu/fr"},
}

# A domain végződése alapján is kizárunk: egy .at cím akkor is osztrák cég,
# ha a modell tévedésből magyarnak mondja. Ugyanígy a tiltott országoké.
BLOCKED_TLDS = (".at", ".de", ".ch", ".li", ".es", ".it")

LANG_NAMES = {
    "hu": "Hungarian", "sk": "Slovak", "ro": "Romanian",
    "hr": "Croatian", "sl": "Slovenian", "en": "English", "fr": "French",
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
    "en": "If this is not relevant right now, a short “no” is enough and I will not write again.",
    "fr": "Si ce n’est pas d’actualité, un simple « non » suffit et je ne vous écrirai plus.",
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
    "en": "Hello,\n\nI am writing once more in case my previous email got lost. If it is not relevant, a short “no” is enough and I will not write again.\n\nMilán Hutkai · AXIMBRA · aximbra.hu/en",
    "fr": "Bonjour,\n\nJe vous écris une dernière fois, au cas où mon précédent message se serait perdu. Si ce n’est pas d’actualité, un simple « non » suffit et je ne vous écrirai plus.\n\nMilán Hutkai · AXIMBRA · aximbra.hu/fr",
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
1. Any company qualifies that could realistically put one of our agents to work: shared customer inboxes, a customer service or call centre team, many documents (orders, invoices, contracts, delivery notes), several locations, lots of incoming enquiries, or NIS2 obligations. A stated problem is NOT required.
2. Quote one specific FACT word for word (original language) from the company's own website that shows which agent fits: their customer service hours or channels, number of locations, volume ("5000 shipments a month"), the documents they handle, the enquiries they receive, their NIS2 sector. A generic slogan ("quality is our priority") does NOT qualify.
3. Buying signals are not required, but a letter built on a current, verified signal gets several times more
   replies than one without, so look hard for one and prefer those companies: hiring several people for repetitive work (their careers page or the country's job sites, e.g. profession.hu, jobs.hu, cvonline, profesia.sk, ejobs.ro, moj-posao.net, mojedelo.com, reed.co.uk, irishjobs.ie, welcometothejungle.com, francetravail.fr, stepstone.be), a new site or plant, NIS2 scope, growth news.
4. Score fit 0–100: how clearly one specific agent maps to that fact, company size (50–1000 ideal), local decision-making (a local HQ, not a foreign group's branch), and a buying signal (a verified, recent one is worth about 10–15 points).

Exclude: micro businesses under 20 staff, restaurants, cafés, beauty salons, small repair shops, public institutions, state-owned companies, hospitals run by the state, schools, military, multinationals whose decisions are made abroad, and these domains: {excl}.
The email address must be printed on the company's own website (contact page, footer or imprint) and must be a company role address (info@, office@, ugyfelszolgalat@, sales@, kapcsolat@, iroda@ …). Never a private person's address, never a guessed one.

Answer ONLY with a JSON array, no prose, each item:
{{"company": "...", "town": "...", "country": "{country}", "sector": "{'|'.join(SECTORS)}", "website": "https://...", "email": "...", "email_url": "https://... (page where the email is printed)", "observation": "exact sentence copied from their site (the fact)", "observation_url": "https://...", "pain": "{'|'.join(PAINS)}", "signal": "{'|'.join(SIGNAL_TYPES)}", "signal_note": "one line: what the signal is, e.g. '3 ügyfélszolgálati munkatársat keresnek a karrieroldalukon, 2026-09'", "signal_url": "https://... or empty", "score": 0-100, "score_reason": "one line"}}
Write "score_reason" and "signal_note" in Hungarian, short and plain (the owner reads them on his phone).
Leave out anything you cannot verify. Fewer strong leads beat more weak ones."""


# Kutatással alátámasztott levélírási szabályok. A levélíró és a bíráló is
# ebből dolgozik; a gépileg mérhető részét a verify.check_letter nézi.
#  - Rövid, egyszerű nyelv: az egyszerű szóhasználatú, rövid mondatos hideg
#    levelekre jóval többen válaszolnak (Boomerang, több millió levél elemzése;
#    feldolgozási könnyedség: Reber & Schwarz).
#  - Személyre szabás a cég saját tényéből: a konkrétum hihetőbb és figyelmet
#    kelt (Hansen & Wänke; hidegmegkeresési A/B-elemzések).
#  - Egy kérdés, amire egy szóval lehet felelni, időpontkérés helyett: az
#    érdeklődésre rákérdező zárás több választ hoz, mint a hívásra kérés
#    (Gong levélelemzések; a döntési teher csökkentése: Iyengar & Lepper).
#  - A veszteség a nyereségnél erősebben hat, ezért a következményt
#    kérdezzük meg — feltételezésként, kitalált szám nélkül (Kahneman & Tversky).
#  - Vásárlási jel (álláshirdetés, új telephely, növekedés): a jelre épülő levélre
#    többszörös a válasz (Martal, Hunter.io elemzések) -> a kutató előre sorolja,
#    a magától küldés előbb ezeket küldi.
#  - Tárgysor: 2–4 szó, a címzett helyzetéről; kérdés is lehet (Belkins, 5,5 M levél).
#  - Kiszállási sor: elsősorban a szabályosság és a kézbesíthetőség miatt van
#    (kevesebb spamjelentés). A „szabadon nemet mondhat” technika szemtől
#    szemben erős, online a metaelemzés szerint alig hat (Carpenter 2013).
#  - Egy utánkövetés: a kétlevelű sor hozza a legtöbb választ, a harmadik levél
#    már csökkenti, a 4+ többszörösére növeli a leiratkozást és a spamjelentést
#    (Belkins 2025). Ezért pontosan egy utánkövetés van.
#  - A vevők nagy része eladó nélkül szeretne tájékozódni (Gartner 2025–26), ezért
#    az ui. mindig a regisztráció nélkül kipróbálható élő demóra mutat.
#  - Gyors válasz: aki egy órán belül válaszol az érdeklődőre, hétszer nagyobb
#    eséllyel jut tovább (HBR, 2,24 M érdeklődő) -> félóránkénti válaszfigyelés.
#  - Ha válaszolt, onnan konkrét időpontot kérünk: az üzleti ciklusban a konkrét
#    kérés működik jobban (Gong).
#  - A következmény-kérdés a SPIN „implikációs” kérdése: a legjobb eladók négyszer
#    annyit kérdeznek így (Rackham, 35 000 üzleti beszélgetés); ha van rá, egy
#    nem nyilvánvaló iparági felismeréssel (Challenger, CEB: 6000 értékesítő).
#  - A potenciális vevők ~95%-a most nem vásárol (LinkedIn B2B Institute): a hang
#    udvarias és emlékezetes, sosem nyomulós — később ők a vevők.
MAX_SENTENCE_WORDS = 25


def compose_prompt(lead: dict) -> str:
    lang = lead["lang"]
    site = site_for(lead)
    ps = DEMO_PS[lead["pain"]]["hu" if lang == "hu" else "other"].format(site=site)
    sig = SIGNATURE["hu" if lang == "hu" else "other"].format(site=site)
    sec = SECTORS.get(lead.get("sector") or "", {})
    signal = (lead.get("signal_note") or "").strip()
    return f"""You are an expert cold-email writer for mid-sized and large companies in Central Europe, writing to the person who owns the process (operations, customer service, finance or IT lead). Write one email ENTIRELY in {LANG_NAMES[lang]} — every sentence, the subject, the P.S. — to {lead['company']} ({lead.get('town') or ''}).

Facts you may use (and nothing else):
- A fact from their website: "{lead['observation']}"
{f'- Buying signal found: {signal}' if signal else ''}
- Their sector's real pain: {sec.get('pain', 'n/a')}
- What we offer: a {PAINS[lead['pain']]}. Concretely: {sec.get('value', PAINS[lead['pain']])}. Built by Milán Hutkai, AXIMBRA.

Proven structure (observation → consequence question → one-line offer → interest question), plain text, formal register, parts separated by one empty line:
1. Greeting ("Jó napot!" in Hungarian, the normal formal greeting otherwise).
2. One sentence with that specific fact ("Láttam, hogy 12 telephelyük van." / "Az oldalukon azt írják, hogy…").
3. One question that turns the fact into a likely workload for THEM, as a hypothesis, not an accusation ("Ennyi telephelynél gondolom sok ugyanolyan kérdés fut be naponta — ezt most kézzel válaszolják meg?"). Concrete, no jargon.
4. One sentence: "Építettem egy …" / "I built a …" — our tool in their exact situation, naming what it writes down or sorts.
5. The question "Would this be interesting for you?" in {LANG_NAMES[lang]}.
6. Signature line exactly: {sig}
7. A postscript (P.S.) in {LANG_NAMES[lang]}: {ps}
8. Last line exactly: {OPT_OUT[lang]}

Proven writing rules: short sentences (max 20 words each), everyday words a 12-year-old understands, no
abstract nouns where a concrete one exists; the closing question must be answerable with a single word; frame the
consequence question around what they lose today, as a guess, never with a made-up number. If the sector
knowledge offers a non-obvious insight about where the hidden cost is, use it in that question — teach them
something about their own process instead of describing ours.

Never name or describe individual employees (no personal names, no "X's position"); talk about the company, its team or its processes.
Rules: parts 1–5 together under 75 words. You-focused, not we-focused. No prices, no links, no hype ("revolutionary", "cutting-edge"), no urgency, no claims about clients or results, no emojis, no flattery.
Subject: 2–4 words about THEIR situation (a short question is fine), lowercase except the first word, no punctuation tricks.

Answer ONLY with JSON: {{"subject": "...", "body": "..."}}"""


def critique_prompt(lead: dict, subject: str, body: str) -> str:
    return f"""You are a demanding cold-email reviewer. Review this {LANG_NAMES[lead['lang']]} email to {lead['company']}.

Subject: {subject}
---
{body}
---
Their website says: "{lead['observation']}"

Score 0–10 against: (a) the first lines are specific to THIS business, not generic; (b) exactly one consequence question the reader can picture; (c) the offer is one concrete sentence; (d) parts before the signature under 75 words; (e) no hype, no price, no link, no flattery, no claims about clients, no named individuals; (f) natural, native {LANG_NAMES[lead['lang']]} a local business owner would not find odd; (g) signature, P.S. and the last opt-out line kept exactly; (h) easy to read: every sentence under 20 words, everyday words, the closing question answerable with one word.
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
    tz_note = " Times are Budapest time (CET/CEST); Romania is one hour ahead, so give their local time too." if lang == "ro" \
        else " Times are Budapest time (CET/CEST); the UK and Ireland are one hour behind, so give their local time too." if lang == "en" else ""
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


def list_prompt(country: str, count: int, exclude_domains: list[str], focus: str = "") -> str:
    c = COUNTRIES[country]
    excl = ", ".join(exclude_domains[:300]) or "none"
    sectors = ", ".join(f"{k} ({v['hu']})" for k, v in SECTORS.items())
    focus_line = f" Prefer these sectors: {focus}." if focus else ""
    return f"""List {count} REAL private companies headquartered in {c['name']} ({country}) with roughly 50–1000 employees,
in these sectors: {sectors}.{focus_line}
Only companies you are confident exist, with their official website. Prefer locally owned companies (decisions made in {c['name']}),
spread across different towns, not only the capital. Exclude state-owned companies, public institutions, multinationals' branches,
and these domains: {excl}.
Answer ONLY with a JSON array: [{{"company": "...", "town": "...", "sector": "{'|'.join(SECTORS)}", "website": "https://..."}}]"""


def fact_prompt(company: dict, pages: str, emails: list[str]) -> str:
    pains = "\n".join(f"- {k}: {v}" for k, v in PAINS.items())
    return f"""You are a senior B2B sales researcher. Below is text from the website of {company.get('company')} ({company.get('town', '')}).

Our agents:
{pains}

From the text, pick ONE specific fact, copied WORD FOR WORD from the text (original language, 8–40 words), that shows which agent fits:
customer service hours or channels, number of locations, volumes, documents they handle, enquiries they receive, hiring for repetitive roles, NIS2 sector.
A generic slogan does not qualify, and neither does a sentence that names individual employees. If nothing specific is in the text, answer {{"skip": true}}.

Company role email addresses found on the site (choose the best one for a first business contact): {", ".join(emails)}

Score fit 0–100: how clearly one agent maps to the fact, company size (50–1000 ideal), local decision-making.
Answer ONLY with JSON:
{{"observation": "the exact copied sentence", "observation_url": "the URL of the page it is on", "email": "one of the listed addresses",
"pain": "{'|'.join(PAINS)}", "signal": "{'|'.join(SIGNAL_TYPES)}", "signal_note": "short, in Hungarian", "score": 0-100, "score_reason": "short, in Hungarian"}}

WEBSITE TEXT:
{pages}"""


# ---- a tartalomtémák névsora -------------------------------------------------

# Az aximbra.hu tizenöt agentkártyája, ugyanabban a sorrendben. A napi
# tartalomtéma ebből a listából kap egy agentet, körbe — enélkül a modell
# magától mindig a legkézenfekvőbbre (e-mail rendező) írt, és a lista vége
# soha nem került sorra.
#
# Ár és átfutás szándékosan NINCS itt: a poszt úgysem árazhat, és egy
# második árlista előbb-utóbb elcsúszna az oldalétól (az az AXIMBRA_FACTS).
# Itt csak az van, ami egy témához kell: a név és a helyzet, amit megold.
AGENTS = (
    {"key": "email", "hu": "E-mail rendező", "en": "Email sorter",
     "hu_what": "a közös postafiókot reggelre kategóriába sorolja, sürgősséget állapít meg, és megmondja, kihez tartozik",
     "en_what": "sorts a shared inbox by morning: categories, urgency, and who each message belongs to"},
    {"key": "leads", "hu": "Érdeklődő-minősítő", "en": "Lead qualifier",
     "hu_what": "végignézi a beérkező érdeklődést, pontozza, és megmondja, mit érdemes vele kezdeni — ma vagy három hónap múlva",
     "en_what": "reviews incoming leads, scores them, and says what to do with each — today or in three months"},
    {"key": "admin", "hu": "Belső admin agent", "en": "Internal admin agent",
     "hu_what": "adatot visz át rendszerek között, jelentést állít össze, űrlapot tölt ki — a láthatatlan munka",
     "en_what": "moves data between systems, compiles reports, fills out forms — the invisible work"},
    {"key": "research", "hu": "Kutatási monitor", "en": "Research monitor",
     "hu_what": "figyeli a versenytársakat, a jogszabályt vagy a piacot, és csak akkor szól, ha valóban történt valami",
     "en_what": "watches competitors, regulation or the market, and only speaks up when something actually happened"},
    {"key": "support", "hu": "Ügyfélszolgálati agent", "en": "Customer support agent",
     "hu_what": "a cég saját dokumentumaiból válaszol, forrásmegjelöléssel; amit nem tud, átadja embernek",
     "en_what": "answers from the company's own documents, with sources; what it doesn't know, it hands to a human"},
    {"key": "content", "hu": "Tartalom-agent", "en": "Content agent",
     "hu_what": "egy hangnemre betanítva ír hírlevelet, termékleírást, közösségi posztot; a jóváhagyás a cégnél marad",
     "en_what": "writes newsletters, product copy and social posts in one trained voice; approval stays with the company"},
    {"key": "webshop", "hu": "Webshop-asszisztens", "en": "Webshop assistant",
     "hu_what": "megválaszolja a vásárlói leveleket (hol a csomag, visszaküldés, számla), a rendelést a webshopból keresi ki",
     "en_what": "answers customer emails (where is my parcel, returns, invoices) and looks the order up in the shop"},
    {"key": "documents", "hu": "Dokumentum-elemző", "en": "Document analyzer",
     "hu_what": "szerződést, számlát, ajánlatot olvas, és kiszedi belőle azt a néhány mezőt, amiért eddig valaki végigolvasta",
     "en_what": "reads contracts, invoices and quotes and pulls out the few fields someone used to read the whole thing for"},
    {"key": "finance", "hu": "Pénzügyi asszisztens", "en": "Financial assistant",
     "hu_what": "költséget kategorizál, eltérést jelez, riportot állít össze; minden állítás mögött ott a forrássor",
     "en_what": "categorizes costs, flags anomalies, compiles reports; every statement has a source line behind it"},
    {"key": "recruiting", "hu": "Toborzási agent", "en": "Recruitment agent",
     "hu_what": "önéletrajzot előszűr strukturált szempontok szerint, audit-naplóval és emberi felülbírálattal (EU AI Act)",
     "en_what": "pre-screens CVs by structured criteria, with an audit log and human override (EU AI Act)"},
    {"key": "itops", "hu": "IT-üzemeltető agent", "en": "IT operations agent",
     "hu_what": "logot néz, riasztást osztályoz, ismert hibára lefuttatja a javítást; amit nem ismer, azzal felébreszti az ügyeletest",
     "en_what": "watches logs, classifies alerts, runs the fix for known issues, and wakes the on-call for the rest"},
    {"key": "multi", "hu": "Multi-agent rendszer", "en": "Multi-agent system",
     "hu_what": "több agent egy folyamaton, átadásokkal és ellenőrzési pontokkal; akkor van értelme, ha a folyamat tényleg összetett",
     "en_what": "several agents in one process, with handoffs and checkpoints; worth it only when the process is genuinely complex"},
    {"key": "nis2", "hu": "NIS2-megfelelési agent", "en": "NIS2 compliance agent",
     "hu_what": "folyamatosan gyűjti, amit az audit kér: ki fér hozzá mihez, mikor volt mentés, hol hiányzik a kétlépcsős belépés — támadás ellen NEM véd",
     "en_what": "continuously collects what the audit asks for: who can reach what, when backups ran, where MFA is missing — it does NOT protect against attacks"},
    {"key": "sales", "hu": "Értékesítő agent", "en": "Sales agent",
     "hu_what": "megkeresi az illeszkedő cégeket, elolvassa az oldalukat, és mindegyiknek egy valódi megfigyelésre épülő rövid levelet ír",
     "en_what": "finds companies that fit, reads their websites, and writes each one a short letter built on one real observation"},
    {"key": "custom", "hu": "Egyedi agent", "en": "Custom agent",
     "hu_what": "ami nincs a listán: ha a feladat reális, a cég saját folyamatára épül meg; ha nem reális, azt mondjuk meg",
     "en_what": "what isn't on the list: if the task is realistic we build it for the company's own process, and if it isn't we say so"},
)


# ---- tanácsadó ---------------------------------------------------------------

# Az árak és határidők az aximbra.hu-ról valók (ugyanaz a lista, amit a
# telefonos agent mond). Máshonnan a tanácsadó sem vehet számot.
AXIMBRA_FACTS = """AXIMBRA: egyszemélyes AI agent stúdió, alapító Hutkai Milán, aximbra.hu, aximbra@gmail.com.
Cégeknek épít egyedi AI agenteket a saját rendszereikbe. Az oldalon élő demók vannak regisztráció nélkül
(e-mail rendező mintapostafiókon, érdeklődő-minősítő, telefonos AI, ami 10 másodpercen belül visszahív).
Piac: Magyarország elsősorban, Szlovákia, Románia, Horvátország, Szlovénia. Ausztriába és Németországba kéretlen levél tilos.
Agentek, nettó ár, átfutás:
- E-mail rendező: 150–400 ezer Ft, 2–4 hét
- Érdeklődő-minősítő: 400 ezer–1,2 millió Ft, 3–5 hét
- Belső adminisztrációs agent: 150–400 ezer Ft, 2–4 hét
- Kutató/figyelő agent: 150–400 ezer Ft, 2–4 hét
- Ügyfélszolgálati agent: 1,5–4 millió Ft, 6–10 hét
- Tartalomgyártó agent: 400 ezer–1,2 millió Ft, 2–3 hét
- Webshop-asszisztens: 600 ezer–1,5 millió Ft, 3–5 hét
- Dokumentumelemző: 2–4 millió Ft, 6–8 hét
- Pénzügyi asszisztens: 2–4 millió Ft, 6–8 hét
- Toborzó agent: 1,7–3,9 millió Ft, 3–4 hét + jogi átnézés
- IT-üzemeltetési agent: 600 ezer–2 millió Ft, 3–6 hét
- NIS2 megfelelőségi agent: 600 ezer–2 millió Ft, 4–8 hét (bizonyítékot gyűjt az audithoz, támadás ellen NEM véd)
- Értékesítő agent: 600 ezer–1,5 millió Ft, 3–5 hét
- Több agentes rendszer: 6–15 millió Ft, 10–16 hét
- Egyedi agent: nincs fix ár, 20 perces felmérés után árazzuk
- Weboldal: egyoldalas 120 ezer Ft (3–5 nap), többoldalas 290 ezer Ft (1–2 hét), egyedi/AI-integrált 900 ezer Ft-tól
Jelenlegi helyzet: induló vállalkozás, még nincs fizető referencia-ügyfél, a marketingköltség most minimális."""


def advisor_plan_prompt(question: str, history: str) -> str:
    return f"""You decide what to look up on the web before answering a sales/marketing question for AXIMBRA (a Hungarian AI agent studio).

Conversation so far (may be empty):
{history or "-"}

New question: {question}

Search when the answer depends on facts you may not know or that change: a company, person, product, platform, tool, price,
market data, trend, law, competitor, or anything the user refers to that you do not recognise. Do NOT search for general
technique questions you can answer well from knowledge. Write queries in the language that finds the best results (Hungarian for Hungarian topics).
Answer ONLY with JSON: {{"queries": ["at most 3 search queries"], "reason": "short"}}"""


def advisor_prompt(question: str, history: str, context: str, sources: list[dict], searched: bool) -> str:
    src = "\n\n".join(f"[{i}] {s['title']} — {s['url']}\n{s['text']}" for i, s in enumerate(sources, 1))
    web = (f"WEB SOURCES (cite them as [1], [2] where you use them):\n{src}" if sources else
           "No web sources are available for this question." + (
               " A search was attempted but returned nothing: say so in one line if the answer depends on current facts."
               if searched else ""))
    return f"""Te az AXIMBRA vezető értékesítési és marketing tanácsadója vagy: B2B értékesítés, founder-led sales, cold outreach,
LinkedIn, videómarketing, ajánlatírás, tárgyalás, árazás, ellenvetés-kezelés, pozicionálás. Hutkai Milánnak dolgozol, aki egyedül viszi a céget.

MIT TUDSZ A CÉGRŐL:
{AXIMBRA_FACTS}

AZ ÉRTÉKESÍTŐ AGENT ADATAI (valós, a saját rendszerünkből):
{context}

{web}

Eddigi beszélgetés:
{history or "-"}

KÉRDÉS: {question}

SZABÁLYOK:
- Magyarul válaszolj, tegezve, tömören. Az elején a lényeg, utána a konkrétumok. Nincs bevezető, nincs dicséret.
- Kész, használható anyagot adj: forgatókönyvet jelenetekre bontva másodpercekkel, kész posztszöveget, kész levelet, hívásvázlatot
  kérdésekkel, ellenvetésre szó szerinti választ. Ne általánosságot („legyél hiteles”).
- Módszert nevesíts és indokolj (pl. SPIN, Challenger, Jobs-to-be-done, problem-agitate-solve, hook–demo–proof–CTA), de csak ha tényleg illik.
- SOHA ne találj ki ügyfelet, referenciát, esettanulmányt, véleményt, számot vagy eredményt. Nincs még fizető ügyfél: ha bizonyíték kell,
  az élő demó, a saját agentek működése és a pilot-ajánlat a bizonyíték. Ha egy módszerhez kitalált adat kellene, mondd meg, mit kell előbb összegyűjteni.
- Árat csak a fenti listából mondj. Hideg első megkeresésbe ne tegyél árat: az a hívásra való.
- A kész szövegekbe SOHA ne írj magadnak szóló megjegyzést vagy szögletes zárójeles belső utalást (pl. „[az árak a listából valók]”);
  szögletes zárójel csak kitöltendő helyen lehet: [Cégnév], [Név].
- Magyar cégvezetőnek szóló hideg levélben és üzenetben magázódj; tegezni csak a saját LinkedIn-posztban lehet.
- Azt, hogy nincs még referencia, ne írd bele a megkeresésbe vagy a posztba; ez ellenvetés-kezelésbe való, ha rákérdeznek.
  A bizonyíték az élő demó: azt mutasd, ne mentegetőzz.
- Statisztikát, százalékot, piaci vagy időmegtakarítási számot SEHOL ne írj (a forgatókönyv narrációjában és a posztban sem),
  csak ha egy webes forrás tartalmazza, és [n]-nel hivatkozod. Szám helyett kérdezz („Hány órát visz el nálatok…?”).
- Ha nem értesz egyet a kérdés feltevésével, mondd ki egy mondatban, aztán segíts.
- Jogszabálynál (GDPR, kéretlen levél, reklám) légy óvatos, és jelezd, ha jogászt kell kérdezni.
- Ha webes forrást használsz, jelöld [n]-nel. Ha valamiben bizonytalan vagy, mondd meg.
- A végén egyetlen sor: „Következő lépés: …” — a legtöbbet hozó konkrét teendő.
Csak a választ írd, markdown nélkül (nincs #, nincs **). Felsoroláshoz „- ” jelet használj."""
