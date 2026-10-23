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
SITE_TEXT_CHARS = 40_000
MIN_SITE_CHARS = 300
PAGE_DAYS = 90
PUBLIC_BASE = "https://aximbra.hu/neked"
CONTACT_EMAIL = "aximbra@gmail.com"

# Egyszerre ennyi oldal készülhet: két modellhívás + hat letöltés oldalanként,
# az ingyenes Gemini-keret percenkénti korlátja ennél többet nem bír.
_SLOTS = threading.BoundedSemaphore(2)


class DemoError(RuntimeError):
    """A hívónak szóló, megmutatható hiba (rossz cím, tiltott cím, foglalt)."""


class ModelError(DemoError):
    """A modell kétszer egymás után sem adott használható elemzést."""



# ---------------------------------------------------------------- katalógus
# Az Emergent-féle katalógus: magyar név, ár- és átfutás-szöveg, mire jó.
# A díjak és átfutások az aximbra.hu-val egyeznek (frontend/src/i18n/*.js).
# kind = a demó formája az oldalon (frontend/src/neked/demos/).
CATALOG = {
    "email": {"name": "E-mail rendező", "name_en": "Email triage agent", "price_en": "HUF 150–400k", "lead_en": "2–3 weeks", "price": "150–400 ezer Ft", "price_min": 150_000, "price_max": 400_000,
              "lead": "2–3 hét", "demo": "https://aximbra.hu/demo/email-agent", "kind": "inbox",
              "does": "Beérkező leveleket kategorizál, sürgősséget állapít meg, továbbít és válaszvázlatot ír."},
    "lead": {"name": "Érdeklődő-minősítő", "name_en": "Lead qualifier", "price_en": "HUF 400k–1.2M", "lead_en": "2–3 weeks", "price": "400 ezer–1,2 millió Ft", "price_min": 400_000,
             "price_max": 1_200_000, "lead": "2–3 hét", "demo": "https://aximbra.hu/agent/erdeklodo-minosito?demo=1",
             "kind": "leads",
             "does": "Beérkező érdeklődőket/ajánlatkéréseket pontoz, minősít, kiegészíti adatokkal és a megfelelő "
                     "emberhez irányítja."},
    "admin": {"name": "Belső admin agent", "name_en": "Internal admin agent", "price_en": "HUF 150–400k", "lead_en": "2–3 weeks", "price": "150–400 ezer Ft", "price_min": 150_000, "price_max": 400_000,
              "lead": "2–3 hét", "demo": None, "kind": "timeline",
              "does": "Ismétlődő belső adminisztrációt végez: táblázatok, nyilvántartások, időpontok, emlékeztetők, "
                      "adatrögzítés."},
    "research": {"name": "Kutatási monitor", "name_en": "Research monitor", "price_en": "HUF 150–400k", "lead_en": "2–3 weeks", "price": "150–400 ezer Ft", "price_min": 150_000, "price_max": 400_000,
                 "lead": "2–3 hét", "demo": None, "kind": "report",
                 "does": "Folyamatosan figyel forrásokat (piac, versenytársak, pályázatok, jogszabályok, hírek) és "
                         "összefoglalót küld."},
    "content": {"name": "Tartalom-agent", "name_en": "Content agent", "price_en": "HUF 400k–1.2M", "lead_en": "2 weeks", "price": "400 ezer–1,2 millió Ft", "price_min": 400_000,
                "price_max": 1_200_000, "lead": "2 hét", "demo": None, "kind": "drafts",
                "does": "Tartalmat készít: posztok, hírlevelek, termékleírások, blogcikkek vázlatai a cég hangján."},
    "webshop": {"name": "Webshop-asszisztens", "name_en": "Webshop assistant", "price_en": "HUF 600k–1.5M", "lead_en": "2–4 weeks", "price": "600 ezer–1,5 millió Ft", "price_min": 600_000,
                "price_max": 1_500_000, "lead": "2–4 hét", "demo": "https://aximbra.hu/demo/webshop#ugyfelszolgalat",
                "kind": "chat",
                "does": "Online áruházban válaszol a vásárlói kérdésekre, terméket ajánl, rendelésállapotot ad, "
                        "visszáruzást kezel."},
    "sales": {"name": "Értékesítő agent", "name_en": "Sales agent", "price_en": "HUF 600k–1.5M", "lead_en": "2–4 weeks", "price": "600 ezer–1,5 millió Ft", "price_min": 600_000,
              "price_max": 1_500_000, "lead": "2–4 hét", "demo": None, "kind": "leads",
              "does": "Ajánlatot készít, utánkövet, személyre szabott megkereséseket ír, kezeli az értékesítési "
                      "folyamat lépéseit."},
    "it": {"name": "IT-üzemeltető agent", "name_en": "IT operations agent", "price_en": "HUF 600k–2M", "lead_en": "3–5 weeks", "price": "600 ezer–2 millió Ft", "price_min": 600_000,
           "price_max": 2_000_000, "lead": "3–5 hét", "demo": None, "kind": "inbox",
           "does": "IT-jegyeket kezel, rendszereket monitoroz, riaszt, rutinszerű üzemeltetési feladatokat végez."},
    "nis2": {"name": "NIS2-megfelelési agent", "name_en": "NIS2 compliance agent", "price_en": "HUF 600k–2M", "lead_en": "3–6 weeks", "price": "600 ezer–2 millió Ft", "price_min": 600_000,
             "price_max": 2_000_000, "lead": "3–6 hét", "demo": None, "kind": "report",
             "does": "Bizonyítékot gyűjt a NIS2-audithoz, nyilvántartja a kontrollokat és hiányosságokat "
                     "(támadás ellen nem véd)."},
    "recruit": {"name": "Toborzási agent", "name_en": "Recruitment agent", "price_en": "HUF 1.7–3.9M", "lead_en": "3–4 weeks + legal review", "price": "1,7–3,9 millió Ft", "price_min": 1_700_000,
                "price_max": 3_900_000, "lead": "3–4 hét + jogi átnézés", "demo": None, "kind": "leads",
                "does": "Önéletrajzokat előszűr, jelölteket rangsorol, interjúidőpontot egyeztet, álláshirdetést "
                        "fogalmaz."},
    "docs": {"name": "Dokumentum-elemző", "name_en": "Document analyser", "price_en": "HUF 2–4M", "lead_en": "4–5 weeks", "price": "2–4 millió Ft", "price_min": 2_000_000, "price_max": 4_000_000,
             "lead": "4–5 hét", "demo": "https://aximbra.hu/agent/dokumentum-elemzo?demo=1", "kind": "document",
             "does": "Szerződéseket, ajánlatokat, műszaki vagy jogi dokumentumokat olvas, kiemeli a kockázatos "
                     "pontokat, adatot kinyer."},
    "finance": {"name": "Pénzügyi asszisztens", "name_en": "Finance assistant", "price_en": "HUF 2–4M", "lead_en": "4–6 weeks", "price": "2–4 millió Ft", "price_min": 2_000_000,
                "price_max": 4_000_000, "lead": "4–6 hét", "demo": None, "kind": "report",
                "does": "Számlákat dolgoz fel, egyeztet, kintlévőséget követ, pénzügyi riportot készít."},
    "support": {"name": "Ügyfélszolgálati agent", "name_en": "Customer support agent", "price_en": "HUF 1.5–4M", "lead_en": "4–7 weeks", "price": "1,5–4 millió Ft", "price_min": 1_500_000,
                "price_max": 4_000_000, "lead": "4–7 hét", "demo": None, "kind": "chat",
                "does": "Ügyfélkérdésekre válaszol több csatornán (chat, e-mail), jegyet nyit, eszkalál emberhez."},
    "multi": {"name": "Multi-agent rendszer", "name_en": "Multi-agent system", "price_en": "HUF 6–15M", "lead_en": "7–12 weeks", "price": "6–15 millió Ft", "price_min": 6_000_000,
              "price_max": 15_000_000, "lead": "7–12 hét", "demo": None, "kind": "timeline",
              "does": "Több együttműködő agent egy összetett, több lépéses folyamat végigviteléhez."},
    "phone": {"name": "Telefonos AI-recepciós", "name_en": "AI phone receptionist", "price_en": "on quote (with a website from HUF 900k)", "lead_en": "on quote", "price": "ajánlat alapján (weboldallal együtt 900 ezer Ft-tól)",
              "price_min": 900_000, "price_max": None, "lead": "ajánlat alapján", "demo": "tel:+18024249852",
              "demo_label": "+1 802 424 9852", "kind": "call",
              "does": "Felveszi a telefont, válaszol a kérdésekre, időpontot foglal, üzenetet rögzít, leiratot "
                      "készít."},
    "custom": {"name": "Egyedi agent", "name_en": "Custom agent", "price_en": "on quote, after an assessment", "lead_en": "after an assessment", "price": "ajánlat alapján, felmérés után", "price_min": None,
               "price_max": None, "lead": "felmérés után", "demo": None, "kind": "timeline",
               "does": "A cég egy speciális folyamatára szabott agent, ha a fentiek egyike sem illik jól."},
}


