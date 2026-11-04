/**
 * Kamu Binance USDⓈ-M futures + Telegram + Gemini + RSS szerver a Bot2 tesztjeihez.
 * Csak azt tudja, amit a bot használ; az állapot memóriában van.
 */
export interface MCandle { openTime: number; closeTime: number; open: number; high: number; low: number; close: number }

export const H4 = 4 * 3_600_000;

/** n darab lezárt 4h gyertya; az utolsó épp most zárult. kind: long kitörés / short letörés / nincs jelzés. */
export function makeCandles(n: number, base: number, kind: "long" | "short" | "none", lastCloseAgoMs = 60_000): MCandle[] {
  const lastOpen = Date.now() - lastCloseAgoMs - H4 + 1;
  const out: MCandle[] = [];
  let px = base;
  const drift = kind === "short" ? -0.001 : 0.001;
  for (let i = 0; i < n; i++) {
    px = px * (1 + drift);
    let close = px;
    if (i === n - 1 && kind === "long") close = px * 1.03;
    if (i === n - 1 && kind === "short") close = px * 0.97;
    const openTime = lastOpen - (n - 1 - i) * H4;
    out.push({ openTime, closeTime: openTime + H4 - 1, open: px, high: Math.max(close, px) * 1.005, low: Math.min(close, px) * 0.995, close });
  }
  return out;
}

interface Order { symbol: string; clientOrderId: string; orderId: number; side: string; type: string; status: string; executedQty: string; avgPrice: string; reduceOnly: boolean }
interface Algo { symbol: string; clientAlgoId: string; algoId: number; side: string; quantity: string; triggerPrice: string; algoStatus: string; reduceOnly: boolean }
interface Trade { symbol: string; side: string; qty: string; price: string; realizedPnl: string; commission: string; commissionAsset: string; time: number }

export class MockWorld {
  prices = new Map<string, number>();
  klines = new Map<string, MCandle[]>();
  wallet = 5000;
  positions = new Map<string, { amt: number; entryPrice: number }>();
  orders = new Map<string, Order>();
  algos = new Map<string, Algo>();
  trades: Trade[] = [];
  income: { symbol: string; income: string; time: number }[] = [];
  telegram: string[] = [];
  geminiCalls = 0;
  geminiReply: (prompt: string) => string = () => "[]";
  feedXml = `<?xml version="1.0"?><rss><channel></channel></rss>`;
  failAlgo = 0;              // ennyi következő stop-leadás elutasítva
  orderUnknownOnce = false;  // a következő MARKET megbízás létrejön, de 503-at kap a kliens
  setupCalls: string[] = [];
  requests: string[] = [];
  private id = 1000;
  server: ReturnType<typeof Bun.serve>;

  constructor(symbols: string[]) {
    for (const s of symbols) this.prices.set(s, 100);
    this.server = Bun.serve({ port: 0, fetch: (req) => this.handle(req) });
  }
  get url() { return `http://127.0.0.1:${this.server.port}`; }
  stop() { this.server.stop(true); }

  setCandles(symbol: string, c: MCandle[]) {
    this.klines.set(symbol, c);
    this.prices.set(symbol, c[c.length - 1].close);
  }

  private err(status: number, code: number, msg: string) { return Response.json({ code, msg }, { status }); }

  private fill(symbol: string, side: string, qty: number, price: number, reduceOnly: boolean): number {
    const pos = this.positions.get(symbol) ?? { amt: 0, entryPrice: 0 };
    const signed = side === "BUY" ? qty : -qty;
    if (reduceOnly) {
      if (pos.amt === 0 || Math.sign(signed) === Math.sign(pos.amt)) return 0;
      qty = Math.min(qty, Math.abs(pos.amt));
    }
    let realized = 0;
    if (pos.amt !== 0 && Math.sign(signed) !== Math.sign(pos.amt)) {
      const closeQty = Math.min(qty, Math.abs(pos.amt));
      realized = (price - pos.entryPrice) * closeQty * Math.sign(pos.amt);
      pos.amt += Math.sign(signed) * closeQty;
      this.wallet += realized;
    } else {
      pos.entryPrice = pos.amt === 0 ? price : (pos.entryPrice * Math.abs(pos.amt) + price * qty) / (Math.abs(pos.amt) + qty);
      pos.amt += signed;
    }
    pos.amt = Math.round(pos.amt * 1e8) / 1e8;
    const fee = qty * price * 0.0004;
    this.wallet -= fee;
    if (pos.amt === 0) this.positions.delete(symbol); else this.positions.set(symbol, pos);
    this.trades.push({ symbol, side, qty: String(qty), price: String(price), realizedPnl: String(realized), commission: String(fee), commissionAsset: "USDT", time: Date.now() });
    return qty;
  }

