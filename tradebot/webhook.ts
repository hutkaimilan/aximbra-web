/**
 * Trader bot – Telegram webhook (Railway Function, Bun HTTP szerver).
 *
 * Azonnal válaszol a magyar parancsokra. Kereskedni NEM kereskedik:
 *   - olvassa a worker pillanatképét (/allapot), a trade-naplót (/trades)
 *   - jelzőket állít az adatbázisban (szünet, folytatás, mindent zár),
 *     amelyeket a worker a következő futásán (legfeljebb 5 perc) hajt végre
 *   - /elemez: azonnali piacelemzés a Binance NYILVÁNOS adataiból (kulcs nem kell)
 *   - /figyel, /torol, /lista, /toke: a kézi trade-figyelés beállításai
 *   - Bot2 (több piacos futures bot): /allapot2, /trades2, /stop2, /folytat2, /zaras2
 *
 * Biztonság:
 *   - csak a Telegram titkos fejléccel (X-Telegram-Bot-Api-Secret-Token) érkező kérést fogad el
 *   - csak a beállított chat ID parancsait hajtja végre
 *   - minden update csak egyszer kerül feldolgozásra (Telegram újraküldés esetén is)
 */
import { SQL } from "bun";
import { timingSafeEqual } from "node:crypto";

const DATABASE_URL = (process.env.DATABASE_URL ?? "").trim();
const SECRET = (process.env.TG_WEBHOOK_SECRET ?? "").trim();
const CHAT_ID = (process.env.TELEGRAM_CHAT_ID ?? "").trim();
const BINANCE = (process.env.BINANCE_BASE_URL ?? "https://demo-api.binance.com").trim().replace(/\/$/, "");
const MANUAL_DEFAULT = (process.env.MANUAL_SYMBOLS ?? "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT").trim();
const CAPITAL_DEFAULT = Number(process.env.MANUAL_CAPITAL_USDT ?? 10_000) || 10_000;
const PORT = Number(process.env.PORT ?? 3000);

const SYMBOL_RE = /^[A-Z0-9]{2,20}USDT$/;
const MAX_WATCH = 15;
const RISK = 0.01, STOP_ATR = 2, LOOKBACK = 20, EMA_N = 200, ATR_N = 14;

if (!DATABASE_URL || !SECRET || !CHAT_ID) {
  console.error("Hiányzó környezeti változó (DATABASE_URL / TG_WEBHOOK_SECRET / TELEGRAM_CHAT_ID)");
}

const db = DATABASE_URL ? new SQL(DATABASE_URL) : null;
let migrated = false;

async function migrate(d: SQL): Promise<void> {
  if (migrated) return;
  await d`CREATE TABLE IF NOT EXISTS kv (key text PRIMARY KEY, value jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())`;
  await d`CREATE TABLE IF NOT EXISTS tg_updates (update_id bigint PRIMARY KEY, received_at timestamptz NOT NULL DEFAULT now())`;
  await d`CREATE TABLE IF NOT EXISTS trades (
    id serial PRIMARY KEY, symbol text NOT NULL, entry_time timestamptz NOT NULL, exit_time timestamptz NOT NULL,
    entry_price double precision NOT NULL, exit_price double precision NOT NULL, qty double precision NOT NULL,
    pnl double precision NOT NULL, r_multiple double precision NOT NULL, reason text NOT NULL, exit_client_id text UNIQUE)`;
  migrated = true;
}

async function kvGet<T>(d: SQL, key: string, fallback: T): Promise<T> {
  const rows = await d`SELECT value FROM kv WHERE key = ${key}`;
  return rows.length ? (rows[0].value as T) : fallback;
}
async function kvSet(d: SQL, key: string, value: unknown): Promise<void> {
  await d`INSERT INTO kv (key, value, updated_at) VALUES (${key}, ${JSON.stringify(value)}::text::jsonb, now())
          ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()`;
}

