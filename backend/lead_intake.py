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
"""
import asyncio
import logging
import os
import re
import smtplib
import ssl
import time
from datetime import date
from email.message import EmailMessage

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

# Nem teljes RFC 5322 — az úgysem mond semmit arról, hogy létezik-e a cím.
# Annyi a dolga, hogy a nyilvánvaló elgépelést még a küldés előtt megfogja.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")

_ip_hits: dict[str, list[float]] = {}
_day_state = {"day": date.today(), "count": 0}


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def smtp_config() -> dict | None:
    """A kézbesítés beállításai, vagy None, ha hiányos.

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
        "host": host, "port": port, "user": user, "password": password,
        "to": to, "from": _env("LEAD_FROM") or user,
    }


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


def _build_message(cfg: dict, body: ContactRequest) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = f"AXIMBRA ajánlatkérés — {_header_safe(body.name)}"
    msg["From"] = cfg["from"]
    msg["To"] = cfg["to"]
    # Így a levélre elég a „Válasz" gomb; a feladó a saját címünk marad, mert
    # idegen címről feladni levelet SPF/DKIM alatt úgysem lehet.
    msg["Reply-To"] = _header_safe(body.email)
    lines = [
        f"Név:    {body.name}",
        f"E-mail: {body.email}",
    ]
    if body.company:
        lines.append(f"Cég:    {body.company}")
    lines += ["", body.message, "", "—", "Az aximbra.hu ajánlatkérő űrlapjáról."]
    msg.set_content("\n".join(lines))
    return msg


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
    present = {name: bool(_env(name)) for name in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD", "LEAD_TO")}
    if smtp_config() is not None:
        logger.info("contact form ENABLED (set: %s)", ", ".join(k for k, v in present.items() if v))
    else:
        missing = [k for k in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD") if not present[k]]
        logger.warning(
            "contact form DISABLED - the page will keep the mailto buttons. Missing: %s",
            ", ".join(missing) or "(a recipient: LEAD_TO or SMTP_USER)",
        )


log_contact_config()


@router.get("/status")
async def status():
    """A lap ebből tudja, megjelenítheti-e az űrlapot."""
    return {"configured": smtp_config() is not None}


@router.post("")
async def submit(request: Request, body: ContactRequest):
    cfg = smtp_config()
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

    msg = _build_message(cfg, body)
    try:
        await asyncio.to_thread(_send_sync, cfg, msg)
    except (smtplib.SMTPException, OSError, ssl.SSLError) as e:
        # A tartalmat nem naplózzuk: az a látogató adata, és a hibához nem kell.
        logger.error("contact delivery failed: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="Az üzenetet most nem sikerült elküldeni.")

    _day_state["count"] += 1
    logger.info("contact delivered (message %d chars)", len(body.message))
    return {"ok": True}
