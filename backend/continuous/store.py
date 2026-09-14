"""Ami megmarad két futás között — és ami szándékosan nem.

Tárolunk:

  * a fiók azonosítóját és e-mail címét,
  * a Google **refresh tokent**, titkosítva (enélkül nincs kétóránkénti futás),
  * hol tartottunk a postafiókban (`history_id`), hogy a következő futás csak
    az újat nézze,
  * és futásonként a **megállapítást** minden levélről: feladó, tárgy, dátum,
    kategória, sürgősség, összefoglaló, javasolt lépés.

Nem tárolunk:

  * levéltörzset, csatolmányt, HTML-t — azok maradnak a Gmailben, ahol
    eleve vannak. Ha ez az adatbázis kiszivárog, egy lista áll benne arról,
    hogy kitől jött levél és mennyire sürgős, nem pedig a levelezés.

A refresh token az egyetlen igazán veszélyes adat itt, ezért nem nyersen
fekszik: Fernettel titkosítva megy be, és a kulcs nem az adatbázisban van.
Aki megszerzi a fájlt, nem fér hozzá senki postafiókjához.

SQLite, mert a stdlib-ben van: egy ügyfélnek szánt, egyfiókos rendszerhez nem
kell külön adatbázis-szolgáltatás. Hálózati lemezen (Railway-volume) kell
laknia — a konténer fájlrendszere újraindításkor eltűnik.
"""
import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_DB_PATH = "/data/continuous.sqlite3"

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL,
    refresh_token BLOB NOT NULL,          -- titkosítva
    history_id    TEXT,                   -- hol tartottunk a postafiókban
    created_at    TEXT NOT NULL,
    last_run_at   TEXT,
    last_error    TEXT,
    failures      INTEGER NOT NULL DEFAULT 0,
    paused        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS findings (
    account_id  TEXT NOT NULL,
    message_id  TEXT NOT NULL,
    sender      TEXT,
    subject     TEXT,
    date        TEXT,
    category    TEXT,
    urgency     INTEGER,
    needs_reply TEXT,
    summary     TEXT,
    next_step   TEXT,
    seen_at     TEXT NOT NULL,
    PRIMARY KEY (account_id, message_id)
);

