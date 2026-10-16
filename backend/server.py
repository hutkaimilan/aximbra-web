from fastapi import FastAPI, APIRouter, Request, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse
import asyncio
import contextvars
import os
import json
import time
import logging
import httpx
from pathlib import Path
from datetime import datetime, timezone, date
from pydantic import BaseModel, ValidationError, field_validator
from typing import Literal
from openai import AsyncOpenAI, BadRequestError, RateLimitError

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

app = FastAPI()
api_router = APIRouter(prefix="/api")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ---------- Rate limiting / cost ceiling (in-memory, no DB) ----------
def _env_float(name: str, default: float) -> float:
    """A bad value keeps the default rather than crashing the service on boot:
    a typo in a dashboard should not take the whole API down."""
    try:
        raw = os.environ.get(name, "").strip()
        return float(raw) if raw else default
    except ValueError:
        logger_env = logging.getLogger(__name__)
        logger_env.warning("ignoring non-numeric %s", name)
        return default


# Both are env-tunable because the mailbox agent now reads up to 50 emails per
# run: at the default estimate that is ~0.50 USD a run, so the 4 USD/day ceiling
# closes every demo — the lead qualifier included — after about eight runs.
# Raise DEMO_DAILY_CEILING_USD on the service rather than editing this file.
DAILY_COST_CEILING_USD = _env_float("DEMO_DAILY_CEILING_USD", 4.0)
# A deliberately conservative flat estimate; exact token cost is not read back,
# so the real spend per call is expected to be well under this. Lower it (and
# raise the ceiling) once you have measured what a run actually costs.
EST_COST_PER_CALL_USD = _env_float("DEMO_EST_COST_PER_CALL_USD", 0.01)
MAX_RUNS_PER_SESSION = 8
MAX_REQ_PER_IP_HOUR = 20
MAX_INPUT_CHARS = 4000

_state = {"day": date.today(), "cost": 0.0}
_session_runs = {}   # session_id -> count
_ip_hits = {}        # ip -> [timestamps]


def _reset_if_new_day():
    today = date.today()
    if _state["day"] != today:
        _state["day"] = today
        _state["cost"] = 0.0
        _session_runs.clear()


def _check_limits(request: Request, session_id: str):
    _reset_if_new_day()
    if _state["cost"] >= DAILY_COST_CEILING_USD:
        raise HTTPException(status_code=429, detail="Az élő demók mára elérték a napi keretüket. Nézz vissza holnap — vagy írj nekünk: aximbra@gmail.com")
    if _session_runs.get(session_id, 0) >= MAX_RUNS_PER_SESSION:
        raise HTTPException(status_code=429, detail="Ebben a munkamenetben elérted a próbálkozások számát (8). Frissítsd az oldalt, vagy írj nekünk.")
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    hits = [t for t in _ip_hits.get(ip, []) if now - t < 3600]
    if len(hits) >= MAX_REQ_PER_IP_HOUR:
        raise HTTPException(status_code=429, detail="Túl sok kérés érkezett erről a hálózatról. Kérlek, próbáld újra később.")
    hits.append(now)
    _ip_hits[ip] = hits


def _record_run(session_id: str):
    _state["cost"] += EST_COST_PER_CALL_USD
    _session_runs[session_id] = _session_runs.get(session_id, 0) + 1