def monthly_fee(agent_id: str) -> int | None:
    hi = CATALOG[agent_id]["price_max"]
    if hi is None:
        return None
    return 25_000 if hi <= 400_000 else 50_000 if hi <= 2_000_000 else 90_000


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
# Az elemző és a tartalomíró prompt, a demóformák és a felület szövegei az
# Emergent-féle generátorból jönnek (hutkaimilan/aximbra-demooldalak); a
# letöltés, az ellenőrzések és a mentés a miénk.

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"\+?\d[\d \-/()]{8,}\d")


def _scrub(s):
    """Elérhetőség nem kerülhet a generált szövegbe: se e-mail, se telefonszám."""
    return _EMAIL.sub("[e-mail]", _PHONE.sub("[…]", s)) if isinstance(s, str) else s


def _drop_contacts(s):
    """Az elemzés szövegeiből (indoklás, leírás) az elérhetőséget tartalmazó
    mondat egészében kimarad: egy "[e-mail]" helykitöltő egy valódi cégnek
    írt mondatban hibának látszik."""
    if not isinstance(s, str):
        return s
    parts = re.split(r"(?<=[.!?])\s+", s)
    return " ".join(p for p in parts if not (_EMAIL.search(p) or _PHONE.search(p))).strip()


def _str(v, n: int = 400) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def _catalog_text() -> str:
    return "\n".join(f'{k}: {a["name"]}: {a["does"]}' for k, a in CATALOG.items())


