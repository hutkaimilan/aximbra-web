import { afterAll, beforeAll, beforeEach, describe, expect, test } from "bun:test";
import { SQL } from "bun";
import { type Config, kvGet, kvSet, keywordImpacts, parseFeed, runOnce, validateImpacts } from "../bot2";
import { H4, makeCandles, MockWorld, rss } from "./mock";

const DB_URL = process.env.TEST_DATABASE_URL ?? "postgres://postgres@127.0.0.1:55432/postgres";
const SYMS = ["BTCUSDT", "ETHUSDT", "TSLAUSDT"];
let db: SQL;
let w: MockWorld;

function cfg(over: Partial<Config> = {}): Config {
  return {
    databaseUrl: DB_URL, fapiBase: w.url, apiKey: "k", apiSecret: "s", tgToken: "t", tgChatId: "123456", tgApiBase: w.url,
    geminiKey: "g", geminiBase: w.url, geminiModel: "m", geminiDailyCalls: 100,
    symbols: SYMS, riskPerTrade: 0.01, maxPositions: 4, maxLeverage: 2, dailyLossLimit: 0.03, killSwitchDd: 0.2,
    enableShort: true, lookback: 20, emaN: 200, atrN: 14, stopAtr: 2, trailAtr: 3, maxEntryDelayMs: 30 * 60_000,
    minWallet: 50, newsVetoStrength: 2, newsWindowMs: 12 * 3_600_000, feeds: [{ name: "Teszt", url: `${w.url}/feed.xml` }],
    ...over,
  };
}

const tgAll = () => w.telegram.join("\n---\n");
const marketOrders = () => w.requests.filter((r) => r === "POST /fapi/v1/order").length;
const liveStops = (s: string) => [...w.algos.values()].filter((a) => a.symbol === s && a.algoStatus === "NEW");

beforeAll(async () => {
  db = new SQL(DB_URL);
});
afterAll(async () => {
  await db.close();
});
beforeEach(async () => {
  await db`DROP TABLE IF EXISTS kv, b2_lease, b2_positions, b2_trades, b2_news, b2_decisions`;
  w?.stop();
  w = new MockWorld(SYMS);
  for (const s of SYMS) w.setCandles(s, makeCandles(260, 100, "none"));
});

