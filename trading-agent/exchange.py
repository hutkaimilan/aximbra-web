"""Végrehajtás: papír (szimuláció) vagy Binance (demó vagy éles) spot megbízások.

A stratégia és a kockázati szabályok ugyanazok; csak az változik, hogy a
kötés a naplóban születik-e, vagy a tőzsdén.

Binance-biztonsági elvek:
- Minden megbízás determinisztikus clientOrderId-t kap. Ha egy kérés sorsa
  bizonytalan (időtúllépés, 5xx), előbb lekérdezzük, és csak akkor adjuk le
  újra, ha biztosan nem létezik — így nincs dupla vétel.
- A védőstop a TŐZSDÉN van (STOP_LOSS_LIMIT), tehát akkor is véd, ha a bot leáll.
  Ha a stopot nem sikerül leadni, a hívó azonnal kiszáll a pozícióból.
- Az aláírás Ed25519: a privát kulcs csak a szerveren van, a Binance csak a
  nyilvános felét ismeri, kivételi jog nincs a kulcson.
"""
from __future__ import annotations

import base64
import logging
import os
import time
import urllib.parse
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

import httpx

logger = logging.getLogger(__name__)

DEMO_URL = "https://demo-api.binance.com"
STOP_LIMIT_GAP = Decimal("0.005")   # a stop-limit ár ennyivel a stop alatt, hogy gyors esésben is teljesüljön


class ExchangeError(RuntimeError):
    def __init__(self, msg: str, code: int | None = None, uncertain: bool = False):
        super().__init__(msg)
        self.code = code
        self.uncertain = uncertain   # nem tudni, a tőzsde végrehajtotta-e


@dataclass(frozen=True)
class Fill:
    qty: float       # ténylegesen birtokolt mennyiség (díj levonva, ha alapdevizában vonták)
    price: float     # átlagár
    fee: float       # díj USDT-ben (becslés, ha nem USDT-ben vonták)


# --- papír ------------------------------------------------------------------------
class PaperExecutor:
    live = False
    name = "papír"

    def __init__(self, fee: float, slippage: float):
        self.fee, self.slippage = fee, slippage

    def round_qty(self, symbol: str, qty: float) -> float:
        return qty

    def min_notional(self, symbol: str) -> float:
        return 10.0

    def buy(self, symbol: str, qty: float, price: float, cid: str) -> Fill:
        px = price * (1 + self.slippage)
        return Fill(qty, px, qty * px * self.fee)

    def sell(self, symbol: str, qty: float, price: float, cid: str) -> Fill:
        px = price * (1 - self.slippage)
        return Fill(qty, px, qty * px * self.fee)

    def protect(self, symbol: str, qty: float, stop: float, cid: str) -> None:
        return None

    def unprotect(self, symbol: str, cid: str | None) -> None:
        return None

    def stop_state(self, symbol: str, cid: str | None):
        return None

    def lookup(self, symbol: str, cid: str):
        return None


# --- Binance -----------------------------------------------------------------------
def _dec(x) -> Decimal:
    return Decimal(str(x))