  /** A tőzsdei stop "kiüt": az ár a stop szintjére megy, a stop teljesül. */
  triggerStop(symbol: string) {
    const a = [...this.algos.values()].find((x) => x.symbol === symbol && x.algoStatus === "NEW");
    if (!a) throw new Error("nincs élő stop");
    a.algoStatus = "FINISHED";
    const p = Number(a.triggerPrice);
    this.prices.set(symbol, p);
    this.fill(symbol, a.side, Number(a.quantity), p, true);
    for (const x of this.algos.values()) if (x.symbol === symbol && x.algoStatus === "NEW") x.algoStatus = "CANCELED";
  }

  unrealized(): number {
    let u = 0;
    for (const [s, p] of this.positions) u += ((this.prices.get(s) ?? p.entryPrice) - p.entryPrice) * p.amt;
    return u;
  }

  async handle(req: Request): Promise<Response> {
    const u = new URL(req.url);
    const q = u.searchParams;
    const path = u.pathname;
    this.requests.push(`${req.method} ${path}`);

    if (path.includes("/sendMessage")) {
      const b: any = await req.json();
      this.telegram.push(b.text);
      return Response.json({ ok: true, result: {} });
    }
    if (path.includes(":generateContent")) {
      this.geminiCalls++;
      const b: any = await req.json();
      const text = this.geminiReply(b.contents[0].parts[0].text);
      return Response.json({ candidates: [{ content: { parts: [{ text }] } }] });
    }
    if (path === "/feed.xml") return new Response(this.feedXml, { headers: { "content-type": "application/rss+xml" } });

    const sym = q.get("symbol") ?? "";
    switch (`${req.method} ${path}`) {
      case "GET /fapi/v1/time":
        return Response.json({ serverTime: Date.now() });
      case "GET /fapi/v1/exchangeInfo":
        return Response.json({
          symbols: [...this.prices.keys()].map((s) => ({
            symbol: s, status: "TRADING", contractType: s.startsWith("TSLA") ? "TRADIFI_PERPETUAL" : "PERPETUAL",
            filters: [
              { filterType: "PRICE_FILTER", tickSize: "0.01" },
              { filterType: "LOT_SIZE", stepSize: "0.001", minQty: "0.001", maxQty: "1000" },
              { filterType: "MARKET_LOT_SIZE", stepSize: "0.001", minQty: "0.001", maxQty: "1000" },
              { filterType: "MIN_NOTIONAL", notional: "5" },
            ],
          })),
        });
      case "GET /fapi/v1/klines": {
        const c = this.klines.get(sym) ?? [];
        const rows = c.map((k) => [k.openTime, String(k.open), String(k.high), String(k.low), String(k.close), "0", k.closeTime]);
        const lastC = c[c.length - 1];
        if (lastC) rows.push([lastC.closeTime + 1, String(lastC.close), String(lastC.close), String(lastC.close), String(lastC.close), "0", lastC.closeTime + 4 * 3_600_000]); // nyitott gyertya
        return Response.json(rows);
      }
      case "GET /fapi/v1/ticker/price":
        return Response.json([...this.prices].map(([symbol, p]) => ({ symbol, price: String(p) })));
      case "GET /fapi/v2/account": {
        const margin = [...this.positions].reduce((s, [k, p]) => s + Math.abs(p.amt) * p.entryPrice / 2, 0);
        const eq = this.wallet + this.unrealized();
        return Response.json({ totalWalletBalance: String(this.wallet), totalMarginBalance: String(eq), availableBalance: String(eq - margin) });
      }
      case "GET /fapi/v2/positionRisk":
        return Response.json([...this.positions].map(([symbol, p]) => ({ symbol, positionAmt: String(p.amt), entryPrice: String(p.entryPrice), markPrice: String(this.prices.get(symbol)) })));
      case "POST /fapi/v1/marginType":
      case "POST /fapi/v1/leverage":
        this.setupCalls.push(`${path}:${sym}`);
        return Response.json({ code: 200, msg: "success" });
      case "POST /fapi/v1/order": {
        const cid = q.get("newClientOrderId")!;
        if (this.orders.has(cid)) return this.err(400, -4116, "ClientOrderId is duplicated.");
        const price = this.prices.get(sym)!;
        const filled = this.fill(sym, q.get("side")!, Number(q.get("quantity")), price, q.get("reduceOnly") === "true");
        const o: Order = { symbol: sym, clientOrderId: cid, orderId: this.id++, side: q.get("side")!, type: q.get("type")!, status: filled > 0 ? "FILLED" : "EXPIRED", executedQty: String(filled), avgPrice: String(filled > 0 ? price : 0), reduceOnly: q.get("reduceOnly") === "true" };
        this.orders.set(cid, o);
        if (this.orderUnknownOnce) { this.orderUnknownOnce = false; return new Response("bad gateway", { status: 503 }); }
        return Response.json(o);
      }
      case "GET /fapi/v1/order": {
        const o = this.orders.get(q.get("origClientOrderId")!);
        return o ? Response.json(o) : this.err(400, -2013, "Order does not exist.");
      }
      case "POST /fapi/v1/algoOrder": {
        if (this.failAlgo > 0) { this.failAlgo--; return this.err(400, -2021, "Order would immediately trigger."); }
        const cid = q.get("clientAlgoId")!;
        const a: Algo = { symbol: sym, clientAlgoId: cid, algoId: this.id++, side: q.get("side")!, quantity: q.get("quantity")!, triggerPrice: q.get("triggerPrice")!, algoStatus: "NEW", reduceOnly: q.get("reduceOnly") === "true" };
        this.algos.set(cid, a);
        return Response.json(a);
      }
      case "GET /fapi/v1/algoOrder": {
        const a = this.algos.get(q.get("clientAlgoId")!);
        return a ? Response.json(a) : this.err(400, -2013, "Order does not exist.");
      }
      case "DELETE /fapi/v1/algoOrder": {
        const a = this.algos.get(q.get("clientAlgoId")!);
        if (!a || a.algoStatus !== "NEW") return this.err(400, -2011, "Unknown order sent.");
        a.algoStatus = "CANCELED";
        return Response.json({ clientAlgoId: a.clientAlgoId, code: "200", msg: "success" });
      }
      case "GET /fapi/v1/openAlgoOrders":
        return Response.json([...this.algos.values()].filter((a) => a.symbol === sym && a.algoStatus === "NEW"));
      case "GET /fapi/v1/userTrades": {
        const from = Number(q.get("startTime")), to = Number(q.get("endTime"));
        return Response.json(this.trades.filter((t) => t.symbol === sym && t.time >= from && t.time <= to));
      }
      case "GET /fapi/v1/income":
        return Response.json(this.income.filter((x) => x.symbol === sym));
    }
    return this.err(404, -5000, `mock: ismeretlen ${req.method} ${path}`);
  }
}

export function rss(items: { title: string; link: string; agoMin: number }[]): string {
  return `<?xml version="1.0"?><rss><channel>${items
    .map((i) => `<item><title><![CDATA[${i.title}]]></title><link>${i.link}</link><pubDate>${new Date(Date.now() - i.agoMin * 60_000).toUTCString()}</pubDate></item>`)
    .join("")}</channel></rss>`;
}
