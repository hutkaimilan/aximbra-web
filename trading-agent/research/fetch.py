"""Világpiaci napi árfolyamok letöltése a Yahoo Finance nyilvános végpontjáról (kulcs nélkül)."""
import json, sys, time, urllib.parse
import httpx

UNIVERSE = {
    "forex": ["EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X", "USDCAD=X", "USDCHF=X", "NZDUSD=X", "EURJPY=X", "EURGBP=X", "USDHUF=X"],
    "index": ["^GSPC", "^IXIC", "^DJI", "^RUT", "^GDAXI", "^FTSE", "^N225", "^HSI", "^STOXX50E"],
    "commodity": ["GC=F", "SI=F", "CL=F", "NG=F", "HG=F"],
    "stock": ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM", "XOM", "WMT"],
    "crypto": ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD"],
    "macro": ["^VIX", "DX-Y.NYB", "^TNX"],
}
H = {"User-Agent": "Mozilla/5.0"}

def fetch(sym, rng="15y", interval="1d"):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}"
    for a in range(3):
        try:
            r = httpx.get(url, params={"range": rng, "interval": interval}, headers=H, timeout=30)
            if r.status_code == 200:
                res = r.json()["chart"]["result"][0]
                q = res["indicators"]["quote"][0]
                rows = [(t, o, h, l, c, v) for t, o, h, l, c, v in zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"], q["volume"]) if c is not None and o is not None]
                return rows
            if r.status_code == 429: time.sleep(5 * (a + 1))
        except Exception as e:
            time.sleep(2)
    return None

if __name__ == "__main__":
    out = {}
    for cls, syms in UNIVERSE.items():
        for s in syms:
            rows = fetch(s)
            print(f"{cls:10s} {s:10s} {'-' if rows is None else len(rows)}")
            if rows: out[s] = {"cls": cls, "rows": rows}
            time.sleep(0.4)
    json.dump(out, open(sys.argv[1], "w"))
