"""A napló és a papírszámla: SQLite, egy folyamat, Railway-kötetre mentve.

Az újraindítás nem veszít állapotot (nyitott pozíció, készpénz, feldolgozott
jelzések). A kettős végrehajtás ellen két zár véd az adatbázis szintjén:
- egy jelzés (instrumentum, gyertya, irány) csak egyszer kerülhet be;
- instrumentumonként legfeljebb egy nyitott pozíció lehet (részleges egyedi index).
A pozíció zárása feltételes UPDATE (`status='open'`), így két szál sem tudja
ugyanazt kétszer lezárni és kétszer jóváírni.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from dataclasses import dataclass
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS positions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  symbol TEXT NOT NULL,
  qty REAL NOT NULL,
  entry_price REAL NOT NULL,
  entry_fee REAL NOT NULL,
  stop REAL NOT NULL,
  target REAL NOT NULL,
  risk_amount REAL NOT NULL,
  entry_candle INTEGER NOT NULL,
  opened_at TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  exit_price REAL,
  exit_fee REAL,
  exit_reason TEXT,
  closed_at TEXT,
  pnl REAL,
  r_multiple REAL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_per_symbol ON positions(symbol) WHERE status = 'open';
CREATE INDEX IF NOT EXISTS positions_closed_at ON positions(closed_at);
CREATE TABLE IF NOT EXISTS signals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  symbol TEXT NOT NULL,
  candle_time INTEGER NOT NULL,
  action TEXT NOT NULL,
  price REAL NOT NULL,
  reason TEXT NOT NULL,
  outcome TEXT,
  UNIQUE (symbol, candle_time, action)
);
CREATE TABLE IF NOT EXISTS kv (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT
);
CREATE TABLE IF NOT EXISTS news (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  link TEXT NOT NULL UNIQUE,
  source TEXT NOT NULL,
  title TEXT NOT NULL,
  published TEXT,
  seen_at TEXT NOT NULL,
  analysis TEXT
);
CREATE TABLE IF NOT EXISTS equity_log (
  ts INTEGER PRIMARY KEY,
  equity REAL NOT NULL,
  cash REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chat (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  role TEXT NOT NULL,
  content TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Position:
    id: int
    symbol: str
    qty: float
    entry_price: float
    entry_fee: float
    stop: float
    target: float
    risk_amount: float
    entry_candle: int
    opened_at: str
    status: str
    exit_price: float | None
    exit_fee: float | None
    exit_reason: str | None
    closed_at: str | None
    pnl: float | None
    r_multiple: float | None
    stop_cid: str | None = None
    side: int = 1          # 1: long (emelkedésre), -1: short (esésre)
    kind: str = "trend"


class Store:
    def __init__(self, path: str, start_equity: float):
        if path != ":memory:":
            directory = os.path.dirname(os.path.abspath(path))
            try:
                os.makedirs(directory, exist_ok=True)
            except OSError as e:
                raise RuntimeError(f"az adatbázis mappája nem hozható létre ({directory}): {e}") from e
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            if path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)
            # Régebbi adatbázisokhoz: a tőzsdei stop megbízásának azonosítója.
            cols = {r["name"] for r in self._conn.execute("PRAGMA table_info(positions)")}
            if "stop_cid" not in cols:
                self._conn.execute("ALTER TABLE positions ADD COLUMN stop_cid TEXT")
            if "side" not in cols:
                self._conn.execute("ALTER TABLE positions ADD COLUMN side INTEGER NOT NULL DEFAULT 1")
            if "kind" not in cols:
                self._conn.execute("ALTER TABLE positions ADD COLUMN kind TEXT NOT NULL DEFAULT 'trend'")
            # Csak az első induláskor: a meglévő számla kezdőtőkéjét nem írja felül.
            self._conn.execute("INSERT OR IGNORE INTO kv(key, value) VALUES ('cash', ?)", (repr(float(start_equity)),))
            self._conn.execute("INSERT OR IGNORE INTO kv(key, value) VALUES ('start_equity', ?)",
                               (repr(float(start_equity)),))

    # --- kulcs-érték ---------------------------------------------------------
    def get(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO kv(key, value) VALUES (?, ?) "
                               "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))

    def delete(self, key: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM kv WHERE key = ?", (key,))

    def get_prefix(self, prefix: str) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM kv WHERE key LIKE ?", (prefix + "%",)).fetchall()
        return {r["key"][len(prefix):]: r["value"] for r in rows}

    def cash(self) -> float:
        return float(self.get("cash", "0"))

    def start_equity(self) -> float:
        return float(self.get("start_equity", "0"))

    # --- jelzések ------------------------------------------------------------
    def record_signal(self, symbol: str, candle_time: int, action: str, price: float, reason: str) -> bool:
        """True, ha új; False, ha ezt a jelzést már feldolgoztuk (újraindulás, ismételt ciklus)."""
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT OR IGNORE INTO signals(created_at, symbol, candle_time, action, price, reason) "
                "VALUES (?, ?, ?, ?, ?, ?)", (now_iso(), symbol, candle_time, action, price, reason))
            return cur.rowcount == 1

    def set_signal_outcome(self, symbol: str, candle_time: int, action: str, outcome: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE signals SET outcome = ? WHERE symbol = ? AND candle_time = ? AND action = ?",
                               (outcome, symbol, candle_time, action))

    def recent_signals(self, limit: int = 10) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM signals ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # --- pozíciók ------------------------------------------------------------
    def open_position(self, symbol: str, qty: float, entry_price: float, entry_fee: float, stop: float,
                      target: float, entry_candle: int, stop_cid: str | None = None,
                      force: bool = False, side: int = 1, kind: str = "trend") -> int | None:
        """Megnyitja a pozíciót és levonja a költséget. None, ha már van nyitott
        pozíció ezen az instrumentumon, vagy nincs rá fedezet. force: a tőzsdén már
        teljesült vételt mindenképp könyvelni kell, a napló fedezete ilyenkor nem dönthet."""
        # Long: a vételár és a díj megy ki. Short: az eladás bevétele bejön, a díj kimegy;
        # a visszavásárlás a záráskor terheli a számlát.
        cost = qty * entry_price + entry_fee if side == 1 else entry_fee - qty * entry_price
        with self._lock:
            try:
                with self._conn:
                    cash = float(self._conn.execute("SELECT value FROM kv WHERE key = 'cash'").fetchone()["value"])
                    if side == 1 and cost > cash + 1e-9 and not force:
                        return None
                    cur = self._conn.execute(
                        "INSERT INTO positions(symbol, qty, entry_price, entry_fee, stop, target, risk_amount, "
                        "entry_candle, opened_at, stop_cid, side, kind) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (symbol, qty, entry_price, entry_fee, stop, target, qty * abs(entry_price - stop),
                         entry_candle, now_iso(), stop_cid, side, kind))
                    self._conn.execute("UPDATE kv SET value = ? WHERE key = 'cash'", (repr(cash - cost),))
                    return cur.lastrowid
            except sqlite3.IntegrityError:
                return None

    def close_position(self, pos_id: int, exit_price: float, exit_fee: float, reason: str, pnl: float) -> bool:
        with self._lock, self._conn:
            row = self._conn.execute("SELECT qty, risk_amount, side FROM positions WHERE id = ? AND status = 'open'",
                                     (pos_id,)).fetchone()
            if row is None:
                return False
            r_multiple = pnl / row["risk_amount"] if row["risk_amount"] > 0 else None
            cur = self._conn.execute(
                "UPDATE positions SET status = 'closed', exit_price = ?, exit_fee = ?, exit_reason = ?, "
                "closed_at = ?, pnl = ?, r_multiple = ? WHERE id = ? AND status = 'open'",
                (exit_price, exit_fee, reason, now_iso(), pnl, r_multiple, pos_id))
            if cur.rowcount != 1:
                return False
            # Long: eladás bevétele. Short: visszavásárlás költsége (negatív).
            proceeds = (row["qty"] * exit_price - exit_fee) if row["side"] == 1 else -(row["qty"] * exit_price + exit_fee)
            self._conn.execute("UPDATE kv SET value = CAST(CAST(value AS REAL) + ? AS TEXT) WHERE key = 'cash'",
                               (proceeds,))
            return True

    def set_stop_cid(self, pos_id: int, cid: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE positions SET stop_cid = ? WHERE id = ?", (cid, pos_id))

    def _positions(self, where: str, params: tuple = ()) -> list[Position]:
        with self._lock:
            rows = self._conn.execute(f"SELECT * FROM positions WHERE {where}", params).fetchall()
        return [Position(**dict(r)) for r in rows]

    def open_positions(self) -> list[Position]:
        return self._positions("status = 'open' ORDER BY id")

    def open_position_for(self, symbol: str) -> Position | None:
        found = self._positions("status = 'open' AND symbol = ?", (symbol,))
        return found[0] if found else None

    def get_position(self, pos_id: int) -> Position | None:
        found = self._positions("id = ?", (pos_id,))
        return found[0] if found else None

    def closed_since(self, iso: str) -> list[Position]:
        return self._positions("status = 'closed' AND closed_at >= ? ORDER BY closed_at", (iso,))

    def closed_positions(self, limit: int | None = None) -> list[Position]:
        if limit is None:
            return self._positions("status = 'closed' ORDER BY id DESC")
        return self._positions("status = 'closed' ORDER BY id DESC LIMIT ?", (int(limit),))

    def realized_since(self, iso: str) -> float:
        return sum(p.pnl or 0.0 for p in self.closed_since(iso))

    # --- események (az élő felület hírfolyama) ---------------------------------
    def add_event(self, kind: str, title: str, body: str = "") -> int:
        with self._lock, self._conn:
            cur = self._conn.execute("INSERT INTO events(created_at, kind, title, body) VALUES (?, ?, ?, ?)",
                                     (now_iso(), kind, title[:300], body[:4000]))
            self._conn.execute("DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 1000)")
            return cur.lastrowid

    def events_after(self, after_id: int = 0, limit: int = 100) -> list[dict]:
        with self._lock:
            if after_id:
                rows = self._conn.execute("SELECT * FROM events WHERE id > ? ORDER BY id LIMIT ?",
                                          (after_id, limit)).fetchall()
            else:
                rows = list(reversed(self._conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?",
                                                        (limit,)).fetchall()))
        return [dict(r) for r in rows]

    # --- egyenleg-idősor ----------------------------------------------------------
    def log_equity(self, ts: int, equity: float, cash: float) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT OR REPLACE INTO equity_log(ts, equity, cash) VALUES (?, ?, ?)",
                               (int(ts), equity, cash))
            # 90 nap 5 percenként ~26 ezer sor: ennél régebbit nem tartunk
            self._conn.execute("DELETE FROM equity_log WHERE ts < ?", (int(ts) - 90 * 86400,))

    def equity_history(self, since_ts: int, max_points: int = 300) -> list[tuple[int, float]]:
        with self._lock:
            rows = self._conn.execute("SELECT ts, equity FROM equity_log WHERE ts >= ? ORDER BY ts",
                                      (int(since_ts),)).fetchall()
        rows = [(r["ts"], r["equity"]) for r in rows]
        if len(rows) > max_points:   # egyenletes ritkítás, az utolsó pont mindig marad
            step = len(rows) / max_points
            rows = [rows[int(i * step)] for i in range(max_points - 1)] + [rows[-1]]
        return rows

    # --- hírek -----------------------------------------------------------------
    def add_news(self, link: str, source: str, title: str, published: str | None) -> int | None:
        """Id, ha új hír; None, ha már láttuk."""
        with self._lock, self._conn:
            cur = self._conn.execute("INSERT OR IGNORE INTO news(link, source, title, published, seen_at) "
                                     "VALUES (?, ?, ?, ?, ?)", (link, source, title[:300], published, now_iso()))
            self._conn.execute("DELETE FROM news WHERE id NOT IN (SELECT id FROM news ORDER BY id DESC LIMIT 3000)")
            return cur.lastrowid if cur.rowcount == 1 else None

    def set_news_analysis(self, news_id: int, analysis: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("UPDATE news SET analysis = ? WHERE id = ?", (analysis, news_id))

    def recent_news(self, limit: int = 30) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM news ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # --- beszélgetés ---------------------------------------------------------
    def add_chat(self, role: str, content: str) -> None:
        with self._lock, self._conn:
            self._conn.execute("INSERT INTO chat(created_at, role, content) VALUES (?, ?, ?)",
                               (now_iso(), role, content[:4000]))
            self._conn.execute("DELETE FROM chat WHERE id NOT IN (SELECT id FROM chat ORDER BY id DESC LIMIT 200)")

    def recent_chat(self, limit: int = 10) -> list[dict]:
        with self._lock:
            rows = self._conn.execute("SELECT role, content FROM chat ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in reversed(rows)]
