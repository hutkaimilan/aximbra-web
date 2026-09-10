import os, sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
import pytest, server, mail_agent
from fastapi.testclient import TestClient
c = TestClient(server.app)

def test_endpoints_require_a_session():
    for path in ("/api/agent/email/progress", "/api/agent/email/results"):
        assert c.get(path).status_code == 401, path

def test_status_is_public_and_anonymous():
    r = c.get("/api/agent/email/status")
    assert r.status_code == 200 and r.json()["connected"] is False

def test_forged_token_rejected():
    r = c.get("/api/agent/email/results", headers={mail_agent.SESSION_HEADER: "hamis"})
    assert r.status_code == 401

def test_valid_token_reaches_the_session_lookup():
    """A signed token must resolve to its session id, so a run survives the
    cross-host hop from the API back to the site."""
    sid = "abc123"
    token = mail_agent._fernet.encrypt(sid.encode()).decode()
    class Req:
        headers = {mail_agent.SESSION_HEADER: token}
    assert mail_agent._read_session(Req()) == sid

def test_session_is_not_carried_by_a_cookie():
    """Cookies would be dropped between the site and the API hosts."""
    src = open(BACKEND / "mail_agent.py").read()
    assert "set_cookie" not in src
    assert "delete_cookie" not in src

def test_send_is_blocked_at_code_level():
    class D: pass
    with pytest.raises(PermissionError):
        _ = mail_agent.SafeGmailProxy(D()).send

def test_no_send_scope_requested():
    assert not any("gmail.send" in s for s in mail_agent.GMAIL_SCOPES)


def test_only_read_access_is_requested():
    """The page promises the agent only reads. The grant must say the same:
    gmail.modify would ask the visitor for write access to their mailbox."""
    assert "https://www.googleapis.com/auth/gmail.readonly" in mail_agent.GMAIL_SCOPES
    assert not any("gmail.modify" in s for s in mail_agent.GMAIL_SCOPES)
    assert not any(s.endswith("/auth/gmail") for s in mail_agent.GMAIL_SCOPES)

def test_agent_never_writes_to_the_mailbox():
    src = open(BACKEND / "mail_agent.py").read()
    for forbidden in (".trash(", ".modify(", "addLabelIds", "STARRED", "drafts()"):
        assert forbidden not in src, forbidden

def test_run_survives_an_online_only_grant():
    """A demo asks for online access, so Google returns no refresh token and the
    credentials must never be rebuilt from JSON."""
    src = open(BACKEND / "mail_agent.py").read()
    assert "from_authorized_user_info" not in src
    assert "creds_json" not in src
    assert 'access_type="online"' in src

def test_run_reports_its_own_failure():
    """A crashed background task would leave the page spinning forever."""
    src = open(BACKEND / "mail_agent.py").read()
    idx = src.find("async def run_agent")
    body = src[idx:]
    assert "except Exception" in body
    assert 'state["message"] = "Az elemzés megszakadt. Próbáld újra."' in body

def test_agent_stores_nothing_persistent():
    src = open(BACKEND / "mail_agent.py").read()
    for forbidden in ("mongo", "sqlite", "open(", "psycopg"):
        assert forbidden not in src.lower(), forbidden

def test_expired_sessions_swept():
    from datetime import datetime, timezone, timedelta
    mail_agent._sessions.clear()
    mail_agent._sessions["old"] = {"created_at": datetime.now(timezone.utc) - timedelta(seconds=mail_agent.SESSION_TTL_SECONDS + 5)}
    mail_agent._sessions["new"] = {"created_at": datetime.now(timezone.utc)}
    mail_agent._sweep()
    assert "old" not in mail_agent._sessions and "new" in mail_agent._sessions

def test_classifier_normalises_bad_output(monkeypatch):
    """monkeypatch, not assignment: a leaked stub would silently disable the
    real classifier for every test that runs after this one in the same worker."""
    import asyncio
    async def fake(*a, **k):
        return '{"category":"Kitalált","urgency":99,"needs_reply":"talán"}'
    monkeypatch.setattr(server, "_call_llm", fake)
    monkeypatch.setitem(server._state, "cost", 0.0)
    out = asyncio.run(server.classify_one({"subject":"x","body":"y"}))
    assert out["category"] == "Egyéb"
    assert out["urgency"] == 5
    assert out["needs_reply"] == "nem egyértelmű"