def _floor(value: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        return value
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def _fmt(d: Decimal) -> str:
    s = format(d.normalize(), "f")
    return s if s not in ("-0", "") else "0"


class BinanceClient:
    def __init__(self, api_key: str, private_key_pem: str, base_url: str = DEMO_URL,
                 client: httpx.Client | None = None, fee: float = 0.001):
        from cryptography.hazmat.primitives.serialization import load_pem_private_key
        self._key = api_key
        try:
            self._signer = load_pem_private_key(private_key_pem.encode(), password=None)
        except (ValueError, TypeError) as e:
            raise ExchangeError(f"a BINANCE_PRIVATE_KEY nem érvényes PEM kulcs ({type(e).__name__})") from None
        self.base = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=15)
        self.fee = fee
        self._filters: dict[str, dict] = {}

    @classmethod
    def from_env(cls, fee: float) -> "BinanceClient | None":
        key = os.environ.get("BINANCE_API_KEY", "").strip()
        pem = os.environ.get("BINANCE_PRIVATE_KEY", "").strip().replace("\\n", "\n")
        if not (key and pem):
            return None
        return cls(key, pem, os.environ.get("BINANCE_BASE_URL", DEMO_URL).strip() or DEMO_URL, fee=fee)

    @property
    def is_demo(self) -> bool:
        return "demo-api" in self.base or "testnet" in self.base

    def _request(self, method: str, path: str, params: dict | None = None, signed: bool = False):
        params = {k: v for k, v in (params or {}).items() if v is not None}
        headers = {}
        if signed:
            params["timestamp"] = int(time.time() * 1000)
            params["recvWindow"] = 10_000
            query = urllib.parse.urlencode(params)
            sig = base64.b64encode(self._signer.sign(query.encode("ascii"))).decode()
            query += "&signature=" + urllib.parse.quote(sig, safe="")
            headers["X-MBX-APIKEY"] = self._key
        else:
            query = urllib.parse.urlencode(params)
        url = f"{self.base}{path}" + (f"?{query}" if query else "")
        try:
            r = self.client.request(method, url, headers=headers)
        except httpx.TimeoutException:
            raise ExchangeError("a Binance nem válaszolt időben", uncertain=True) from None
        except httpx.HTTPError as e:
            raise ExchangeError(f"a Binance nem érhető el ({type(e).__name__})", uncertain=method != "GET") from None
        try:
            data = r.json()
        except ValueError:
            data = None
        if r.status_code >= 500:
            raise ExchangeError(f"Binance-szerverhiba (HTTP {r.status_code})", uncertain=method != "GET")
        if r.status_code >= 400:
            code = data.get("code") if isinstance(data, dict) else None
            msg = data.get("msg") if isinstance(data, dict) else r.text[:200]
            raise ExchangeError(f"Binance-hiba ({code}): {msg}", code=code)
        return data

    # --- lekérdezések
    def account(self) -> dict:
        return self._request("GET", "/api/v3/account", {"omitZeroBalances": "true"}, signed=True)

    def free(self, asset: str) -> float:
        for b in self.account().get("balances", []):
            if b.get("asset") == asset:
                return float(b.get("free", 0))
        return 0.0

    def filters(self, symbol: str) -> dict:
        if symbol not in self._filters:
            info = self._request("GET", "/api/v3/exchangeInfo", {"symbol": symbol})
            sym = (info.get("symbols") or [None])[0]
            if not sym:
                raise ExchangeError(f"ismeretlen instrumentum: {symbol}")
            f = {x["filterType"]: x for x in sym.get("filters", [])}
            self._filters[symbol] = {
                "base": sym["baseAsset"], "quote": sym["quoteAsset"],
                "step": _dec(f.get("LOT_SIZE", {}).get("stepSize", "0")),
                "min_qty": _dec(f.get("LOT_SIZE", {}).get("minQty", "0")),
                "tick": _dec(f.get("PRICE_FILTER", {}).get("tickSize", "0")),
                "min_notional": float((f.get("NOTIONAL") or f.get("MIN_NOTIONAL") or {}).get("minNotional", 5)),
                "order_types": sym.get("orderTypes", []),
            }
        return self._filters[symbol]

    def get_order(self, symbol: str, cid: str) -> dict | None:
        try:
            return self._request("GET", "/api/v3/order", {"symbol": symbol, "origClientOrderId": cid}, signed=True)
        except ExchangeError as e:
            if e.code == -2013:   # Order does not exist
                return None
            raise

    def place(self, params: dict) -> dict:
        """Megbízás idempotensen: bizonytalan eredménynél lekérdez, mielőtt bármit újra küldene."""
        cid = params["newClientOrderId"]
        try:
            return self._request("POST", "/api/v3/order", params, signed=True)
        except ExchangeError as e:
            if e.code == -2010 and "Duplicate" in str(e):
                found = self.get_order(params["symbol"], cid)
                if found:
                    return found
            if not e.uncertain:
                raise
        for attempt in range(3):
            time.sleep(1 + attempt)
            try:
                found = self.get_order(params["symbol"], cid)
            except ExchangeError:
                continue
            if found:
                return found
            break
        return self._request("POST", "/api/v3/order", params, signed=True)

    def cancel(self, symbol: str, cid: str) -> None:
        try:
            self._request("DELETE", "/api/v3/order", {"symbol": symbol, "origClientOrderId": cid}, signed=True)
        except ExchangeError as e:
            if e.code in (-2011, -2013):   # már nincs ilyen nyitott megbízás
                return
            raise


