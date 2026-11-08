"""Világpiaci radar: árfolyamok és hírek folyamatos figyelése.

Két forrás, mindkettő kulcs nélkül:
- Árak: Yahoo Finance nyilvános diagramvégpontja (forex, indexek, nyersanyagok, részvények, kripto, VIX).
- Hírek: nyilvános RSS-csatornák (BBC, MarketWatch, CoinDesk, Cointelegraph, Fed, EKB, Google News).

Amit a radar NEM csinál: nem jósol árat. Azt mondja meg, hogy mi történik MOST és mi
szokatlan (mozgás a megszokott ingadozáshoz képest, pánikjelek, súlyos hírek), hogy ne
érjen készületlenül. A mérések szerint a napi irány megjósolhatatlan közel véletlen
(walk-forward AUC ≈ 0,51), a nagy esések előjele gyenge (≈ 0,59).
"""
from __future__ import annotations

import json
import logging
import math
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import httpx

from llm import LLMError, extract_json

logger = logging.getLogger(__name__)

UNIVERSE: dict[str, tuple[str, str]] = {
    # jel: (név, osztály)
    "EURUSD=X": ("EUR/USD", "forex"), "GBPUSD=X": ("GBP/USD", "forex"), "USDJPY=X": ("USD/JPY", "forex"),
    "AUDUSD=X": ("AUD/USD", "forex"), "USDCAD=X": ("USD/CAD", "forex"), "USDCHF=X": ("USD/CHF", "forex"),
    "USDHUF=X": ("USD/HUF", "forex"), "EURHUF=X": ("EUR/HUF", "forex"),
    "^GSPC": ("S&P 500", "index"), "^IXIC": ("Nasdaq", "index"), "^DJI": ("Dow Jones", "index"),
    "^GDAXI": ("DAX", "index"), "^FTSE": ("FTSE 100", "index"), "^N225": ("Nikkei 225", "index"),
    "^HSI": ("Hang Seng", "index"),
    "GC=F": ("Arany", "commodity"), "SI=F": ("Ezüst", "commodity"), "CL=F": ("WTI olaj", "commodity"),
    "NG=F": ("Földgáz", "commodity"),
    "AAPL": ("Apple", "stock"), "MSFT": ("Microsoft", "stock"), "NVDA": ("Nvidia", "stock"),
    "AMZN": ("Amazon", "stock"), "GOOGL": ("Alphabet", "stock"), "META": ("Meta", "stock"),
    "TSLA": ("Tesla", "stock"), "JPM": ("JPMorgan", "stock"),
    "AMD": ("AMD", "stock"), "NFLX": ("Netflix", "stock"), "AVGO": ("Broadcom", "stock"), "PLTR": ("Palantir", "stock"),
    "COIN": ("Coinbase", "stock"), "V": ("Visa", "stock"), "KO": ("Coca-Cola", "stock"), "XOM": ("ExxonMobil", "stock"),
    "WMT": ("Walmart", "stock"), "BRK-B": ("Berkshire Hathaway", "stock"),
    "DOGE-USD": ("Dogecoin", "crypto"),
    "BTCUSDT": ("Bitcoin", "crypto"), "ETHUSDT": ("Ethereum", "crypto"), "SOLUSDT": ("Solana", "crypto"),
    "BNBUSDT": ("BNB", "crypto"), "XRPUSDT": ("XRP", "crypto"), "DOGEUSDT": ("Dogecoin", "crypto"),
    "BTC-USD": ("Bitcoin", "crypto"), "ETH-USD": ("Ethereum", "crypto"), "SOL-USD": ("Solana", "crypto"),
    "BNB-USD": ("BNB", "crypto"), "XRP-USD": ("XRP", "crypto"),
    "^VIX": ("VIX (félelemindex)", "macro"), "DX-Y.NYB": ("Dollárindex", "macro"), "^TNX": ("USA 10 éves hozam", "macro"),
}
# Ennyi százalékos napi mozgás alatt a mozgás nem érdekes, akármekkora a z-érték.
MIN_MOVE = {"forex": 0.5, "index": 1.5, "commodity": 2.0, "stock": 3.0, "crypto": 4.0, "macro": 5.0}
Z_ALERT = 2.5
Z_SEVERE = 4.0

