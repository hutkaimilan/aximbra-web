"""Ajánlatkérő űrlap: a lap el tudja küldeni, amit valaki beír.

Miért kell egyáltalán:

Eddig minden hívás-a-cselekvésre gomb a látogató levelezőprogramját nyitotta
meg. Telefonon ez a lépés a legtöbb érdeklődőt elveszíti: kilép a böngészőből,
egy üres levélbe kerül, és ott már nem az a kérdés, hogy megírja-e, hanem hogy
visszatalál-e.

Két tervezési döntés, amit indokolni kell:

1. Ha nincs beállítva a kézbesítés, az űrlap meg sem jelenik. Egy űrlap, ami
   „Köszönjük, hamarosan jelentkezünk"-öt ír ki, miközben a levél sehova nem
   megy, rosszabb, mint a régi mailto-gomb: csendben veszít el egy ügyfelet.
   A `/status` végpont miatt a bekapcsolás egy Railway-változó, nem új deploy.

2. Nincs adatbázis. A beküldött adat egyetlen levélben megy az üzemeltetőhöz,
   és a kiszolgálón nem marad. Kevesebb hely, ahonnan kiszivároghat, és az
   adatkezelési tájékoztató is ezt tudja állítani — igazul.

Spam ellen: rejtett csapdamező, minimális kitöltési idő, IP-nkénti és napi
korlát. Szándékosan nincs harmadik féltől való CAPTCHA: az egy külső szkript
és egy újabb adatkezelő lenne egy olyan lapon, ami épp az ellenkezőjét ígéri.

Két kézbesítési út van, és a Resend az elsőbbségi:

- **Resend (HTTPS)**, ha van `RESEND_API_KEY`. A Railway a Pro csomag alatt
  letiltja a kimenő SMTP-t, és ez élesben pontosan így derült ki: az űrlap
  „bekapcsolva" jelentett, a naplóban „ENABLED" állt, a próbaküldés pedig
  OSError-ral bukott, mert a 465-ös port el sem érhető. HTTPS-en nincs ilyen
  tiltás, és a telefonos agent is ezen küld.
- **SMTP**, ha nincs Resend-kulcs. Induláskor megnézzük, elérhető-e egyáltalán
  a port, és ha nem, az űrlap nem jelenik meg — ugyanazzal az indokkal, mint
  a hiányzó beállításnál.
"""
import asyncio
import logging
import os
import re
import smtplib
import socket
import ssl
import threading
import time
from datetime import date
from email.message import EmailMessage

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/contact")

MAX_NAME = 120
MAX_EMAIL = 200
MAX_COMPANY = 160
MAX_MESSAGE = 4000
# Egy ember nem tölt ki értelmesen egy űrlapot két másodperc alatt.
MIN_FILL_SECONDS = 2
MAX_PER_IP_HOUR = 5
MAX_PER_DAY = 60
SMTP_TIMEOUT_SECONDS = 15
SMTP_PROBE_SECONDS = 8
RESEND_URL = "https://api.resend.com/emails"
RESEND_TIMEOUT_SECONDS = 15
# A Resend saját tesztfeladója. Ellenőrzött domain nélkül csak a Resend-fiók
# saját címére kézbesít — ezért kell a LEAD_TO, és ezért jó így: a levél úgyis
# az üzemeltetőnek szól.
RESEND_DEFAULT_FROM = "AXIMBRA <onboarding@resend.dev>"

# Nem teljes RFC 5322 — az úgysem mond semmit arról, hogy létezik-e a cím.
# Annyi a dolga, hogy a nyilvánvaló elgépelést még a küldés előtt megfogja.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")

_ip_hits: dict[str, list[float]] = {}
_day_state = {"day": date.today(), "count": 0}

