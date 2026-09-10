import base64
import os, sys
from email import message_from_bytes, policy
from email.header import decode_header, make_header
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

def test_agent_never_alters_existing_mail():
    """The agent may now create a reply draft, on an explicit grant plus a
    per-email confirmation. Everything else about the mailbox stays untouched: it
    does not label, star, trash, or modify a single existing message."""
    src = open(BACKEND / "mail_agent.py").read()
    for forbidden in (".trash(", ".modify(", "addLabelIds", "removeLabelIds", "STARRED",
                      "messages().insert", "messages().batchModify"):
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
        "can_draft": False,
        "drafts": {},
        "saved": {},
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


def test_drafting_never_sends():
    """Writing a draft is allowed now; sending one never is. The line that must
    not move is send, in any form — drafts().send() included."""
    src = open(BACKEND / "mail_agent.py").read()
    for forbidden in (".send(", "messages().send", "drafts().send", "gmail.send"):
        assert forbidden not in src, forbidden
    # the send block is still the code-level guarantee, not just an absent call
    class D: pass
    with pytest.raises(PermissionError):
        _ = mail_agent.SafeGmailProxy(D()).send


def test_read_only_is_still_the_default_grant():
    """The wider scope is opt-in. A visitor who does not ask for draft writing must
    not be asked for it."""
    assert "https://www.googleapis.com/auth/gmail.readonly" in mail_agent.GMAIL_SCOPES
    assert mail_agent.COMPOSE_SCOPE not in mail_agent.GMAIL_SCOPES
    assert mail_agent.COMPOSE_SCOPE in mail_agent.GMAIL_SCOPES_COMPOSE
    # readonly is still requested alongside compose - compose cannot read mail
    assert all(s in mail_agent.GMAIL_SCOPES_COMPOSE for s in mail_agent.GMAIL_SCOPES)
    # modify is still never requested: it would allow altering existing mail
    assert not any("gmail.modify" in s for s in mail_agent.GMAIL_SCOPES_COMPOSE)


# ---------------- writing the draft into the mailbox ----------------
class FakeDrafts:
    """Stands in for service.users().drafts(): records calls, returns ids."""
    def __init__(self, store):
        self.store = store

    def create(self, userId, body):
        self.store.append(("create", userId, body))
        return _Exec({"id": "draft-1", "message": {"threadId": body["message"].get("threadId")}})

    def update(self, userId, id, body):
        self.store.append(("update", userId, id, body))
        return _Exec({"id": id})


class _Exec:
    def __init__(self, result):
        self._r = result

    def execute(self):
        return self._r


class FakeUsers:
    def __init__(self, store):
        self._d = FakeDrafts(store)

    def drafts(self):
        return self._d


class FakeService:
    def __init__(self, store):
        self._u = FakeUsers(store)

    def users(self):
        return self._u


@pytest.fixture
def gmail_calls(monkeypatch):
    """Intercepts build() so no real Gmail call is made; returns recorded calls."""
    calls = []
    monkeypatch.setattr(mail_agent, "build", lambda *a, **k: FakeService(calls))
    monkeypatch.setattr(mail_agent, "SafeGmailProxy", lambda target: target)
    return calls


THREADED = dict(
    EMAIL, thread_id="t99", message_id="<orig@pelda.hu>",
    references="<older@pelda.hu>", reply_to="",
)


def _session_ready_to_save(can_draft=True, email=None):
    """A session that already holds a generated draft for EMAIL m1."""
    sid, h = _session_with([dict(email or THREADED)])
    s = mail_agent._sessions[sid]
    s["can_draft"] = can_draft
    s["drafts"]["m1:hivatalos"] = {
        "tone": "hivatalos", "targy": "Árajánlat", "valasz": "Kedves A!\n\nKöszönjük.",
    }
    return sid, h


def test_saving_a_draft_requires_a_session():
    r = c.post("/api/agent/email/draft/save", json={"id": "m1", "confirm": True})
    assert r.status_code == 401