FEEDS = [
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("MarketWatch", "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ("WSJ Markets", "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
    ("Fed", "https://www.federalreserve.gov/feeds/press_all.xml"),
    ("EKB", "https://www.ecb.europa.eu/rss/press.html"),
    ("Google News", "https://news.google.com/rss/search?q=" + quote("stock market OR forex OR bitcoin OR central bank")
     + "&hl=en-US&gl=US&ceid=US:en"),
]
# Ha a modell nem elérhető, ezek a szavak jelzik a súlyos hírt.
SEVERE_WORDS = re.compile(r"\b(crash|plunge|plummet|collapse|default|bankrupt|emergency|rate (cut|hike)|"
                          r"war|invasion|sanction|hack|exploit|halt|circuit breaker|bank run|recession)\b", re.I)


@dataclass(frozen=True)
class Move:
    symbol: str
    name: str
    cls: str
    price: float
    day_pct: float       # a legutóbbi két napi zárás közti változás
    week_pct: float
    z: float             # a napi mozgás a szokásos (21 napi) szóráshoz mérve
    bar_date: str


def parse_chart(data: dict) -> list[tuple[int, float]]:
    """[(időbélyeg, zárás)] a Yahoo-válaszból; a hiányzó (None) zárásokat kihagyja."""
    try:
        res = data["chart"]["result"][0]
        ts, closes = res["timestamp"], res["indicators"]["quote"][0]["close"]
    except (KeyError, IndexError, TypeError):
        raise ValueError("váratlan válaszformátum") from None
    return [(t, float(c)) for t, c in zip(ts, closes) if c is not None and c > 0]


def measure(symbol: str, series: list[tuple[int, float]]) -> Move | None:
    if len(series) < 25:
        return None
    name, cls = UNIVERSE.get(symbol, (symbol, "stock"))
    closes = [c for _, c in series]
    rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    window = rets[-22:-1]                                 # a mai (utolsó) mozgás nélkül: ahhoz mérjük
    mean = sum(window) / len(window)
    sd = math.sqrt(sum((r - mean) ** 2 for r in window) / (len(window) - 1))
    if sd <= 0:
        return None
    day = rets[-1]
    week = math.log(closes[-1] / closes[-6]) if len(closes) >= 6 else 0.0
    date = time.strftime("%Y-%m-%d", time.gmtime(series[-1][0]))
    return Move(symbol, name, cls, closes[-1], (math.exp(day) - 1) * 100, (math.exp(week) - 1) * 100,
                day / sd, date)


def is_notable(m: Move) -> bool:
    return abs(m.z) >= Z_ALERT and abs(m.day_pct) >= MIN_MOVE[m.cls]


def risk_off_reason(moves: dict[str, Move]) -> str | None:
    """Kemény, kódolt feltétel a védekezéshez. Szándékosan szűk: ritkán szólaljon meg, de akkor komolyan."""
    vix, spx, btc = moves.get("^VIX"), moves.get("^GSPC"), moves.get("BTC-USD")
    if vix and vix.day_pct >= 25 and vix.price >= 22:
        return f"a VIX egy nap alatt {vix.day_pct:+.0f}%-ot ugrott ({vix.price:.1f})"
    if spx and spx.day_pct <= -3:
        return f"az S&P 500 egy nap alatt {spx.day_pct:+.1f}%-ot esett"
    if btc and btc.day_pct <= -10:
        return f"a Bitcoin egy nap alatt {btc.day_pct:+.1f}%-ot esett"
    return None


def parse_rss(xml_text: str, source: str) -> list[dict]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    out = []
    for item in list(root.iter("item")) + list(root.iter("{http://www.w3.org/2005/Atom}entry")):
        title = (item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not link:
            a = item.find("{http://www.w3.org/2005/Atom}link")
            link = (a.get("href") if a is not None else "") or ""
        pub = item.findtext("pubDate") or item.findtext("{http://www.w3.org/2005/Atom}updated") or ""
        try:
            pub = parsedate_to_datetime(pub).isoformat() if pub else ""
        except (TypeError, ValueError):
            pass
        if title and link.startswith("http"):
            out.append({"title": re.sub(r"\s+", " ", title), "link": link, "source": source, "published": pub})
    return out


def heuristic(title: str) -> dict:
    sev = 4 if SEVERE_WORDS.search(title) else 2
    return {"sev": sev, "dir": "none", "assets": [], "hu": "", "why": "kulcsszó alapján (a modell nem elérhető)"}


class Radar:
    def __init__(self, store, llm=None, emit=None, client: httpx.Client | None = None, clock=time.time):
        self.store, self.llm, self.clock = store, llm, clock
        self.emit = emit or (lambda *a, **k: None)     # emit(kind, title, body, push_priority|None)
        self.client = client or httpx.Client(timeout=20, follow_redirects=True,
                                             headers={"User-Agent": "Mozilla/5.0 (milan-trader-radar)"})
        self.moves: dict[str, Move] = {}

    # --- árak ----------------------------------------------------------------
    def fetch_series(self, symbol: str) -> list[tuple[int, float]] | None:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol)}"
        for attempt in range(2):
            try:
                r = self.client.get(url, params={"range": "3mo", "interval": "1d"})
            except httpx.HTTPError:
                time.sleep(1)
                continue
            if r.status_code == 429:
                logger.warning("a Yahoo korlátoz (429), a következő körben folytatom")
                return None
            if r.status_code == 200:
                try:
                    return parse_chart(r.json())
                except ValueError:
                    return None
        return None

    def scan_markets(self) -> list[Move]:
        moves: dict[str, Move] = {}
        for sym in UNIVERSE:
            if sym.endswith("USDT"):
                continue
            series = self.fetch_series(sym)
            if series:
                m = measure(sym, series)
                if m:
                    moves[sym] = m
            time.sleep(0.25)
        if len(moves) < 10:
            raise RuntimeError(f"csak {len(moves)} instrumentum jött le a Yahoo-ról")
        self.moves = moves
        self.store.set("radar:moves", json.dumps({k: m.__dict__ for k, m in moves.items()}))
        self.store.set("radar:moves_at", int(self.clock()))
        notable = [m for m in moves.values() if is_notable(m)]
        for m in sorted(notable, key=lambda x: -abs(x.z)):
            self._alert_move(m)
        reason = risk_off_reason(moves)
        if reason:
            self._risk_off(reason)
        return notable

    def _alert_move(self, m: Move) -> None:
        sign = "up" if m.day_pct > 0 else "down"
        key = f"alert:{m.symbol}:{m.bar_date}:{sign}"
        severe = abs(m.z) >= Z_SEVERE
        level = "severe" if severe else "move"
        if self.store.get(key) in (level, "severe"):
            return
        self.store.set(key, level)
        arrow = "📈" if m.day_pct > 0 else "📉"
        title = f"{arrow} {m.name}: {m.day_pct:+.2f}% ({m.price:,.4g})"
        body = (f"A mai mozgás {abs(m.z):.1f}-szerese a szokásos napi ingadozásnak. "
                f"Heti változás: {m.week_pct:+.1f}%. Ez leírás, nem előrejelzés.")
        self.emit("move", title, body, 4 if severe else None)

    def _risk_off(self, reason: str) -> None:
        key = f"riskoff:{time.strftime('%Y-%m-%d', time.gmtime(self.clock()))}"
        if self.store.get(key):
            return
        self.store.set(key, reason)
        self.emit("riskoff", f"🛑 Védekező mód: {reason}", reason, 5)

    # --- hírek ---------------------------------------------------------------
    def scan_news(self) -> int:
        first_run = not self.store.get("radar:news_seeded")
        fresh: list[tuple[int, dict]] = []
        for source, url in FEEDS:
            try:
                r = self.client.get(url)
            except httpx.HTTPError as e:
                logger.warning("hírcsatorna nem érhető el (%s): %s", source, type(e).__name__)
                continue
            if r.status_code != 200:
                logger.warning("hírcsatorna hiba (%s): HTTP %s", source, r.status_code)
                continue
            for it in parse_rss(r.text, source)[:25]:
                nid = self.store.add_news(it["link"], source, it["title"], it["published"])
                if nid:
                    fresh.append((nid, it))
        self.store.set("radar:news_seeded", "1")
        if not fresh:
            return 0
        # Első induláskor a régi hírekből csak a legfrissebbeket elemezzük, riasztás nélkül.
        batch = fresh[:25] if not first_run else fresh[:12]
        analyses = self._analyze([it for _, it in batch])
        for (nid, it), a in zip(batch, analyses):
            self.store.set_news_analysis(nid, json.dumps(a, ensure_ascii=False))
            if a["sev"] >= 4 and not first_run:
                assets = ", ".join(a.get("assets") or []) or "általános"
                self.emit("news", f"🚨 {a.get('hu') or it['title']}",
                          f"{it['source']} • érintett: {assets} • irány: {a.get('dir')}\n{a.get('why','')}\n{it['link']}",
                          4 if a["sev"] == 4 else 5)
            elif a["sev"] >= 3 and not first_run:
                self.emit("news", f"📰 {a.get('hu') or it['title']}", f"{it['source']} • {a.get('why','')}\n{it['link']}", None)
        return len(fresh)

    def _analyze(self, items: list[dict]) -> list[dict]:
        fallback = [heuristic(it["title"]) for it in items]
        if self.llm is None or not items:
            return fallback
        listing = "\n".join(f"{i}. [{it['source']}] {it['title']}" for i, it in enumerate(items))
        prompt = (
            "Pénzügyi hírek címei következnek. Minden címhez add meg, mekkora hatása lehet a piacokra.\n"
            "Válaszolj KIZÁRÓLAG JSON tömbbel, elemenként: "
            '{"i": sorszám, "sev": 1-5, "dir": "up|down|mixed|none", "assets": ["BTC","USD","S&P500",...], '
            '"hu": "egy mondatos magyar összefoglaló", "why": "egy mondat: miért érinti a piacot"}.\n'
            "sev: 1 jelentéktelen, 2 szokásos, 3 említésre méltó, 4 súlyos (azonnal figyelni kell), "
            "5 rendkívüli (pánik, rendszerszintű kockázat, háború, csőd, kamatsokk). "
            "Légy szigorú: a 4-5 ritka. Csak a címből dolgozz, ne találj ki tényeket.\n\n" + listing)
        try:
            data = self.llm.ask(prompt)
            parsed = extract_json(data)
        except (LLMError, ValueError) as e:
            logger.warning("a hírelemzés a kulcsszavas módra állt át: %s", e)
            return fallback
        out = list(fallback)
        for row in parsed if isinstance(parsed, list) else []:
            try:
                i = int(row["i"])
                if 0 <= i < len(out):
                    out[i] = {"sev": max(1, min(5, int(row.get("sev", 2)))), "dir": str(row.get("dir", "none")),
                              "assets": [str(a) for a in (row.get("assets") or [])][:6],
                              "hu": str(row.get("hu", ""))[:220], "why": str(row.get("why", ""))[:260]}
            except (KeyError, TypeError, ValueError):
                continue
        return out

    # --- összefoglaló ----------------------------------------------------------
    def snapshot(self) -> dict:
        moves = self.moves or {k: Move(**v) for k, v in json.loads(self.store.get("radar:moves", "{}")).items()}
        top = sorted(moves.values(), key=lambda m: -abs(m.z))[:8]
        news = []
        for n in self.store.recent_news(12):
            a = json.loads(n["analysis"]) if n.get("analysis") else {}
            news.append({"cím": a.get("hu") or n["title"], "forrás": n["source"], "súly": a.get("sev"),
                         "érintett": a.get("assets")})
        vix = moves.get("^VIX")
        return {"frissítve_másodperce": int(time.time() - int(self.store.get("radar:moves_at", "0") or 0))
                if self.store.get("radar:moves_at") else None,
                "vix": round(vix.price, 1) if vix else None,
                "legszokatlanabb_mozgások": [{"név": m.name, "napi_%": round(m.day_pct, 2), "z": round(m.z, 1)} for m in top],
                "friss_hírek": news}


