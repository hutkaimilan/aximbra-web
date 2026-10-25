"""Csevegés a szelvényekről és a meccsekről: Google Gemini, képekkel.

A felület a beszélgetést (szöveg + képek) és egy adatösszefoglalót küld: a felhasználó szelvényét a
TippmixPro-szorzókkal, a szelvény meccseinek modell-elemzését és a kiírt meccsek listáját. A modell
csak ezekből dolgozhat (böngészni nem tud), ezt a rendszerüzenet ki is köti.

Környezeti változók:
  GEMINI_API_KEY   a Google AI Studio kulcsa (Railway-en az aximbra-api szolgáltatásra hivatkozva)
  GEMINI_MODEL     a modell neve (alapból gemini-2.5-flash)
  CHAT_DAILY_LIMIT napi kérésplafon az egész oldalra (alapból 300), hogy a közös kulcs kerete ne fogyjon el
"""
import base64
import json
import logging
import os
import re
import threading
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-2.5-flash"
TIMEOUT = 90
MAX_MESSAGES = 24
MAX_TEXT = 4000
MAX_CONTEXT = 60000
MAX_IMAGES = 6            # az egész beszélgetésben
MAX_IMAGE_BYTES = 2 * 1024 * 1024
IMAGE_TYPES = ("image/jpeg", "image/png", "image/webp")
_DATA_URL = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$")
BUDAPEST = ZoneInfo("Europe/Budapest")

SYSTEM = """Te egy tapasztalt, őszinte sportfogadási elemző vagy egy magyar TippmixPro-szelvényépítő oldalon.
Magyarul válaszolsz, tömören, telefonon is jól olvashatóan (rövid bekezdések, felsorolás, félkövér kiemelés).

Szabályok:
- Csak az ADATOK részben kapott számokból és a felhasználó által küldött képekből dolgozz. Böngészni nem
  tudsz. Ha valamihez nincs adat (sérültek, kezdőcsapat, időjárás, friss hírek), mondd ki, hogy nincs, és ne
  találj ki semmit.
- A számokat (esély, szorzó, várható gól) idézd, hogy ellenőrizhető legyen, mire alapozol.
- Az esély a modell becslése, nem garancia. A TippmixPro árrése miatt hosszú távon a várható érték
  többnyire negatív; ezt egyszer, röviden mondd ki, ha releváns, ne minden válaszban.
- Szelvény véleményezésénél tippenként: rövid ítélet (erős / rendben / kockázatos / gyenge), indok a
  számokból, és ha van jobb alternatíva ugyanarra a meccsre a kínálatból, javasold. A végén az egész
  szelvényről egy-két mondat: becsült esély, a leggyengébb láb, és mit cserélnél.
- Ugyanarra a meccsre tett tippek Fogadásépítőt alkotnak: összefüggnek, nem szorozhatók egyszerűen össze.
- Képen (pl. TippmixPro-szelvény képernyőképe) olvasd ki a meccseket, tippeket, szorzókat, és vesd össze az
  ADATOK meccslistájával. Ha egy meccs nincs az adatokban, mondd meg.
- Ne biztass nagyobb tétre, és ne ígérj nyerést. Ha a felhasználó veszteség után akar visszanyerni, jelezd
  finoman a kockázatot."""


class ChatError(RuntimeError):
    """A felhasználónak mutatható hiba (magyarul)."""

    def __init__(self, msg: str, status: int = 502):
        super().__init__(msg)
        self.status = status


class DailyLimit:
    """Napi kérésszámláló budapesti nap szerint, szálbiztosan."""

    def __init__(self, limit: int):
        self.limit = limit
        self._day = None
        self._n = 0
        self._lock = threading.Lock()

    def take(self) -> bool:
        today = datetime.now(BUDAPEST).date()
        with self._lock:
            if today != self._day:
                self._day, self._n = today, 0
            if self._n >= self.limit:
                return False
            self._n += 1
            return True


