from fastapi import FastAPI, APIRouter, Request, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
import os
import json
import time
import logging
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
DAILY_COST_CEILING_USD = 4.0
EST_COST_PER_CALL_USD = 0.01
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


class EmailResult(BaseModel):
    kategoria: Literal["Reklamáció", "Árajánlat-kérés", "Számlázási kérdés", "Technikai támogatás", "Együttműködési ajánlat", "Egyéb"]
    surgosseg: Literal["Sürgős", "Normál", "Ráér"]
    felelos: Literal["Ügyfélszolgálat", "Értékesítés", "Pénzügy", "Műszaki", "Vezetőség"]
    valaszhatarido: Literal["4 órán belül", "1 munkanap", "3 munkanap"]
    osszefoglalo: str
    javasolt_lepes: str

    @field_validator("osszefoglalo", "javasolt_lepes")
    @classmethod
    def _cap(cls, v):
        return v[:300]


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


EMAIL_SYS = (
    "Te egy magyar ügyfélszolgálati e-mail rendező asszisztens vagy. Osztályozd a beérkező e-mailt. "
    "KIZÁRÓLAG érvényes JSON objektummal válaszolj, magyarázat nélkül, ezekkel a kulcsokkal: "
    "kategoria (Reklamáció|Árajánlat-kérés|Számlázási kérdés|Technikai támogatás|Együttműködési ajánlat|Egyéb), "
    "surgosseg (Sürgős|Normál|Ráér), "
    "felelos (Ügyfélszolgálat|Értékesítés|Pénzügy|Műszaki|Vezetőség), "
    "valaszhatarido (4 órán belül|1 munkanap|3 munkanap), "
    "osszefoglalo (max 300 karakter, magyarul), javasolt_lepes (max 300 karakter, magyarul)."
)

LEAD_SYS = (
    "Te egy magyar értékesítési érdeklődő-minősítő asszisztens vagy. Minősítsd a leírt érdeklődőt (BANT logika). "
    "KIZÁRÓLAG érvényes JSON objektummal válaszolj, magyarázat nélkül, ezekkel a kulcsokkal: "
    "minosites (A|B|C|D, ahol A a legjobb), "
    "igeny, koltsegvetes, donteshozo, hatarido — mindegyik értéke pontosan: Igazolt|Valószínű|Ismeretlen|Nem illeszkedik, "
    "indoklas (max 400 karakter, magyarul), javasolt_lepes (max 300 karakter, magyarul)."
)


async def _call_llm(system_msg: str, user_text: str) -> str:
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
        "max_tokens": 600,
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


async def _run_demo(request: Request, body: DemoRequest, system_msg: str, model_cls):
    session_id = request.headers.get("X-Session-Id", "anon")
    _check_limits(request, session_id)
    last_err = None
    for _ in range(3):  # 1 try + 2 retries
        try:
            raw = await _call_llm(system_msg, body.text)
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


@api_router.post("/demo/email")
async def demo_email(request: Request, body: DemoRequest):
    return await _run_demo(request, body, EMAIL_SYS, EmailResult)


@api_router.post("/demo/lead")
async def demo_lead(request: Request, body: DemoRequest):
    return await _run_demo(request, body, LEAD_SYS, LeadResult)


app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)