def test_saving_is_refused_without_the_grant(gmail_calls):
    sid, h = _session_ready_to_save(can_draft=False)
    try:
        r = c.post("/api/agent/email/draft/save",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 403
        assert "vázlatírási engedély" in r.json()["detail"]
        assert gmail_calls == [], "Gmail was touched without the grant"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_saving_is_refused_without_confirmation(gmail_calls):
    """The mailbox is never written on an unconfirmed request, grant or no grant."""
    sid, h = _session_ready_to_save()
    try:
        for payload in ({"id": "m1"}, {"id": "m1", "confirm": False}):
            r = c.post("/api/agent/email/draft/save", json=payload, headers=h)
            assert r.status_code == 400, payload
            assert "Megerősítés nélkül" in r.json()["detail"]
        assert gmail_calls == [], "Gmail was touched without confirmation"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_saving_needs_an_existing_draft(gmail_calls):
    sid, h = _session_with([dict(THREADED)])
    mail_agent._sessions[sid]["can_draft"] = True
    try:
        r = c.post("/api/agent/email/draft/save",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 409
        assert gmail_calls == []
    finally:
        mail_agent._sessions.pop(sid, None)


def test_confirmed_save_creates_a_threaded_reply_draft(gmail_calls):
    sid, h = _session_ready_to_save()
    try:
        r = c.post("/api/agent/email/draft/save",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["draft_id"] == "draft-1"
        assert body["updated"] is False
        assert body["to"] == "a@b.hu"
        assert body["subject"] == "Re: Árajánlat"
        assert "draft-1" in body["gmail_url"]

        assert len(gmail_calls) == 1
        op, user, payload = gmail_calls[0]
        assert (op, user) == ("create", "me")
        assert payload["message"]["threadId"] == "t99"

        # Parsed, not string-matched: a Hungarian subject is RFC 2047 encoded
        # (=?utf-8?q?...?=), so asserting on the raw bytes would either fail on
        # correct output or pass on mojibake.
        msg = message_from_bytes(
            base64.urlsafe_b64decode(payload["message"]["raw"]), policy=policy.default
        )
        assert msg["To"] == "a@b.hu"
        assert msg["From"] == "teszt@example.com"
        assert str(make_header(decode_header(msg["Subject"]))) == "Re: Árajánlat"
        # threading headers, not just Gmail's threadId
        assert msg["In-Reply-To"] == "<orig@pelda.hu>"
        assert msg["References"] == "<older@pelda.hu> <orig@pelda.hu>"
        assert "Köszönjük" in msg.get_content()
    finally:
        mail_agent._sessions.pop(sid, None)


def test_reply_to_wins_over_from(gmail_calls):
    sid, h = _session_ready_to_save(email=dict(THREADED, reply_to="ugyfelszolgalat@b.hu"))
    try:
        r = c.post("/api/agent/email/draft/save",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.json()["to"] == "ugyfelszolgalat@b.hu"
        msg = message_from_bytes(base64.urlsafe_b64decode(gmail_calls[0][2]["message"]["raw"]))
        assert msg["To"] == "ugyfelszolgalat@b.hu"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_reconfirming_updates_the_same_draft(gmail_calls):
    """A second confirmation must not leave a pile of near-identical drafts."""
    sid, h = _session_ready_to_save()
    try:
        c.post("/api/agent/email/draft/save", json={"id": "m1", "confirm": True}, headers=h)
        r = c.post("/api/agent/email/draft/save", json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 200
        assert r.json()["updated"] is True
        assert r.json()["draft_id"] == "draft-1"
        assert [call[0] for call in gmail_calls] == ["create", "update"]
    finally:
        mail_agent._sessions.pop(sid, None)


def test_unanswerable_sender_is_refused(gmail_calls):
    sid, h = _session_ready_to_save(email=dict(THREADED, sender="", reply_to=""))
    try:
        r = c.post("/api/agent/email/draft/save",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 422
        assert gmail_calls == []
    finally:
        mail_agent._sessions.pop(sid, None)


def test_gmail_refusal_is_a_502_not_a_crash(monkeypatch):
    class Boom:
        def users(self):
            raise RuntimeError("gmail said no")
    monkeypatch.setattr(mail_agent, "build", lambda *a, **k: Boom())
    monkeypatch.setattr(mail_agent, "SafeGmailProxy", lambda t: t)
    sid, h = _session_ready_to_save()
    try:
        r = c.post("/api/agent/email/draft/save",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 502
        assert "nem fogadta el" in r.json()["detail"]
    finally:
        mail_agent._sessions.pop(sid, None)


def test_subject_is_normalised_to_a_reply():
    f = mail_agent._reply_subject
    assert f("Árajánlat") == "Re: Árajánlat"
    assert f("Re: Árajánlat") == "Re: Árajánlat"
    assert f("RE: Árajánlat") == "RE: Árajánlat"
    assert f("") == "Re:"
    assert f("(nincs tárgy)") == "Re:"


def test_status_reports_draft_permission():
    body = c.get("/api/agent/email/status").json()
    assert body["can_draft"] is False, "no session means no draft permission"


def test_granted_scopes_decide_not_what_was_requested():
    """A visitor can untick a scope on Google's consent screen. Asking is not
    receiving, and the page must not offer a button that cannot work."""
    class Creds:
        def __init__(self, scopes):
            self.granted_scopes = scopes
    g = mail_agent._granted_compose
    assert g(Creds([mail_agent.COMPOSE_SCOPE]), requested=True) is True
    assert g(Creds(["https://www.googleapis.com/auth/gmail.readonly"]), requested=True) is False
    assert g(Creds([]), requested=True) is True, "no list reported -> fall back to request"
    assert g(Creds([]), requested=False) is False


def test_connect_carries_the_draft_choice_into_the_oauth_state(monkeypatch):
    """The callback must rebuild the flow with the same scopes, or Google rejects
    the exchange."""
    seen = {}

    class FakeFlow:
        code_verifier = "v"

        def authorization_url(self, **kw):
            return ("https://accounts.google.com/fake", "state-1")

    def fake_flow(with_compose=False):
        seen["with_compose"] = with_compose
        return FakeFlow()

    monkeypatch.setattr(mail_agent, "_flow", fake_flow)
    mail_agent._oauth_states.clear()

    c.get("/api/agent/email/connect")
    assert seen["with_compose"] is False
    assert mail_agent._oauth_states["state-1"]["with_compose"] is False

    c.get("/api/agent/email/connect?drafts=true")
    assert seen["with_compose"] is True
    assert mail_agent._oauth_states["state-1"]["with_compose"] is True
    mail_agent._oauth_states.clear()
