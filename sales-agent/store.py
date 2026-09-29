"""A napló: kinek írtunk, mit, mikor, mit válaszolt, ki nem kér többet.

SQLite, mert egy felhasználó és egy folyamat van; a kötet a Railway-en
megmarad az újraindítások között. Minden állapotváltás egyetlen feltételes
UPDATE, így két párhuzamos kérés sem tud ugyanarra a levélre kétszer
"küldést" indítani.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

DEFAULT_PATH = os.environ.get("SALES_DB_PATH", "/data/sales.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  company TEXT NOT NULL,
  town TEXT,
  country TEXT NOT NULL,
  lang TEXT NOT NULL,
  website TEXT,
  domain TEXT NOT NULL,
  email TEXT NOT NULL UNIQUE,
  email_url TEXT,
  observation TEXT,
  observation_url TEXT,
  pain TEXT NOT NULL,
  subject TEXT,
  body TEXT,
  warnings TEXT,
  status TEXT NOT NULL DEFAULT 'draft',
  sent_at TEXT,
  message_id TEXT,
  last_error TEXT,
  followup_status TEXT NOT NULL DEFAULT 'none',
  followup_body TEXT,
  followup_sent_at TEXT,
  reply_kind TEXT NOT NULL DEFAULT 'none',
  reply_text TEXT,
  reply_suggestion TEXT,
  reply_at TEXT
);
CREATE INDEX IF NOT EXISTS leads_domain ON leads(domain);
CREATE INDEX IF NOT EXISTS leads_status ON leads(status);
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT
);
CREATE TABLE IF NOT EXISTS blocked (
  key TEXT PRIMARY KEY,           -- e-mail cím vagy domain, kisbetűvel
  reason TEXT,
  created_at TEXT NOT NULL
);
"""

# Később hozzáadott oszlopok: a meglévő adatbázis a köteten van, ezért
# indításkor pótoljuk őket, adatvesztés nélkül.
EXTRA_COLUMNS = {
    "sector": "TEXT", "signal": "TEXT", "signal_note": "TEXT", "signal_url": "TEXT",
    "score": "INTEGER", "score_reason": "TEXT", "critique": "TEXT", "slots": "TEXT", "lang2": "TEXT",
}

# draft -> sending -> sent | failed ; draft -> skipped ; failed -> draft (újra)
STATUSES = ("draft", "sending", "sent", "failed", "skipped")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def domain_of(email_or_url: str) -> str:
    s = (email_or_url or "").strip().lower()
    if "@" in s:
        s = s.split("@", 1)[1]
    s = s.split("://", 1)[-1].split("/", 1)[0].split(":", 1)[0]
    return s[4:] if s.startswith("www.") else s


