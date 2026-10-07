"""Az értékesítő hálózat nélkül: modell, Gmail és letöltés csonkkal."""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import mailer  # noqa: E402
import pipeline  # noqa: E402
import verify  # noqa: E402
from playbook import OPT_OUT  # noqa: E402
from store import Store  # noqa: E402

PAGE = """<html><body><p>Asztalfoglalás kizárólag telefonon: +36 1 234 5678.</p>
<footer>Írjon nekünk: <a href="mailto:info@kertbisztro.hu">info@kertbisztro.hu</a></footer></body></html>"""

CAND = {"company": "Kert Bisztró", "town": "Szeged", "country": "HU", "website": "https://kertbisztro.hu",
        "email": "info@kertbisztro.hu", "email_url": "https://kertbisztro.hu/kapcsolat",
        "observation": "Asztalfoglalás kizárólag telefonon", "observation_url": "https://kertbisztro.hu/kapcsolat",
        "pain": "phone", "sector": "hospitality", "signal": "notice", "score": 80}


class FakeLLM:
    def __init__(self, cands):
        self.cands = cands
        self.calls = 0

    def research(self, country, count, exclude, focus=""):
        self.focus = focus
        self.calls += 1
        return self.cands if self.calls == 1 else []

    def compose(self, lead):
        return {"subject": "Esti foglalások telefonon",
                "body": "Jó napot!\n\nAz oldalukon azt írják, hogy asztalt csak telefonon foglalnak.\n\n"
                        "Hutkai Milán · AXIMBRA · aximbra.hu\n\n" + OPT_OUT["hu"]}

    def critique(self, lead, subject, body):
        return {"score": 7, "issues": ["túl általános kérdés"], "subject": subject,
                "body": body.replace("foglalnak.", "foglalnak.\n\nPéntek este ki veszi fel?")}

    def classify(self, original, reply):
        return "no" if "nem" in reply.lower() else "interested"

    def draft_reply(self, original, reply, slots, lang):
        return "Köszönöm! Mikor beszélhetnénk 20 percet? " + " / ".join(slots)


def FAKE_SLOTS(company, guest):
    return {"calendar": True, "slots": [{"iso": "2026-09-29T10:00:00+02:00", "label": "szeptember 29. (kedd) 10:00",
                                         "link": "https://calendar.google.com/x"}]}


class FakeMailbox:
    contacted: set = set()
    inbox: list = []
    bounces: list = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def close(self):
        pass

    def ever_contacted(self, address, domain):
        return address in self.contacted

    def messages_from(self, address, since_days=30):
        return [m for m in self.inbox if m["from"] == address or m["from"].endswith("@" + address)]

    def bounces_since(self, since_days=14):
        return self.bounces


class FakeMailer:
    AuthError = mailer.AuthError
    MailError = mailer.MailError

    def __init__(self, fail=None):
        self.sent = []
        self.fail = fail

    def build_message(self, to, subject, body, in_reply_to=None):
        return {"to": to, "subject": subject, "body": body, "in_reply_to": in_reply_to}

    def send(self, msg):
        if self.fail:
            raise self.fail
        self.sent.append(msg)
        return f"<m{len(self.sent)}@gmail.com>"


@pytest.fixture
def store(tmp_path):
    FakeMailbox.contacted, FakeMailbox.inbox, FakeMailbox.bounces = set(), [], []
    return Store(str(tmp_path / "s.db"))


def run(store, cands, fetch=lambda url: PAGE):
    log = pipeline.RunLog()
    pipeline.research_run(store, {"HU": 1}, log, llm=FakeLLM(cands), fetch=fetch, mailbox_factory=FakeMailbox)
    return log


# ---- ellenőrzés -------------------------------------------------------------

def test_verified_candidate_becomes_draft(store):
    log = run(store, [dict(CAND)])
    assert log.added == 1
    lead = store.list("draft")[0]
    assert lead["email"] == "info@kertbisztro.hu" and lead["lang"] == "hu"
    assert OPT_OUT["hu"] in lead["body"]


def test_email_not_on_page_is_rejected(store):
    log = run(store, [dict(CAND, email="foglalas@kertbisztro.hu")])
    assert log.added == 0 and "nincs rajta" in "\n".join(log.lines)


def test_invented_quote_is_rejected(store):
    log = run(store, [dict(CAND, observation="Hétvégén senki nem veszi fel a telefont, sajnos")])
    assert log.added == 0


def test_austrian_domain_rejected_even_if_model_says_hungary(store):
    log = run(store, [dict(CAND, email="office@wirt.at", website="https://wirt.at")])
    assert log.added == 0 and "osztrák" in "\n".join(log.lines)


def test_country_outside_targets_rejected(store):
    with pytest.raises(ValueError):
        pipeline.research_run(store, {"DE": 2}, pipeline.RunLog(), llm=FakeLLM([]), mailbox_factory=FakeMailbox)


def test_already_contacted_in_gmail_is_skipped_and_blocked(store):
    FakeMailbox.contacted = {"info@kertbisztro.hu"}
    log = run(store, [dict(CAND)])
    assert log.added == 0
    assert store.is_blocked("info@kertbisztro.hu")


def test_same_company_twice_only_once(store):
    run(store, [dict(CAND)])
    log = run(store, [dict(CAND, email="hello@kertbisztro.hu")])
    assert log.added == 0 and len(store.list()) == 1


def test_blocked_domain_skipped(store):
    store.block("kertbisztro.hu", "kézzel")
    assert run(store, [dict(CAND)]).added == 0


def test_quote_match_tolerates_small_rewording():
    page = "Kérjük, vegye figyelembe: az aznapi asztalfoglalás kizárólag telefonon lehetséges nálunk."
    assert verify.quote_on_page("Aznapi asztalfoglalás kizárólag telefonon lehetséges.", page)
    assert not verify.quote_on_page("Online foglalás nincs, és a telefon sem működik.", page)


def test_obfuscated_email_found():
    assert verify.email_on_page("info@ceg.hu", "Írjon: info [at] ceg [dot] hu")


def test_letter_checks_flag_price_and_link():
    w = verify.check_letter({"lang": "hu", "subject": "Kérdés", "body": "Ára 150 000 Ft, https://x.hu aximbra.hu"})
    assert any("ár" in x for x in w) and any("link" in x for x in w) and any("leiratkozó" in x for x in w)


# ---- küldés -----------------------------------------------------------------

def test_send_once_only(store):
    run(store, [dict(CAND)])
    lid = store.list("draft")[0]["id"]
    m = FakeMailer()
    assert pipeline.send_one(store, lid, mailer=m)[0] is True
    ok, why = pipeline.send_one(store, lid, mailer=m)
    assert ok is False and len(m.sent) == 1


def test_failed_send_can_be_retried(store):
    run(store, [dict(CAND)])
    lid = store.list("draft")[0]["id"]
    ok, _ = pipeline.send_one(store, lid, mailer=FakeMailer(fail=mailer.MailError("hálózat")))
    assert ok is False and store.get(lid)["status"] == "failed"
    assert pipeline.send_one(store, lid, mailer=FakeMailer())[0] is True