const fmt = (n: number, d = 2) => n.toLocaleString("hu-HU", { minimumFractionDigits: d, maximumFractionDigits: d });
const sign = (n: number) => (n >= 0 ? "+" : "−") + fmt(Math.abs(n));
const pct = (a: number, b: number) => ((a - b) / b) * 100;
const hhmm = (ms: number) =>
  new Intl.DateTimeFormat("hu-HU", { timeZone: "Europe/Budapest", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(ms));
/** Ár formázása a nagyságrendjéhez igazított tizedesekkel (BTC: 2, kis árú coin: több). */
const fp = (n: number) => fmt(n, n >= 100 ? 2 : n >= 1 ? 4 : 6);
const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

// ---------------------------------------------------------------------------
// Indikátorok – azonosak a workerrel (a teszt ellenőrzi az egyezést)
// ---------------------------------------------------------------------------
export interface Candle { openTime: number; closeTime: number; open: number; high: number; low: number; close: number }

function ema(values: number[], n: number): number[] {
  const a = 2 / (n + 1);
  const out: number[] = new Array(values.length).fill(NaN);
  let y = NaN;
  for (let i = 0; i < values.length; i++) {
    y = i === 0 ? values[0] : a * values[i] + (1 - a) * y;
    if (i >= n - 1) out[i] = y;
  }
  return out;
}
function atr(c: Candle[], n: number): number[] {
  const tr = c.map((k, i) =>
    i === 0 ? k.high - k.low : Math.max(k.high - k.low, Math.abs(k.high - c[i - 1].close), Math.abs(k.low - c[i - 1].close)),
  );
  const a = 1 / n;
  const out: number[] = new Array(c.length).fill(NaN);
  let y = NaN;
  for (let i = 0; i < tr.length; i++) {
    y = i === 0 ? tr[0] : a * tr[i] + (1 - a) * y;
    if (i >= n - 1) out[i] = y;
  }
  return out;
}
export function evaluate(c: Candle[]) {
  if (c.length < EMA_N + LOOKBACK + 5) throw new Error(`Kevés gyertya: ${c.length}`);
  const i = c.length - 1;
  const e = ema(c.map((k) => k.close), EMA_N)[i];
  const a = atr(c, ATR_N)[i];
  let priorHigh = -Infinity;
  for (let j = i - LOOKBACK; j < i; j++) priorHigh = Math.max(priorHigh, c[j].high);
  const close = c[i].close;
  const valid = Number.isFinite(e) && Number.isFinite(a) && a > 0;
  return { entry: valid && close > priorHigh && close > e, close, priorHigh, emaFilter: e, atr: a };
}

// ---------------------------------------------------------------------------
// Binance nyilvános adatok
// ---------------------------------------------------------------------------
class MarketError extends Error {
  constructor(public code: number | undefined, msg: string) { super(msg); }
}
async function publicGet(path: string): Promise<any> {
  let res: Response;
  try {
    res = await fetch(`${BINANCE}${path}`, { signal: AbortSignal.timeout(8_000) });
  } catch (e) {
    throw new MarketError(undefined, `Binance nem elérhető: ${(e as Error).message}`);
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) throw new MarketError(body?.code, body?.msg ?? `HTTP ${res.status}`);
  return body;
}

export function normSymbol(arg: string | undefined): string | null {
  if (!arg) return null;
  let s = arg.trim().toUpperCase().replace(/[^A-Z0-9]/g, "");
  if (!s) return null;
  if (!s.endsWith("USDT")) s += "USDT";
  return SYMBOL_RE.test(s) ? s : null;
}

async function symbolExists(symbol: string): Promise<boolean> {
  try {
    const info = await publicGet(`/api/v3/exchangeInfo?symbol=${symbol}`);
    return info?.symbols?.[0]?.status === "TRADING";
  } catch (e) {
    if (e instanceof MarketError && (e.code === -1121 || e.code === -1100)) return false;
    throw e;
  }
}

async function analyze(d: SQL, arg: string | undefined): Promise<string> {
  const symbol = normSymbol(arg);
  if (!symbol) return "Add meg a piacot, például: <code>/elemez BTC</code>";
  let rows: any[], tick: any;
  try {
    [rows, tick] = await Promise.all([
      publicGet(`/api/v3/klines?symbol=${symbol}&interval=4h&limit=1000`),
      publicGet(`/api/v3/ticker/price?symbol=${symbol}`),
    ]);
  } catch (e) {
    if (e instanceof MarketError && (e.code === -1121 || e.code === -1100)) return `Nincs ilyen piac a Binance-en: ${symbol}`;
    console.error("Elemzés hiba:", e);
    return "⚠️ Most nem érem el a Binance-t, próbáld újra egy perc múlva.";
  }
  const now = Date.now();
  const candles: Candle[] = rows
    .map((r) => ({ openTime: r[0], closeTime: r[6], open: +r[1], high: +r[2], low: +r[3], close: +r[4] }))
    .filter((k) => k.closeTime < now && [k.open, k.high, k.low, k.close].every((x) => Number.isFinite(x) && x > 0));
  if (candles.length < EMA_N + LOOKBACK + 5) return `A(z) ${symbol} piacnak túl rövid a története az elemzéshez.`;

  const price = Number(tick.price);
  const sig = evaluate(candles);
  const last20 = candles.slice(-LOOKBACK);
  const high20 = Math.max(...last20.map((k) => k.high));
  const low20 = Math.min(...last20.map((k) => k.low));
  const up = sig.close > sig.emaFilter;
  const capital = await kvGet<number | null>(d, "manual_capital", null) ?? CAPITAL_DEFAULT;

  const stopDist = STOP_ATR * sig.atr;
  const stop = price - stopDist;
  let qty = (capital * RISK) / stopDist;
  let capped = false;
  if (qty * price > capital) { qty = capital / price; capped = true; }
  const loss = qty * stopDist;

  let strategy: string;
  if (sig.entry) strategy = "🟢 A legutóbbi lezárt 4 órás gyertyán <b>VAN belépési jelzés</b> (kitörés emelkedő trendben).";
  else if (!up) strategy = "🔴 Nincs jelzés: az ár a 200-as átlag alatt van (csökkenő trend), ilyenkor a stratégia nem vesz.";
  else strategy = `🟡 Nincs jelzés. Kitöréshez egy 4 órás gyertyának <b>${fp(high20)}</b> fölött kell zárnia (+${fmt(pct(high20, price), 1)}% a mostani ártól).`;

  return [
    `📈 <b>${symbol} elemzés</b> (4 órás gyertyák)`,
    `Ár: <b>${fp(price)}</b> USDT`,
    `Trend: ${up ? "emelkedő ↗" : "csökkenő ↘"} (az ár ${fmt(Math.abs(pct(sig.close, sig.emaFilter)), 1)}%-kal a 200-as átlag ${up ? "felett" : "alatt"})`,
    `20 gyertyás csúcs: ${fp(high20)} (${sign(pct(high20, price))}%)`,
    `20 gyertyás mélypont: ${fp(low20)} (${sign(pct(low20, price))}%)`,
    `Volatilitás (ATR): ${fp(sig.atr)} (${fmt((sig.atr / price) * 100, 1)}% / 4 óra)`,
    "",
    "<b>Stratégia</b>",
    strategy,
    "",
    "<b>Ha most belépnél</b>",
    `Stop-loss: <b>${fp(stop)}</b> (−${fmt((stopDist / price) * 100, 1)}%)`,
    `Max mennyiség 1% kockázattal: <b>${+qty.toPrecision(6)}</b> (~${fmt(qty * price)} USDT)`,
    `Ha kiüt a stop: −${fmt(loss)} USDT (${fmt(capital, 0)} USDT tőkével számolva${capped ? "; a teljes tőke kellene hozzá" : ""})`,
    "",
    "<i>A stratégia szabályainak alkalmazása, nem befektetési tanács.</i>",
  ].join("\n");
}

// ---------------------------------------------------------------------------
// Bot2 (több piacos futures bot) – csak jelzők és olvasás; a worker hajtja végre
// ---------------------------------------------------------------------------
async function bot2Status(d: SQL): Promise<string> {
  const s = await kvGet<any>(d, "b2:snapshot", null);
  if (!s) return "🤖 Bot2 még nem futott le (legfeljebb 5 perc).";
  const mode = s.halted ? "🛑 LEÁLLT (kill switch) – újraindítás: /folytat2 IGEN" : s.paused ? "⏸ szünetel" : "▶️ fut";
  const pos = s.positions.length
    ? s.positions.map((p: any) =>
        `• <b>${esc(p.name)}</b> ${p.side === "LONG" ? "↑ emelkedésre" : "↓ esésre"}: belépő ${fp(p.entry)}, most ${fp(p.last)}\n   stop ${fp(p.stop)}, eredmény ${sign(p.pnl)} USDT`,
      ).join("\n")
    : "• nincs nyitott pozíció";
  const money = s.startEquity
    ? `${fmt(s.startEquity, 0)} → <b>${fmt(s.equity, 0)} USDT</b> (${sign(((s.equity - s.startEquity) / s.startEquity) * 100)}%)`
    : `<b>${fmt(s.equity, 0)} USDT</b>`;
  const dd = s.peak > 0 ? (s.equity / s.peak - 1) * 100 : 0;
  const funds = s.wallet < 50 ? "\n⏳ A futures demó-tárcában nincs pénz, ezért még nem kereskedik." : "";
  return `🤖 <b>Bot2 állapot</b> (frissítve: ${hhmm(s.updatedAt)})\nTőke: ${money}\nVisszaesés a csúcstól: ${fmt(dd, 1)}%\n` +
    `Lezárt trade-ek: ${s.trades} db, összesen ${sign(s.realized)} USDT\nÜzemmód: ${mode}${funds}\n${pos}`;
}

async function bot2Trades(d: SQL): Promise<string> {
  let rows: any[] = [];
  try {
    rows = await d`SELECT symbol, side, exit_time, pnl, r_multiple FROM b2_trades ORDER BY exit_time DESC LIMIT 10`;
  } catch {
    rows = []; // a tábla még nem létezik
  }
  if (!rows.length) return "🤖 Bot2-nek még nincs lezárt trade-je.";
  return "📜 <b>Bot2 utolsó trade-jei</b>\n" +
    rows.map((t: any) => `• ${hhmm(new Date(t.exit_time).getTime())} ${t.symbol.replace("USDT", "")} ${t.side === "LONG" ? "↑" : "↓"}: ${sign(Number(t.pnl))} USDT (${Number(t.r_multiple).toFixed(2)}R)`).join("\n");
}

// ---------------------------------------------------------------------------
// Parancsok
// ---------------------------------------------------------------------------
const HELP =
  "🤖 <b>Trader bot parancsok</b>\n\n" +
  "<b>Régi bot (BTC+ETH)</b>\n" +
  "/allapot – tőke, pozíciók (bot és kézi), üzemmód\n" +
  "/trades – a bot utolsó 10 lezárt trade-je\n" +
  "/stop – szünet: a bot nem nyit új pozíciót\n" +
  "/folytat – szünet vége\n" +
  "/zaras – a bot minden pozíciójának zárása (megerősítést kér)\n\n" +
  "<b>Bot2 (minden piac, hírek)</b>\n" +
  "/allapot2 – Bot2 tőke, pozíciók\n" +
  "/trades2 – Bot2 utolsó 10 trade-je\n" +
  "/stop2 – Bot2 szünet\n" +
  "/folytat2 – Bot2 szünet vége\n" +
  "/zaras2 – Bot2 minden pozíciójának zárása (megerősítést kér)\n\n" +
  "<b>Saját trade-jeid</b>\n" +
  "/elemez BTC – piacelemzés, javasolt stop és pozícióméret\n" +
  "/lista – figyelt piacok és a beállított tőkéd\n" +
  "/figyel SOL – piac hozzáadása a figyeléshez\n" +
  "/torol SOL – piac levétele\n" +
  "/toke 5000 – a tőkéd (ehhez számolom az 1%-os kockázatot)\n" +
  "/elad BTC – kézi pozíció eladása piaci áron (megerősítést kér)\n" +
  "/autostop be|ki – automatikus stop-loss a kézi vételeidre\n\n" +
  "<b>Hírfolyam</b>\n" +
  "/hirek ki – a 4 óránkénti összefoglaló és a riasztások kikapcsolása\n" +
  "/hirek be – visszakapcsolás\n\n" +
  "A kézi trade-jeidet a bot 5 percenként nézi: szól, ha veszel vagy eladsz, és magától beteszi a stop-losst (ha az /autostop be van kapcsolva).";

const STOP_LABEL: Record<string, string> = { ok: "stop ✅", partial: "részben védett ⚠️", none: "NINCS STOP ⚠️", unchecked: "ellenőrzés alatt" };

async function watchlist(d: SQL): Promise<string[]> {
  const stored = await kvGet<string[] | null>(d, "manual_symbols", null);
  return (stored ?? MANUAL_DEFAULT.split(",").map((s) => s.trim().toUpperCase())).filter((s) => SYMBOL_RE.test(s));
}

export async function handleCommand(d: SQL, text: string): Promise<string> {
  const [rawCmd, ...args] = text.trim().split(/\s+/);
  const cmd = rawCmd.toLowerCase().replace(/@\w+$/, "");
  const confirm = args[0]?.toUpperCase() === "IGEN";

  switch (cmd) {
    case "/start":
    case "/segitseg":
    case "/help":
      return HELP;

    case "/allapot": {
      const s = await kvGet<any>(d, "snapshot", null);
      if (!s) return "Még nincs adat: a bot első futása még nem történt meg (legfeljebb 5 perc).";
      const mode = s.halted ? "🛑 LEÁLLT (kill switch) – újraindítás: /folytat IGEN" : s.paused ? "⏸ szünetel" : "▶️ fut";
      const pos = s.positions.length
        ? s.positions.map((p: any) =>
            `• <b>${p.symbol}</b>: ${p.qty} db, belépő ${fmt(p.entry)}, most ${fmt(p.last)}\n   stop ${fmt(p.stop)}, eredmény ${sign(p.pnl)} USDT`,
          ).join("\n")
        : "• nincs nyitott pozíció";
      const dd = s.peak > 0 ? (s.equity / s.peak - 1) * 100 : 0;
      let manual = "";
      if (s.manual) {
        const lines = s.manual.open.length
          ? s.manual.open.map((p: any) =>
              `• <b>${p.symbol}</b>: ${+Number(p.qty).toFixed(8)} db, átlagár ${fp(p.avg)}, most ${fp(p.last)}\n   eredmény ${sign(p.pnl)} USDT, ${STOP_LABEL[p.stop] ?? p.stop}`,
            ).join("\n")
          : "• nincs nyitott kézi pozíció";
        manual = `\n\n<b>Te (kézi trade-ek)</b>\n${lines}\nLezárt kézi eredmény összesen: ${sign(s.manual.realizedTotal)} USDT`;
      }
      return (
        `📊 <b>Állapot</b> (frissítve: ${hhmm(s.updatedAt)})\n` +
        `<b>Bot</b> – tőke: <b>${fmt(s.equity)} USDT</b> (${sign(s.equity - s.capital)} az indulás óta)\n` +
        `Visszaesés a csúcstól: ${fmt(dd, 1)}%\nÜzemmód: ${mode}\n${pos}${manual}\n\nBot2: /allapot2`
      );
    }

    case "/trades": {
      const rows = await d`SELECT symbol, exit_time, pnl, r_multiple FROM trades ORDER BY exit_time DESC LIMIT 10`;
      if (!rows.length) return "A botnak még nincs lezárt trade-je.";
      return (
        "📜 <b>A bot utolsó trade-jei</b>\n" +
        rows.map((t: any) => `• ${hhmm(new Date(t.exit_time).getTime())} ${t.symbol}: ${sign(Number(t.pnl))} USDT (${Number(t.r_multiple).toFixed(2)}R)`).join("\n")
      );
    }

    case "/stop":
    case "/tavol":
      await kvSet(d, "paused", true);
      return "⏸ Szünet bekapcsolva: a bot új pozíciót nem nyit. A nyitott pozíciók stop-lossa a tőzsdén marad.\nFolytatás: /folytat";

    case "/folytat": {
      const halted = await kvGet<boolean>(d, "halted", false);
      if (halted && !confirm) {
        return "🛑 A bot a kill switch miatt állt le. Ha átnézted, és újra akarod indítani, írd: <code>/folytat IGEN</code>";
      }
      if (halted) {
        const s = await kvGet<any>(d, "snapshot", null);
        if (s) await kvSet(d, "peak_equity", s.equity); // új csúcs-alap az újraindításkor
        await kvSet(d, "halted", false);
      }
      await kvSet(d, "paused", false);
      return "▶️ A bot újra kereskedik.";
    }

    case "/zaras":
      if (!confirm) return "⚠️ Ez a bot minden nyitott pozícióját piaci áron lezárja, és szünetelteti a botot. (A kézi pozícióidhoz nem nyúl.)\nHa biztos vagy benne, írd: <code>/zaras IGEN</code>";
      await kvSet(d, "close_all_requested", true);
      return "⏳ Rendben, a következő futásnál (legfeljebb 5 perc) a bot minden pozícióját lezárom, és értesítelek.";

    case "/allapot2":
      return bot2Status(d);

    case "/trades2":
      return bot2Trades(d);

    case "/stop2":
      await kvSet(d, "b2:paused", true);
      return "⏸ Bot2 szünetel: új pozíciót nem nyit. A nyitott pozíciók stop-lossa a tőzsdén marad.\nFolytatás: /folytat2";

    case "/folytat2": {
      const halted = await kvGet<boolean>(d, "b2:halted", false);
      if (halted && !confirm) {
        return "🛑 Bot2 a kill switch miatt állt le. Ha átnézted, és újra akarod indítani, írd: <code>/folytat2 IGEN</code>";
      }
      if (halted) {
        const s = await kvGet<any>(d, "b2:snapshot", null);
        if (s) await kvSet(d, "b2:peak", s.equity); // új csúcs-alap az újraindításkor
        await kvSet(d, "b2:halted", false);
      }
      await kvSet(d, "b2:paused", false);
      return "▶️ Bot2 újra kereskedik.";
    }

    case "/zaras2":
      if (!confirm) return "⚠️ Ez Bot2 minden nyitott pozícióját piaci áron lezárja, és szünetelteti. (A régi bothoz nem nyúl.)\nHa biztos vagy benne, írd: <code>/zaras2 IGEN</code>";
      await kvSet(d, "b2:close_all", true);
      return "⏳ Rendben, Bot2 a következő futásnál (legfeljebb 5 perc) minden pozícióját lezárja, és értesítelek.";

    case "/elemez":
      return analyze(d, args[0]);

    case "/lista": {
      const list = await watchlist(d);
      const capital = await kvGet<number | null>(d, "manual_capital", null) ?? CAPITAL_DEFAULT;
      return `👀 <b>Figyelt piacok</b> (kézi trade-ek)\n${list.map((s) => `• ${s}`).join("\n") || "• üres"}\n\nTőkéd (az 1%-os kockázathoz): ${fmt(capital, 0)} USDT\nMódosítás: /figyel, /torol, /toke`;
    }

    case "/figyel": {
      const symbol = normSymbol(args[0]);
      if (!symbol) return "Add meg a piacot, például: <code>/figyel SOL</code>";
      const list = await watchlist(d);
      if (list.includes(symbol)) return `${symbol} már a listán van. /lista`;
      if (list.length >= MAX_WATCH) return `Legfeljebb ${MAX_WATCH} piacot figyelhetek. Előbb törölj egyet: /torol`;
      try {
        if (!(await symbolExists(symbol))) return `Nincs ilyen kereskedhető piac a Binance-en: ${symbol}`;
      } catch {
        return "⚠️ Most nem érem el a Binance-t, próbáld újra egy perc múlva.";
      }
      await kvSet(d, "manual_symbols", [...list, symbol]);
      return `✅ ${symbol} hozzáadva. A következő futástól (legfeljebb 5 perc) figyelem az ezen a piacon kötött kézi trade-jeidet.`;
    }

    case "/torol": {
      const symbol = normSymbol(args[0]);
      if (!symbol) return "Add meg a piacot, például: <code>/torol SOL</code>";
      const list = await watchlist(d);
      if (!list.includes(symbol)) return `${symbol} nincs a listán. /lista`;
      await kvSet(d, "manual_symbols", list.filter((s) => s !== symbol));
      return `🗑 ${symbol} levéve a figyelőlistáról.`;
    }

    case "/toke": {
      const raw = (args[0] ?? "").replace(/[\s.]/g, "").replace(",", ".");
      const v = Number(raw);
      if (!raw || !Number.isFinite(v) || v < 50 || v > 10_000_000) {
        return "Add meg a tőkédet USDT-ben (50 és 10 000 000 között), például: <code>/toke 5000</code>";
      }
      await kvSet(d, "manual_capital", v);
      return `✅ Tőke beállítva: ${fmt(v, 0)} USDT. Ehhez számolom az 1%-os kockázatot (${fmt(v * RISK)} USDT / trade).`;
    }

    case "/hirek": {
      const arg = (args[0] ?? "").toLowerCase();
      if (arg === "ki") {
        await kvSet(d, "feed_off", true);
        return "🔕 Hírfolyam kikapcsolva: nem küldök 4 óránkénti összefoglalót és piaci riasztást.\nA trade-értesítések és a reggeli/esti riport megmaradnak. Visszakapcsolás: /hirek be";
      }
      if (arg === "be") {
        await kvSet(d, "feed_off", false);
        return "🔔 Hírfolyam bekapcsolva: 4 óránként összefoglaló, ⚡ riasztás 3%-os óránkénti mozgásnál, 🎯 riasztás a vételi szint közelében.";
      }
      const off = await kvGet<boolean>(d, "feed_off", false);
      return `Hírfolyam: ${off ? "🔕 ki" : "🔔 be"}\nKapcsolás: <code>/hirek be</code> vagy <code>/hirek ki</code>`;
    }

    case "/autostop": {
      const arg = (args[0] ?? "").toLowerCase();
      if (arg === "be") {
        await kvSet(d, "autostop", true);
        return "🛡 Automatikus stop-loss bekapcsolva: ha kézzel veszel, legfeljebb 5 percen belül beteszem a stop-losst a tőzsdén (2×ATR szint), és szólok.";
      }
      if (arg === "ki") {
        await kvSet(d, "autostop", false);
        return "⚠️ Automatikus stop-loss kikapcsolva. Az új vételeidhez nem teszek stopot, csak figyelmeztetek. (A már betett stopokat nem törlöm.)\nVisszakapcsolás: /autostop be";
      }
      const on = await kvGet<boolean>(d, "autostop", true);
      return `Automatikus stop-loss: ${on ? "🛡 be" : "⚠️ ki"}\nKapcsolás: <code>/autostop be</code> vagy <code>/autostop ki</code>`;
    }

    case "/elad": {
      const symbol = normSymbol(args[0]);
      if (!symbol) return "Add meg, mit adjak el, például: <code>/elad BTC</code>";
      let pos: any;
      try {
        [pos] = await d`SELECT qty, avg_price FROM manual_positions WHERE symbol = ${symbol}`;
      } catch {
        pos = undefined; // a tábla még nem létezik: nincs kézi pozíció
      }
      if (!pos) return `Nincs nyitott kézi ${symbol} pozíciód, amit el tudnék adni. /allapot`;
      if (args[1]?.toUpperCase() !== "IGEN") {
        return `⚠️ Eladom a teljes kézi ${symbol} pozíciódat (${+Number(pos.qty).toFixed(8)} db) piaci áron, és törlöm a hozzá tett automatikus stop-losst.\n` +
          `Ha biztos vagy benne, írd: <code>/elad ${symbol.replace("USDT", "")} IGEN</code>`;
      }
      // atomi hozzáadás; ha már van folyamatban lévő kérés erre a piacra, nem írjuk felül
      await d`INSERT INTO kv (key, value, updated_at) VALUES ('sell_req', jsonb_build_object(${symbol}::text, ''), now())
              ON CONFLICT (key) DO UPDATE SET
                value = CASE WHEN kv.value ? ${symbol}::text THEN kv.value ELSE kv.value || EXCLUDED.value END,
                updated_at = now()`;
      return `⏳ Rendben, legfeljebb 5 percen belül eladom a ${symbol} pozíciódat piaci áron, és szólok az eredménnyel.`;
    }

    default:
      return "Ezt a parancsot nem ismerem. /segitseg";
  }
}

function secretOk(req: Request): boolean {
  const got = req.headers.get("x-telegram-bot-api-secret-token") ?? "";
  const a = Buffer.from(got), b = Buffer.from(SECRET);
  return SECRET.length > 0 && a.length === b.length && timingSafeEqual(a, b);
}

const reply = (chatId: number | string, text: string) =>
  Response.json({ method: "sendMessage", chat_id: chatId, text, parse_mode: "HTML" });

export async function handle(req: Request): Promise<Response> {
  const url = new URL(req.url);
  if (req.method === "GET" && url.pathname === "/health") return new Response("ok");
  if (req.method !== "POST" || url.pathname !== "/telegram") return new Response("not found", { status: 404 });
  if (!secretOk(req)) return new Response("forbidden", { status: 403 });
  if (!db) return new Response("not configured", { status: 503 });

  let update: any;
  try {
    update = await req.json();
  } catch {
    return new Response("bad request", { status: 400 });
  }
  const msg = update?.message;
  const updateId = Number(update?.update_id);
  if (!Number.isSafeInteger(updateId) || !msg?.chat?.id || typeof msg.text !== "string") return new Response("");

  try {
    await migrate(db);
    const ins = await db`INSERT INTO tg_updates (update_id) VALUES (${updateId}) ON CONFLICT DO NOTHING RETURNING update_id`;
    if (!ins.length) return new Response(""); // már feldolgozva

    if (String(msg.chat.id) !== CHAT_ID) {
      console.warn("Idegen chat próbálkozás:", msg.chat.id);
      return reply(msg.chat.id, "Ez egy privát bot.");
    }
    if (!msg.text.startsWith("/")) return reply(msg.chat.id, "Parancsokkal irányíthatsz. Lista: /segitseg");
    return reply(msg.chat.id, await handleCommand(db, msg.text.slice(0, 200)));
  } catch (e) {
    console.error("Webhook hiba:", e);
    // 200-at adunk, hogy a Telegram ne küldje újra végtelenül; a felhasználó kap visszajelzést
    return reply(msg.chat.id, "⚠️ Belső hiba, próbáld újra egy perc múlva.");
  }
}

if (import.meta.main) {
  Bun.serve({ port: PORT, fetch: handle });
  console.log(`Webhook fut a ${PORT} porton`);
}
