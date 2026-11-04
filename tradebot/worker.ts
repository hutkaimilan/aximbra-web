/**
 * Trader bot – kereskedő worker (Railway Function, Bun, cron: 5 percenként).
 *
 * Minden futás egy rövid, önálló lépés (stateless worker, az állapot Postgresben):
 *   1. lease (zár), hogy két futás ne fusson egyszerre
 *   2. félbemaradt belépések rendezése (crash utáni helyreállítás)
 *   3. nyitott pozíciók ellenőrzése: kiütött-e a stop, él-e a tőzsdei stop
 *   4. felhasználói kérések (mindent zár), kill switch, napi limit
 *   5. új lezárt 4 órás gyertyán: követő stop emelése, belépési jelzés keresése
 *   6. pillanatkép a Telegram /allapot parancshoz, napi riportok
 *
 * Stratégia (a backtesttel azonos): 4h Donchian kitörés.
 *   Belépés: záró > előző 20 gyertya csúcsa ÉS záró > EMA200.
 *   Kezdő stop: belépő − 2×ATR14, a TŐZSDÉN leadva (STOP_LOSS).
 *   Követő stop: legmagasabb záró − 3×ATR14, csak felfelé mozdul.
 *
 * Biztonsági elvek:
 *   - Minden megbízás determinisztikus clientOrderId-t kap; időtúllépés után
 *     először lekérdezzük, és csak akkor küldjük újra, ha biztosan nem létezik.
 *   - A stop mindig a tőzsdén van; ha nem sikerül leadni, a bot azonnal kiszáll.
 *   - A bot csak a saját pozícióit kezeli (a demo számla egyéb egyenlegeihez nem nyúl).
 */
import { SQL } from "bun";
import { createHmac, randomUUID } from "node:crypto";

// ---------------------------------------------------------------------------
// Konfiguráció
// ---------------------------------------------------------------------------
function envStr(name: string, fallback?: string): string {
  const v = (process.env[name] ?? "").trim();
  if (v) return v;
  if (fallback !== undefined) return fallback;
  throw new ConfigError(`Hiányzó környezeti változó: ${name}`);
}
function envNum(name: string, fallback: number, min: number, max: number): number {
  const raw = (process.env[name] ?? "").trim();
  if (!raw) return fallback;
  const v = Number(raw);
  if (!Number.isFinite(v) || v < min || v > max) {
    throw new ConfigError(`Érvénytelen ${name}=${raw} (megengedett: ${min}..${max})`);
  }
  return v;
}

export class ConfigError extends Error {}

export interface Config {
  databaseUrl: string;
  binanceBase: string;
  apiKey: string;
  apiSecret: string;
  tgToken: string;
  tgChatId: string;
  tgApiBase: string;
  webhookUrl: string;
  webhookSecret: string;
  symbols: string[];
  capital: number;
  riskPerTrade: number;
  maxPositions: number;
  dailyLossLimit: number;
  killSwitchDd: number;
  lookback: number;
  emaFilter: number;
  atrN: number;
  stopAtr: number;
  trailAtr: number;
  maxEntryDelayMs: number;
  manualSymbols: string[];
  manualCapital: number;
}

export const SYMBOL_RE = /^[A-Z0-9]{2,20}USDT$/;
export const MANUAL_DEFAULT = "BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT";

export function loadConfig(): Config {
  const symbols = envStr("SYMBOLS", "BTCUSDT,ETHUSDT")
    .split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
  if (!symbols.every((s) => SYMBOL_RE.test(s))) {
    throw new ConfigError(`Érvénytelen SYMBOLS: ${symbols.join(",")}`);
  }
  const manualSymbols = envStr("MANUAL_SYMBOLS", MANUAL_DEFAULT)
    .split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
  if (!manualSymbols.every((s) => SYMBOL_RE.test(s))) {
    throw new ConfigError(`Érvénytelen MANUAL_SYMBOLS: ${manualSymbols.join(",")}`);
  }
  const chatId = envStr("TELEGRAM_CHAT_ID");
  if (!/^-?\d{5,20}$/.test(chatId)) throw new ConfigError("Érvénytelen TELEGRAM_CHAT_ID");
  return {
    databaseUrl: envStr("DATABASE_URL"),
    binanceBase: envStr("BINANCE_BASE_URL", "https://demo-api.binance.com").replace(/\/$/, ""),
    apiKey: envStr("BINANCE_API_KEY"),
    apiSecret: envStr("BINANCE_API_SECRET"),
    tgToken: envStr("TELEGRAM_TOKEN"),
    tgChatId: chatId,
    tgApiBase: envStr("TELEGRAM_API_BASE", "https://api.telegram.org").replace(/\/$/, ""),
    webhookUrl: envStr("WEBHOOK_URL", ""),
    webhookSecret: envStr("TG_WEBHOOK_SECRET", ""),
    symbols,
    capital: envNum("BOT_CAPITAL_USDT", 10_000, 50, 10_000_000),
    riskPerTrade: envNum("RISK_PER_TRADE", 0.01, 0.001, 0.02),
    maxPositions: envNum("MAX_POSITIONS", 2, 1, 5),
    dailyLossLimit: envNum("DAILY_LOSS_LIMIT", 0.03, 0.005, 0.2),
    killSwitchDd: envNum("KILL_SWITCH_DD", 0.2, 0.05, 0.5),
    lookback: 20,
    emaFilter: 200,
    atrN: 14,
    stopAtr: 2,
    trailAtr: 3,
    maxEntryDelayMs: 30 * 60_000,
    manualSymbols,
    manualCapital: envNum("MANUAL_CAPITAL_USDT", 10_000, 50, 10_000_000),
  };
}

