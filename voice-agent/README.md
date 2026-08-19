# AXIMBRA voice agent

Telefonos érdeklődő-fogadó agent. Twilio ConversationRelay + OpenAI.

## Végpontok
- `GET /health` — állapot, napi számláló
- `POST /twiml` — Twilio webhook
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

Ha `PUBLIC_HOSTNAME` vagy `TWILIO_AUTH_TOKEN` hiányzik, az aláírás-ellenőrzés
kikapcsol, és a szerver ezt indításkor a logba írja.

## Twilio beállítás
A szám Voice webhookja: `https://<PUBLIC_HOSTNAME>/twiml`, HTTP POST.
