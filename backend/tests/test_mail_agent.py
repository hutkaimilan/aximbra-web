import base64
import os, sys
from email import message_from_bytes, policy
from email.header import decode_header, make_header
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.environ.setdefault("OPENAI_API_KEY", "sk-test")
import pytest, server, mail_agent
from googleapiclient.discovery import Resource
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
        "sent": {},
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


def test_sending_is_refused_by_default_and_down_the_chain():
    """Sending is now possible, on one confirmed path. Everywhere else the proxy
    must still refuse — including on a Resource reached through it, or the refusal
    would only be skin deep."""
    class D: pass
    with pytest.raises(PermissionError):
        _ = mail_agent.SafeGmailProxy(D()).send

    class FakeResource(Resource):
        def __init__(self):
            pass

    class Users:
        def messages(self):
            return FakeResource()

    # a nested Resource inherits the refusal
    nested = mail_agent.SafeGmailProxy(Users()).messages()
    with pytest.raises(PermissionError):
        _ = nested.send
    # and an explicitly permitted proxy passes it down
    permitted = mail_agent.SafeGmailProxy(Users(), allow_send=True).messages()
    assert permitted is not None


def test_only_one_call_site_may_send():
    """Grepping is the point: a second allow_send=True somewhere else would be a
    second way to send mail, and this test is what makes that a deliberate act."""
    src = open(BACKEND / "mail_agent.py").read()
    # Comment lines are stripped first: the docstring above SafeGmailProxy names
    # allow_send=True in prose, and counting prose would make this test lie.
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#")
    )
    assert code.count("allow_send=True") == 1, "more than one code path can send"
    # and it lives in the confirmed send endpoint, not somewhere incidental
    idx = code.index("allow_send=True")
    enclosing = code.rindex("async def ", 0, idx)
    assert "async def send_draft" in code[enclosing:enclosing + 40]


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


# ---------------- sending ----------------
class FakeDraftsSend(FakeDrafts):
    def send(self, userId, body):
        self.store.append(("send", userId, body["id"]))
        return _Exec({"id": "sent-1", "threadId": "t99"})


class FakeUsersSend(FakeUsers):
    def __init__(self, store):
        self._d = FakeDraftsSend(store)


class FakeServiceSend(FakeService):
    def __init__(self, store):
        self._u = FakeUsersSend(store)


@pytest.fixture
def gmail_send_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(mail_agent, "build", lambda *a, **k: FakeServiceSend(calls))
    monkeypatch.setattr(mail_agent, "SafeGmailProxy", lambda target, allow_send=False: target)
    return calls


def test_send_requires_a_session():
    r = c.post("/api/agent/email/draft/send", json={"id": "m1", "confirm": True})
    assert r.status_code == 401