// ---------------------------------------------------------------------------
// Indikátorok – a pandas implementációval egyező számítás (ewm adjust=False)
// ---------------------------------------------------------------------------
export interface Candle {
  openTime: number;
  closeTime: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export function ema(values: number[], n: number): number[] {
  const a = 2 / (n + 1);
  const out: number[] = new Array(values.length).fill(NaN);
  let y = NaN;
  for (let i = 0; i < values.length; i++) {
    y = i === 0 ? values[0] : a * values[i] + (1 - a) * y;
    if (i >= n - 1) out[i] = y;
  }
  return out;
}

export function atr(c: Candle[], n: number): number[] {
  const tr = c.map((k, i) =>
    i === 0
      ? k.high - k.low
      : Math.max(k.high - k.low, Math.abs(k.high - c[i - 1].close), Math.abs(k.low - c[i - 1].close)),
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

export interface SignalState {
  entry: boolean;
  close: number;
  priorHigh: number;
  emaFilter: number;
  atr: number;
}

/** Az utolsó LEZÁRT gyertyára számolt jelzés. */
export function evaluate(c: Candle[], cfg: Pick<Config, "lookback" | "emaFilter" | "atrN">): SignalState {
  if (c.length < cfg.emaFilter + cfg.lookback + 5) {
    throw new Error(`Kevés gyertya az indikátorokhoz: ${c.length}`);
  }
  const i = c.length - 1;
  const closes = c.map((k) => k.close);
  const e = ema(closes, cfg.emaFilter)[i];
  const a = atr(c, cfg.atrN)[i];
  let priorHigh = -Infinity;
  for (let j = i - cfg.lookback; j < i; j++) priorHigh = Math.max(priorHigh, c[j].high);
  const close = c[i].close;
  const valid = Number.isFinite(e) && Number.isFinite(a) && a > 0;
  return { entry: valid && close > priorHigh && close > e, close, priorHigh, emaFilter: e, atr: a };
}

// ---------------------------------------------------------------------------
// Binance REST kliens
// ---------------------------------------------------------------------------
export class BinanceError extends Error {
  constructor(public status: number, public code: number | undefined, msg: string, public data?: any) {
    super(msg);
  }
}
export class RateLimitError extends Error {}
/** Hálózati hiba / időtúllépés / 5xx: a kérés sorsa ismeretlen. */
export class UnknownOutcomeError extends Error {}

interface SymbolRules {
  stepSize: number;
  stepDecimals: number;
  minQty: number;
  tickSize: number;
  tickDecimals: number;
  minNotional: number;
  stopType: "STOP_LOSS" | "STOP_LOSS_LIMIT";
  base: string;
}

function decimalsOf(step: string): number {
  const s = String(Number(step));
  if (s.includes("e-")) return Number(s.split("e-")[1]);
  const i = s.indexOf(".");
  return i < 0 ? 0 : s.length - i - 1;
}
export function floorTo(value: number, step: number, decimals: number): string {
  const units = Math.floor(value / step + 1e-9);
  return (units * step).toFixed(decimals);
}

export class Binance {
  private timeOffset = 0;
  constructor(private cfg: Config) {}

  async syncTime(): Promise<void> {
    const t0 = Date.now();
    const r = await this.req("GET", "/api/v3/time", {}, false);
    this.timeOffset = r.serverTime - Math.round((t0 + Date.now()) / 2);
  }
  now(): number {
    return Date.now() + this.timeOffset;
  }

  async req(method: string, path: string, params: Record<string, string | number>, signed: boolean, retryClock = true): Promise<any> {
    const q = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) q.set(k, String(v));
    if (signed) {
      q.set("timestamp", String(this.now()));
      q.set("recvWindow", "5000");
      q.set("signature", createHmac("sha256", this.cfg.apiSecret).update(q.toString()).digest("hex"));
    }
    const url = `${this.cfg.binanceBase}${path}?${q.toString()}`;
    let res: Response;
    try {
      res = await fetch(url, {
        method,
        headers: signed ? { "X-MBX-APIKEY": this.cfg.apiKey } : {},
        signal: AbortSignal.timeout(10_000),
      });
    } catch (e) {
      throw new UnknownOutcomeError(`Hálózati hiba (${method} ${path}): ${(e as Error).message}`);
    }
    if (res.status === 429 || res.status === 418) {
      throw new RateLimitError(`Binance rate limit (${res.status}), retry-after=${res.headers.get("retry-after")}`);
    }
    if (res.status >= 500) throw new UnknownOutcomeError(`Binance ${res.status} (${method} ${path})`);
    const text = await res.text();
    let body: any;
    try {
      body = JSON.parse(text);
    } catch {
      throw new BinanceError(res.status, undefined, `Nem JSON válasz (${res.status}): ${text.slice(0, 200)}`);
    }
    if (!res.ok) {
      if (body?.code === -1021 && retryClock) {
        await this.syncTime();
        return this.req(method, path, params, signed, false);
      }
      throw new BinanceError(res.status, body?.code, body?.msg ?? `HTTP ${res.status}`, body?.data);
    }
    return body;
  }

  async rules(symbol: string): Promise<SymbolRules> {
    const info = await this.req("GET", "/api/v3/exchangeInfo", { symbol }, false);
    const s = info.symbols?.[0];
    if (!s || s.status !== "TRADING") throw new Error(`${symbol} nem kereskedhető (${s?.status})`);
    const f = (t: string) => s.filters.find((x: any) => x.filterType === t);
    const lot = f("LOT_SIZE"), price = f("PRICE_FILTER"), notional = f("NOTIONAL") ?? f("MIN_NOTIONAL");
    if (!lot || !price) throw new Error(`${symbol}: hiányzó LOT_SIZE/PRICE_FILTER szűrő`);
    const types: string[] = s.orderTypes ?? [];
    const stopType = types.includes("STOP_LOSS") ? "STOP_LOSS" : types.includes("STOP_LOSS_LIMIT") ? "STOP_LOSS_LIMIT" : null;
    if (!stopType) throw new Error(`${symbol}: a tőzsde nem támogat stop megbízást`);
    return {
      stepSize: Number(lot.stepSize), stepDecimals: decimalsOf(lot.stepSize), minQty: Number(lot.minQty),
      tickSize: Number(price.tickSize), tickDecimals: decimalsOf(price.tickSize),
      minNotional: Number(notional?.minNotional ?? 0), stopType, base: s.baseAsset,
    };
  }

  async closedCandles(symbol: string): Promise<Candle[]> {
    const rows: any[] = await this.req("GET", "/api/v3/klines", { symbol, interval: "4h", limit: 1000 }, false);
    const now = this.now();
    return rows
      .map((r) => ({
        openTime: r[0], closeTime: r[6],
        open: Number(r[1]), high: Number(r[2]), low: Number(r[3]), close: Number(r[4]),
      }))
      .filter((k) => k.closeTime < now && [k.open, k.high, k.low, k.close].every((x) => Number.isFinite(x) && x > 0));
  }

  async price(symbol: string): Promise<number> {
    const r = await this.req("GET", "/api/v3/ticker/price", { symbol }, false);
    const p = Number(r.price);
    if (!Number.isFinite(p) || p <= 0) throw new Error(`Érvénytelen ár: ${symbol} ${r.price}`);
    return p;
  }

  async freeBalance(asset: string): Promise<number> {
    const r = await this.req("GET", "/api/v3/account", { omitZeroBalances: "true" }, true);
    const b = (r.balances ?? []).find((x: any) => x.asset === asset);
    return b ? Number(b.free) : 0;
  }

  /** null, ha a megbízás nem létezik. */
  async getOrder(symbol: string, clientId: string): Promise<any | null> {
    try {
      return await this.req("GET", "/api/v3/order", { symbol, origClientOrderId: clientId }, true);
    } catch (e) {
      if (e instanceof BinanceError && e.code === -2013) return null;
      throw e;
    }
  }

  /**
   * Idempotens megbízás: ismeretlen kimenetelnél lekérdezi a clientOrderId-t,
   * és csak akkor küldi újra, ha a tőzsde biztosan nem kapta meg.
   */
  async placeOrder(params: Record<string, string | number>): Promise<any> {
    const clientId = String(params.newClientOrderId);
    const symbol = String(params.symbol);
    for (let attempt = 1; attempt <= 3; attempt++) {
      const existing = attempt > 1 ? await this.getOrder(symbol, clientId) : null;
      if (existing) return existing;
      try {
        return await this.req("POST", "/api/v3/order", { ...params, newOrderRespType: "FULL" }, true);
      } catch (e) {
        if (!(e instanceof UnknownOutcomeError)) throw e;
        await Bun.sleep(1500 * attempt);
      }
    }
    const final = await this.getOrder(symbol, clientId);
    if (final) return final;
    throw new UnknownOutcomeError(`A megbízás sorsa nem tisztázható: ${clientId}`);
  }

  /** true, ha törölve lett vagy már nem élt. */
  async cancelOrder(symbol: string, clientId: string): Promise<void> {
    try {
      await this.req("DELETE", "/api/v3/order", { symbol, origClientOrderId: clientId }, true);
    } catch (e) {
      if (e instanceof BinanceError && (e.code === -2011 || e.code === -2013)) return;
      throw e;
    }
  }

  async cancelReplace(params: Record<string, string | number>): Promise<{ cancelOk: boolean; newOk: boolean; data?: any }> {
    try {
      const r = await this.req("POST", "/api/v3/order/cancelReplace", { ...params, cancelReplaceMode: "STOP_ON_FAILURE" }, true);
      return { cancelOk: r.cancelResult === "SUCCESS", newOk: r.newOrderResult === "SUCCESS", data: r };
    } catch (e) {
      if (e instanceof BinanceError && e.data) {
        return { cancelOk: e.data.cancelResult === "SUCCESS", newOk: e.data.newOrderResult === "SUCCESS", data: e.data };
      }
      throw e;
    }
  }

  async tradesForOrder(symbol: string, orderId: number): Promise<any[]> {
    return await this.req("GET", "/api/v3/myTrades", { symbol, orderId }, true);
  }

  async myTrades(symbol: string, opts: { fromId?: number; limit?: number }): Promise<any[]> {
    const p: Record<string, string | number> = { symbol, limit: opts.limit ?? 1000 };
    if (opts.fromId !== undefined) p.fromId = opts.fromId;
    return await this.req("GET", "/api/v3/myTrades", p, true);
  }

  async getOrderById(symbol: string, orderId: number): Promise<any | null> {
    try {
      return await this.req("GET", "/api/v3/order", { symbol, orderId }, true);
    } catch (e) {
      if (e instanceof BinanceError && e.code === -2013) return null;
      throw e;
    }
  }

  async openOrders(symbol: string): Promise<any[]> {
    return await this.req("GET", "/api/v3/openOrders", { symbol }, true);
  }

  /** Az ár ~1 órával ezelőtt (13 db 5 perces gyertya első nyitóára). */
  async priceHourAgo(symbol: string): Promise<number> {
    const rows: any[] = await this.req("GET", "/api/v3/klines", { symbol, interval: "5m", limit: 13 }, false);
    const p = Number(rows?.[0]?.[1]);
    if (!Number.isFinite(p) || p <= 0) throw new Error(`Érvénytelen 5m adat: ${symbol}`);
    return p;
  }
}

// ---------------------------------------------------------------------------
// Adatbázis
// ---------------------------------------------------------------------------
export async function migrate(db: SQL): Promise<void> {
  await db`CREATE TABLE IF NOT EXISTS kv (key text PRIMARY KEY, value jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())`;
  await db`CREATE TABLE IF NOT EXISTS lease (name text PRIMARY KEY, holder text NOT NULL, expires_at timestamptz NOT NULL)`;
  await db`CREATE TABLE IF NOT EXISTS tg_updates (update_id bigint PRIMARY KEY, received_at timestamptz NOT NULL DEFAULT now())`;
  await db`CREATE TABLE IF NOT EXISTS positions (
    symbol text PRIMARY KEY,
    status text NOT NULL,                 -- opening | open
    entry_client_id text NOT NULL,
    candle_open_time double precision NOT NULL,
    planned_stop_dist double precision NOT NULL,
    qty double precision,
    cost_usdt double precision,
    entry_price double precision,
    entry_time timestamptz,
    stop_price double precision,
    stop_client_id text,
    stop_seq int NOT NULL DEFAULT 0,
    highest_close double precision,
    risk_usdt double precision
  )`;
  await db`CREATE TABLE IF NOT EXISTS trades (
    id serial PRIMARY KEY,
    symbol text NOT NULL,
    entry_time timestamptz NOT NULL,
    exit_time timestamptz NOT NULL,
    entry_price double precision NOT NULL,
    exit_price double precision NOT NULL,
    qty double precision NOT NULL,
    pnl double precision NOT NULL,
    r_multiple double precision NOT NULL,
    reason text NOT NULL,
    exit_client_id text UNIQUE
  )`;
  await db`CREATE TABLE IF NOT EXISTS manual_fills (
    symbol text NOT NULL, trade_id bigint NOT NULL, is_bot boolean NOT NULL,
    seen_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY (symbol, trade_id))`;
  await db`CREATE TABLE IF NOT EXISTS manual_positions (
    symbol text PRIMARY KEY,
    qty double precision NOT NULL,
    cost double precision NOT NULL,
    avg_price double precision NOT NULL,
    realized double precision NOT NULL DEFAULT 0,
    opened_at timestamptz NOT NULL DEFAULT now(),
    stop_state text NOT NULL DEFAULT 'unchecked',  -- unchecked | ok | partial | none
    risk_state text NOT NULL DEFAULT 'ok'          -- ok | high
  )`;
  await db`ALTER TABLE manual_positions ADD COLUMN IF NOT EXISTS auto_stop_id text`;
  await db`ALTER TABLE manual_positions ADD COLUMN IF NOT EXISTS auto_stop_seq int NOT NULL DEFAULT 0`;
  await db`CREATE TABLE IF NOT EXISTS manual_closed (
    id serial PRIMARY KEY, symbol text NOT NULL, opened_at timestamptz NOT NULL,
    closed_at timestamptz NOT NULL DEFAULT now(), pnl double precision NOT NULL)`;
}

export async function kvGet<T>(db: SQL, key: string, fallback: T): Promise<T> {
  const rows = await db`SELECT value FROM kv WHERE key = ${key}`;
  return rows.length ? (rows[0].value as T) : fallback;
}
export async function kvSet(db: SQL, key: string, value: unknown): Promise<void> {
  await db`INSERT INTO kv (key, value, updated_at) VALUES (${key}, ${JSON.stringify(value)}::text::jsonb, now())
           ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()`;
}

async function acquireLease(db: SQL, holder: string): Promise<boolean> {
  const rows = await db`
    INSERT INTO lease (name, holder, expires_at) VALUES ('worker', ${holder}, now() + interval '4 minutes')
    ON CONFLICT (name) DO UPDATE SET holder = EXCLUDED.holder, expires_at = EXCLUDED.expires_at
      WHERE lease.expires_at < now()
    RETURNING holder`;
  return rows.length === 1;
}
async function releaseLease(db: SQL, holder: string): Promise<void> {
  await db`UPDATE lease SET expires_at = now() WHERE name = 'worker' AND holder = ${holder}`;
}

// ---------------------------------------------------------------------------
// Telegram (csak küldés; a parancsokat a webhook function fogadja)
// ---------------------------------------------------------------------------
export function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function budapestParts(ms: number): { date: string; hour: number } {
  const f = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Budapest", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", hourCycle: "h23",
  });
  const p = Object.fromEntries(f.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  return { date: `${p.year}-${p.month}-${p.day}`, hour: Number(p.hour) };
}
export function hhmm(ms: number): string {
  return new Intl.DateTimeFormat("hu-HU", { timeZone: "Europe/Budapest", hour: "2-digit", minute: "2-digit" }).format(new Date(ms));
}

export class Telegram {
  constructor(private cfg: Config) {}
  /** Éjjel (23–7) néma értesítés, kivéve ha sürgős. Hibát nem dob: a kereskedést nem akaszthatja meg. */
  async send(html: string, urgent = false): Promise<boolean> {
    const { hour } = budapestParts(Date.now());
    const quiet = !urgent && (hour >= 23 || hour < 7);
    try {
      const res = await fetch(`${this.cfg.tgApiBase}/bot${this.cfg.tgToken}/sendMessage`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ chat_id: this.cfg.tgChatId, text: html, parse_mode: "HTML", disable_notification: quiet }),
        signal: AbortSignal.timeout(10_000),
      });
      if (!res.ok) console.error("Telegram küldési hiba", res.status, (await res.text()).slice(0, 200));
      return res.ok;
    } catch (e) {
      console.error("Telegram nem elérhető:", (e as Error).message);
      return false;
    }
  }
  async call(method: string, payload: unknown): Promise<any> {
    const res = await fetch(`${this.cfg.tgApiBase}/bot${this.cfg.tgToken}/${method}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(10_000),
    });
    const body = await res.json().catch(() => ({}));
    if (!res.ok || !body.ok) throw new Error(`Telegram ${method} hiba: ${res.status} ${JSON.stringify(body).slice(0, 200)}`);
    return body.result;
  }
}

const COMMANDS = [
  { command: "allapot", description: "Tőke, nyitott pozíciók, üzemmód" },
  { command: "elemez", description: "Piacelemzés, pl. /elemez BTC" },
  { command: "lista", description: "Figyelt piacok és a tőkéd" },
  { command: "figyel", description: "Piac hozzáadása, pl. /figyel SOL" },
  { command: "torol", description: "Piac törlése, pl. /torol SOL" },
  { command: "toke", description: "A kézi tőkéd beállítása, pl. /toke 5000" },
  { command: "hirek", description: "Piaci hírfolyam be/ki, pl. /hirek ki" },
  { command: "elad", description: "Kézi pozíció eladása, pl. /elad BTC" },
  { command: "autostop", description: "Automatikus stop-loss be/ki" },
  { command: "trades", description: "Az utolsó 10 lezárt trade" },
  { command: "stop", description: "Szünet: nem nyit új pozíciót" },
  { command: "folytat", description: "Szünet vége, a bot újra kereskedik" },
  { command: "zaras", description: "Minden pozíció zárása (megerősítéssel)" },
  { command: "segitseg", description: "Parancsok listája" },
];

async function ensureTelegramSetup(db: SQL, cfg: Config, tg: Telegram): Promise<void> {
  if (!cfg.webhookUrl || !cfg.webhookSecret) return;
  const want = { url: cfg.webhookUrl, v: 6 };
  const have = await kvGet<any>(db, "tg_setup", null);
  if (have && have.url === want.url && have.v === want.v) return;
  await tg.call("setWebhook", { url: cfg.webhookUrl, secret_token: cfg.webhookSecret, allowed_updates: ["message"] });
  await tg.call("setMyCommands", { commands: COMMANDS });
  await kvSet(db, "tg_setup", want);
  // "csak pénz" mód: a piaci hírfolyam alapból ki (egyszer állítjuk; /hirek be visszakapcsolja)
  if ((have?.v ?? 0) < 6) await kvSet(db, "feed_off", true);
  if (!have) {
    await tg.send("✅ <b>A Trader bot elindult.</b>\nDemó módban kereskedik (BTC, ETH, 4 órás kitörés-stratégia).\nParancsok: /segitseg");
    return;
  }
  const parts: string[] = [];
  if ((have.v ?? 0) < 3) {
    parts.push(
      "🔄 <b>Frissítés: a bot mostantól a te kézi trade-jeidet is figyeli.</b>\n" +
        "• Szólok, ha veszel vagy eladsz a Binance-en\n• Figyelmeztetek, ha nincs stop-loss, vagy 1%-nál többet kockáztatsz\n" +
        "• Új parancs: /elemez BTC – piacelemzés és pozícióméret\n• /lista, /figyel, /torol, /toke",
    );
  }
  if ((have.v ?? 0) < 4) {
    parts.push(
      "📡 <b>Új: piaci hírfolyam</b>\n" +
        "• 4 óránként összefoglaló a figyelt piacokról (01, 05, 09, 13, 17, 21 óra körül)\n" +
        "• ⚡ riasztás, ha egy piac 1 óra alatt 3%-nál többet mozdul\n" +
        "• 🎯 riasztás, ha egy piac 1%-on belül van a vételi szinthez\n" +
        "Éjjel 23–7 között némán jönnek. Kikapcsolás: /hirek ki",
    );
  }
  if ((have.v ?? 0) < 5) {
    parts.push(
      "🛡 <b>Új: automatikus stop-loss</b>\n" +
        "• Ha kézzel veszel, a bot magától beteszi a stop-losst a tőzsdén (2×ATR szint), és szól\n" +
        "• Eladni így tudsz a legegyszerűbben: /elad BTC\n" +
        "• Kikapcsolás: /autostop ki",
    );
  }
  if ((have.v ?? 0) < 6) {
    const coins = cfg.symbols.map((s) => s.replace("USDT", "")).join(", ");
    parts.push(
      "💰 <b>Csak pénz mód</b>\n" +
        `• A bot mostantól ${cfg.symbols.length} piacot figyel: ${coins}\n` +
        `• Egyszerre legfeljebb ${cfg.maxPositions} pozíciót nyit, mindegyiknél 1% kockázattal\n` +
        "• Csak akkor írok, ha vett, ha zárt (mennyit nyert/veszített), reggel és este a tőke állásáról, vagy ha baj van\n" +
        "• A 4 óránkénti piaci hírek ki vannak kapcsolva (vissza: /hirek be)\n" +
        "Neked semmit nem kell csinálnod.",
    );
  }
  if (parts.length) await tg.send(parts.join("\n\n") + "\n\nRészletek: /segitseg");
}

/** Ugyanazt a hibát legfeljebb óránként egyszer küldi el. */
async function notifyError(db: SQL, tg: Telegram, key: string, html: string): Promise<void> {
  const last = await kvGet<number>(db, `err:${key}`, 0);
  if (Date.now() - last < 3_600_000) return;
  await kvSet(db, `err:${key}`, Date.now());
  await tg.send(html, true);
}

// ---------------------------------------------------------------------------
// Kereskedési logika
// ---------------------------------------------------------------------------
interface PositionRow {
  symbol: string;
  status: "opening" | "open";
  entry_client_id: string;
  candle_open_time: number;
  planned_stop_dist: number;
  qty: number;
  cost_usdt: number;
  entry_price: number;
  entry_time: Date;
  stop_price: number;
  stop_client_id: string;
  stop_seq: number;
  highest_close: number;
  risk_usdt: number;
}

const fmt = (n: number, d = 2) =>
  n.toLocaleString("hu-HU", { minimumFractionDigits: d, maximumFractionDigits: d });
const sign = (n: number) => (n >= 0 ? "+" : "−") + fmt(Math.abs(n));

export class Trader {
  private rulesCache = new Map<string, SymbolRules>();

  constructor(
    private db: SQL,
    private bn: Binance,
    private tg: Telegram,
    private cfg: Config,
    private prices: Map<string, number> = new Map(),
  ) {}

  private async rules(symbol: string): Promise<SymbolRules> {
    let r = this.rulesCache.get(symbol);
    if (!r) {
      r = await this.bn.rules(symbol);
      this.rulesCache.set(symbol, r);
    }
    return r;
  }
  private async lastPrice(symbol: string): Promise<number> {
    let p = this.prices.get(symbol);
    if (p === undefined) {
      p = await this.bn.price(symbol);
      this.prices.set(symbol, p);
    }
    return p;
  }

  async positions(): Promise<PositionRow[]> {
    return (await this.db`SELECT * FROM positions ORDER BY symbol`) as PositionRow[];
  }

  async realizedTotal(): Promise<number> {
    const r = await this.db`SELECT COALESCE(SUM(pnl), 0) AS s FROM trades`;
    return Number(r[0].s);
  }

  /** Bot-tőke = induló tőke + realizált eredmény + nyitott pozíciók nem realizált eredménye. */
  async equity(): Promise<{ equity: number; cash: number; unrealized: number }> {
    const realized = await this.realizedTotal();
    let unrealized = 0, invested = 0;
    for (const p of await this.positions()) {
      if (p.status !== "open") continue;
      unrealized += p.qty * (await this.lastPrice(p.symbol)) - p.cost_usdt;
      invested += p.cost_usdt;
    }
    const cash = this.cfg.capital + realized - invested;
    return { equity: cash + invested + unrealized, cash, unrealized };
  }

  // --- belépés ------------------------------------------------------------
  async enter(symbol: string, candle: Candle, sig: SignalState): Promise<void> {
    const rules = await this.rules(symbol);
    const { equity, cash } = await this.equity();
    const price = await this.lastPrice(symbol);
    const stopDist = this.cfg.stopAtr * sig.atr;
    if (!(stopDist > 0) || stopDist >= price) return;

    let qty = (equity * this.cfg.riskPerTrade) / stopDist;
    const freeUsdt = await this.bn.freeBalance("USDT");
    const maxByCash = (Math.min(cash, freeUsdt) * 0.98) / price; // tartalék díjra és csúszásra
    if (qty > maxByCash) qty = maxByCash;
    const qtyStr = floorTo(qty, rules.stepSize, rules.stepDecimals);
    if (Number(qtyStr) < rules.minQty || Number(qtyStr) * price < Math.max(rules.minNotional, 10)) {
      console.log(`${symbol} jelzés kihagyva: túl kicsi pozíció (szabad USDT: ${fmt(freeUsdt)})`);
      return;
    }

    const clientId = `tb-${symbol}-${candle.openTime}-e`;
    // Szándék rögzítése a megbízás ELŐTT: crash esetén a következő futás rendezi.
    const ins = await this.db`
      INSERT INTO positions (symbol, status, entry_client_id, candle_open_time, planned_stop_dist)
      VALUES (${symbol}, 'opening', ${clientId}, ${candle.openTime}, ${stopDist})
      ON CONFLICT (symbol) DO NOTHING RETURNING symbol`;
    if (!ins.length) return; // már van pozíció ezen a piacon

    let order: any;
    try {
      order = await this.bn.placeOrder({ symbol, side: "BUY", type: "MARKET", quantity: qtyStr, newClientOrderId: clientId });
    } catch (e) {
      if (e instanceof UnknownOutcomeError) throw e; // a sor marad 'opening', a következő futás tisztázza
      await this.db`DELETE FROM positions WHERE symbol = ${symbol} AND status = 'opening'`;
      throw e;
    }
    await this.finishEntry(symbol, order);
  }

  /** Teljesült vételi megbízásból nyitott pozíció + tőzsdei stop. */
  private async finishEntry(symbol: string, order: any): Promise<void> {
    const rules = await this.rules(symbol);
    const [pos] = (await this.db`SELECT * FROM positions WHERE symbol = ${symbol}`) as PositionRow[];
    if (!pos) return;
    const executed = Number(order.executedQty);
    if (order.status !== "FILLED" || !(executed > 0)) {
      if (["CANCELED", "EXPIRED", "REJECTED", "EXPIRED_IN_MATCH"].includes(order.status) && executed === 0) {
        await this.db`DELETE FROM positions WHERE symbol = ${symbol} AND status = 'opening'`;
      }
      return;
    }
    const quote = Number(order.cummulativeQuoteQty);
    let fills: any[] = order.fills;
    if (!fills) fills = await this.bn.tradesForOrder(symbol, order.orderId);
    const baseFee = fills.filter((f) => f.commissionAsset === rules.base).reduce((s, f) => s + Number(f.commission), 0);
    const usdtFee = fills.filter((f) => f.commissionAsset === "USDT").reduce((s, f) => s + Number(f.commission), 0);
    const netQty = Number(floorTo(executed - baseFee, rules.stepSize, rules.stepDecimals));
    const entryPrice = quote / executed;
    const cost = quote + usdtFee;
    const stop = Number(floorTo(entryPrice - pos.planned_stop_dist, rules.tickSize, rules.tickDecimals));
    const risk = (entryPrice - stop) * netQty;

    await this.db`UPDATE positions SET status = 'open', qty = ${netQty}, cost_usdt = ${cost},
      entry_price = ${entryPrice}, entry_time = now(), highest_close = ${entryPrice}, risk_usdt = ${risk}
      WHERE symbol = ${symbol}`;

    const ok = await this.placeStop(symbol, netQty, stop, 1);
    if (!ok) {
      await this.marketExit(symbol, "stop_hiba");
      await this.tg.send(`🚨 <b>${symbol}</b>: a stop-loss nem volt leadható, ezért a pozíciót azonnal lezártam.`, true);
      return;
    }
    await this.tg.send(
      `🟢 <b>VÉTEL – ${symbol}</b>\n` +
        `Belépő: ${fmt(entryPrice)} USDT\nMennyiség: ${netQty}\nÉrték: ${fmt(cost)} USDT\n` +
        `Stop-loss: ${fmt(stop)} (−${fmt(((entryPrice - stop) / entryPrice) * 100)}%)\n` +
        `Kockázat: ${fmt(risk)} USDT\nOk: a záróár áttörte az előző 20 gyertya csúcsát, emelkedő trendben.`,
    );
  }

  private stopParams(symbol: string, rules: SymbolRules, qty: number, stop: number, clientId: string) {
    const p: Record<string, string | number> = {
      symbol, side: "SELL", type: rules.stopType,
      quantity: floorTo(qty, rules.stepSize, rules.stepDecimals),
      stopPrice: floorTo(stop, rules.tickSize, rules.tickDecimals),
      newClientOrderId: clientId,
    };
    if (rules.stopType === "STOP_LOSS_LIMIT") {
      p.timeInForce = "GTC";
      p.price = floorTo(stop * 0.99, rules.tickSize, rules.tickDecimals); // 1% sáv a teljesüléshez
    }
    return p;
  }

  private async placeStop(symbol: string, qty: number, stop: number, seq: number): Promise<boolean> {
    const rules = await this.rules(symbol);
    const [pos] = (await this.db`SELECT * FROM positions WHERE symbol = ${symbol}`) as PositionRow[];
    const clientId = `tb-${symbol}-${pos.candle_open_time}-s${seq}`;
    try {
      await this.bn.placeOrder(this.stopParams(symbol, rules, qty, stop, clientId));
    } catch (e) {
      console.error(`Stop leadása sikertelen ${symbol}:`, (e as Error).message);
      return false;
    }
    await this.db`UPDATE positions SET stop_price = ${Number(floorTo(stop, rules.tickSize, rules.tickDecimals))},
      stop_client_id = ${clientId}, stop_seq = ${seq} WHERE symbol = ${symbol}`;
    return true;
  }

  // --- kilépés --------------------------------------------------------------
  private async recordExit(pos: PositionRow, exitQuoteNet: number, soldQty: number, reason: string, clientId: string): Promise<number> {
    const costPart = pos.cost_usdt * (soldQty / pos.qty);
    const pnl = exitQuoteNet - costPart;
    const exitPrice = exitQuoteNet / soldQty;
    const r = pos.risk_usdt > 0 ? pnl / pos.risk_usdt : 0;
    await this.db.begin(async (tx) => {
      await tx`INSERT INTO trades (symbol, entry_time, exit_time, entry_price, exit_price, qty, pnl, r_multiple, reason, exit_client_id)
        VALUES (${pos.symbol}, ${pos.entry_time}, now(), ${pos.entry_price}, ${exitPrice}, ${soldQty}, ${pnl}, ${r}, ${reason}, ${clientId})
        ON CONFLICT (exit_client_id) DO NOTHING`;
      await tx`DELETE FROM positions WHERE symbol = ${pos.symbol}`;
    });
    const label: Record<string, string> = {
      stop: "stop-loss / követő stop", kill_switch: "kill switch", kezi_zaras: "kézi zárás", stop_hiba: "stop leadási hiba",
      stop_vedelem: "biztonsági zárás (a stop nem aktiválódott)",
    };
    const realizedAll = await this.realizedTotal();
    const total = this.cfg.capital + realizedAll;
    await this.tg.send(
      `${pnl >= 0 ? "✅" : "🔴"} <b>ZÁRÁS – ${pos.symbol}: ${sign(pnl)} USDT</b>\n` +
        `Belépő: ${fmt(pos.entry_price)} → Kilépő: ${fmt(exitPrice)} (${r >= 0 ? "+" : ""}${r.toFixed(2)}R)\nOk: ${label[reason] ?? reason}\n` +
        `💰 Lezárt trade-ek összesen: ${fmt(this.cfg.capital, 0)} → <b>${fmt(total, 0)} USDT</b> (${sign((realizedAll / this.cfg.capital) * 100)}%)`,
      reason === "kill_switch" || reason === "stop_hiba",
    );
    return pnl;
  }

  private async fillQuote(symbol: string, order: any): Promise<{ quoteNet: number; qty: number }> {
    const qty = Number(order.executedQty);
    let quote = Number(order.cummulativeQuoteQty);
    try {
      const fills: any[] = order.fills ?? (await this.bn.tradesForOrder(symbol, order.orderId));
      const usdtFee = fills.filter((f) => f.commissionAsset === "USDT").reduce((s, f) => s + Number(f.commission), 0);
      quote -= usdtFee;
    } catch {
      quote *= 0.999; // díjbecslés, ha a részletek nem kérhetők le
    }
    return { quoteNet: quote, qty };
  }

  async marketExit(symbol: string, reason: string): Promise<void> {
    const [pos] = (await this.db`SELECT * FROM positions WHERE symbol = ${symbol} AND status = 'open'`) as PositionRow[];
    if (!pos) return;
    const rules = await this.rules(symbol);
    let partialQuote = 0, partialQty = 0;
    if (pos.stop_client_id) {
      await this.bn.cancelOrder(symbol, pos.stop_client_id);
      const st = await this.bn.getOrder(symbol, pos.stop_client_id);
      if (st && st.status === "FILLED") {
        const f = await this.fillQuote(symbol, st);
        await this.recordExit(pos, f.quoteNet, f.qty, "stop", pos.stop_client_id);
        return;
      }
      if (st && Number(st.executedQty) > 0) {
        // részben teljesült stop: a maradékot adjuk el, az eredményt együtt számoljuk
        const f = await this.fillQuote(symbol, st);
        partialQuote = f.quoteNet;
        partialQty = f.qty;
      }
    }
    const remaining = floorTo(pos.qty - partialQty, rules.stepSize, rules.stepDecimals);
    const clientId = `tb-${symbol}-${pos.candle_open_time}-x`;
    let quote = partialQuote, sold = partialQty;
    if (Number(remaining) > 0) {
      const order = await this.bn.placeOrder({ symbol, side: "SELL", type: "MARKET", quantity: remaining, newClientOrderId: clientId });
      const f = await this.fillQuote(symbol, order);
      quote += f.quoteNet;
      sold += f.qty;
    }
    await this.recordExit(pos, quote, sold, reason, clientId);
  }

  /** Félbemaradt belépések és a tőzsdei stopok állapotának egyeztetése. */
  async reconcile(): Promise<void> {
    for (const pos of await this.positions()) {
      if (pos.status === "opening") {
        const order = await this.bn.getOrder(pos.symbol, pos.entry_client_id);
        if (!order) {
          await this.db`DELETE FROM positions WHERE symbol = ${pos.symbol} AND status = 'opening'`;
        } else {
          await this.finishEntry(pos.symbol, order);
        }
        continue;
      }
      if (!pos.stop_client_id) {
        // nyitott pozíció stop nélkül: azonnal pótoljuk, vagy kiszállunk
        const price = await this.lastPrice(pos.symbol);
        const stop = pos.entry_price - pos.planned_stop_dist;
        if (price <= stop || !(await this.placeStop(pos.symbol, pos.qty, stop, pos.stop_seq + 1))) {
          await this.marketExit(pos.symbol, "stop_hiba");
        }
        continue;
      }
      const st = await this.bn.getOrder(pos.symbol, pos.stop_client_id);
      const price = await this.lastPrice(pos.symbol);
      if (st && st.status === "FILLED") {
        const f = await this.fillQuote(pos.symbol, st);
        await this.recordExit(pos, f.quoteNet, f.qty, "stop", pos.stop_client_id);
      } else if (!st || ["CANCELED", "EXPIRED", "REJECTED"].includes(st.status)) {
        // a stop eltűnt (pl. kézi törlés a tőzsdén): pótlás vagy kiszállás
        if (price <= pos.stop_price || !(await this.placeStop(pos.symbol, pos.qty, pos.stop_price, pos.stop_seq + 1))) {
          await this.marketExit(pos.symbol, "stop_vedelem");
        } else {
          await notifyError(this.db, this.tg, `stopgone:${pos.symbol}`, `⚠️ ${pos.symbol}: a stop-loss eltűnt a tőzsdéről, újra leadtam.`);
        }
      } else if (price < pos.stop_price * 0.995) {
        // az ár a stop alatt van, de a stop nem teljesült (pl. STOP_LOSS_LIMIT átugrotta)
        await this.marketExit(pos.symbol, "stop_vedelem");
      }
    }
  }

  /** Követő stop emelése a lezárt gyertya alapján (csak felfelé). */
  async trail(symbol: string, candle: Candle, sig: SignalState): Promise<void> {
    const [pos] = (await this.db`SELECT * FROM positions WHERE symbol = ${symbol} AND status = 'open'`) as PositionRow[];
    if (!pos || candle.openTime <= pos.candle_open_time) return;
    const rules = await this.rules(symbol);
    const highest = Math.max(pos.highest_close, candle.close);
    await this.db`UPDATE positions SET highest_close = ${highest} WHERE symbol = ${symbol}`;
    const newStop = Number(floorTo(highest - this.cfg.trailAtr * sig.atr, rules.tickSize, rules.tickDecimals));
    if (!(newStop > pos.stop_price * 1.001)) return;
    const price = await this.lastPrice(symbol);
    if (newStop >= price) {
      // az ár már az új stop alatt: azonnal zárunk (a backtest is így zárna a következő gyertyán)
      await this.marketExit(symbol, "stop");
      return;
    }
    const seq = pos.stop_seq + 1;
    const clientId = `tb-${symbol}-${pos.candle_open_time}-s${seq}`;
    let res;
    try {
      res = await this.bn.cancelReplace({
        ...this.stopParams(symbol, rules, pos.qty, newStop, clientId),
        cancelOrigClientOrderId: pos.stop_client_id,
      });
    } catch (e) {
      if (!(e instanceof UnknownOutcomeError)) throw e;
      const created = await this.bn.getOrder(symbol, clientId);
      res = { cancelOk: !!created, newOk: !!created };
    }
    if (res.cancelOk && res.newOk) {
      await this.db`UPDATE positions SET stop_price = ${newStop}, stop_client_id = ${clientId}, stop_seq = ${seq} WHERE symbol = ${symbol}`;
      return;
    }
    if (res.cancelOk && !res.newOk) {
      // a régi stop törölve, az új nem jött létre: a pozíció védtelen
      await this.db`UPDATE positions SET stop_client_id = NULL WHERE symbol = ${symbol}`;
      if (!(await this.placeStop(symbol, pos.qty, newStop, seq + 1))) await this.marketExit(symbol, "stop_hiba");
    }
    // cancelOk=false: a régi stop valószínűleg már teljesült – a reconcile rendezi
  }

  async closeAll(reason: string): Promise<void> {
    for (const p of await this.positions()) {
      if (p.status === "open") await this.marketExit(p.symbol, reason);
    }
  }
}

// ---------------------------------------------------------------------------
// Kézi kereskedés figyelése: a felhasználó saját trade-jei ugyanazon a számlán.
// Figyel és figyelmeztet; megbízást csak az automatikus stop-losshoz (as-) és az /elad kéréshez (ms-) ad le.
// ---------------------------------------------------------------------------
interface ManualPos {
  symbol: string;
  qty: number;
  cost: number;
  avg_price: number;
  realized: number;
  opened_at: Date;
  stop_state: "unchecked" | "ok" | "partial" | "none";
  risk_state: "ok" | "high";
  auto_stop_id: string | null;
  auto_stop_seq: number;
}

export interface ManualEvent {
  via?: "user" | "as" | "ms";
  autoStopId?: string | null;
  kind: "buy" | "sell";
  symbol: string;
  qty: number;
  price: number;
  value: number;
  pnl?: number;
  closedTotal?: number;
  untracked?: number;
  posQty: number;
  posAvg: number;
}

const fp = (n: number) => fmt(n, n >= 100 ? 2 : n >= 1 ? 4 : 6);
const pctc = (a: number, b: number) => ((a - b) / b) * 100;
const sgn = (n: number, d = 1) => (n >= 0 ? "+" : "−") + fmt(Math.abs(n), d) + "%";
const STOP_TYPES = new Set(["STOP_LOSS", "STOP_LOSS_LIMIT"]);
const MAX_WATCH = 15;

export class ManualWatcher {
  private rulesCache = new Map<string, SymbolRules>();
  private candleCache = new Map<string, Candle[]>();
  private auto = true;

  constructor(
    private db: SQL,
    private bn: Binance,
    private tg: Telegram,
    private cfg: Config,
    private prices: Map<string, number>,
  ) {}

  async watchlist(): Promise<string[]> {
    const stored = await kvGet<string[] | null>(this.db, "manual_symbols", null);
    const list = (stored ?? this.cfg.manualSymbols).filter((s) => SYMBOL_RE.test(s));
    return [...new Set(list)].slice(0, MAX_WATCH);
  }
  async capital(): Promise<number> {
    const v = await kvGet<number | null>(this.db, "manual_capital", null);
    return typeof v === "number" && v > 0 ? v : this.cfg.manualCapital;
  }
  private async rules(symbol: string): Promise<SymbolRules> {
    let r = this.rulesCache.get(symbol);
    if (!r) {
      r = await this.bn.rules(symbol);
      this.rulesCache.set(symbol, r);
    }
    return r;
  }
  private async price(symbol: string): Promise<number> {
    let p = this.prices.get(symbol);
    if (p === undefined) {
      p = await this.bn.price(symbol);
      this.prices.set(symbol, p);
    }
    return p;
  }
  /** A stratégia szerinti javasolt stop és az 1%-os kockázathoz tartozó max méret. */
  private async suggestion(symbol: string, capital: number): Promise<{ stop: number; qty: number; value: number } | null> {
    try {
      let c = this.candleCache.get(symbol);
      if (!c) {
        c = await this.bn.closedCandles(symbol);
        this.candleCache.set(symbol, c);
      }
      const sig = evaluate(c, this.cfg);
      const price = await this.price(symbol);
      const dist = this.cfg.stopAtr * sig.atr;
      if (!(dist > 0) || dist >= price) return null;
      let qty = (capital * this.cfg.riskPerTrade) / dist;
      if (qty * price > capital) qty = capital / price;
      return { stop: price - dist, qty, value: qty * price };
    } catch (e) {
      console.error(`Javaslat számítása sikertelen ${symbol}:`, (e as Error).message);
      return null;
    }
  }

  async positions(): Promise<ManualPos[]> {
    return (await this.db`SELECT * FROM manual_positions ORDER BY symbol`) as ManualPos[];
  }

  async autostopEnabled(): Promise<boolean> {
    return await kvGet<boolean>(this.db, "autostop", true);
  }

  /** Egy futás: /elad kérések, új kézi kötések feldolgozása, majd stop/kockázat ellenőrzés. */
  async run(botSymbols: Set<string>): Promise<void> {
    const capital = await this.capital();
    this.auto = await this.autostopEnabled();
    await this.processSellRequests();
    for (const symbol of await this.watchlist()) {
      try {
        const events = await this.syncSymbol(symbol);
        for (const ev of events) await this.notify(ev, capital, botSymbols);
      } catch (e) {
        if (e instanceof BinanceError && (e.code === -1121 || e.code === -1100)) {
          const list = (await this.watchlist()).filter((s) => s !== symbol);
          await kvSet(this.db, "manual_symbols", list);
          await this.tg.send(`ℹ️ A(z) ${symbol} piac nem létezik a Binance-en, levettem a figyelőlistáról.`);
          continue;
        }
        throw e;
      }
    }
    await this.checkProtection(capital, botSymbols);
  }

  /** Új kötések lekérése kurzorral; az első futás csak beállítja a kurzort (a régi kötéseket nem jelzi). */
  async syncSymbol(symbol: string): Promise<ManualEvent[]> {
    const curKey = `mcur:${symbol}`;
    const cursor = await kvGet<number | null>(this.db, curKey, null);
    if (cursor === null) {
      const recent = await this.bn.myTrades(symbol, { limit: 1000 });
      const maxId = recent.reduce((m: number, t: any) => Math.max(m, Number(t.id)), 0);
      await kvSet(this.db, curKey, maxId);
      return [];
    }
    const trades = await this.bn.myTrades(symbol, { fromId: cursor + 1, limit: 1000 });
    if (!trades.length) return [];
    const byOrder = new Map<number, any[]>();
    for (const t of trades) {
      const id = Number(t.orderId);
      if (!byOrder.has(id)) byOrder.set(id, []);
      byOrder.get(id)!.push(t);
    }
    const events: ManualEvent[] = [];
    for (const [orderId, fills] of [...byOrder.entries()].sort((a, b) => a[0] - b[0])) {
      const order = await this.bn.getOrderById(symbol, orderId);
      const cid = String(order?.clientOrderId ?? "");
      const isBot = cid.startsWith("tb-");
      const via: ManualEvent["via"] = cid.startsWith("as-") ? "as" : cid.startsWith("ms-") ? "ms" : "user";
      const ev = await this.applyFills(symbol, fills, isBot);
      if (ev) {
        ev.via = via;
        // a pozíció lezárult: a megmaradt automatikus stopot töröljük, különben más coinodat adná el
        if (ev.closedTotal !== undefined && ev.autoStopId) {
          await this.bn.cancelOrder(symbol, ev.autoStopId).catch((e) => console.error("Auto stop törlése:", e.message));
        }
        events.push(ev);
      }
    }
    const maxId = trades.reduce((m: number, t: any) => Math.max(m, Number(t.id)), cursor);
    await kvSet(this.db, curKey, maxId);
    return events;
  }

  /** Kötések könyvelése egy tranzakcióban; minden trade-id csak egyszer számít (retry-biztos). */
  private async applyFills(symbol: string, fills: any[], isBot: boolean): Promise<ManualEvent | null> {
    const rules = await this.rules(symbol);
    const price = await this.price(symbol);
    let event: ManualEvent | null = null;
    await this.db.begin(async (tx) => {
      const fresh: any[] = [];
      for (const f of fills) {
        const ins = await tx`INSERT INTO manual_fills (symbol, trade_id, is_bot) VALUES (${symbol}, ${Number(f.id)}, ${isBot})
          ON CONFLICT DO NOTHING RETURNING trade_id`;
        if (ins.length) fresh.push(f);
      }
      if (isBot || !fresh.length) return;

      let qty = 0, quote = 0;
      const isBuy = Boolean(fresh[0].isBuyer);
      for (const f of fresh) {
        const q = Number(f.qty), v = Number(f.quoteQty), c = Number(f.commission);
        if (isBuy) {
          qty += q - (f.commissionAsset === rules.base ? c : 0);
          quote += v + (f.commissionAsset === "USDT" ? c : 0);
        } else {
          qty += q;
          quote += v - (f.commissionAsset === "USDT" ? c : 0);
        }
      }
      if (!(qty > 0)) return;
      const [pos] = (await tx`SELECT * FROM manual_positions WHERE symbol = ${symbol} FOR UPDATE`) as ManualPos[];

      if (isBuy) {
        if (!pos) {
          await tx`INSERT INTO manual_positions (symbol, qty, cost, avg_price) VALUES (${symbol}, ${qty}, ${quote}, ${quote / qty})`;
          event = { kind: "buy", symbol, qty, price: quote / qty, value: quote, posQty: qty, posAvg: quote / qty };
        } else {
          const nq = pos.qty + qty, nc = pos.cost + quote;
          // utánvétel: új kockázat, a stop-ellenőrzés újraindul
          await tx`UPDATE manual_positions SET qty = ${nq}, cost = ${nc}, avg_price = ${nc / nq},
            stop_state = 'unchecked', risk_state = 'ok', opened_at = now() WHERE symbol = ${symbol}`;
          event = { kind: "buy", symbol, qty, price: quote / qty, value: quote, posQty: nq, posAvg: nc / nq };
        }
        return;
      }

      // eladás: csak a figyelés óta vett mennyiség eredményét számoljuk
      const tracked = pos?.qty ?? 0;
      const sold = Math.min(qty, tracked);
      const untracked = qty - sold;
      let pnl = 0;
      if (pos && sold > 0) {
        const proceeds = quote * (sold / qty);
        const costPart = pos.cost * (sold / pos.qty);
        pnl = proceeds - costPart;
        const nq = pos.qty - sold, nc = pos.cost - costPart, realized = pos.realized + pnl;
        const dust = nq < rules.minQty || nq * price < Math.max(rules.minNotional, 1);
        if (dust) {
          await tx`INSERT INTO manual_closed (symbol, opened_at, pnl) VALUES (${symbol}, ${pos.opened_at}, ${realized})`;
          await tx`DELETE FROM manual_positions WHERE symbol = ${symbol}`;
          event = { kind: "sell", symbol, qty, price: quote / qty, value: quote, pnl, closedTotal: realized, untracked, posQty: 0, posAvg: pos.avg_price, autoStopId: pos.auto_stop_id };
        } else {
          await tx`UPDATE manual_positions SET qty = ${nq}, cost = ${nc}, realized = ${realized} WHERE symbol = ${symbol}`;
          event = { kind: "sell", symbol, qty, price: quote / qty, value: quote, pnl, untracked, posQty: nq, posAvg: pos.avg_price };
        }
      } else {
        event = { kind: "sell", symbol, qty, price: quote / qty, value: quote, untracked, posQty: 0, posAvg: 0 };
      }
    });
    return event as ManualEvent | null;
  }

  private async notify(ev: ManualEvent, capital: number, botSymbols: Set<string>): Promise<void> {
    if (ev.kind === "buy") {
      const sug = await this.suggestion(ev.symbol, capital);
      const lines = [
        `🟦 <b>KÉZI VÉTEL – ${ev.symbol}</b>`,
        `Mennyiség: ${ev.qty} @ ${fmt(ev.price)}`,
        `Érték: ${fmt(ev.value)} USDT`,
      ];
      if (ev.posQty > ev.qty) lines.push(`Teljes kézi pozíció: ${+ev.posQty.toFixed(8)} (átlagár: ${fmt(ev.posAvg)})`);
      if (sug) {
        const pct = ((ev.price - sug.stop) / ev.price) * 100;
        lines.push(
          "",
          `Javasolt stop-loss (2×ATR): <b>${fmt(sug.stop)}</b> (−${fmt(pct, 1)}%)`,
          `1%-os kockázathoz max: ${+sug.qty.toFixed(6)} (~${fmt(sug.value)} USDT, ${fmt(capital, 0)} USDT tőkével)`,
        );
        if (ev.posQty * ev.posAvg > sug.value * 1.05) lines.push(`⚠️ A pozíciód nagyobb, mint amit az 1%-os szabály enged.`);
      }
      if (botSymbols.has(ev.symbol)) lines.push("", "⚠️ A bot is nyitva van ezen a piacon – ez dupla kockázat.");
      lines.push("", this.auto
        ? "🛡 A stop-losst automatikusan beteszem helyetted (külön üzenetben jön)."
        : "⏱ 5 perc múlva ellenőrzöm, tettél-e stop-losst.");
      await this.tg.send(lines.join("\n"));
      return;
    }
    const title = ev.via === "as"
      ? `🛡 <b>STOP-LOSS KIÜTÖTT – ${ev.symbol}</b>\nAz ár elérte a stop szintet, a Binance automatikusan eladta, hogy ne veszíts többet.`
      : ev.via === "ms"
        ? `🟧 <b>ELADVA A KÉRÉSEDRE – ${ev.symbol}</b>`
        : `🟧 <b>KÉZI ELADÁS – ${ev.symbol}</b>`;
    const lines = [title, `Mennyiség: ${+ev.qty.toFixed(8)} @ ${fmt(ev.price)}`];
    if (ev.pnl !== undefined && ev.qty - (ev.untracked ?? 0) > 0) lines.push(`Eredmény ezen a részen: <b>${sign(ev.pnl)} USDT</b>`);
    if (ev.closedTotal !== undefined) {
      lines.push(`${ev.closedTotal >= 0 ? "✅" : "🔴"} A kézi pozíció lezárva. Összes eredmény: <b>${sign(ev.closedTotal)} USDT</b>`);
    } else if (ev.posQty > 0) {
      lines.push(`Maradék: ${+ev.posQty.toFixed(8)}`);
    }
    if ((ev.untracked ?? 0) > 1e-12) {
      lines.push(`ℹ️ ${+ev.untracked!.toFixed(8)} db a figyelés indulása előtti állományból – ennek eredményét nem számolom.`);
    }
    await this.tg.send(lines.join("\n"));
  }

  private stopParams(rules: SymbolRules, symbol: string, qty: string, stop: number, clientId: string) {
    const p: Record<string, string | number> = {
      symbol, side: "SELL", type: rules.stopType, quantity: qty,
      stopPrice: floorTo(stop, rules.tickSize, rules.tickDecimals), newClientOrderId: clientId,
    };
    if (rules.stopType === "STOP_LOSS_LIMIT") {
      p.timeInForce = "GTC";
      p.price = floorTo(stop * 0.99, rules.tickSize, rules.tickDecimals); // 1% sáv a teljesüléshez
    }
    return p;
  }

  /**
   * Automatikus stop-loss: a saját stopjaiddal nem fedett mennyiségre, a stratégia szerinti
   * (2×ATR) szinten. Utánvételnél nagyobbra, részeladásnál kisebbre cseréli; ha a te stopod
   * mindent fed, a sajátját törli. Visszaadja, hogy most tett-e be új stopot.
   */
  private async ensureAutoStop(pos: ManualPos, orders: any[], userCovered: number, capital: number): Promise<{ qty: number; stop: number } | null> {
    const rules = await this.rules(pos.symbol);
    const price = await this.price(pos.symbol);
    const ours = pos.auto_stop_id ? orders.find((o: any) => o.clientOrderId === pos.auto_stop_id) : undefined;
    if (pos.auto_stop_id && !ours) {
      // a stopunk már nincs nyitva: ha (részben) teljesült, a következő szinkron rendezi – most nem nyúlunk hozzá
      const st = await this.bn.getOrder(pos.symbol, pos.auto_stop_id);
      if (st && Number(st.executedQty) > 0) return null;
    }
    const ourQty = ours ? Number(ours.origQty) - Number(ours.executedQty) : 0;
    const need = Number(floorTo(Math.max(0, pos.qty - userCovered), rules.stepSize, rules.stepDecimals));
    const minVal = Math.max(rules.minNotional, 5);

    if (need < rules.minQty || need * price < minVal) {
      // nincs mit védeni (vagy a te stopod mindent fed): a miénk felesleges
      if (ours) await this.bn.cancelOrder(pos.symbol, pos.auto_stop_id!);
      if (pos.auto_stop_id) await this.db`UPDATE manual_positions SET auto_stop_id = NULL WHERE symbol = ${pos.symbol}`;
      return null;
    }
    if (ours && Math.abs(ourQty - need) <= rules.stepSize * 1.5) return null; // a meglévő stop rendben van

    let stop: number | null = null;
    if (ours && need < ourQty && Number(ours.stopPrice) < price) stop = Number(ours.stopPrice); // részeladás: a szint marad
    if (stop === null) stop = (await this.suggestion(pos.symbol, capital))?.stop ?? null;
    if (stop === null || !(stop < price)) throw new Error("nem számolható érvényes stop szint");

    if (ours) await this.bn.cancelOrder(pos.symbol, pos.auto_stop_id!);
    const free = await this.bn.freeBalance(rules.base);
    const qty = floorTo(Math.min(need, free), rules.stepSize, rules.stepDecimals);
    if (Number(qty) < rules.minQty || Number(qty) * stop < minVal) {
      await this.db`UPDATE manual_positions SET auto_stop_id = NULL WHERE symbol = ${pos.symbol}`;
      throw new Error(`nincs szabad ${rules.base} a stophoz (le van foglalva egy másik megbízásban?)`);
    }
    const seq = pos.auto_stop_seq + 1;
    const cid = `as-${pos.symbol}-${Math.floor(new Date(pos.opened_at).getTime() / 1000)}-${seq}`;
    // a szándékot a megbízás ELŐTT rögzítjük, így crash/időtúllépés után is megtaláljuk
    await this.db`UPDATE manual_positions SET auto_stop_id = ${cid}, auto_stop_seq = ${seq} WHERE symbol = ${pos.symbol}`;
    await this.bn.placeOrder(this.stopParams(rules, pos.symbol, qty, stop, cid));
    return { qty: Number(qty), stop: Number(floorTo(stop, rules.tickSize, rules.tickDecimals)) };
  }

  /** /elad kérések végrehajtása: automatikus stop törlése, majd piaci eladás (idempotens clientOrderId-val). */
  private async processSellRequests(): Promise<void> {
    const reqs = await kvGet<Record<string, string>>(this.db, "sell_req", {});
    // atomi módosítások: a webhook közben új kérést tehet be
    const finish = async (symbol: string) => {
      await this.db`UPDATE kv SET value = value - ${symbol}::text, updated_at = now() WHERE key = 'sell_req'`;
    };
    for (const [symbol, prevCid] of Object.entries(reqs)) {
      try {
        if (prevCid && (await this.bn.getOrder(symbol, prevCid))) { await finish(symbol); continue; } // már elküldtük
        const [pos] = (await this.db`SELECT * FROM manual_positions WHERE symbol = ${symbol}`) as ManualPos[];
        if (!pos) {
          await this.tg.send(`ℹ️ ${symbol}: nincs nyitott kézi pozíciód, nincs mit eladni.`);
          await finish(symbol);
          continue;
        }
        const rules = await this.rules(symbol);
        if (pos.auto_stop_id) await this.bn.cancelOrder(symbol, pos.auto_stop_id);
        const free = await this.bn.freeBalance(rules.base);
        const qty = floorTo(Math.min(pos.qty, free), rules.stepSize, rules.stepDecimals);
        if (Number(qty) < rules.minQty) {
          await this.tg.send(
            `⚠️ ${symbol}: nem tudom eladni, mert a coin le van foglalva egy másik megbízásban (pl. egy általad beállított stop-loss).\n` +
              `A Binance-en az <b>Open Orders</b> alatt töröld, és írd újra: /elad ${symbol.replace("USDT", "")}`,
          );
          await finish(symbol);
          continue;
        }
        const cid = `ms-${symbol}-${Math.floor(Date.now() / 1000)}`;
        await this.db`UPDATE kv SET value = jsonb_set(value, ARRAY[${symbol}::text], to_jsonb(${cid}::text)), updated_at = now() WHERE key = 'sell_req'`;
        await this.bn.placeOrder({ symbol, side: "SELL", type: "MARKET", quantity: qty, newClientOrderId: cid });
        await this.db`UPDATE manual_positions SET auto_stop_id = NULL WHERE symbol = ${symbol}`;
        await finish(symbol);
      } catch (e) {
        if (e instanceof UnknownOutcomeError) continue; // a kérés marad, a következő futás tisztázza
        await this.tg.send(`⚠️ ${symbol} eladása nem sikerült: ${esc((e as Error).message).slice(0, 200)}`, true);
        await finish(symbol);
      }
    }
  }

  /** Védelem ellenőrzése: automatikus stop (ha be van kapcsolva), majd figyelmeztetés, ha mégis védtelen. Csak állapotváltáskor szól. */
  async checkProtection(capital: number, botSymbols: Set<string>): Promise<void> {
    const rows = (await this.db`SELECT *, (opened_at <= now() - interval '4 minutes') AS due FROM manual_positions`) as (ManualPos & { due: boolean })[];
    for (const pos of rows) {
      if (!this.auto && !pos.due) continue;
      let orders = await this.bn.openOrders(pos.symbol);
      const isStop = (o: any) => o.side === "SELL" && STOP_TYPES.has(o.type) && !String(o.clientOrderId ?? "").startsWith("tb-");
      const isOurs = (o: any) => String(o.clientOrderId ?? "").startsWith("as-");

      let placed: { qty: number; stop: number } | null = null;
      if (this.auto) {
        let userCovered = 0;
        for (const o of orders) if (isStop(o) && !isOurs(o)) userCovered += Math.max(0, Number(o.origQty) - Number(o.executedQty));
        try {
          placed = await this.ensureAutoStop(pos, orders, userCovered, capital);
        } catch (e) {
          console.error(`Auto stop hiba ${pos.symbol}:`, (e as Error).message);
          await notifyError(this.db, this.tg, `autostop:${pos.symbol}`,
            `⚠️ <b>${pos.symbol}</b>: nem sikerült automatikusan beállítani a stop-losst (${esc((e as Error).message).slice(0, 150)}). 5 perc múlva újrapróbálom.`);
        }
        orders = await this.bn.openOrders(pos.symbol); // a friss állapot alapján számolunk tovább
        if (placed) {
          const loss = Math.max(0, (pos.avg_price - placed.stop) * placed.qty);
          await this.tg.send(
            `🛡 <b>Stop-loss beállítva – ${pos.symbol}</b>\n` +
              `Ha az ár <b>${fmt(placed.stop)}</b> alá esik (${sgn(pctc(placed.stop, await this.price(pos.symbol)))}), a Binance automatikusan eladja: ${placed.qty} db.\n` +
              (loss > 0 ? `Ennyit veszíthetsz legfeljebb: ~${fmt(loss)} USDT\n` : "") +
              `Ha előbb el akarod adni: /elad ${pos.symbol.replace("USDT", "")}`,
          );
        }
      }

      const stops = orders.filter(isStop);
      let covered = 0, risk = 0;
      for (const o of stops) {
        const q = Math.max(0, Number(o.origQty) - Number(o.executedQty));
        covered += q;
        risk += Math.max(0, pos.avg_price - Number(o.stopPrice)) * Math.min(q, pos.qty);
      }
      const uncovered = Math.max(0, pos.qty - covered);
      risk += uncovered * pos.avg_price;
      const stopState: ManualPos["stop_state"] = covered >= pos.qty * 0.95 ? "ok" : covered > 0 ? "partial" : "none";
      const riskState: ManualPos["risk_state"] = stopState === "ok" && risk > capital * this.cfg.riskPerTrade * 1.05 ? "high" : "ok";
      const value = pos.qty * (await this.price(pos.symbol));

      if (stopState !== pos.stop_state && (pos.due || this.auto)) {
        if (stopState === "none" || stopState === "partial") {
          const sug = await this.suggestion(pos.symbol, capital);
          const what = stopState === "none"
            ? `${+pos.qty.toFixed(8)} db (~${fmt(value)} USDT) védelem nélkül van.`
            : `a pozíciónak csak ${fmt((covered / pos.qty) * 100, 0)}%-a van stop-losszal védve.`;
          await this.tg.send(
            `⚠️ <b>NINCS STOP-LOSS – ${pos.symbol}</b>\nA kézi pozíciód: ${what}\n` +
              (sug ? `Javasolt stop: <b>${fmt(sug.stop)}</b> (2×ATR a mostani ártól).\n` : "") +
              (this.auto ? "Automatikusan újrapróbálom." : `Tegyél be egy Stop-Limit eladást a Binance-en, vagy kapcsold be: /autostop be`),
            true,
          );
        } else if (stopState === "ok" && pos.stop_state !== "unchecked" && !placed) {
          await this.tg.send(`✅ ${pos.symbol}: a kézi pozíciód stop-lossa rendben.`);
        }
      }
      if (riskState === "high" && pos.risk_state !== "high") {
        const sug = await this.suggestion(pos.symbol, capital);
        await this.tg.send(
          `⚠️ <b>NAGY KOCKÁZAT – ${pos.symbol}</b>\nHa a stop kiüt: <b>−${fmt(risk)} USDT</b> = a tőkéd ${fmt((risk / capital) * 100, 1)}%-a ` +
            `(${fmt(capital, 0)} USDT tőkével számolva; a szabály 1%).\n` +
            (sug ? `1%-hoz max ${+sug.qty.toFixed(6)} db.` : ""),
          true,
        );
      }
      if (stopState !== pos.stop_state || riskState !== pos.risk_state) {
        await this.db`UPDATE manual_positions SET stop_state = ${stopState}, risk_state = ${riskState} WHERE symbol = ${pos.symbol}`;
      }
    }
  }

  async summary(): Promise<{ open: any[]; realizedTotal: number; closed24: { n: number; pnl: number } }> {
    const open = [];
    for (const p of await this.positions()) {
      const last = await this.price(p.symbol).catch(() => p.avg_price);
      open.push({ symbol: p.symbol, qty: p.qty, avg: p.avg_price, last, pnl: p.qty * last - p.cost, stop: p.stop_state, risk: p.risk_state });
    }
    const tot = await this.db`SELECT COALESCE(SUM(pnl), 0) AS s FROM manual_closed`;
    const c24 = await this.db`SELECT COUNT(*)::int AS n, COALESCE(SUM(pnl), 0) AS s FROM manual_closed WHERE closed_at >= now() - interval '24 hours'`;
    const openRealized = (await this.positions()).reduce((s, p) => s + p.realized, 0);
    return { open, realizedTotal: Number(tot[0].s) + openRealized, closed24: { n: c24[0].n, pnl: Number(c24[0].s) } };
  }
}

const STOP_LABEL: Record<string, string> = { ok: "stop ✅", partial: "részben védett ⚠️", none: "NINCS STOP ⚠️", unchecked: "ellenőrzés alatt" };
export function manualLines(open: any[]): string {
  return open.length
    ? open.map((p) => `• ${p.symbol}: ${sign(p.pnl)} USDT (átlagár ${fmt(p.avg)}, ${STOP_LABEL[p.stop] ?? p.stop})`).join("\n")
    : "• nincs nyitott kézi pozíció";
}

// ---------------------------------------------------------------------------
// Piaci hírfolyam: 4 óránkénti összefoglaló + riasztások (csak olvas, nem kereskedik)
// ---------------------------------------------------------------------------
export const MOVE_ALERT_PCT = 3;
export const NEAR_BREAKOUT_PCT = 1;

interface FeedRow {
  symbol: string;
  price: number;
  ch4h: number;
  ch24h: number;
  up: boolean;
  level: number;
  dist: number; // %-ban: mennyivel van a kitörési szint az ár felett (negatív = az ár már felette)
  lastOpen: number;
  nextClose: number;
}

export class MarketFeed {
  constructor(
    private db: SQL,
    private bn: Binance,
    private tg: Telegram,
    private cfg: Config,
    private prices: Map<string, number>,
  ) {}

  private async price(symbol: string): Promise<number> {
    let p = this.prices.get(symbol);
    if (p === undefined) {
      p = await this.bn.price(symbol);
      this.prices.set(symbol, p);
    }
    return p;
  }

  async run(symbols: string[], botSymbols: Set<string>, manualOpen: number): Promise<void> {
    if (await kvGet<boolean>(this.db, "feed_off", false)) return;
    const rows: FeedRow[] = [];
    const now = Date.now();
    for (const symbol of symbols) {
      try {
        const c = await this.bn.closedCandles(symbol);
        if (c.length < this.cfg.emaFilter + this.cfg.lookback + 7) continue;
        const sig = evaluate(c, this.cfg);
        const price = await this.price(symbol);
        const last = c[c.length - 1];
        const level = Math.max(...c.slice(-this.cfg.lookback).map((k) => k.high));
        const row: FeedRow = {
          symbol, price,
          ch4h: pctc(last.close, c[c.length - 2].close),
          ch24h: pctc(price, c[c.length - 7].close),
          up: last.close > sig.emaFilter,
          level, dist: pctc(level, price),
          lastOpen: last.openTime, nextClose: last.closeTime + 1 + 4 * 3_600_000,
        };
        rows.push(row);

        // ⚡ nagy mozgás 1 óra alatt (piaconként legfeljebb óránként egyszer)
        const hourAgo = await this.bn.priceHourAgo(symbol);
        const ch1h = pctc(price, hourAgo);
        if (Math.abs(ch1h) >= MOVE_ALERT_PCT) {
          const key = `alert:move:${symbol}`;
          if (now - (await kvGet<number>(this.db, key, 0)) >= 3_600_000) {
            await kvSet(this.db, key, now);
            const extra = botSymbols.has(symbol) ? "\nA botnak nyitott pozíciója van ezen a piacon (a stop-loss a tőzsdén védi)." : "";
            await this.tg.send(
              `⚡ <b>${symbol.replace("USDT", "")} ${ch1h >= 0 ? "emelkedés" : "esés"}: ${sgn(ch1h)} 1 óra alatt</b>\n` +
                `${fp(hourAgo)} → ${fp(price)} USDT${extra}`,
            );
          }
        }

        // 🎯 közel a kitöréshez (gyertyánként egyszer), csak emelkedő trendben
        if (row.up && row.dist <= NEAR_BREAKOUT_PCT && row.dist >= -3) {
          const key = `alert:near:${symbol}`;
          if ((await kvGet<number>(this.db, key, 0)) !== last.openTime) {
            await kvSet(this.db, key, last.openTime);
            const where = row.dist > 0
              ? `Az ár ${fmt(row.dist, 1)}%-ra van a vételi szinttől.`
              : `Az ár már a vételi szint fölött jár (${sgn(-row.dist)}).`;
            const who = this.cfg.symbols.includes(symbol)
              ? "Ha így zár, a bot magától belép."
              : "Ha így zár, a stratégia szerint vételi jelzés lenne (ezen a piacon a bot nem kereskedik).";
            await this.tg.send(
              `🎯 <b>${symbol.replace("USDT", "")} közel a kitöréshez</b>\n` +
                `Vételi szint: <b>${fp(level)}</b> · Ár most: ${fp(price)}\n${where}\n` +
                `Döntés a 4 órás gyertya zárásakor: ${hhmm(row.nextClose)}. ${who}`,
            );
          }
        }
      } catch (e) {
        if (e instanceof BinanceError && (e.code === -1121 || e.code === -1100)) continue;
        console.error(`Hírfolyam hiba ${symbol}:`, (e as Error).message);
      }
    }
    if (!rows.length) return;

    // 📊 összefoglaló minden új 4 órás zárás után
    const lastOpen = Math.max(...rows.map((r) => r.lastOpen));
    if ((await kvGet<number>(this.db, "feed:last", 0)) >= lastOpen) return;
    await kvSet(this.db, "feed:last", lastOpen);
    const lines = rows.map((r) => {
      const name = r.symbol.replace("USDT", "");
      const head = `<b>${name}</b> ${fp(r.price)} · 4h ${sgn(r.ch4h)} · 24h ${sgn(r.ch24h)}`;
      const tail = r.up
        ? `   ↗ emelkedő · vételi szint: ${fp(r.level)} (${r.dist > 0 ? "+" + fmt(r.dist, 1) + "%" : "áttörve"})`
        : "   ↘ csökkenő · a stratégia most nem vesz";
      return `${head}\n${tail}`;
    });
    const botLine = botSymbols.size ? `🤖 Bot: ${[...botSymbols].map((s) => s.replace("USDT", "")).join(", ")} nyitva` : "🤖 Bot: nincs nyitott pozíció";
    const youLine = manualOpen ? `👤 Te: ${manualOpen} kézi pozíció` : "👤 Te: nincs kézi pozíció";
    await this.tg.send(
      `📊 <b>Piaci összefoglaló</b> (4 órás zárás)\n\n${lines.join("\n")}\n\n${botLine} · ${youLine}\n` +
        `Következő: ${hhmm(rows[0].nextClose)} · Kikapcsolás: /hirek ki`,
    );
  }
}

// ---------------------------------------------------------------------------
// Riportok és pillanatkép
// ---------------------------------------------------------------------------
async function snapshot(db: SQL, trader: Trader, cfg: Config, prices: Map<string, number>, manual: any): Promise<any> {
  const { equity } = await trader.equity();
  const positions = (await trader.positions()).filter((p) => p.status === "open").map((p) => {
    const last = prices.get(p.symbol) ?? p.entry_price;
    return {
      symbol: p.symbol, qty: p.qty, entry: p.entry_price, stop: p.stop_price, last,
      pnl: p.qty * last - p.cost_usdt, entryTime: p.entry_time,
    };
  });
  const snap = {
    updatedAt: Date.now(), equity, capital: cfg.capital, positions,
    realized: await trader.realizedTotal(),
    peak: await kvGet<number>(db, "peak_equity", cfg.capital),
    paused: await kvGet<boolean>(db, "paused", false),
    halted: await kvGet<boolean>(db, "halted", false),
    manual,
  };
  await kvSet(db, "snapshot", snap);
  return snap;
}

async function reports(db: SQL, tg: Telegram, snap: any): Promise<void> {
  const { date, hour } = budapestParts(Date.now());
  const mode = snap.halted ? "🛑 LEÁLLT (kill switch)" : snap.paused ? "⏸ szünetel" : "▶️ fut";
  const posLines = snap.positions.length
    ? snap.positions.map((p: any) => `• ${p.symbol}: ${sign(p.pnl)} USDT (stop: ${fmt(p.stop)})`).join("\n")
    : "• nincs nyitott pozíció";
  const total = snap.equity - snap.capital;
  const money = `💰 <b>${fmt(snap.capital, 0)} → ${fmt(snap.equity, 0)} USDT (${sign((total / snap.capital) * 100)}%)</b>`;

  const m = snap.manual;
  const manualBlock = m
    ? `\n\n<b>Te (kézi trade-ek)</b>\n${manualLines(m.open)}\nLezárt kézi eredmény összesen: ${sign(m.realizedTotal)} USDT`
    : "";
  if (hour >= 8 && !(await kvGet(db, `report:morning:${date}`, false))) {
    await kvSet(db, `report:morning:${date}`, true);
    await tg.send(
      `☀️ <b>Reggel</b>\n${money}\nNyitott pozíciók:\n${posLines}\nÜzemmód: ${mode}${manualBlock}`,
    );
  }
  if (hour >= 20 && !(await kvGet(db, `report:evening:${date}`, false))) {
    await kvSet(db, `report:evening:${date}`, true);
    const today = await db`SELECT symbol, pnl, r_multiple FROM trades
      WHERE exit_time >= now() - interval '24 hours' ORDER BY exit_time`;
    const tLines = today.length
      ? today.map((t: any) => `• ${t.symbol}: ${sign(Number(t.pnl))} USDT (${Number(t.r_multiple).toFixed(2)}R)`).join("\n")
      : "• ma nem zárult trade";
    const stats = await db`SELECT COUNT(*)::int AS n, COALESCE(AVG(CASE WHEN pnl > 0 THEN 1 ELSE 0 END), 0) AS w FROM trades`;
    const dd = snap.peak > 0 ? (snap.equity / snap.peak - 1) * 100 : 0;
    await tg.send(
      `🌙 <b>Este</b>\n${money}\nVisszaesés a csúcstól: ${fmt(dd, 1)}%\n\n` +
        `<b>Utolsó 24 óra zárásai</b>\n${tLines}\n\n<b>Nyitott pozíciók</b>\n${posLines}\n\n` +
        `Összes trade: ${stats[0].n}, nyerő arány: ${fmt(Number(stats[0].w) * 100, 0)}% (backtest: ~34%)\nÜzemmód: ${mode}` +
        (m ? `${manualBlock}\nUtolsó 24 óra kézi zárásai: ${m.closed24.n} db, ${sign(m.closed24.pnl)} USDT` : ""),
    );
  }
}

// ---------------------------------------------------------------------------
// Egy futás
// ---------------------------------------------------------------------------
export async function runOnce(cfg: Config, db: SQL): Promise<void> {
  const holder = randomUUID();
  await migrate(db);
  if (!(await acquireLease(db, holder))) {
    console.log("Másik futás aktív, kihagyom.");
    return;
  }
  const tg = new Telegram(cfg);
  const bn = new Binance(cfg);
  try {
    await ensureTelegramSetup(db, cfg, tg).catch((e) => console.error("Telegram beállítás:", e.message));
    await bn.syncTime();
    const prices = new Map<string, number>();
    for (const s of cfg.symbols) prices.set(s, await bn.price(s));
    const trader = new Trader(db, bn, tg, cfg, prices);

    await trader.reconcile();

    // felhasználói kérés: mindent zár
    if (await kvGet(db, "close_all_requested", false)) {
      await trader.closeAll("kezi_zaras");
      await kvSet(db, "close_all_requested", false);
      await kvSet(db, "paused", true);
      await tg.send("⏹ Minden pozíciót lezártam, a bot szünetel. Újraindítás: /folytat", true);
    }

    // kill switch és napi limit
    let { equity } = await trader.equity();
    let peak = await kvGet<number>(db, "peak_equity", cfg.capital);
    if (equity > peak) {
      peak = equity;
      await kvSet(db, "peak_equity", peak);
    }
    let halted = await kvGet<boolean>(db, "halted", false);
    if (!halted && equity < peak * (1 - cfg.killSwitchDd)) {
      await trader.closeAll("kill_switch");
      halted = true;
      await kvSet(db, "halted", true);
      ({ equity } = await trader.equity());
      await tg.send(
        `🛑 <b>KILL SWITCH</b>\nA tőke ${fmt(cfg.killSwitchDd * 100, 0)}%-nál többet esett a csúcsról (${fmt(peak)} → ${fmt(equity)} USDT).\n` +
          `Minden pozíciót lezártam, a bot leállt. Átnézés után újraindítás: <code>/folytat IGEN</code>`,
        true,
      );
    }
    const today = new Date(bn.now()).toISOString().slice(0, 10);
    const day = await kvGet<{ date: string; equity: number }>(db, "day_start", { date: "", equity: 0 });
    if (day.date !== today) await kvSet(db, "day_start", { date: today, equity });
    const dayStart = day.date === today ? day.equity : equity;
    const dailyBlocked = equity < dayStart * (1 - cfg.dailyLossLimit);
    const paused = await kvGet<boolean>(db, "paused", false);

    // jelzések és követő stop az új lezárt gyertyákon
    const lastCandle = await kvGet<Record<string, number>>(db, "last_candle", {});
    for (const symbol of cfg.symbols) {
      const candles = await bn.closedCandles(symbol);
      const last = candles[candles.length - 1];
      if (!last) continue;
      if (bn.now() - last.closeTime > 8 * 3_600_000) {
        await notifyError(db, tg, `stale:${symbol}`, `⚠️ ${symbol}: elavult piaci adat (utolsó gyertya: ${new Date(last.closeTime).toISOString()}).`);
        continue;
      }
      if ((lastCandle[symbol] ?? 0) >= last.openTime) continue;
      const sig = evaluate(candles, cfg);
      await trader.trail(symbol, last, sig);

      const all = await trader.positions();
      const hasPos = all.some((p) => p.symbol === symbol);
      const fresh = bn.now() - last.closeTime <= cfg.maxEntryDelayMs;
      if (sig.entry && !hasPos) {
        if (halted || paused) console.log(`${symbol} jelzés kihagyva (szünet/leállás)`);
        else if (dailyBlocked) console.log(`${symbol} jelzés kihagyva: napi veszteséglimit`);
        else if (all.length >= cfg.maxPositions) console.log(`${symbol} jelzés kihagyva: max pozíciószám`);
        else if (!fresh) console.log(`${symbol} jelzés kihagyva: késői futás`);
        else await trader.enter(symbol, last, sig);
      }
      lastCandle[symbol] = last.openTime;
      await kvSet(db, "last_candle", lastCandle);
    }

    // kézi trade-ek figyelése – hibája nem akaszthatja meg a bot kereskedését
    let manualSummary: any = null;
    const watcher = new ManualWatcher(db, bn, tg, cfg, prices);
    try {
      const botSymbols = new Set((await trader.positions()).map((p) => p.symbol));
      await watcher.run(botSymbols);
      manualSummary = await watcher.summary();
    } catch (e) {
      const err = e as Error;
      console.error("Kézi figyelés hiba:", err.stack ?? err.message);
      await notifyError(db, tg, `manual:${err.constructor.name}`, `⚠️ A kézi trade-figyelés most hibára futott: ${esc(err.message).slice(0, 200)}\nA bot kereskedése ettől zavartalan.`);
    }

    // piaci hírfolyam – hibája nem akaszthatja meg a kereskedést
    try {
      const feedSymbols = [...new Set([...cfg.symbols, ...(await watcher.watchlist().catch(() => cfg.manualSymbols))])];
      const botSymbols = new Set((await trader.positions()).filter((p) => p.status === "open").map((p) => p.symbol));
      await new MarketFeed(db, bn, tg, cfg, prices).run(feedSymbols, botSymbols, manualSummary?.open?.length ?? 0);
    } catch (e) {
      const err = e as Error;
      console.error("Hírfolyam hiba:", err.stack ?? err.message);
      await notifyError(db, tg, `feed:${err.constructor.name}`, `⚠️ A piaci hírfolyam most hibára futott: ${esc(err.message).slice(0, 200)}\nA bot kereskedése ettől zavartalan.`);
    }

    const snap = await snapshot(db, trader, cfg, prices, manualSummary);
    await reports(db, tg, snap);
    await kvSet(db, "last_ok_run", Date.now());
  } catch (e) {
    const err = e as Error;
    console.error("Futási hiba:", err.stack ?? err.message);
    const key = e instanceof RateLimitError ? "ratelimit" : e instanceof BinanceError ? `bn:${(e as BinanceError).code}` : err.constructor.name;
    await notifyError(db, tg, key, `⚠️ <b>Bot hiba</b>: ${esc(err.message).slice(0, 300)}\nA következő futás (5 perc) újrapróbálja.`);
    throw e;
  } finally {
    await releaseLease(db, holder);
  }
}

if (import.meta.main) {
  let code = 0;
  let db: SQL | null = null;
  try {
    const cfg = loadConfig();
    db = new SQL(cfg.databaseUrl);
    await runOnce(cfg, db);
  } catch (e) {
    console.error(e instanceof ConfigError ? `Konfigurációs hiba: ${e.message}` : e);
    code = 1;
  } finally {
    await db?.close();
  }
  process.exit(code);
}