def test_auth_error_stops_batch(store):
    run(store, [dict(CAND)])
    lid = store.list("draft")[0]["id"]
    log = pipeline.send_many(store, [lid, lid], pipeline.RunLog(),
                             mailer=FakeMailer(fail=mailer.AuthError("rossz jelszó")), sleep=lambda s: None)
    assert "Leálltam" in "\n".join(log.lines)


def test_daily_cap(store, monkeypatch):
    monkeypatch.setattr(pipeline, "DAILY_CAP", 0)
    run(store, [dict(CAND)])
    ok, why = pipeline.send_one(store, store.list("draft")[0]["id"], mailer=FakeMailer())
    assert ok is False and "napi" in why


def test_blocked_after_draft_is_not_sent(store):
    run(store, [dict(CAND)])
    lid = store.list("draft")[0]["id"]
    store.block("info@kertbisztro.hu", "nem kér")
    m = FakeMailer()
    assert pipeline.send_one(store, lid, mailer=m)[0] is False and not m.sent


# ---- utánkövetés és válaszok ---------------------------------------------------

def _sent(store):
    run(store, [dict(CAND)])
    lid = store.list("draft")[0]["id"]
    pipeline.send_one(store, lid, mailer=FakeMailer())
    return lid


def test_followup_after_five_workdays_only_once(store):
    lid = _sent(store)
    with store._conn() as c:
        c.execute("UPDATE leads SET sent_at = ? WHERE id = ?", ("2026-09-21T08:00:00+00:00", lid))  # hétfő
    assert pipeline.prepare_followups(store, datetime(2026, 9, 25, 9, tzinfo=timezone.utc)) == 0  # 4 munkanap
    assert pipeline.prepare_followups(store, datetime(2026, 9, 28, 9, tzinfo=timezone.utc)) == 1
    m = FakeMailer()
    assert pipeline.send_followup(store, lid, mailer=m)[0] is True
    assert m.sent[0]["in_reply_to"] == "<m1@gmail.com>" and m.sent[0]["subject"].startswith("Re: ")
    assert pipeline.send_followup(store, lid, mailer=m)[0] is False
    assert pipeline.prepare_followups(store, datetime(2026, 10, 30, tzinfo=timezone.utc)) == 0


def test_no_reply_blocks_and_cancels_followup(store):
    lid = _sent(store)
    FakeMailbox.inbox = [{"from": "info@kertbisztro.hu", "text": "Köszönjük, nem kérjük.", "in_reply_to": "",
                          "references": "", "message_id": "<r1>", "subject": "Re", "date": ""}]
    pipeline.scan_replies(store, pipeline.RunLog(), llm=FakeLLM([]), mailbox_factory=FakeMailbox, slots_fn=FAKE_SLOTS)
    lead = store.get(lid)
    assert lead["reply_kind"] == "no" and store.is_blocked("info@kertbisztro.hu")
    assert pipeline.prepare_followups(store, datetime(2027, 1, 1, tzinfo=timezone.utc)) == 0


def test_interested_reply_gets_suggestion(store):
    lid = _sent(store)
    FakeMailbox.inbox = [{"from": "info@kertbisztro.hu", "text": "Érdekel, mennyibe kerül?\n\n> régi levél",
                          "in_reply_to": "", "references": "", "message_id": "<r2>", "subject": "Re", "date": ""}]
    pipeline.scan_replies(store, pipeline.RunLog(), llm=FakeLLM([]), mailbox_factory=FakeMailbox, slots_fn=FAKE_SLOTS)
    lead = store.get(lid)
    assert lead["reply_kind"] == "interested" and "20 percet" in lead["reply_suggestion"]
    assert "szeptember 29. (kedd) 10:00" in lead["reply_suggestion"] and "calendar.google.com" in lead["slots"]
    assert "régi levél" not in lead["reply_text"]


def test_bounce_blocks(store):
    lid = _sent(store)
    FakeMailbox.bounces = [{"from": "mailer-daemon@googlemail.com", "text": "Address not found: info@kertbisztro.hu"}]
    pipeline.scan_replies(store, pipeline.RunLog(), llm=FakeLLM([]), mailbox_factory=FakeMailbox, slots_fn=FAKE_SLOTS)
    assert store.get(lid)["reply_kind"] == "bounce" and store.is_blocked("info@kertbisztro.hu")


def test_strip_quoted_hungarian_gmail():
    t = "Igen, érdekel.\n\nHutkai Milán <x@gmail.com> ezt írta (időpont: 2026. szept. 28.):\n> régi"
    assert mailer.strip_quoted(t) == "Igen, érdekel."


# ---- API ----------------------------------------------------------------------

def test_api_requires_password(tmp_path, monkeypatch):
    monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "api.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", "helyes-jelszo-123")
    import importlib
    import store as store_mod
    importlib.reload(store_mod)
    import app as app_mod
    importlib.reload(app_mod)
    from fastapi.testclient import TestClient
    c = TestClient(app_mod.app)
    assert c.get("/health").status_code == 200
    assert c.get("/api/state").status_code == 401
    assert c.get("/api/state", auth=("x", "rossz")).status_code == 401
    r = c.get("/api/state", auth=("x", "helyes-jelszo-123"))
    assert r.status_code == 200 and r.json()["cap"] == pipeline.DAILY_CAP
    assert c.post("/api/research", json={"plan": {"AT": 3}}, auth=("x", "helyes-jelszo-123")).status_code == 400
    # Hobby csomagon nincs SMTP: a szerver nem küld, csak ha külön bekapcsolják.
    monkeypatch.delenv("SMTP_ENABLED", raising=False)
    assert c.post("/api/send", json={"ids": [1]}, auth=("x", "helyes-jelszo-123")).status_code == 409


def test_manual_send_marks_sent_once_and_enables_followup(store):
    run(store, [dict(CAND)])
    lid = store.list("draft")[0]["id"]
    assert store.mark_sent_manual(lid) is True
    assert store.mark_sent_manual(lid) is False
    with store._conn() as c:
        c.execute("UPDATE leads SET sent_at = ? WHERE id = ?", ("2026-09-21T08:00:00+00:00", lid))
    assert pipeline.prepare_followups(store, datetime(2026, 9, 28, 9, tzinfo=timezone.utc)) == 1
    assert store.followup_sent_manual(lid) is True
    assert store.followup_sent_manual(lid) is False


def test_weak_fit_rejected(store):
    log = run(store, [dict(CAND, score=20)])
    assert log.added == 0 and "gyenge" in "\n".join(log.lines)


def test_critique_rewrite_applied_and_recorded(store):
    run(store, [dict(CAND)])
    lead = store.list("draft")[0]
    assert "Péntek este" in lead["body"] and lead["critique"].startswith("7/10")
    assert lead["sector"] == "hospitality" and lead["score"] == 80


