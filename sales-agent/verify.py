"""A modell állításainak ellenőrzése, a modell nélkül.

A kutató modell tévedhet: kitalálhat címet, idézhet olyat, ami nincs az
oldalon, vagy osztrák céget mondhat magyarnak. Ezért minden jelöltet a
kód maga is letölt, és csak az marad, amit a saját szemével is lát.
"""
import html
import re
import unicodedata

import httpx

from playbook import BLOCKED_TLDS, COUNTRIES, MAX_SENTENCE_WORDS, MAX_WORDS, OPT_OUT, PAIN_KEYS

FETCH_TIMEOUT = 15
MAX_BYTES = 1_500_000
UA = "Mozilla/5.0 (compatible; AximbraResearch/1.0; +https://aximbra.hu)"
EMAIL_RE = re.compile(r"^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$")


def fetch_text(url: str, client: httpx.Client | None = None) -> str | None:
    """Egy oldal szövege, HTML nélkül. Hiba esetén None — nem kivétel,
    mert egy elérhetetlen oldal csak annyit jelent, hogy a jelölt kiesik."""
    if not url or not url.startswith(("http://", "https://")):
        return None
    own = client is None
    client = client or httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=True, headers={"User-Agent": UA})
    try:
        with client.stream("GET", url) as r:
            if r.status_code >= 400:
                return None
            raw = b""
            for chunk in r.iter_bytes():
                raw += chunk
                if len(raw) > MAX_BYTES:
                    break
        text = raw.decode(r.encoding or "utf-8", errors="replace")
        return html_to_text(text)
    except (httpx.HTTPError, ValueError):
        return None
    finally:
        if own:
            client.close()


def fetch_html(url: str) -> str | None:
    if not url or not url.startswith(("http://", "https://")):
        return None
    try:
        with httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=True, headers={"User-Agent": UA}) as c:
            with c.stream("GET", url) as r:
                if r.status_code >= 400 or "html" not in r.headers.get("content-type", "html"):
                    return None
                raw = b""
                for chunk in r.iter_bytes():
                    raw += chunk
                    if len(raw) > MAX_BYTES:
                        break
            return raw.decode(r.encoding or "utf-8", errors="replace")
    except (httpx.HTTPError, ValueError):
        return None


_LINK_WORDS = ("kapcsolat", "contact", "impresszum", "impressum", "kontakt", "contacte", "rolunk", "rólunk",
               "about", "karrier", "career", "kariera", "cariere", "ugyfelszolgalat", "ugyfelszolgalat",
               "customer", "adatvedelem", "o-nas", "despre", "o-nama", "o-nas")
ROLE_PREFIXES = ("info", "office", "iroda", "kapcsolat", "contact", "ugyfelszolgalat", "sales", "ertekesites",
                 "hello", "recepcio", "kozpont", "titkarsag", "kontakt", "obchod", "vanzari", "prodaja",
                 "customer", "service", "szerviz", "marketing", "ajanlat", "rendeles", "support", "posta")


def crawl_site(website: str, max_pages: int = 5) -> list[tuple[str, str]]:
    """A kezdőlap és a kapcsolat/impresszum/karrier jellegű aloldalak szövege."""
    from urllib.parse import urljoin, urlparse
    home = fetch_html(website)
    if not home:
        return []
    base = urlparse(website).netloc.lower().removeprefix("www.")
    pages = [(website, html_to_text(home))]
    seen = {website.rstrip("/")}
    for href in re.findall(r'href=["\']([^"\'#]+)["\']', home, flags=re.I):
        url = urljoin(website, href)
        low = url.lower()
        if urlparse(url).netloc.lower().removeprefix("www.") != base or low.rstrip("/") in seen:
            continue
        if not any(w in low for w in _LINK_WORDS):
            continue
        seen.add(low.rstrip("/"))
        page = fetch_html(url)
        if page:
            pages.append((url, html_to_text(page)))
        if len(pages) >= max_pages:
            break
    return pages