# ---------- Schemas ----------
class DemoRequest(BaseModel):
    text: str

    @field_validator("text")
    @classmethod
    def _len(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("empty")
        return v[:MAX_INPUT_CHARS]


class LeadResult(BaseModel):
    minosites: Literal["A", "B", "C", "D"]
    igeny: Literal["Igazolt", "Valószínű", "Ismeretlen", "Nem illeszkedik"]
    koltsegvetes: Literal["Igazolt", "Valószínű", "Ismeretlen", "Nem illeszkedik"]
    donteshozo: Literal["Igazolt", "Valószínű", "Ismeretlen", "Nem illeszkedik"]
    hatarido: Literal["Igazolt", "Valószínű", "Ismeretlen", "Nem illeszkedik"]
    indoklas: str
    javasolt_lepes: str

    @field_validator("indoklas")
    @classmethod
    def _cap_i(cls, v):
        return v[:400]

    @field_validator("javasolt_lepes")
    @classmethod
    def _cap_j(cls, v):
        return v[:300]


LEAD_SYS = (
    "Te egy magyar értékesítési érdeklődő-minősítő asszisztens vagy. Minősítsd a leírt érdeklődőt (BANT logika). "
    "KIZÁRÓLAG érvényes JSON objektummal válaszolj, magyarázat nélkül, ezekkel a kulcsokkal: "
    "minosites (A|B|C|D, ahol A a legjobb), "
    "igeny, koltsegvetes, donteshozo, hatarido — mindegyik értéke pontosan: Igazolt|Valószínű|Ismeretlen|Nem illeszkedik, "
    "indoklas (max 400 karakter, magyarul), javasolt_lepes (max 300 karakter, magyarul)."
)


GEMINI_OPENAI_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
# LLM_PROVIDER=emergent: az Emergent „Universal Key” OpenAI-kompatibilis
# átjárója. OpenAI-modellt hív (alapból gpt-4o-mini), a díjat az Emergent-
# kreditből vonja le — így nem kell saját OpenAI-egyenleg, és nem az ingyenes
# Gemini-szint dolgozza fel a leveleket.
EMERGENT_OPENAI_BASE = "https://integrations.emergentagent.com/llm/v1"


def _llm_client() -> tuple[AsyncOpenAI, str]:
    """LLM_PROVIDER=gemini: a Gemini OpenAI-kompatibilis végpontja, ugyanazzal az SDK-val."""
    not_configured = HTTPException(
        status_code=503,
        detail="Az élő demó jelenleg nincs beállítva. Írj nekünk: aximbra@gmail.com",
    )
    if _llm_provider() == "gemini":
        key = os.environ.get("GEMINI_API_KEY")
        if not key:
            raise not_configured
        return (AsyncOpenAI(api_key=key, base_url=GEMINI_OPENAI_BASE, timeout=30.0, max_retries=0),
                os.environ.get("DEMO_GEMINI_MODEL", "gemini-3.5-flash-lite"))
    if _llm_provider() == "emergent":
        key = os.environ.get("EMERGENT_LLM_KEY")
        if not key:
            raise not_configured
        return (AsyncOpenAI(api_key=key, base_url=EMERGENT_OPENAI_BASE, timeout=30.0, max_retries=0),
                os.environ.get("DEMO_EMERGENT_MODEL", "gpt-4o-mini"))
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise not_configured
    return AsyncOpenAI(api_key=key, timeout=30.0, max_retries=0), os.environ.get("DEMO_MODEL", "gpt-4.1-mini")


# A Gemini a rendszerprompt formai kéréseit lazábban veszi, mint az OpenAI:
# hajlamos kódblokkba tenni a JSON-t, átfordítani a kulcsokat, vagy a megadott
# értékkészlet helyett saját szót írni. Ez a kiegészítés ezt zárja ki.
GEMINI_JSON_RULES = (
    "\n\nKIMENETI SZABÁLYOK (szigorúan):\n"
    "- Pontosan egy JSON objektumot adj vissza, semmi mást: se bevezető, se magyarázat, se ```json kódblokk.\n"
    "- A kulcsokat pontosan úgy írd, ahogy fent megadtam: ne fordítsd le, ne adj hozzá újat, ne hagyj ki egyet sem.\n"
    "- Ahol a feladat felsorolja a lehetséges értékeket, ott csak azok közül válassz, betű szerint ugyanúgy írva.\n"
    "- Számot számként írj, ne szövegként. A szöveges mezők hosszkorlátját tartsd be.\n"
    "- Csak abból dolgozz, ami a bemenetben áll. Amit nem tudsz belőle, ne találd ki: ha a feladat ad rá értéket (pl. Ismeretlen vagy other), azt használd."
)


RATE_LIMIT_WAITS = (5, 10, 20, 30)


def _daily_quota(e: Exception) -> bool:
    text = str(e)
    return "PerDay" in text or "insufficient_quota" in text or "credit_balance_exhausted" in text


def _llm_provider() -> str:
    return os.environ.get("LLM_PROVIDER", "openai").strip().lower()


async def _call_llm(system_msg: str, user_text: str, max_tokens: int = 600,
                    model: str | None = None, timeout: float | None = None) -> str:
    """
    Egyetlen OpenAI chat-completion hivas, JSON kimenetre kenyszeritve.

    Kozvetlen SDK-t hasznalunk wrapper helyett: a wrapper egy szolgaltatohoz
    kotne a backendet. Igy a kod barhol fut, ahol van OPENAI_API_KEY.

    Nehany ujabb modell nem engedi a temperature-t vagy a max_tokens-t.
    Ilyenkor a hivast egyszer megismeteljuk igazitott parameterekkel, hogy egy
    modellvaltas ne torje el a demot.
    """
    client, default_model = _llm_client()
    if _llm_provider() == "gemini":
        system_msg = system_msg + GEMINI_JSON_RULES
        model = None  # az OpenAI-modellnevek ott nem léteznek
    if timeout:
        client = client.with_options(timeout=timeout)
    kwargs = {
        "model": model or default_model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_text},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
        "temperature": 0,
    }

    resp = None
    waits = list(RATE_LIMIT_WAITS)
    for _ in range(3 + len(waits)):
        try:
            resp = await client.chat.completions.create(**kwargs)
            break
        except RateLimitError as exc:
            # Percenkénti korlát (a példa-postafiók tíz hívást indít egyszerre):
            # kivárjuk. A napi keret kimerülésénél a várakozás nem segít.
            if not waits or _daily_quota(exc):
                raise
            await asyncio.sleep(waits.pop(0))
        except BadRequestError as exc:
            msg = str(exc)
            if "temperature" in msg and "temperature" in kwargs:
                kwargs.pop("temperature")
                continue
            if "max_tokens" in msg and "max_tokens" in kwargs:
                kwargs["max_completion_tokens"] = kwargs.pop("max_tokens")
                continue
            raise
    if resp is None:
        raise ValueError("model rejected request parameters")

    choice = resp.choices[0]
    if getattr(choice, "finish_reason", None) == "length":
        # Félbevágott JSON lesz belőle: a naplóban látszódjon, hogy a keret kevés.
        logger.warning("llm output cut at the token limit (max %s)", max_tokens)
    content = choice.message.content
    if not content:
        raise ValueError("empty completion")
    return content


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end != -1:
        raw = raw[start:end + 1]
    return json.loads(raw)


def _quota_exhausted(e: Exception) -> bool:
    text = str(e)
    return getattr(e, "code", None) == "insufficient_quota" or "insufficient_quota" in text \
        or "credit_balance_exhausted" in text or "RESOURCE_EXHAUSTED" in text


