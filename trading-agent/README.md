# Trading agent — papírkereskedés valódi árfolyamokon

0–24 órás kriptó-figyelő. Jelzést ad, papíron kereskedik, és Telegramon beszámol.
**Valódi pénz nem mozog**: az árfolyamok a Binance éles adatai, a számla viszont
virtuális (alapból 10 000 USDT). A próbaverzió célja eldönteni, hogy a rendszer
megérdemli-e a valódi pénzt.

## Felépítés

| Modul | Feladat |
|---|---|
| `market.py` | Valódi gyertyák és árak a `data-api.binance.vision` címről (kulcs nélkül; az `api.binance.com` amerikai IP-ről 451-et ad) |
| `strategy.py` | Átlátható alapstratégia: EMA20/50 keresztezés, EMA200 trendszűrő, 2×ATR stop, 2R cél |
| `paper.py` | Pozícióméret, kockázati kapu, díj és csúszás — kódban, a modell nem írhatja felül |
| `store.py` | SQLite napló és számla; az újraindítás nem veszít állapotot, és nincs kettős végrehajtás |
| `backtest.py` | Ugyanaz a stratégia és ugyanazok a szabályok, múltbeli adatokon |
| `agent.py` | A ciklus: adatellenőrzés → stop/cél → jelzés → kockázat → napló → értesítés |
| `llm.py` | Gemini vagy OpenAI: csak magyaráz és válaszol, a számokat a rendszer adja |
| `telegram.py` | Értesítés kifelé, parancsok és kérdések befelé |
| `mailer.py` | E-mailes értesítés (Resend HTTPS API; a Railway a Pro csomag alatt tiltja az SMTP-t) |

**Kockázati szabályok** (alapértékek): 1% kockázat kötésenként, legfeljebb 2 nyitott
pozíció, 3% napi veszteség után aznap nincs új nyitás, 0,1% díj és 0,05% csúszás
oldalanként.

## Indítás

1. **Telegram bot:** írj a [@BotFather](https://t.me/BotFather)-nek, küldd el neki a `/newbot` parancsot, és mentsd el a tokent.
2. **Railway:** hozz létre új szolgáltatást ebből a repóból, *Root Directory* = `trading-agent`, és csatolj egy kötetet a `/data` útvonalra.
   - A régió lehet amerikai is, az adatvégpont onnan is elérhető.
   - **Csak 1 replika fusson.**
3. **Változók:** `TELEGRAM_BOT_TOKEN`, továbbá `GEMINI_API_KEY` vagy `OPENAI_API_KEY` (a sales-agent kulcsa is jó).
4. Írj a botnak bármit. Válaszul elküldi a chat-azonosítódat: ezt állítsd be `TELEGRAM_CHAT_ID` néven, és indítsd újra a szolgáltatást.
   - Ezután a bot csak neked válaszol.

**Telegram-parancsok:** `/status`, `/journal`, `/backtest BTCUSDT`, `/help`. Bármi mást
szabad szövegben is kérdezhetsz.

**Backtest gépen:**
```bash
pip install -r requirements.txt
python backtest.py BTCUSDT ETHUSDT --bars 3000
```

## Változók

- `TRADING_SYMBOLS` (alapból `BTCUSDT,ETHUSDT`), `TRADING_INTERVAL` (alapból `4h`)
- `PAPER_START_EQUITY` (10000), `RISK_PER_TRADE` (0.01, legfeljebb 0.05),
  `MAX_OPEN_POSITIONS` (2), `DAILY_LOSS_LIMIT` (0.03), `FEE_RATE` (0.001), `SLIPPAGE_RATE` (0.0005)
- `POLL_SECONDS` (60), `REPORT_HOUR` (8), `TRADING_TZ` (`Europe/Budapest`), `TRADING_DB_PATH` (`/data/trading.db`)
- `LLM_PROVIDER` (`gemini`|`openai`), `GEMINI_MODEL`, `TRADING_OPENAI_MODEL`
- `RESEND_API_KEY`, `NOTIFY_EMAIL`: e-mailes értesítés (jelzés, zárás, adathiba, napi jelentés); Telegram nélkül is működik
- `STATUS_TOKEN`: ha be van állítva, a `GET /status` végpont az `X-Status-Token` fejléccel elérhető
- `TRADING_LOOP=off`: a háttérszálak nem indulnak (teszteléshez)

A hibás vagy veszélyes értékeket (pl. `RISK_PER_TRADE=1`) a szolgáltatás induláskor elutasítja.

## Hibakezelés

- **Nem jön adat, vagy az adat elavult:** egyszer riaszt, és amíg a hiba tart, nem ad tanácsot. Ha az adat helyreáll, azt is jelzi.
- **Kiesik a modell:** az értesítés ugyanúgy kimegy, csak a magyarázat marad el.
- **Újraindulás:** a jelzések egyedi kulccsal kerülnek a naplóba, és instrumentumonként legfeljebb egy nyitott pozíció lehet. Így nincs dupla nyitás és dupla értesítés.
- **Kéréskorlát (HTTP 429):** nem próbál azonnal újra, mert a Binance ezt IP-tiltással bünteti; a következő ciklusban próbálkozik.
- **Ismert korlátok:**
  - A stopot percenként méri. Ha két mérés között az ár a stop alá ugrik, a rendszer a tényleges, rosszabb áron számol, ahogy élesben is történne.
  - Ha a szolgáltatás több gyertyán át állt, csak a legutolsó gyertyát értékeli.

## Mikor jöhet a valódi pénz

Akkor, ha **legalább 3 hónap papírkereskedés és legalább 30 lezárt kötés** után a `/journal` szerint:
- díjakkal együtt pozitív az átlagos R,
- és a hozam meghaladja a „vedd meg és tartsd” stratégiáét.

Ha ez nem teljesül, a stratégián kell változtatni, nem a valódi pénz felé lépni.
Az alapstratégia egy átlátható kiindulópont, nem bizonyított előny.
