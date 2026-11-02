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
import time
from datetime import datetime, timedelta, timezone

import backtest
import paper
import strategy
from config import Config
from llm import LLMError
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
    "/help — ez a lista\n"
    "Bármi mást kérdezhetsz szabad szöveggel is, pl. „mit csinál most a BTC?”"
)


def _usd(x: float) -> str:
    return f"{x:,.2f} USDT"


class Agent:
    def __init__(self, cfg: Config, store: Store, market: Market, bot=None, llm=None, clock=time.time):
        self.cfg = cfg
        self.store = store
        self.market = market
        self.bot = bot
        self.llm = llm
        self.clock = clock

    # --- kifelé --------------------------------------------------------------
    def notify(self, text: str) -> None:
        if self.bot is None or not self.bot.chat_id:
            logger.info("értesítés (nincs Telegram): %s", text.splitlines()[0] if text else "")
            return
        try:
            self.bot.send(text)
        except TelegramError as e:
            logger.warning("az értesítés nem ment ki: %s", e)

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
            total += p.qty * prices.get(p.symbol, p.entry_price)
        return total

    # --- ciklus --------------------------------------------------------------
    def tick(self) -> None:
        prices: dict[str, float] = {}
        for sym in self.cfg.symbols:
            try:
                self._tick_symbol(sym, prices)
            except MarketError as e:
                self._data_problem(sym, str(e))
        self._maybe_daily_report(prices)

    def _tick_symbol(self, sym: str, prices: dict[str, float]) -> None:
        candles = self.market.candles(sym, self.cfg.interval, limit=300)
        if not candles:
            raise MarketError("nem jött gyertyaadat")
        last = candles[-1]
        age_ms = self.clock() * 1000 - last.close_time
        if age_ms > 2 * self.cfg.interval_seconds * 1000 + 120_000:
            raise MarketError(f"elavult adat: az utolsó lezárt gyertya {age_ms / 3_600_000:.1f} órája zárult")
        price = self.market.price(sym)
        prices[sym] = price
        self._data_ok(sym)

        pos = self.store.open_position_for(sym)
        if pos is not None:
            hit = paper.exit_on_price(pos.stop, pos.target, price)
            if hit:
                self._close(pos, hit[0], hit[1], prices)

        key = f"last_candle:{sym}"
        if int(self.store.get(key, "0")) >= last.open_time:
            return
        pos = self.store.open_position_for(sym)
        sig = strategy.latest(candles, pos is not None)
        if sig is not None:
            self._handle(sym, sig, last.open_time, pos, price, prices)
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
        fill = paper.entry_fill(price, self.cfg.slippage)
        if ok and fill <= sig.stop:
            ok, why = False, "az ár a jelzés óta a stop alá esett"
        qty = paper.size(equity, self.store.cash(), fill, sig.stop, self.cfg.risk_per_trade,
                         self.cfg.max_open, self.cfg.fee) if ok else 0.0
        if ok and qty * fill < paper.MIN_NOTIONAL:
            ok, why = False, "a kockázati szabályok szerinti pozíció túl kicsi"
        pos_id = None
        if ok:
            target = strategy.target_for(fill, sig.stop)
            pos_id = self.store.open_position(sym, qty, fill, qty * fill * self.cfg.fee, sig.stop, target,
                                              candle_time)
            if pos_id is None:
                why = "már van nyitott pozíció, vagy nincs rá fedezet"
        if pos_id is None:
            self.store.set_signal_outcome(sym, candle_time, "enter", f"kihagyva: {why}")
            self.notify(f"{PAPER}\n⚪ {sym}: vételi jelzés, de NEM nyitottam.\nOk: {why}\nJelzés: {sig.reason}")
            return

        self.store.set_signal_outcome(sym, candle_time, "enter", "nyitva")
        p = self.store.get_position(pos_id)
        risk_pct = p.risk_amount / equity if equity > 0 else 0.0
        facts = {"instrumentum": sym, "idősík": self.cfg.interval, "belépés": p.entry_price, "stop": p.stop,
                 "cél": p.target, "darab": p.qty, "pozíció_értéke_usdt": p.qty * p.entry_price,
                 "kockázat_usdt": p.risk_amount, "kockázat_a_tőkéhez": f"{risk_pct:.2%}",
                 "atr": sig.atr, "jelzés_oka": sig.reason, "stratégia": strategy.NAME}
        why_text = self._explain("Magyarázd el a megbízónak, miért nyitottunk most vételi pozíciót, "
                                 "és mi a terv, ha a stop vagy a cél teljesül.", facts)
        self.notify(
            f"{PAPER}\n🟢 VÉTEL — {sym}\n"
            f"Belépés: {p.entry_price:,.2f} | Stop: {p.stop:,.2f} | Cél: {p.target:,.2f}\n"
            f"Méret: {p.qty:.6f} ({_usd(p.qty * p.entry_price)}) | Kockázat: {_usd(p.risk_amount)} ({risk_pct:.2%})\n"
            f"Ok: {sig.reason}" + (f"\n\n🧠 {why_text}" if why_text else ""))

    def _close(self, pos: Position, raw_price: float, reason: str, prices: dict[str, float],
               detail: str = "") -> None:
        exit_px, exit_fee, pnl = paper.settle(pos.qty, pos.entry_price, pos.entry_fee, raw_price,
                                              self.cfg.fee, self.cfg.slippage)
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
        self.notify(f"{PAPER}\n{icon} ZÁRÁS — {pos.symbol} ({reason})\n"
                    f"Belépés: {pos.entry_price:,.2f} → Kilépés: {exit_px:,.2f}\n"
                    f"Eredmény: {pnl:+,.2f} USDT {r}" + (f"\nOk: {detail}" if detail else "")
                    + (f"\n\n🧠 {why_text}" if why_text else ""))

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
        self.notify(self.report(prices, daily=True))

    def report(self, prices: dict[str, float] | None = None, daily: bool = False) -> str:
        positions = self.store.open_positions()
        prices = self._prices([p.symbol for p in positions] + list(self.cfg.symbols), prices or {})
        equity = self.equity(prices)
        start = self.store.start_equity()
        since = (self._now() - timedelta(hours=24)).isoformat(timespec="seconds")
        last_day = self.store.closed_since(since)
        lines = [PAPER, ("☀️ Napi jelentés" if daily else "📋 Állapot") + f" — {self._now().astimezone(self.cfg.tz):%Y-%m-%d %H:%M}",
                 f"Számla: {_usd(equity)} ({equity / start - 1:+.2%} a kezdethez képest)" if start else
                 f"Számla: {_usd(equity)}",
                 f"Készpénz: {_usd(self.store.cash())}"]
        lines.append(f"Árak: " + ", ".join(f"{s} {prices[s]:,.2f}" for s in self.cfg.symbols if s in prices))
        if positions:
            lines.append("Nyitott pozíciók:")
            for p in positions:
                px = prices.get(p.symbol)
                unreal = f"{p.qty * (px - p.entry_price):+,.2f} USDT" if px else "ár nem elérhető"
                lines.append(f"• {p.symbol}: belépés {p.entry_price:,.2f}, stop {p.stop:,.2f}, "
                             f"cél {p.target:,.2f}, most {unreal}")
        else:
            lines.append("Nincs nyitott pozíció — a stratégia vár a következő jelzésre.")
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
            return f"{PAPER}\n📒 Még nincs lezárt kötés. A statisztika az első zárás után indul."
        wins = [p for p in closed if (p.pnl or 0) > 0]
        rs = [p.r_multiple for p in closed if p.r_multiple is not None]
        lines = [PAPER, f"📒 Napló — {len(closed)} lezárt kötés",
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
        text = (text or "").strip()
        if not text:
            return None
        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@")[0].lower()
        if cmd in ("/start", "/help"):
            return f"Szia! A kriptó-brókered vagyok ({PAPER}).\n{HELP}"
        if cmd == "/status":
            return self.report()
        if cmd == "/journal":
            return self.journal()
        if cmd == "/backtest":
            sym = (arg.strip().upper() or self.cfg.symbols[0])
            if sym not in self.cfg.symbols:
                return f"Ezt figyelem: {', '.join(self.cfg.symbols)}. Pl. /backtest {self.cfg.symbols[0]}"
            try:
                return backtest.summary(backtest.run_symbol(self.market, sym, self.cfg))
            except (MarketError, ValueError) as e:
                return f"A backtest most nem futott le: {e}"
        return self.answer(text)

    def answer(self, question: str) -> str:
        if self.llm is None:
            return "Szabad kérdésre csak modellkulccsal tudok válaszolni (GEMINI_API_KEY vagy OPENAI_API_KEY).\n" + HELP
        context = {"állapot": self.report(), "utolsó_jelzések": self.store.recent_signals(5),
                   "stratégia": strategy.NAME,
                   "kockázati_szabályok": {"kockázat_kötésenként": self.cfg.risk_per_trade,
                                           "max_nyitott": self.cfg.max_open,
                                           "napi_veszteséglimit": self.cfg.daily_loss_limit},
                   "korábbi_beszélgetés": self.store.recent_chat(8)}
        reply = self._explain(f"A megbízó kérdése: „{question}”. Válaszolj neki az adatok alapján.", context)
        if not reply:
            return "A modell most nem elérhető, ezért csak a számokat tudom adni:\n\n" + self.report()
        self.store.add_chat("user", question)
        self.store.add_chat("assistant", reply)
        return reply
