"""Valódi árfolyamok a Binance nyilvános piaci adatvégpontjáról, kulcs nélkül.

Miért a data-api.binance.vision és nem az api.binance.com: az utóbbi amerikai
IP-ről 451-et ad (a Railway alapértelmezett régiója is amerikai). A
data-api.binance.vision csak piaci adatot szolgál ki, és onnan is elérhető.
Az árak ugyanazok, mint az éles tőzsdén — a próbaverzió ezért valódi piacon
fut, csak a pénz nem valódi.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("MARKET_DATA_URL", "https://data-api.binance.vision").rstrip("/")
TIMEOUT = 15


class MarketError(RuntimeError):
    pass


@dataclass(frozen=True)
class Candle:
    open_time: int    # ms, UTC
    open: float
    high: float
    low: float
    close: float
    volume: float
    close_time: int   # ms, UTC


class Market:
    def __init__(self, base_url: str = BASE_URL, client: httpx.Client | None = None):
        self.base = base_url
        self.client = client or httpx.Client(timeout=TIMEOUT)

    def _get(self, path: str, params: dict):
        last = "ismeretlen hiba"
        for attempt in range(3):
            try:
                r = self.client.get(self.base + path, params=params)
            except httpx.HTTPError as e:
                last = f"hálózati hiba ({type(e).__name__})"
            else:
                if r.status_code == 200:
                    try:
                        return r.json()
                    except ValueError:
                        last = "nem JSON választ kaptunk"
                elif r.status_code == 451:
                    raise MarketError("a tőzsde ebből a régióból nem engedi az elérést (HTTP 451)")
                elif r.status_code in (418, 429):
                    # A Binance a korlát utáni további kéréseket IP-tiltással bünteti:
                    # itt nem próbálkozunk újra, a következő ciklus majd igen.
                    wait = r.headers.get("Retry-After", "?")
                    raise MarketError(f"kéréskorlát (HTTP {r.status_code}), várakozás: {wait} mp")
                elif 400 <= r.status_code < 500:
                    raise MarketError(f"hibás kérés (HTTP {r.status_code}): {r.text[:200]}")
                else:
                    last = f"HTTP {r.status_code}"
            if attempt < 2:
                time.sleep(2 ** attempt)
        raise MarketError(f"az árfolyam nem érhető el: {last}")

    def candles(self, symbol: str, interval: str, limit: int = 300, end_time: int | None = None,
                closed_only: bool = True, now_ms: int | None = None) -> list[Candle]:
        """Gyertyák időrendben. closed_only: a még alakuló utolsó gyertya kimarad,
        mert arra jelzést adni annyi, mint a jövőbe nézni."""
        params: dict = {"symbol": symbol, "interval": interval, "limit": min(max(int(limit), 1), 1000)}
        if end_time is not None:
            params["endTime"] = int(end_time)
        rows = self._get("/api/v3/klines", params)
        if not isinstance(rows, list):
            raise MarketError("váratlan válaszformátum a gyertyáknál")
        out = []
        for row in rows:
            try:
                out.append(Candle(int(row[0]), float(row[1]), float(row[2]), float(row[3]),
                                  float(row[4]), float(row[5]), int(row[6])))
            except (TypeError, ValueError, IndexError):
                raise MarketError("hibás gyertyaadat a válaszban") from None
        if closed_only:
            now = now_ms if now_ms is not None else int(time.time() * 1000)
            out = [c for c in out if c.close_time < now]
        return out

    def history(self, symbol: str, interval: str, total: int) -> list[Candle]:
        """Legfeljebb `total` lezárt gyertya visszafelé lapozva (1000-es lapokban)."""
        total = max(1, min(int(total), 20_000))
        out: list[Candle] = []
        end = None
        while len(out) < total:
            want = min(1000, total - len(out))
            batch = self.candles(symbol, interval, limit=want, end_time=end)
            if not batch:
                break
            out = batch + out
            end = batch[0].open_time - 1
            if len(batch) < want - 1:   # elértük a kereskedés kezdetét
                break
        seen: dict[int, Candle] = {c.open_time: c for c in out}
        return [seen[k] for k in sorted(seen)][-total:]

    def price(self, symbol: str) -> float:
        data = self._get("/api/v3/ticker/price", {"symbol": symbol})
        try:
            value = float(data["price"])
        except (TypeError, KeyError, ValueError):
            raise MarketError("hibás árfolyam a válaszban") from None
        if value <= 0:
            raise MarketError("nem pozitív árfolyam a válaszban")
        return value