# None: még nem tudjuk (induláskor a próba fut, vagy nincs SMTP). False: a port
# nem érhető el, az űrlap nem jelenhet meg. Egyszer False, az is marad az
# újraindulásig: egy tiltott port nem nyílik ki magától.
_smtp_reachable: dict[str, bool | None] = {"value": None}


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def resend_config() -> dict | None:
    """Kézbesítés a Resend HTTPS API-ján, vagy None, ha nincs kulcs vagy címzett."""
    key = _env("RESEND_API_KEY")
    to = _env("LEAD_TO") or _env("SMTP_USER")
    if not (key and to):
        return None
    return {"via": "resend", "key": key, "to": to, "from": _env("RESEND_FROM") or RESEND_DEFAULT_FROM}


def smtp_config() -> dict | None:
    """Az SMTP-kézbesítés beállításai, vagy None, ha hiányos.

    Mind kell: hiányos beállítással a küldés a felhasználó szeme láttára bukna
    el, ami rosszabb, mint be sem kapcsolni.
    """
    host, user, password = _env("SMTP_HOST"), _env("SMTP_USER"), _env("SMTP_PASSWORD")
    to = _env("LEAD_TO") or user
    if not (host and user and password and to):
        return None
    try:
        port = int(_env("SMTP_PORT", "465"))
    except ValueError:
        logger.warning("SMTP_PORT is not a number, falling back to 465")
        port = 465
    return {
        "via": "smtp", "host": host, "port": port, "user": user, "password": password,
        "to": to, "from": _env("LEAD_FROM") or user,
    }


def delivery_config() -> dict | None:
    """Amin keresztül ténylegesen ki tud menni a levél, vagy None.

    A Resend az elsőbbségi, mert HTTPS-en megy. Az SMTP csak akkor számít, ha a
    portja nem bizonyult elérhetetlennek.
    """
    cfg = resend_config()
    if cfg is not None:
        return cfg
    cfg = smtp_config()
    if cfg is not None and _smtp_reachable["value"] is not False:
        return cfg
    return None


class ContactRequest(BaseModel):
    name: str
    email: str
    message: str
    company: str = ""
    consent: bool = False
    # Csapdamező: a böngészőben rejtett, az ember üresen hagyja.
    website: str = ""
    # Az űrlap megnyitása óta eltelt idő, a kliens méri; csak jelzés, nem bizonyíték.
    elapsed_ms: int = 0

    @field_validator("name", "email", "message", "company", "website")
    @classmethod
    def _strip(cls, v: str) -> str:
        return (v or "").strip()


def _header_safe(value: str) -> str:
    """Fejlécbe kerülő érték soremelés nélkül.

    Egy „Kovács\\nBcc: mindenki@..." típusú név különben új fejlécet nyitna a
    levélben. Az EmailMessage ezt ma már maga is elutasítja, de a bemenetet
    ott kell megtisztítani, ahol belép.
    """
    return re.sub(r"[\r\n]+", " ", value)[:MAX_NAME]


def _check_rate(request: Request) -> None:
    today = date.today()
    if _day_state["day"] != today:
        _day_state["day"] = today
        _day_state["count"] = 0
    if _day_state["count"] >= MAX_PER_DAY:
        raise HTTPException(status_code=429, detail="Ma már sok üzenet érkezett. Kérlek, írj közvetlenül e-mailben.")
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    hits = [t for t in _ip_hits.get(ip, []) if now - t < 3600]
    if len(hits) >= MAX_PER_IP_HOUR:
        raise HTTPException(status_code=429, detail="Túl sok üzenet érkezett erről a hálózatról. Próbáld újra később.")
    hits.append(now)
    _ip_hits[ip] = hits


def _subject(body: ContactRequest) -> str:
    return f"AXIMBRA ajánlatkérés — {_header_safe(body.name)}"


def _text(body: ContactRequest) -> str:
    lines = [
        f"Név:    {body.name}",
        f"E-mail: {body.email}",
    ]
    if body.company:
        lines.append(f"Cég:    {body.company}")
    lines += ["", body.message, "", "—", "Az aximbra.hu ajánlatkérő űrlapjáról."]
    return "\n".join(lines)


