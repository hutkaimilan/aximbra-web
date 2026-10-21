"""Személyre szabott demóoldal egy megkeresett cégnek.

A cég nyilvános weboldalából kiderítjük, mivel foglalkozik és hol van náluk
ismétlődő kézi munka, kiválasztjuk hozzá az AXIMBRA katalógusából a
legjobban illő agentet, és példaadatokkal megmutatjuk, mit csinálna náluk.
Az oldal az aximbra.hu/neked/<slug> címen jelenik meg; az adatot innen kéri.

Semmire nincs korlátozva: se iparágra, se nyelvre, se cégméretre. Ami a
cégről állítás (az idézet, a bizonyíték), azt a kód szó szerint visszakeresi
a letöltött szövegben; amit nem talál, az kimarad. Kitalált állítás egy
hideg megkeresésben többet árt, mint egy hiányzó mondat.
"""
from __future__ import annotations

import html
import ipaddress
import json
import logging
import re
import secrets
import socket
import threading
import unicodedata
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx

logger = logging.getLogger("sales.demo")

UA = "Mozilla/5.0 (compatible; AximbraDemo/1.0; +https://aximbra.hu)"
FETCH_TIMEOUT = 10
MAX_BYTES = 1_500_000
MAX_REDIRECTS = 5
MAX_PAGES = 6
SITE_TEXT_CHARS = 14_000
MIN_SITE_CHARS = 300
MAX_PARAGRAPHS = 70
PAGE_DAYS = 90
PUBLIC_BASE = "https://aximbra.hu/neked"

# Egyszerre ennyi oldal készülhet: két modellhívás + hat letöltés oldalanként,
# az ingyenes Gemini-keret percenkénti korlátja ennél többet nem bír.
_SLOTS = threading.BoundedSemaphore(2)


class DemoError(RuntimeError):
    """A hívónak szóló, megmutatható hiba (rossz cím, tiltott cím, foglalt)."""


class ModelError(DemoError):
    """A modell kétszer egymás után sem adott használható elemzést."""


# Az oldal felülete ezeken a nyelveken van meg (az aximbra.hu nyelvei); más
# nyelvű cégnek angolul írunk, hogy a tartalom és a felület egy nyelven legyen.
LANGS = ("hu", "en", "de", "es", "fr", "it", "ro", "sk", "zh")


# ---------------------------------------------------------------- katalógus
# A díjak és átfutások az aximbra.hu-val egyeznek (frontend/src/i18n/*.js).
# kind = a demó formája; hours = havi megspórolt órák kiinduló becslése,
# a látogató a csúszkán átírhatja.
CATALOG = {
    "email":    {"hu": "E-mail rendező", "en": "Email triage agent", "de": "E-Mail-Sortierer",
                 "price": (150_000, 400_000), "weeks": (2, 3), "kind": "inbox", "hours": 30,
                 "live": "https://aximbra.hu/demo/email-agent"},
    "lead":     {"hu": "Érdeklődő-minősítő", "en": "Lead qualifier", "de": "Anfragen-Qualifizierer",
                 "price": (400_000, 1_200_000), "weeks": (2, 3), "kind": "leads", "hours": 20,
                 "live": "https://aximbra.hu/agent/erdeklodo-minosito?demo=1"},
    "admin":    {"hu": "Belső admin agent", "en": "Internal admin agent", "de": "Interner Admin-Agent",
                 "price": (150_000, 400_000), "weeks": (2, 3), "kind": "timeline", "hours": 25},
    "research": {"hu": "Kutatási monitor", "en": "Research monitor", "de": "Recherche-Monitor",
                 "price": (150_000, 400_000), "weeks": (2, 3), "kind": "report", "hours": 12},
    "content":  {"hu": "Tartalom-agent", "en": "Content agent", "de": "Content-Agent",
                 "price": (400_000, 1_200_000), "weeks": (2, 2), "kind": "content", "hours": 20},
    "webshop":  {"hu": "Webshop-asszisztens", "en": "Webshop assistant", "de": "Webshop-Assistent",
                 "price": (600_000, 1_500_000), "weeks": (2, 4), "kind": "inbox", "hours": 35,
                 "live": "https://aximbra.hu/demo/webshop#ugyfelszolgalat"},
    "sales":    {"hu": "Értékesítő agent", "en": "Sales agent", "de": "Vertriebs-Agent",
                 "price": (600_000, 1_500_000), "weeks": (2, 4), "kind": "content", "hours": 25},
    "it":       {"hu": "IT-üzemeltető agent", "en": "IT operations agent", "de": "IT-Betriebs-Agent",
                 "price": (600_000, 2_000_000), "weeks": (3, 5), "kind": "report", "hours": 25},
    "nis2":     {"hu": "NIS2-megfelelési agent", "en": "NIS2 compliance agent", "de": "NIS2-Compliance-Agent",
                 "price": (600_000, 2_000_000), "weeks": (3, 6), "kind": "report", "hours": 15},
    "recruit":  {"hu": "Toborzási agent", "en": "Recruitment agent", "de": "Recruiting-Agent",
                 "price": (1_700_000, 3_900_000), "weeks": (3, 4), "kind": "leads", "hours": 30, "legal": True},
    "docs":     {"hu": "Dokumentum-elemző", "en": "Document analyser", "de": "Dokumentenanalyse",
                 "price": (2_000_000, 4_000_000), "weeks": (4, 5), "kind": "document", "hours": 30,
                 "live": "https://aximbra.hu/agent/dokumentum-elemzo?demo=1"},
    "finance":  {"hu": "Pénzügyi asszisztens", "en": "Finance assistant", "de": "Finanz-Assistent",
                 "price": (2_000_000, 4_000_000), "weeks": (4, 6), "kind": "report", "hours": 30},
    "support":  {"hu": "Ügyfélszolgálati agent", "en": "Customer support agent", "de": "Kundenservice-Agent",
                 "price": (1_500_000, 4_000_000), "weeks": (4, 7), "kind": "chat", "hours": 40},
    "multi":    {"hu": "Multi-agent rendszer", "en": "Multi-agent system", "de": "Multi-Agenten-System",
                 "price": (6_000_000, 15_000_000), "weeks": (7, 12), "kind": "timeline", "hours": 80},
    "phone":    {"hu": "Telefonos AI-recepciós", "en": "AI phone receptionist", "de": "KI-Telefonrezeption",
                 "price": None, "weeks": None, "kind": "call", "hours": 30, "live": "tel:+18024249852"},
    "custom":   {"hu": "Egyedi agent", "en": "Custom agent", "de": "Individueller Agent",
                 "price": None, "weeks": None, "kind": "timeline", "hours": 25},
}

