import { expect, test } from "bun:test";
process.env.DATABASE_URL = "postgres://postgres@127.0.0.1:55432/postgres";
process.env.TG_WEBHOOK_SECRET = "x"; process.env.TELEGRAM_CHAT_ID = "123456";
const { handleCommand } = await import("../../webhook");
import { SQL } from "bun";
const db = new SQL("postgres://postgres@127.0.0.1:55432/postgres");

test("Bot2 parancsok a webhookban", async () => {
  await db`DROP TABLE IF EXISTS kv, b2_trades`;
  await db`CREATE TABLE kv (key text PRIMARY KEY, value jsonb NOT NULL, updated_at timestamptz NOT NULL DEFAULT now())`;
  expect(await handleCommand(db, "/allapot2")).toContain("még nem futott");
  expect(await handleCommand(db, "/trades2")).toContain("még nincs");
  expect(await handleCommand(db, "/stop2")).toContain("szünetel");
  expect((await db`SELECT value FROM kv WHERE key='b2:paused'`)[0].value).toBe(true);
  await db`INSERT INTO kv VALUES ('b2:halted', 'true'::jsonb, now())`;
  expect(await handleCommand(db, "/folytat2")).toContain("IGEN");
  await db`INSERT INTO kv VALUES ('b2:snapshot', ${JSON.stringify({ updatedAt: Date.now(), wallet: 5000, equity: 4900, startEquity: 5000, peak: 5000, positions: [{ name: "Tesla", side: "SHORT", entry: 400, last: 390, stop: 420, pnl: 25 }], paused: false, halted: true, realized: -100, trades: 2 })}::text::jsonb, now())`;
  expect(await handleCommand(db, "/folytat2 IGEN")).toContain("újra kereskedik");
  expect((await db`SELECT value FROM kv WHERE key='b2:peak'`)[0].value).toBe(4900);
  const st = await handleCommand(db, "/allapot2");
  expect(st).toContain("Tesla");
  expect(st).toContain("esésre");
  expect(await handleCommand(db, "/zaras2")).toContain("IGEN");
  await handleCommand(db, "/zaras2 IGEN");
  expect((await db`SELECT value FROM kv WHERE key='b2:close_all'`)[0].value).toBe(true);
  expect(await handleCommand(db, "/segitseg")).toContain("/allapot2");
  await db.close();
});