def _build_message(cfg: dict, body: ContactRequest) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = _subject(body)
    msg["From"] = cfg["from"]
    msg["To"] = cfg["to"]
    # Így a levélre elég a „Válasz" gomb; a feladó a saját címünk marad, mert
    # idegen címről feladni levelet SPF/DKIM alatt úgysem lehet.
    msg["Reply-To"] = _header_safe(body.email)
    msg.set_content(_text(body))
    return msg


def _resend_payload(cfg: dict, body: ContactRequest) -> dict:
    return {
        "from": cfg["from"],
        "to": [cfg["to"]],
        "reply_to": _header_safe(body.email),
        "subject": _subject(body),
        "text": _text(body),
    }


class ResendError(Exception):
    """A Resend nem fogadta el a levelet. A szöveg a naplóba megy, a látogatóhoz nem."""


async def _send_resend(cfg: dict, payload: dict) -> None:
    async with httpx.AsyncClient(timeout=RESEND_TIMEOUT_SECONDS) as client:
        r = await client.post(RESEND_URL, json=payload, headers={"Authorization": f"Bearer {cfg['key']}"})
    if r.status_code >= 300:
        # A hibaüzenet a beállításról szól (pl. „csak a saját címedre küldhetsz"),
        # nem a látogatóról — a levél tartalma nincs benne.
        try:
            err = r.json()
            detail = f"{err.get('name', '')}: {str(err.get('message', ''))[:200]}"
        except ValueError:
            detail = ""
        raise ResendError(f"HTTP {r.status_code} {detail}".strip())


def probe_smtp(cfg: dict) -> bool:
    """Elérhető-e egyáltalán az SMTP-port. Nem jelentkezik be, nem küld."""
    try:
        with socket.create_connection((cfg["host"], cfg["port"]), timeout=SMTP_PROBE_SECONDS):
            return True
    except OSError:
        return False


def _probe_in_background() -> None:
    cfg = smtp_config()
    if cfg is None or resend_config() is not None:
        return

    def run():
        ok = probe_smtp(cfg)
        _smtp_reachable["value"] = ok
        if ok:
            logger.info("contact form: SMTP port %s:%d reachable", cfg["host"], cfg["port"])
        else:
            logger.warning(
                "contact form DISABLED - SMTP port %s:%d is unreachable (Railway blocks outbound SMTP "
                "below the Pro plan). Set RESEND_API_KEY and LEAD_TO to deliver over HTTPS.",
                cfg["host"], cfg["port"],
            )

    threading.Thread(target=run, name="smtp-probe", daemon=True).start()


def _send_sync(cfg: dict, msg: EmailMessage) -> None:
    ctx = ssl.create_default_context()
    if cfg["port"] == 465:
        with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=SMTP_TIMEOUT_SECONDS, context=ctx) as s:
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"], timeout=SMTP_TIMEOUT_SECONDS) as s:
            s.starttls(context=ctx)
            s.login(cfg["user"], cfg["password"])
            s.send_message(msg)