class Store:
    def __init__(self, path: str | None = None):
        self.path = path or DEFAULT_PATH
        d = os.path.dirname(self.path)
        if d:
            os.makedirs(d, exist_ok=True)
        self._lock = threading.Lock()
        with self._conn() as c:
            c.executescript(SCHEMA)
            have = {r[1] for r in c.execute("PRAGMA table_info(leads)")}
            for col, typ in EXTRA_COLUMNS.items():
                if col not in have:
                    c.execute(f"ALTER TABLE leads ADD COLUMN {col} {typ}")

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
        finally:
            conn.close()

    # ---- beállítások -----------------------------------------------------

    def get_setting(self, key: str) -> str | None:
        with self._conn() as c:
            r = c.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return r[0] if r and r[0] else None

    def set_setting(self, key: str, value: str) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO settings (key, value) VALUES (?, ?) "
                      "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))

    # ---- tiltólista ----------------------------------------------------

    def block(self, key: str, reason: str) -> None:
        key = key.strip().lower()
        if not key:
            return
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO blocked (key, reason, created_at) VALUES (?, ?, ?)",
                      (key, reason, now()))

    def blocked_keys(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM blocked ORDER BY created_at DESC")]

    def is_known(self, email: str, website: str | None = None) -> str | None:
        """Miért nem írhatunk neki, ha nem: már szerepel, vagy tiltott.

        A domaint a weboldalból is nézzük, mert egy gmailes cím mögött is
        ugyanaz a cég lehet, akinek a céges címére már írtunk."""
        email = email.strip().lower()
        doms = {d for d in (domain_of(email), domain_of(website or "")) if d and d not in FREEMAIL}
        with self._conn() as c:
            keys = [email, *doms]
            marks = ",".join("?" * len(keys))
            if c.execute(f"SELECT 1 FROM blocked WHERE key IN ({marks})", keys).fetchone():
                return "tiltólistán"
            if c.execute("SELECT 1 FROM leads WHERE email = ?", (email,)).fetchone():
                return "már szerepel"
            for d in doms:
                if c.execute("SELECT 1 FROM leads WHERE domain = ?", (d,)).fetchone():
                    return "a cég már szerepel"
        return None

    def is_blocked(self, email: str) -> bool:
        email = email.strip().lower()
        with self._conn() as c:
            return bool(c.execute("SELECT 1 FROM blocked WHERE key IN (?, ?)",
                                  (email, domain_of(email))).fetchone())

    def known_domains(self) -> list[str]:
        with self._conn() as c:
            rows = c.execute("SELECT domain FROM leads UNION SELECT key FROM blocked").fetchall()
        return sorted({r[0] for r in rows if r[0] and r[0] not in FREEMAIL})

    # ---- vezetők ---------------------------------------------------------

    def add_lead(self, lead: dict) -> int | None:
        email = lead["email"].strip().lower()
        with self._lock, self._conn() as c:
            try:
                cur = c.execute(
                    """INSERT INTO leads (created_at, company, town, country, lang, website, domain, email,
                       email_url, observation, observation_url, pain, subject, body, warnings, status,
                       sector, signal, signal_note, signal_url, score, score_reason, critique, lang2)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'draft', ?,?,?,?,?,?,?,?)""",
                    (now(), lead["company"], lead.get("town"), lead["country"], lead["lang"],
                     lead.get("website"), domain_of(email if domain_of(email) not in FREEMAIL
                                                     else lead.get("website") or email),
                     email, lead.get("email_url"), lead.get("observation"), lead.get("observation_url"),
                     lead["pain"], lead.get("subject"), lead.get("body"), lead.get("warnings"),
                     lead.get("sector"), lead.get("signal"), lead.get("signal_note"), lead.get("signal_url"),
                     _int(lead.get("score")), lead.get("score_reason"), lead.get("critique"), lead.get("lang2")))
                return cur.lastrowid
            except sqlite3.IntegrityError:
                return None

    def get(self, lead_id: int) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
            return dict(r) if r else None

    def list(self, status: str | None = None) -> list[dict]:
        with self._conn() as c:
            if status == "draft":
                rows = c.execute("SELECT * FROM leads WHERE status = ? ORDER BY COALESCE(score, 0) DESC, id DESC",
                                 (status,))
            elif status:
                rows = c.execute("SELECT * FROM leads WHERE status = ? ORDER BY id DESC", (status,))
            else:
                rows = c.execute("SELECT * FROM leads ORDER BY id DESC")
            return [dict(r) for r in rows]

    def edit(self, lead_id: int, subject: str, body: str) -> bool:
        with self._conn() as c:
            cur = c.execute("UPDATE leads SET subject = ?, body = ? WHERE id = ? AND status IN ('draft','failed')",
                            (subject, body, lead_id))
            return cur.rowcount == 1

    def skip(self, lead_id: int) -> bool:
        with self._conn() as c:
            cur = c.execute("UPDATE leads SET status = 'skipped' WHERE id = ? AND status IN ('draft','failed')",
                            (lead_id,))
            return cur.rowcount == 1

    def claim_for_send(self, lead_id: int) -> bool:
        """Egyetlen feltételes UPDATE: csak az egyik hívó nyer."""
        with self._conn() as c:
            cur = c.execute("UPDATE leads SET status = 'sending', last_error = NULL "
                            "WHERE id = ? AND status IN ('draft','failed')", (lead_id,))
            return cur.rowcount == 1

    def mark_sent(self, lead_id: int, message_id: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE leads SET status = 'sent', sent_at = ?, message_id = ? WHERE id = ?",
                      (now(), message_id, lead_id))

    def mark_sent_manual(self, lead_id: int) -> bool:
        """A levelet ember küldte el a saját Gmailjéből; innentől ugyanúgy
        figyeljük a válaszát, mintha a program küldte volna."""
        with self._conn() as c:
            cur = c.execute("UPDATE leads SET status = 'sent', sent_at = ?, last_error = NULL "
                            "WHERE id = ? AND status IN ('draft','failed')", (now(), lead_id))
            return cur.rowcount == 1

    def followup_sent_manual(self, lead_id: int) -> bool:
        with self._conn() as c:
            cur = c.execute("UPDATE leads SET followup_status = 'sent', followup_sent_at = ? "
                            "WHERE id = ? AND followup_status = 'draft'", (now(), lead_id))
            return cur.rowcount == 1

    def mark_failed(self, lead_id: int, error: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE leads SET status = 'failed', last_error = ? WHERE id = ?", (error[:500], lead_id))

    def stats(self) -> dict:
        """Kiment / válaszolt / érdeklődik, iparág, ország és igény szerint."""
        out = {}
        with self._conn() as c:
            for dim in ("sector", "country", "pain", "signal"):
                rows = c.execute(f"""SELECT COALESCE({dim}, '?') AS k,
                        SUM(status = 'sent') AS sent,
                        SUM(status = 'sent' AND reply_kind IN ('interested','no','other')) AS replied,
                        SUM(reply_kind = 'interested') AS interested,
                        SUM(reply_kind = 'no') AS no,
                        SUM(reply_kind = 'bounce') AS bounced
                        FROM leads GROUP BY k ORDER BY sent DESC""").fetchall()
                out[dim] = [dict(r) for r in rows]
            t = c.execute("""SELECT SUM(status='sent') AS sent,
                        SUM(status='sent' AND reply_kind IN ('interested','no','other')) AS replied,
                        SUM(reply_kind='interested') AS interested, SUM(status='draft') AS drafts,
                        SUM(followup_status='sent') AS followups FROM leads""").fetchone()
            out["total"] = {k: (t[k] or 0) for k in t.keys()}
        return out

    def best_sectors(self, min_sent: int = 5, top: int = 2) -> list[str]:
        """A tanulás: ahol legalább min_sent levél kiment, a válaszarány
        szerint a legjobbak. Kevés adatnál üres — akkor mindent egyformán keres."""
        rows = [r for r in self.stats()["sector"] if (r["sent"] or 0) >= min_sent and r["k"] != "?"]
        rows.sort(key=lambda r: ((r["interested"] or 0) * 3 + (r["replied"] or 0)) / r["sent"], reverse=True)
        return [r["k"] for r in rows[:top]]

    def sent_today(self) -> int:
        today = datetime.now(timezone.utc).date().isoformat()
        with self._conn() as c:
            a = c.execute("SELECT COUNT(*) FROM leads WHERE sent_at LIKE ?", (today + "%",)).fetchone()[0]
            b = c.execute("SELECT COUNT(*) FROM leads WHERE followup_sent_at LIKE ?", (today + "%",)).fetchone()[0]
        return a + b

    # ---- utánkövetés -----------------------------------------------------

    def set_followup_draft(self, lead_id: int, body: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE leads SET followup_status = 'draft', followup_body = ? "
                      "WHERE id = ? AND followup_status = 'none'", (body, lead_id))

    def claim_followup(self, lead_id: int) -> bool:
        with self._conn() as c:
            cur = c.execute("UPDATE leads SET followup_status = 'sending' "
                            "WHERE id = ? AND followup_status = 'draft' AND reply_kind = 'none'", (lead_id,))
            return cur.rowcount == 1

    def followup_done(self, lead_id: int, ok: bool, error: str = "") -> None:
        with self._conn() as c:
            if ok:
                c.execute("UPDATE leads SET followup_status = 'sent', followup_sent_at = ? WHERE id = ?",
                          (now(), lead_id))
            else:
                c.execute("UPDATE leads SET followup_status = 'draft', last_error = ? WHERE id = ?",
                          (error[:500], lead_id))

    def drop_followup(self, lead_id: int) -> None:
        with self._conn() as c:
            c.execute("UPDATE leads SET followup_status = 'dropped' WHERE id = ? AND followup_status = 'draft'",
                      (lead_id,))

    # ---- válaszok ----------------------------------------------------------

    def set_suggestion(self, lead_id: int, suggestion: str, slots_json: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE leads SET reply_suggestion = ?, slots = ? WHERE id = ?",
                      (suggestion[:4000], slots_json, lead_id))

    def set_reply(self, lead_id: int, kind: str, text: str, suggestion: str = "") -> None:
        with self._conn() as c:
            c.execute("UPDATE leads SET reply_kind = ?, reply_text = ?, reply_suggestion = ?, reply_at = ?, "
                      "followup_status = CASE WHEN ? != 'auto' AND followup_status IN ('none','draft') "
                      "THEN 'dropped' ELSE followup_status END WHERE id = ?",
                      (kind, text[:4000], suggestion[:4000], now(), kind, lead_id))
        if kind in ("no", "bounce"):
            lead = self.get(lead_id)
            if lead:
                self.block(lead["email"], "nem kér" if kind == "no" else "visszapattant")


FREEMAIL = {"gmail.com", "googlemail.com", "freemail.hu", "citromail.hu", "t-online.hu", "yahoo.com",
            "outlook.com", "hotmail.com", "outlook.hu", "azet.sk", "centrum.sk", "zoznam.sk", "yahoo.ro",
            "gmail.hr", "net.hr", "siol.net", "icloud.com", "mail.com"}


def _int(v):
    try:
        return max(0, min(100, int(v)))
    except (TypeError, ValueError):
        return None
