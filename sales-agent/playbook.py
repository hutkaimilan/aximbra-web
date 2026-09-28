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


def research_prompt(country: str, count: int, exclude_domains: list[str]) -> str:
    c = COUNTRIES[country]
    excl = ", ".join(exclude_domains[:300]) or "none"
    return f"""Find {count} small or medium PRIVATE businesses in {c['name']} ({country}) for B2B outreach.

A business qualifies only if ITS OWN WEBSITE states one of these concrete pains (quote it word for word, in the original language):
- phone: bookings/appointments only by phone, "if the line is busy we call back", limited phone hours, same-day booking only by phone.
- email: a stated email response time (e.g. "1–3 working days"), email as the main customer channel, lots of order/warranty emails.
- leads: quote requests with callback promises, seasonal backlog, "we call you back within 24 hours".
Good sectors: restaurants, private dental/medical practices, car services, beauty salons, guesthouses, installers, small webshops, driving schools.
Exclude: public institutions, state hospitals, schools, military, big chains, franchises with central call centers, businesses that already solve the exact pain with online booking, and these domains: {excl}.

The email address must be printed on the business's own website (contact page, footer or imprint). Prefer generic addresses (info@, office@, hello@, recepcio@, a business gmail shown on the site). Never guess an address.

Answer ONLY with a JSON array, no prose, each item:
{{"company": "...", "town": "...", "country": "{country}", "website": "https://...", "email": "...", "email_url": "https://... (page where the email is printed)", "observation": "exact sentence copied from their site", "observation_url": "https://... (page where the sentence is)", "pain": "phone|email|leads"}}
If you cannot verify an item, leave it out. Fewer good items beat more weak ones."""


def compose_prompt(lead: dict) -> str:
    lang = lead["lang"]
    site = COUNTRIES[lead["country"]]["site"]
    ps = DEMO_PS[lead["pain"]]["hu" if lang == "hu" else "other"].format(site=site)
    sig = SIGNATURE["hu" if lang == "hu" else "other"].format(site=site)
    return f"""Write a cold B2B email in {LANG_NAMES[lang]} to {lead['company']} ({lead['town']}).

Their website says: "{lead['observation']}"
What we offer: a {PAINS[lead['pain']]}. Built by Milán Hutkai, AXIMBRA.

Structure, exactly in this order, plain text, formal register:
1. Greeting ("Jó napot!" in Hungarian, the normal formal greeting otherwise).
2. One sentence restating what their site says ("Az oldalukon azt írják, hogy…").
3. One question about the consequence of that situation for them.
4. One sentence: "I built a …" describing our tool in their situation, concrete (what it writes down / sorts).
5. The question "Would this be interesting for you?" in {LANG_NAMES[lang]}.
6. Signature line exactly: {sig}
7. A postscript (P.S.) in {LANG_NAMES[lang]}: {ps}
8. Last line exactly: {OPT_OUT[lang]}

Rules: lines 1–5 together under 75 words. No prices, no links, no hype words, no urgency, no claims about clients or results, no emojis.
Subject: 3–5 words about THEIR situation, not about us.

Answer ONLY with JSON: {{"subject": "...", "body": "..."}}"""


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
