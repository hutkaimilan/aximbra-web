"""A modell állításainak ellenőrzése, a modell nélkül.

A kutató modell tévedhet: kitalálhat címet, idézhet olyat, ami nincs az
oldalon, vagy osztrák céget mondhat magyarnak. Ezért minden jelöltet a
kód maga is letölt, és csak az marad, amit a saját szemével is lát.
"""
import html
import re
import unicodedata

import httpx

from playbook import BLOCKED_TLDS, COUNTRIES, MAX_WORDS, OPT_OUT, PAIN_KEYS

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
            p.append("osztrák/német domain")
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
}
_LANG_CHARS = {"hu": "őűáéíóöúü", "sk": "ľťďňôäŕĺ", "ro": "ășțâî", "hr": "ćđ", "sl": ""}


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
    if re.search(r"\d[\d\s.]*\s?(ft|huf|eur|€|lei|ron)\b", body, flags=re.I):
        w.append("ár van benne")
    return w