async def _run_demo(request: Request, body: DemoRequest, system_msg: str, model_cls, max_tokens: int = 600):
    session_id = request.headers.get("X-Session-Id", "anon")
    _check_limits(request, session_id)
    last_err = None
    for _ in range(3):  # 1 try + 2 retries
        try:
            raw = await _call_llm(system_msg, body.text, max_tokens)
            data = _parse_json(raw)
            result = model_cls(**data)
            _record_run(session_id)
            return result.model_dump()
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_err = e
            continue
        except HTTPException:
            raise
        except Exception as e:
            if _quota_exhausted(e):
                # Elfogyott a modellkeret: az újrapróbálás és az "fogalmazd át"
                # tanács is félrevezető lenne. A felület a látogató nyelvén írja ki.
                logger.error("demo paused: model quota exhausted")
                raise HTTPException(status_code=503, detail="demo_paused")
            last_err = e
            logger.error(f"demo llm error: {e}")
            continue
    raise HTTPException(status_code=502, detail="Az agent most nem tudott érvényes választ adni. Kérlek, próbáld újra kicsit másképp megfogalmazva.")


@api_router.get("/")
async def root():
    return {"message": "AXIMBRA API"}


VOICE_BASE_URL = os.environ.get(
    "VOICE_BASE_URL", "https://aximbra-voice-production.up.railway.app"
).rstrip("/")
VOICE_HEALTH_URL = f"{VOICE_BASE_URL}/health"
VOICE_CALLBACK_URL = f"{VOICE_BASE_URL}/callback"


@api_router.get("/voice/health")
async def voice_health():
    """Server-side proxy for the live voice-agent health endpoint (avoids CORS)."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(VOICE_HEALTH_URL)
            r.raise_for_status()
            data = r.json()
        return {
            "reachable": True,
            "ok": bool(data.get("ok", False)),
            "day": data.get("day"),
            "count": data.get("count"),
            "live": data.get("live"),
            # Ebbol tudja a lap, megjelenitse-e a "hivjon vissza" urlapot.
            # Egy urlap, ami sose csorget vissza, tobbet art, mint hasznal.
            "callback": bool(data.get("callback", False)),
        }
    except Exception as e:
        logger.warning(f"voice health unreachable: {e}")
        return {
            "reachable": False,
            "ok": False,
            "day": None,
            "count": None,
            "live": None,
            "callback": False,
        }


class CallbackRequest(BaseModel):
    """A látogató saját telefonszáma, ahogy beírta.

    A szám alakját szándékosan NEM itt ellenőrizzük. Egyetlen helyen dőljön
    el, mi számít érvényesnek: a voice-agent `callback.ts` modulja végzi a
    normalizálást és az ország-szűrést is, és az hívja a telefont. Két
    validáló két helyen előbb-utóbb elcsúszik, és akkor a hibaüzenet mást
    mond, mint ami történik.
    """

    phone: str
    lang: str = "hu"

    @field_validator("phone")
    @classmethod
    def _phone_len(cls, v):
        v = (v or "").strip()
        # Csak a nyilvánvaló szemét ellen: egy telefonszám nem 32 karakter.
        if not v or len(v) > 32:
            raise ValueError("phone")
        return v

    @field_validator("lang")
    @classmethod
    def _lang(cls, v):
        return "en" if (v or "").strip().lower() == "en" else "hu"


@api_router.post("/voice/callback")
async def voice_callback(body: CallbackRequest):
    """A "hívjon vissza" kérés továbbítása a voice-agentnek.

    Miért proxy: ugyanabból az okból, amiért a /voice/health is az. A lap az
    api.aximbra.hu-val beszél; ha innen közvetlenül a voice szolgáltatást
    hívná, minden látogatónak CORS-kört kellene futnia egy harmadik
    tartománnyal. A hívásindítás, a keretek és a szám ellenőrzése ott marad,
    ahol a telefon van.

    A válasz státuszkódja átmegy, mert a felületen az számít, MIÉRT nem megy
    a hívás: hibás szám, mai kerete elfogyott, vagy a szolgáltatás áll.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                VOICE_CALLBACK_URL,
                json={"phone": body.phone, "lang": body.lang},
            )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        return JSONResponse(status_code=r.status_code, content=data or {"ok": False, "reason": "failed"})
    except Exception as e:
        # A számot nem naplózzuk: személyes adat, és a hibakereséshez nem kell.
        logger.warning(f"voice callback proxy failed: {e}")
        return JSONResponse(status_code=502, content={"ok": False, "reason": "failed"})


@api_router.post("/demo/lead")
async def demo_lead(request: Request, body: DemoRequest):
    return await _run_demo(request, body, LEAD_SYS, LeadResult)


# ---------- Dokumentum-elemző demó ----------
# A látogató egy mintadokumentumot választ, vagy feltölt egyet (PDF, DOCX, TXT,
# max 5 MB, base64-ben a JSON-ban — így nem kell multipart-függőség). A fájl csak
# a memóriában él, a válasz után eldobjuk. A modell minden mezőhöz megadja a
# forrásmondatot is; ha az a dokumentumban nincs meg, a mezőt "nem található"-ra
# állítjuk: a demó semmit nem állíthat, ami nincs a papíron.
import base64
import re as _re
import unicodedata as _ud
from doc_samples import SAMPLES as DOC_SAMPLES
import attachments as _att

DOC_MAX_BYTES = 5 * 1024 * 1024
DOC_MAX_CHARS = 30000
DOC_TYPES = {"contract", "invoice", "quote", "other"}
DOC_FIELDS = ("parties", "subject", "date", "duration", "amount", "payment_terms",
              "due_date_or_deadline", "termination")
DOC_LISTS = ("key_obligations", "risks_or_unusual_terms")
DOC_LIST_MAX = 6
DOC_RISK_MAX = 10
# A kockázati kör erősebb modellen fut: a mini a csapdák egy részét kihagyta
# (kötbér, elvesző beruházás) és összekevert pontokat. Üres = az alapmodell.
DOC_RISK_MODEL = os.environ.get("DOC_RISK_MODEL", "gpt-4o").strip()
DOC_MAIN_TOKENS = 8000
DOC_RISK_TOKENS = 6000
DOC_SEVERITY = {"high", "medium", "low"}


