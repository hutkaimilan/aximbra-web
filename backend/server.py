from fastapi import FastAPI, APIRouter, Request, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import json
import time
import logging
import httpx
from pathlib import Path
from datetime import datetime, timezone, date
from pydantic import BaseModel, ValidationError, field_validator
from typing import Literal
from openai import AsyncOpenAI, BadRequestError

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


async def _call_llm(system_msg: str, user_text: str, max_tokens: int = 600) -> str:
    """
    Egyetlen OpenAI chat-completion hivas, JSON kimenetre kenyszeritve.

    Kozvetlen SDK-t hasznalunk wrapper helyett: a wrapper egy szolgaltatohoz
    kotne a backendet. Igy a kod barhol fut, ahol van OPENAI_API_KEY.

    Nehany ujabb modell nem engedi a temperature-t vagy a max_tokens-t.
    Ilyenkor a hivast egyszer megismeteljuk igazitott parameterekkel, hogy egy
    modellvaltas ne torje el a demot.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Az élő demó jelenleg nincs beállítva. Írj nekünk: aximbra@gmail.com",
        )

    client = AsyncOpenAI(api_key=api_key, timeout=30.0, max_retries=0)
    kwargs = {
        "model": os.environ.get("DEMO_MODEL", "gpt-4.1-mini"),
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_text},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
        "temperature": 0,
    }

    resp = None
    for _ in range(3):
        try:
            resp = await client.chat.completions.create(**kwargs)
            break
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

    content = resp.choices[0].message.content
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
            last_err = e
            logger.error(f"demo llm error: {e}")
            continue
    raise HTTPException(status_code=502, detail="Az agent most nem tudott érvényes választ adni. Kérlek, próbáld újra kicsit másképp megfogalmazva.")


@api_router.get("/")
async def root():
    return {"message": "AXIMBRA API"}


VOICE_HEALTH_URL = "https://aximbra-voice-production.up.railway.app/health"


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
        }
    except Exception as e:
        logger.warning(f"voice health unreachable: {e}")
        return {"reachable": False, "ok": False, "day": None, "count": None, "live": None}


@api_router.post("/demo/lead")
async def demo_lead(request: Request, body: DemoRequest):
    return await _run_demo(request, body, LEAD_SYS, LeadResult)


# Nyolc nyelven fut az oldal, tehát nyolc nyelven kell a kimenet is. A
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



async def classify_one(email: dict, lang: str = "hu") -> dict:
    """One classification for the in-page email agent. Shares the demos' daily
    cost ceiling so a long mailbox cannot run up an unbounded bill."""
    _reset_if_new_day()
    if _state["cost"] >= DAILY_COST_CEILING_USD:
        raise HTTPException(status_code=429, detail="Az agent mára elérte a napi keretét.")
    text = (
        f"Feladó: {email.get('sender', '')}\n"
        f"Tárgy: {email.get('subject', '')}\n"
        f"Dátum: {email.get('date', '')}\n\n"
        f"Levél törzse:\n{(email.get('body') or email.get('snippet') or '')[:6000]}"
    )
    raw = await _call_llm(agent_sys(lang), text, max_tokens=700)
    _state["cost"] += EST_COST_PER_CALL_USD
    data = _parse_json(raw)

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
