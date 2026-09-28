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
        "pain": "phone", "sector": "restaurant", "signal": "notice", "score": 80}


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
        if "nem" in reply.lower():
            return {"kind": "no", "suggestion": ""}
        return {"kind": "interested", "suggestion": "Köszönöm! Mikor beszélhetnénk 20 percet?"}


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
    pipeline.scan_replies(store, pipeline.RunLog(), llm=FakeLLM([]), mailbox_factory=FakeMailbox)
    lead = store.get(lid)
    assert lead["reply_kind"] == "no" and store.is_blocked("info@kertbisztro.hu")
    assert pipeline.prepare_followups(store, datetime(2027, 1, 1, tzinfo=timezone.utc)) == 0


def test_interested_reply_gets_suggestion(store):
    lid = _sent(store)
    FakeMailbox.inbox = [{"from": "info@kertbisztro.hu", "text": "Érdekel, mennyibe kerül?\n\n> régi levél",
                          "in_reply_to": "", "references": "", "message_id": "<r2>", "subject": "Re", "date": ""}]
    pipeline.scan_replies(store, pipeline.RunLog(), llm=FakeLLM([]), mailbox_factory=FakeMailbox)
    lead = store.get(lid)
    assert lead["reply_kind"] == "interested" and "20 percet" in lead["reply_suggestion"]
    assert "régi levél" not in lead["reply_text"]


def test_bounce_blocks(store):
    lid = _sent(store)
    FakeMailbox.bounces = [{"from": "mailer-daemon@googlemail.com", "text": "Address not found: info@kertbisztro.hu"}]
    pipeline.scan_replies(store, pipeline.RunLog(), llm=FakeLLM([]), mailbox_factory=FakeMailbox)
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
    assert lead["sector"] == "restaurant" and lead["score"] == 80


def test_drafts_sorted_by_score(store):
    run(store, [dict(CAND, score=75)])
    run(store, [dict(CAND, company="Másik", email="info@masik.hu", website="https://masik.hu", score=95)],
        fetch=lambda url: PAGE.replace("kertbisztro", "masik"))
    assert [l["score"] for l in store.list("draft")] == [95, 75]


def test_learning_prefers_sector_with_replies(store):
    for i, (sector, kind) in enumerate([("dental", "interested")] * 5 + [("auto", "none")] * 5):
        lid = store.add_lead(dict(CAND, email=f"a{i}@c{i}.hu", website=f"https://c{i}.hu", lang="hu",
                                  sector=sector))
        store.mark_sent_manual(lid)
        if kind != "none":
            store.set_reply(lid, kind, "érdekel")
    assert store.best_sectors()[0] == "dental"
    llm = FakeLLM([])
    pipeline.research_run(store, {"HU": 1}, pipeline.RunLog(), llm=llm, mailbox_factory=FakeMailbox)
    assert llm.focus.startswith("dental")


def test_extract_json_prefers_outer_object():
    import llm
    assert llm.extract_json('Íme: {"score": 7, "issues": ["x"], "body": "b"}')["score"] == 7
    assert llm.extract_json('```json\n[{"a": 1}]\n```') == [{"a": 1}]