ANALYSIS_SYSTEM = f"""You are a senior AI-automation consultant at AXIMBRA, an AI agency. You analyse a company's PUBLIC website
text and decide which AXIMBRA AI agent would help them most. Work for ANY company: any industry, size, country,
language or business model. Derive everything ONLY from the provided website text.

HARD RULES:
- NEVER invent facts about the company. Only state what the website text supports. If unsure, be general.
- Never output personal data: no names of people, no e-mail addresses, no phone numbers.
- observation.quote MUST be copied VERBATIM (exact characters) from ONE item of a page's "PROSE" list (running text),
  never from menus, buttons, link texts, headings or bullet lists. It must be ONE complete, meaningful sentence of at
  least 8 words that contains a verb, 30-250 chars, and hint at repetitive manual work or a process an agent could
  take over (e.g. how they take requests, bookings, quotes, support, orders, documents, applications). It must not
  contain a person's name, e-mail or phone number. page_url = that page's URL exactly.
  If no such sentence exists, set "observation": null. Never paraphrase inside "quote".
- Pick exactly 1 main agent and at most 2 secondary agents from the catalog by id. Weigh ALL catalog entries and
  choose the one with the clearest, highest-value fit to the company's ACTUAL repetitive work evidenced on the site
  (what comes in to them repeatedly: calls, e-mails, enquiries, orders, documents, applications, invoices, tickets,
  content needs, compliance). Explain the choice in "reason" with reference to that evidence.
- The customer service agent ("support") may be the MAIN agent ONLY if the site really shows an FAQ, a support/help
  section or a customer-service contact. In that case fill "support_evidence" with a VERBATIM snippet from the page
  text that proves it (e.g. the FAQ heading or customer-service sentence) and its page_url. Otherwise set
  "support_evidence": null and do not choose "support" as main. If they sell through their own online store,
  "webshop" fits better than "support"; if phone is their main channel, consider "phone". If nothing fits well, use
  "custom" as main and fill custom_agent_idea with a concrete idea tailored to this company.
- what_it_does: 2-4 sentences, concrete, tailored to THEIR activity (what comes in, what the agent does, what a human approves).
- All text fields must be written in the output language given by the user message.

AXIMBRA catalog (id: name: what it does):
{_catalog_text()}

Return JSON:
{{"language": "ISO 639-1 code of the output language", "company_name": "...", "what_they_do": "1-2 sentences",
 "audience": "who they serve", "repetitive_work": ["2-5 short items"],
 "observation": {{"quote": "verbatim", "page_url": "...", "insight": "1-2 sentences why this matters for an agent"}} | null,
 "support_evidence": {{"quote": "verbatim", "page_url": "..."}} | null,
 "main_agent": {{"id": "email", "reason": "...", "what_it_does": "..."}},
 "secondary_agents": [{{"id": "lead", "reason": "..."}}],
 "custom_agent_idea": "..." | null}}"""


HU_UI = {
    "observation_label": "Amit a weboldalukon láttunk",
    "observation_source": "Forrás",
    "agent_label": "A javasolt agent",
    "why_label": "Miért ez",
    "steps_label": "Így dolgozna nálatok",
    "secondary_label": "Kiegészítésként",
    "custom_label": "Az egyedi ötlet",
    "demo_label": "Kattintható demó",
    "sample_badge": "Példaadatok",
    "live_demo": "Élő demó kipróbálása",
    "live_demo_phone": "Hívd fel az élő AI-recepcióst",
    "roi_title": "Mennyit hozhat?",
    "roi_hours": "Megspórolt óra havonta",
    "roi_rate": "Óradíj (Ft)",
    "roi_savings_month": "Havi megtakarítás",
    "roi_savings_year": "Éves megtakarítás",
    "roi_assumptions": "Feltételezések (módosítható)",
    "price_label": "Bevezetés ára (nettó)",
    "lead_label": "Átfutás",
    "fee_label": "Havidíj (felügyelet és javítás)",
    "payback_label": "Megtérülés",
    "months": "hónap",
    "per_month": "/ hó",
    "on_quote": "ajánlat alapján",
    "approval_note": "Minden agent-kimenetet ember hagy jóvá, mielőtt kimenne.",
    "cta": "Beszéljünk 20 percet",
    "cta_sub": "Megnézzük, hol hozná a legtöbbet nálatok, és kapsz egy konkrét ajánlatot.",
    "label_category": "Kategória",
    "label_urgency": "Sürgősség",
    "label_draft": "Válaszvázlat",
    "label_score": "Pontszám",
    "label_next_step": "Javasolt következő lépés",
    "label_risk": "Kockázat",
    "label_comment": "Agent megjegyzése",
    "label_before": "Előtte",
    "label_after": "Utána",
    "label_caller": "Hívó",
    "label_agent": "AI agent",
    "label_summary": "Összefoglaló",
    "label_customer": "Ügyfél",
    "label_answer": "Agent válasza",
    "label_play": "Lejátszás",
    "label_replay": "Újra",
    "label_approve": "Jóváhagyom",
    "label_approved": "Jóváhagyva",
    "label_select": "Válassz egy elemet a részletekhez",
    "label_brief": "Bemenet",
    "level_high": "Magas",
    "level_medium": "Közepes",
    "level_low": "Alacsony",
}

EN_UI = {
    "observation_label": "What we noticed on your website", "observation_source": "Source",
    "agent_label": "The recommended agent", "why_label": "Why this one", "steps_label": "How it would work for you",
    "secondary_label": "As a complement", "custom_label": "The custom idea", "demo_label": "Clickable demo",
    "sample_badge": "Sample data", "live_demo": "Try the live demo", "live_demo_phone": "Call the live AI receptionist",
    "roi_title": "What could it bring?", "roi_hours": "Hours saved per month", "roi_rate": "Hourly cost (HUF)",
    "roi_savings_month": "Monthly saving", "roi_savings_year": "Yearly saving",
    "roi_assumptions": "Assumptions (editable)", "price_label": "Implementation price (net)", "lead_label": "Lead time",
    "fee_label": "Monthly fee (monitoring and fixes)", "payback_label": "Payback", "months": "months",
    "per_month": "/ month", "on_quote": "on quote",
    "approval_note": "Every agent output is approved by a human before it goes out.",
    "cta": "Let's talk for 20 minutes",
    "cta_sub": "We'll look at where it would help you most, and you get a concrete proposal.",
    "label_category": "Category", "label_urgency": "Urgency", "label_draft": "Draft reply", "label_score": "Score",
    "label_next_step": "Suggested next step", "label_risk": "Risk", "label_comment": "Agent comment",
    "label_before": "Before", "label_after": "After", "label_caller": "Caller", "label_agent": "AI agent",
    "label_summary": "Summary", "label_customer": "Customer", "label_answer": "Agent reply", "label_play": "Play",
    "label_replay": "Replay", "label_approve": "Approve", "label_approved": "Approved",
    "label_select": "Pick an item to see the details", "label_brief": "Brief", "level_high": "High",
    "level_medium": "Medium", "level_low": "Low",
}

