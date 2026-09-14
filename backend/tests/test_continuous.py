"""A kétóránként futó agent motorja.

Ez a rendszer az egyetlen, ami adatot őriz két futás között, ezért minden
állítása bizonyítandó: hogy a token titkosítva fekszik, hogy a levéltörzs nem
kerül bele, hogy az első futás öt hónapot néz vissza, a többi csak az újat, és
hogy egy visszavont hozzáférés nem pörög a végtelenségig.
"""
import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet

from continuous import worker
from continuous.store import Store, dump_for_export


@pytest.fixture
def store(tmp_path):
    s = Store(path=str(tmp_path / "t.sqlite3"), key=Fernet.generate_key().decode())
    yield s
    s.close()


# ------------------------------------------------------------------- tárolás
def test_the_refresh_token_is_not_readable_from_the_file(tmp_path):
    key = Fernet.generate_key().decode()
    path = str(tmp_path / "t.sqlite3")
    s = Store(path=path, key=key)
    s.add_account("acc1", "ugyfel@pelda.hu", "1//titkos-refresh-token")
    s.close()

    raw = open(path, "rb").read()
    assert b"1//titkos-refresh-token" not in raw, "a token nyersen fekszik a fájlban"

    # A helyes kulccsal visszafejthető…
    again = Store(path=path, key=key)
    assert again.refresh_token("acc1") == "1//titkos-refresh-token"
    again.close()

    # …másikkal nem, és ezt meg is mondja, nem tesz úgy, mintha nem lenne fiók.
    other = Store(path=path, key=Fernet.generate_key().decode())
    with pytest.raises(RuntimeError):
        other.refresh_token("acc1")
    other.close()


def test_a_store_without_a_key_refuses_to_start(tmp_path, monkeypatch):
    monkeypatch.delenv("CONTINUOUS_KEY", raising=False)
    with pytest.raises(RuntimeError):
        Store(path=str(tmp_path / "x.sqlite3"))


def test_only_the_verdict_is_stored_never_the_email_body(store):
    store.add_account("acc1", "a@b.hu", "rt")
    store.save_findings("acc1", [{
        "id": "m1", "sender": "x@y.hu", "subject": "Ajánlat", "date": "2026-09-01T10:00:00+00:00",
        "body": "EZ A LEVÉL TÖRZSE, ENNEK NEM SZABAD BEKERÜLNIE",
        "snippet": "részlet", "category": "opportunity", "urgency": 4,
        "needs_reply": "igen", "summary": "Ajánlatot kér.", "next_step": "Hívd vissza.",
    }])
    saved = store.findings("acc1")[0]
    assert saved["summary"] == "Ajánlatot kér."
    assert "body" not in saved and "snippet" not in saved
    raw = sqlite3.connect(store.path).execute("SELECT * FROM findings").fetchall()
    assert not any("TÖRZSE" in str(cell) for row in raw for cell in row)


def test_the_same_message_is_not_stored_twice(store):
    store.add_account("acc1", "a@b.hu", "rt")
    one = [{"id": "m1", "subject": "A", "urgency": 1}]
    assert store.save_findings("acc1", one) == 1
    assert store.save_findings("acc1", one) == 0
    assert len(store.findings("acc1")) == 1


def test_disconnecting_takes_the_findings_with_it(store):
    store.add_account("acc1", "a@b.hu", "rt")
    store.save_findings("acc1", [{"id": "m1", "subject": "A"}])
    store.remove_account("acc1")
    assert store.accounts() == []
    assert store.findings("acc1") == []


def test_the_export_carries_the_findings_but_not_the_token(store):
    store.add_account("acc1", "ugyfel@pelda.hu", "1//titok")
    store.save_findings("acc1", [{"id": "m1", "subject": "Ajánlat"}])
    dump = dump_for_export(store, "acc1")
    assert "Ajánlat" in dump and "ugyfel@pelda.hu" in dump
    assert "1//titok" not in dump and "refresh_token" not in dump


# ----------------------------------------------------------- esedékesség
def test_a_new_account_runs_immediately_then_every_two_hours():
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    never = {"id": "a", "last_run_at": None, "failures": 0, "paused": 0}
    fresh = {"id": "b", "last_run_at": (now - timedelta(minutes=30)).isoformat(), "failures": 0, "paused": 0}
    old = {"id": "c", "last_run_at": (now - timedelta(hours=2, minutes=1)).isoformat(), "failures": 0, "paused": 0}
    due = [a["id"] for a in worker.due_accounts([never, fresh, old], now=now, interval_minutes=120)]
    assert due == ["a", "c"]


def test_a_paused_or_repeatedly_failing_account_is_skipped():
    now = datetime.now(timezone.utc)
    paused = {"id": "p", "last_run_at": None, "failures": 0, "paused": 1}
    broken = {"id": "b", "last_run_at": None, "failures": worker.MAX_FAILURES, "paused": 0}
    assert worker.due_accounts([paused, broken], now=now) == []


def test_a_naive_timestamp_does_not_break_the_schedule():
    """Időzóna nélküli dátum a fájlban: UTC-nek vesszük, nem dobunk kivételt."""
    now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
    naive = {"id": "a", "last_run_at": "2026-09-14T09:00:00", "failures": 0, "paused": 0}
    assert [a["id"] for a in worker.due_accounts([naive], now=now)] == ["a"]


def test_the_first_pass_looks_five_months_back():
    now = datetime(2026, 9, 14, tzinfo=timezone.utc)
    q = worker.backfill_query(now=now, months=5)
    after = int(q.split(":")[1])
    days = (now - datetime.fromtimestamp(after, tz=timezone.utc)).days
    assert 150 <= days <= 155, days