class BinanceExecutor:
    live = True

    def __init__(self, client: BinanceClient):
        self.c = client
        self.name = "Binance demó" if client.is_demo else "Binance ÉLES"

    def round_qty(self, symbol: str, qty: float) -> float:
        f = self.c.filters(symbol)
        q = _floor(_dec(qty), f["step"])
        return float(q) if q >= f["min_qty"] else 0.0

    def min_notional(self, symbol: str) -> float:
        return self.c.filters(symbol)["min_notional"]

    def _fill(self, symbol: str, order: dict, side: str) -> Fill:
        f = self.c.filters(symbol)
        executed = float(order.get("executedQty", 0))
        quote = float(order.get("cummulativeQuoteQty", 0))
        if executed <= 0:
            raise ExchangeError(f"a megbízás nem teljesült (állapot: {order.get('status')})")
        avg = quote / executed
        fee_usdt, base_fee = 0.0, 0.0
        fills = order.get("fills")
        if fills:
            for x in fills:
                comm, asset = float(x.get("commission", 0)), x.get("commissionAsset")
                if asset == f["base"]:
                    base_fee += comm
                    fee_usdt += comm * float(x.get("price", avg))
                elif asset == f["quote"]:
                    fee_usdt += comm
                else:  # pl. BNB-ben vont díj: becsüljük
                    fee_usdt += float(x.get("qty", 0)) * float(x.get("price", avg)) * self.c.fee
        else:
            fee_usdt = quote * self.c.fee
            if side == "BUY":
                base_fee = executed * self.c.fee
        held = executed - base_fee if side == "BUY" else executed
        return Fill(held, avg, fee_usdt)

    def buy(self, symbol: str, qty: float, price: float, cid: str) -> Fill:
        q = self.round_qty(symbol, qty)
        if q <= 0:
            raise ExchangeError("a mennyiség a tőzsdei minimum alatt van")
        order = self.c.place({"symbol": symbol, "side": "BUY", "type": "MARKET", "quantity": _fmt(_dec(q)),
                              "newClientOrderId": cid, "newOrderRespType": "FULL"})
        return self._fill(symbol, order, "BUY")

    def sell(self, symbol: str, qty: float, price: float, cid: str) -> Fill:
        f = self.c.filters(symbol)
        free = self.c.free(f["base"])
        q = self.round_qty(symbol, min(qty, free))
        if q <= 0:
            raise ExchangeError(f"nincs eladható mennyiség (szabad {f['base']}: {free})")
        order = self.c.place({"symbol": symbol, "side": "SELL", "type": "MARKET", "quantity": _fmt(_dec(q)),
                              "newClientOrderId": cid, "newOrderRespType": "FULL"})
        return self._fill(symbol, order, "SELL")

    def protect(self, symbol: str, qty: float, stop: float, cid: str) -> None:
        f = self.c.filters(symbol)
        if "STOP_LOSS_LIMIT" not in f["order_types"]:
            raise ExchangeError(f"{symbol}: a tőzsde nem enged STOP_LOSS_LIMIT megbízást")
        q = self.round_qty(symbol, qty)
        if q <= 0:
            raise ExchangeError("a stop mennyisége a tőzsdei minimum alatt van")
        stop_px = _floor(_dec(stop), f["tick"])
        limit_px = _floor(stop_px * (1 - STOP_LIMIT_GAP), f["tick"])
        self.c.place({"symbol": symbol, "side": "SELL", "type": "STOP_LOSS_LIMIT", "timeInForce": "GTC",
                      "quantity": _fmt(_dec(q)), "stopPrice": _fmt(stop_px), "price": _fmt(limit_px),
                      "newClientOrderId": cid})

    def unprotect(self, symbol: str, cid: str | None) -> None:
        if cid:
            self.c.cancel(symbol, cid)

    def lookup(self, symbol: str, cid: str) -> Fill | None:
        """Egy korábbi vétel eredménye a tőzsdéről (helyreállításhoz). None, ha nem jött létre."""
        order = self.c.get_order(symbol, cid)
        if not order or float(order.get("executedQty", 0)) <= 0:
            return None
        return self._fill(symbol, order, "BUY")

    def stop_state(self, symbol: str, cid: str | None):
        """None: a stop él, nincs teendő. ("filled", Fill): kiütött. ("gone", None): eltűnt a stop."""
        if not cid:
            return ("gone", None)
        order = self.c.get_order(symbol, cid)
        if order is None:
            return ("gone", None)
        status = order.get("status")
        if status == "FILLED":
            return ("filled", self._fill(symbol, order, "SELL"))
        if status in ("NEW", "PARTIALLY_FILLED", "PENDING_NEW"):
            return None
        return ("gone", None)


def selftest(client: BinanceClient, symbol: str = "BTCUSDT") -> list[str]:
    """Kis valódi kör a demószámlán: vétel → stop → stop törlése → eladás.
    Minden lépés eredménye egy sor; az első hibánál megáll."""
    ex = BinanceExecutor(client)
    out = []
    stamp = int(time.time())
    try:
        usdt = client.free("USDT")
        out.append(f"✅ fiók elérhető, szabad USDT: {usdt:,.2f}")
        f = client.filters(symbol)
        out.append(f"✅ {symbol} szabályai: lépésköz {f['step']}, min. kötés {f['min_notional']} USDT")
        price = float(client._request("GET", "/api/v3/ticker/price", {"symbol": symbol})["price"])
        qty = (max(f["min_notional"], 5) * 2.2) / price
        buy = ex.buy(symbol, qty, price, f"mtb-test-{stamp}-b")
        out.append(f"✅ vétel teljesült: {buy.qty:.6f} @ {buy.price:,.2f}")
        ex.protect(symbol, buy.qty, buy.price * 0.9, f"mtb-test-{stamp}-s")
        state = ex.stop_state(symbol, f"mtb-test-{stamp}-s")
        out.append("✅ védőstop a tőzsdén" if state is None else f"⚠️ stop állapota: {state[0]}")
        ex.unprotect(symbol, f"mtb-test-{stamp}-s")
        out.append("✅ stop törölve")
        sell = ex.sell(symbol, buy.qty, price, f"mtb-test-{stamp}-x")
        out.append(f"✅ eladás teljesült: {sell.qty:.6f} @ {sell.price:,.2f}")
    except ExchangeError as e:
        out.append(f"❌ {e}")
    return out