def role_emails(pages: list[tuple[str, str]], website: str) -> list[tuple[str, str]]:
    """(cím, oldal) párok: csak céges szerepkör-címek, a cég domainjén vagy
    ismert ingyenes szolgáltatón; magánszemélynek tűnő címet nem adunk vissza."""
    from urllib.parse import urlparse
    dom = urlparse(website).netloc.lower().removeprefix("www.")
    found = {}
    for url, text in pages:
        for e in re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text):
            e = e.lower().strip(".")
            user, edom = e.split("@", 1)
            if not (edom == dom or edom.endswith("." + dom) or dom.endswith(edom)):
                continue
            if not any(user == p or user.startswith(p) for p in ROLE_PREFIXES):
                continue
            found.setdefault(e, url)
    ranked = sorted(found.items(), key=lambda kv: next((i for i, p in enumerate(ROLE_PREFIXES)
                                                        if kv[0].split("@")[0].startswith(p)), 99))
    return ranked


def html_to_text(src: str) -> str:
    # A mailto: linkekben lévő cím is számít: sok oldal csak ott írja ki.
    mailtos = " ".join(re.findall(r'mailto:([^"\'?>\s]+)', src, flags=re.I))
    src = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", src)
    src = re.sub(r"(?s)<[^>]+>", " ", src)
    return html.unescape(src + " " + mailtos)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[„“”\"'’‘«»]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def email_on_page(email: str, text: str) -> bool:
    t = norm(text)
    e = email.lower()
    if e in t:
        return True
    # "info [at] ceg [dot] hu" és hasonló kiírások.
    user, dom = e.split("@", 1)
    alt = re.sub(r"\s*(\[at\]|\(at\)| at |\[kukac\]|\(kukac\))\s*", "@", t)
    alt = re.sub(r"\s*(\[dot\]|\(dot\)|\[pont\]|\(pont\))\s*", ".", alt)
    return f"{user}@{dom}" in alt


def quote_on_page(quote: str, text: str) -> bool:
    """Szó szerinti egyezés, vagy ha a modell kicsit átfogalmazott, a
    szavak legalább 85%-a ugyanabban a sorrendben egy rövid ablakban."""
    q, t = norm(quote), norm(text)
    if len(q) < 15:
        return False
    if q in t:
        return True
    words = [w for w in re.findall(r"\w+", q) if len(w) > 2]
    if len(words) < 4:
        return False
    tw = re.findall(r"\w+", t)
    need = int(len(words) * 0.85 + 0.999)
    window = len(words) * 2
    for i in range(len(tw)):
        seg = set(tw[i:i + window])
        if sum(1 for w in words if w in seg) >= need:
            return True
    return False


def candidate_problems(c: dict) -> list[str]:
    """Kemény kizárások a letöltés előtt. Üres lista = mehet tovább."""
    p = []
    email = (c.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        p.append("hibás e-mail cím")
    if c.get("country") not in COUNTRIES:
        p.append("nem célország")
    for u in (email.split("@")[-1], c.get("website") or "", c.get("email_url") or ""):
        host = u.lower().split("://")[-1].split("/")[0]
        if host.endswith(BLOCKED_TLDS):
            p.append("osztrák/német vagy más tiltott országú domain")
            break
    if c.get("pain") not in PAIN_KEYS:
        p.append("ismeretlen igény")
    if not (c.get("observation") or "").strip():
        p.append("nincs megfigyelés")
    return p


# Nyelvfelismerés a levél ellenőrzéséhez. Nem kell tökéletesnek lennie,
# csak annyinak, hogy egy magyar és egy szlovák bekezdést egy levélen belül
# biztosan megkülönböztessen.
_LANG_WORDS = {
    "hu": {"és", "hogy", "nem", "az", "egy", "van", "csak", "önöknek", "önök", "kérjük", "ha", "vagy",
           "amikor", "ami", "lenne", "ez", "is", "már", "jó", "napot", "oldalukon", "írják", "többet", "írok",
           "nekünk", "kérem", "kapcsolat", "nyitvatartás", "asztalfoglalás", "foglalás", "étterem",
           "kizárólag", "telefonon", "hétfő", "vasárnap", "szombat", "időpont", "ügyfél", "írjon"},
    "sk": {"je", "na", "sa", "že", "pre", "vám", "ako", "sú", "alebo", "keď", "by", "to", "nie", "vás",
           "stačí", "viac", "napíšem", "dobrý", "deň", "môžete", "ktorý", "rezervácia", "rezervácie",
           "telefonicky", "otváracie", "hodiny", "kontakt", "pondelok", "nedeľa", "objednávka"},
    "ro": {"și", "este", "pentru", "nu", "la", "vă", "sunt", "că", "cu", "pe", "dumneavoastră", "bună",
           "ziua", "mai", "scriu", "dacă", "sau"},
    "hr": {"je", "i", "za", "vam", "nije", "su", "ili", "što", "kada", "vas", "poštovani", "bi", "li",
           "neću", "više", "pisati", "ako"},
    "sl": {"je", "in", "za", "vam", "ni", "so", "ali", "kaj", "ko", "vas", "pozdravljeni", "bi", "če",
           "ne", "bom", "več", "pisal"},
    "en": {"the", "and", "you", "your", "we", "our", "of", "for", "with", "this", "that", "would",
           "not", "are", "if", "or", "hello", "dear", "write", "again", "will", "have", "it", "do"},
    "fr": {"le", "la", "les", "et", "vous", "votre", "vos", "nous", "pour", "avec", "est", "sont", "une",
           "des", "du", "que", "qui", "pas", "si", "bonjour", "écrirai", "plus", "suffit", "dans", "sur"},
}
_LANG_CHARS = {"hu": "őűáéíóöúü", "sk": "ľťďňôäŕĺ", "ro": "ășțâî", "hr": "ćđ", "sl": "", "en": "", "fr": "èàçêùûœ"}


def detect_lang(text: str) -> str | None:
    words = re.findall(r"[^\W\d_]+", (text or "").lower())
    if len(words) < 4:
        return None
    scores, hits = {}, {}
    for lang, vocab in _LANG_WORDS.items():
        hits[lang] = sum(1 for w in words if w in vocab)
        scores[lang] = hits[lang] * 2 + sum(1 for ch in (text or "").lower() if ch in _LANG_CHARS[lang]) * 0.5
    best = max(scores, key=scores.get)
    ranked = sorted(scores.values(), reverse=True)
    # Legalább két jellemző szó kell: egy rövid mondatban egyetlen közös
    # szó (pl. "este") még nem dönti el a nyelvet.
    if hits[best] < 2 or ranked[0] - ranked[1] < 1:
        return None
    return best


SEPARATOR = "— — —"


def letter_langs(lead: dict) -> list[str]:
    """A levél szakaszainak nyelve sorrendben: kétnyelvű levélnél előbb a
    magyar, alatta az ország nyelve."""
    return [lead["lang2"], lead["lang"]] if lead.get("lang2") else [lead["lang"]]


def mixed_language(lead: dict) -> list[str]:
    """Azok a bekezdések, amelyek nem a saját szakaszuk nyelvén vannak.
    A szlovén és a horvát közeli rokon: egymással nem számít keveredésnek."""
    close = {frozenset({"hr", "sl"})}
    langs = letter_langs(lead)
    sections = (lead.get("body") or "").split(SEPARATOR)
    if len(sections) != len(langs):
        return [f"{len(langs)} nyelvi szakasz kellene, {len(sections)} van"]
    bad = []
    for want, section in zip(langs, sections):
        for para in section.strip().split("\n\n"):
            if "aximbra.hu" in para and len(para.split()) < 10:
                continue  # aláírás
            got = detect_lang(para)
            if got and got != want and frozenset({got, want}) not in close:
                bad.append(para[:60])
    subjects = (lead.get("subject") or "").split(" / ") if len(langs) == 2 else [lead.get("subject") or ""]
    for want, subj in zip(langs, subjects):
        got = detect_lang(subj)
        if got and got != want and frozenset({got, want}) not in close:
            bad.append("tárgy: " + subj[:40])
    return bad


def long_sentences(body: str) -> list[str]:
    """Az üzenetrész (az aláírás előtti bekezdések) túl hosszú mondatai.
    Az aláírás, az ui. és a leiratkozó sor kötött szöveg, azt nem mérjük."""
    out = []
    for section in (body or "").split(SEPARATOR):
        for para in section.strip().split("\n\n"):
            if "aximbra" in para.lower():
                break  # innen aláírás, ui., leiratkozás
            for sent in re.split(r"(?<=[.!?…])\s+", para):
                if len(sent.split()) > MAX_SENTENCE_WORDS:
                    out.append(sent[:60])
    return out


def check_letter(lead: dict) -> list[str]:
    """A megírt levél gépi ellenőrzése. Figyelmeztet, nem tilt: a
    jóváhagyó ember látja, és javíthatja."""
    w = []
    body = lead.get("body") or ""
    subj = lead.get("subject") or ""
    n = len(letter_langs(lead))
    if not subj.strip() or len(subj.split()) > 8 * n + (n - 1):
        w.append("a tárgysor hiányzik vagy túl hosszú")
    if len(body.split()) > MAX_WORDS * n + 5:
        w.append(f"túl hosszú ({len(body.split())} szó)")
    if any(OPT_OUT[l] not in body for l in letter_langs(lead)):
        w.append("hiányzik a leiratkozó mondat")
    if "aximbra.hu" not in body:
        w.append("hiányzik az aximbra.hu")
    if re.search(r"https?://", body):
        w.append("link van benne")
    if mixed_language(lead):
        w.append("VEGYES NYELV — ne küldd el")
    if has_price(body):
        w.append("ár van benne")
    if long_sentences(body):
        w.append(f"túl hosszú mondat ({MAX_SENTENCE_WORDS} szó felett) — nehezen olvasható")
    return w


# ---- kemény szabályok --------------------------------------------------------
# Ezek nem a modell ítéletén múlnak. A panelről küldött levélnél a
# célország-szabály tilt, a többi figyelmeztet (ember látta a levelet);
# a magától kimenő levélnél bármelyik találat megállítja a küldést.

_PRICE_RE = re.compile(
    r"\d[\d\s.,]*\s*(ezer|e\.|millió|m\.|mio|tisíc|tis\.|mii|milioane?|milion[a-z]*|tisuć[a-z]*|tisoč[a-z]*)?\s*"
    r"(ft|huf|forint[a-z]*|eur|euró[a-z]*|euro[a-z]*|lei|ron|kn|kuna|gbp|pounds?)\b|[€£$]\s*\d|\d\s*[€£]", re.I)


def has_price(text: str) -> bool:
    return bool(_PRICE_RE.search(text or ""))


# Kitalált ügyfél, referencia, esettanulmány: "ügyfelünk", "náš klient"...
# A "ügyfeleik/ügyfeleiknek" (az ő ügyfeleik) szándékosan nem akad be.
_REFERENCE_RE = re.compile(
    r"\bügyfel(ünk|ünknél|ünknek|eink|einknél|einknek|einktől)\b|\bpartner(ünk|eink)\b|\breferenci|"
    r"\besettanulmány|\bmár\s+\d+\s+(cég|vállalkozás|ügyfél)|\btöbb\s+(száz|tucat|tíz)\s+(cég|ügyfél|vállalkozás)|"
    r"\b(náš|naši|našich|nášmu|našim)\s+(klient|zákazník|partner)|\breferenci[ae]|\bpríkladov[aá]\s+štúdi|"
    r"\b(clientul|clienții|clientii|clienților|partenerii|partenerul)\s+(nostru|noștri|nostri|noastre)|\bstudiu\s+de\s+caz|"
    r"\b(naš|naši|našim|naših|našeg)\s+(klijent|kupac|partner|stranka|stranke|strank)|\breferenc|\breferin|"
    r"\bour\s+(clients?|customers?|partners?)\b|\bcase\s+stud|\btestimonial|"
    r"\b(nos|notre)\s+(clients?|partenaires?)\b|\bétude\s+de\s+cas|\btémoignage",
    re.I)

# Statisztika, százalék, szorzó: "40%-kal", "3x gyorsabb", "kétszer annyi".
_STAT_RE = re.compile(
    r"\d\s?%|\bszázalék|\bpercent|\bprocent|\bpostot|\bodstot|\b\d+\s?[x×]\b|\b\d+-(szor|szer|ször)\b|"
    r"\b(kétszer|háromszor|négyszer|ötször|tízszer)\s+(annyi|gyorsabb|több|kevesebb)|\bpour\s?cent|"
    r"\b(twice|three\s+times|ten\s+times)\s+(as|faster|more|fewer)|\bdeux\s+fois\s+plus", re.I)

# Munkatárs megnevezése. Csak a megszólításos, egyértelmű alakokat fogja:
# egy puszta "Kovács Péter" név, megszólítás nélkül, átcsúszhat. Ezért a
# magától küldés ezen felül csak ember által nem javított, magas pontú
# vázlatra, bemért pontszám mellett indul.
_UPPER = "A-ZÁÉÍÓÖŐÚÜŰČĎĽĹŇÔŔŠŤÝŽĂÂÎȘȚĆĐ"
_NAME_RE = re.compile(
    rf"\b[{_UPPER}][a-záéíóöőúüű]+\s+(úr|úrnak|úrral|urat|úrtól|asszony|asszonynak|asszonnyal|asszonyt|kolléganő)\b|"
    rf"\b(pán|pani|pánovi|panej|pána|panu|domnul|doamna|domnului|doamnei|dl\.|dna\.|gospodin|gospodine|"
    rf"gospođa|gospođo|gospa|gospod|g\.|ga\.|[Mm]r\.?|[Mm]rs\.?|[Mm]s\.?|[Mm]onsieur|[Mm]adame|[Mm]me\.?|M\.)\s+[{_UPPER}]|"
    rf"\b(Kedves|Tisztelt|Dear|Milý|Milá|Vážený|Vážená|Stimate|Stimată|Dragă|Poštovani|Poštovana|Spoštovani|Spoštovana|Cher|Chère|Bonjour|Hello|Hi)"
    # A kivétellista kis- és nagybetűre is érvényes: „Stimate Domn / Stimată Doamnă” általános megszólítás.
    rf"\s+(?!(?i:Hölgyem|Uram|Címzett|Partner|Ügyfél|Csapat|Kolleg|Munkatárs|pán|pani|páni|pane|domn|doamn|gospo|gospa|kolegi|kolegovia|Sir|Madam|team|Monsieur|Madame|équipe))"
    rf"[{_UPPER}][a-záéíóöőúüűčďľĺňôŕšťýžăâîșțćđ]+", re.U)


def target_problems(lead: dict) -> list[str]:
    """Célország-szabály: AT/DE soha, és csak a playbook országai."""
    p = []
    if lead.get("country") not in COUNTRIES:
        p.append("nem célország")
    for u in ((lead.get("email") or "").split("@")[-1], lead.get("website") or "", lead.get("email_url") or ""):
        host = u.lower().split("://")[-1].split("/")[0].split(":")[0]
        if host.endswith(BLOCKED_TLDS):
            p.append("osztrák/német domain")
            break
    return p


def rule_violations(lead: dict) -> list[str]:
    """Minden gépileg ellenőrizhető szabály egy helyen. Üres = tiszta."""
    text = f"{lead.get('subject') or ''}\n{lead.get('body') or ''}"
    v = target_problems(lead) + check_letter(lead)
    if _REFERENCE_RE.search(text):
        v.append("ügyfélre/referenciára hivatkozik")
    if _STAT_RE.search(text):
        v.append("számot/statisztikát állít")
    if _NAME_RE.search(text):
        v.append("munkatársat nevez meg")
    return v
