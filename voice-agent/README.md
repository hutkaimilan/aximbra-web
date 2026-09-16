# AXIMBRA voice agent

Telefonos érdeklődő-fogadó agent. Twilio ConversationRelay + OpenAI.

## Ki veszi fel

A döntés a hívó számán múlik (`src/routing.ts`):

| Hívó | Kihez kerül |
|---|---|
| magyar szám (`+36…`) | a tulajdonos mobiljára; ha nem fogadja, az agenthez, magyarul |
| más ország száma | az agenthez, angol köszönéssel |
| rejtett vagy értelmezhetetlen szám | az agenthez, magyarul |
| maga a tulajdonos | az agenthez, magyarul (hogy ki tudja próbálni) |

A tulajdonos telefonján a Twilio-szám látszik, és felvétel után egy hang kéri:
„nyomd meg az egyest". Csak erre kapcsolódik össze a hívás. Ha nem nyom
gombot, nem veszi fel `OWNER_RING_SECONDS` alatt, foglalt, vagy a hangposta
venné fel, a hívó az agenthez kerül — nem a hangpostára.

A magyar hívásokat a napi keret nem korlátozza, csak ha az agenthez kerülnek.

## Végpontok
- `GET /health` — állapot, napi számláló
- `POST /twiml` — Twilio webhook, itt dől el, ki veszi fel
- `POST /twiml/screen`, `/twiml/screen-done`, `/twiml/owner-done` — az átkapcsolás lépései
- `WS /relay` — a beszélgetés

## Env változók

| Név | Kötelező | Alap | Mire jó |
|---|---|---|---|
| `OPENAI_API_KEY` | igen | — | modellhívás |
| `PUBLIC_HOSTNAME` | erősen ajánlott | — | signature-ellenőrzéshez |
| `TWILIO_AUTH_TOKEN` | erősen ajánlott | — | signature-ellenőrzéshez |
| `VOICE_MODEL` | nem | `gpt-4.1-mini` | modell |
| `MAX_CALLS_PER_DAY` | nem | `15` | napi keret (0 = ki) |
| `MAX_CALL_SECONDS` | nem | `240` | híváshossz |
| `NOTIFY_EMAIL` | nem | — | ide megy az összefoglaló |
| `RESEND_API_KEY` | nem | — | email küldéshez |
| `TTS_VOICE` | nem | `Google.hu-HU-Standard-A` | hang |
| `CURRENT_PROJECTS` | nem | `0` | ennyi futó projekt alapján mond határidő-intervallumot |
| `OWNER_PHONE` | nem | — | ide kapcsolja a magyar hívásokat, `+36301234567` alakban. Üresen: nincs átkapcsolás |
| `OWNER_RING_SECONDS` | nem | `20` | ennyit cseng a tulajdonos telefonja, mielőtt az agent átveszi |

Ha `PUBLIC_HOSTNAME` vagy `TWILIO_AUTH_TOKEN` hiányzik, az aláírás-ellenőrzés
kikapcsol, és a szerver ezt indításkor a logba írja.

Az `OWNER_PHONE` szándékosan nincs a kódban: a repó nyilvános.

## Twilio beállítás
A szám Voice webhookja: `https://<PUBLIC_HOSTNAME>/twiml`, HTTP POST.

Az átkapcsolás kimenő hívás Magyarországra. Ha a Twilio-fiókban a
Voice → Settings → Geo permissions alatt Magyarország nincs engedélyezve, a
hívás nem megy ki — ilyenkor a hívó az agenthez kerül, és a logban
`a tulajdonos nem fogadta (failed)` áll.

## Tesztek
```
npm test
```