# Mire való az egyes agent — a modell ebből választ, ezért pontos és rövid.
PURPOSE = {
    "email": "sorts a shared inbox: category, urgency, who handles it, reply draft for approval",
    "lead": "scores incoming enquiries/quote requests and says whom to call back first",
    "admin": "moves data between systems, fills forms, compiles routine reports",
    "research": "watches competitors, tenders, regulation or the market and reports only real changes",
    "content": "drafts newsletters, product texts, social posts in the company's voice, for approval",
    "webshop": "answers webshop customer emails (where is my parcel, returns, invoices) from order data",
    "sales": "finds fitting prospects, writes short personal outreach, follows up, sorts replies",
    "it": "watches logs and alerts, classifies them, runs approved fixes, escalates unknowns",
    "nis2": "collects and maintains the evidence a NIS2 audit asks for (access, backups, MFA); it does not protect",
    "recruit": "pre-screens CVs against structured criteria, with audit log and human override",
    "docs": "reads contracts, invoices, offers; extracts key data and flags risky clauses",
    "finance": "categorises costs, flags anomalies, writes monthly reports with source lines",
    "support": "answers customer questions from the company's own documents with sources; hands over the rest",
    "multi": "several agents on one complex cross-department process, with checkpoints",
    "phone": "answers the phone when staff can't, takes bookings/requests, sends a summary",
    "custom": "a custom agent for a specific repetitive task not covered above",
}

KINDS = ("inbox", "chat", "leads", "document", "report", "call", "content", "timeline")


def monthly_fee(agent_id: str) -> int | None:
    price = CATALOG[agent_id]["price"]
    if not price:
        return None
    hi = price[1]
    return 25_000 if hi <= 400_000 else 50_000 if hi <= 2_000_000 else 90_000


def agent_name(agent_id: str, lang: str) -> str:
    a = CATALOG[agent_id]
    return a.get(lang) or a["en"]


# ------------------------------------------------------------ biztonságos letöltés

def _ip_ok(ip: str) -> bool:
    a = ipaddress.ip_address(ip)
    return not (a.is_private or a.is_loopback or a.is_link_local or a.is_reserved
                or a.is_multicast or a.is_unspecified)


def host_ok(host: str) -> bool:
    """Csak a nyilvános internet: belső hálózatra, a gépre magára vagy a
    felhő metaadat-címére (169.254.x) mutató címet nem töltünk le."""
    if not host:
        return False
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    return bool(infos) and all(_ip_ok(sa[0]) for *_, sa in infos)


def normalize_url(raw: str) -> str:
    raw = (raw or "").strip()
    if not raw:
        raise DemoError("Hiányzik a weboldal címe.")
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    p = urlparse(raw)
    if p.scheme not in ("http", "https") or not p.hostname or "." not in p.hostname:
        raise DemoError("Ez nem weboldal-cím.")
    return f"{p.scheme}://{p.hostname.lower()}{p.path or '/'}"


def domain_of(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


class Fetcher:
    """Egy weboldal letöltése: kézi átirányítás-követéssel (minden lépésnél
    újra ellenőrzött címmel), a robots.txt tiszteletben tartásával, és
    tanúsítvány-ellenőrzéssel. Kis cégek oldalán gyakori a lejárt vagy hibás
    tanúsítvány: ilyenkor egyszer ellenőrzés nélkül is próbálkozunk — csak
    olvasunk, nem küldünk semmit —, és ezt naplózzuk."""

    def __init__(self):
        self._robots: dict[str, RobotFileParser | None] = {}
        self.insecure_hosts: set[str] = set()

    def _get(self, url: str, verify: bool) -> httpx.Response | None:
        with httpx.Client(timeout=FETCH_TIMEOUT, follow_redirects=False, verify=verify,
                          headers={"User-Agent": UA, "Accept-Language": "*"}) as c:
            with c.stream("GET", url) as r:
                raw = b""
                if r.status_code < 300 and "html" in r.headers.get("content-type", "text/html").lower() \
                        or url.endswith("/robots.txt"):
                    for chunk in r.iter_bytes():
                        raw += chunk
                        if len(raw) > MAX_BYTES:
                            break
                r._content = raw  # a stream lezárása után is olvasható maradjon
                return r

    def _one(self, url: str) -> httpx.Response | None:
        host = urlparse(url).hostname or ""
        verify = host not in self.insecure_hosts
        try:
            return self._get(url, verify)
        except httpx.ConnectError as e:
            if verify and ("CERTIFICATE" in str(e).upper() or "SSL" in str(e).upper()):
                logger.warning("demo fetch: invalid TLS certificate on %s, reading without verification", host)
                self.insecure_hosts.add(host)
                try:
                    return self._get(url, False)
                except httpx.HTTPError:
                    return None
            return None
        except httpx.HTTPError:
            return None

    def _allowed(self, url: str) -> bool:
        p = urlparse(url)
        key = f"{p.scheme}://{p.netloc}"
        if key not in self._robots:
            rp = None
            r = self._one(key + "/robots.txt") if host_ok(p.hostname or "") else None
            if r is not None and r.status_code == 200:
                rp = RobotFileParser()
                rp.parse(r.content.decode("utf-8", "replace").splitlines())
            self._robots[key] = rp
        rp = self._robots[key]
        return rp is None or rp.can_fetch(UA, url)

    def fetch(self, url: str) -> tuple[str, str] | None:
        """(végső cím, HTML) vagy None."""
        for _ in range(MAX_REDIRECTS + 1):
            p = urlparse(url)
            if p.scheme not in ("http", "https") or not host_ok(p.hostname or ""):
                return None
            if not self._allowed(url):
                logger.info("demo fetch: robots.txt disallows %s", url)
                return None
            r = self._one(url)
            if r is None:
                return None
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("location"):
                url = urljoin(url, r.headers["location"])
                continue
            if r.status_code >= 400 or not r.content:
                return None
            enc = _charset(r)
            try:
                return url, r.content.decode(enc, errors="replace")
            except LookupError:
                return url, r.content.decode("utf-8", errors="replace")
        return None


_META_CHARSET = re.compile(rb"""<meta[^>]+charset=["']?([A-Za-z0-9_-]+)""", re.I)


def _charset(r: httpx.Response) -> str:
    """A fejlécben megadott kódolás, különben a HTML <meta charset>-je
    (régi oldalakon gyakori az iso-8859-2 / windows-1250), különben UTF-8."""
    ct = r.headers.get("content-type", "")
    m = re.search(r"charset=([\w-]+)", ct, re.I)
    if m:
        return m.group(1)
    m = _META_CHARSET.search(r.content[:4096])
    return m.group(1).decode("ascii") if m else "utf-8"


# ------------------------------------------------------------ szövegkinyerés

_SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}
# Ami nem a cég saját mondata: menü, fejléc, lábléc, gombok, űrlapok.
_CHROME = {"nav", "header", "footer", "aside", "form", "button", "select", "label", "menu"}
_BLOCK = {"p", "div", "li", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article",
          "br", "tr", "dd", "dt", "blockquote", "figcaption", "main"}