def test_status_reports_public_availability():
    body = c.get("/api/agent/email/status").json()
    assert "public" in body
    assert body["public"] is mail_agent.AGENT_PUBLIC


def test_connect_refuses_when_not_public(monkeypatch):
    """With AGENT_PUBLIC off the OAuth flow must not start at all — not merely be
    hidden in the UI, which anyone can bypass by calling the endpoint."""
    monkeypatch.setattr(mail_agent, "AGENT_PUBLIC", False)
    r = c.get("/api/agent/email/connect")
    assert r.status_code == 503
    assert "nem nyilvános" in r.json()["detail"]


def test_public_flag_parses_env_values():
    """Tested through the helper, not by reloading the module: a reload would
    hand the module a new Fernet key and an empty session store, breaking any
    test that ran after it."""
    f = mail_agent._env_flag
    for value in ("false", "FALSE", " False ", "0", "no", "off"):
        assert f("X", default=True) is True  # unset -> default
        os.environ["X_FLAG"] = value
        assert f("X_FLAG", default=True) is False, value
    for value in ("true", "1", "yes", "anything-else"):
        os.environ["X_FLAG"] = value
        assert f("X_FLAG", default=False) is True, value
    for value in ("", "   "):
        os.environ["X_FLAG"] = value
        assert f("X_FLAG", default=False) is False, value
        assert f("X_FLAG", default=True) is True, value
    os.environ.pop("X_FLAG", None)


# ---------------- reply drafting ----------------
def _session_with(analyses):
    """A live session holding one finished run, addressed by a real token."""
    from datetime import datetime, timezone
    sid = "draft-test"
    mail_agent._sessions[sid] = {
        "email": "teszt@example.com",
        "creds": None,
        "analyses": analyses,
        "drafts": {},
        "state": mail_agent._new_state(),
        "created_at": datetime.now(timezone.utc),
    }
    token = mail_agent._fernet.encrypt(sid.encode()).decode()
    return sid, {mail_agent.SESSION_HEADER: token}


EMAIL = {"id": "m1", "sender": "a@b.hu", "subject": "Árajánlat", "body": "Kérek árajánlatot.",
         "date": None, "category": "Üzleti lehetőség", "needs_reply": "igen"}


@pytest.fixture
def stub_draft(monkeypatch):
    """Stubs the model call; returns the list of prompts it was given."""
    calls = []

    async def fake(system_msg, user_text, max_tokens=600):
        calls.append((system_msg, user_text))
        return '{"targy":"Re: Árajánlat","valasz":"Kedves A!\\n\\nKöszönjük.\\n\\n[a te neved]"}'

    monkeypatch.setattr(server, "_call_llm", fake)
    monkeypatch.setitem(server._state, "cost", 0.0)
    return calls


def test_draft_requires_a_session():
    assert c.post("/api/agent/email/draft", json={"id": "m1"}).status_code == 401