class DocRequest(BaseModel):
    sample: str = ""
    filename: str = ""
    mime: str = ""
    data_b64: str = ""
    lang: str = "hu"


def doc_sys(lang: str) -> str:
    in_lang = AGENT_LANG_NAMES.get(lang, AGENT_LANG_NAMES["hu"])
    return (
        "You analyse ONE business document (usually a contract) for a small-business owner who will sign or pay it. "
        "Reply with a VALID JSON object ONLY, with keys:\n"
        "document_type: EXACTLY one of contract|invoice|quote|other.\n"
        "summary: 2-4 plain sentences: what this document is, who owes what to whom, and then the 2-3 clauses "
        "that are most dangerous or costly for the reader (e.g. one-sided termination, penalties, lock-in, "
        "extreme interest), named concretely. Only facts stated in the document.\n"
        "parties, subject, date, duration, amount, payment_terms, due_date_or_deadline, termination: each an object "
        "{\"value\": string, \"source\": string}. parties = the parties with their role; subject = what is being "
        "delivered or done; date = date of signing/issue; duration = term, start and end, renewal; amount = the main "
        "fee or total with currency, and whether it is net/gross, monthly/one-off; payment_terms = how and when to pay, "
        "advance, late-payment interest; due_date_or_deadline = the most important deadline; termination = how and "
        "when EACH party can end it (state both sides separately), notice periods, exit costs.\n"
        f"key_obligations: list of at most {DOC_LIST_MAX} objects {{\"party\": string, \"value\": string, \"source\": string}} "
        "— the concrete duties, party = who has to do it.\n"
        f"risks_or_unusual_terms: list of at most {DOC_LIST_MAX} objects {{\"value\": string, \"why\": string, "
        "\"severity\": \"high\"|\"medium\"|\"low\", \"source\": string}} — clauses that are unfavourable, one-sided or "
        "unusual for the reader (automatic price rises, lock-in, penalties, exit fees, retention of title, warranty "
        "conditions, unlimited liability, short complaint windows); why = in one sentence, what it can cost the reader. "
        "Most severe first.\n"
        "recommendations: list of at most 4 short strings: what the reader should ask, negotiate or check before "
        "signing, each tied to a clause above.\n"
        f"Write every value, why, summary and recommendation {in_lang}; values max 300 characters. "
        "\"source\" MUST be copied word for word from the document — the exact sentence or line the value comes from; "
        "when the value comes from two places (e.g. the two parties), join the two exact quotes with \" … \". "
        "If the document does not contain the information, use value \"\" and source \"\". NEVER guess or infer facts."
        + (" Address the reader informally (tegezés: \"kérdezd meg\", \"tárgyald újra\"), never with \"Ön\"."
           if lang == "hu" else "")
    )


def doc_risk_sys(lang: str) -> str:
    """Külön kör csak a kockázatokra: egy hívásban a modell a mezők mellett a
    csapdák harmadát találta meg; pontról pontra, ellenőrzőlistával mindet."""
    in_lang = AGENT_LANG_NAMES.get(lang, AGENT_LANG_NAMES["hu"])
    return (
        "You review ONE business document to protect the party who receives it and pays or signs (tenant, customer, "
        "buyer, client, subscriber). Go through the document CLAUSE BY CLAUSE and flag EVERY clause that is "
        "unfavourable, one-sided, unusual or costly for that party. Check in particular: the other party's right to "
        "terminate unilaterally or at short notice, and any asymmetry between the two parties' rights; immediate "
        "termination for small or short delays; lock-in periods and automatic renewal with long notice; price "
        "increases or indexation, especially with a minimum; penalties, liquidated damages, exit fees; late-payment "
        "interest (convert daily or monthly rates to a yearly figure in 'why'); deposits, their size and slow or "
        "conditional refund; costs normally borne by the other party (structural repairs, roof, walls, utilities "
        "lines, insurance); losing investments or improvements without compensation; accepting the subject 'as is' "
        "or waiving later complaints; waiving court proceedings or an arbitrator chosen by one side; restrictions on "
        "assignment, subletting or change of ownership; unlimited liability; short warranty or complaint windows; "
        "obligations to operate or stay open.\n"
        "Reply with a VALID JSON object ONLY: {\"risks\": [{\"value\": string, \"why\": string, "
        "\"severity\": \"high\"|\"medium\"|\"low\", \"source\": string}], \"recommendations\": [string]}. "
        f"At most {DOC_RISK_MAX} risks, most severe first; at most 5 recommendations: what to ask, delete or "
        "renegotiate before signing, each naming the clause by the number printed in the document. value = the clause "
        "in a few words; why = one concrete sentence on what THAT clause can cost or how it can hurt — never mix two "
        "clauses in one risk: each risk is exactly one clause, and its source is that clause. "
        f"Write value, why and recommendations {in_lang}. "
        "\"source\" MUST be copied word for word from the document. Only clauses that are really in the document."
        + (" Address the reader informally (tegezés), never with \"Ön\"." if lang == "hu" else "")
    )


# A PDF-ek gyakran ligatúrával írják a „fi”-t („ﬁzet”), a modell viszont sima
# betűkkel idéz, és a tipográfiai jeleket (–, „ ”) is egyszerűsítheti. Ezeket
# mindkét oldalon egy alakra hozzuk, különben a jó idézet is „nincs a papíron”.
_PUNCT = str.maketrans({"–": "-", "—": "-", "‑": "-", "„": '"', "”": '"', "“": '"',
                        "‚": "'", "‘": "'", "’": "'", "«": '"', "»": '"'})


def _norm(s: str) -> str:
    s = _ud.normalize("NFKC", s or "").translate(_PUNCT)
    return _re.sub(r"\s+", " ", s).strip().lower()


