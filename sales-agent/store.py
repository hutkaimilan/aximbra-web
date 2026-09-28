"""A napló: kinek írtunk, mit, mikor, mit válaszolt, ki nem kér többet.

SQLite, mert egy felhasználó és egy folyamat van; a kötet a Railway-en
megmarad az újraindítások között. Minden állapotváltás egyetlen feltételes
UPDATE, így két párhuzamos kérés sem tud ugyanarra a levélre kétszer
"küldést" indítani.
"""
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
CREATE TABLE IF NOT EXISTS blocked (
  key TEXT PRIMARY KEY,           -- e-mail cím vagy domain, kisbetűvel
  reason TEXT,
  created_at TEXT NOT NULL
);
"""

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

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
        finally:
            conn.close()

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
                       email_url, observation, observation_url, pain, subject, body, warnings, status)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'draft')""",
                    (now(), lead["company"], lead.get("town"), lead["country"], lead["lang"],
                     lead.get("website"), domain_of(email if domain_of(email) not in FREEMAIL
                                                     else lead.get("website") or email),
                     email, lead.get("email_url"), lead.get("observation"), lead.get("observation_url"),
                     lead["pain"], lead.get("subject"), lead.get("body"), lead.get("warnings")))
                return cur.lastrowid
            except sqlite3.IntegrityError:
                return None

    def get(self, lead_id: int) -> dict | None:
        with self._conn() as c:
            r = c.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
            return dict(r) if r else None

    def list(self, status: str | None = None) -> list[dict]:
        with self._conn() as c:
            if status:
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
