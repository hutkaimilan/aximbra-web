"""Világpiaci árfolyamok (részvény, index, nyersanyag, kripto) a Yahoo Finance-ről, a Market felületével.

Napi gyertyák: a még alakuló mai gyertya kimarad. A gyertyákat 30 percig gyorsítótárazzuk
(naponta egyszer változnak), az árat 2 percig — így a Yahoo-t percenként legfeljebb
néhányszor kérdezzük.
"""
from __future__ import annotations

import threading
import time
from urllib.parse import quote

import httpx

from market import Candle, MarketError

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{}"


class YahooMarket:
    def __init__(self, client: httpx.Client | None = None, clock=time.time):
        self.client = client or httpx.Client(timeout=20, headers={"User-Agent": "Mozilla/5.0 (milan-trader)"})
        self.clock = clock
        self._lock = threading.Lock()
        self._candles: dict[str, tuple[float, list[Candle]]] = {}
        self._price: dict[str, tuple[float, float]] = {}

    def _chart(self, symbol: str, rng: str) -> dict:
        try:
            r = self.client.get(URL.format(quote(symbol)), params={"range": rng, "interval": "1d"})
        except httpx.HTTPError as e:
            raise MarketError(f"a Yahoo nem érhető el ({type(e).__name__})") from None
        if r.status_code == 429:
            raise MarketError("a Yahoo korlátozza a kéréseket (429)")
        if r.status_code != 200:
            raise MarketError(f"Yahoo-hiba (HTTP {r.status_code})")
        try:
            return r.json()["chart"]["result"][0]
        except (ValueError, KeyError, IndexError, TypeError):
            raise MarketError("váratlan Yahoo-válasz") from None

    def candles(self, symbol: str, interval: str = "1d", limit: int = 300, **_) -> list[Candle]:
        if interval != "1d":
            raise MarketError("a világpiaci forrás csak napi gyertyát ad")
        now = self.clock()
        with self._lock:
            hit = self._candles.get(symbol)
        if hit and now - hit[0] < 1800:
            return hit[1][-limit:]
        res = self._chart(symbol, "2y")
        q = res.get("indicators", {}).get("quote", [{}])[0]
        out = []
        for t, o, h, l, c, v in zip(res.get("timestamp") or [], q.get("open") or [], q.get("high") or [],
                                    q.get("low") or [], q.get("close") or [], q.get("volume") or []):
            if None in (t, o, h, l, c) or c <= 0:
                continue
            close_ms = (int(t) + 86400) * 1000 - 1
            if close_ms >= now * 1000:          # a mai, még alakuló gyertya
                continue
            out.append(Candle(int(t) * 1000, float(o), float(h), float(l), float(c), float(v or 0), close_ms))
        if len(out) < 30:
            raise MarketError(f"kevés napi adat ({len(out)})")
        with self._lock:
            self._candles[symbol] = (now, out)
        return out[-limit:]

    def price(self, symbol: str) -> float:
        now = self.clock()
        with self._lock:
            hit = self._price.get(symbol)
        if hit and now - hit[0] < 120:
            return hit[1]
        meta = self._chart(symbol, "5d").get("meta", {})
        p = meta.get("regularMarketPrice")
        if not isinstance(p, (int, float)) or p <= 0:
            raise MarketError("nincs aktuális ár")
        with self._lock:
            self._price[symbol] = (now, float(p))
        return float(p)

    def history(self, symbol: str, interval: str, total: int) -> list[Candle]:
        return self.candles(symbol, interval, limit=total)