_PARA = {"p", "blockquote", "dd"}


class _Extract(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.skip = 0
        self.chrome = 0
        self.text: list[str] = []
        self.paras: list[str] = []
        self._para: list[str] | None = None
        self._para_depth = 0
        self.links: list[str] = []
        self.title = ""
        self._in_title = False
        self.lang = ""
        self.description = ""

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "html" and a.get("lang"):
            self.lang = a["lang"][:2].lower()
        if tag == "meta" and (a.get("name") or "").lower() == "description":
            self.description = (a.get("content") or "")[:300]
        if tag == "title":
            self._in_title = True
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        if tag in ("br", "img", "meta", "link", "input", "hr"):
            if tag == "br":
                self.text.append("\n")
            return
        self.stack.append(tag)
        if tag in _SKIP:
            self.skip += 1
        if tag in _CHROME or (a.get("role") or "") in ("navigation", "banner", "contentinfo", "menu"):
            self.chrome += 1
            self.stack[-1] = tag + "#chrome"
        if tag in _BLOCK:
            self.text.append("\n")
        if tag in _PARA and self._para is None and not self.chrome and not self.skip:
            self._para = []
            self._para_depth = len(self.stack)

    def handle_endtag(self, tag):
        if tag == "title":
            self._in_title = False
        if tag not in self.stack and tag + "#chrome" not in self.stack:
            return
        while self.stack:
            t = self.stack.pop()
            base = t.split("#")[0]
            if base in _SKIP:
                self.skip -= 1
            if t.endswith("#chrome"):
                self.chrome -= 1
            if self._para is not None and len(self.stack) < self._para_depth:
                s = re.sub(r"\s+", " ", "".join(self._para)).strip()
                if s:
                    self.paras.append(s)
                self._para = None
            if base == tag:
                break
        if tag in _BLOCK:
            self.text.append("\n")

    def handle_data(self, data):
        if self._in_title:
            self.title += data
        if self.skip:
            return
        self.text.append(data)
        if self._para is not None:
            self._para.append(data)


def extract(src: str) -> dict:
    p = _Extract()
    try:
        p.feed(src)
        p.close()
    except Exception:  # noqa - hibás HTML: ami eddig megvan, az is jó
        pass
    text = re.sub(r"[ \t\r\f\v]+", " ", "".join(p.text))
    text = re.sub(r"\n\s*\n+", "\n", text).strip()
    return {"text": text, "paras": p.paras, "links": p.links, "title": html.unescape(p.title).strip(),
            "lang": p.lang, "description": p.description}


# Aloldal-választás: a nevükből látszik, hol írnak a cég munkájáról. Sok nyelven,
# mert a generátor nincs nyelvre korlátozva.
_SUB_WORDS = (
    "about", "rolunk", "rólunk", "uber-uns", "ueber-uns", "despre", "o-nas", "chi-siamo", "qui-sommes", "nosotros",
    "service", "szolgaltatas", "szolgáltatás", "leistung", "servic", "sluzb", "servizi", "prestation",
    "product", "termek", "termék", "produkt", "produs", "prodott", "produit", "producto",
    "contact", "kapcsolat", "kontakt", "contatt", "contacto",
    "faq", "gyik", "hilfe", "help", "support", "ugyfelszolgalat", "ügyfélszolgálat", "kundenservice",
    "shop", "bolt", "aruhaz", "store", "rendel", "order", "bestell",
    "price", "pricing", "arak", "árak", "preise", "tarif", "cennik", "prezzi",
    "career", "karrier", "jobs", "allas", "állás", "stellen", "kariera", "cariere", "lavora",
    "booking", "foglal", "reserv", "buchen", "termin", "appointment", "idopont", "időpont",
    "referenc", "project", "projekt", "portfolio", "solution", "megoldas", "loesung", "lösung",
)
_SUB_SKIP = re.compile(
    r"\.(pdf|jpe?g|png|gif|webp|svg|zip|docx?|xlsx?|mp4|mp3)$|login|signin|cart|kosar|kosár|checkout|account|"
    r"fiok|fiók|belepes|belépés|bejelentkez|regisztr|register|anmeld|felhasznalo|/user/|/my-|"
    r"wp-admin|privacy|adatvedelem|adatkezel|cookie|aszf|terms|agb|datenschutz|impressum|impresszum|"
    r"tag/|category/|kategoria/|/feed|\?", re.I)


_LANG_SEG = re.compile(r"^[a-z]{2}(?:[-_][a-z]{2})?$", re.I)


def _lang_seg(path: str) -> str:
    """Az útvonal nyelvi előtagja (/hu/..., /en-gb/...), ha van."""
    first = path.strip("/").split("/")[0]
    return first.lower() if _LANG_SEG.match(first) else ""


def pick_subpages(home_url: str, links: list[str], limit: int = MAX_PAGES - 1) -> list[str]:
    dom = domain_of(home_url)
    home_seg = _lang_seg(urlparse(home_url).path)
    seen, scored = {home_url.rstrip("/")}, []
    for href in links:
        if href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        url = urljoin(home_url, href).split("#")[0]
        if domain_of(url) != dom or url.rstrip("/") in seen or _SUB_SKIP.search(url):
            continue
        seen.add(url.rstrip("/"))
        path = urlparse(url).path.lower()
        seg = _lang_seg(path)
        if seg and seg != home_seg:  # ugyanaz az oldal másik nyelven
            continue
        depth = path.strip("/").count("/") + 1 if path.strip("/") else 0
        if depth == 0 or depth > 3:
            continue
        hits = sum(1 for w in _SUB_WORDS if w in path)
        scored.append((-hits, depth, len(path), url))
    scored.sort()
    return [u for *_, u in scored[:limit]]


def crawl(url: str, fetcher: Fetcher | None = None) -> list[dict]:
    """A kezdőlap és legfeljebb 5 aloldal kinyert szövege."""
    fetcher = fetcher or Fetcher()
    home = fetcher.fetch(url)
    if not home and url.startswith("https://"):
        home = fetcher.fetch("http://" + url[len("https://"):])
    if not home and "://www." not in url:
        home = fetcher.fetch(url.replace("://", "://www.", 1))
    if not home:
        return []
    home_url, src = home
    first = extract(src)
    pages = [{"url": home_url, **first}]
    for sub in pick_subpages(home_url, first["links"]):
        got = fetcher.fetch(sub)
        if got and not _SUB_SKIP.search(got[0]):  # pl. belépésre irányított át
            pages.append({"url": got[0], **extract(got[1])})
    return pages


# Ha a HTML nem mondja meg a nyelvét: a leggyakoribb rövid szavakból. Csak a
# felület nyelveit kell felismerni; ami egyik sem, az angol oldalt kap.
_STOP = {
    "hu": "a az és hogy nem is egy van meg már csak vagy mint ha el kell minden szerint",
    "en": "the and to of for with our you your is are we this that on from",
    "de": "der die das und ist nicht mit für auf wir sie ein eine zu von den",
    "es": "el la los las de que y en para con por una nuestro es del",
    "fr": "le la les des et est pour avec une dans nous vous sur du au",
    "it": "il la di che e per con una sono nostro del della gli le",
    "ro": "și de la în cu pentru este sau un o nu din care mai",
    "sk": "a je na sa v pre so že ako ale to aj alebo od",
}
_STOP_SETS = {k: set(v.split()) for k, v in _STOP.items()}


def guess_lang(text: str) -> str | None:
    if len(re.findall(r"[\u4e00-\u9fff]", text[:4000])) > 200:
        return "zh"
    words = re.findall(r"\w+", text[:8000].lower())
    if len(words) < 40:
        return None
    score = {k: sum(1 for w in words if w in st) for k, st in _STOP_SETS.items()}
    first, second = sorted(score.values(), reverse=True)[:2]
    best = max(score, key=score.get)
    # Termékneveknél, menüknél kevés a kötőszó: elég a 3%, ha egyértelmű a győztes.
    return best if first >= 0.03 * len(words) and first >= 1.5 * second else None


# ------------------------------------------------------------ ellenőrzések

def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = re.sub(r"[„“”\"'’‘«»]", "", s)
    return re.sub(r"\s+", " ", s).strip()


_CONTACT = re.compile(r"@|https?://|www\.|\+?\d[\d\s/().-]{7,}\d")


def good_quote(q: str, paragraph: str) -> bool:
    """Idézet csak a cég saját folyó szövegéből: egyetlen teljes mondat,
    legalább 8 szó, szó szerint a megjelölt bekezdésben, elérhetőség nélkül.
    Menü, gomb, lábléc eleve nem kerül a bekezdések közé (lásd _Extract)."""
    q = (q or "").strip().strip("„“”\"'")
    words = re.findall(r"\w+", q)
    if not (8 <= len(words) <= 45):
        return False
    if not re.search(r"[.!?…]$", q) or _CONTACT.search(q):
        return False
    if len(re.findall(r"[.!?]\s+\S", q)) > 0:  # több mondat
        return False
    if q.isupper():
        return False
    return norm(q) in norm(paragraph)


def evidence_on_pages(ev: str, pages: list[dict]) -> bool:
    e = norm(ev)
    return len(e) >= 3 and any(e in norm(p["text"]) for p in pages)


# ------------------------------------------------------------ modellhívások

LANG_NAMES = {"hu": "Hungarian", "en": "English", "de": "German", "ro": "Romanian", "sk": "Slovak",
              "cs": "Czech", "pl": "Polish", "hr": "Croatian", "sr": "Serbian", "sl": "Slovenian",
              "fr": "French", "it": "Italian", "es": "Spanish", "pt": "Portuguese", "nl": "Dutch",
              "zh": "Simplified Chinese"}


def _site_digest(pages: list[dict]) -> tuple[str, list[str]]:
    """A modellnek: oldalanként a szöveg (levágva), és a számozott bekezdések,
    amelyekből idézni lehet."""
    budget = SITE_TEXT_CHARS
    parts = []
    for p in pages:
        chunk = p["text"][: max(800, budget // max(1, len(pages)))]
        parts.append(f"=== {p['url']} ===\n{p['title']}\n{p.get('description', '')}\n{chunk}")
    paras: list[str] = []
    for p in pages:
        for s in p["paras"]:
            if len(re.findall(r"\w+", s)) >= 8 and s not in paras:
                paras.append(s)
    return "\n\n".join(parts)[:SITE_TEXT_CHARS], paras[:MAX_PARAGRAPHS]


def _catalog_text() -> str:
    return "\n".join(f"- {k}: {PURPOSE[k]}" for k in CATALOG)


def analyze_prompt(pages: list[dict], lang: str | None, company: str | None, avoid_support: bool = False) -> str:
    digest, paras = _site_digest(pages)
    numbered = "\n".join(f"[{i}] {s}" for i, s in enumerate(paras))
    out_lang = f"in {LANG_NAMES.get(lang, lang)}" if lang else "in the main language of the website"
    support_rule = ("Do NOT choose 'support' as main." if avoid_support else
                    "Choose 'support' as main ONLY if the site shows real customer-question volume (FAQ, help "
                    "centre, support/customer service contact) and give that text word for word in "
                    "support_evidence; otherwise pick the agent that fits their actual repetitive work.")
    return f"""You analyse ONE company's public website for AXIMBRA, an AI agent studio, to show them what an AI agent could do for THEM. Any industry, size or country is possible; never assume an industry.

Website text:
{digest}

Numbered paragraphs (the only text you may quote):
{numbered or '(none)'}

AXIMBRA agents (id: purpose):
{_catalog_text()}

Reply with a VALID JSON object only:
{{"company": "the company's own name as written on the site{(' (given: ' + company + ')') if company else ''}",
"site_language": "ISO 639-1 code of the website's main language",
"summary": "1-2 plain sentences {out_lang}: what they do and for whom, only what the site states",
"work": [{{"task": "a repetitive manual task they likely have, {out_lang}", "evidence": "short text copied WORD FOR WORD from the website that shows it"}}],
"main": "agent id", "main_reason": "1-2 sentences {out_lang}: why this agent fits THEM, citing what the site shows",
"support_evidence": "word-for-word text or empty",
"extras": [{{"id": "agent id", "reason": "one sentence {out_lang}"}}],
"custom_idea": "if main is custom: the concrete agent idea {out_lang}, else empty",
"quote": "ONE complete sentence copied word for word from ONE numbered paragraph that best shows something an agent could help with; empty if none fits",
"quote_paragraph": paragraph number or -1}}

Rules: at most 2 extras, different from main. {support_rule} Prefer the agent tied to the most frequent, most time-consuming work the site reveals (bookings, orders, enquiries, quotes, documents, applications, reports...). If nothing in the catalogue fits well, choose 'custom' with a concrete idea. Never invent facts about the company: every claim must be supported by the website text."""


DEMO_SHAPES = {
    "inbox": '{"items": [{"from": "a role, e.g. a customer or supplier, no real names", "subject": "...", "snippet": "first line of the email", "category": "...", "urgency": 1-5, "reply": "short reply draft"}]} with exactly 5 items',
    "chat": '{"messages": [{"role": "customer|agent", "text": "..."}], "handoff": "when and how the agent hands over to a human"} with 6-8 messages',
    "leads": '{"items": [{"name": "an invented first name or invented company", "need": "what they asked", "score": 0-100, "grade": "A|B|C|D", "next": "suggested next step"}]} with exactly 5 items',
    "document": '{"title": "an invented document typical for them", "clauses": [{"text": "clause text", "risk": "high|medium|none", "note": "why"}]} with exactly 5 clauses',
    "report": '{"title": "...", "period": "...", "metrics": [{"label": "...", "value": "...", "change": "..."}], "findings": ["..."], "actions": ["..."]} with 3 metrics, 3 findings, 2 actions',
    "call": '{"lines": [{"who": "caller|agent", "text": "..."}], "summary": "what the agent records and sends after the call"} with 6-8 lines',
    "content": '{"items": [{"channel": "e.g. newsletter, product page, social post, outreach email", "title": "...", "text": "40-80 words"}]} with exactly 3 items',
    "timeline": '{"before": [{"time": "e.g. 08:30", "task": "..."}], "after": [{"time": "...", "task": "..."}]} with 4 entries each',
}


def demo_prompt(company: str, summary: str, agent_id: str, reason: str, lang: str) -> str:
    kind = CATALOG[agent_id]["kind"]
    return f"""Create SAMPLE DATA for an interactive demo page showing what AXIMBRA's "{CATALOG[agent_id]['en']}" ({PURPOSE[agent_id]}) would do at {company}.
What the company does (from its website): {summary}
Why this agent fits: {reason}

Write everything in {LANG_NAMES.get(lang, lang)}. The data is clearly fictional sample data: use invented customer names or roles only, no real people, no prices or facts about {company} that are not in the description above, no claims about their customers or results. Make it specific to their kind of work so they recognise their own day.

Reply with a VALID JSON object only:
{{"steps": ["3 short steps: how the agent would work at them"], "demo": {DEMO_SHAPES[kind]}}}"""


def _str(v, n: int = 400) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def clean_demo(kind: str, d) -> dict | None:
    """A modell demóadata, alakra ellenőrizve és levágva. None, ha használhatatlan."""
    if not isinstance(d, dict):
        return None
    try:
        if kind in ("inbox",):
            items = [{"from": _str(i.get("from"), 60), "subject": _str(i.get("subject"), 120),
                      "snippet": _str(i.get("snippet"), 240), "category": _str(i.get("category"), 40),
                      "urgency": max(1, min(5, int(i.get("urgency") or 3))), "reply": _str(i.get("reply"), 600)}
                     for i in d.get("items", [])[:6] if isinstance(i, dict) and i.get("subject")]
            return {"items": items} if len(items) >= 3 else None
        if kind == "chat":
            msgs = [{"role": "agent" if m.get("role") == "agent" else "customer", "text": _str(m.get("text"), 400)}
                    for m in d.get("messages", [])[:10] if isinstance(m, dict) and m.get("text")]
            return {"messages": msgs, "handoff": _str(d.get("handoff"), 300)} if len(msgs) >= 4 else None
        if kind == "leads":
            items = [{"name": _str(i.get("name"), 60), "need": _str(i.get("need"), 240),
                      "score": max(0, min(100, int(i.get("score") or 0))),
                      "grade": (_str(i.get("grade"), 1).upper() or "C") if _str(i.get("grade"), 1).upper() in "ABCD" else "C",
                      "next": _str(i.get("next"), 200)}
                     for i in d.get("items", [])[:6] if isinstance(i, dict) and i.get("need")]
            return {"items": sorted(items, key=lambda x: -x["score"])} if len(items) >= 3 else None
        if kind == "document":
            cl = [{"text": _str(c.get("text"), 400), "risk": c.get("risk") if c.get("risk") in ("high", "medium") else "none",
                   "note": _str(c.get("note"), 240)}
                  for c in d.get("clauses", [])[:6] if isinstance(c, dict) and c.get("text")]
            return {"title": _str(d.get("title"), 120), "clauses": cl} if len(cl) >= 3 else None
        if kind == "report":
            m = [{"label": _str(x.get("label"), 60), "value": _str(x.get("value"), 30), "change": _str(x.get("change"), 30)}
                 for x in d.get("metrics", [])[:4] if isinstance(x, dict) and x.get("label")]
            f = [_str(x, 240) for x in d.get("findings", [])[:4] if x]
            a = [_str(x, 240) for x in d.get("actions", [])[:3] if x]
            return {"title": _str(d.get("title"), 120), "period": _str(d.get("period"), 60),
                    "metrics": m, "findings": f, "actions": a} if m and f else None
        if kind == "call":
            ln = [{"who": "agent" if x.get("who") == "agent" else "caller", "text": _str(x.get("text"), 300)}
                  for x in d.get("lines", [])[:10] if isinstance(x, dict) and x.get("text")]
            return {"lines": ln, "summary": _str(d.get("summary"), 400)} if len(ln) >= 4 else None
        if kind == "content":
            it = [{"channel": _str(x.get("channel"), 60), "title": _str(x.get("title"), 120), "text": _str(x.get("text"), 700)}
                  for x in d.get("items", [])[:4] if isinstance(x, dict) and x.get("text")]
            return {"items": it} if len(it) >= 2 else None
        if kind == "timeline":
            b = [{"time": _str(x.get("time"), 12), "task": _str(x.get("task"), 160)}
                 for x in d.get("before", [])[:6] if isinstance(x, dict) and x.get("task")]
            a = [{"time": _str(x.get("time"), 12), "task": _str(x.get("task"), 160)}
                 for x in d.get("after", [])[:6] if isinstance(x, dict) and x.get("task")]
            return {"before": b, "after": a} if len(b) >= 2 and len(a) >= 2 else None
    except (TypeError, ValueError, AttributeError):
        return None
    return None


# Ha a modell nem ad használható demót: egyszerű, általános idővonal.
FALLBACK = {
    "hu": {"before": [{"time": "08:30", "task": "Beérkezett levelek, kérések kézi átnézése"},
                      {"time": "10:00", "task": "Ugyanazok a válaszok újra és újra begépelve"},
                      {"time": "14:00", "task": "Adatok átmásolása egyik rendszerből a másikba"},
                      {"time": "17:30", "task": "Ami kimaradt, az holnapra csúszik"}],
           "after": [{"time": "08:30", "task": "Az agent már besorolta és rangsorolta, ami éjjel jött"},
                     {"time": "09:00", "task": "Te csak jóváhagyod az elkészült vázlatokat"},
                     {"time": "13:00", "task": "Az adatmozgatás magától lefut, eltérésnél szól"},
                     {"time": "16:00", "task": "Marad idő arra, amihez tényleg ember kell"}]},
    "en": {"before": [{"time": "08:30", "task": "Going through incoming emails and requests by hand"},
                      {"time": "10:00", "task": "Typing the same answers again and again"},
                      {"time": "14:00", "task": "Copying data from one system to another"},
                      {"time": "17:30", "task": "Whatever is left slips to tomorrow"}],
           "after": [{"time": "08:30", "task": "The agent has already sorted and ranked last night's requests"},
                     {"time": "09:00", "task": "You only approve the prepared drafts"},
                     {"time": "13:00", "task": "Data moves by itself, it flags any mismatch"},
                     {"time": "16:00", "task": "Time is left for the work that needs a person"}]},
    "de": {"before": [{"time": "08:30", "task": "Eingehende E-Mails und Anfragen von Hand durchgehen"}, {"time": "10:00", "task": "Immer wieder dieselben Antworten tippen"}, {"time": "14:00", "task": "Daten von einem System ins andere kopieren"}, {"time": "17:30", "task": "Was liegen bleibt, rutscht auf morgen"}],
           "after": [{"time": "08:30", "task": "Der Agent hat die Anfragen der Nacht schon sortiert und priorisiert"}, {"time": "09:00", "task": "Sie geben die fertigen Entwürfe nur noch frei"}, {"time": "13:00", "task": "Die Daten wandern von selbst, Abweichungen meldet er"}, {"time": "16:00", "task": "Es bleibt Zeit für die Arbeit, die einen Menschen braucht"}]},
    "es": {"before": [{"time": "08:30", "task": "Revisar a mano los correos y solicitudes entrantes"}, {"time": "10:00", "task": "Escribir las mismas respuestas una y otra vez"}, {"time": "14:00", "task": "Copiar datos de un sistema a otro"}, {"time": "17:30", "task": "Lo que queda pendiente pasa a mañana"}],
           "after": [{"time": "08:30", "task": "El agente ya ha clasificado y priorizado las solicitudes de la noche"}, {"time": "09:00", "task": "Usted solo aprueba los borradores preparados"}, {"time": "13:00", "task": "Los datos se mueven solos y avisa de cualquier diferencia"}, {"time": "16:00", "task": "Queda tiempo para el trabajo que necesita a una persona"}]},
    "fr": {"before": [{"time": "08:30", "task": "Trier à la main les e-mails et demandes reçus"}, {"time": "10:00", "task": "Retaper sans cesse les mêmes réponses"}, {"time": "14:00", "task": "Copier des données d'un système à l'autre"}, {"time": "17:30", "task": "Ce qui reste est repoussé au lendemain"}],
           "after": [{"time": "08:30", "task": "L'agent a déjà trié et priorisé les demandes de la nuit"}, {"time": "09:00", "task": "Vous validez seulement les brouillons préparés"}, {"time": "13:00", "task": "Les données circulent seules, il signale tout écart"}, {"time": "16:00", "task": "Il reste du temps pour le travail qui demande une personne"}]},
    "it": {"before": [{"time": "08:30", "task": "Controllare a mano email e richieste in arrivo"}, {"time": "10:00", "task": "Riscrivere sempre le stesse risposte"}, {"time": "14:00", "task": "Copiare dati da un sistema all'altro"}, {"time": "17:30", "task": "Quello che resta slitta a domani"}],
           "after": [{"time": "08:30", "task": "L'agente ha già ordinato e classificato le richieste della notte"}, {"time": "09:00", "task": "Lei approva solo le bozze già pronte"}, {"time": "13:00", "task": "I dati si spostano da soli, segnala ogni differenza"}, {"time": "16:00", "task": "Resta tempo per il lavoro che richiede una persona"}]},
    "ro": {"before": [{"time": "08:30", "task": "Parcurgerea manuală a e-mailurilor și cererilor primite"}, {"time": "10:00", "task": "Aceleași răspunsuri tastate din nou și din nou"}, {"time": "14:00", "task": "Copierea datelor dintr-un sistem în altul"}, {"time": "17:30", "task": "Ce rămâne nefăcut se mută pe mâine"}],
           "after": [{"time": "08:30", "task": "Agentul a sortat și prioritizat deja cererile din timpul nopții"}, {"time": "09:00", "task": "Dumneavoastră doar aprobați ciornele pregătite"}, {"time": "13:00", "task": "Datele se mută singure, iar diferențele sunt semnalate"}, {"time": "16:00", "task": "Rămâne timp pentru munca ce are nevoie de un om"}]},
    "sk": {"before": [{"time": "08:30", "task": "Ručné prechádzanie prichádzajúcich e-mailov a požiadaviek"}, {"time": "10:00", "task": "Stále dokola písanie tých istých odpovedí"}, {"time": "14:00", "task": "Kopírovanie údajov z jedného systému do druhého"}, {"time": "17:30", "task": "Čo zostane, presunie sa na zajtra"}],
           "after": [{"time": "08:30", "task": "Agent už roztriedil a zoradil požiadavky z noci"}, {"time": "09:00", "task": "Vy len schválite pripravené koncepty"}, {"time": "13:00", "task": "Údaje sa presúvajú samy, pri rozdiele upozorní"}, {"time": "16:00", "task": "Zostane čas na prácu, ktorá potrebuje človeka"}]},
    "zh": {"before": [{"time": "08:30", "task": "手动查看收到的邮件和请求"}, {"time": "10:00", "task": "一遍又一遍地输入相同的回复"}, {"time": "14:00", "task": "把数据从一个系统复制到另一个系统"}, {"time": "17:30", "task": "没做完的工作推到明天"}],
           "after": [{"time": "08:30", "task": "智能体已将夜间收到的请求分类并排好优先级"}, {"time": "09:00", "task": "您只需审批已准备好的草稿"}, {"time": "13:00", "task": "数据自动流转，发现差异会提醒"}, {"time": "16:00", "task": "把时间留给真正需要人来做的工作"}]},
}


# ------------------------------------------------------------ összeállítás

def make_slug(company: str, domain: str) -> str:
    base = unicodedata.normalize("NFKD", company or domain).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:40] or "ceg"
    return f"{base}-{secrets.token_hex(3)}"


def _valid_agent(a) -> str | None:
    return a if isinstance(a, str) and a in CATALOG else None


def build_page(url: str, *, ask, extract_json, lang: str | None = None, company: str | None = None,
               decision: dict | None = None, fetcher: Fetcher | None = None) -> dict:
    """A teljes oldal adata. ask(prompt) -> szöveg, extract_json(szöveg) -> dict.
    decision: a cégre korábban elmentett agent-választás (main, extras); ha van,
    nem választunk újra, így ugyanaz a cég mindig ugyanazt az agentet kapja."""
    url = normalize_url(url)
    if not host_ok(urlparse(url).hostname or ""):
        raise DemoError("Ez a cím nem nyilvános weboldal.")
    dom = domain_of(url)
    pages = crawl(url, fetcher)
    # Csak JavaScriptből felépülő oldalnál szinte üres a letöltött szöveg: abból
    # a modell csak találgatna, ezért ilyenkor is az általános oldal jön.
    if sum(len(p["text"]) for p in pages) < MIN_SITE_CHARS:
        return _generic(url, dom, lang or (pages[0]["lang"] if pages else "") or "hu", company, decision)

    site_lang = pages[0].get("lang") or guess_lang(" ".join(p["text"] for p in pages))
    out_lang = (lang or site_lang or "en")[:2].lower()
    if out_lang not in LANGS:
        out_lang = "en"
    data = None
    for avoid_support in (False, True):
        raw = ask(analyze_prompt(pages, out_lang, company, avoid_support))
        try:
            data = extract_json(raw)
        except Exception:  # noqa - egyszer újrapróbáljuk
            data = None
        if not isinstance(data, dict):
            data = None
            continue
        main = _valid_agent(data.get("main"))
        if main == "support" and not decision and not evidence_on_pages(data.get("support_evidence") or "", pages):
            data = None  # nincs valódi ügyfélszolgálati jel: válasszon mást
            continue
        break
    if not data:
        # Az oldalt elolvastuk, csak a modell válasza volt rossz: általános oldal
        # helyett hiba, hogy újra lehessen próbálni.
        raise ModelError("A modell nem adott használható elemzést, próbáld újra.")

    if decision and _valid_agent(decision.get("main")):
        main = decision["main"]
        extras = [e for e in decision.get("extras", []) if _valid_agent(e) and e != main][:2]
        reasons = {e.get("id"): e.get("reason") for e in data.get("extras", []) if isinstance(e, dict)}
        main_reason = _str(data.get("main_reason"), 500) if data.get("main") == main else ""
    else:
        main = _valid_agent(data.get("main")) or "custom"
        extras = []
        for e in data.get("extras", []) or []:
            if isinstance(e, dict) and _valid_agent(e.get("id")) and e["id"] != main and e["id"] not in extras:
                extras.append(e["id"])
        extras = extras[:2]
        reasons = {e.get("id"): e.get("reason") for e in data.get("extras", []) if isinstance(e, dict)}
        main_reason = _str(data.get("main_reason"), 500)

    name = _str(company or data.get("company"), 80) or dom
    summary = _str(data.get("summary"), 500)

    # Idézet: csak ha szó szerint ott van a megjelölt bekezdésben, és teljes mondat.
    _, paras = _site_digest(pages)
    quote = None
    qi = data.get("quote_paragraph")
    q = _str(data.get("quote"), 400)
    if isinstance(qi, int) and 0 <= qi < len(paras) and good_quote(q, paras[qi]):
        src_url = next((p["url"] for p in pages if paras[qi] in p["paras"]), pages[0]["url"])
        quote = {"text": q.strip("„“”\"' "), "url": src_url}

    work = []
    for w in data.get("work", []) or []:
        if isinstance(w, dict) and w.get("task") and evidence_on_pages(w.get("evidence") or "", pages):
            work.append(_str(w["task"], 160))
    work = work[:3]

    demo, steps = None, []
    kind = CATALOG[main]["kind"]
    reason_for_demo = main_reason or summary
    try:
        dd = extract_json(ask(demo_prompt(name, summary, main, reason_for_demo, out_lang)))
        demo = clean_demo(kind, dd.get("demo") if isinstance(dd, dict) else None)
        steps = [_str(s, 200) for s in (dd.get("steps") or [])[:3]] if isinstance(dd, dict) else []
    except Exception as e:  # noqa - a demó nélkül is van oldal
        logger.warning("demo content failed: %s", type(e).__name__)
    if demo is None:
        kind, demo = "timeline", FALLBACK[out_lang]

    return _page(url, dom, out_lang, name, summary, main, main_reason, extras, reasons, kind, demo,
                 steps, quote, work, _str(data.get("custom_idea"), 300) if main == "custom" else "",
                 generic=False)


def _page(url, dom, lang, name, summary, main, main_reason, extras, reasons, kind, demo, steps, quote,
          work, custom_idea, generic) -> dict:
    a = CATALOG[main]
    return {
        "url": url, "domain": dom, "lang": lang, "company": name, "summary": summary, "generic": generic,
        "quote": quote, "work": work,
        "main": {"id": main, "name": agent_name(main, lang), "reason": main_reason, "steps": steps,
                 "custom_idea": custom_idea, "price": list(a["price"]) if a["price"] else None,
                 "weeks": list(a["weeks"]) if a["weeks"] else None, "legal": bool(a.get("legal")),
                 "monthly": monthly_fee(main), "live": a.get("live"), "hours": a["hours"]},
        "extras": [{"id": e, "name": agent_name(e, lang), "reason": _str(reasons.get(e), 240),
                    "live": CATALOG[e].get("live")} for e in extras],
        "demo": {"kind": kind, **demo},
    }


def _generic(url, dom, lang, company, decision) -> dict:
    main = _valid_agent((decision or {}).get("main")) or "email"
    lang = (lang or "")[:2].lower()
    lang = lang if lang in LANGS else "en"
    return _page(url, dom, lang, _str(company, 80) or dom, "", main, "", [], {}, "timeline",
                 FALLBACK[lang], [], None, [], "", generic=True)


def generate(url: str, **kw) -> dict:
    """build_page a párhuzamossági korláttal: ha már kettő fut, legfeljebb
    3 percet vár, utána foglalt."""
    if not _SLOTS.acquire(timeout=180):
        raise DemoError("Most sok oldal készül egyszerre, próbáld újra egy perc múlva.")
    try:
        return build_page(url, **kw)
    finally:
        _SLOTS.release()


def public_view(row: dict) -> dict:
    """Amit a nyilvános oldal megkap: a belső számlálók és a lead nélkül."""
    data = json.loads(row["data"])
    return {"slug": row["slug"], "created_at": row["created_at"], "expires_at": row["expires_at"], **data}


def expires_at(now: datetime | None = None) -> str:
    return ((now or datetime.now(timezone.utc)) + timedelta(days=PAGE_DAYS)).isoformat(timespec="seconds")