KIND_SPEC = {
    "inbox": "6 incoming e-mails/requests typical for THIS company. title=subject, subtitle=sender role (e.g. 'new "
             "customer', never a name), tag=category, level=urgency, body=the message (2-4 sentences), "
             "output=the agent's draft reply (2-4 sentences).",
    "leads": "6 incoming enquiries/leads (or job applicants if the agent is recruitment). title=short description, "
             "subtitle=source channel, score=0-100, tag=classification, body=the request text (2-3 sentences), "
             "output=recommended next step with short reasoning.",
    "document": "one typical document they handle (contract, offer, specification, application...). demo.title=document "
                "name. 6 items = clauses: title=clause heading, body=clause text (1-3 sentences), level=risk, "
                "output=agent comment (what to check / change).",
    "call": "one phone call to them. 8-10 items alternating between the caller and the AI receptionist: "
            "subtitle='caller' or 'agent' (literally these two values), body=the spoken line. demo.summary=what the "
            "agent captured and the next step.",
    "report": "a report the agent delivers to them. 5 items: title=section or KPI, tag=headline figure, level=importance, "
              "body=finding (1-2 sentences), output=recommended action.",
    "timeline": "a typical working day. 6 items: title=time (e.g. 08:30), subtitle=task, body=how it goes today by hand, "
                "output=how it goes with the agent.",
    "chat": "3 customer conversations. title=topic, body=the customer's message, output=the agent's answer, "
            "tag=outcome (e.g. answered / handed to a human).",
    "drafts": "4 content pieces the agent drafts for them. title=piece title, subtitle=channel, tag=format, "
              "body=the brief/input, output=the draft (3-5 sentences).",
}

CONTENT_SYSTEM = """You write the content of a personalised demo page for AXIMBRA, an AI agency, showing a company what one
specific AI agent would do for THEM. Output language is given; write every text field in it.
RULES:
- Never claim facts about the company beyond the provided analysis. Sample data is clearly fictional but realistic for
  their activity (their kind of customers, products/services, requests). No real people's names, no e-mail addresses,
  no phone numbers, no real customer names; use roles ("a new customer", "a supplier").
- Keep texts short and concrete. Every agent output is approved by a human.
- roi.assumptions come first: 3-4 short estimates, at least a monthly volume, the minutes of manual work per item and
  the share the agent takes over. roi.hours_per_month MUST be the arithmetic result of those assumptions
  (volume x minutes x share / 60, rounded), between 5 and 120; adjust the assumptions rather than the result.
  roi.hourly_rate_huf: realistic loaded hourly labour cost in Hungarian forints for staff doing this work in their
  country (e.g. Hungary ~6000-12000 HUF). Write the assumptions clearly as estimates.
- quote_check: judge the given website quote (if any): full_sentence = is it one complete, meaningful sentence
  (not a menu, button, link text or list)? has_verb = does it contain a finite verb?
Return JSON only."""


def _content_schema(kind: str, need_ui: bool, names: dict) -> str:
    ui = ', "ui": {same keys as UI_SOURCE plus "title" ("What an AI agent would do at <Company>"), "footer" ' \
         '("This demo is based on <Company>\'s public website; the sample data is fictional.") and "footer_generic" ' \
         '("This demo was prepared for <Company>; their website could not be read, and the sample data is fictional."),' \
         ' all translated}' if need_ui else ""
    if names:
        ui += ', "agent_names": {"<id>": "agent name translated into the output language"} for ' + \
              json.dumps(names, ensure_ascii=False)
    return ('{"hero_subtitle": "1 sentence", "agent_pitch": "2-3 sentences, what the agent does for them", '
            '"agent_steps": ["3-4 short steps: what comes in -> what the agent does -> what a human approves"], '
            '"demo": {"title": "...", "intro": "1 sentence", "summary": "", "items": [{"title": "", "subtitle": "", '
            '"tag": "", "level": "high|medium|low|", "score": null, "body": "", "output": ""}]}, '
            '"roi": {"hours_per_month": 30, "hourly_rate_huf": 8000, "assumptions": ["..."]}, '
            '"price_text": "price translated, numbers unchanged", "lead_text": "only the duration translated, no label", '
            '"quote_check": {"full_sentence": true, "has_verb": true} | null' + ui + "}"
            f"\nDEMO ({kind}): {KIND_SPEC[kind]}")


# ---- a modell válaszainak ellenőrzése ---------------------------------------

