"""A jóváhagyásra váró második változat: szélesebb szemétszűrő, két hét után
nem sürgős, és a két hónapnál régebbi levelek Kukába (engedéllyel)."""
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("OPENAI_API_KEY", "sk-test")

import pytest  # noqa: E402
import server  # noqa: E402
import mail_agent  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

c = TestClient(server.app)


def test_low_urgency_notices_are_junk_only_in_v2():
    notice = {"category": "provider_notice", "urgency": 2}
    urgent_notice = {"category": "provider_notice", "urgency": 4}
    assert not mail_agent._is_trashable(notice)
    assert mail_agent._is_trashable(notice, wide=True)
    assert not mail_agent._is_trashable(urgent_notice, wide=True)
    for cat in ("invoice", "customer_question", "authority", "opportunity"):
        assert not mail_agent._is_trashable({"category": cat, "urgency": 1}, wide=True)


def test_an_email_older_than_two_weeks_is_never_urgent():
    now = datetime.now(timezone.utc)
    old = {"date": (now - timedelta(days=20)).isoformat()}
    new = {"date": (now - timedelta(days=3)).isoformat()}
    assert mail_agent._cap_stale(old, {"urgency": 5}, now)["urgency"] == 2
    assert mail_agent._cap_stale(new, {"urgency": 5}, now)["urgency"] == 5
    assert mail_agent._cap_stale({"date": None}, {"urgency": 5}, now)["urgency"] == 5


def test_the_callback_returns_only_to_a_listed_origin(monkeypatch):
    monkeypatch.setattr(mail_agent, "RETURN_ORIGINS", {"https://preview.example.app"})
    assert mail_agent._safe_return("https://preview.example.app/") == "https://preview.example.app"
    assert mail_agent._safe_return("https://evil.example.com") == ""
    st = mail_agent._pack_state("v" * 43, False, "hu", v2=True, ret="https://evil.example.com")
    out = mail_agent._unpack_state(st)
    assert out["v2"] is True and out["ret"] == ""


@pytest.fixture
def stub_classifier(monkeypatch):
    async def fake(email, lang="hu"):
        cat = "newsletter" if "hírlevél" in (email.get("subject") or "").lower() else "other"
        return {"category": cat, "urgency": 1, "needs_reply": "nem", "urgency_reason": "",
                "deadline": "", "summary": "", "next_step": ""}
    monkeypatch.setattr(server, "classify_one", fake)
    monkeypatch.setitem(server._state, "cost", 0.0)
    server._ip_hits.clear()


def _wait(h):
    for _ in range(100):
        if not c.get("/api/agent/email/progress", headers=h).json()["running"]:
            return
        time.sleep(0.05)


def test_the_sample_old_mail_cleanup_needs_a_confirmation(stub_classifier):
    tok = c.post("/api/agent/email/sample?lang=hu&v2=true").json()["session"]
    h = {"X-Agent-Session": tok}
    _wait(h)
    assert c.get("/api/agent/email/status", headers=h).json()["v2"] is True
    n = c.get("/api/agent/email/old", headers=h).json()["count"]
    assert n == mail_agent.SAMPLE_OLD_COUNT
    assert c.post("/api/agent/email/old/trash", json={}, headers=h).status_code == 400
    r = c.post("/api/agent/email/old/trash", json={"confirm": True}, headers=h).json()
    assert r["trashed"] == n and r["remaining"] == 0
    assert c.get("/api/agent/email/old", headers=h).json()["count"] == 0


def test_the_live_site_sample_has_no_old_mail(stub_classifier):
    tok = c.post("/api/agent/email/sample?lang=hu").json()["session"]
    h = {"X-Agent-Session": tok}
    _wait(h)
    assert c.get("/api/agent/email/status", headers=h).json()["v2"] is False
    assert c.get("/api/agent/email/old", headers=h).json()["count"] == 0


def test_a_real_session_without_the_cleanup_grant_cannot_trash_old_mail():
    sid = "v2-nogrant"
    mail_agent._sessions[sid] = {
        "creds": object(), "email": "p@example.com", "analyses": [], "drafts": {}, "saved": {},
        "sent": {}, "created_at": datetime.now(timezone.utc), "state": mail_agent._new_state(),
        "sample": False, "can_draft": False, "can_trash": False, "v2": True,
    }
    try:
        h = {"X-Agent-Session": mail_agent._fernet.encrypt(sid.encode()).decode()}
        r = c.post("/api/agent/email/old/trash", json={"confirm": True}, headers=h)
        assert r.status_code == 403
    finally:
        mail_agent._sessions.pop(sid, None)


class _Exec:
    def __init__(self, fn):
        self.fn = fn

    def execute(self, http=None):
        return self.fn()


class _FakeGmail:
    """Csak az, amit a régi-levél takarítás hív: list, trash, batch."""

    def __init__(self, n):
        self.box = [f"m{i}" for i in range(n)]
        self.trashed = []

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, userId, q, maxResults, pageToken=None):
        assert "older_than:60d" in q and "-is:starred" in q and "in:inbox" in q
        start = int(pageToken or 0)
        page = self.box[start:start + maxResults]
        nxt = str(start + maxResults) if start + maxResults < len(self.box) else None
        return _Exec(lambda: {"messages": [{"id": m} for m in page], "nextPageToken": nxt})

    def trash(self, userId, id):
        return id

    def new_batch_http_request(self, callback):
        gmail = self
        class B:
            def __init__(self):
                self.items = []
            def add(self, req, request_id):
                self.items.append(request_id)
            def execute(self, http=None):
                for mid in self.items:
                    gmail.trashed.append(mid)
                    gmail.box.remove(mid)
                    callback(mid, {}, None)
        return B()


def test_old_mail_goes_to_trash_in_rounds_of_at_most_500(monkeypatch):
    gmail = _FakeGmail(620)
    monkeypatch.setattr(mail_agent, "build", lambda *a, **k: gmail)
    monkeypatch.setattr(mail_agent, "SafeGmailProxy", lambda t, allow_send=False: t)
    monkeypatch.setattr(mail_agent, "_fresh_http", lambda creds: None)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    sid = "v2-old"
    mail_agent._sessions[sid] = {
        "creds": object(), "email": "p@example.com", "analyses": [], "drafts": {}, "saved": {},
        "sent": {}, "created_at": datetime.now(timezone.utc), "state": mail_agent._new_state(),
        "sample": False, "can_draft": False, "can_trash": True, "v2": True,
    }
    try:
        h = {"X-Agent-Session": mail_agent._fernet.encrypt(sid.encode()).decode()}
        assert c.get("/api/agent/email/old", headers=h).json()["count"] == 620
        r = c.post("/api/agent/email/old/trash", json={"confirm": True}, headers=h).json()
        assert r["trashed"] == 500 and r["remaining"] == 120
        r = c.post("/api/agent/email/old/trash", json={"confirm": True}, headers=h).json()
        assert r["trashed"] == 120 and r["remaining"] == 0
        assert len(gmail.trashed) == 620
    finally:
        mail_agent._sessions.pop(sid, None)
