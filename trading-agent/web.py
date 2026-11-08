"""Az élő felület: jelszóval védett weboldal — állapot, hírfolyam, világpiaci radar, chat a bottal.

Belépés: WEB_PASSWORD. A süti a jelszóból képzett HMAC, HttpOnly + Secure + SameSite=Strict.
Hibás próbálkozásból legfeljebb 8 lehet 10 percen belül (nyers erő ellen).
"""
from __future__ import annotations

import hashlib
import re
from urllib.parse import quote

import httpx
import hmac
import json
import os
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Cookie, HTTPException, Response
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field

COOKIE = "mtb_session"
PAGE = Path(__file__).parent / "static" / "index.html"


class Login(BaseModel):
    password: str = Field(max_length=200)


class Chat(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


def make_router(agent, state: dict) -> APIRouter:
    router = APIRouter()
    fails: list[float] = []
    fails_lock = threading.Lock()
    cache = {"at": 0.0, "data": None}
    cache_lock = threading.Lock()
    chat_lock = threading.Lock()     # egyszerre egy kérdés: a modell hívása drága és lassú

    def password() -> str:
        return os.environ.get("WEB_PASSWORD", "")

    def token() -> str:
        return hmac.new(password().encode(), b"mtb-session-v1", hashlib.sha256).hexdigest()

    def auth(session: str | None) -> None:
        if not password():
            raise HTTPException(404, "a webes felület nincs bekapcsolva (WEB_PASSWORD)")
        if not session or not hmac.compare_digest(session, token()):
            raise HTTPException(401, "nincs belépve")

    @router.get("/")
    def page(k: str | None = None):
        if not password():
            raise HTTPException(404, "a webes felület nincs bekapcsolva")
        link_key = os.environ.get("WEB_LINK_KEY", "")
        if k is not None:
            # Titkos link: jelszó gépelése nélkül belép, a süti 1 évig megmarad, a kulcs eltűnik a címsorból.
            if len(link_key) >= 24 and hmac.compare_digest(k.encode(), link_key.encode()):
                r = RedirectResponse("/", status_code=303)
                r.set_cookie(COOKIE, token(), max_age=365 * 86400, httponly=True, secure=True, samesite="lax")
                return r
            raise HTTPException(401, "érvénytelen link")
        return FileResponse(PAGE, headers={"Cache-Control": "no-store"})

    @router.post("/api/login")
    def login(body: Login, response: Response):
        if not password():
            raise HTTPException(404, "a webes felület nincs bekapcsolva")
        now = time.time()
        with fails_lock:
            fails[:] = [t for t in fails if now - t < 600]
            if len(fails) >= 8:
                raise HTTPException(429, "túl sok hibás próbálkozás, várj 10 percet")
            ok = hmac.compare_digest(body.password.encode(), password().encode())
            if not ok:
                fails.append(now)
        if not ok:
            raise HTTPException(401, "hibás jelszó")
        response.set_cookie(COOKIE, token(), max_age=30 * 86400, httponly=True, secure=True, samesite="strict")
        return {"ok": True}

    @router.post("/api/logout")
    def logout(response: Response):
        response.delete_cookie(COOKIE)
        return {"ok": True}

    @router.get("/api/state")
    def get_state(mtb_session: str | None = Cookie(default=None)):
        auth(mtb_session)
        with cache_lock:
            if cache["data"] and time.time() - cache["at"] < 10:
                return cache["data"]
        def book(a, all_prices: bool):
            positions = a.store.open_positions()
            syms = [p.symbol for p in positions] + (list(a.cfg.symbols) if all_prices else [])
            prices = a._prices(syms, {})
            out = []
            for p in positions:
                px = prices.get(p.symbol)
                out.append({"symbol": a.name_of(p.symbol), "sym": p.symbol, "qty": p.qty, "entry": p.entry_price, "stop": p.stop,
                            "target": p.target, "price": px, "opened_at": p.opened_at, "side": p.side, "kind": p.kind,
                            "entry_value": p.qty * p.entry_price + p.entry_fee,
                            "value": p.qty * px if px else None,
                            "pnl": p.side * p.qty * (px - p.entry_price) - p.entry_fee if px else None})
            closed = a.store.closed_positions(limit=200)
            eq = a.equity(prices)
            st = a.stats()
            exposure = sum(abs(p["value"] or p["entry_value"]) for p in out)
            at_risk = sum(max(0.0, (pp.side * (prices.get(pp.symbol, pp.entry_price) - pp.stop)) * pp.qty)
                          for pp in positions)
            return prices, {"label": a.label, "mode": a.executor.name, "equity": eq, "start": a.store.start_equity(),
                            "cash": a.store.cash(), "positions": out, "closed": len(closed),
                            "closed_pnl": sum(p.pnl or 0 for p in closed), "started_at": a.store.get("started_at"),
                            "history": a.store.equity_history(int(time.time()) - 30 * 86400),
                            "exposure": exposure, "at_risk": at_risk, "max_open": a.cfg.max_open,
                            "risk_per_trade": a.cfg.risk_per_trade, "symbols": len(a.cfg.symbols),
                            "interval": a.cfg.interval, "stats": st, "decisions": a.decisions(),
                            "paused": a.entries_paused()}
        prices, main = book(agent, True)
        equity, start, pos_out = main["equity"], main["start"], main["positions"]
        worlds = []
        for peer in agent.peers:
            try:
                worlds.append(book(peer, False)[1])
            except Exception:
                worlds.append({"label": peer.label, "error": "az adatok most nem érhetők el"})
        snap = agent.radar.snapshot() if agent.radar else {}
        moves = {}
        if agent.radar:
            moves = sorted(({"name": m.name, "sym": m.symbol, "cls": m.cls, "price": m.price, "day": m.day_pct, "week": m.week_pct,
                             "z": m.z} for m in (agent.radar.moves or {}).values()), key=lambda m: -abs(m["z"]))
        closed = agent.store.closed_positions(limit=200)
        data = {"mode": agent.executor.name, "label": agent.label, "equity": equity, "start": start,
                "cash": agent.store.cash(), "positions": pos_out, "paused": agent.entries_paused(),
                "prices": prices, "moves": moves, "vix": snap.get("vix"),
                "closed": len(closed), "closed_pnl": sum(p.pnl or 0 for p in closed),
                "started_at": agent.store.get("started_at"),
                "history": agent.store.equity_history(int(time.time()) - 30 * 86400),
                "last_tick_age": None if state.get("last_tick") is None else round(time.time() - state["last_tick"]),
                "server_time": time.time(), "books": worlds, "main": main,
                "system": {"llm": agent.llm.provider if agent.llm else None, "push": agent.push is not None,
                           "radar_age": None if not state.get("radar_tick") else round(time.time() - state["radar_tick"]),
                           "world_age": None if not state.get("world_tick") else round(time.time() - state["world_tick"]),
                           "last_error": state.get("last_error"), "radar_error": state.get("radar_error")}}
        with cache_lock:
            cache.update(at=time.time(), data=data)
        return data

    chart_cache: dict[tuple[str, str], tuple[float, list]] = {}
    chart_lock = threading.Lock()
    http = httpx.Client(timeout=15, headers={"User-Agent": "Mozilla/5.0 (milan-trader)"})
    RANGES = {   # (Binance intervallum, darab), (Yahoo range, intervallum)
        "1D": (("15m", 96), ("1d", "5m")), "1W": (("1h", 168), ("5d", "30m")),
        "1M": (("4h", 180), ("1mo", "60m")), "3M": (("1d", 90), ("3mo", "1d")), "1Y": (("1d", 365), ("1y", "1d")),
    }

    def series(sym: str, rng: str) -> list:
        (b_int, b_n), (y_rng, y_int) = RANGES[rng]
        if sym.endswith("USDT"):
            candles = agent.market.candles(sym, b_int, limit=b_n, closed_only=False)
            return [[c.close_time // 1000, c.close] for c in candles]
        r = http.get(f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(sym)}",
                     params={"range": y_rng, "interval": y_int})
        if r.status_code != 200:
            raise HTTPException(502, f"az árfolyam most nem érhető el (HTTP {r.status_code})")
        res = r.json()["chart"]["result"][0]
        closes = res["indicators"]["quote"][0]["close"]
        return [[t, c] for t, c in zip(res.get("timestamp") or [], closes) if c is not None]

    @router.get("/api/chart")
    def chart(sym: str, range: str = "1M", mtb_session: str | None = Cookie(default=None)):
        auth(mtb_session)
        if range not in RANGES or not re.fullmatch(r"[A-Za-z0-9^=.\-]{1,20}", sym):
            raise HTTPException(400, "hibás paraméter")
        key = (sym, range)
        with chart_lock:
            hit = chart_cache.get(key)
        if hit and time.time() - hit[0] < 60:
            pts = hit[1]
        else:
            try:
                pts = series(sym, range)
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(502, "az árfolyam most nem érhető el") from None
            with chart_lock:
                chart_cache[key] = (time.time(), pts)
                if len(chart_cache) > 300:
                    chart_cache.clear()
        pos = None
        for a in [agent] + list(agent.peers):
            p = a.store.open_position_for(sym) if sym in a.cfg.symbols else None
            if p:
                pos = {"entry": p.entry_price, "stop": p.stop, "target": p.target, "qty": p.qty, "side": p.side,
                       "kind": p.kind, "opened_at": p.opened_at, "entry_value": p.qty * p.entry_price + p.entry_fee,
                       "fee": p.entry_fee}
        return {"sym": sym, "name": agent.name_of(sym), "range": range, "points": pts, "position": pos}

    @router.get("/api/news")
    def news(mtb_session: str | None = Cookie(default=None)):
        auth(mtb_session)
        out = []
        for n in agent.store.recent_news(80):
            a = json.loads(n["analysis"]) if n.get("analysis") else {}
            out.append({"id": n["id"], "title": n["title"], "hu": a.get("hu"), "source": n["source"], "link": n["link"],
                        "seen_at": n["seen_at"], "published": n.get("published"), "sev": a.get("sev"),
                        "dir": a.get("dir"), "assets": a.get("assets") or [], "why": a.get("why")})
        return {"news": out}

    @router.get("/api/events")
    def events(after: int = 0, mtb_session: str | None = Cookie(default=None)):
        auth(mtb_session)
        return {"events": agent.store.events_after(max(0, after), 150)}

    @router.get("/api/chat")
    def history(mtb_session: str | None = Cookie(default=None)):
        auth(mtb_session)
        return {"messages": agent.store.recent_chat(40)}

    @router.post("/api/chat")
    def chat(body: Chat, mtb_session: str | None = Cookie(default=None)):
        auth(mtb_session)
        # A telefon böngészője kb. egy perc után feladja a kérést. Ha a modell lassú (túlterhelt),
        # 45 mp után válaszolunk, a modell pedig a háttérben befejezi, és a válasz bekerül a chatbe.
        result: dict = {}

        def work():
            with chat_lock:
                try:
                    reply = agent.respond(body.text) or "Ezt nem értettem. /help"
                except Exception:
                    reply = "A válasz összeállítása nem sikerült, próbáld újra."
                last = agent.store.recent_chat(1)
                if not last or last[-1]["content"] != reply[:4000]:   # a szabad kérdést az agent már elmentette
                    agent.store.add_chat("user", body.text)
                    agent.store.add_chat("assistant", reply)
                result["reply"] = reply

        t = threading.Thread(target=work, daemon=True)
        t.start()
        t.join(timeout=45)
        if "reply" in result:
            return {"reply": result["reply"], "pending": False}
        return {"reply": "⏳ Az AI most lassan válaszol. A válaszom pár perc múlva megjelenik itt magától.",
                "pending": True}

    return router