def _flat(s: str) -> str:
    """Kötőjel nélkül: a sor végén elválasztott „webshop-⏎funkcióval” és a
    modell „webshop-funkcióval” idézete így ugyanaz."""
    return _re.sub(r"\s*-\s*", "", s)


def _source_pieces(source: str) -> list[str]:
    """A forrás darabjai: a „ … ” jellel elválasztott idézetek, és azokon belül
    a mondatok. A modell gyakran két nem szomszédos mondatot idéz egyben; ha
    mindkettő szó szerint megvan, az idézet valódi."""
    out = []
    for chunk in _re.split(r"\s*(?:…|\.\.\.)\s*", source):
        for piece in _re.split(r"(?<=[.;!?])\s+", _norm(chunk)):
            piece = piece.strip(" .;:,…\"'")
            if len(piece) >= 4:
                out.append(piece)
    return out


def _grounded(item, text_n: str) -> dict:
    """Egy mező, csak ha a forrása tényleg a dokumentumból származik."""
    if not isinstance(item, dict):
        return {"value": "", "source": ""}
    value = _re.sub(r"\s*…\s*", ", ", str(item.get("value") or "")).strip()[:320]
    source = str(item.get("source") or "").strip()[:400]
    # A forrás állhat több rövid idézetből is („ … ” jellel elválasztva), pl. a
    # felek két külön sorból: mindegyik darabnak szó szerint benne kell lennie.
    pieces = _source_pieces(source)
    text_flat = None

    def found(piece: str) -> bool:
        nonlocal text_flat
        if piece in text_n:
            return True
        if text_flat is None:
            text_flat = _flat(text_n)
        return _flat(piece) in text_flat

    # Apró, általános darabokból („a megrendelő”, „fizet”) bármi összerakható:
    # hosszabb forrásnál a szöveg nagyobbik része érdemi, 16+ karakteres mondat legyen.
    substantial = sum(len(p) for p in pieces if len(p) >= 16)
    if not value or not pieces or not all(found(p) for p in pieces) \
            or (len(_norm(source)) > 30 and substantial * 2 < sum(map(len, pieces))):
        return {"value": "", "source": ""}
    return {"value": value, "source": source}


def _clean_list(items, text_n: str, limit: int = DOC_LIST_MAX) -> list:
    """Kötelezettség- vagy kockázatlista: csak a forrással igazolt elemek, a
    kiegészítő mezőkkel (ki a kötelezett, miért kockázat, mennyire súlyos)."""
    out = []
    for x in (items if isinstance(items, list) else [])[:limit]:
        g = _grounded(x, text_n)
        if not g["value"]:
            continue
        if x.get("party"):
            g["party"] = str(x["party"]).strip()[:80]
        if x.get("why"):
            g["why"] = str(x["why"]).strip()[:300]
        sev = str(x.get("severity") or "").strip().lower()
        if sev in DOC_SEVERITY:
            g["severity"] = sev
        out.append(g)
    return out


def _doc_text(body: DocRequest) -> str:
    if body.sample:
        doc = DOC_SAMPLES.get(body.sample)
        if not doc:
            raise HTTPException(status_code=400, detail="unknown_sample")
        return doc["text"]
    if not body.data_b64:
        raise HTTPException(status_code=400, detail="no_document")
    try:
        data = base64.b64decode(body.data_b64, validate=False)
    except Exception:
        raise HTTPException(status_code=400, detail="bad_file")
    if len(data) > DOC_MAX_BYTES:
        raise HTTPException(status_code=413, detail="too_large")
    kind = _att.kind_of(body.filename[:200], body.mime[:100])
    if kind not in {_att._WORD, _att._PDF, "text/plain"}:
        raise HTTPException(status_code=415, detail="unsupported")
    try:
        text = _att._READERS[kind](data)
    except Exception as e:  # noqa - sérült vagy jelszavas fájl
        logger.info("doc demo unreadable: %s", type(e).__name__)
        text = ""
    text = _re.sub(r"[ \t]+", " ", text or "").strip()
    if len(text) < 20:
        raise HTTPException(status_code=422, detail="no_text")
    return text[:DOC_MAX_CHARS]


