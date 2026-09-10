"""Local tests for the AXIMBRA demo API.

Deliberately offline: the LLM call is stubbed, so the suite exercises the
endpoints' own logic (validation, schema enforcement, rate limits) without a
network round trip, an API key or a cent of model spend.
"""
import os
import sys
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import pytest
from fastapi.testclient import TestClient

import server

client = TestClient(server.app)

LEAD_MINOSITES = {"A", "B", "C", "D"}
LEAD_DIM = {"Igazolt", "Valószínű", "Ismeretlen", "Nem illeszkedik"}

VALID_LEAD = (
    '{"minosites":"A","igeny":"Igazolt","koltsegvetes":"Valószínű",'
    '"donteshozo":"Igazolt","hatarido":"Ismeretlen",'
    '"indoklas":"Konkrét igény és döntéshozó.","javasolt_lepes":"Hívd fel a héten."}'
)


def _sid():
    return f"test-{uuid.uuid4().hex[:12]}"


@pytest.fixture(autouse=True)
def clean_limits(monkeypatch):
    """Every test starts from an empty budget; the counters are module globals."""
    server._state["cost"] = 0.0
    server._session_runs.clear()
    server._ip_hits.clear()
    yield
    server._state["cost"] = 0.0
    server._session_runs.clear()
    server._ip_hits.clear()


@pytest.fixture
def llm(monkeypatch):
    """Replaces the single OpenAI call with a scripted reply."""
    def _set(reply, record=None):
        async def fake(system_msg, user_text, max_tokens=600):
            if record is not None:
                record.append(user_text)
            return reply(user_text) if callable(reply) else reply
        monkeypatch.setattr(server, "_call_llm", fake)
    return _set


def test_root():
    r = client.get("/api/")
    assert r.status_code == 200
    assert r.json().get("message") == "AXIMBRA API"


def test_lead_success_schema(llm):
    llm(VALID_LEAD)
    r = client.post(
        "/api/demo/lead",
        json={"text": "150 fős SaaS cég marketing igazgatója vagyok, 15-20 millió Ft kerettel."},
        headers={"X-Session-Id": _sid()},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["minosites"] in LEAD_MINOSITES
    for key in ("igeny", "koltsegvetes", "donteshozo", "hatarido"):
        assert data[key] in LEAD_DIM, f"{key}={data[key]}"
    assert data["indoklas"] and data["javasolt_lepes"]


def test_lead_empty_returns_422(llm):
    llm(VALID_LEAD)
    r = client.post("/api/demo/lead", json={"text": "   "}, headers={"X-Session-Id": _sid()})
    assert r.status_code == 422


def test_lead_truncates_long_input(llm):
    """The server caps the prompt at MAX_INPUT_CHARS so a paste cannot run up cost."""
    seen = []
    llm(VALID_LEAD, record=seen)
    long_text = "Érdeklődő leírása. " + ("nagyon hosszú " * 800)
    assert len(long_text) > server.MAX_INPUT_CHARS
    r = client.post(
        "/api/demo/lead", json={"text": long_text}, headers={"X-Session-Id": _sid()}
    )
    assert r.status_code == 200, r.text
    assert len(seen[0]) == server.MAX_INPUT_CHARS


def test_invalid_model_output_falls_back_to_502(llm):
    """Three malformed replies must surface as a graceful error, never a 500."""
    llm('{"minosites":"Z"}')
    r = client.post(
        "/api/demo/lead", json={"text": "Teszt érdeklődő."}, headers={"X-Session-Id": _sid()}
    )
    assert r.status_code == 502
    assert "nem tudott érvényes választ adni" in r.json()["detail"]


def test_failed_run_is_not_billed(llm):
    """A run only counts against the budget once it produced a valid answer."""
    llm("nem json")
    client.post("/api/demo/lead", json={"text": "Teszt."}, headers={"X-Session-Id": _sid()})
    assert server._state["cost"] == 0.0


def test_rate_limit_per_session(llm):
    """The (MAX_RUNS_PER_SESSION + 1)-th run in one session is refused."""
    llm(VALID_LEAD)
    sid = _sid()
    payload = {"text": "Rövid teszt érdeklődő."}
    for i in range(server.MAX_RUNS_PER_SESSION):
        r = client.post("/api/demo/lead", json=payload, headers={"X-Session-Id": sid})
        assert r.status_code == 200, f"run {i + 1}: {r.text}"
    r = client.post("/api/demo/lead", json=payload, headers={"X-Session-Id": sid})
    assert r.status_code == 429, r.text
    assert "munkamenetben" in r.json()["detail"]


def test_daily_cost_ceiling_closes_the_demo(llm):
    llm(VALID_LEAD)
    server._state["cost"] = server.DAILY_COST_CEILING_USD
    r = client.post("/api/demo/lead", json={"text": "Teszt."}, headers={"X-Session-Id": _sid()})
    assert r.status_code == 429
    assert "napi keret" in r.json()["detail"]


def test_missing_api_key_is_a_clear_503(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = client.post("/api/demo/lead", json={"text": "Teszt."}, headers={"X-Session-Id": _sid()})
    assert r.status_code == 503
    assert "nincs beállítva" in r.json()["detail"]


def test_voice_health_degrades_instead_of_failing(monkeypatch):
    """The home page badge must render even when the voice service is down."""
    class Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, url):
            raise RuntimeError("unreachable")

    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kw: Boom())
    r = client.get("/api/voice/health")
    assert r.status_code == 200
    assert r.json() == {
        "reachable": False, "ok": False, "day": None, "count": None, "live": None
    }
