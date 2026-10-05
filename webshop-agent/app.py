"""Webshop ügyfélszolgálati agent — HTTP felület.

- POST /api/reply: éles használat (X-Agent-Token), a beállított webshopmotorral.
- POST /api/demo/reply: nyilvános demó az aximbra.hu-nak, mindig a kitalált
  ŐRLŐ demóbolttal; IP-nként korlátozva, hogy a modellkeretet ne lehessen leszívni.
"""
from __future__ import annotations

import logging
import os
import secrets
import threading
import time
from collections import deque

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

import agent
import re

from connectors import DemoShop, create_visitor_order, shop_from_env

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="AXIMBRA webshop agent")
app.add_middleware(CORSMiddleware, allow_origins=["https://aximbra.hu", "https://www.aximbra.hu", "http://localhost:3000"],
                   allow_methods=["POST", "GET"], allow_headers=["*"])

DEMO_PER_HOUR = int(os.environ.get("DEMO_PER_HOUR", "20"))
DEMO_PER_DAY_TOTAL = int(os.environ.get("DEMO_PER_DAY_TOTAL", "500"))
_hits: dict[str, deque] = {}
_day = {"d": "", "n": 0}
_lock = threading.Lock()


class MailIn(BaseModel):
    from_email: str = Field(default="", max_length=200)
    subject: str = Field(default="", max_length=300)
    body: str = Field(min_length=3, max_length=6000)


@app.get("/health")
def health():
    return {"ok": True, "shop": os.environ.get("SHOP_KIND", "demo")}


@app.post("/api/reply")
def api_reply(m: MailIn, x_agent_token: str = Header(default="")):
    want = os.environ.get("AGENT_TOKEN", "")
    if len(want) < 24:
        raise HTTPException(503, "Nincs beállítva AGENT_TOKEN.")
    if not secrets.compare_digest(x_agent_token.encode(), want.encode()):
        time.sleep(1)
        raise HTTPException(401, "Hibás kulcs.")
    try:
        shop = shop_from_env()
    except KeyError as e:
        raise HTTPException(503, f"Hiányzó webshop-beállítás: {e}")
    return agent.reply(shop, m.from_email, m.subject, m.body, shop_name=os.environ.get("SHOP_NAME", "AXIMBRA demo"))


def _limit(ip: str) -> None:
    now = time.time()
    today = time.strftime("%Y-%m-%d")
    with _lock:
        if _day["d"] != today:
            _day.update(d=today, n=0)
        if _day["n"] >= DEMO_PER_DAY_TOTAL:
            raise HTTPException(429, "A demó mára elérte a napi keretet. Holnap újra kipróbálható.")
        q = _hits.setdefault(ip, deque())
        while q and now - q[0] > 3600:
            q.popleft()
        if len(q) >= DEMO_PER_HOUR:
            raise HTTPException(429, "Túl sok próbálkozás. Egy óra múlva újra mehet.")
        q.append(now)
        _day["n"] += 1


@app.post("/api/demo/reply")
def demo_reply(m: MailIn, request: Request):
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    _limit(ip)
    return agent.reply(DemoShop(), m.from_email, m.subject, m.body, shop_name="ŐRLŐ")


class OrderIn(BaseModel):
    email: str = Field(max_length=200)
    lang: str = "hu"


@app.post("/api/demo/order")
def demo_order(m: OrderIn, request: Request):
    """Próbarendelés a látogató saját címére, hogy a saját e-mailjével próbálhassa ki az agentet."""
    if not re.fullmatch(r"[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}", m.email.strip()):
        raise HTTPException(422, "Adj meg egy érvényes e-mail-címet.")
    ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")).split(",")[0].strip()
    _limit(ip)
    o = create_visitor_order(m.email, m.lang if m.lang in ("hu", "en", "de") else "en")
    return {"number": o.number, "items": o.items, "total": o.total}