def _ask_json(ask, extract_json, system: str, user: str, check):
    """Modellhívás JSON-válasszal; `check(dict)` visszaadja a tiszta adatot, vagy
    ValueError-t dob. Egyszer visszaküldjük a hibát javításra, utána None.
    A modell elérhetetlensége (LLMError) nem itt dől el: továbbmegy a hívóhoz."""
    prompt = f"{system}\n\n{user}"
    for attempt in range(2):
        raw = ask(prompt)  # elérhetetlen modell: a hiba innen továbbmegy
        try:
            data = extract_json(raw)
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
            return check(data)
        except Exception as e:  # noqa: BLE001 - hibás JSON vagy alak: egyszer javíttatjuk
            logger.warning("demo: invalid model answer (attempt %s): %s", attempt + 1, str(e)[:200])
            prompt = (f"{system}\n\n{user}\n\nYour previous answer was invalid: {str(e)[:300]}. "
                      "Return ONLY valid JSON matching the schema.")
    return None


def _check_analysis(d: dict) -> dict:
    main = d.get("main_agent") or {}
    if not isinstance(main, dict) or main.get("id") not in CATALOG:
        raise ValueError("main_agent.id must be a catalog id")
    sec = []
    for s in d.get("secondary_agents") or []:
        if isinstance(s, dict) and s.get("id") in CATALOG and s["id"] != main["id"] \
                and s["id"] not in [x["id"] for x in sec]:
            sec.append({"id": s["id"], "reason": _drop_contacts(_str(s.get("reason"), 300))})
    obs = d.get("observation") if isinstance(d.get("observation"), dict) else None
    ev = d.get("support_evidence") if isinstance(d.get("support_evidence"), dict) else None
    return {
        "language": _str(d.get("language"), 12).lower(),
        "company_name": _str(d.get("company_name"), 80),
        "what_they_do": _drop_contacts(_str(d.get("what_they_do"), 400)),
        "audience": _drop_contacts(_str(d.get("audience"), 200)),
        "repetitive_work": [_drop_contacts(_str(x, 160)) for x in (d.get("repetitive_work") or [])[:5] if x],
        "observation": {"quote": _str(obs.get("quote"), 400), "page_url": _str(obs.get("page_url"), 500),
                        "insight": _drop_contacts(_str(obs.get("insight"), 400))} if obs else None,
        "support_evidence": _str(ev.get("quote"), 300) if ev else "",
        "main": main["id"],
        "reason": _drop_contacts(_str(main.get("reason"), 600)),
        "what_it_does": _drop_contacts(_str(main.get("what_it_does"), 800)),
        "secondary": sec[:2],
        "custom_idea": _drop_contacts(_str(d.get("custom_agent_idea"), 400)),
    }


_LEVELS = ("high", "medium", "low")


def _check_content(d: dict) -> dict:
    demo = d.get("demo") or {}
    items = []
    for it in (demo.get("items") or [])[:10]:
        if not isinstance(it, dict):
            continue
        score = it.get("score")
        try:
            score = max(0, min(100, int(score))) if score is not None else None
        except (TypeError, ValueError):
            score = None
        items.append({"title": _scrub(_str(it.get("title"), 160)), "subtitle": _scrub(_str(it.get("subtitle"), 80)),
                      "tag": _scrub(_str(it.get("tag"), 60)),
                      "level": it.get("level") if it.get("level") in _LEVELS else "",
                      "score": score, "body": _scrub(_str(it.get("body"), 900)),
                      "output": _scrub(_str(it.get("output"), 1200))})
    if len(items) < 3:
        raise ValueError("need at least 3 demo items")
    roi = d.get("roi") or {}
    try:
        hours = max(1, min(200, int(roi.get("hours_per_month"))))
        rate = max(1000, min(60_000, int(roi.get("hourly_rate_huf"))))
    except (TypeError, ValueError):
        raise ValueError("roi.hours_per_month and roi.hourly_rate_huf must be numbers")
    qc = d.get("quote_check") if isinstance(d.get("quote_check"), dict) else None
    ui = d.get("ui") if isinstance(d.get("ui"), dict) else None
    names = d.get("agent_names") if isinstance(d.get("agent_names"), dict) else {}
    return {
        "hero_subtitle": _scrub(_str(d.get("hero_subtitle"), 300)),
        "agent_pitch": _scrub(_str(d.get("agent_pitch"), 600)),
        "agent_steps": [_scrub(_str(x, 200)) for x in (d.get("agent_steps") or [])[:4] if x],
        "demo": {"title": _scrub(_str(demo.get("title"), 160)), "intro": _scrub(_str(demo.get("intro"), 300)),
                 "summary": _scrub(_str(demo.get("summary"), 600)), "items": items},
        "roi": {"hours_per_month": hours, "hourly_rate_huf": rate,
                "assumptions": [_scrub(_str(x, 200)) for x in (roi.get("assumptions") or [])[:4] if x]},
        "price_text": _str(d.get("price_text"), 120),
        "lead_text": _str(d.get("lead_text"), 80),
        "quote_ok": None if not qc else bool(qc.get("full_sentence")) and bool(qc.get("has_verb")),
        "ui": {k: _str(v, 200) for k, v in ui.items() if isinstance(v, str)} if ui else None,
        "agent_names": {str(k): _str(v, 80) for k, v in names.items() if isinstance(v, str)},
    }


# ---- magyar nyelvtan a címhez -------------------------------------------------

_VOWELS = "aáeéiíoóöőuúüű"


def hu_article(name: str) -> str:
    first = name.strip()[:1].lower()
    if not first.isalpha():
        return "a(z)"
    return "az" if first in _VOWELS else "a"


# A cégforma rövidítését betűzve mondjuk ("bé-té", "ká-ef-té"), ezért -nél.
_LEGAL_FORM = re.compile(r"\b(kft|bt|zrt|nyrt|kkt|ev|e\.v)\.?$", re.I)


