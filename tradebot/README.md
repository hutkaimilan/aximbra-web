# Trader bot (Binance demó)

- `worker.ts` – régi bot (BTC+ETH spot, 4h Donchian), a Railway `trader-worker` szolgáltatásban fut.
- `webhook.ts` – Telegram parancsok (`telegram-webhook`), Bot2 parancsokkal: /allapot2 /trades2 /stop2 /folytat2 /zaras2.
- `bot2/bot2.ts` – új, több piacos futures bot (`trader-bot2`, cron 5 perc): long+short 4h kitörés, tőzsdei stop (Algo API),
  1% kockázat, ≤2x összes névérték, napi 3% limit, 20% kill switch, hírek (RSS + Gemini, kulcsszavas tartalék) csak vétóként.
- Tesztek: `cd bot2 && bun test` (Postgres kell: `TEST_DATABASE_URL`, alapból `postgres://postgres@127.0.0.1:55432/postgres`).
