"""Az élő felület: jelszóval védett weboldal — állapot, hírfolyam, világpiaci radar, chat a bottal.

Belépés: WEB_PASSWORD. A süti a jelszóból képzett HMAC, HttpOnly + Secure + SameSite=Strict.
Hibás próbálkozásból legfeljebb 8 lehet 10 percen belül (nyers erő ellen).
"""
from __future__ import annotations

import hashlib
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
        positions = agent.store.open_positions()
        prices = agent._prices([p.symbol for p in positions] + list(agent.cfg.symbols), {})
        equity = agent.equity(prices)
        start = agent.store.start_equity()
        pos_out = []
        for p in positions:
            px = prices.get(p.symbol)
            pos_out.append({"symbol": p.symbol, "qty": p.qty, "entry": p.entry_price, "stop": p.stop,
                            "target": p.target, "price": px, "opened_at": p.opened_at,
                            "entry_value": p.qty * p.entry_price + p.entry_fee,
                            "value": p.qty * px if px else None,
                            "pnl": p.qty * (px - p.entry_price) - p.entry_fee if px else None})
        snap = agent.radar.snapshot() if agent.radar else {}
        moves = {}
        if agent.radar:
            moves = sorted(({"name": m.name, "cls": m.cls, "price": m.price, "day": m.day_pct, "week": m.week_pct,
                             "z": m.z} for m in (agent.radar.moves or {}).values()), key=lambda m: -abs(m["z"]))
        closed = agent.store.closed_positions(limit=200)
        data = {"mode": agent.executor.name, "label": agent.label, "equity": equity, "start": start,
                "cash": agent.store.cash(), "positions": pos_out, "paused": agent.entries_paused(),
                "prices": prices, "moves": moves, "vix": snap.get("vix"),
                "closed": len(closed), "closed_pnl": sum(p.pnl or 0 for p in closed),
                "started_at": agent.store.get("started_at"),
                "history": agent.store.equity_history(int(time.time()) - 30 * 86400),
                "last_tick_age": None if state.get("last_tick") is None else round(time.time() - state["last_tick"]),
                "server_time": time.time()}
        with cache_lock:
            cache.update(at=time.time(), data=data)
        return data

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
        if not chat_lock.acquire(timeout=90):
            raise HTTPException(429, "még dolgozom az előző kérdésen")
        try:
            reply = agent.respond(body.text) or "Ezt nem értettem. /help"
        except Exception:
            raise HTTPException(500, "a válasz összeállítása nem sikerült") from None
        finally:
            chat_lock.release()
        if not body.text.startswith("/"):
            pass  # a szabad kérdéseket az agent.answer már elmentette
        else:
            agent.store.add_chat("user", body.text)
            agent.store.add_chat("assistant", reply)
        return {"reply": reply}

    return router
