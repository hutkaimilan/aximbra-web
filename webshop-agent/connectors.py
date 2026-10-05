"""Webshopmotorok bekötése: rendelés keresése szám vagy e-mail alapján.

Mindegyik csatoló ugyanazt az Order-t adja vissza, így az agent nem tudja,
melyik motor van mögötte. Új motor (Shoprenter, UNAS) = egy új osztály.

Csak OLVASUNK: egyik csatoló sem módosít rendelést.
"""
from __future__ import annotations

import os
import re
from dataclasses import asdict, dataclass, field

import httpx

TIMEOUT = 20


class ShopError(RuntimeError):
    pass


@dataclass
class Order:
    number: str
    email: str
    name: str = ""
    status: str = "unknown"      # received | processing | shipped | delivered | cancelled | refunded | on_hold | unknown
    created: str = ""            # ÉÉÉÉ-HH-NN
    total: str = ""              # "12 500 Ft" / "€39.90" — ahogy a bolt mutatja
    items: list[str] = field(default_factory=list)
    carrier: str = ""
    tracking_number: str = ""
    tracking_url: str = ""
    shipped: str = ""
    delivered: str = ""

    def facts(self) -> dict:
        """Amit a válasz egyáltalán említhet. Az e-mail-címet nem adjuk át a modellnek."""
        d = asdict(self)
        d.pop("email", None)
        return {k: v for k, v in d.items() if v}


def _norm_num(s: str) -> str:
    return re.sub(r"[^0-9a-z]", "", (s or "").lower())


class Shop:
    name = "shop"

    def find(self, number: str | None = None, email: str | None = None) -> list[Order]:
        raise NotImplementedError


# ---- demóbolt (ŐRLŐ kávépörkölő, kitalált) -----------------------------------

DEMO_ORDERS = [
    Order("ORL-1042", "anna.kovacs@example.com", "Kovács Anna", "shipped", "2026-10-02", "11 300 Ft",
          ["Etiópia Guji 250 g", "Kolumbia Huila 250 g"], "GLS", "GLS38441729", "https://gls-group.com/HU/hu/csomagkovetes?match=GLS38441729",
          shipped="2026-10-04"),
    Order("ORL-1043", "peter.nagy@example.com", "Nagy Péter", "processing", "2026-10-04", "5 200 Ft",
          ["Hétköznapi espresso 250 g"]),
    Order("ORL-1039", "anna.kovacs@example.com", "Kovács Anna", "delivered", "2026-09-21", "4 900 Ft",
          ["Brazília Cerrado 250 g"], "Foxpost", "FP7720155", "", shipped="2026-09-22", delivered="2026-09-24"),
]

DEMO_POLICY = {
    "hu": "Szállítás: a pörkölés után 48 órán belül feladjuk, GLS vagy Foxpost. Visszaküldés: bontatlan csomag 14 napon belül, a visszautalás 5 munkanap. Számlát minden rendelés után e-mailben küldünk, másolatot kérésre.",
    "en": "Shipping: dispatched within 48 hours of roasting via GLS or Foxpost. Returns: unopened packs within 14 days, refund within 5 working days. An invoice is emailed with every order; copies on request.",
    "de": "Versand: innerhalb von 48 Stunden nach der Röstung mit GLS oder Foxpost. Rückgabe: ungeöffnete Packungen innerhalb von 14 Tagen, Erstattung in 5 Werktagen. Die Rechnung kommt per E-Mail, Kopien auf Anfrage.",
}


# A látogatók próbarendelései (csak memóriában, 24 óráig, legfeljebb 2000 db).
_VISITOR: dict[str, tuple[float, Order]] = {}
VISITOR_TTL = 24 * 3600
VISITOR_MAX = 2000


def create_visitor_order(email: str, lang: str = "hu") -> Order:
    import random
    import time
    from datetime import date, timedelta
    now = time.time()
    for k, (t, _) in list(_VISITOR.items()):
        if now - t > VISITOR_TTL:
            _VISITOR.pop(k, None)
    if len(_VISITOR) >= VISITOR_MAX:
        _VISITOR.pop(next(iter(_VISITOR)))
    num = f"ORL-{random.randint(2000, 9999)}"
    while num in _VISITOR:
        num = f"ORL-{random.randint(2000, 9999)}"
    today = date.today()
    huf = lang == "hu"
    o = Order(num, email.strip(), "", "shipped", (today - timedelta(days=2)).isoformat(),
              "10 800 Ft" if huf else "€30.80", ["Etiópia Guji 250 g", "Hétköznapi espresso 250 g"] if huf else ["Ethiopia Guji 250 g", "Everyday espresso 250 g"],
              "GLS", f"GLS{random.randint(10_000_000, 99_999_999)}", "", shipped=(today - timedelta(days=1)).isoformat())
    o.tracking_url = f"https://gls-group.com/HU/hu/csomagkovetes?match={o.tracking_number}"
    _VISITOR[num] = (now, o)
    return o


class DemoShop(Shop):
    name = "demo"

    def find(self, number=None, email=None):
        out = []
        for o in DEMO_ORDERS + [v for _, v in _VISITOR.values()]:
            if number and re.sub(r"\D", "", o.number) != re.sub(r"\D", "", number):
                continue
            if email and o.email.lower() != email.lower():
                continue
            if number or email:
                out.append(o)
        return out


# ---- WooCommerce (REST v3) ---------------------------------------------------