describe("Bot2", () => {
  test("pénz nélkül nem kereskedik, de szól és figyeli a híreket", async () => {
    w.wallet = 0;
    w.setCandles("BTCUSDT", makeCandles(260, 100, "long"));
    w.feedXml = rss([{ title: "Fed holds rates steady as expected", link: "https://x/1", agoMin: 5 }]);
    await runOnce(cfg(), db);
    expect(marketOrders()).toBe(0);
    expect(tgAll()).toContain("nincs pénz");
    expect((await db`SELECT COUNT(*)::int AS n FROM b2_news`)[0].n).toBe(1);
  });

  test("long kitörés: piaci vétel + tőzsdei stop 2×ATR-rel, 1% kockázat", async () => {
    w.setCandles("BTCUSDT", makeCandles(260, 100, "long"));
    await runOnce(cfg(), db);
    const pos = w.positions.get("BTCUSDT")!;
    expect(pos.amt).toBeGreaterThan(0);
    const stops = liveStops("BTCUSDT");
    expect(stops.length).toBe(1);
    expect(stops[0].side).toBe("SELL");
    expect(stops[0].reduceOnly).toBe(true);
    const [row] = await db`SELECT * FROM b2_positions WHERE symbol = 'BTCUSDT'`;
    expect(row.status).toBe("open");
    const risk = (row.entry_price - Number(stops[0].triggerPrice)) * pos.amt;
    expect(risk).toBeLessThanOrEqual(50.5);
    expect(risk).toBeGreaterThan(40);
    expect(w.setupCalls).toContain("/fapi/v1/leverage:BTCUSDT");
    expect(tgAll()).toContain("VÉTEL");
    expect(tgAll()).toContain("Miért?");

    // ugyanarra a gyertyára újrafuttatva nincs új megbízás
    const before = marketOrders();
    await runOnce(cfg(), db);
    expect(marketOrders()).toBe(before);
    expect(liveStops("BTCUSDT").length).toBe(1);
  });

  test("kiütött stop: eredmény naplózva, értesítés", async () => {
    w.setCandles("BTCUSDT", makeCandles(260, 100, "long"));
    await runOnce(cfg(), db);
    w.triggerStop("BTCUSDT");
    await runOnce(cfg(), db);
    const tr = await db`SELECT * FROM b2_trades`;
    expect(tr.length).toBe(1);
    expect(Number(tr[0].pnl)).toBeLessThan(-40);
    expect(Number(tr[0].pnl)).toBeGreaterThan(-60);
    expect(Number(tr[0].r_multiple)).toBeLessThan(-0.9);
    expect((await db`SELECT COUNT(*)::int AS n FROM b2_positions`)[0].n).toBe(0);
    expect(tgAll()).toContain("ZÁRÁS");
  });

  test("eltűnt stop: újra leadja", async () => {
    w.setCandles("BTCUSDT", makeCandles(260, 100, "long"));
    await runOnce(cfg(), db);
    for (const a of w.algos.values()) a.algoStatus = "CANCELED";
    await runOnce(cfg(), db);
    const stops = liveStops("BTCUSDT");
    expect(stops.length).toBe(1);
    expect(stops[0].clientAlgoId).toEndWith("-s2");
    expect(w.positions.get("BTCUSDT")!.amt).toBeGreaterThan(0);
    expect(tgAll()).toContain("eltűnt");
  });

  test("ha a stop nem adható le: azonnali zárás", async () => {
    w.setCandles("BTCUSDT", makeCandles(260, 100, "long"));
    w.failAlgo = 1;
    await runOnce(cfg(), db);
    expect(w.positions.has("BTCUSDT")).toBe(false);
    expect((await db`SELECT COUNT(*)::int AS n FROM b2_trades WHERE reason = 'stop_hiba'`)[0].n).toBe(1);
    expect(tgAll()).toContain("nem tudtam leadni");
  });

  test("short letörés: eladás + stop az ár felett", async () => {
    w.setCandles("ETHUSDT", makeCandles(260, 100, "short"));
    await runOnce(cfg(), db);
    expect(w.positions.get("ETHUSDT")!.amt).toBeLessThan(0);
    const s = liveStops("ETHUSDT")[0];
    expect(s.side).toBe("BUY");
    expect(Number(s.triggerPrice)).toBeGreaterThan(w.prices.get("ETHUSDT")!);
    expect(tgAll()).toContain("SHORT");
  });

  test("short kikapcsolva: nem shortol", async () => {
    w.setCandles("ETHUSDT", makeCandles(260, 100, "short"));
    await runOnce(cfg({ enableShort: false }), db);
    expect(marketOrders()).toBe(0);
  });

  test("hírvétó (Gemini): erős ellentétes hír → nincs belépés + riasztás", async () => {
    w.setCandles("BTCUSDT", makeCandles(260, 100, "long"));
    w.feedXml = rss([{ title: "Bitcoin crashes after major exchange hack", link: "https://x/2", agoMin: 10 }]);
    w.geminiReply = () => JSON.stringify([{ i: 0, impacts: [{ a: "BTC", d: -1, s: 3 }], hu: "A Bitcoin zuhan egy tőzsdei hack után." }]);
    await runOnce(cfg(), db);
    expect(marketOrders()).toBe(0);
    expect(w.geminiCalls).toBe(1);
    expect(tgAll()).toContain("kihagyott belépés");
    expect(tgAll()).toContain("Fontos hír");
  });

  test("hírvétó kulcsszavas tartalékkal (Gemini kulcs nélkül)", async () => {
    w.setCandles("BTCUSDT", makeCandles(260, 100, "long"));
    w.feedXml = rss([{ title: "Bitcoin price crash deepens as miners sell", link: "https://x/3", agoMin: 10 }]);
    await runOnce(cfg({ geminiKey: "" }), db);
    expect(w.geminiCalls).toBe(0);
    expect(marketOrders()).toBe(0);
    expect(tgAll()).toContain("kihagyott belépés");
  });

  test("egyező hír nem nyit jelzés nélkül", async () => {
    w.feedXml = rss([{ title: "Tesla stock soars to record high", link: "https://x/4", agoMin: 10 }]);
    w.geminiReply = () => JSON.stringify([{ i: 0, impacts: [{ a: "TSLA", d: 1, s: 3 }], hu: "A Tesla rekordon." }]);
    await runOnce(cfg(), db);
    expect(marketOrders()).toBe(0);
  });

  test("kill switch: 20%-os visszaesésnél mindent zár és leáll", async () => {
    w.setCandles("BTCUSDT", makeCandles(260, 100, "long"));
    await runOnce(cfg(), db);
    expect(w.positions.has("BTCUSDT")).toBe(true);
    await kvSet(db, "b2:peak", 10_000);
    await runOnce(cfg(), db);
    expect(w.positions.size).toBe(0);
    expect(await kvGet(db, "b2:halted", false)).toBe(true);
    expect(tgAll()).toContain("KILL SWITCH");
  });

  test("ismeretlen kimenetelű belépés: nincs dupla megbízás", async () => {
    w.setCandles("BTCUSDT", makeCandles(260, 100, "long"));
    w.orderUnknownOnce = true;
    await runOnce(cfg(), db);
    expect(w.orders.size).toBe(1);
    expect(w.positions.get("BTCUSDT")!.amt).toBeGreaterThan(0);
    expect(liveStops("BTCUSDT").length).toBe(1);
    expect((await db`SELECT status FROM b2_positions`)[0].status).toBe("open");
  });

  test("követő stop: új lezárt gyertyán feljebb húzza, a régit törli", async () => {
    const c = makeCandles(260, 100, "long");
    w.setCandles("BTCUSDT", c);
    await runOnce(cfg(), db);
    const s1 = liveStops("BTCUSDT")[0];
    const last = c[c.length - 1];
    const up = last.close * 1.1;
    c.push({ openTime: last.openTime + 1000, closeTime: Date.now() - 30_000, open: last.close, high: up * 1.002, low: last.close, close: up });
    w.setCandles("BTCUSDT", c);
    await runOnce(cfg(), db);
    const s = liveStops("BTCUSDT");
    expect(s.length).toBe(1);
    expect(s[0].clientAlgoId).not.toBe(s1.clientAlgoId);
    expect(Number(s[0].triggerPrice)).toBeGreaterThan(Number(s1.triggerPrice));
    expect(w.algos.get(s1.clientAlgoId)!.algoStatus).toBe("CANCELED");
  });

  test("tőkeáttétel-plafon: az összes névérték legfeljebb 2× tőke", async () => {
    w.setCandles("BTCUSDT", makeCandles(260, 100, "long"));
    w.setCandles("ETHUSDT", makeCandles(260, 100, "long"));
    await runOnce(cfg({ riskPerTrade: 0.5 }), db);
    let notional = 0;
    for (const [s, p] of w.positions) notional += Math.abs(p.amt) * w.prices.get(s)!;
    expect(notional).toBeGreaterThan(0);
    expect(notional).toBeLessThanOrEqual(2 * 5000 + 1);
  });

  test("idegen pozíció: nem nyúl hozzá, nem nyit mellé, szól", async () => {
    w.setCandles("ETHUSDT", makeCandles(260, 100, "long"));
    w.positions.set("ETHUSDT", { amt: 1, entryPrice: 100 });
    await runOnce(cfg(), db);
    expect(marketOrders()).toBe(0);
    expect(w.positions.get("ETHUSDT")!.amt).toBe(1);
    expect(tgAll()).toContain("nem én nyitottam");
  });

  test("késve futó cron: régi jelzésre nem lép be", async () => {
    w.setCandles("BTCUSDT", makeCandles(260, 100, "long", 45 * 60_000));
    await runOnce(cfg(), db);
    expect(marketOrders()).toBe(0);
  });

  test("/zaras2 kérés: mindent zár és szünetel", async () => {
    w.setCandles("BTCUSDT", makeCandles(260, 100, "long"));
    await runOnce(cfg(), db);
    await kvSet(db, "b2:close_all", true);
    await runOnce(cfg(), db);
    expect(w.positions.size).toBe(0);
    expect(await kvGet(db, "b2:paused", false)).toBe(true);
    expect(liveStops("BTCUSDT").length).toBe(0);
  });

  test("párhuzamos futás: a második kimarad (lease)", async () => {
    w.setCandles("BTCUSDT", makeCandles(260, 100, "long"));
    await Promise.all([runOnce(cfg(), db), runOnce(cfg(), db)]);
    expect(w.orders.size).toBe(1);
  });
});