def test_drafts_sorted_by_score(store):
    run(store, [dict(CAND, score=75)])
    run(store, [dict(CAND, company="Másik", email="info@masik.hu", website="https://masik.hu", score=95)],
        fetch=lambda url: PAGE.replace("kertbisztro", "masik"))
    assert [l["score"] for l in store.list("draft")] == [95, 75]


def test_learning_prefers_sector_with_replies(store):
    for i, (sector, kind) in enumerate([("logistics", "interested")] * 5 + [("energy", "none")] * 5
                                       + [("restaurant", "interested")] * 6):
        lid = store.add_lead(dict(CAND, email=f"a{i}@c{i}.hu", website=f"https://c{i}.hu", lang="hu",
                                  sector=sector))
        store.mark_sent_manual(lid)
        if kind != "none":
            store.set_reply(lid, kind, "érdekel")
    assert store.best_sectors()[0] == "logistics" and "restaurant" not in store.best_sectors()
    llm = FakeLLM([])
    pipeline.research_run(store, {"HU": 1}, pipeline.RunLog(), llm=llm, mailbox_factory=FakeMailbox)
    assert llm.focus.startswith("logistics")


def test_extract_json_prefers_outer_object():
    import llm
    assert llm.extract_json('Íme: {"score": 7, "issues": ["x"], "body": "b"}')["score"] == 7
    assert llm.extract_json('```json\n[{"a": 1}]\n```') == [{"a": 1}]


ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:1
DTSTART;TZID=Europe/Budapest:20260929T093000
DTEND;TZID=Europe/Budapest:20260929T110000
SUMMARY:Egyetem
END:VEVENT
BEGIN:VEVENT
UID:2
DTSTART;VALUE=DATE:20260930
DTEND;VALUE=DATE:20261001
SUMMARY:Egész nap
END:VEVENT
END:VCALENDAR
"""


def test_free_slots_avoid_busy_and_all_day_and_spread_days():
    import calendar_slots as cs
    now = datetime(2026, 9, 28, 20, 0, tzinfo=cs.TZ)  # hétfő este
    slots = cs.free_slots(now=now, ics_text=ICS)
    assert len(slots) == 3 and len({s.date() for s in slots}) == 3
    assert slots[0].date().isoformat() == "2026-09-29" and slots[0].hour >= 11  # a 9:30–11 foglalt
    assert all(s.date().isoformat() != "2026-09-30" for s in slots)            # egész napos
    assert all(s.weekday() < 5 for s in slots)


def test_calendar_link_invites_guest():
    import calendar_slots as cs
    link = cs.calendar_link(datetime(2026, 9, 29, 14, 0, tzinfo=cs.TZ), "Kert Bisztró", "info@kertbisztro.hu")
    assert "action=TEMPLATE" in link and "add=info%40kertbisztro.hu" in link and "20260929T120000Z" in link


def test_two_calendars_both_block():
    import calendar_slots as cs
    other = ICS.replace("20260929T093000", "20260929T133000").replace("20260929T110000", "20260929T160000")
    now = datetime(2026, 9, 28, 20, 0, tzinfo=cs.TZ)
    slots = cs.free_slots(now=now, ics_texts=[ICS, other])
    assert all(s.date().isoformat() != "2026-09-29" for s in slots)  # kedd délelőtt és délután is foglalt


def test_calendar_urls_split(monkeypatch):
    import calendar_slots as cs
    monkeypatch.setenv("CALENDAR_ICS_URL", "https://a/x.ics, webcal://b/y.ics  nemurl")
    assert cs.calendar_urls() == ["https://a/x.ics", "webcal://b/y.ics"]


# ---- Gmail API-s küldés ----------------------------------------------------------

@pytest.fixture
def gapi(monkeypatch, store):
    import gmail_api
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "sec")
    monkeypatch.setenv("OAUTH_REDIRECT_URI", "https://x/oauth/callback")
    monkeypatch.setenv("SALES_TOKEN_KEY", "k" * 40)
    monkeypatch.setenv("COMPOSE_ACCOUNT", "aximbra@gmail.com")
    gmail_api._cache.update(token=None, exp=0.0)
    return gmail_api


def _idtok(email):
    import base64, json as _j
    p = base64.urlsafe_b64encode(_j.dumps({"email": email}).encode()).decode().rstrip("=")
    return f"h.{p}.s"


class _Resp:
    def __init__(self, code, data):
        self.status_code, self._d = code, data

    def json(self):
        return self._d


def test_oauth_state_signed_and_expires(gapi, monkeypatch):
    url = gapi.auth_url()
    state = dict(p.split("=", 1) for p in url.split("?", 1)[1].split("&"))["state"]
    assert gapi.state_ok(state.replace("%2E", "."))
    assert not gapi.state_ok("123.abc")
    import time as _t
    monkeypatch.setattr(_t, "time", lambda: 10**10)
    assert not gapi.state_ok(state.replace("%2E", "."))


def test_exchange_rejects_other_account(gapi, store, monkeypatch):
    monkeypatch.setattr(gapi.httpx, "post", lambda *a, **k: _Resp(200, {
        "id_token": _idtok("valaki@gmail.com"), "refresh_token": "r", "scope": "gmail.send", "access_token": "a"}))
    with pytest.raises(mailer.AuthError):
        gapi.exchange("code", store)
    assert not gapi.connected(store)


def test_exchange_then_send_through_api(gapi, store, monkeypatch):
    calls = []

    def post(url, **k):
        calls.append(url)
        if url == gapi.TOKEN_URL:
            return _Resp(200, {"id_token": _idtok("aximbra@gmail.com"), "refresh_token": "r",
                               "scope": "openid email https://www.googleapis.com/auth/gmail.send",
                               "access_token": "a", "expires_in": 3600})
        assert k["headers"]["Authorization"] == "Bearer a" and k["json"]["raw"]
        return _Resp(200, {"id": "m1"})

    monkeypatch.setattr(gapi.httpx, "post", post)
    assert gapi.exchange("code", store) == "aximbra@gmail.com"
    assert gapi.connected(store)
    assert store.get_setting("gmail_refresh") != "r"  # titkosítva van

    class S:
        def available(self):
            return gapi.connected(store)

        def __call__(self, msg):
            return gapi.send(msg, store)

    mailer.set_api_sender(S())
    try:
        msg = mailer.build_message("info@kertbisztro.hu", "Tárgy", "Szöveg")
        assert msg["From"].endswith("<aximbra@gmail.com>")
        assert mailer.send(msg) == msg["Message-ID"]
        assert calls[-1] == gapi.SEND_URL
    finally:
        mailer.set_api_sender(None)


def test_revoked_grant_disconnects(gapi, store, monkeypatch):
    store.set_setting("gmail_refresh", gapi._fernet().encrypt(b"r").decode())
    monkeypatch.setattr(gapi.httpx, "post", lambda *a, **k: _Resp(400, {"error": "invalid_grant"}))
    with pytest.raises(mailer.AuthError):
        gapi.send(mailer.build_message("a@b.hu", "s", "b"), store)
    assert not gapi.connected(store)


def test_due_slot_twice_a_day(monkeypatch, tmp_path):
    monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "sch.db"))
    import importlib
    import app as app_mod
    importlib.reload(app_mod)
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Europe/Budapest")
    ts = ["10:00", "19:00"]
    done = set()
    assert app_mod.due_slot(datetime(2026, 9, 29, 9, 59, tzinfo=tz), ts, done) is None
    k = app_mod.due_slot(datetime(2026, 9, 29, 10, 5, tzinfo=tz), ts, done)
    assert k == "2026-09-29 10:00"
    done.add(k)
    assert app_mod.due_slot(datetime(2026, 9, 29, 10, 10, tzinfo=tz), ts, done) is None
    assert app_mod.due_slot(datetime(2026, 9, 29, 10, 45, tzinfo=tz), ts, set()) is None  # 30 perc után kihagyja
    assert app_mod.due_slot(datetime(2026, 9, 29, 19, 0, tzinfo=tz), ts, done) == "2026-09-29 19:00"
    monkeypatch.setenv("AUTO_TIMES", "19:00, 7:5, rossz")
    assert app_mod.auto_times() == ["07:05", "19:00"]


def test_round_sends_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "n.db"))
    monkeypatch.setenv("NOTIFY_TO", "milan@example.com")
    monkeypatch.setenv("GMAIL_USER", "aximbra@gmail.com")
    import importlib
    import app as app_mod
    importlib.reload(app_mod)
    sent = []
    monkeypatch.setattr(app_mod.mailer, "send", lambda msg: sent.append(msg) or "<id>")
    monkeypatch.setattr(app_mod.pipeline, "scan_replies", lambda store, log: log)

    def fake_research(store, plan, log):
        store.add_lead(dict(CAND, lang="hu"))
        return log
    monkeypatch.setattr(app_mod.pipeline, "research_run", fake_research)
    log = pipeline.RunLog()
    app_mod._morning(log)
    assert len(sent) == 1 and sent[0]["To"] == "milan@example.com"
    assert "1 új vázlat" in sent[0]["Subject"] and "Kert Bisztró" in sent[0].get_content()


def test_organizer_run_counts_only(monkeypatch, tmp_path):
    monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "o.db"))
    monkeypatch.setenv("NOTIFY_SECRET", "s" * 32)
    monkeypatch.setenv("NOTIFY_TO", "aximbra@gmail.com")
    monkeypatch.setenv("GMAIL_USER", "aximbra@gmail.com")
    import importlib
    import app as app_mod
    importlib.reload(app_mod)
    sent = []
    monkeypatch.setattr(app_mod.mailer, "send", lambda m: sent.append(m) or "<id>")
    from fastapi.testclient import TestClient
    c = TestClient(app_mod.app)
    body = {"counts": {"Ügyfél – kérdés": 3, "Spam / kéretlen": 2, "Titkos tárgy: fizetés": 9}, "urgent": 1}
    assert c.post("/internal/organizer-run", json=body).status_code == 403
    assert c.post("/internal/organizer-run", json=body, headers={"X-Notify-Secret": "rossz" * 8}).status_code == 403
    r = c.post("/internal/organizer-run", json=body, headers={"X-Notify-Secret": "s" * 32})
    assert r.status_code == 200 and len(sent) == 1
    text = sent[0].get_content()
    assert "Ügyfél – kérdés" in text and "Titkos tárgy" not in text and "5 új levél, 1 sürgős" in sent[0]["Subject"]


MIXED = {"lang": "sk", "subject": "Rezervácia – nie každý vie vždy zdvihnúť telefón", "body": (
    "Jó napot kívánok!\n\nNálatok az asztalfoglalás csak telefonon megy. Ha épp tele vagytok, vendégek meg "
    "folyamatosan csörögnek, előfordult már, hogy lemaradtak róluk?\n\nMám riešenie – AI recepčný príjme hovor, "
    "keď personál práve obsluhuje, a zapíše meno, počet osôb, čas a číslo.\n\nBolo by to pre vás zaujímavé?\n\n"
    "Milán Hutkai · AXIMBRA · aximbra.hu/sk")}


def test_mixed_language_letter_is_caught_and_blocked(store):
    assert verify.mixed_language(MIXED)
    assert any("VEGYES" in w for w in verify.check_letter(dict(MIXED, body=MIXED["body"] + "\n\n" + OPT_OUT["sk"])))
    lid = store.add_lead(dict(CAND, lang="sk", country="SK", subject=MIXED["subject"], body=MIXED["body"]))
    m = FakeMailer()
    ok, why = pipeline.send_one(store, lid, mailer=m)
    assert ok is False and "vegyes" in why and not m.sent


def test_pure_letters_pass():
    sk = dict(MIXED, body="Dobrý deň,\n\nna vašej stránke píšete, že rezervácie sú len telefonicky.\n\n"
                          "Kto zdvihne telefón v piatok večer, keď je plno?\n\nBolo by to pre vás zaujímavé?")
    assert not verify.mixed_language(sk)
    hu = {"lang": "hu", "subject": "Esti foglalások", "body": "Jó napot!\n\nAz oldalukon azt írják, hogy asztalt csak "
          "telefonon foglalnak.\n\nPéntek este ki veszi fel a telefont, amikor tele van a terem?"}
    assert not verify.mixed_language(hu)


def test_hungarian_business_abroad_gets_both_languages(store):
    llm = FakeLLM([dict(CAND, country="SK", email="info@kertbisztro.sk", website="https://kertbisztro.sk",
                        email_url="https://kertbisztro.sk", observation_url="https://kertbisztro.sk",
                        observation="Asztalfoglalás kizárólag telefonon")])
    seen = []

    def compose(lead):
        seen.append(lead["lang"])
        if lead["lang"] == "hu":
            return {"subject": "Esti foglalások", "body": "Jó napot!\n\nAz oldalukon azt írják, hogy asztalt csak "
                    "telefonon foglalnak, és ez nem mindig könnyű.\n\nMilán · AXIMBRA · aximbra.hu\n\n" + OPT_OUT["hu"]}
        return {"subject": "Večerné rezervácie", "body": "Dobrý deň,\n\nna vašej stránke píšete, že rezervácie sú "
                "len telefonicky a že to nie je vždy ľahké.\n\nMilán · AXIMBRA · aximbra.hu/sk\n\n" + OPT_OUT["sk"]}
    llm.compose = compose
    llm.critique = lambda lead, s, b: {"score": 9, "issues": [], "subject": s, "body": b}
    pipeline.research_run(store, {"SK": 1}, pipeline.RunLog(), llm=llm,
                          fetch=lambda url: PAGE.replace("kertbisztro.hu", "kertbisztro.sk"), mailbox_factory=FakeMailbox)
    lead = store.list("draft")[0]
    assert seen == ["hu", "sk"] and lead["lang"] == "sk" and lead["lang2"] == "hu"
    hu_part, sk_part = lead["body"].split(verify.SEPARATOR)
    assert "Jó napot" in hu_part and "Dobrý deň" in sk_part and lead["subject"] == "Esti foglalások / Večerné rezervácie"
    assert not verify.mixed_language(lead) and "VEGYES" not in (lead["warnings"] or "")


def test_stops_at_once_when_openai_credit_runs_out(store):
    class Broke(FakeLLM):
        def research(self, *a, **k):
            self.calls += 1
            raise RuntimeError("Error code: 429 - insufficient_quota")
    llm = Broke([])
    log = pipeline.research_run(store, {"HU": 3, "SK": 2}, pipeline.RunLog(), llm=llm, mailbox_factory=FakeMailbox)
    assert llm.calls == 1 and "OpenAI-egyenleg" in log.lines[-1]


def test_gemini_path_retries_minute_limit_and_stops_on_daily(monkeypatch):
    import llm
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    calls = []

    class R:
        def __init__(self, code, data=None, text=""):
            self.status_code, self._d, self.text = code, data, text

        def json(self):
            return self._d

    seq = [R(429, text="RATE_LIMIT per minute"), R(200, {"candidates": [{"content": {"parts": [{"text": '{"kind": "no"}'}]}}]})]
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: calls.append(k["json"]) or seq.pop(0))
    assert llm.provider() == "gemini" and llm.classify("a", "nem") == "no" and len(calls) == 2
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: R(429, text="GenerateRequestsPerDayPerProjectPerModel"))
    with pytest.raises(llm.LLMError, match="insufficient_quota"):
        llm.research("HU", 2, [])


# ---- tanácsadó ----

import advisor  # noqa: E402
import llm  # noqa: E402
import websearch  # noqa: E402


def test_urls_in_finds_links_and_bare_domains():
    got = websearch.urls_in("Nézd meg: https://pelda.hu/rolunk, és az aximbra.hu oldalt.")
    assert got == ["https://pelda.hu/rolunk", "https://aximbra.hu"]


def test_advisor_searches_reads_pages_and_saves_turns(store, monkeypatch):
    prompts = []

    def fake_ask(prompt, **kw):
        prompts.append(prompt)
        if len(prompts) == 1:
            return '{"queries": ["AI ügynökség bemutató videó"], "reason": "trend"}'
        return "**Lényeg:** 60 mp-es demó [1].\n# Cím\nKövetkező lépés: forgass."

    monkeypatch.setattr(llm, "_ask", fake_ask)
    searched = []
    monkeypatch.setattr(websearch, "search", lambda q, n=4: searched.append(q) or [
        {"title": "Cikk", "url": "https://cikk.hu", "text": "videós tippek"}])
    monkeypatch.setattr(websearch, "read_page", lambda u: {"title": u, "url": u, "text": "AXIMBRA oldal"})

    out = advisor.ask(store, "Videót akarok az aximbráról, ilyesmit: aximbra.hu")

    assert searched == ["AI ügynökség bemutató videó"]
    assert out["answer"].startswith("Lényeg: 60 mp")  # markdown nélkül
    assert "# " not in out["answer"]
    assert [s["url"] for s in out["sources"]] == ["https://aximbra.hu", "https://cikk.hu"]
    assert "videós tippek" in prompts[1] and "AXIMBRA oldal" in prompts[1]
    hist = store.advisor_history()
    assert [m["role"] for m in hist] == ["user", "assistant"]


def test_advisor_answers_without_search_when_planner_fails(store, monkeypatch):
    calls = []

    def fake_ask(prompt, **kw):
        calls.append(prompt)
        if len(calls) == 1:
            raise llm.LLMError("a modell nem adott értelmezhető JSON-t")
        return "Válasz."

    monkeypatch.setattr(llm, "_ask", fake_ask)
    monkeypatch.setattr(websearch, "search", lambda q, n=4: pytest.fail("nem kellett volna keresni"))
    assert advisor.ask(store, "Mi a SPIN módszer?")["answer"] == "Válasz."


def test_advisor_quota_error_saves_nothing(store, monkeypatch):
    def fake_ask(prompt, **kw):
        raise llm.LLMError("insufficient_quota: elfogyott")

    monkeypatch.setattr(llm, "_ask", fake_ask)
    with pytest.raises(llm.LLMError):
        advisor.ask(store, "Kérdés")
    assert store.advisor_history() == []


def test_web_search_falls_back_to_nothing_without_keys(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert websearch.search("bármi") == []


# ---- szabályellenőrzés és magától küldés ------------------------------------

CLEAN_BODY = ("Jó napot!\n\nAz oldalukon azt írják, hogy asztalt csak telefonon foglalnak. Ügyfeleik este is hívják.\n\n"
              "Hutkai Milán · AXIMBRA · aximbra.hu\n\n" + OPT_OUT["hu"])


def _lead(**kw):
    return {**CAND, "lang": "hu", "subject": "Esti foglalások telefonon", "body": CLEAN_BODY, **kw}


@pytest.mark.parametrize("bad,why", [
    ("Egyik ügyfelünknél bevált.", "ügyfélre"),
    ("A hívások 40%-át elveszítik.", "statisztik"),
    ("Háromszor gyorsabb válasz.", None),
    ("Kovács úrnak írok.", "munkatárs"),
    ("Tisztelt Nagy Anna!", "munkatárs"),
    ("Vážený pán Novák,", "munkatárs"),
    ("Ára 400 ezer Ft.", "ár"),
    ("Ára 1,2 millió forint.", "ár"),
    ("Cena od 900 €.", "ár"),
    ("Náš klient ušetril čas.", "ügyfélre"),
])
def test_rule_violations_catch_forbidden_content(bad, why):
    v = verify.rule_violations(_lead(body=bad + "\n\n" + CLEAN_BODY))
    if why:
        assert any(why in x for x in v), v


def test_rule_violations_clean_letter_and_their_customers_ok():
    assert verify.rule_violations(_lead()) == []
    assert verify.rule_violations(_lead(body="Tisztelt Hölgyem/Uram!\n\n" + CLEAN_BODY)) == []
    assert not verify._NAME_RE.search("Stimate Domn / Stimată Doamnă,")
    assert not verify._NAME_RE.search("Vážený pane / Vážená pani,")


def test_at_de_never_sent_even_by_button(store):
    lid = store.add_lead(_lead(email="office@wirt.at", website="https://wirt.at"))
    m = FakeMailer()
    ok, why = pipeline.send_one(store, lid, mailer=m)
    assert not ok and "osztrák" in why and not m.sent and store.get(lid)["status"] == "skipped"


def _decide(store, n, edited=0, skipped=0, score=85):
    """n döntés: ebből edited javítva, skipped kihagyva, a többi érintetlenül ki."""
    m = FakeMailer()
    for i in range(n):
        lid = store.add_lead(_lead(email=f"info@c{i}-{score}.hu", website=f"https://c{i}-{score}.hu", score=score))
        if i < skipped:
            store.skip(lid)
            continue
        if i < skipped + edited:
            store.edit(lid, "Más tárgy", CLEAN_BODY + " x")
        pipeline.send_one(store, lid, mailer=m)


def test_readiness_needs_sample_and_rate(store, monkeypatch):
    monkeypatch.setattr(pipeline, "DAILY_CAP", 10_000)
    _decide(store, 19)
    r = pipeline.readiness(store)
    assert not r["ready"] and r["decided"] == 19 and r["rate"] == 1.0
    _decide(store, 40, edited=8, score=90)
    r = pipeline.readiness(store)
    assert r["decided"] == 59 and r["edited"] == 8 and not r["ready"]  # 51/59 = 86% < 90%


def test_manual_gmail_sends_and_low_scores_dont_count(store, monkeypatch):
    monkeypatch.setattr(pipeline, "DAILY_CAP", 10_000)
    _decide(store, 10, score=75)
    lid = store.add_lead(_lead(email="info@kezi.hu", website="https://kezi.hu", score=95))
    store.mark_sent_manual(lid)
    assert pipeline.readiness(store)["decided"] == 0


def _ready_store(store, monkeypatch):
    monkeypatch.setattr(pipeline, "DAILY_CAP", 10_000)
    monkeypatch.setenv("AUTO_SEND_MIN_SAMPLE", "20")
    _decide(store, 20)
    store.set_setting("auto_send", "on")


WEEKDAY_10 = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)  # csütörtök


def test_auto_send_sends_only_clean_untouched_high_scores_within_cap(store, monkeypatch):
    _ready_store(store, monkeypatch)
    monkeypatch.setenv("AUTO_SEND_DAILY", "2")
    good = [store.add_lead(_lead(email=f"info@j{i}.hu", website=f"https://j{i}.hu", score=90 - i)) for i in range(3)]
    low = store.add_lead(_lead(email="info@low.hu", website="https://low.hu", score=75))
    dirty = store.add_lead(_lead(email="info@ref.hu", website="https://ref.hu", score=99,
                                 body="Egyik ügyfelünknél bevált.\n\n" + CLEAN_BODY))
    touched = store.add_lead(_lead(email="info@t.hu", website="https://t.hu", score=98))
    store.edit(touched, "Esti foglalások telefonon", CLEAN_BODY + " P.S.")
    m = FakeMailer()
    sent = pipeline.auto_send(store, pipeline.RunLog(), now=WEEKDAY_10, mailer=m, sleep=lambda s: None)
    assert [l["id"] for l in sent] == good[:2] and len(m.sent) == 2
    assert store.get(good[0])["sent_via"] == "auto"
    for lid in (good[2], low, dirty, touched):
        assert store.get(lid)["status"] == "draft"
    # a keret napi: újra futtatva nem küld többet
    assert pipeline.auto_send(store, pipeline.RunLog(), now=WEEKDAY_10, mailer=m, sleep=lambda s: None) == []


def test_auto_send_off_by_default_and_not_on_weekend(store, monkeypatch):
    _ready_store(store, monkeypatch)
    store.add_lead(_lead(email="info@w.hu", website="https://w.hu", score=90))
    m = FakeMailer()
    sat = datetime(2026, 10, 3, 10, 0, tzinfo=timezone.utc)
    assert pipeline.auto_send(store, pipeline.RunLog(), now=sat, mailer=m, sleep=lambda s: None) == []
    evening = datetime(2026, 10, 1, 19, 0, tzinfo=timezone.utc)
    assert pipeline.auto_send(store, pipeline.RunLog(), now=evening, mailer=m, sleep=lambda s: None) == []
    store.set_setting("auto_send", "off")
    assert pipeline.auto_send(store, pipeline.RunLog(), now=WEEKDAY_10, mailer=m, sleep=lambda s: None) == []
    assert not m.sent


def test_auto_send_brake_on_bounces(store, monkeypatch):
    _ready_store(store, monkeypatch)
    m = FakeMailer()
    for i in range(2):
        lid = store.add_lead(_lead(email=f"info@b{i}.hu", website=f"https://b{i}.hu", score=90))
        pipeline.send_one(store, lid, mailer=m, via="auto")
        store.set_reply(lid, "bounce", "nem kézbesíthető")
    store.add_lead(_lead(email="info@next.hu", website="https://next.hu", score=90))
    log = pipeline.RunLog()
    now = datetime.now(timezone.utc).replace(hour=10)
    now = now if now.weekday() < 5 else now - timedelta(days=now.weekday() - 4)
    assert pipeline.auto_send(store, log, now=now, mailer=m, sleep=lambda s: None) == []
    assert store.get_setting("auto_send") == "off" and any("VÉSZFÉK" in x for x in log.lines)


def test_auto_send_turns_itself_off_when_not_calibrated(store):
    store.set_setting("auto_send", "on")
    log = pipeline.RunLog()
    assert pipeline.auto_send(store, log, now=WEEKDAY_10, mailer=FakeMailer(), sleep=lambda s: None) == []
    assert store.get_setting("auto_send") == "off"


def test_auto_send_toggle_endpoint_refuses_until_ready(monkeypatch, tmp_path):
    monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", "jelszo12345")
    import importlib
    import app as app_mod
    importlib.reload(app_mod)
    from fastapi.testclient import TestClient
    c = TestClient(app_mod.app)
    a = ("x", "jelszo12345")
    r = c.post("/api/auto-send", json={"on": True}, auth=a)
    assert r.status_code == 409 and "döntés" in r.json()["detail"]
    assert c.post("/api/auto-send", json={"on": False}, auth=a).status_code == 200
    st = c.get("/api/state", auth=a).json()
    assert st["auto_send"]["on"] is False and st["auto_send"]["ready"] is False



def test_manual_lead_passes_the_same_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "man.db"))
    monkeypatch.setenv("ADMIN_PASSWORD", "helyes-jelszo-123")
    import importlib
    import store as store_mod
    importlib.reload(store_mod)
    import app as app_mod
    importlib.reload(app_mod)
    from fastapi.testclient import TestClient
    c, A = TestClient(app_mod.app), ("x", "helyes-jelszo-123")
    good = {"company": "Példa Kft.", "email": "info@pelda.hu", "website": "https://pelda.hu", "subject": "Kérdés",
            "body": "Tisztelt Hölgyem/Uram!\n\nRövid levél az aximbra.hu oldalról.\n\n"
                    "Ha nem aktuális, egy „nem” válasz elég, többet nem írok.\n\nÜdvözlettel:\nHutkai Milán"}
    r = c.post("/api/manual-lead", json=good, auth=A)
    assert r.status_code == 200 and r.json()["id"]
    assert c.post("/api/manual-lead", json=good, auth=A).status_code == 409            # kétszer nem
    assert c.post("/api/manual-lead", json={**good, "email": "a@pelda.at"}, auth=A).status_code == 409   # AT soha
    bad = {**good, "email": "b@pelda.hu", "body": good["body"].replace("Ha nem aktuális, egy „nem” válasz elég, többet nem írok.", "")}
    assert c.post("/api/manual-lead", json=bad, auth=A).status_code == 409             # leiratkozás nélkül nem
    assert c.post("/api/manual-lead", json=good, auth=("x", "rossz")).status_code == 401


def test_long_sentence_in_the_message_is_flagged_but_not_in_the_fixed_lines():
    long = " ".join(["szó"] * 30) + "."
    assert any("hosszú mondat" in w for w in verify.check_letter(_lead(body="Jó napot!\n\n" + long + "\n\n" + CLEAN_BODY)))
    assert not verify.long_sentences(CLEAN_BODY)
    assert not verify.long_sentences("Jó napot!\n\nRövid.\n\nHutkai Milán · AXIMBRA · aximbra.hu\n\n" + long)


def test_auto_send_spends_the_cap_on_signal_leads_first(store, monkeypatch):
    monkeypatch.setenv("AUTO_SEND_DAILY", "1")
    store.set_setting("auto_send", "on")
    monkeypatch.setattr(pipeline, "readiness", lambda s: {"ready": True, "why": []})
    plain = store.add_lead(dict(CAND, email="info@sima.hu", website="https://sima.hu", company="Sima", score=95,
                                signal="none", subject="Kérdés", body=CLEAN_BODY, lang="hu", country="HU"))
    hot = store.add_lead(dict(CAND, email="info@jel.hu", website="https://jel.hu", company="Jel", score=85,
                              signal="job_ad", subject="Kérdés", body=CLEAN_BODY, lang="hu", country="HU"))
    sent = []
    monkeypatch.setattr(pipeline, "send_one", lambda st, i, **k: sent.append(i) or (True, "ok"))
    monkeypatch.setattr(pipeline.verify, "rule_violations", lambda l: [])
    pipeline.auto_send(store, pipeline.RunLog(), now=datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc), sleep=lambda s: None)
    assert sent == [hot] and plain


def test_reply_watch_runs_by_day_every_half_hour():
    d = datetime(2026, 10, 1, 9, 0)
    assert pipeline.reply_watch_due(d, None)
    assert not pipeline.reply_watch_due(d, d - timedelta(minutes=10))
    assert pipeline.reply_watch_due(d, d - timedelta(minutes=31))
    assert not pipeline.reply_watch_due(datetime(2026, 10, 1, 23, 0), None)


def test_reply_watch_notifies_only_on_new_replies(monkeypatch, tmp_path):
    monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "w.db"))
    import importlib
    import app as app_mod
    importlib.reload(app_mod)
    told = []
    monkeypatch.setattr(app_mod, "_notify", lambda *a, **k: told.append(1))
    monkeypatch.setattr(app_mod.pipeline, "scan_replies", lambda st, log: log)
    assert app_mod._reply_watch() == 0 and not told
    lid = app_mod.store.add_lead(dict(CAND, subject="s", body=CLEAN_BODY, lang="hu", country="HU"))
    monkeypatch.setattr(app_mod.pipeline, "scan_replies",
                        lambda st, log: st.set_reply(lid, "interested", "Érdekel") or log)
    assert app_mod._reply_watch() == 1 and told == [1]


# ---- új országok: az oldal nyelvei, ahol szabad írni ----

def test_site_languages_cover_allowed_countries_only():
    from playbook import COUNTRIES, BLOCKED_TLDS
    assert {"GB", "IE", "FR", "BE"} <= set(COUNTRIES)
    assert not {"DE", "AT", "CH", "ES", "IT", "CN"} & set(COUNTRIES)
    assert {".ch", ".es", ".it"} <= set(BLOCKED_TLDS)
    for tld in ("ch", "es", "it", "de", "at"):
        assert verify.target_problems({"country": "FR", "email": f"info@x.{tld}", "website": f"https://x.{tld}"})


def test_every_country_is_in_the_automatic_plan(monkeypatch, tmp_path):
    monkeypatch.setenv("SALES_DB_PATH", str(tmp_path / "p.db"))
    monkeypatch.setenv("AUTO_PLAN", "HU:10,SK:2,RO:2,HR:1,FR:0")
    import importlib
    import app as app_mod
    importlib.reload(app_mod)
    from playbook import COUNTRIES
    plan = app_mod._auto_plan()
    assert set(plan) == set(COUNTRIES) and plan["HU"] == 10 and plan["FR"] == 0 and plan["GB"] >= 1


EN_BODY = ("Hello,\n\nYour website says that your support team answers enquiries in three languages.\n\n"
           "Do you answer the same questions by hand every day?\n\n"
           "I built an agent that drafts those answers from your own documents for your team to approve.\n\n"
           "Would this be interesting for you?\n\nMilán Hutkai · AXIMBRA · aximbra.hu/en\n\n"
           "P.S. You can try it on a sample mailbox at aximbra.hu/en, no sign-up needed.\n\n" + OPT_OUT["en"])
FR_BODY = ("Bonjour,\n\nSur votre site, vous indiquez que votre service client répond aux demandes du lundi au samedi.\n\n"
           "Est-ce que vous répondez à la main aux mêmes questions chaque jour ?\n\n"
           "J’ai construit un agent qui prépare ces réponses à partir de vos documents, que votre équipe valide.\n\n"
           "Est-ce que cela vous intéresserait ?\n\nMilán Hutkai · AXIMBRA · aximbra.hu/fr\n\n"
           "P.S. Vous pouvez l’essayer sur une boîte de démonstration sur aximbra.hu/fr, sans inscription.\n\n" + OPT_OUT["fr"])


def test_english_and_french_letters_pass_and_are_recognised():
    assert verify.detect_lang("Do you answer the same questions by hand every day with your team?") == "en"
    assert verify.detect_lang("Est-ce que vous répondez à la main aux mêmes questions pour votre équipe ?") == "fr"
    en = _lead(lang="en", country="GB", subject="Support questions", body=EN_BODY, email="info@acme.co.uk",
               website="https://acme.co.uk")
    fr = _lead(lang="fr", country="FR", subject="Questions clients", body=FR_BODY, email="contact@acme.fr",
               website="https://acme.fr")
    assert verify.rule_violations(en) == []
    assert verify.rule_violations(fr) == []


@pytest.mark.parametrize("bad,why", [
    ("One of our clients saved time.", "ügyfélre"),
    ("Nos clients gagnent du temps.", "ügyfélre"),
    ("Dear Mr. Smith,", "munkatárs"),
    ("Bonjour Madame Martin,", "munkatárs"),
    ("It costs £400.", "ár"),
    ("Trois fois plus vite, 40 pour cent de moins.", "statisztik"),
])
def test_rules_hold_in_english_and_french(bad, why):
    v = verify.rule_violations(_lead(lang="en", country="GB", subject="Support questions", email="info@acme.co.uk",
                                     website="https://acme.co.uk", body=bad + "\n\n" + EN_BODY))
    assert any(why in x for x in v), v


# ---- napi tartalomtéma a videós agentnek ------------------------------------

def test_content_sends_two_briefs_once_and_never_leaks_names(store, monkeypatch):
    import json as _json
    import content
    from datetime import datetime as _dt
    monkeypatch.setenv("CONTENT_DAILY", "1")
    monkeypatch.setenv("AGENT_TOKEN", "x" * 32)
    store.add_lead(dict(CAND, lang="hu"))
    company = CAND["company"]
    now = _dt(2026, 10, 5, 7, 45)
    assert content.enabled() and content.due(now, store)
    assert not content.due(now.replace(hour=7, minute=0), store)          # kezdés előtt nem

    replies = [{"hu": {"brief": f"{company} postafiókja reggel, AXIMBRA e-mail rendező bemutató.", "form": "video"},
                "en": {"brief": "AXIMBRA phone agent: a missed call at a busy logistics firm, shown in one strong image.", "form": "image"}},
               {"hu": {"brief": "AXIMBRA: hétfő reggel kétszáz levél a közös postafiókban, kkv-vezetőknek, nyugodt hangulat.", "form": "carousel"},
                "en": {"brief": "AXIMBRA phone agent: a missed call at a busy logistics firm, shown in one strong image.", "form": "image"}}]
    monkeypatch.setattr(content.llm, "_ask", lambda prompt: _json.dumps(replies.pop(0)))
    sent = []
    fail = {"on": True}

    def fake_send(item):
        if fail["on"]:
            fail["on"] = False
            raise RuntimeError("nem érhető el")
        sent.append(item)
    monkeypatch.setattr(content, "_send", fake_send)

    with pytest.raises(content.llm.LLMError):                              # cégnév a témában: eldobja
        content.run(store, now)
    with pytest.raises(RuntimeError):                                      # a küldés elhasal
        content.run(store, now)
    assert not content.due(now + timedelta(minutes=10), store)            # vár RETRY_MIN percet
    later = now + timedelta(minutes=content.RETRY_MIN)
    assert content.due(later, store)
    content.run(store, later)                                              # ugyanazt a témát küldi újra
    assert [s["id"] for s in sent] == ["sales-2026-10-05-hu", "sales-2026-10-05-en"]
    assert sent[0]["targets"] == ["linkedin"] and sent[1]["targets"] == ["instagram"]
    assert sent[0]["form"] == "carousel" and company.lower() not in sent[0]["brief"].lower()
    assert not content.due(later + timedelta(hours=2), store)             # ma kész
    assert content.due(later + timedelta(days=1), store)


def test_content_covers_every_agent_before_repeating_any(store, monkeypatch):
    """A panasz az volt, hogy az e-mail rendezőről húsz poszt van kint, a
    multi-agent rendszerről nulla. A névsort ezért a kód forgatja, nem a modell."""
    import json as _json
    import content
    from playbook import AGENTS
    monkeypatch.setenv("CONTENT_DAILY", "1")
    monkeypatch.setenv("AGENT_TOKEN", "x" * 32)
    monkeypatch.setattr(content.llm, "_ask", lambda prompt: _json.dumps(
        {"hu": {"brief": "AXIMBRA: hétfő reggel a közös postafiók, kkv-vezetőknek, nyugodt hangulat.",
                "form": "video"},
         "en": {"brief": "AXIMBRA: Monday morning at a logistics firm, one strong opening image.",
                "form": "image"}}))
    sent = []
    monkeypatch.setattr(content, "_send", lambda item: sent.append(item))

    start = datetime(2026, 10, 5, 7, 45)
    for d in range(len(AGENTS)):
        content.run(store, start + timedelta(days=d))

    order = _json.loads(store.get_setting("content_agents"))
    assert order == [a["key"] for a in AGENTS]            # mind sorra kerül, pont egyszer
    assert len(set(order)) == len(AGENTS) >= 15

    # Egy nap = egy agent, és az a LinkedInre is, az Instagramra is kimegy.
    day = (start + timedelta(days=3)).date().isoformat()
    pair = [s for s in sent if s["id"].startswith(f"sales-{day}-")]
    assert [s["targets"] for s in pair] == [["linkedin"], ["instagram"]]
    assert {s["source"] for s in pair} == {f"sales agent · {AGENTS[3]['key']}"}

    # A tizenhatodik nap a legrégebbit hozza vissza, nem a modell kedvencét.
    content.run(store, start + timedelta(days=len(AGENTS)))
    assert _json.loads(store.get_setting("content_agents"))[-1] == AGENTS[0]["key"]


def test_rotation_lists_exactly_the_agents_the_website_sells():
    """Ha az oldalra új agentkártya kerül, de a névsorba nem, arról megint nulla
    poszt menne ki — csendben, ugyanúgy, mint eddig. A forrás az aximbra.hu
    magyar szövege; a sorrendnek is egyeznie kell, hogy a kettő összenézhető
    maradjon."""
    import re
    from playbook import AGENTS
    site = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src", "i18n", "hu.js")
    if not os.path.exists(site):
        pytest.skip("a frontend nincs a checkoutban")
    with open(site, encoding="utf-8") as f:
        s = f.read()
    start = s.index("\n  agents: [")
    titles = re.findall(r'title:\s*"([^"]+)"', s[start:s.index("\n  ]", start)])
    assert [a["hu"] for a in AGENTS] == titles
    assert len({a["key"] for a in AGENTS}) == len(AGENTS)


def test_content_retry_keeps_the_same_agent_and_never_burns_one(store, monkeypatch):
    """Egy elhasalt küldés (vagy modellhívás) nem léptetheti a névsort: aznap
    ugyanaz az agent jön vissza, és a sikertelen nap nem ég el."""
    import json as _json
    import content
    from playbook import AGENTS
    monkeypatch.setenv("CONTENT_DAILY", "1")
    monkeypatch.setenv("AGENT_TOKEN", "x" * 32)
    now = datetime(2026, 10, 5, 7, 45)

    monkeypatch.setattr(content.llm, "_ask", lambda prompt: "nem JSON")
    with pytest.raises(content.llm.LLMError):                     # a modell elhasal
        content.run(store, now)
    assert store.get_setting("content_agents") in (None, "[]")    # a névsor nem lépett

    monkeypatch.setattr(content.llm, "_ask", lambda prompt: _json.dumps(
        {"hu": {"brief": "AXIMBRA: hétfő reggel a közös postafiók, kkv-vezetőknek, nyugodt hangulat.",
                "form": "video"},
         "en": {"brief": "AXIMBRA: Monday morning at a logistics firm, one strong opening image.",
                "form": "image"}}))
    fail = {"on": True}

    def flaky(item):
        if fail["on"]:
            fail["on"] = False
            raise RuntimeError("a videós agent nem érhető el")
        sent.append(item)
    sent = []
    monkeypatch.setattr(content, "_send", flaky)

    with pytest.raises(RuntimeError):
        content.run(store, now)
    content.run(store, now + timedelta(minutes=content.RETRY_MIN))
    assert _json.loads(store.get_setting("content_agents")) == [AGENTS[0]["key"]]
    assert {s["source"] for s in sent} == {f"sales agent · {AGENTS[0]['key']}"}