# ------------------------------------------------------------------ futás
class FakeGmail:
    def __init__(self, ids, history_id="h2", fail=None):
        self.ids, self.history_id, self.fail = ids, history_id, fail
        self.calls = []

    async def list_since(self, query, limit):
        self.calls.append(("backfill", query))
        if self.fail:
            raise self.fail
        return self.ids[:limit], self.history_id

    async def list_new(self, history_id, limit):
        self.calls.append(("incremental", history_id))
        if self.fail:
            raise self.fail
        return self.ids[:limit], self.history_id

    async def fetch(self, mid):
        return {"id": mid, "sender": f"{mid}@x.hu", "subject": f"Tárgy {mid}",
                "date": "2026-09-01T10:00:00+00:00", "body": "törzs"}


async def _classify(email, lang="hu"):
    return {"category": "other", "urgency": 2, "needs_reply": "nem",
            "summary": "s", "next_step": "n", "urgency_reason": ""}


def test_the_first_run_backfills_and_the_second_only_asks_for_the_new(store):
    store.add_account("acc1", "a@b.hu", "rt")
    account = store.accounts()[0]
    gmail = FakeGmail(["m1", "m2"])

    r1 = asyncio.run(worker.run_account(account, store, gmail, _classify))
    assert r1["first_run"] is True and r1["new"] == 2
    assert gmail.calls[0][0] == "backfill"
    assert store.accounts()[0]["history_id"] == "h2"

    gmail2 = FakeGmail(["m3"], history_id="h3")
    r2 = asyncio.run(worker.run_account(store.accounts()[0], store, gmail2, _classify))
    assert r2["first_run"] is False and r2["new"] == 1
    assert gmail2.calls[0] == ("incremental", "h2"), "onnan folytatja, ahol abbahagyta"
    assert len(store.findings("acc1")) == 3


def test_an_already_seen_message_is_not_classified_again(store):
    store.add_account("acc1", "a@b.hu", "rt")
    store.save_findings("acc1", [{"id": "m1", "subject": "régi"}])
    seen = []

    async def counting(email, lang="hu"):
        seen.append(email["id"])
        return await _classify(email, lang)

    gmail = FakeGmail(["m1", "m2"])
    asyncio.run(worker.run_account(store.accounts()[0], store, gmail, counting))
    assert seen == ["m2"], "a már ismert levélre nem megy újabb modellhívás"


def test_a_revoked_access_is_recorded_and_eventually_pauses_the_account(store):
    store.add_account("acc1", "a@b.hu", "rt")
    gmail = FakeGmail([], fail=RuntimeError("invalid_grant"))
    for _ in range(worker.MAX_FAILURES):
        asyncio.run(worker.run_account(store.accounts()[0], store, gmail, _classify))
    acc = store.accounts()[0]
    assert acc["failures"] == worker.MAX_FAILURES
    assert "invalid_grant" in acc["last_error"]
    assert worker.due_accounts([acc]) == [], "a hibás fiók nem pörög tovább kétóránként"


def test_a_halted_run_does_not_move_the_bookmark(store):
    """Ha a napi keret elfogy, a history_id marad — különben a ki nem osztályozott
    levelek soha többé nem kerülnének elő."""
    store.add_account("acc1", "a@b.hu", "rt")
    store.set_history_id("acc1", "h1")

    async def out_of_budget(email, lang="hu"):
        raise RuntimeError("429 napi keret")

    gmail = FakeGmail(["m1", "m2"], history_id="h9")
    r = asyncio.run(worker.run_account(store.accounts()[0], store, gmail, out_of_budget))
    assert r["halted"] == "budget"
    assert store.accounts()[0]["history_id"] == "h1"


def test_the_loop_is_off_unless_switched_on(monkeypatch):
    monkeypatch.delenv("CONTINUOUS_ENABLED", raising=False)
    assert worker.is_enabled() is False
    monkeypatch.setenv("CONTINUOUS_ENABLED", "true")
    assert worker.is_enabled() is True


# ------------------------------------------------------------- Gmail-oldal
def test_the_mailbox_only_ever_asks_for_read_access():
    """Ez a rendszer olvas. A hatókör nem konfigurációs kérdés, hanem állítás,
    amit a lap is kimond — tehát tesztelni kell, nem emlékezni rá."""
    from continuous import gmail as cg

    assert cg.READONLY == ["https://www.googleapis.com/auth/gmail.readonly"]
    source = __import__("pathlib").Path(cg.__file__).read_text(encoding="utf-8")
    for forbidden in ("gmail.compose", "gmail.modify", "gmail.send", "drafts().create", "messages().send"):
        assert forbidden not in source, f"{forbidden} megjelent az olvasó modulban"


def test_an_expired_history_id_falls_back_to_a_full_pass(monkeypatch):
    """A Google véges ideig tartja a történetet. Ha elavult, inkább fussunk egy
    kört fölöslegesen, mint hogy csendben kimaradjon egy hét levele."""
    from continuous.gmail import GmailMailbox

    box = GmailMailbox.__new__(GmailMailbox)   # hálózat nélkül
    box._creds = None
    box._proxy = None
    box._service = None
    called = {}

    async def boom(*a, **k):
        raise RuntimeError("404 startHistoryId is too old")

    async def full(query, limit):
        called["query"] = query
        return (["m1"], "h9")

    async def svc():
        class S:
            def users(self):
                return self

            def history(self):
                return self

            def list(self, **k):
                class E:
                    def execute(self, http=None):
                        raise RuntimeError("404 startHistoryId is too old")
                return E()
        return S()

    box._svc = svc
    box.list_since = full
    ids, hid = asyncio.run(box.list_new("h-regi", 50))
    assert ids == ["m1"] and hid == "h9"
    assert called["query"].startswith("after:"), "teljes lekérdezésre esett vissza"
