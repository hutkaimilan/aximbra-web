"""A modell állításainak ellenőrzése, a modell nélkül.

A kutató modell tévedhet: kitalálhat címet, idézhet olyat, ami nincs az
oldalon, vagy osztrák céget mondhat magyarnak. Ezért minden jelöltet a
kód maga is letölt, és csak az marad, amit a saját szemével is lát.
"""
import html
import re
import unicodedata

import httpx

from playbook import BLOCKED_TLDS, COUNTRIES, MAX_WORDS, OPT_OUT

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
    if c.get("pain") not in ("phone", "email", "leads"):
        p.append("ismeretlen igény")
    if not (c.get("observation") or "").strip():
        p.append("nincs megfigyelés")
    return p


def check_letter(lead: dict) -> list[str]:
    """A megírt levél gépi ellenőrzése. Figyelmeztet, nem tilt: a
    jóváhagyó ember látja, és javíthatja."""
    w = []
    body = lead.get("body") or ""
    subj = lead.get("subject") or ""
    if not subj.strip() or len(subj.split()) > 8:
        w.append("a tárgysor hiányzik vagy túl hosszú")
    if len(body.split()) > MAX_WORDS:
        w.append(f"túl hosszú ({len(body.split())} szó)")
    if OPT_OUT[lead["lang"]] not in body:
        w.append("hiányzik a leiratkozó mondat")
    if "aximbra.hu" not in body:
        w.append("hiányzik az aximbra.hu")
    if re.search(r"https?://", body):
        w.append("link van benne")
    if re.search(r"\d[\d\s.]*\s?(ft|huf|eur|€|lei|ron)\b", body, flags=re.I):
        w.append("ár van benne")
    return w