def hu_suffix(name: str) -> str:
    if _LEGAL_FORM.search(name.strip()):
        return "nél"
    last = name.split()[-1] if name.split() else name
    if len(last) > 1 and last.isupper():
        # Betűszó: az utolsó betű nevének hangja dönt (OTP = ó-té-pé -> -nél,
        # MOL = em-o-el -> -nél, BKK = bé-ká-ká -> -nál).
        return "nál" if last[-1] in "AÁHKOÓUÚ" else "nél"
    vowels = [c for c in name.lower() if c in _VOWELS]
    return "nál" if vowels and vowels[-1] in "aáoóuú" else "nél"


def hu_with_suffix(name: str) -> str:
    """Rag a cégnévhez: közvetlenül ("Bortársaságnál"), kötőjellel csak
    rövidítés, betűszó, domain, szám vagy írásjel után ("Kft.-nél", "OTP-nél",
    "Kifli.hu-nál")."""
    name = name.strip()
    last = name.split()[-1] if name.split() else name
    hyphen = (not name[-1:].isalpha() or _LEGAL_FORM.search(name) or "." in last
              or (len(last) > 1 and last.isupper()))
    return f"{name}{'-' if hyphen else ''}{hu_suffix(name)}"


def title_and_footer(company: str, lang: str, ui: dict, generic: bool) -> tuple[str, str]:
    if lang.startswith("hu"):
        art = hu_article(company)
        footer = (f"Ez a bemutató {art} {company} számára készült; a weboldaluk nem volt olvasható, a példaadatok "
                  "kitaláltak.") if generic else \
            f"Ez a bemutató {art} {company} nyilvános weboldala alapján készült; a példaadatok kitaláltak."
        return f"Ezt csinálná egy AI agent {art} {hu_with_suffix(company)}", footer
    if generic:
        footer = ui.get("footer_generic") or (f"This demo was prepared for {company}; their website could not be "
                                              "read, and the sample data is fictional.")
    else:
        footer = ui.get("footer") or f"This demo is based on {company}'s public website; the sample data is fictional."
    return ui.get("title") or f"What an AI agent would do at {company}", footer


# Ha a modell a nyelv nélküli (olvashatatlan) oldalhoz sem ad tartalmat:
# általános, semmit nem állító e-mail-rendező demó.
FALLBACK = {
    "hu": {
        "hero_subtitle": "Egy AI agent átveszi a beérkező levelek rendezését, ti csak jóváhagytok.",
        "agent_pitch": "Az E-mail rendező minden beérkező levelet elolvas, kategorizál, megjelöli a sürgőseket, "
                       "és válaszvázlatot ír. A végső szót mindig egy kollégátok mondja ki.",
        "agent_steps": ["Beérkezik egy levél", "Az agent kategorizál és sürgősséget állapít meg",
                        "Válaszvázlatot ír", "Egy kolléga jóváhagyja és elküldi"],
        "demo": {"title": "Beérkező levelek", "intro": "Kattints egy levélre a kategóriáért és a válaszvázlatért.",
                 "summary": "", "items": [
                     {"title": "Árajánlatot kérnék", "subtitle": "Új érdeklődő", "tag": "Ajánlatkérés",
                      "level": "high", "score": None,
                      "body": "Jó napot! Szeretnénk árajánlatot kérni a szolgáltatásukra a jövő hónapra. Mikor "
                              "tudnának válaszolni?",
                      "output": "Köszönjük megkeresését! Az ajánlathoz pár adatot kérnénk: mekkora mennyiségről és "
                                "milyen határidőről van szó? Két munkanapon belül küldjük az ajánlatot."},
                     {"title": "Számla másolat", "subtitle": "Meglévő ügyfél", "tag": "Pénzügy", "level": "medium",
                      "score": None, "body": "Kérem, küldjék el újra a múlt havi számlát, mert nem találom.",
                      "output": "Természetesen, mellékelten küldjük a múlt havi számla másolatát."},
                     {"title": "Időpont módosítás", "subtitle": "Meglévő ügyfél", "tag": "Ügyintézés",
                      "level": "medium", "score": None, "body": "A csütörtöki egyeztetést át tudnánk tenni péntekre?",
                      "output": "Köszönjük a jelzést! Pénteken 10 és 14 óra között van szabad időpontunk, melyik "
                                "lenne megfelelő?"},
                     {"title": "Hírlevél ajánlat", "subtitle": "Külső partner", "tag": "Egyéb", "level": "low",
                      "score": None, "body": "Hirdetési lehetőséget kínálunk a hírlevelünkben.",
                      "output": "Köszönjük, jelenleg nem tervezünk ilyen együttműködést."}]},
        "roi": {"hours_per_month": 20, "hourly_rate_huf": 8000,
                "assumptions": ["Havi kb. 400 beérkező levél", "Levelenként átlag 3 perc kézi munka",
                                "Az agent ennek kb. 70%-át átveszi"]},
    },
    "en": {
        "hero_subtitle": "An AI agent sorts your incoming e-mail, you just approve.",
        "agent_pitch": "The E-mail sorter reads every incoming message, categorises it, flags urgent ones and drafts a "
                       "reply. A member of your team always has the final word.",
        "agent_steps": ["An e-mail arrives", "The agent categorises it and sets urgency", "It drafts a reply",
                        "A colleague approves and sends"],
        "demo": {"title": "Incoming e-mail", "intro": "Click a message to see its category and draft reply.",
                 "summary": "", "items": [
                     {"title": "Request for a quote", "subtitle": "New prospect", "tag": "Quote", "level": "high",
                      "score": None,
                      "body": "Hello, we would like a quote for your services next month. When could you reply?",
                      "output": "Thank you for reaching out! Could you tell us the volume and deadline? We'll send the "
                                "quote within two working days."},
                     {"title": "Invoice copy", "subtitle": "Existing customer", "tag": "Finance", "level": "medium",
                      "score": None, "body": "Could you resend last month's invoice? I can't find it.",
                      "output": "Of course, please find last month's invoice attached."},
                     {"title": "Reschedule meeting", "subtitle": "Existing customer", "tag": "Admin",
                      "level": "medium", "score": None, "body": "Could we move Thursday's meeting to Friday?",
                      "output": "Thanks for letting us know! We are free on Friday between 10:00 and 14:00 — which "
                                "suits you?"},
                     {"title": "Newsletter offer", "subtitle": "External vendor", "tag": "Other", "level": "low",
                      "score": None, "body": "We offer advertising space in our newsletter.",
                      "output": "Thank you, we are not planning such a collaboration at the moment."}]},
        "roi": {"hours_per_month": 20, "hourly_rate_huf": 8000,
                "assumptions": ["About 400 incoming e-mails a month", "About 3 minutes of manual work each",
                                "The agent takes over about 70% of it"]},
    },
}


