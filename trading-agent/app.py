"""A szolgáltatás: két háttérszál (piacfigyelés, Telegram) és egy egészség-végpont.

Egyetlen példányban fusson (Railway: 1 replica). Két példány kétszer küldené
az értesítéseket, és két külön SQLite-fájlba könyvelne.
"""
from __future__ import annotations

import hmac
import logging
import os
import threading
import time

from fastapi import FastAPI, Header, HTTPException

import config
from agent import Agent
from exchange import BinanceClient, BinanceExecutor, ExchangeError, PaperExecutor, selftest
from llm import LLM
from mailer import Mailer
from market import Market
from store import Store
from telegram import Telegram, TelegramError

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
# INFO szinten a httpx kiírná a kérés URL-jét, abban pedig benne van a Telegram-token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("trading-agent")

cfg = config.load()
MODE = os.environ.get("TRADING_MODE", "paper").strip().lower()


def _binance_executor() -> tuple[BinanceExecutor, float]:
    client = BinanceClient.from_env(cfg.fee)
    if client is None:
        raise SystemExit("TRADING_MODE=binance, de hiányzik a BINANCE_API_KEY vagy a BINANCE_PRIVATE_KEY")
    if not client.is_demo and os.environ.get("BINANCE_LIVE_CONFIRM", "") != "VALODI_PENZ":
        # Éles címre csak kifejezett, külön jóváhagyással: egy elgépelt URL ne kereskedjen valódi pénzzel.
        raise SystemExit("éles Binance-cím BINANCE_LIVE_CONFIRM=VALODI_PENZ nélkül — leállok")
    last = None
    for attempt in range(3):
        try:
            return BinanceExecutor(client), client.free("USDT")
        except ExchangeError as e:
            last = e
            time.sleep(3 * (attempt + 1))
    raise SystemExit(f"a Binance-fiók nem érhető el: {last}")


if MODE == "binance":
    executor, start_equity = _binance_executor()
    db_path = os.environ.get("TRADING_DB_PATH_BINANCE", "/data/trading-binance.db")
elif MODE == "paper":
    executor, start_equity, db_path = PaperExecutor(cfg.fee, cfg.slippage), cfg.start_equity, cfg.db_path
else:
    raise SystemExit(f"ismeretlen TRADING_MODE: {MODE} (paper | binance)")

store = Store(db_path, start_equity)
bot = Telegram.from_env()
llm = LLM.from_env()
mailer = Mailer.from_env()
agent = Agent(cfg, store, Market(), bot, llm, mailer=mailer, executor=executor)
state = {"started": time.time(), "last_tick": None, "last_error": None}

app = FastAPI(title="AXIMBRA trading agent (papír)")


@app.get("/health")
def health():
    last = state["last_tick"]
    return {"ok": True, "mode": executor.name, "symbols": list(cfg.symbols), "interval": cfg.interval,
            "telegram": bot is not None, "telegram_chat": bool(bot and bot.chat_id), "email": mailer is not None,
            "llm": llm.provider if llm else None,
            "last_tick_age_s": None if last is None else round(time.time() - last),
            "last_error": state["last_error"]}


@app.get("/status")
def status(x_status_token: str | None = Header(default=None)):
    token = os.environ.get("STATUS_TOKEN", "")
    if not token:
        raise HTTPException(404, "állítsd be a STATUS_TOKEN változót a végpont bekapcsolásához")
    if not x_status_token or not hmac.compare_digest(x_status_token, token):
        raise HTTPException(401, "hibás token")
    return {"report": agent.report(), "journal": agent.journal()}


def _market_loop() -> None:
    while True:
        started = time.time()
        try:
            agent.tick()
            state["last_tick"] = time.time()
            state["last_error"] = None
        except Exception as e:  # a szálnak túl kell élnie bármilyen hibát; a következő ciklus újrapróbálja
            logger.exception("a ciklus hibával állt le")
            state["last_error"] = f"{type(e).__name__}: {e}"[:300]
        time.sleep(max(1.0, cfg.poll_seconds - (time.time() - started)))


def _telegram_loop() -> None:
    offset = int(store.get("tg_offset", "0"))
    while True:
        try:
            updates = bot.updates(offset)
        except TelegramError as e:
            logger.warning("Telegram lekérdezés: %s", e)
            time.sleep(10)
            continue
        for u in updates:
            # Feldolgozás ELŐTT léptetjük: összeomláskor egy kérdés válasz nélkül marad,
            # de újraindulás után sem kap senki kétszer választ.
            offset = int(u.get("update_id", offset)) + 1
            store.set("tg_offset", offset)
            msg = u.get("message") or {}
            chat_id = (msg.get("chat") or {}).get("id")
            text = msg.get("text")
            if chat_id is None or not text:
                continue
            try:
                reply = agent.handle_message(chat_id, text)
                if reply:
                    bot.send(reply, chat_id=str(chat_id))
            except Exception:
                logger.exception("az üzenet feldolgozása nem sikerült")


@app.on_event("startup")
def _startup() -> None:
    if os.environ.get("TRADING_LOOP", "on").lower() == "off":
        logger.info("TRADING_LOOP=off: a háttérszálak nem indulnak")
        return
    threading.Thread(target=_market_loop, name="market", daemon=True).start()
    if bot is not None:
        threading.Thread(target=_telegram_loop, name="telegram", daemon=True).start()
    hello = (f"🚀 Elindultam ({executor.name}). Figyelem: {', '.join(cfg.symbols)} ({cfg.interval}). "
             f"Számla: {store.cash():,.2f} USDT.")
    # Telegramon minden indulás jelez; e-mailben csak az első, hogy a csatorna
    # működése igazolva legyen, de egy-egy újratelepítés ne töltse a postafiókot.
    first_mail = mailer is not None and not store.get("mail_hello")
    agent.notify(hello + (" /help" if bot else ""), email=first_mail)
    if first_mail:
        store.set("mail_hello", "1")
    if executor.live and not store.get("selftest_ok") and os.environ.get("BINANCE_SELFTEST", "on") != "off":
        # Egyszer, az első induláskor: egy kis valódi kör a demószámlán, hogy minden lépés igazolva legyen.
        lines = selftest(executor.c, cfg.symbols[0])
        for line in lines:
            logger.info("önteszt: %s", line)
        ok = all(l.startswith("✅") for l in lines)
        if ok:
            store.set("selftest_ok", "1")
        agent.notify(f"{agent.label}\n{'✅' if ok else '❌'} Binance-önteszt\n" + "\n".join(lines))
    logger.info("indulás: %s, %s, telegram=%s, email=%s, llm=%s", cfg.symbols, cfg.interval, bot is not None,
                mailer is not None, llm.provider if llm else None)
