"""Az agent: figyel, jelez, papíron kereskedik, beszámol, válaszol.

Egy ciklus (tick) instrumentumonként:
1. friss, lezárt gyertyák és aktuális ár; ha az adat elavult vagy nem jön, riaszt és nem tanácsol;
2. a nyitott pozíció stopját és célját az aktuális árhoz méri;
3. ha új gyertya zárult, lefuttatja a stratégiát; a jelzést a kockázati kapu engedi vagy tiltja;
4. minden döntés a naplóba kerül, és Telegramon megy ki — a modell magyarázatával, ha elérhető.

A modell csak szöveget ír. Ha kiesik, minden értesítés a kódolt adatokkal megy ki.
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timedelta, timezone

import backtest
import paper
import strategy
from config import Config
from exchange import ExchangeError, PaperExecutor
from llm import LLMError
from mailer import MailError
from market import Market, MarketError
from store import Position, Store
from telegram import TelegramError

logger = logging.getLogger(__name__)

PAPER = "🧪 PAPÍRKERESKEDÉS — nem valódi pénz"
HELP = (
    "Parancsok:\n"
    "/status — számla, nyitott pozíciók, utolsó jelzések\n"
    "/journal — lezárt kötések és statisztika\n"
    "/backtest [SYMBOL] — visszateszt valódi múltbeli adatokon\n"
    "/radar — világpiaci radar: szokatlan mozgások és friss hírek\n"
    "/vedekezes — minden pozíció azonnali lezárása, új nyitás tiltva\n"
    "/folytat — a védekező mód feloldása\n"
    "/help — ez a lista\n"
    "Bármi mást kérdezhetsz szabad szöveggel is, pl. „mit csinál most a BTC?”"
)


def _usd(x: float) -> str:
    return f"{x:,.2f} USDT"


class Agent:
    def __init__(self, cfg: Config, store: Store, market: Market, bot=None, llm=None, clock=time.time,
                 mailer=None, executor=None, push=None):
        self.cfg = cfg
        self.store = store
        self.market = market
        self.bot = bot
        self.llm = llm
        self.clock = clock
        self.mailer = mailer
        self.push = push
        self.radar = None
        self.peers: list["Agent"] = []           # a többi számla (helyzetképhez, chathez)
        self.kinds: dict[str, set[str]] = {}     # instrumentumonként engedélyezett fogadástípusok
        self.default_kinds: set[str] = {"trend_long"}
        self.stale_seconds: float | None = None  # None: 2 gyertya + 2 perc
        self.batch_checks = False                # True: a gyertyánkénti döntésekből egy összesítő értesítés
        self._checks: list[str] = []
        self.executor = executor or PaperExecutor(cfg.fee, cfg.slippage)
        self.label = PAPER if not self.executor.live else f"🧪 {self.executor.name.upper()}" + (
            " — játékpénz" if "demó" in self.executor.name else " — VALÓDI PÉNZ")

    # --- kifelé --------------------------------------------------------------
    def notify(self, text: str, email: bool = True, kind: str = "trade", push: int | None = 4) -> None:
        """Minden beállított csatornára: élő felület (esemény), telefon (ntfy), Telegram, e-mail.
        Egy csatorna hibája nem akadályozza a többit."""
        title = self._subject(text).removeprefix("Milán Trader Bot — ")
        lines = [l for l in (text or "").splitlines() if l.strip() and l.strip() != self.label]
        try:
            self.store.add_event(kind, title, "\n".join(lines[1:]))
        except Exception:
            logger.exception("az esemény mentése nem sikerült")
        delivered = True   # az élő felületen minden esemény látszik
        if push is None and os.environ.get("PUSH_ALL", "off").lower() == "on":
            push = 2       # minden lépésről szól, a kevésbé fontosakról halkan
        if push is not None and self.push is not None:
            # A link nem fér el olvashatóan az értesítésben: rákoppintva nyílik meg.
            links = [l.strip() for l in lines[1:] if l.strip().startswith("http")]
            body = "\n".join(l for l in lines[1:] if not l.strip().startswith("http"))
            self.push.send(title, body or " ", priority=push, click=links[0] if links else None)
        if self.bot is not None and self.bot.chat_id:
            try:
                self.bot.send(text)
            except TelegramError as e:
                logger.warning("a Telegram-értesítés nem ment ki: %s", e)
        if email and self.mailer is not None and os.environ.get("EMAIL_ALERTS", "on").lower() != "off":
            try:
                self.mailer.send(self._subject(text), text)
            except MailError as e:
                logger.warning("az e-mail nem ment ki: %s", e)
        if not delivered:
            logger.info("értesítés: %s", title)

    def _subject(self, text: str) -> str:
        """A tárgy az első érdemi sor: a mód-jelölés minden levélben ugyanaz."""
        lines = [l.strip() for l in (text or "").splitlines() if l.strip() and l.strip() != self.label]
        return ("Milán Trader Bot — " + lines[0]) if lines else "Milán Trader Bot"

    def _explain(self, task: str, facts: dict) -> str:
        if self.llm is None:
            return ""
        prompt = (f"{task}\n\nAdatok (csak ezekre hivatkozhatsz):\n"
                  f"{json.dumps(facts, ensure_ascii=False, default=str, indent=1)}\n\n"
                  "Legfeljebb 5 mondat, mobilon olvasható, felsorolásjel nélkül.")
        try:
            return self.llm.ask(prompt)[:1500]
        except LLMError as e:
            logger.warning("a magyarázat elmaradt: %s", e)
            return ""

    # --- idő, számla ---------------------------------------------------------
    def _now(self) -> datetime:
        return datetime.fromtimestamp(self.clock(), timezone.utc)

    def _day_start_iso(self) -> str:
        local = self._now().astimezone(self.cfg.tz)
        start = local.replace(hour=0, minute=0, second=0, microsecond=0)
        return start.astimezone(timezone.utc).isoformat(timespec="seconds")

    def _prices(self, symbols, known: dict[str, float]) -> dict[str, float]:
        prices = dict(known)
        for sym in symbols:
            if sym not in prices:
                try:
                    prices[sym] = self.market.price(sym)
                except MarketError as e:
                    logger.warning("%s ára nem érhető el: %s", sym, e)
        return prices

    def equity(self, prices: dict[str, float]) -> float:
        """Készpénz + nyitott pozíciók piaci értéke. Ha egy ár hiányzik, a belépési árral számol."""
        total = self.store.cash()
        for p in self.store.open_positions():
            total += p.side * p.qty * prices.get(p.symbol, p.entry_price)
        return total

    # --- ciklus --------------------------------------------------------------
    def _maybe_force_entry(self, prices: dict[str, float]) -> None:
        """Kézi indítás (FORCE_ENTRY=BTCUSDT): egyszer, a stratégiai jelzés nélkül is nyit egy pozíciót.
        Ugyanazon a kapun megy át, mint a jelzés: kockázati méret, napi limit, tőzsdei stop."""
        sym = os.environ.get("FORCE_ENTRY", "").strip().upper()
        if not sym or sym not in self.cfg.symbols or self.store.get(f"forced:{sym}"):
            return
        self.store.set(f"forced:{sym}", self._now().isoformat(timespec="seconds"))   # előbb jelölünk: egyszer fusson
        if self.store.open_position_for(sym) is not None:
            return
        candles = self.market.candles(sym, self.cfg.interval, limit=300)
        ind = strategy.compute(candles)
        a = ind["atr"][-1] if candles else None
        price = self.market.price(sym)
        if not a:
            self.notify(f"{self.label}\n⚪ {sym}: a kézi indítás nem ment, nincs elég adat az ATR-hez.")
            return
        prices[sym] = price
        sig = strategy.Signal("enter", price, "KÉZI INDÍTÁS (nem stratégiai jelzés): a megbízó kérésére, játékpénzzel",
                              stop=price - strategy.STOP_ATR * a, atr=a)
        self._handle(sym, sig, int(self.clock() * 1000), None, price, prices)

    def tick(self) -> None:
        prices: dict[str, float] = {}
        try:
            self._maybe_force_entry(prices)
        except (MarketError, ExchangeError) as e:
            logger.warning("kézi indítás: %s", e)
        self._checks = []
        for sym in self.cfg.symbols:
            try:
                self._tick_symbol(sym, prices)
            except MarketError as e:
                self._data_problem(sym, str(e))
        if self.batch_checks and self._checks:
            self.notify(f"🔍 Napi döntések ({len(self._checks)} piac)\n" + "\n".join(self._checks),
                        email=False, kind="check", push=None)
        self._maybe_daily_report(prices)
        self._log_equity(prices)

    def _tick_symbol(self, sym: str, prices: dict[str, float]) -> None:
        candles = self.market.candles(sym, self.cfg.interval, limit=300)
        if not candles:
            raise MarketError("nem jött gyertyaadat")
        last = candles[-1]
        age_ms = self.clock() * 1000 - last.close_time
        limit_s = self.stale_seconds or (2 * self.cfg.interval_seconds + 120)
        if age_ms > limit_s * 1000:
            raise MarketError(f"elavult adat: az utolsó lezárt gyertya {age_ms / 3_600_000:.1f} órája zárult")
        price = self.market.price(sym)
        prices[sym] = price
        self._data_ok(sym)

        self._reconcile_pending(sym, prices)
        pos = self.store.open_position_for(sym)
        if pos is not None:
            self._check_exit(pos, price, prices)

        key = f"last_candle:{sym}"
        if int(self.store.get(key, "0")) >= last.open_time:
            return
        pos = self.store.open_position_for(sym)
        sig = strategy.evaluate(candles, pos, self.kinds.get(sym, self.default_kinds))
        if sig is not None:
            self._handle(sym, sig, last.open_time, pos, price, prices)
        elif len(candles) >= strategy.MIN_BARS:
            self._report_check(sym, candles, pos, price)
        # A jelzés feldolgozása után: ha közben hiba volt, a következő ciklus újra
        # megpróbálja, a naplóbeli egyedi kulcs pedig kizárja a kettős végrehajtást.
        self.store.set(key, last.open_time)

    def _handle(self, sym: str, sig: strategy.Signal, candle_time: int, pos: Position | None,
                price: float, prices: dict[str, float]) -> None:
        if not self.store.record_signal(sym, candle_time, sig.action, sig.price, sig.reason):
            return
        if sig.action == "exit":
            if pos is not None:
                self._close(pos, price, "jelzés", prices, sig.reason)
                self.store.set_signal_outcome(sym, candle_time, "exit", "zárva")
            return

        equity = self.equity(prices)
        ok, why = paper.can_open(len(self.store.open_positions()), self.cfg.max_open,
                                 self.store.realized_since(self._day_start_iso()), equity,
                                 self.cfg.daily_loss_limit)
        paused = self.entries_paused()
        if ok and paused and not sig.reason.startswith("KÉZI"):
            ok, why = False, f"védekező mód: {paused}"
        if ok:
            blocked = self.news_block(sym, sig.side)
            if blocked:
                ok, why = False, blocked
        fill = price * (1 + self.cfg.slippage * sig.side)
        if ok and (fill - sig.stop) * sig.side <= 0:
            ok, why = False, "az ár a jelzés óta már a stopon túl van"
        risk_unit = abs(fill - sig.stop)
        qty = paper.size(equity, max(self.store.cash(), equity), fill, fill - risk_unit, self.cfg.risk_per_trade,
                         self.cfg.max_open, self.cfg.fee) if ok else 0.0
        try:
            qty = self.executor.round_qty(sym, qty) if ok else 0.0
            min_notional = max(paper.MIN_NOTIONAL, self.executor.min_notional(sym))
        except ExchangeError as e:
            ok, why, min_notional = False, f"a tőzsde nem érhető el: {e}", paper.MIN_NOTIONAL
        if ok and qty * fill < min_notional:
            ok, why = False, "a kockázati szabályok szerinti pozíció túl kicsi"
        pos_id = None
        if ok:
            pos_id, why = self._enter(sym, qty, price, sig.stop, candle_time, prices, sig.side, sig.kind)
        if pos_id is None:
            self.store.set_signal_outcome(sym, candle_time, "enter", f"kihagyva: {why}")
            self.notify(f"{self.label}\n⚪ {sym}: jelzés, de NEM nyitottam.\nOk: {why}\nJelzés: {sig.reason}")
            return

        self.store.set_signal_outcome(sym, candle_time, "enter", "nyitva")
        p = self.store.get_position(pos_id)
        risk_pct = p.risk_amount / equity if equity > 0 else 0.0
        facts = {"instrumentum": sym, "idősík": self.cfg.interval, "belépés": p.entry_price, "stop": p.stop,
                 "cél": p.target, "darab": p.qty, "pozíció_értéke_usdt": p.qty * p.entry_price,
                 "kockázat_usdt": p.risk_amount, "kockázat_a_tőkéhez": f"{risk_pct:.2%}",
                 "atr": sig.atr, "jelzés_oka": sig.reason, "stratégia": strategy.NAME}
        facts["irány"] = "emelkedésre (long)" if p.side == 1 else "esésre (short)"
        facts["fogadás_típusa"] = sig.kind
        why_text = self._explain("Magyarázd el a megbízónak, miért nyitottunk most pozíciót, merre fogadunk, "
                                 "és mi a terv, ha a stop vagy a cél teljesül.", facts)
        head = "🟢 EMELKEDÉSRE FOGADOK (VÉTEL)" if p.side == 1 else "🔻 ESÉSRE FOGADOK (SHORT)"
        if sig.kind == "dip":
            head = "🟢 VISSZAPATTANÁSRA FOGADOK (VÉTEL)"
        self.notify(
            f"{self.label}\n{head} — {self.name_of(sym)}\n"
            f"Belépés: {p.entry_price:,.2f} | Stop: {p.stop:,.2f} | Cél: {p.target:,.2f}\n"
            f"Méret: {p.qty:.6f} ({_usd(p.qty * p.entry_price)}) | Kockázat: {_usd(p.risk_amount)} ({risk_pct:.2%})\n"
            f"Ok: {sig.reason}" + (f"\n\n🧠 {why_text}" if why_text else ""))

    def _close(self, pos: Position, raw_price: float, reason: str, prices: dict[str, float],
               detail: str = "") -> None:
        try:
            fill = self._exit_fill(pos, raw_price)
        except ExchangeError as e:
            self._exit_failed(pos, e)
            return
        if fill is None:   # közben kiütött a tőzsdei stop: azt könyveltük
            return
        exit_px, exit_fee = fill.price, fill.fee
        pnl = pos.side * pos.qty * (exit_px - pos.entry_price) - exit_fee - pos.entry_fee
        if not self.store.close_position(pos.id, exit_px, exit_fee, reason, pnl):
            return
        closed = self.store.get_position(pos.id)
        icon = "🟢" if pnl > 0 else "🔴"
        r = f"{closed.r_multiple:+.2f}R" if closed.r_multiple is not None else ""
        facts = {"instrumentum": pos.symbol, "belépés": pos.entry_price, "kilépés": exit_px, "ok": reason,
                 "eredmény_usdt": pnl, "r_szorzó": closed.r_multiple, "részlet": detail,
                 "számla_értéke": self.equity(prices)}
        why_text = self._explain("Számolj be a pozíció zárásáról: mi történt, és mit jelent ez a terv szempontjából.",
                                 facts)
        self.notify(f"{self.label}\n{icon} ZÁRÁS — {self.name_of(pos.symbol)} ({reason})\n"
                    f"Belépés: {pos.entry_price:,.2f} → Kilépés: {exit_px:,.2f}\n"
                    f"Eredmény: {pnl:+,.2f} USDT {r}" + (f"\nOk: {detail}" if detail else "")
                    + (f"\n\n🧠 {why_text}" if why_text else ""))

    # --- végrehajtás ----------------------------------------------------------
    @staticmethod
    def _cid(sym: str, candle_time: int) -> str:
        # Binance: legfeljebb 36 karakter, [.A-Za-z:/0-9_-]
        return f"mtb-{sym}-{candle_time // 1000}"

    def _enter(self, sym: str, qty: float, price: float, stop: float, candle_time: int,
               prices: dict[str, float], side: int = 1, kind: str = "trend") -> tuple[int | None, str]:
        """Vétel, napló, tőzsdei stop. (pozíció id, ok) — id None, ha nem nyitottunk."""
        cid = self._cid(sym, candle_time)
        pending_key = f"pending_entry:{sym}"
        # Előbb a szándék: ha a vétel után összeomlunk, a következő ciklus ebből rendezi.
        if side == -1 and self.executor.live:
            return None, "ezen a számlán esésre nem lehet fogadni (spot)"
        self.store.set(pending_key, json.dumps({"cid": cid, "stop": stop, "candle": candle_time, "kind": kind}))
        try:
            fill = (self.executor.buy if side == 1 else self.executor.sell)(sym, qty, price, cid + "-b")
        except ExchangeError as e:
            if not e.uncertain:
                self.store.delete(pending_key)
            return None, f"a vétel nem sikerült: {e}"
        pos_id = self._book_entry(sym, fill, stop, candle_time, cid, side, kind)
        self.store.delete(pending_key)
        if pos_id is None:
            return None, "már van nyitott pozíció, vagy nincs rá fedezet"
        self._protect_or_exit(pos_id, prices)
        return (pos_id if self.store.get_position(pos_id).status == "open" else None,
                "a tőzsdei stopot nem sikerült leadni, ezért azonnal kiszálltam")

    def _book_entry(self, sym: str, fill, stop: float, candle_time: int, cid: str, side: int = 1,
                    kind: str = "trend") -> int | None:
        target = strategy.target_for_side(fill.price, stop, side, kind)
        return self.store.open_position(sym, fill.qty, fill.price, fill.fee, stop, target, candle_time,
                                        stop_cid=(cid + "-s") if self.executor.live else None,
                                        force=self.executor.live, side=side, kind=kind)

    def _protect_or_exit(self, pos_id: int, prices: dict[str, float]) -> None:
        p = self.store.get_position(pos_id)
        if not self.executor.live:
            return
        try:
            self.executor.protect(p.symbol, p.qty, p.stop, p.stop_cid)
            self.notify(f"{self.label}\n🛡 {p.symbol}: védőstop leadva a tőzsdén {p.stop:,.2f}-n "
                        f"({p.qty:.6f} db). Ha az ár ide esik, a Binance automatikusan elad.", kind="trade", push=3)
        except ExchangeError as e:
            logger.error("%s: a stop leadása nem sikerült: %s", p.symbol, e)
            self._close(p, prices.get(p.symbol, p.entry_price), "biztonsági zárás",
                        prices, f"a tőzsdei stopot nem sikerült leadni ({e})")

    def _reconcile_pending(self, sym: str, prices: dict[str, float]) -> None:
        """Félbemaradt vétel rendezése (összeomlás vagy bizonytalan válasz után)."""
        raw = self.store.get(f"pending_entry:{sym}")
        if not raw or not self.executor.live:
            if raw:
                self.store.delete(f"pending_entry:{sym}")
            return
        info = json.loads(raw)
        if self.store.open_position_for(sym) is not None:
            self.store.delete(f"pending_entry:{sym}")
            return
        fill = self.executor.lookup(sym, info["cid"] + "-b")
        if fill is None:
            self.store.delete(f"pending_entry:{sym}")   # a vétel nem jött létre
            return
        pos_id = self._book_entry(sym, fill, info["stop"], info["candle"], info["cid"], 1, info.get("kind", "trend"))
        self.store.delete(f"pending_entry:{sym}")
        if pos_id:
            self.notify(f"{self.label}\n🔧 {sym}: egy félbemaradt vételt rendeztem a tőzsdei adatok alapján "
                        f"({fill.qty:.6f} @ {fill.price:,.2f}), és leadom a stopot.")
            self._protect_or_exit(pos_id, prices)

    def _check_exit(self, pos: Position, price: float, prices: dict[str, float]) -> None:
        if not self.executor.live:
            hit = paper.exit_on_price(pos.stop, pos.target, price, pos.side)
            if hit:
                self._close(pos, hit[0], hit[1], prices)
            return
        state = self.executor.stop_state(pos.symbol, pos.stop_cid)
        if state is not None and state[0] == "filled":
            self._book_exit(pos, state[1], "stop (tőzsdei)", prices)
        elif state is not None:
            self._close(pos, price, "biztonsági zárás", prices, "a tőzsdei stop eltűnt vagy törlődött")
        elif price >= pos.target:
            self._close(pos, price, "cél", prices)

    def _exit_fill(self, pos: Position, raw_price: float):
        if not self.executor.live:
            return (self.executor.sell if pos.side == 1 else self.executor.buy)(pos.symbol, pos.qty, raw_price, "")
        self.executor.unprotect(pos.symbol, pos.stop_cid)
        # A törlés és a kiütés versenyezhet: ha a stop közben teljesült, azt könyveljük.
        state = self.executor.stop_state(pos.symbol, pos.stop_cid)
        if state is not None and state[0] == "filled":
            self._book_exit(pos, state[1], "stop (tőzsdei)", {})
            return None
        return self.executor.sell(pos.symbol, pos.qty, raw_price, f"mtb-p{pos.id}-x")

    def _book_exit(self, pos: Position, fill, reason: str, prices: dict[str, float]) -> None:
        pnl = pos.side * pos.qty * (fill.price - pos.entry_price) - fill.fee - pos.entry_fee
        if self.store.close_position(pos.id, fill.price, fill.fee, reason, pnl):
            closed = self.store.get_position(pos.id)
            r = f"{closed.r_multiple:+.2f}R" if closed.r_multiple is not None else ""
            self.notify(f"{self.label}\n{'🟢' if pnl > 0 else '🔴'} ZÁRÁS — {pos.symbol} ({reason})\n"
                        f"Belépés: {pos.entry_price:,.2f} → Kilépés: {fill.price:,.2f}\n"
                        f"Eredmény: {pnl:+,.2f} USDT {r}")

    def _exit_failed(self, pos: Position, error: ExchangeError) -> None:
        """Az eladás nem ment át: a pozíció nyitva marad, és újra stopot kap, hogy ne legyen védtelen."""
        logger.error("%s: a zárás nem sikerült: %s", pos.symbol, error)
        new_cid = f"mtb-p{pos.id}-s{int(self.clock()) % 100000}"
        protected = False
        try:
            self.executor.protect(pos.symbol, pos.qty, pos.stop, new_cid)
            self.store.set_stop_cid(pos.id, new_cid)
            protected = True
        except ExchangeError as e:
            logger.error("%s: az újbóli stop sem ment át: %s", pos.symbol, e)
        self.notify(f"{self.label}\n⚠️ {pos.symbol}: a zárás nem sikerült ({error}). "
                    + ("A pozíciót újra védi a tőzsdei stop; a következő ciklusban újrapróbálom."
                       if protected else "A pozíció JELENLEG STOP NÉLKÜL van — nézd meg a tőzsdén!"))

    def _log_equity(self, prices: dict[str, float]) -> None:
        """5 percenként egy pont az egyenleg-grafikonhoz (csak friss árakkal, hogy ne torzítson)."""
        now = int(self.clock())
        if now - int(self.store.get("equity_logged_at", "0") or 0) < 300:
            return
        if any(p.symbol not in prices for p in self.store.open_positions()):
            return
        self.store.log_equity(now, self.equity(prices), self.store.cash())
        self.store.set("equity_logged_at", now)

    def name_of(self, sym: str) -> str:
        try:
            from radar import UNIVERSE
            name = UNIVERSE.get(sym, (None,))[0]
        except ImportError:
            name = None
        return f"{name} ({sym})" if name else sym

    def news_block(self, sym: str, side: int) -> str | None:
        """Ha az elmúlt 12 órában súlyos hír jött az eszközről a fogadással ellentétes irányba, nem lépünk be.
        Ez a szabály a hírek jellege miatt visszamenőleg nem tesztelhető; óvatossági fék, nem jelzés."""
        if self.radar is None:
            return None
        from radar import news_conflict
        return news_conflict(self.radar.store, sym, side)

    def decision(self, sym: str) -> str:
        """Egy mondatban: mit döntött a bot az adott piacon, és miért."""
        try:
            candles = self.market.candles(sym, self.cfg.interval, limit=300)
        except MarketError:
            return "nincs friss adat, ezért nem döntök"
        if len(candles) < strategy.MIN_BARS:
            return "kevés az adat a döntéshez"
        ind = strategy.compute(candles)
        f, sl, r, close = ind["fast"][-1], ind["slow"][-1], ind["regime"][-1], candles[-1].close
        if close <= r:
            return (f"NEM VESZEK — esik a piac (az ár {r / close - 1:.1%}-kal a hosszú távú átlag alatt). "
                    f"Esésben vásárolni a leggyakoribb veszteségforrás; akkor veszek, ha {r:,.0f} fölé megy")
        if f <= sl:
            return "MÉG NEM VESZEK — a hosszú trend emelkedő, de a rövid távú lendület még gyenge"
        return "NEM VESZEK MOST — emelkedik, de a belépési pont már elment; a következő lendületnél lépek"

    def _report_check(self, sym: str, candles, pos, price: float) -> None:
        """Minden lezárt gyertyánál: mit látott a bot, és miért nem lépett."""
        ind = strategy.compute(candles)
        f, sl, r = ind["fast"][-1], ind["slow"][-1], ind["regime"][-1]
        close = candles[-1].close
        trend = "emelkedő (EMA200 felett)" if close > r else "csökkenő (EMA200 alatt)"
        if pos is not None:
            why = (f"nyitott pozíció: {pos.qty * (price - pos.entry_price):+,.2f} USDT, "
                   f"stop {pos.stop:,.2f}, cél {pos.target:,.2f}")
        elif close <= r:
            why = f"csökkenő trendben nem veszek; az EMA200 ({r:,.2f}) {r / close - 1:+.1%}-ra van"
        elif f <= sl:
            why = "a trend emelkedő, de az EMA20 még az EMA50 alatt van: várom a felfelé keresztezést"
        else:
            why = "a trend emelkedő, az EMA20 az EMA50 felett van, de a keresztezés nem most történt"
        if self.batch_checks:
            short = ("pozícióban" if pos is not None else
                     "nem veszek, esik" if close <= r else "várok, a lendület még gyenge" if f <= sl
                     else "várok jobb belépőre")
            self._checks.append(f"• {self.name_of(sym)}: {close:,.2f} — {short}")
            return
        self.notify(f"🔍 {sym} döntés ({close:,.2f})\nTrend: {trend}. Döntés: {why}.",
                    email=False, kind="check", push=None)

    # --- radar és védekezés -----------------------------------------------------
    def radar_emit(self, kind: str, title: str, body: str = "", push: int | None = None) -> None:
        text = f"{title}\n{body}" if body else title
        self.notify(text, email=False, kind=kind, push=push)
        if kind == "riskoff":
            self.risk_off(body or title)

    def entries_paused(self) -> str | None:
        until = float(self.store.get("entries_paused_until", "0") or 0)
        return self.store.get("entries_paused_reason") if until > self.clock() else None

    def risk_off(self, reason: str, hours: float = 24) -> None:
        """Védekező mód: minden nyitott pozíciót lezár (a pénz USDT-ben marad a számlán), és
        a következő órákra letiltja az új nyitást. A kivételi jog a kulcson nincs."""
        self.store.set("entries_paused_until", self.clock() + hours * 3600)
        self.store.set("entries_paused_reason", reason)
        closed = []
        prices: dict[str, float] = {}
        for pos in self.store.open_positions():
            try:
                px = self.market.price(pos.symbol)
            except MarketError:
                px = pos.entry_price
            prices[pos.symbol] = px
            self._close(pos, px, "védekező mód", prices, reason)
            closed.append(pos.symbol)
        for peer in self.peers:
            peer.risk_off(reason, hours)
        self.notify(f"🛑 VÉDEKEZŐ MÓD {hours:.0f} órára\n{reason}\n"
                    + (f"Lezárt pozíciók: {', '.join(closed)}." if closed else "Nem volt nyitott pozíció.")
                    + "\nÚj pozíciót nem nyitok. Feloldás: írd be a chatbe: /folytat",
                    email=False, kind="riskoff", push=5)

    def pulse(self) -> None:
        """Óránkénti élő helyzetkép az eseményfolyamba (telefonra nem megy)."""
        prices = self._prices(list(self.cfg.symbols), {})
        eq = self.equity(prices)
        pos = self.store.open_positions()
        bits = [f"Számla {eq:,.0f} USDT ({eq / self.store.start_equity() - 1:+.2%})"]
        for p in pos:
            px = prices.get(p.symbol)
            if px:
                bits.append(f"{p.symbol} {p.qty * (px - p.entry_price):+,.2f} USDT")
        if not pos:
            bits.append("nincs nyitott pozíció")
        snap = self.radar.snapshot() if self.radar else {}
        if snap.get("vix"):
            bits.append(f"VIX {snap['vix']}")
        for peer in self.peers:
            try:
                peq = peer.equity(peer._prices([p.symbol for p in peer.store.open_positions()], {}))
                bits.append(f"Világpiaci számla {peq:,.0f} ({peq / peer.store.start_equity() - 1:+.2%}, "
                            f"{len(peer.store.open_positions())} pozíció)")
            except Exception:
                logger.exception("a világpiaci számla összesítése nem sikerült")
        paused = self.entries_paused()
        if paused:
            bits.append("⏸ védekező mód")
        self.notify("🕐 Helyzetkép\n" + " • ".join(bits), email=False, kind="pulse", push=None)

    # --- adatminőség ---------------------------------------------------------
    def _data_problem(self, sym: str, error: str) -> None:
        logger.warning("%s: %s", sym, error)
        key = f"data_alert:{sym}"
        if self.store.get(key):
            return  # már szóltunk; nem ismételjük percenként
        self.store.set(key, self._now().isoformat(timespec="seconds"))
        self.notify(f"⚠️ {sym}: nincs megbízható piaci adat ({error}). Amíg ez tart, nem adok tanácsot, "
                    "és a stopokat sem tudom figyelni.")

    def _data_ok(self, sym: str) -> None:
        key = f"data_alert:{sym}"
        if self.store.get(key):
            self.store.delete(key)
            self.notify(f"✅ {sym}: a piaci adat újra rendben érkezik.")

    # --- napi jelentés -------------------------------------------------------
    def _maybe_daily_report(self, prices: dict[str, float]) -> None:
        local = self._now().astimezone(self.cfg.tz)
        today = local.date().isoformat()
        if local.hour < self.cfg.report_hour or self.store.get("last_report") == today:
            return
        self.store.set("last_report", today)  # előbb jelöljük: hiba esetén se menjen ki kétszer
        self.notify(self.report(prices, daily=True), kind="report", push=3)

    def report(self, prices: dict[str, float] | None = None, daily: bool = False) -> str:
        positions = self.store.open_positions()
        prices = self._prices([p.symbol for p in positions] + list(self.cfg.symbols), prices or {})
        equity = self.equity(prices)
        start = self.store.start_equity()
        since = (self._now() - timedelta(hours=24)).isoformat(timespec="seconds")
        last_day = self.store.closed_since(since)
        lines = [self.label, ("☀️ Napi jelentés" if daily else "📋 Állapot") + f" — {self._now().astimezone(self.cfg.tz):%Y-%m-%d %H:%M}",
                 f"Számla: {_usd(equity)} ({equity / start - 1:+.2%} a kezdethez képest)" if start else
                 f"Számla: {_usd(equity)}",
                 f"Készpénz: {_usd(self.store.cash())}"]
        lines.append(f"Árak: " + ", ".join(f"{s} {prices[s]:,.2f}" for s in self.cfg.symbols if s in prices))
        if positions:
            lines.append("Nyitott pozíciók:")
            for p in positions:
                px = prices.get(p.symbol)
                unreal = f"{p.side * p.qty * (px - p.entry_price):+,.2f} USDT" if px else "ár nem elérhető"
                lines.append(f"• {self.name_of(p.symbol)} {'emelkedésre' if p.side == 1 else 'ESÉSRE'}: "
                             f"belépés {p.entry_price:,.2f}, stop {p.stop:,.2f}, cél {p.target:,.2f}, most {unreal}")
        else:
            lines.append("Nincs nyitott pozíció. Döntéseim:")
            for sym in self.cfg.symbols:
                lines.append(f"• {sym}: {self.decision(sym)}")
        if last_day:
            lines.append(f"Elmúlt 24 óra: {len(last_day)} zárás, {sum(p.pnl or 0 for p in last_day):+,.2f} USDT")
        alerts = [s for s in self.cfg.symbols if self.store.get(f"data_alert:{s}")]
        if alerts:
            lines.append("⚠️ Adathiba: " + ", ".join(alerts))
        text = "\n".join(lines)
        if daily:
            facts = {"jelentés": text, "utolsó_jelzések": self.store.recent_signals(5)}
            why_text = self._explain("Adj rövid reggeli helyzetképet a megbízónak a számla és a pozíciók alapján.",
                                     facts)
            if why_text:
                text += f"\n\n🧠 {why_text}"
        return text

    def journal(self) -> str:
        closed = self.store.closed_positions()
        if not closed:
            return f"{self.label}\n📒 Még nincs lezárt kötés. A statisztika az első zárás után indul."
        wins = [p for p in closed if (p.pnl or 0) > 0]
        rs = [p.r_multiple for p in closed if p.r_multiple is not None]
        lines = [self.label, f"📒 Napló — {len(closed)} lezárt kötés",
                 f"Találati arány: {len(wins) / len(closed):.0%} | átlag: {sum(rs) / len(rs) if rs else 0:+.2f}R | "
                 f"összesen: {sum(p.pnl or 0 for p in closed):+,.2f} USDT", "Utolsó 10:"]
        for p in closed[:10]:
            lines.append(f"• {p.closed_at[:10]} {p.symbol} {p.exit_reason}: {p.pnl:+,.2f} USDT "
                         f"({p.r_multiple:+.2f}R)" if p.r_multiple is not None else
                         f"• {p.closed_at[:10]} {p.symbol} {p.exit_reason}: {p.pnl:+,.2f} USDT")
        return "\n".join(lines)

    # --- befelé (Telegram) ---------------------------------------------------
    def handle_message(self, chat_id, text: str) -> str | None:
        """A válasz szövege, vagy None, ha nem válaszolunk (idegen chat)."""
        if not self.bot or not self.bot.chat_id:
            return (f"A chat-azonosítód: {chat_id}\nÁllítsd be a szolgáltatásban TELEGRAM_CHAT_ID néven, "
                    "és indítsd újra. Addig senkinek nem adok ki adatot.")
        if str(chat_id) != str(self.bot.chat_id):
            logger.warning("idegen chatből jött üzenet (%s), figyelmen kívül hagyva", chat_id)
            return None
        return self.respond(text)

    def respond(self, text: str) -> str | None:
        """Parancs vagy szabad kérdés; a hívó felelős a jogosultság ellenőrzéséért (Telegram-chat, webes belépés)."""
        text = (text or "").strip()
        if not text:
            return None
        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@")[0].lower()
        if cmd in ("/start", "/help"):
            return f"Szia! A kriptó-brókered vagyok ({self.label}).\n{HELP}"
        if cmd == "/status":
            return self.report()
        if cmd == "/journal":
            return self.journal()
        if cmd == "/radar":
            return self.radar_text()
        if cmd in ("/vilag", "/világ"):
            return "\n\n".join(p.report() for p in self.peers) or "Nincs világpiaci számla."
        if cmd == "/folytat":
            self.store.set("entries_paused_until", 0)
            return "▶️ A védekező mód feloldva, az új pozíciók nyitása újra engedélyezett."
        if cmd == "/vedekezes":
            self.risk_off("kézi kérés (/vedekezes)")
            return "🛑 Védekező mód bekapcsolva, a pozíciókat lezártam."
        if cmd == "/backtest":
            sym = (arg.strip().upper() or self.cfg.symbols[0])
            if sym not in self.cfg.symbols:
                return f"Ezt figyelem: {', '.join(self.cfg.symbols)}. Pl. /backtest {self.cfg.symbols[0]}"
            try:
                return backtest.summary(backtest.run_symbol(self.market, sym, self.cfg))
            except (MarketError, ValueError) as e:
                return f"A backtest most nem futott le: {e}"
        return self.answer(text)

    def radar_text(self) -> str:
        if not self.radar:
            return "A radar nincs bekapcsolva."
        snap = self.radar.snapshot()
        lines = [f"🌍 Világpiaci radar" + (f" (frissítve {snap['frissítve_másodperce'] // 60} perce)"
                                          if snap.get("frissítve_másodperce") is not None else "")]
        if snap.get("vix"):
            lines.append(f"VIX: {snap['vix']}")
        lines.append("Legszokatlanabb mozgások:")
        for m in snap["legszokatlanabb_mozgások"]:
            lines.append(f"• {m['név']}: {m['napi_%']:+.2f}% (z={m['z']})")
        lines.append("Friss hírek:")
        for n in snap["friss_hírek"][:6]:
            lines.append(f"• [{n['súly'] or '-'}] {n['cím']} ({n['forrás']})")
        return "\n".join(lines)

    def answer(self, question: str) -> str:
        if self.llm is None:
            return "Szabad kérdésre csak modellkulccsal tudok válaszolni (GEMINI_API_KEY vagy OPENAI_API_KEY).\n" + HELP
        context = {"állapot": self.report(), "utolsó_jelzések": self.store.recent_signals(5),
                   "stratégia": strategy.NAME,
                   "kockázati_szabályok": {"kockázat_kötésenként": self.cfg.risk_per_trade,
                                           "max_nyitott": self.cfg.max_open,
                                           "napi_veszteséglimit": self.cfg.daily_loss_limit},
                   "világpiaci_radar": self.radar.snapshot() if self.radar else None,
                   "védekező_mód": self.entries_paused(),
                   "világpiaci_számla": [p.report() for p in self.peers],
                   "korábbi_beszélgetés": self.store.recent_chat(8)}
        history = "\n".join(f"{'Milán' if m['role'] == 'user' else 'Bot'}: {m['content'][:600]}"
                             for m in self.store.recent_chat(10))
        context.pop("korábbi_beszélgetés", None)
        prompt = (f"Élő adatok (csak ezekre hivatkozhatsz):\n"
                  f"{json.dumps(context, ensure_ascii=False, default=str, indent=1)}\n\n"
                  f"Eddigi beszélgetés:\n{history or '(még nincs)'}\n\nMilán most ezt írta: {question}")
        try:
            from llm import CHAT_PERSONA
            reply = self.llm.ask(prompt, system=CHAT_PERSONA).replace("**", "")[:3000]
        except LLMError as e:
            logger.warning("a chat válasza elmaradt: %s", e)
            reply = ""
        if not reply:
            return "A modell most nem elérhető, ezért csak a számokat tudom adni:\n\n" + self.report()
        self.store.add_chat("user", question)
        self.store.add_chat("assistant", reply)
        return reply