# ------------------------------------------------------------ összeállítás

def make_slug(company: str, domain: str) -> str:
    base = unicodedata.normalize("NFKD", company or domain).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:40] or "ceg"
    return f"{base}-{secrets.token_hex(3)}"


def _site_text(pages: list[dict]) -> str:
    """A modellnek: oldalanként a szöveg és a folyó szöveges bekezdések
    (PROSE), csak ezekből lehet idézni."""
    parts = []
    for p in pages:
        prose = "\n".join(f"- {b}" for b in p["paras"][:25])
        parts.append(f"=== PAGE: {p['url']}\nTITLE: {p['title']}\nTEXT:\n{p['text'][:5000]}\n"
                     f"PROSE (allowed quote sources):\n{prose}")
    return "\n\n".join(parts)[:SITE_TEXT_CHARS]


def verify_observation(obs: dict | None, pages: list[dict]) -> dict | None:
    """Az idézet csak akkor marad, ha egy letöltött oldal folyó szövegében szó
    szerint ott van, teljes mondat, és nincs benne elérhetőség vagy felsorolásjel."""
    if not obs or re.search(r"[|•»›·]", obs["quote"]):
        return None
    ordered = sorted(pages, key=lambda p: p["url"] != obs["page_url"])
    for p in ordered:
        for para in p["paras"]:
            if good_quote(obs["quote"], para):
                return {"quote": obs["quote"].strip().strip("„“”\"' "), "page_url": p["url"],
                        "insight": obs["insight"]}
    return None


def _generic_analysis(company: str, lang: str, decision: dict | None) -> dict:
    main = (decision or {}).get("main") if (decision or {}).get("main") in CATALOG else "email"
    sec = [e for e in (decision or {}).get("extras", []) if e in CATALOG and e != main][:2] \
        if decision else ["admin", "support"]
    return {"language": lang, "company_name": company, "what_they_do": "", "audience": "", "repetitive_work": [],
            "observation": None, "support_evidence": "", "main": main, "reason": "", "what_it_does": "",
            "secondary": [{"id": s, "reason": ""} for s in sec], "custom_idea": "", "generic": True}


def _analyze(pages, ask, extract_json, lang, company, decision) -> dict:
    site_lang = pages[0].get("lang") or guess_lang(" ".join(p["text"] for p in pages)) or ""
    lang_rule = f"Output language: {lang}." if lang else (
        f"Output language: the main language of the website text (html lang attribute hint: '{site_lang}'). "
        "Detect it from the text itself.")
    name_rule = f"Company name (given): {company}." if company else (
        f"Company name: derive the brand name from the website (title hint: '{pages[0]['title'][:80]}', "
        f"domain: {domain_of(pages[0]['url'])}).")
    user = f"{lang_rule}\n{name_rule}\n\nWEBSITE:\n{_site_text(pages)}"
    if decision:
        user += (f"\n\nTHE AGENT CHOICE IS ALREADY DECIDED: main agent id {decision['main']}, secondary agent ids "
                 f"{decision.get('extras', [])}. Use exactly these ids and write the reasons/what_it_does for them.")
    a = _ask_json(ask, extract_json, ANALYSIS_SYSTEM, user, _check_analysis)
    if a is None:
        raise ModelError("A modell nem adott használható elemzést, próbáld újra.")
    if decision:
        if a["main"] != decision["main"]:
            a.update(main=decision["main"], reason="", what_it_does="")
        reasons = {s["id"]: s["reason"] for s in a["secondary"]}
        a["secondary"] = [{"id": e, "reason": reasons.get(e, "")} for e in decision.get("extras", [])
                          if e in CATALOG and e != a["main"]][:2]
    elif a["main"] == "support" and not evidence_on_pages(a["support_evidence"], pages):
        retry = _ask_json(ask, extract_json, ANALYSIS_SYSTEM, user + (
            "\n\nIMPORTANT: no FAQ/support/customer-service evidence could be verified on this site, so \"support\" "
            "must NOT be the main agent. Choose the agent that fits their actual repetitive work."), _check_analysis)
        if retry and retry["main"] != "support":
            a = retry
        else:
            alt = next((s for s in a["secondary"] if s["id"] != "support"), None)
            if alt is None:
                a.update(main="custom", reason="", what_it_does="")
            else:
                a.update(main=alt["id"], reason=alt["reason"], what_it_does="")
            a["secondary"] = [s for s in a["secondary"] if s["id"] not in ("support", a["main"])]
    if company:
        a["company_name"] = _str(company, 80)
    if a["main"] != "custom":
        a["custom_idea"] = ""
    a["observation"] = verify_observation(a["observation"], pages)
    a["generic"] = False
    return a