@api_router.post("/demo/document")
async def demo_document(request: Request, body: DocRequest):
    lang = body.lang if body.lang in AGENT_LANG_NAMES else "hu"
    text = _doc_text(body)
    session_id = request.headers.get("X-Session-Id", "anon")
    _check_limits(request, session_id)
    text_n = _norm(text)

    async def ask(system: str, tokens: int, model: str | None = None, timeout: float | None = None):
        last = None
        for _ in range(2):
            try:
                data = _parse_json(await _call_llm(system, text, tokens, model=model, timeout=timeout))
                if isinstance(data, dict):
                    return data
                last = ValueError("not an object")
            except (json.JSONDecodeError, ValueError, AttributeError) as e:
                last = e
            except HTTPException:
                raise
            except Exception as e:
                if _quota_exhausted(e):
                    logger.error("doc demo paused: model quota exhausted")
                    raise HTTPException(status_code=503, detail="demo_paused")
                last = e
                logger.error(f"doc demo llm error: {type(e).__name__}")
        raise last or ValueError("no answer")

    # A mezők és a kockázatok két párhuzamos hívás: így nem lassabb, és a
    # kockázati kör a teljes figyelmét a feltételekre fordíthatja. A keret
    # bőséges: magyarul a teljes válasz 3000 token fölé is mehet, és a Gemini a
    # gondolkodását is ebből vonja le; levágott JSON-ból nincs eredmény.
    main, risk = await asyncio.gather(ask(doc_sys(lang), DOC_MAIN_TOKENS, None, 75.0),
                                      ask(doc_risk_sys(lang), DOC_RISK_TOKENS, DOC_RISK_MODEL or None, 75.0),
                                      return_exceptions=True)
    if isinstance(main, HTTPException):
        raise main
    if isinstance(main, Exception):
        last_err = main
    else:
        data = main
        dtype = str(data.get("document_type") or "other").strip().lower()
        out = {"document_type": dtype if dtype in DOC_TYPES else "other",
               "summary": str(data.get("summary") or "").strip()[:900]}
        for k in DOC_FIELDS:
            out[k] = _grounded(data.get(k), text_n)
        out["key_obligations"] = _clean_list(data.get("key_obligations"), text_n)
        risks = _clean_list(risk.get("risks"), text_n, DOC_RISK_MAX) if isinstance(risk, dict) else []
        out["risks_or_unusual_terms"] = risks or _clean_list(data.get("risks_or_unusual_terms"), text_n)
        rank = {"high": 0, "medium": 1, "low": 2}
        out["risks_or_unusual_terms"].sort(key=lambda r: rank.get(r.get("severity"), 3))
        recs = risk.get("recommendations") if isinstance(risk, dict) and isinstance(risk.get("recommendations"), list) else []
        if not recs:
            recs = data.get("recommendations") if isinstance(data.get("recommendations"), list) else []
        out["recommendations"] = [str(r).strip()[:300] for r in recs[:5] if isinstance(r, str) and r.strip()]
        out["truncated"] = len(text) >= DOC_MAX_CHARS
        _record_run(session_id)
        return out
    logger.warning("doc demo failed: %s", type(last_err).__name__ if last_err else "?")
    raise HTTPException(status_code=502, detail="model_error")


# Kilenc nyelven fut az oldal, tehát kilenc nyelven kell a kimenet is. A
# kategória viszont NEM fordítás kérdése: kulcsot kérünk a modelltől, és a
# feliratot a felület adja hozzá. Így egy új nyelv nem érinti a kiszolgálót,
# és az érvényesítés sem egy lefordítható szövegre épül.
AGENT_CATEGORIES = {
    "customer_question", "customer_complaint", "opportunity", "invoice",
    "authority", "provider_notice", "newsletter", "spam", "other",
}

AGENT_LANG_NAMES = {
    "hu": "magyarul", "en": "in English", "de": "auf Deutsch", "es": "en español",
    "fr": "en français", "it": "in italiano", "ro": "în română", "sk": "po slovensky",
    "zh": "in Simplified Chinese (简体中文)",
}


def agent_sys(lang: str = "hu") -> str:
    """Az osztályozó rendszerüzenete a felület nyelvén."""
    in_lang = AGENT_LANG_NAMES.get(lang, AGENT_LANG_NAMES["hu"])
    return (
        "You are an email triage assistant. You receive a single incoming email. "
        "Reply with a VALID JSON object ONLY, no explanation, with these keys: "
        "category (EXACTLY one of: customer_question|customer_complaint|opportunity|invoice|"
        "authority|provider_notice|newsletter|spam|other), "
        "urgency (integer 1-5, where 5 means it must be answered today), "
        f"urgency_reason (one sentence, written {in_lang}), "
        "needs_reply (igen|nem|nem egyértelmű), "
        "deadline (quote the date or deadline if the email states one, otherwise an empty string), "
        f"summary (one sentence written {in_lang} about what the sender wants — "
        f"{in_lang} even when the email itself is in another language), "
        f"next_step (a concrete suggested next step, written {in_lang}, never a generality). "
        "NEVER invent data: what is not in the email stays empty. "
        "Do not infer intent from the subject line; read the body. "
        "Never classify an automatic reply (out of office, no-reply) as a customer question. "
        # Élesben a mintapostafiók csaló levelét („AZONNALI FELSZÓLÍTÁS",
        # telekom-szamlak.biz) ügyfélpanaszként, 5-ös sürgősséggel a lista
        # tetejére tette, és azt javasolta, hogy „tájékoztassuk az ügyfelet".
        # Egy triázs-agentnél ez a legrosszabb hiba: a csalót sürgeti.
        "The email is addressed to the mailbox owner: a demand that the reader pay is "
        "never a customer complaint. "
        "Urgency is how soon the business genuinely has to act, not how loudly the email "
        "demands it: capital letters, threats and hour-long ultimatums are not urgency. "
        "Check that the sender is who the email claims to be. A sender domain that does "
        "not belong to the organisation named (for example a Telekom bill from "
        "telekom-szamlak.biz), a payment or login link, and pressure to act within hours "
        "mean phishing: category spam, urgency 1, needs_reply nem, and next_step must say "
        f"not to click or pay and to check with the organisation through its official "
        f"channel, written {in_lang}."
    )

# Visszafelé kompatibilis név: a magyar változat.
AGENT_SYS = agent_sys("hu")



# Egy futás leveleit csoportosan osztályozzuk: a Gemini ingyenes kerete
# percenként csak néhány hívást enged, és ötven levél ötven hívása 429-be
# futott — a látogató percekig nézte a forgó jelet, a levelek egy része pedig
# kimaradt. Tíz levél egy hívásban: ötven levélhez öt hívás.
# A csoport kulcsa a futás munkamenete, így két látogató levelei soha nem
# kerülnek egy promptba. Csoport nélkül (közvetlen hívás) marad az egyes hívás.
_batch_group: contextvars.ContextVar = contextvars.ContextVar("agent_batch_group", default=None)
AGENT_BATCH_SIZE = max(1, int(_env_float("AGENT_BATCH_SIZE", 10)))
AGENT_BATCH_WINDOW = 1.5  # mp: ennyit vár a csomag a többi levélre, mielőtt elindul
AGENT_BATCH_BODY_CHARS = 3000
_batches: dict = {}
_batch_tasks: set = set()