def log_contact_config() -> None:
    """Induláskor mondja meg, tud-e levelet küldeni, és ha nem, mi hiányzik.

    A lapon csak annyi látszik, hogy az űrlap nincs ott — ez így helyes, egy
    látogatónak nem kell tudnia a beállításainkról. A hiányzó darabot viszont
    valahol ki kell írni, különben a „nem működik" és a „nincs beállítva"
    ugyanúgy néz ki. A deploy-napló privát, ez a helye.

    Egy változó, ami létezik, de üres, ugyanúgy hiányzik — ezért a jelenlétet
    nézzük, nem a definiáltságot. Érték soha nem kerül a naplóba: egy SMTP-jelszó
    egy naplósorban is jelszó.
    """
    present = {
        name: bool(_env(name))
        for name in ("RESEND_API_KEY", "RESEND_FROM", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "LEAD_TO")
    }
    set_names = ", ".join(k for k, v in present.items() if v)
    if resend_config() is not None:
        logger.info("contact form ENABLED via Resend (set: %s)", set_names)
    elif smtp_config() is not None:
        # Még nem végleges: a port-próba a háttérben dönt, és ha a port zárva,
        # külön sorban kikapcsolja.
        logger.info("contact form ENABLED via SMTP, checking the port (set: %s)", set_names)
    else:
        missing = [k for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD") if not present[k]]
        logger.warning(
            "contact form DISABLED - the page will keep the mailto buttons. "
            "Set RESEND_API_KEY and LEAD_TO, or SMTP. Missing for SMTP: %s",
            ", ".join(missing) or "(a recipient: LEAD_TO or SMTP_USER)",
        )


log_contact_config()
_probe_in_background()


@router.get("/status")
async def status():
    """A lap ebből tudja, megjelenítheti-e az űrlapot."""
    return {"configured": delivery_config() is not None}


@router.post("")
async def submit(request: Request, body: ContactRequest):
    cfg = delivery_config()
    if cfg is None:
        # 503, nem 200: a kliens ebből tudja, hogy a levelezőprogramos utat
        # kell felkínálnia ahelyett, hogy sikert hazudna.
        raise HTTPException(status_code=503, detail="A közvetlen küldés most nem elérhető.")

    if body.website:                       # csapdamező kitöltve: robot
        logger.info("contact honeypot triggered")
        return {"ok": True}                # a robot ne tanuljon a hibából
    if body.elapsed_ms and body.elapsed_ms < MIN_FILL_SECONDS * 1000:
        logger.info("contact rejected: submitted in %d ms", body.elapsed_ms)
        raise HTTPException(status_code=400, detail="Az űrlap túl gyorsan érkezett. Próbáld újra.")

    if not body.consent:
        raise HTTPException(status_code=400, detail="A hozzájárulás nélkül nem tudjuk feldolgozni az üzenetet.")
    if not body.name or len(body.name) > MAX_NAME:
        raise HTTPException(status_code=400, detail="Kérlek, add meg a neved.")
    if not _EMAIL_RE.match(body.email) or len(body.email) > MAX_EMAIL:
        raise HTTPException(status_code=400, detail="Ez az e-mail-cím nem tűnik érvényesnek.")
    if len(body.message) < 10 or len(body.message) > MAX_MESSAGE:
        raise HTTPException(status_code=400, detail="Írj néhány mondatot arról, miben segíthetünk.")
    if len(body.company) > MAX_COMPANY:
        raise HTTPException(status_code=400, detail="A cégnév túl hosszú.")

    _check_rate(request)

    try:
        if cfg["via"] == "resend":
            await _send_resend(cfg, _resend_payload(cfg, body))
        else:
            await asyncio.to_thread(_send_sync, cfg, _build_message(cfg, body))
    except ResendError as e:
        logger.error("contact delivery failed via Resend: %s", e)
        raise HTTPException(status_code=502, detail="Az üzenetet most nem sikerült elküldeni.")
    except httpx.HTTPError as e:
        logger.error("contact delivery failed via Resend: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="Az üzenetet most nem sikerült elküldeni.")
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        # A tartalmat nem naplózzuk: az a látogató adata, és a hibához nem kell.
        logger.error("contact delivery failed via SMTP: %s", type(e).__name__)
        if isinstance(e, OSError) and not isinstance(e, (smtplib.SMTPException, ssl.SSLError)):
            # Hálózati hiba: a port nem érhető el. A következő látogatónak már
            # meg se jelenjen az űrlap, amit úgysem tud elküldeni.
            _smtp_reachable["value"] = False
        raise HTTPException(status_code=502, detail="Az üzenetet most nem sikerült elküldeni.")

    _day_state["count"] += 1
    logger.info("contact delivered via %s (message %d chars)", cfg["via"], len(body.message))
    return {"ok": True}