CREATE INDEX IF NOT EXISTS findings_by_account ON findings (account_id, urgency DESC, date DESC);
"""


class Store:
    """Egy SQLite-fájl, szálbiztosan.

    A `check_same_thread=False` és a lakat együtt jár: a futtató szál és a
    webkiszolgáló szála ugyanazt a kapcsolatot használja, és az SQLite nem
    szereti, ha két szál egyszerre ír.
    """

    def __init__(self, path: str | None = None, key: str | None = None):
        self.path = path or os.environ.get("CONTINUOUS_DB_PATH") or DEFAULT_DB_PATH
        raw_key = key or os.environ.get("CONTINUOUS_KEY") or ""
        if not raw_key:
            raise RuntimeError(
                "CONTINUOUS_KEY hiányzik. Kulcs nélkül a refresh tokenek titkosítatlanul "
                "feküdnének az adatbázisban, ezért a rendszer nem indul el."
            )
        self._fernet = Fernet(raw_key.encode())
        self._lock = threading.Lock()
        if self.path != ":memory:":
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # ------------------------------------------------------------------ fiók
    @contextmanager
    def _write(self):
        with self._lock:
            yield self._conn
            self._conn.commit()

    def add_account(self, account_id: str, email: str, refresh_token: str) -> None:
        token = self._fernet.encrypt(refresh_token.encode())
        with self._write() as c:
            c.execute(
                "INSERT INTO accounts (id, email, refresh_token, created_at) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET email=excluded.email, "
                "refresh_token=excluded.refresh_token, paused=0, failures=0, last_error=NULL",
                (account_id, email, token, datetime.now(timezone.utc).isoformat()),
            )

    def refresh_token(self, account_id: str) -> str | None:
        """A visszafejtett token, vagy None, ha a kulcs nem ehhez az adatbázishoz való."""
        with self._lock:
            row = self._conn.execute(
                "SELECT refresh_token FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
        if not row:
            return None
        try:
            return self._fernet.decrypt(row["refresh_token"]).decode()
        except InvalidToken:
            # Rossz kulcs vagy sérült sor. Csendben None-t adni azt jelentené,
            # hogy „nincs ilyen fiók" — pedig van, csak nem tudjuk olvasni.
            raise RuntimeError(f"a {account_id} fiók tokenje nem fejthető vissza ezzel a kulccsal")

    def accounts(self) -> list:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, email, history_id, last_run_at, failures, paused, last_error "
                "FROM accounts ORDER BY created_at"
            ).fetchall()
        return [dict(r) for r in rows]

    def remove_account(self, account_id: str) -> None:
        """Lecsatlakozás: a token és minden megállapítás megy vele."""
        with self._write() as c:
            c.execute("DELETE FROM findings WHERE account_id = ?", (account_id,))
            c.execute("DELETE FROM accounts WHERE id = ?", (account_id,))

    def set_history_id(self, account_id: str, history_id: str | None) -> None:
        with self._write() as c:
            c.execute("UPDATE accounts SET history_id = ? WHERE id = ?", (history_id, account_id))

    def mark_run(self, account_id: str, error: str | None = None) -> None:
        """A futás vége. Hibánál számolunk, sikernél nullázunk.

        A számláló nem kozmetika: egy visszavont hozzáférés különben kétóránként
        újra és újra nekifutna, és a naplóban minden nyoma egyforma lenne.
        """
        now = datetime.now(timezone.utc).isoformat()
        with self._write() as c:
            if error:
                c.execute(
                    "UPDATE accounts SET last_run_at = ?, last_error = ?, failures = failures + 1 "
                    "WHERE id = ?", (now, error[:300], account_id))
            else:
                c.execute(
                    "UPDATE accounts SET last_run_at = ?, last_error = NULL, failures = 0 "
                    "WHERE id = ?", (now, account_id))

    def set_paused(self, account_id: str, paused: bool) -> None:
        with self._write() as c:
            c.execute("UPDATE accounts SET paused = ? WHERE id = ?", (1 if paused else 0, account_id))

    # --------------------------------------------------------- megállapítások
    def save_findings(self, account_id: str, findings: list) -> int:
        """Levelenként egy sor. Ugyanaz a levél kétszer nem kerül be."""
        now = datetime.now(timezone.utc).isoformat()
        rows = [
            (account_id, f.get("id"), f.get("sender"), f.get("subject"), f.get("date"),
             f.get("category"), f.get("urgency"), f.get("needs_reply"),
             f.get("summary"), f.get("next_step"), now)
            for f in findings if f.get("id")
        ]
        if not rows:
            return 0
        with self._write() as c:
            # rowcount, nem total_changes: az utóbbi a kapcsolat egész élete alatt
            # végzett módosításokat számolja, tehát futásról futásra nőne, és
            # minden kör azt állítaná, hogy több új levél érkezett, mint amennyi.
            cur = c.executemany(
                "INSERT INTO findings (account_id, message_id, sender, subject, date, category, "
                "urgency, needs_reply, summary, next_step, seen_at) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                "ON CONFLICT(account_id, message_id) DO NOTHING",
                rows,
            )
            return max(cur.rowcount, 0)

    def findings(self, account_id: str, limit: int = 100, needs_reply_only: bool = False) -> list:
        sql = ("SELECT * FROM findings WHERE account_id = ?"
               + (" AND needs_reply = 'igen'" if needs_reply_only else "")
               + " ORDER BY urgency DESC, date DESC LIMIT ?")
        with self._lock:
            rows = self._conn.execute(sql, (account_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def known_message_ids(self, account_id: str) -> set:
        with self._lock:
            rows = self._conn.execute(
                "SELECT message_id FROM findings WHERE account_id = ?", (account_id,)
            ).fetchall()
        return {r["message_id"] for r in rows}

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def dump_for_export(store: "Store", account_id: str) -> str:
    """Amit az ügyfél kikérhet magáról. GDPR 15. és 20. cikk.

    A token nincs benne: az hitelesítő adat, nem a felhasználó adata, és
    exportálni sem lenne értelme.
    """
    account = next((a for a in store.accounts() if a["id"] == account_id), None)
    return json.dumps(
        {"account": account, "findings": store.findings(account_id, limit=10000)},
        ensure_ascii=False, indent=2,
    )