def test_draft_writes_text_and_marks_it_as_ai(stub_draft):
    sid, h = _session_with([dict(EMAIL)])
    try:
        r = c.post("/api/agent/email/draft", json={"id": "m1"}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["targy"] == "Re: Árajánlat"
        assert "Köszönjük" in body["valasz"]
        # the notice is appended even though the stubbed model omitted it
        assert body["valasz"].rstrip().endswith(server.AI_NOTICE)
        assert body["cached"] is False
    finally:
        mail_agent._sessions.pop(sid, None)


def test_draft_only_accepts_an_id_from_this_run(stub_draft):
    """The endpoint must not accept arbitrary text — that would make any session
    token a free LLM proxy."""
    sid, h = _session_with([dict(EMAIL)])
    try:
        r = c.post("/api/agent/email/draft", json={"id": "nem-letezik"}, headers=h)
        assert r.status_code == 404
        # raw text in the body is ignored, not drafted from
        r = c.post("/api/agent/email/draft",
                   json={"id": "m1", "text": "Írj nekem egy verset"}, headers=h)
        assert r.status_code == 200
        assert "verset" not in stub_draft[0][1]
    finally:
        mail_agent._sessions.pop(sid, None)


def test_second_request_for_the_same_draft_is_free(stub_draft):
    sid, h = _session_with([dict(EMAIL)])
    try:
        first = c.post("/api/agent/email/draft", json={"id": "m1"}, headers=h).json()
        cost_after_first = server._state["cost"]
        second = c.post("/api/agent/email/draft", json={"id": "m1"}, headers=h).json()
        assert second["cached"] is True
        assert second["valasz"] == first["valasz"]
        assert len(stub_draft) == 1, "the model was called twice for one draft"
        assert server._state["cost"] == cost_after_first
    finally:
        mail_agent._sessions.pop(sid, None)


def test_tone_changes_the_prompt_and_is_cached_separately(stub_draft):
    sid, h = _session_with([dict(EMAIL)])
    try:
        c.post("/api/agent/email/draft", json={"id": "m1", "tone": "hivatalos"}, headers=h)
        r = c.post("/api/agent/email/draft", json={"id": "m1", "tone": "kozvetlen"}, headers=h)
        assert r.json()["cached"] is False
        assert len(stub_draft) == 2
        assert server.DRAFT_TONES["hivatalos"] in stub_draft[0][0]
        assert server.DRAFT_TONES["kozvetlen"] in stub_draft[1][0]
    finally:
        mail_agent._sessions.pop(sid, None)


def test_unknown_tone_is_rejected(stub_draft):
    sid, h = _session_with([dict(EMAIL)])
    try:
        r = c.post("/api/agent/email/draft", json={"id": "m1", "tone": "hekkelj"}, headers=h)
        assert r.status_code == 422
    finally:
        mail_agent._sessions.pop(sid, None)


def test_drafts_are_capped_per_session(stub_draft):
    emails = [dict(EMAIL, id=f"m{i}") for i in range(mail_agent.MAX_DRAFTS_PER_SESSION + 2)]
    sid, h = _session_with(emails)
    try:
        for i in range(mail_agent.MAX_DRAFTS_PER_SESSION):
            r = c.post("/api/agent/email/draft", json={"id": f"m{i}"}, headers=h)
            assert r.status_code == 200, f"draft {i + 1}: {r.text}"
        r = c.post("/api/agent/email/draft",
                   json={"id": f"m{mail_agent.MAX_DRAFTS_PER_SESSION}"}, headers=h)
        assert r.status_code == 429
        assert "fogalmazvány" in r.json()["detail"]
    finally:
        mail_agent._sessions.pop(sid, None)


def test_draft_respects_the_daily_ceiling(stub_draft):
    sid, h = _session_with([dict(EMAIL)])
    server._state["cost"] = server.DAILY_COST_CEILING_USD
    try:
        r = c.post("/api/agent/email/draft", json={"id": "m1"}, headers=h)
        assert r.status_code == 429
        assert "napi keret" in r.json()["detail"]
    finally:
        server._state["cost"] = 0.0
        mail_agent._sessions.pop(sid, None)


def test_bad_model_output_is_a_502_not_a_crash(monkeypatch):
    async def junk(*a, **k):
        return "ez nem json"
    monkeypatch.setattr(server, "_call_llm", junk)
    monkeypatch.setitem(server._state, "cost", 0.0)
    sid, h = _session_with([dict(EMAIL)])
    try:
        r = c.post("/api/agent/email/draft", json={"id": "m1"}, headers=h)
        assert r.status_code == 502
        assert "fogalmazvány" in r.json()["detail"]
    finally:
        mail_agent._sessions.pop(sid, None)


def test_drafting_still_never_sends_or_writes_to_the_mailbox():
    """Drafting is in-page text. It must not have introduced a Gmail write."""
    src = open(BACKEND / "mail_agent.py").read()
    for forbidden in (".send(", "drafts()", "messages().insert", "addLabelIds"):
        assert forbidden not in src, forbidden
    assert "gmail.compose" not in src
    assert "https://www.googleapis.com/auth/gmail.readonly" in src