# Melyik hírben szereplő szó melyik instrumentumot érinti (a modell "assets" mezője és a cím alapján).
ALIASES: dict[str, list[str]] = {
    "AAPL": ["apple", "aapl", "iphone"], "MSFT": ["microsoft", "msft"], "NVDA": ["nvidia", "nvda"],
    "AMZN": ["amazon", "amzn"], "GOOGL": ["alphabet", "google", "googl"], "META": ["meta", "facebook"],
    "TSLA": ["tesla", "teslát", "teslat", "tsla", "musk"], "JPM": ["jpmorgan", "jpm"],
    "^GSPC": ["s&p", "s&p500", "sp500", "wall street", "us stocks", "részvény"], "^IXIC": ["nasdaq", "tech stocks"],
    "^GDAXI": ["dax", "germany", "german"], "CL=F": ["oil", "olaj", "olajat", "crude", "opec", "wti", "brent"],
    "GC=F": ["gold", "arany", "aranyat"], "SI=F": ["silver", "ezüst"],
    "BTC-USD": ["bitcoin", "btc", "crypto", "kripto"], "BTCUSDT": ["bitcoin", "btc", "crypto", "kripto"],
    "ETH-USD": ["ethereum", "eth", "crypto", "kripto"], "ETHUSDT": ["ethereum", "eth", "crypto", "kripto"],
    "SOL-USD": ["solana", "sol", "crypto", "kripto"], "SOLUSDT": ["solana", "sol", "crypto", "kripto"],
    "XRP-USD": ["xrp", "ripple", "crypto"], "XRPUSDT": ["xrp", "ripple", "crypto"],
    "BNB-USD": ["bnb", "binance"], "BNBUSDT": ["bnb", "binance"], "DOGE-USD": ["doge", "dogecoin"],
    "DOGEUSDT": ["doge", "dogecoin"], "AMD": ["amd"], "NFLX": ["netflix"], "AVGO": ["broadcom"],
    "PLTR": ["palantir"], "COIN": ["coinbase"], "XOM": ["exxon", "olaj részvény", "olajrészvény", "olaj reszveny", "olajcég", "olajceg"], "^DJI": ["dow jones", "dow"],
    "^FTSE": ["ftse", "london"], "^N225": ["nikkei", "japan"], "KO": ["coca-cola"], "WMT": ["walmart"],
}


def news_conflict(store, symbol: str, side: int, hours: float = 12) -> str | None:
    """Szöveges ok, ha az elmúlt órákban súlyos (4-5) hír jött az eszközről a fogadással ellentétes irányba."""
    words = ALIASES.get(symbol)
    if not words:
        return None
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - hours * 3600))
    for n in store.recent_news(150):
        if (n.get("seen_at") or "") < cutoff or not n.get("analysis"):
            continue
        try:
            a = json.loads(n["analysis"])
        except ValueError:
            continue
        if int(a.get("sev", 0)) < 4:
            continue
        hay = " ".join([n["title"], a.get("hu", ""), " ".join(a.get("assets") or [])]).lower()
        if not any(w in hay for w in words):
            continue
        d = a.get("dir")
        if (side == 1 and d == "down") or (side == -1 and d == "up"):
            return f"súlyos ellentétes hír ({n['source']}): {a.get('hu') or n['title']}"
    return None