def test_send_is_refused_without_the_grant(gmail_send_calls):
    sid, h = _session_ready_to_save(can_draft=False)
    try:
        r = c.post("/api/agent/email/draft/send",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 403
        assert gmail_send_calls == [], "Gmail was touched without the grant"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_send_is_refused_without_confirmation(gmail_send_calls):
    """Sending cannot be undone; an unconfirmed request must never reach Gmail."""
    sid, h = _session_ready_to_save()
    try:
        for payload in ({"id": "m1"}, {"id": "m1", "confirm": False}):
            r = c.post("/api/agent/email/draft/send", json=payload, headers=h)
            assert r.status_code == 400, payload
            assert "Megerősítés nélkül nem küldünk" in r.json()["detail"]
        assert gmail_send_calls == []
    finally:
        mail_agent._sessions.pop(sid, None)


def test_send_needs_an_existing_draft(gmail_send_calls):
    """Nothing is ever sent that the user has not read on the page."""
    sid, h = _session_with([dict(THREADED)])
    mail_agent._sessions[sid]["can_draft"] = True
    try:
        r = c.post("/api/agent/email/draft/send",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 409
        assert gmail_send_calls == []
    finally:
        mail_agent._sessions.pop(sid, None)


def test_confirmed_send_creates_then_sends_that_draft(gmail_send_calls):
    sid, h = _session_ready_to_save()
    try:
        r = c.post("/api/agent/email/draft/send",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["message_id"] == "sent-1"
        assert body["to"] == "a@b.hu"
        assert body["subject"] == "Re: Árajánlat"

        ops = [call[0] for call in gmail_send_calls]
        assert ops == ["create", "send"], ops
        # what is sent is the draft that was built, by id — not a second compose
        assert gmail_send_calls[1][2] == "draft-1"
        msg = message_from_bytes(
            base64.urlsafe_b64decode(gmail_send_calls[0][2]["message"]["raw"]),
            policy=policy.default,
        )
        assert msg["To"] == "a@b.hu"
        assert msg["In-Reply-To"] == "<orig@pelda.hu>"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_send_reuses_an_already_saved_draft(gmail_send_calls):
    """If the user saved first and then sent, the saved draft is updated and sent,
    not duplicated."""
    sid, h = _session_ready_to_save()
    mail_agent._sessions[sid]["saved"]["m1"] = "draft-existing"
    try:
        c.post("/api/agent/email/draft/send", json={"id": "m1", "confirm": True}, headers=h)
        ops = [call[0] for call in gmail_send_calls]
        assert ops == ["update", "send"], ops
        assert gmail_send_calls[1][2] == "draft-existing"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_one_email_cannot_be_answered_twice(gmail_send_calls):
    """A double click or a replayed request must not send a second reply."""
    sid, h = _session_ready_to_save()
    try:
        first = c.post("/api/agent/email/draft/send",
                       json={"id": "m1", "confirm": True}, headers=h)
        assert first.status_code == 200
        second = c.post("/api/agent/email/draft/send",
                        json={"id": "m1", "confirm": True}, headers=h)
        assert second.status_code == 409
        assert "már küldtünk választ" in second.json()["detail"]
        assert [call[0] for call in gmail_send_calls].count("send") == 1
    finally:
        mail_agent._sessions.pop(sid, None)


def test_sent_message_carries_no_ai_draft_notice(gmail_send_calls):
    """The notice is for the reader of the page, not for the recipient: shipping
    'this is an AI draft' to a customer would be nonsense."""
    sid, h = _session_ready_to_save()
    mail_agent._sessions[sid]["drafts"]["m1:hivatalos"] = {
        "tone": "hivatalos", "targy": "Árajánlat",
        "valasz": f"Kedves A!\n\nKöszönjük.\n\n{server.AI_NOTICE}",
    }
    try:
        c.post("/api/agent/email/draft/send", json={"id": "m1", "confirm": True}, headers=h)
        msg = message_from_bytes(
            base64.urlsafe_b64decode(gmail_send_calls[0][2]["message"]["raw"]),
            policy=policy.default,
        )
        content = msg.get_content()
        assert server.AI_NOTICE not in content
        assert "Köszönjük" in content
    finally:
        mail_agent._sessions.pop(sid, None)


def test_saved_draft_carries_no_ai_draft_notice_either(gmail_calls):
    """A saved draft is one click from going out, so it must not carry it either."""
    sid, h = _session_ready_to_save()
    mail_agent._sessions[sid]["drafts"]["m1:hivatalos"] = {
        "tone": "hivatalos", "targy": "Árajánlat",
        "valasz": f"Kedves A!\n\nKöszönjük.\n\n{server.AI_NOTICE}",
    }
    try:
        c.post("/api/agent/email/draft/save", json={"id": "m1", "confirm": True}, headers=h)
        msg = message_from_bytes(
            base64.urlsafe_b64decode(gmail_calls[0][2]["message"]["raw"]),
            policy=policy.default,
        )
        assert server.AI_NOTICE not in msg.get_content()
    finally:
        mail_agent._sessions.pop(sid, None)


def test_send_failure_is_a_502_and_does_not_mark_it_sent(monkeypatch):
    class Boom:
        def users(self):
            raise RuntimeError("gmail said no")
    monkeypatch.setattr(mail_agent, "build", lambda *a, **k: Boom())
    monkeypatch.setattr(mail_agent, "SafeGmailProxy", lambda t, allow_send=False: t)
    sid, h = _session_ready_to_save()
    try:
        r = c.post("/api/agent/email/draft/send",
                   json={"id": "m1", "confirm": True}, headers=h)
        assert r.status_code == 502
        assert "Vázlatok" in r.json()["detail"], "a failed send should point somewhere useful"
        assert mail_agent._sessions[sid]["sent"] == {}, "a failed send must not block a retry"
    finally:
        mail_agent._sessions.pop(sid, None)


# ---------------- the run itself ----------------
def test_reads_fifty_emails():
    assert mail_agent.MAX_EMAILS == 50
    src = open(BACKEND / "mail_agent.py").read()
    assert "maxResults=MAX_EMAILS" in src, "the Gmail query must follow the constant"


def _run_session(ids):
    from datetime import datetime, timezone
    sid = "run-test"
    mail_agent._sessions[sid] = {
        "email": "teszt@example.com", "creds": None, "analyses": [],
        "can_draft": False, "drafts": {}, "saved": {}, "sent": {},
        "state": mail_agent._new_state(), "created_at": datetime.now(timezone.utc),
    }
    return sid


class RunFakeService:
    """Gmail stub for a whole run: lists ids, returns a message per id."""
    def __init__(self, ids, tracker):
        self._ids, self._t = ids, tracker

    def users(self):
        return self

    def messages(self):
        return self

    def list(self, userId, maxResults, q):
        self._t["max_results"] = maxResults
        return _Exec({"messages": [{"id": i} for i in self._ids[:maxResults]]})

    def get(self, userId, id, format):
        return _Exec({
            "id": id, "threadId": f"t{id}", "snippet": "s",
            "payload": {"headers": [{"name": "From", "value": f"{id}@x.hu"},
                                    {"name": "Subject", "value": f"Tárgy {id}"}],
                        "mimeType": "text/plain", "body": {}},
        })


def _install_run_stubs(monkeypatch, ids, classify):
    tracker = {"max_results": None, "peak": 0, "live": 0}
    monkeypatch.setattr(mail_agent, "build", lambda *a, **k: RunFakeService(ids, tracker))
    monkeypatch.setattr(mail_agent, "SafeGmailProxy", lambda t, allow_send=False: t)

    async def wrapped(email):
        tracker["live"] += 1
        tracker["peak"] = max(tracker["peak"], tracker["live"])
        try:
            return await classify(email)
        finally:
            tracker["live"] -= 1

    monkeypatch.setattr(server, "classify_one", wrapped)
    return tracker


def test_a_full_run_classifies_every_email(monkeypatch):
    import asyncio
    ids = [f"m{i}" for i in range(50)]

    async def classify(email):
        await asyncio.sleep(0)
        return {"category": "Egyéb", "urgency": 1, "needs_reply": "nem",
                "urgency_reason": "", "deadline": "", "summary": "", "next_step": ""}

    tracker = _install_run_stubs(monkeypatch, ids, classify)
    sid = _run_session(ids)
    try:
        asyncio.run(mail_agent.run_agent(sid))
        sess = mail_agent._sessions[sid]
        assert tracker["max_results"] == 50
        assert sess["state"]["total"] == 50
        assert sess["state"]["done"] == 50
        assert sess["state"]["errors"] == 0
        assert len(sess["analyses"]) == 50
        assert sess["state"]["message"] == "Kész"
        assert sess["state"]["running"] is False
    finally:
        mail_agent._sessions.pop(sid, None)


def test_the_run_is_concurrent_but_bounded(monkeypatch):
    """Sequentially this would be 50 round trips end to end. Concurrency is the
    point — but unbounded it would hammer Gmail and OpenAI at once."""
    import asyncio
    ids = [f"m{i}" for i in range(50)]

    async def classify(email):
        await asyncio.sleep(0.01)  # long enough for overlap to show
        return {"category": "Egyéb", "urgency": 1, "needs_reply": "nem",
                "urgency_reason": "", "deadline": "", "summary": "", "next_step": ""}

    tracker = _install_run_stubs(monkeypatch, ids, classify)
    sid = _run_session(ids)
    try:
        asyncio.run(mail_agent.run_agent(sid))
        assert tracker["peak"] > 1, "the run never overlapped — it is still sequential"
        assert tracker["peak"] <= mail_agent.RUN_CONCURRENCY, tracker["peak"]
    finally:
        mail_agent._sessions.pop(sid, None)


def test_one_bad_email_does_not_stop_the_rest(monkeypatch):
    import asyncio
    ids = [f"m{i}" for i in range(10)]

    async def classify(email):
        if email["sender"].startswith("m3"):
            raise RuntimeError("boom")
        return {"category": "Egyéb", "urgency": 1, "needs_reply": "nem",
                "urgency_reason": "", "deadline": "", "summary": "", "next_step": ""}

    _install_run_stubs(monkeypatch, ids, classify)
    sid = _run_session(ids)
    try:
        asyncio.run(mail_agent.run_agent(sid))
        sess = mail_agent._sessions[sid]
        assert sess["state"]["errors"] == 1
        assert len(sess["analyses"]) == 9
        assert sess["state"]["message"] == "Kész"
    finally:
        mail_agent._sessions.pop(sid, None)


def test_hitting_the_budget_halts_the_run_once(monkeypatch):
    """Fifty emails must not produce fifty identical budget failures; the run
    stops and says why, and the count of attempts stays bounded."""
    import asyncio
    from fastapi import HTTPException
    ids = [f"m{i}" for i in range(50)]
    attempts = {"n": 0}

    async def classify(email):
        attempts["n"] += 1
        if attempts["n"] > 3:
            raise HTTPException(status_code=429, detail="Az agent mára elérte a napi keretét.")
        return {"category": "Egyéb", "urgency": 1, "needs_reply": "nem",
                "urgency_reason": "", "deadline": "", "summary": "", "next_step": ""}

    _install_run_stubs(monkeypatch, ids, classify)
    sid = _run_session(ids)
    try:
        asyncio.run(mail_agent.run_agent(sid))
        sess = mail_agent._sessions[sid]
        assert sess["state"]["message"] == "Az agent mára elérte a napi keretét."
        assert sess["state"]["errors"] == 0, "a budget stop is not a per-email error"
        # at most one extra batch gets through before the halt is seen
        assert attempts["n"] <= 3 + mail_agent.RUN_CONCURRENCY, attempts["n"]
        assert sess["state"]["running"] is False
    finally:
        mail_agent._sessions.pop(sid, None)


def test_a_visitor_leaving_mid_run_stops_the_work(monkeypatch):
    import asyncio
    ids = [f"m{i}" for i in range(50)]
    sid = _run_session(ids)

    async def classify(email):
        # drop the session as soon as the first email is classified
        mail_agent._sessions.pop(sid, None)
        return {"category": "Egyéb", "urgency": 1, "needs_reply": "nem",
                "urgency_reason": "", "deadline": "", "summary": "", "next_step": ""}

    tracker = _install_run_stubs(monkeypatch, ids, classify)
    # held directly: the run removes it from _sessions, and the point is what it
    # stopped doing, not the size of a global dict other tests also write to
    sess = mail_agent._sessions[sid]
    try:
        asyncio.run(mail_agent.run_agent(sid))
        assert tracker["live"] == 0, "work was still in flight when the run returned"
        assert sid not in mail_agent._sessions
        assert len(sess["analyses"]) < len(ids), "the run kept going after the visitor left"
        assert sess["state"]["running"] is False
    finally:
        mail_agent._sessions.pop(sid, None)


def test_cost_knobs_are_env_tunable(monkeypatch):
    """A 50-email run costs ~50x a single call, so the ceiling has to be
    changeable on the service without a code deploy."""
    f = server._env_float
    monkeypatch.setenv("X_CEIL", "12.5")
    assert f("X_CEIL", 4.0) == 12.5
    monkeypatch.setenv("X_CEIL", "")
    assert f("X_CEIL", 4.0) == 4.0
    monkeypatch.setenv("X_CEIL", "nem szám")
    assert f("X_CEIL", 4.0) == 4.0, "a typo must not take the API down on boot"
    monkeypatch.delenv("X_CEIL", raising=False)
    assert f("X_CEIL", 4.0) == 4.0


def test_config_check_names_the_gap_without_leaking_values(monkeypatch, caplog):
    """A missing setting must be diagnosable from the deploy log — but a client
    secret must never appear in one."""
    import logging
    monkeypatch.setattr(mail_agent, "GOOGLE_CLIENT_ID", "")
    monkeypatch.setattr(mail_agent, "GOOGLE_CLIENT_SECRET", "titkos-ertek-123")
    monkeypatch.setattr(mail_agent, "GMAIL_REDIRECT_URI", "https://x/cb")
    monkeypatch.setattr(mail_agent, "SITE_URL", "https://x")
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")  # set but empty
    with caplog.at_level(logging.WARNING, logger="mail_agent"):
        mail_agent._log_agent_config()
    text = caplog.text
    assert "GOOGLE_CLIENT_ID" in text
    assert "set but empty" in text
    assert "GOOGLE_CLIENT_SECRET" not in text, "a present setting should not be reported missing"
    assert "titkos-ertek-123" not in text, "a secret value reached the log"


def test_config_values_are_stripped():
    """A trailing newline in a dashboard variable is invisible and would break the
    redirect URI match at Google rather than here."""
    src = open(BACKEND / "mail_agent.py").read()
    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "AGENT_REDIRECT_URI", "FRONTEND_URL"):
        line = next(l for l in src.splitlines() if f'os.environ.get("{name}", "")' in l)
        assert line.rstrip().endswith('.strip()'), name


# ---------------- message body extraction ----------------
def _b64(text):
    """Gmail-style base64url, padding stripped the way Gmail often sends it."""
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _part(mime, text=None, parts=None, attachment=False):
    body = {}
    if text is not None:
        body["data"] = _b64(text)
        body["size"] = len(text)
    if attachment:
        body = {"attachmentId": "att1", "size": 999}
    p = {"mimeType": mime, "body": body}
    if parts:
        p["parts"] = parts
    return p


BODY_TEXT = "Azonnali felszólítás!\n\nTelefonszámla befizetés!"


def test_plain_text_body_is_read():
    text, _ = mail_agent._body(_part("text/plain", BODY_TEXT))
    assert text == BODY_TEXT


def test_unpadded_base64_is_still_decoded():
    """Gmail routinely omits the '=' padding. Strict decoding raised, which took
    the whole email out of the run as an unexplained error."""
    # both padding lengths Gmail can drop: one '=' and two
    for original in ("Azonnali felszolitas", "Telefonszamla"):
        data = _b64(original)
        assert len(data) % 4 != 0, f"{original!r} does not exercise padding"
        text, _ = mail_agent._body({"mimeType": "text/plain", "body": {"data": data}})
        assert text == original


def test_mime_type_with_parameters_is_not_missed():
    """'text/plain; charset=UTF-8' is valid and used to fail an equality check,
    losing the body silently."""
    text, _ = mail_agent._body(_part('text/plain; charset="UTF-8"', BODY_TEXT))
    assert text == BODY_TEXT
    text, _ = mail_agent._body(_part("TEXT/PLAIN", BODY_TEXT))
    assert text == BODY_TEXT


def test_multipart_alternative_prefers_plain_text():
    payload = _part("multipart/alternative", parts=[
        _part("text/plain", BODY_TEXT),
        _part("text/html", f"<p>{BODY_TEXT}</p>"),
    ])
    text, _ = mail_agent._body(payload)
    assert text == BODY_TEXT


def test_html_only_message_falls_back_to_stripped_html():
    payload = _part("multipart/alternative", parts=[
        _part("text/html", "<div>Azonnali<br>felszólítás</div><script>x=1</script>"),
    ])
    text, _ = mail_agent._body(payload)
    assert "Azonnali" in text and "felszólítás" in text
    assert "<div>" not in text
    assert "x=1" not in text, "script contents must not land in the body"


def test_nested_multipart_is_walked():
    payload = _part("multipart/mixed", parts=[
        _part("multipart/related", parts=[
            _part("multipart/alternative", parts=[_part("text/plain", BODY_TEXT)]),
        ]),
        _part("application/pdf", attachment=True),
    ])
    text, _ = mail_agent._body(payload)
    assert text == BODY_TEXT


def test_unknown_text_subtype_is_a_last_resort():
    payload = _part("multipart/alternative", parts=[_part("text/x-amp-html", "<p>Szia</p>")])
    text, _ = mail_agent._body(payload)
    assert "Szia" in text


def test_a_broken_part_yields_an_empty_body_not_a_lost_email():
    payload = {"mimeType": "text/plain", "body": {"data": "!!! nem base64 !!!"}}
    text, _ = mail_agent._body(payload)
    assert text == ""  # and crucially: no exception


def test_parse_survives_a_body_it_cannot_read():
    """_parse raising would drop the email from the run entirely."""
    msg = {"id": "m1", "threadId": "t1", "snippet": "elonezet",
           "payload": {"mimeType": "text/plain", "body": {"data": "***"},
                       "headers": [{"name": "From", "value": "a@b.hu"}]}}
    out = mail_agent._parse(msg)
    assert out["body"] == ""
    assert out["snippet"] == "elonezet"
    assert out["sender"] == "a@b.hu"


def test_empty_body_and_snippet_logs_the_payload_shape(caplog):
    """The case that sent me looking in the wrong place: no way to tell a
    genuinely empty email from one we failed to parse."""
    import logging
    msg = {"id": "m9", "snippet": "  ", "payload": _part("multipart/alternative", parts=[
        _part("text/plain", attachment=True),
        _part("text/html", attachment=True),
    ])}
    with caplog.at_level(logging.WARNING, logger="mail_agent"):
        out = mail_agent._parse(msg)
    assert out["body"] == ""
    assert "m9" in caplog.text
    assert "multipart/alternative" in caplog.text
    assert "attachment" in caplog.text, "the shape must say why there was no text"


def test_the_shape_log_never_carries_content(caplog):
    import logging
    secret = "SZIGORUAN-TITKOS-TARTALOM"
    msg = {"id": "m10", "snippet": "", "payload": _part("text/plain", secret)}
    with caplog.at_level(logging.WARNING, logger="mail_agent"):
        mail_agent._parse(msg)
    assert secret not in caplog.text