AGENT_BATCH_RULES = (
    "\n\nBATCH MODE: instead of a single email you receive several, each introduced by a "
    "line '### EMAIL id=N'. Classify every email independently, as if it were the only one: "
    "never let one email's content influence another's result. Return ONE JSON object of the "
    'form {"results": [{"id": N, ...the keys above...}, ...]} with exactly one entry per id.'
)


def _agent_text(email: dict, body_chars: int) -> str:
    return (
        f"Feladó: {email.get('sender', '')}\n"
        f"Tárgy: {email.get('subject', '')}\n"
        f"Dátum: {email.get('date', '')}\n\n"
        f"Levél törzse:\n{(email.get('body') or email.get('snippet') or '')[:body_chars]}"
    )


def _normalise_agent(data: dict) -> dict:
    category = data.get("category")
    if category not in AGENT_CATEGORIES:
        category = "other"
    try:
        urgency = max(1, min(5, int(data.get("urgency", 1))))
    except Exception:  # noqa
        urgency = 1
    needs_reply = data.get("needs_reply")
    if needs_reply not in ("igen", "nem", "nem egyértelmű"):
        needs_reply = "nem egyértelmű"
    # A spam soha nem kerülhet a lista tetejére, és válasz sem kell rá — akkor
    # sem, ha a modell a kategóriát eltalálja, de a sürgősséget a levél
    # hangereje alapján adja meg.
    if category == "spam":
        urgency = 1
        needs_reply = "nem"
    return {
        "category": category,
        "urgency": urgency,
        "urgency_reason": str(data.get("urgency_reason") or "")[:300],
        "needs_reply": needs_reply,
        "deadline": str(data.get("deadline") or "")[:120],
        "summary": str(data.get("summary") or "")[:400],
        "next_step": str(data.get("next_step") or "")[:400],
    }


async def _classify_single(email: dict, lang: str) -> dict:
    raw = await _call_llm(agent_sys(lang), _agent_text(email, 6000), max_tokens=700)
    return _parse_json(raw)