describe("segédfüggvények", () => {
  test("RSS feldolgozás", () => {
    const items = parseFeed(rss([{ title: "Gold &amp; silver jump", link: "https://x/9", agoMin: 1 }]), "T");
    expect(items.length).toBe(1);
    expect(items[0].title).toBe("Gold & silver jump");
  });
  test("Gemini kimenet szigorú ellenőrzése", () => {
    const v = validateImpacts([{ a: "BTC", d: -1, s: 3 }, { a: "DOGE", d: 1, s: 2 }, { a: "ETH", d: 5, s: 2 }, { a: "TSLAUSDT", d: 1, s: 9 }], SYMS);
    expect(v).toEqual([{ a: "BTCUSDT", d: -1, s: 3 }]);
  });
  test("kulcsszavas tartalék", () => {
    expect(keywordImpacts("Nvidia shares surge on earnings", ["NVDAUSDT", "BTCUSDT"])).toEqual([{ a: "NVDAUSDT", d: 1, s: 2 }]);
    expect(keywordImpacts("Gold steady ahead of Fed", ["XAUUSDT"])).toEqual([]);
    expect(keywordImpacts("Meta platforms hack exposes data", ["METAUSDT"])).toEqual([{ a: "METAUSDT", d: -1, s: 2 }]);
  });
});

void H4;
