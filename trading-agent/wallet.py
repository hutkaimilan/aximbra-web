"""Saját tárca: szabad pénz, amit a két számla (kripto, illetve részvény és világpiac) és a tárca között
lehet mozgatni (Betesz / Kivesz). A számla eredményét a mozgatás nem torzítja: a készpénz és a kezdőtőke
együtt mozog. A bot 0–24 figyeli a számlákat, és szól, ha egy számla a csúcsától nagyot esett.

A régebbi funkciók (vétel/eladás a tárcából, figyelőlista, előrejelzés) az API-ban megmaradtak.

A tárca a te pénzed nyilvántartása (könyvelés), nem tőzsdei megbízás: a bot nem utal és nem köt a
nevedben, a valódi számládhoz nem nyúl. Vételnél a tárca egyenlegéből levonja az összeget, eladásnál
jóváírja. A bot folyamatosan figyeli a tárcában lévő és a figyelt eszközöket, és szól (push, e-mail,
élő felület), ha teendő van: vétel javasolt összeggel, eladás, vagy pénz betétele / kivétele.

Előrejelzés: a bot nem tudja biztosan, mi lesz. Amit tud: megnézi, hogy az elmúlt ~2 évben a mostanihoz
hasonló helyzetekben (trend, lendület) az ár hányszor volt magasabban 5 és 20 nap múlva, és mennyivel.
Ez gyakoriság a múltból, nem garancia — és így is írja ki.

Pénzügyi szabályok kódban (a nyelvi modell nem írhatja felül):
- egy vétel kockázata (a javasolt stopig) legfeljebb a tárca teljes értékének RISK_PCT része;
- egy eszköz legfeljebb a tárca MAX_POS_FRAC részét kaphatja;
- eladás, ha a záróár a követő stop alá esik (vétel −2 ATR, a csúcs óta legfeljebb −3 ATR), vagy a trend megtörik.
"""
from __future__ import annotations

import json
import logging
import math
import re
import threading
import time
from dataclasses import dataclass

import strategy
from market import MarketError

logger = logging.getLogger("wallet")

SCHEMA = """
CREATE TABLE IF NOT EXISTS wallet_tx (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  kind TEXT NOT NULL CHECK (kind IN ('deposit', 'withdraw', 'buy', 'sell')),
  symbol TEXT,
  qty REAL,
  price REAL,
  amount REAL NOT NULL,
  note TEXT
);
"""
SYMBOL_RE = re.compile(r"^[A-Z0-9.^=\-]{1,15}$")
MAX_AMOUNT = 1e9
RISK_PCT = 0.02
MAX_POS_FRAC = 0.25
MIN_TRADE = 10.0
STOP_ATR, TRAIL_ATR = 2.0, 3.0
BUY_KINDS = frozenset({"trend_long", "pull_long"})
DEFAULT_WATCH = ("AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AVGO", "JPM", "V", "KO", "WMT",
                 "^GSPC", "GC=F", "BTC-USD", "ETH-USD")
EPS = 1e-9


class WalletError(ValueError):
    """Érvénytelen kérés (pl. több pénz kivétele, mint ami van). A szövege magyarul a felhasználónak szól."""


@dataclass
class Holding:
    symbol: str
    qty: float
    cost: float              # a megmaradt darabok beszerzési értéke (átlagár-módszer)
    first_buy: str           # az első (még nyitott) vétel ideje, ISO

    @property
    def avg(self) -> float:
        return self.cost / self.qty if self.qty > EPS else 0.0


def _now_iso(clock) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(clock()))


def _usd(x: float) -> str:
    """1234.5 → "1 234,50 $" (magyar írásmód)."""
    return f"{x:,.2f}".replace(",", " ").replace(".", ",") + " $"