def _content(a: dict, lang: str, ask, extract_json) -> dict | None:
    agent = CATALOG[a["main"]]
    kind = agent["kind"]
    is_hu, is_en = lang.startswith("hu"), lang.startswith("en")
    need_ui = not (is_hu or is_en)
    names = {} if is_hu else {k: CATALOG[k]["name"] for k in [a["main"], *[s["id"] for s in a["secondary"]]]}
    facts = ("NO website could be read: write a general page for this company name only, assume nothing about "
             "their activity, keep sample data neutral.") if a["generic"] else json.dumps({
        "what_they_do": a["what_they_do"], "audience": a["audience"], "repetitive_work": a["repetitive_work"],
        "agent_reason": a["reason"], "agent_what_it_does": a["what_it_does"],
        "custom_agent_idea": a["custom_idea"]}, ensure_ascii=False)
    quote = a["observation"]["quote"] if a["observation"] else None
    user = (f"Output language: {lang}\nCompany: {a['company_name']}\nAgent: {agent['name']} — {agent['does']}\n"
            f"Price: {agent['price']}; lead time: {agent['lead']}\nAnalysis: {facts}\n"
            f"Website quote to judge: {json.dumps(quote, ensure_ascii=False)}\n"
            + (f"UI_SOURCE (translate values): {json.dumps(EN_UI, ensure_ascii=False)}\n" if need_ui else "")
            + f"JSON schema:\n{_content_schema(kind, need_ui, names)}")
    return _ask_json(ask, extract_json, CONTENT_SYSTEM, user, _check_content)


def _strip_label(s: str) -> str:
    return re.sub(r"^[^:\d]{1,30}:\s*", "", s or "").strip()


def build_page(url: str, *, ask, extract_json, lang: str | None = None, company: str | None = None,
               decision: dict | None = None, fetcher: Fetcher | None = None) -> dict:
    """A teljes oldal adata. ask(prompt) -> szöveg, extract_json(szöveg) -> dict.
    decision: a cégre korábban elmentett agent-választás (main, extras); ha van,
    nem választunk újra, így ugyanaz a cég mindig ugyanazt az agentet kapja."""
    url = normalize_url(url)
    if not host_ok(urlparse(url).hostname or ""):
        raise DemoError("Ez a cím nem nyilvános weboldal.")
    dom = domain_of(url)
    lang = (lang or "").strip().lower() or None
    pages = crawl(url, fetcher)
    # Csak JavaScriptből felépülő oldalnál szinte üres a letöltött szöveg: abból
    # a modell csak találgatna, ezért ilyenkor általános oldal készül.
    readable = sum(len(p["text"]) for p in pages) >= MIN_SITE_CHARS
    if readable:
        a = _analyze(pages, ask, extract_json, lang, company, decision)
    else:
        page_lang = lang or (pages[0]["lang"] if pages else "") or "hu"
        a = _generic_analysis(_str(company, 80) or dom, page_lang, decision)
    out_lang = (lang or a["language"] or (pages[0]["lang"] if pages else "") or "hu")[:12]

    c = _content(a, out_lang, ask, extract_json)
    if c is None:
        if not a["generic"]:
            # Az oldalt elolvastuk, csak a tartalom nem lett jó: nem mentünk
            # hozzá nem illő általános demót, inkább újra lehet próbálni.
            raise ModelError("A modell nem adott használható demótartalmat, próbáld újra.")
        fb = FALLBACK["hu" if out_lang.startswith("hu") else "en"]
        c = {**fb, "price_text": "", "lead_text": "", "quote_ok": None, "ui": None, "agent_names": {}}
        a["main"], a["secondary"] = "email", [s for s in a["secondary"] if s["id"] != "email"]
        if not out_lang.startswith("hu"):
            out_lang = "en"

    is_hu = out_lang.startswith("hu")
    ui = HU_UI if is_hu else {**EN_UI, **{k: v for k, v in (c["ui"] or {}).items() if v}}
    company_name = a["company_name"] or dom
    title, footer = title_and_footer(company_name, out_lang, ui, a["generic"])
    obs = a["observation"]
    if obs and c["quote_ok"] is False:
        obs = None
    agent = CATALOG[a["main"]]
    names = c["agent_names"]
    return {
        "url": url, "domain": dom, "company": company_name, "lang": out_lang, "generic": a["generic"],
        "title": title, "footer": footer, "ui": ui, "hero_subtitle": c["hero_subtitle"],
        "observation": obs,
        "agent": {
            "id": a["main"], "name": names.get(a["main"]) or agent["name" if is_hu else "name_en"],
            "demo_url": agent["demo"], "demo_label": agent.get("demo_label"),
            "price_text": agent["price"] if is_hu else _strip_label(c["price_text"]) or agent["price_en"],
            "lead_text": agent["lead"] if is_hu else _strip_label(c["lead_text"]) or agent["lead_en"],
            "price_min": agent["price_min"], "price_max": agent["price_max"], "monthly_fee": monthly_fee(a["main"]),
            "reason": a["reason"],
            "what_it_does": a["what_it_does"] or c["agent_pitch"] or agent["does"],
            "steps": c["agent_steps"], "custom_idea": a["custom_idea"] or None,
        },
        "secondary": [{"id": s["id"], "name": names.get(s["id"]) or CATALOG[s["id"]]["name" if is_hu else "name_en"],
                       "reason": s["reason"]} for s in a["secondary"]],
        "demo": {"kind": agent["kind"], **c["demo"]},
        "roi": c["roi"],
        "contact_email": CONTACT_EMAIL,
    }


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