WOO_STATUS = {"pending": "received", "processing": "processing", "on-hold": "on_hold", "completed": "delivered",
              "cancelled": "cancelled", "refunded": "refunded", "failed": "cancelled"}


class WooCommerce(Shop):
    """Kulcs: WooCommerce → Beállítások → Haladó → REST API → csak olvasási jog."""
    name = "woocommerce"

    def __init__(self, base_url: str, key: str, secret: str):
        self.base = base_url.rstrip("/") + "/wp-json/wc/v3"
        self.auth = (key, secret)

    def _get(self, path: str, params: dict | None = None):
        try:
            r = httpx.get(self.base + path, params=params or {}, auth=self.auth, timeout=TIMEOUT)
        except httpx.HTTPError as e:
            raise ShopError(f"a webshop nem érhető el ({type(e).__name__})") from e
        if r.status_code == 404:
            return None
        if r.status_code >= 400:
            raise ShopError(f"WooCommerce: HTTP {r.status_code}")
        return r.json()

    @staticmethod
    def _order(o: dict) -> Order:
        b = o.get("billing") or {}
        tracking = {}
        for m in o.get("meta_data") or []:
            if m.get("key") == "_wc_shipment_tracking_items" and m.get("value"):
                tracking = (m["value"] or [{}])[-1]
        cur = o.get("currency") or ""
        return Order(
            number=str(o.get("number") or o.get("id")), email=(b.get("email") or "").strip(),
            name=f"{b.get('last_name', '')} {b.get('first_name', '')}".strip(),
            status=("shipped" if tracking and o.get("status") == "processing" else WOO_STATUS.get(o.get("status", ""), "unknown")),
            created=(o.get("date_created") or "")[:10], total=f"{o.get('total', '')} {cur}".strip(),
            items=[f"{i.get('name')} × {i.get('quantity')}" for i in o.get("line_items") or []],
            carrier=tracking.get("tracking_provider") or tracking.get("custom_tracking_provider") or "",
            tracking_number=tracking.get("tracking_number") or "", tracking_url=tracking.get("custom_tracking_link") or "",
        )

    def find(self, number=None, email=None):
        if number:
            o = self._get(f"/orders/{re.sub(r'[^0-9]', '', number)}") if re.sub(r"[^0-9]", "", number) else None
            found = [self._order(o)] if o else []
            if not found:
                found = [self._order(x) for x in (self._get("/orders", {"search": number, "per_page": 5}) or [])]
            return [x for x in found if not email or x.email.lower() == email.lower()]
        if email:
            return [self._order(x) for x in (self._get("/orders", {"search": email, "per_page": 5}) or [])
                    if (x.get("billing") or {}).get("email", "").lower() == email.lower()]
        return []


# ---- Shopify (Admin REST) ----------------------------------------------------

class Shopify(Shop):
    """Kulcs: Shopify admin → Settings → Apps → Develop apps → read_orders jog."""
    name = "shopify"
    API = "2025-01"

    def __init__(self, domain: str, token: str):
        self.base = f"https://{domain.strip().rstrip('/')}/admin/api/{self.API}"
        self.head = {"X-Shopify-Access-Token": token}

    def _orders(self, params: dict) -> list[dict]:
        try:
            r = httpx.get(self.base + "/orders.json", params={"status": "any", "limit": 5, **params},
                          headers=self.head, timeout=TIMEOUT)
        except httpx.HTTPError as e:
            raise ShopError(f"a webshop nem érhető el ({type(e).__name__})") from e
        if r.status_code >= 400:
            raise ShopError(f"Shopify: HTTP {r.status_code}")
        return r.json().get("orders") or []

    @staticmethod
    def _order(o: dict) -> Order:
        f = (o.get("fulfillments") or [{}])[-1]
        status = "cancelled" if o.get("cancelled_at") else {
            "fulfilled": "shipped", "partial": "shipped"}.get(o.get("fulfillment_status") or "", "processing")
        if f.get("shipment_status") == "delivered":
            status = "delivered"
        if o.get("financial_status") == "refunded":
            status = "refunded"
        return Order(
            number=str(o.get("name") or o.get("order_number")).lstrip("#"), email=(o.get("email") or "").strip(),
            name=" ".join(x for x in [(o.get("customer") or {}).get("last_name"), (o.get("customer") or {}).get("first_name")] if x),
            status=status, created=(o.get("created_at") or "")[:10], total=f"{o.get('total_price', '')} {o.get('currency', '')}".strip(),
            items=[f"{i.get('name')} × {i.get('quantity')}" for i in o.get("line_items") or []],
            carrier=f.get("tracking_company") or "", tracking_number=f.get("tracking_number") or "",
            tracking_url=f.get("tracking_url") or "", shipped=(f.get("created_at") or "")[:10],
        )

    def find(self, number=None, email=None):
        params = {}
        if number:
            params["name"] = "#" + re.sub(r"[^0-9A-Za-z-]", "", number)
        if email:
            params["email"] = email
        if not params:
            return []
        return [self._order(o) for o in self._orders(params)
                if not email or (o.get("email") or "").lower() == email.lower()]


def shop_from_env() -> Shop:
    kind = (os.environ.get("SHOP_KIND") or "demo").strip().lower()
    if kind == "woocommerce":
        return WooCommerce(os.environ["WOO_URL"], os.environ["WOO_KEY"], os.environ["WOO_SECRET"])
    if kind == "shopify":
        return Shopify(os.environ["SHOPIFY_DOMAIN"], os.environ["SHOPIFY_TOKEN"])
    return DemoShop()