def _batch_results(raw: str) -> dict:
    """{id: eredmény} a csomag válaszából. Elfogadja a csupasz listát is."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    try:
        data = json.loads(text)
    except ValueError:
        data = _parse_json(raw)
    rows = data.get("results") if isinstance(data, dict) else data
    out = {}
    for r in rows if isinstance(rows, list) else []:
        if isinstance(r, dict) and r.get("id") is not None:
            out[str(r["id"]).strip()] = r
    return out


async def _run_batch(lang: str, items: list):
    try:
        if len(items) == 1:
            by_id = {"1": await _classify_single(items[0][0], lang)}
        else:
            text = "\n\n".join(
                f"### EMAIL id={i}\n{_agent_text(email, AGENT_BATCH_BODY_CHARS)}"
                for i, (email, _) in enumerate(items, 1)
            )
            raw = await _call_llm(agent_sys(lang) + AGENT_BATCH_RULES, text,
                                  max_tokens=min(8000, 450 * len(items) + 200))
            by_id = _batch_results(raw)
    except Exception as e:  # noqa - minden várakozó ugyanazt a hibát kapja
        for _, fut in items:
            if not fut.done():
                fut.set_exception(e)
        return
    for i, (email, fut) in enumerate(items, 1):
        if fut.done():  # a hívó közben feladta
            continue
        row = by_id.get(str(i))
        if row is None:
            # A modell kihagyott egyet: azt az egyet külön kérdezzük meg.
            try:
                row = await _classify_single(email, lang)
            except Exception as e:  # noqa
                if not fut.done():
                    fut.set_exception(e)
                continue
        if not fut.done():
            fut.set_result(row)


def _flush_batch(key):
    b = _batches.pop(key, None)
    if not b:
        return
    b["timer"].cancel()
    task = b["loop"].create_task(_run_batch(key[2], b["items"]))
    _batch_tasks.add(task)
    task.add_done_callback(_batch_tasks.discard)


def _enqueue_batch(group, lang: str, email: dict) -> asyncio.Future:
    loop = asyncio.get_running_loop()
    key = (id(loop), group, lang)
    b = _batches.get(key)
    if b is None:
        b = _batches[key] = {
            "loop": loop, "items": [],
            "timer": loop.call_later(AGENT_BATCH_WINDOW, _flush_batch, key),
        }
    fut = loop.create_future()
    b["items"].append((email, fut))
    if len(b["items"]) >= AGENT_BATCH_SIZE:
        _flush_batch(key)
    return fut


async def classify_one(email: dict, lang: str = "hu") -> dict:
    """One classification for the in-page email agent. Shares the demos' daily
    cost ceiling so a long mailbox cannot run up an unbounded bill."""
    _reset_if_new_day()
    if _state["cost"] >= DAILY_COST_CEILING_USD:
        raise HTTPException(status_code=429, detail="Az agent mára elérte a napi keretét.")
    group = _batch_group.get()
    if group is None or AGENT_BATCH_SIZE <= 1:
        data = await _classify_single(email, lang)
    else:
        data = await _enqueue_batch(group, lang, email)
    _state["cost"] += EST_COST_PER_CALL_USD
    return _normalise_agent(data)


# ---------- Reply drafting (in-page only, never sent) ----------
# A jelzés a lapon olvasandó, a felület nyelvén. Küldés és mentés előtt a
# mail_agent kiszedi, tehát az ügyfélhez soha nem jut ki — ezért kell az ÖSSZES
# nyelvi változatot ismerni ott is, nem csak az aktuálisat.
AI_NOTICES = {
    "hu": "— AI-fogalmazvány, küldés előtt olvasd át. —",
    "en": "— AI draft, read it through before sending. —",
    "de": "— KI-Entwurf, vor dem Senden bitte durchlesen. —",
    "es": "— Borrador de IA, léelo antes de enviarlo. —",
    "fr": "— Brouillon généré par IA, à relire avant envoi. —",
    "it": "— Bozza generata dall'IA, rileggila prima di inviarla. —",
    "ro": "— Ciornă generată de AI, citește-o înainte de trimitere. —",
    "sk": "— Návrh od AI, pred odoslaním si ho prečítaj. —",
    "zh": "— AI 草稿，发送前请通读一遍。—",
}
AI_NOTICE = AI_NOTICES["hu"]


def ai_notice(lang: str = "hu") -> str:
    return AI_NOTICES.get(lang, AI_NOTICES["hu"])

DRAFT_TONES = {
    "hivatalos": "hivatalos, tisztelettudó, magázódó üzleti hangnem",
    "kozvetlen": "közvetlen, barátságos, tegező hangnem, de nem bizalmaskodó",
}


class DraftResult(BaseModel):
    targy: str
    valasz: str

    @field_validator("targy")
    @classmethod
    def _cap_t(cls, v):
        return v.strip()[:120]

    @field_validator("valasz")
    @classmethod
    def _cap_v(cls, v):
        return v.strip()[:4000]


def draft_sys(tone: str, lang: str = "hu") -> str:
    """A fogalmazó rendszerüzenete.

    A válasz nyelve szándékosan NEM a felület nyelve, hanem a bejövő levélé:
    egy német ügyfélnek németül kell válaszolni akkor is, ha a tulajdonos
    magyarul nézi a lapot. A lap alján megjelenő jelzés viszont a felület
    nyelvén szól, mert azt a tulajdonos olvassa.
    """
    return (
        "You are the email assistant of a small business. You receive one incoming email and write "
        "the DRAFT OF THE REPLY on behalf of the recipient. "
        "Reply with a VALID JSON object ONLY, no explanation, with these keys: "
        "targy (the reply's subject line, max 120 characters), "
        "valasz (the full reply text, with a salutation and a sign-off). "
        "Rules: the reply MUST be in the same language as the incoming email. "
        f"Tone: {DRAFT_TONES[tone]}. "
        "NEVER invent a fact, a price, a deadline, a name or a contact detail: when something is not "
        "in the email, leave a square-bracketed placeholder in its place, for example [date] or [amount]. "
        "Do not invent a name in the sign-off either — put a placeholder there too. "
        "Do not promise the sender anything the email does not support. "
        "The very last line of the valasz field must always be exactly this line, on its own: "
        + ai_notice(lang)
    )


# Visszafelé kompatibilis név.
DRAFT_SYS = draft_sys("hivatalos", "hu")


async def draft_one(email: dict, tone: str = "hivatalos", lang: str = "hu") -> dict:
    """Write a reply draft for one email. Shares the demos' daily cost ceiling.

    Drafting only: the text is returned to the page for the visitor to read and
    copy. Nothing is written back to the mailbox and nothing is ever sent — see
    the send block in mail_agent.SafeGmailProxy.
    """
    _reset_if_new_day()
    if _state["cost"] >= DAILY_COST_CEILING_USD:
        raise HTTPException(status_code=429, detail="Az agent mára elérte a napi keretét.")
    if tone not in DRAFT_TONES:
        tone = "hivatalos"
    text = (
        f"Feladó: {email.get('sender', '')}\n"
        f"Tárgy: {email.get('subject', '')}\n"
        f"Dátum: {email.get('date', '')}\n\n"
        f"Levél törzse:\n{(email.get('body') or email.get('snippet') or '')[:6000]}"
    )
    system_msg = draft_sys(tone, lang)

    last_err = None
    for _ in range(3):  # 1 try + 2 retries, same as the other demos
        try:
            raw = await _call_llm(system_msg, text, max_tokens=1100)
            _state["cost"] += EST_COST_PER_CALL_USD
            result = DraftResult(**_parse_json(raw))
            out = result.model_dump()
            # A jelzés akkor is odakerül, ha a modell lehagyta: a szöveget a
            # lapról másolják ki, és nem szabad úgy kinéznie, mintha ember írta
            # volna. Küldés előtt a mail_agent kiszedi.
            if not any(n in out["valasz"] for n in AI_NOTICES.values()):
                out["valasz"] = f"{out['valasz']}\n\n{ai_notice(lang)}"
            return {"tone": tone, **out}
        except HTTPException:
            raise
        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            last_err = e
            continue
        except Exception as e:  # noqa
            last_err = e
            logger.error(f"draft error: {e}")
            continue
    logger.warning(f"draft gave up: {last_err}")
    raise HTTPException(
        status_code=502,
        detail="Az agent most nem tudott fogalmazványt írni erre a levélre. Próbáld újra.",
    )



app.include_router(api_router)

from mail_agent import router as mail_agent_router  # noqa: E402 - after api_router
app.include_router(mail_agent_router)

from lead_intake import router as contact_router  # noqa: E402 - after api_router
app.include_router(contact_router)

from visits import router as visits_router  # noqa: E402 - after api_router
app.include_router(visits_router)

_cors_origins = [o.strip() for o in os.environ.get('CORS_ORIGINS', '*').split(',') if o.strip()]

app.add_middleware(
    CORSMiddleware,
    # The agent session travels in the X-Agent-Session header, never a cookie, so
    # credentialed CORS is not needed. Allowing it together with a wildcard origin
    # would let any site read a visitor's run; keep it off unless origins are named.
    allow_credentials='*' not in _cors_origins,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Session-Id", "X-Agent-Session"],
)