def _amount(x, what: str = "összeg") -> float:
    try:
        v = float(x)
    except (TypeError, ValueError):
        raise WalletError(f"az {what} nem szám") from None
    if not math.isfinite(v) or v <= 0:
        raise WalletError(f"az {what} legyen pozitív szám")
    if v > MAX_AMOUNT:
        raise WalletError(f"az {what} túl nagy")
    return v


def _symbol(s) -> str:
    sym = str(s or "").strip().upper()
    if not SYMBOL_RE.match(sym):
        raise WalletError("érvénytelen jelölés (pl. AAPL, BTC-USD, ^GSPC)")
    return sym


class Wallet:
    def __init__(self, store, market, notify, clock=time.time, watch: tuple[str, ...] = DEFAULT_WATCH,
                 accounts: dict | None = None):
        """store: Store (a SQLite-kapcsolatát használja); market: candles()/price() — Yahoo-jelölésekkel;
        notify(text, kind=..., push=...) — a bot meglévő értesítő csatornái."""
        self.store, self.market, self.notify, self.clock = store, market, notify, clock
        self.default_watch = tuple(watch)
        # számlák, amelyekre a tárcából pénzt lehet tenni: {"crypto": (név, agent), "world": (név, agent)}
        self.accounts = dict(accounts or {})
        self._lock = threading.RLock()          # a pénzmozgások sorban, egyszerre egy
        with store._lock, store._conn:
            store._conn.executescript(SCHEMA)

    # --- könyvelés -------------------------------------------------------------
    def _rows(self) -> list[dict]:
        with self.store._lock:
            rows = self.store._conn.execute("SELECT * FROM wallet_tx ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def _insert(self, kind: str, amount: float, symbol=None, qty=None, price=None, note=None) -> int:
        with self.store._lock, self.store._conn:
            cur = self.store._conn.execute(
                "INSERT INTO wallet_tx(created_at, kind, symbol, qty, price, amount, note) VALUES (?,?,?,?,?,?,?)",
                (_now_iso(self.clock), kind, symbol, qty, price, amount, note))
            return int(cur.lastrowid)

    def ledger(self) -> tuple[float, dict[str, Holding], float]:
        """(egyenleg, nyitott tételek, realizált eredmény) a teljes naplóból."""
        bal, hold, realized = 0.0, {}, 0.0
        for r in self._rows():
            k, amt = r["kind"], float(r["amount"])
            if k == "deposit":
                bal += amt
            elif k == "withdraw":
                bal -= amt
            elif k == "buy":
                bal -= amt
                h = hold.get(r["symbol"])
                if h is None or h.qty <= EPS:
                    hold[r["symbol"]] = Holding(r["symbol"], float(r["qty"]), amt, r["created_at"])
                else:
                    h.qty += float(r["qty"])
                    h.cost += amt
            elif k == "sell":
                bal += amt
                h = hold[r["symbol"]]
                q = float(r["qty"])
                part = h.cost * (q / h.qty) if h.qty > EPS else 0.0
                realized += amt - part
                h.qty -= q
                h.cost -= part
                if h.qty <= EPS:
                    del hold[r["symbol"]]
        return bal, hold, realized

    def balance(self) -> float:
        return self.ledger()[0]

    def deposit(self, amount, note: str | None = None) -> dict:
        amt = _amount(amount)
        with self._lock:
            self._insert("deposit", amt, note=note)
            return self.summary(prices={})

    def withdraw(self, amount, note: str | None = None) -> dict:
        amt = _amount(amount)
        with self._lock:
            bal = self.balance()
            if amt > bal + EPS:
                raise WalletError(f"nincs ennyi szabad pénz a tárcában (szabad: {bal:,.2f} $)")
            self._insert("withdraw", amt, note=note)
            return self.summary(prices={})

    def transfer(self, account: str, direction: str, amount) -> dict:
        """Pénz a tárca és egy számla között. direction: "in" = a tárcából a számlára, "out" = a számláról a tárcába.
        Számlára csak a tárca szabad egyenlegéből, számláról csak a számla szabad (nem pozícióban lévő) készpénzéből."""
        if account not in self.accounts:
            raise WalletError("ismeretlen számla")
        if direction not in ("in", "out"):
            raise WalletError("ismeretlen irány")
        amt = _amount(amount)
        name, ag = self.accounts[account]
        with self._lock:
            if direction == "in":
                bal = self.balance()
                if amt > bal + EPS:
                    raise WalletError(f"a tárcában csak {_usd(bal)} szabad pénz van")
                tx = self._insert("withdraw", amt, note=f"→ {name}")
                try:
                    ag.store.move_capital(amt)
                except Exception:
                    with self.store._lock, self.store._conn:      # visszavonás: a pénz nem veszhet el
                        self.store._conn.execute("DELETE FROM wallet_tx WHERE id = ?", (tx,))
                    raise
            else:
                if not ag.store.move_capital(-amt):
                    raise WalletError(f"a(z) {name} számlán csak {_usd(ag.store.cash())} szabad készpénz van "
                                      "(a többi nyitott pozícióban áll)")
                self._insert("deposit", amt, note=f"← {name}")
        return {"wallet": self.balance(), "account": ag.store.cash()}

    def return_all(self) -> dict:
        """A tárcában álló pénzből annyit visszatesz az egyes számlákra, amennyit onnan áttettek
        (a „← név” és „→ név” megjegyzésű mozgások egyenlege). A kézzel betett pénzhez nem nyúl."""
        moved = {}
        with self._lock:
            rows = self._rows()
            left = self.balance()
            for key, (name, _ag) in self.accounts.items():
                net = sum(float(r["amount"]) for r in rows if r["kind"] == "deposit" and r["note"] == f"← {name}") \
                    - sum(float(r["amount"]) for r in rows if r["kind"] == "withdraw" and r["note"] == f"→ {name}")
                amt = round(min(net, left), 2)
                if amt >= 0.01:
                    self.transfer(key, "in", amt)
                    left -= amt
                    moved[key] = amt
        return {"moved": moved, "wallet": self.balance()}

    def _price(self, sym: str, price=None) -> float:
        if price is not None:
            return _amount(price, "ár")
        try:
            return float(self.market.price(sym))
        except MarketError as e:
            raise WalletError(f"{sym}: nincs aktuális ár ({e})") from None

    def buy(self, symbol, amount, price=None, note: str | None = None) -> dict:
        """`amount` dollárért vesz `symbol`-ból; az összeg levonódik az egyenlegből."""
        sym, amt = _symbol(symbol), _amount(amount)
        px = self._price(sym, price)
        with self._lock:
            bal = self.balance()
            if amt > bal + EPS:
                raise WalletError(f"nincs ennyi szabad pénz a tárcában (szabad: {bal:,.2f} $). "
                                  "Előbb tegyél be pénzt.")
            self._insert("buy", amt, sym, amt / px, px, note)
            return self.summary(prices={sym: px})

    def sell(self, symbol, qty=None, price=None, note: str | None = None) -> dict:
        """Elad `qty` darabot (alapból mindet); az ellenérték jóváíródik az egyenlegen."""
        sym = _symbol(symbol)
        px = self._price(sym, price)
        with self._lock:
            h = self.ledger()[1].get(sym)
            if h is None:
                raise WalletError(f"{sym}: nincs a tárcában")
            q = h.qty if qty is None else _amount(qty, "darabszám")
            if q > h.qty + EPS:
                raise WalletError(f"{sym}: csak {h.qty:.6g} darab van a tárcában")
            q = min(q, h.qty)
            self._insert("sell", q * px, sym, q, px, note)
            return self.summary(prices={sym: px})

    # --- figyelőlista ------------------------------------------------------------
    def watchlist(self) -> list[str]:
        raw = self.store.get("wallet:watch")
        return json.loads(raw) if raw else list(self.default_watch)

    def set_watchlist(self, symbols) -> list[str]:
        syms = list(dict.fromkeys(_symbol(s) for s in symbols))[:60]
        self.store.set("wallet:watch", json.dumps(syms))
        return syms

    # --- állapot -------------------------------------------------------------------
    def summary(self, prices: dict[str, float] | None = None) -> dict:
        bal, hold, realized = self.ledger()
        prices = dict(prices or {})
        items, invested_now = [], 0.0
        for h in hold.values():
            px = prices.get(h.symbol)
            if px is None:
                try:
                    px = float(self.market.price(h.symbol))
                except MarketError:
                    px = None
            value = h.qty * px if px is not None else h.cost
            invested_now += value
            items.append({"symbol": h.symbol, "qty": h.qty, "avg": h.avg, "cost": h.cost, "price": px,
                          "value": value, "pnl": value - h.cost if px is not None else None,
                          "pnl_pct": (value / h.cost - 1) * 100 if px is not None and h.cost > 0 else None})
        net_in = sum(float(r["amount"]) * (1 if r["kind"] == "deposit" else -1)
                     for r in self._rows() if r["kind"] in ("deposit", "withdraw"))
        total = bal + invested_now
        return {"balance": bal, "invested": invested_now, "total": total, "net_deposits": net_in,
                "pnl": total - net_in, "realized": realized,
                "holdings": sorted(items, key=lambda x: -x["value"])}

    def transactions(self, limit: int = 100) -> list[dict]:
        return list(reversed(self._rows()))[:limit]

    # --- előrejelzés (múltbeli gyakoriság) -------------------------------------------
    @staticmethod
    def _state(f, s, r, c, i) -> str | None:
        if None in (f[i], s[i], r[i]):
            return None
        return ("fel" if c[i] > r[i] else "le") + ("+" if f[i] > s[i] else "-")

    def outlook(self, symbol, candles=None) -> dict:
        """A mostani helyzethez hasonló múltbeli napokon mi történt 5 és 20 nap múlva."""
        sym = _symbol(symbol)
        cs = candles if candles is not None else self.market.candles(sym, "1d", limit=600)
        if len(cs) < strategy.MIN_BARS + 25:
            raise WalletError(f"{sym}: kevés adat az előrejelzéshez")
        ind = strategy.compute(cs)
        f, s, r, c = ind["fast"], ind["slow"], ind["regime"], ind["close"]
        n = len(c)
        now = self._state(f, s, r, c, n - 1)
        if now is None:
            raise WalletError(f"{sym}: kevés adat az előrejelzéshez")
        out = {"symbol": sym, "price": c[-1], "state": now, "state_hu": {
            "fel+": "emelkedő trend, erősödő lendület", "fel-": "emelkedő trend, gyengülő lendület",
            "le+": "eső trend, éledő lendület", "le-": "eső trend, gyengülő lendület"}[now], "horizons": []}
        for hz in (5, 20):
            rets = [c[i + hz] / c[i] - 1 for i in range(n - hz) if self._state(f, s, r, c, i) == now]
            if len(rets) < 15:
                out["horizons"].append({"days": hz, "n": len(rets), "up_pct": None, "median_pct": None})
                continue
            srt = sorted(rets)
            out["horizons"].append({
                "days": hz, "n": len(rets),
                "up_pct": round(100 * sum(1 for x in rets if x > 0) / len(rets), 1),
                "median_pct": round(100 * srt[len(srt) // 2], 2),
                "low_pct": round(100 * srt[len(srt) // 10], 2),        # a legrosszabb 10% határa
                "high_pct": round(100 * srt[len(srt) * 9 // 10], 2)})  # a legjobb 10% határa
        h20 = out["horizons"][-1]
        if h20["up_pct"] is None:
            out["text"] = "Kevés hasonló múltbeli eset: nem mondok számot."
        else:
            out["text"] = (f"Az elmúlt ~2 évben {h20['n']} hasonló napon az ár 20 nap múlva {h20['up_pct']:.0f}%-ban "
                           f"volt magasabban (medián {h20['median_pct']:+.1f}%, a rossz esetek −10%-a "
                           f"{h20['low_pct']:+.1f}% alatt). Gyakoriság a múltból, nem garancia.")
        return out

    # --- a bot figyel és tanácsol ------------------------------------------------------
    def _once(self, key: str) -> bool:
        k = "wallet:sent:" + key
        if self.store.get(k):
            return False
        self.store.set(k, int(self.clock()))
        return True

    @staticmethod
    def _stop_for(h: Holding, cs, ind) -> float | None:
        a = ind["atr"][-1]
        if not a:
            return None
        closes_since = [c.close for c in cs if time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(c.close_time / 1000))
                        >= h.first_buy]
        hi = max(closes_since) if closes_since else h.avg
        return max(h.avg - STOP_ATR * a, hi - TRAIL_ATR * a)

    def scan(self) -> list[str]:
        """Figyelőkör: ha egy számla értéke a csúcsától 10%-nál többet esett, egyszer szól (csúcsonként),
        hogy érdemes-e pénzt kivenni a tárcába. A számlák saját kötéseiről a bot külön értesít."""
        sent = []
        for key, (name, ag) in self.accounts.items():
            try:
                eq = ag.equity(ag._prices([p.symbol for p in ag.store.open_positions()], {}))
            except Exception:
                logger.exception("tárca: a(z) %s számla értéke nem számolható", name)
                continue
            # A betét/kivét ne számítson esésnek: a csúcsot a kezdőtőkéhez mért eredményen követjük.
            res = eq - ag.store.start_equity()
            pk = f"wallet:peak:{key}"
            peak = float(self.store.get(pk, "nan"))
            if math.isnan(peak) or res > peak:
                self.store.set(pk, res)
                self.store.delete(f"wallet:dd:{key}")
                continue
            drop = peak - res
            if eq > 0 and drop > 0.10 * eq and not self.store.get(f"wallet:dd:{key}"):
                self.store.set(f"wallet:dd:{key}", int(self.clock()))
                msg = (f"⚠️ TEENDŐ? A(z) {name} számla a csúcsa óta {drop:,.0f} $-t esett (most {eq:,.0f} $).\n"
                       "Ha óvatosabb lennél, a Kivesz gombbal tegyél át pénzt a tárcába; a nyitott pozíciókat a bot "
                       "a védőszinteknél magától zárja.")
                self.notify(msg, kind="wallet", push=5)
                sent.append(msg)
        return sent

    def _check_drawdown(self, summ: dict) -> None:
        """Ha a tárca befektetett része a csúcsától 10%-nál többet esett, egyszer szól (csúcsonként)."""
        inv = summ["invested"]
        peak = float(self.store.get("wallet:peak_invested", "0") or 0)
        if inv > peak or not summ["holdings"]:
            self.store.set("wallet:peak_invested", inv)
            self.store.delete("wallet:dd_alerted")
            return
        if peak > 0 and inv < peak * 0.9 and not self.store.get("wallet:dd_alerted"):
            self.store.set("wallet:dd_alerted", int(self.clock()))
            worst = min(summ["holdings"], key=lambda x: x["pnl_pct"] if x["pnl_pct"] is not None else 0)
            self.notify(f"⚠️ A befektetéseid a csúcsuk óta {inv / peak - 1:.1%}-ot estek ({peak:,.0f} → {inv:,.0f} $).\n"
                        f"Leggyengébb: {worst['symbol']} ({(worst['pnl_pct'] or 0):+.1f}%). "
                        "Gondold át, mennyit akarsz bent tartani; a védőszint alatti tételekről külön szólok.",
                        kind="wallet", push=5)
