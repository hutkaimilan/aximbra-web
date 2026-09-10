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