DAILY = DailyLimit(int(os.environ.get("CHAT_DAILY_LIMIT", "300")))


def _image_part(url: str) -> dict:
    m = _DATA_URL.match(url or "")
    if not m:
        raise ChatError("Csak JPEG, PNG vagy WebP kép küldhető.", 400)
    data = m.group(2)
    if len(data) * 3 // 4 > MAX_IMAGE_BYTES:
        raise ChatError("Túl nagy kép (legfeljebb 2 MB).", 400)
    try:
        base64.b64decode(data, validate=True)
    except ValueError:
        raise ChatError("Hibás kép.", 400) from None
    return {"inline_data": {"mime_type": m.group(1), "data": data}}


def build_request(messages, context: str) -> dict:
    """A Gemini-kérés a kliens üzeneteiből; hibás bemenetnél ChatError(400)."""
    if not isinstance(messages, list) or not messages:
        raise ChatError("Üres beszélgetés.", 400)
    messages = messages[-MAX_MESSAGES:]
    if not isinstance(context, str):
        context = ""
    contents, images = [], 0
    for i, msg in enumerate(messages):
        if not isinstance(msg, dict) or msg.get("role") not in ("user", "assistant"):
            raise ChatError("Hibás üzenet.", 400)
        text = str(msg.get("text") or "")[:MAX_TEXT]
        parts = []
        if i == len(messages) - 1 and msg["role"] == "user":
            # az adatokat a legutolsó kérdés mellé tesszük: mindig a friss állapotot látja
            parts.append({"text": "ADATOK (az oldal mostani állapota):\n" + context[:MAX_CONTEXT]})
        for url in msg.get("images") or []:
            images += 1
            if images > MAX_IMAGES:
                raise ChatError(f"Egy beszélgetésben legfeljebb {MAX_IMAGES} kép lehet. Kezdj új beszélgetést.", 400)
            parts.append(_image_part(url))
        if text:
            parts.append({"text": text})
        if not parts:
            continue
        contents.append({"role": "user" if msg["role"] == "user" else "model", "parts": parts})
    if not contents or contents[-1]["role"] != "user":
        raise ChatError("Az utolsó üzenet a tiéd kell legyen.", 400)
    return {
        "system_instruction": {"parts": [{"text": SYSTEM}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 2048},
    }


def ask(messages, context: str) -> str:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise ChatError("A csevegés nincs beállítva (hiányzik a GEMINI_API_KEY).", 503)
    req_body = build_request(messages, context)
    if not DAILY.take():
        raise ChatError("Mára elfogyott a csevegés napi kerete. Holnap újra megy.", 429)
    model = os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODEL
    if not re.fullmatch(r"[A-Za-z0-9.\-]{1,60}", model):
        model = DEFAULT_MODEL
    req = urllib.request.Request(API.format(model=model), data=json.dumps(req_body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read(2000).decode("utf-8", "replace")
        logger.warning("Gemini HTTP %s: %s", e.code, detail[:300])
        if e.code == 429:
            raise ChatError("A Gemini most túlterhelt vagy elfogyott a kerete. Próbáld újra egy perc múlva.", 429) from None
        if e.code in (401, 403):
            raise ChatError("A Gemini-kulcs nem érvényes ehhez a szolgáltatáshoz.", 502) from None
        raise ChatError(f"A Gemini hibát adott ({e.code}).", 502) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        logger.warning("Gemini nem érhető el: %s", e)
        raise ChatError("A Gemini most nem érhető el. Próbáld újra.", 502) from None
    except ValueError:
        raise ChatError("A Gemini érthetetlen választ adott.", 502) from None
    cands = data.get("candidates") or []
    if not cands:
        reason = (data.get("promptFeedback") or {}).get("blockReason")
        raise ChatError("A Gemini nem válaszolt erre" + (f" ({reason})." if reason else "."), 502)
    parts = (cands[0].get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
    if not text:
        raise ChatError("A Gemini üres választ adott. Fogalmazd meg másképp.", 502)
    return text
