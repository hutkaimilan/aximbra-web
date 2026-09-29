"""Az értékesítő hálózat nélkül: modell, Gmail és letöltés csonkkal."""
import os
import sys
from datetime import datetime, timezone

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


# ---- videós agent ----

import videomaker  # noqa: E402


def test_video_script_is_normalized_and_ends_with_cta():
    raw = {"title": "T", "scenes": [
        {"kind": "cta", "headline": "Korai CTA", "seconds": 4},
        {"kind": "hook", "headline": "Ki veszi fel?", "seconds": 3},
        {"kind": "bogus", "headline": "x"},
        {"kind": "problem", "headline": "Ismerős?", "lines": ["a", "b", "c", "d", "e", "f", "g"], "seconds": 99},
    ]}
    s = videomaker.normalize(raw, 30)
    assert [x["kind"] for x in s["scenes"]] == ["hook", "problem", "cta"]
    assert len(s["scenes"][1]["lines"]) == 6
    assert all(2 <= x["seconds"] <= 10 for x in s["scenes"])
    assert s["first_comment"]


def test_video_script_without_usable_scenes_fails():
    with pytest.raises(videomaker.VideoError):
        videomaker.normalize({"scenes": [{"kind": "hook", "headline": ""}]}, 30)


def test_video_ids_cannot_escape_the_folder():
    assert videomaker.video_path("../../etc/passwd") is None
    assert videomaker.video_path("abc") is None


def test_video_served_in_byte_ranges(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_mod
    monkeypatch.setenv("ADMIN_PASSWORD", "jelszo1234")
    monkeypatch.setattr(videomaker, "VIDEO_DIR", str(tmp_path))
    (tmp_path / "abcdef012345.mp4").write_bytes(bytes(range(100)))
    c = TestClient(app_mod.app)
    r = c.get("/api/videos/abcdef012345.mp4", headers={"Range": "bytes=10-19"}, auth=("a", "jelszo1234"))
    assert r.status_code == 206 and r.content == bytes(range(10, 20))
    assert r.headers["content-range"] == "bytes 10-19/100"
    assert c.get("/api/videos/abcdef012345.mp4", auth=("a", "rossz")).status_code == 401
