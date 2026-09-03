/**
 * Teszt-agent: felhivja a sajat voice agentunket, es erdeklodo ugyfelet
 * jatszik. A beszelgetes felvetele es idobelyeges leirata visszanezheto.
 *
 * MIERT NEM ConversationRelay a mi oldalunkon:
 * Ket ConversationRelay-vezerelt hivaslab osszekotese nem mukodott. A hivas
 * felepult, 3 percig elt, de a felvetel 3 masodperc hangot tartalmazott es az
 * atirat ures maradt: egyik oldal beszedfelismeroje sem ismerte fel a masik
 * szintetikus hangjat beszedkent.
 *
 * A megoldas: a mi labunk klasszikus <Say> + <Gather input="speech"> parost
 * hasznal. A TESZTELT oldal valtozatlan marad.
 *
 * ------------------------------------------------------------------
 * 2026-09-03 JAVITASOK - mind egy valodi felvetel elemzesebol jott:
 *
 * 1. A <Say> a <Gather>-en BELUL volt. A Gather beszedfelismerese a nested
 *    <Say> alatt is fut, es az elso eszlelt hangra ELVAGJA a mondatot
 *    (barge-in). Mivel a masik oldalon egy folyamatosan beszelo agent van,
 *    a mondataink fele el sem hangzott: 1390 karakternyi szoveg 47 masodperc
 *    beszedben, ami ~29 karakter/masodperc - fizikailag lehetetlen.
 *    MOST: a <Say> a <Gather> ELE kerult. Elobb vegigmondjuk, aztan
 *    hallgatunk. Cserebe minket nem lehet felbeszakitani - egy teszt-hivonal
 *    ez jo csere, mert a kiszamithatosag fontosabb.
 *
 * 2. Az elso TwiML azonnal beszelt, mikozben a masik oldal welcomeGreeting-je
 *    is szolt. A ket koszones egymasra ment.
 *    MOST: az elso TwiML csak HALLGAT. Akkor mutatkozunk be, amikor a masik
 *    fel mar koszont - ahogy egy valodi hivo is tenne.
 *
 * 3. Az atirat idobelyegei a run letrehozasatol szamoltak, nem a hivas
 *    felveteletol. A csorgesi ido (5-10 mp) bennmaradt, ezert a leirat
 *    idopontjai NEM voltak osszevethetok a felvetel pozicioival.
 *    MOST: a hivas felvetelekor ujraallitjuk a nullpontot.
 *
 * 4. A fordulo-korlat elerese egyszeruen lecsapta a hivast - pont akkor,
 *    amikor az agent az elerhetoseget kerte. A teszt igy sosem jutott el
 *    a lenyeges lepesig.
 *    MOST: van egy LEZARO FAZIS. Nehany fordulóval a korlat elott a
 *    teszt-hivo elkezd lezarni: megadja az elerhetoseget, elkoszon.
 *
 * 5. A modell felrehallott mondatokhoz kitalalt tartalmat ("gyereklamacio"
 *    -> "a gyerekek szemuveg-reklamacioja"), amit a masik oldal tenykent
 *    visszaigazolt. MOST: kifejezett tiltas + visszakerdezes.
 * ------------------------------------------------------------------
 */

import crypto from 'node:crypto';
import twilio from 'twilio';
import OpenAI from 'openai';
import type { WebSocket } from 'ws';

import { env } from './env.js';
import { reply, type Turn } from './llm.js';
import {
  buildTesterPrompt,
  scenarioByKey,
  SCENARIOS,
  openerFor,
  END_MARKER,
} from './testPrompt.js';
import {
  appendTurn,
  createRun,
  isValidRunId,
  listRuns,
  loadRun,
  updateRun,
  type TestRun,
} from './testStore.js';

/* ------------------------------------------------------------------ */
/* Konfiguracio                                                        */
/* ------------------------------------------------------------------ */

function testCfg() {
  return {
    token: process.env['TEST_AGENT_TOKEN']?.trim() ?? '',
    from: process.env['TEST_AGENT_FROM']?.trim() ?? '',
    target: process.env['TEST_AGENT_TARGET']?.trim() ?? '',
    maxTurns: intEnv('TEST_MAX_TURNS', 14, 3, 60),
    maxSeconds: intEnv('TEST_MAX_SECONDS', 180, 30, 600),
    // <Say> hang: prefixSZEL. Env-bol jon, hogy kod nelkul cserelheto legyen.
    sayVoice: process.env['TEST_SAY_VOICE']?.trim() || 'Google.hu-HU-Wavenet-A',
    // A teszt-agent modellje kulon allithato: itt a gyorsasag fontosabb,
    // mint az eles oldalon. Minden masodperc gondolkodas nema vonal.
    model: process.env['TEST_MODEL']?.trim() || env().model,
    // Ferfi hang. A Twilio <Say> magyar keszleteben CSAK noi hang van
    // (hu-HU-Standard-B es hu-HU-Wavenet-B), ezert az OpenAI TTS-evel
    // szintetizalunk, es <Play>-jel jatsszuk le.
    ttsModel: process.env['TEST_TTS_MODEL']?.trim() || 'tts-1',
    ttsVoice: process.env['TEST_TTS_VOICE']?.trim() || 'onyx',
    // Ennyi csendet varunk a masik fel mondata utan, mielott lezarjuk a
    // felismerest. Az "auto" MONDAT KOZBEN zart le, ezert vagott bele a
    // teszt-agent az AXIMBRA agent szavaba 11-bol 8 alkalommal.
    speechTimeout: intEnv('TEST_SPEECH_TIMEOUT', 2, 1, 10),
  };
}

/** Ervenytelen szam eseten az alapertelmezes, hangos figyelmeztetessel. */
function intEnv(name: string, fallback: number, min: number, max: number): number {
  const raw = process.env[name];
  if (!raw || raw.trim() === '') return fallback;
  const parsed = Number.parseInt(raw.trim(), 10);
  if (!Number.isFinite(parsed) || parsed < min || parsed > max) {
    console.warn(`[test] ${name}="${raw}" ervenytelen, helyette: ${fallback}`);
    return fallback;
  }
  return parsed;
}

export function testAgentEnabled(): boolean {
  const c = testCfg();
  const cfg = env();
  return (
    c.token !== '' &&
    c.from !== '' &&
    c.target !== '' &&
    cfg.twilioAccountSid !== '' &&
    cfg.twilioAuthToken !== ''
  );
}

/** Idozites-biztos token-osszehasonlitas. */
function tokenMatches(given: string | null): boolean {
  const expected = testCfg().token;
  if (!expected || !given) return false;
  const a = Buffer.from(given);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i++) diff |= a[i]! ^ b[i]!;
  return diff === 0;
}

function escapeXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

/**
 * Beszedfelismeresi tippek.
 *
 * A magyar nyelvi modell nem ismeri a markanevet: a korabbi felvetelen
 * "lakcimbra" es "accimrai" lett belole. A hints ezt kozvetlenul javitja,
 * es igy az atirat is hasznalhato lesz kiertekelesre.
 */
const SPEECH_HINTS = [
  'Aximbra',
  'AI ügynökség',
  'agent',
  'automatizálás',
  'e-mail rendező',
  'érdeklődő minősítő',
  'árajánlat',
  'elérhetőség',
  'visszahívás',
].join(',');

/* ------------------------------------------------------------------ */
/* Beszedszinezis (ferfi hang)                                          */
/* ------------------------------------------------------------------ */

/**
 * A Twilio <Say> magyar hangkeszleteben nincs ferfi hang: csak
 * hu-HU-Standard-B es hu-HU-Wavenet-B letezik, mindketto noi. Ezert a
 * teszt-agent mondatait az OpenAI TTS-evel szintetizaljuk, es <Play>-jel
 * jatsszuk le.
 *
 * A hangfajlt memoriaban tartjuk: a Twilio egy masodpercen belul lekeri,
 * es utana mar nincs ra szukseg. Lemezre irni felesleges I/O lenne.
 */
interface Clip {
  buf: Buffer;
  at: number;
}

const clips = new Map<string, Clip>();
const CLIP_TTL_MS = 15 * 60_000;
/** Felso korlat, hogy egy elszabadult ciklus se ehesse meg a memoriat. */
const CLIP_MAX = 200;

function sweepClips(): void {
  const now = Date.now();
  for (const [id, c] of clips) {
    if (now - c.at > CLIP_TTL_MS) clips.delete(id);
  }
  while (clips.size > CLIP_MAX) {
    const oldest = clips.keys().next();
    if (oldest.done) break;
    clips.delete(oldest.value);
  }
}

let ttsClient: OpenAI | null = null;

/**
 * Egy mondat felmondasa hangfajlba.
 *
 * Hiba eseten null-t ad vissza, es a hivo <Say>-re esik vissza: a teszt
 * inkabb menjen tovabb noi hanggal, mint hogy elszalljon a hivas.
 */
async function synth(text: string): Promise<string | null> {
  const c = testCfg();
  try {
    if (!ttsClient) {
      ttsClient = new OpenAI({ apiKey: env().openaiApiKey, maxRetries: 1 });
    }
    // A voice/model mezok union-tipusuak az SDK-ban, de env-bol allithatok
    // akarunk lenni, ezert a parametertombot egyben tipizaljuk.
    const params = {
      model: c.ttsModel,
      voice: c.ttsVoice,
      input: text,
      response_format: 'mp3',
    } as unknown as OpenAI.Audio.SpeechCreateParams;

    const res = await ttsClient.audio.speech.create(params, { timeout: 15_000 });
    const buf = Buffer.from(await res.arrayBuffer());
    if (buf.length === 0) return null;

    const id = crypto.randomBytes(8).toString('hex');
    sweepClips();
    clips.set(id, { buf, at: Date.now() });
    return id;
  } catch (err) {
    console.error('[test] TTS hiba, visszaesunk <Say>-re:', err);
    return null;
  }
}

/* ------------------------------------------------------------------ */
/* Hivasinditas                                                        */
/* ------------------------------------------------------------------ */

export async function startTestCall(
  scenarioKey: string,
): Promise<{ ok: true; run: TestRun } | { ok: false; error: string }> {
  const c = testCfg();
  const cfg = env();
  const scenario = scenarioByKey(scenarioKey);

  if (!testAgentEnabled()) {
    return { ok: false, error: 'A teszt-agent nincs konfiguralva.' };
  }
  if (!cfg.publicHostname) {
    return { ok: false, error: 'PUBLIC_HOSTNAME hianyzik.' };
  }

  const run = await createRun(scenario.label, c.target);

  try {
    const client = twilio(cfg.twilioAccountSid, cfg.twilioAuthToken);
    const call = await client.calls.create({
      to: c.target,
      from: c.from,
      url:
        `https://${cfg.publicHostname}/test/twiml` +
        `?run=${encodeURIComponent(run.id)}` +
        `&scenario=${encodeURIComponent(scenario.key)}` +
        `&token=${encodeURIComponent(c.token)}`,
      method: 'POST',
      record: true,
      // Ket csatorna: kulon sav a ket felnek, igy visszahallgatasnal
      // egyertelmu, ki mit mondott.
      recordingChannels: 'dual',
      timeLimit: c.maxSeconds,
      statusCallback:
        `https://${cfg.publicHostname}/test/status` +
        `?run=${encodeURIComponent(run.id)}` +
        `&token=${encodeURIComponent(c.token)}`,
      statusCallbackEvent: ['completed'],
      statusCallbackMethod: 'POST',
    });

    await updateRun(run.id, { callSid: call.sid });
    console.log(`[test] hivas inditva run=${run.id} callSid=${call.sid}`);

    const updated = await loadRun(run.id);
    return { ok: true, run: updated ?? run };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error('[test] hivasinditas sikertelen:', msg);
    await updateRun(run.id, { status: 'failed', error: msg });
    return { ok: false, error: msg };
  }
}

/* ------------------------------------------------------------------ */
/* TwiML                                                               */
/* ------------------------------------------------------------------ */

/**
 * Egy fordulo: (opcionalisan) kimondjuk a szoveget, majd hallgatunk.
 *
 * A <Say> SZANDEKOSAN a <Gather>-en KIVUL van. Nested <Say> eseten a
 * felismero mar a sajat mondatunk alatt fut, es a masik oldal hangjara
 * elvagja - ez okozta, hogy a mondataink fele elveszett.
 *
 * timeout="12" - ennyit varunk arra, hogy a masik fel MEGSZOLALJON. A
 * tesztelt agent modellhivasa is idobe telik, 5 masodperc (az alapertek)
 * keves volt, es feleslegesen inditott csend-agat.
 *
 * speechTimeout="auto" - a Twilio dontse el, mikor fejezte be a mondatot.
 *
 * A <Gather> utani <Redirect> akkor fut le, ha nem erkezett beszed. A
 * csend-szamlalot URL-ben visszuk tovabb, mert a kereseknek nincs kozos
 * memoriajuk.
 */
async function turnTwiml(
  speak: string | null,
  runId: string,
  scenarioKey: string,
  token: string,
  silences: number,
): Promise<string> {
  const c = testCfg();
  const cfg = env();
  const q =
    `run=${encodeURIComponent(runId)}` +
    `&amp;scenario=${encodeURIComponent(scenarioKey)}` +
    `&amp;token=${encodeURIComponent(token)}`;

  const action = `https://${escapeXml(cfg.publicHostname)}/test/turn?${q}`;

  return `<?xml version="1.0" encoding="UTF-8"?>
<Response>${await voiceBlock(speak, token)}
  <Gather input="speech" language="hu-HU" speechTimeout="${c.speechTimeout}" timeout="12"
          hints="${escapeXml(SPEECH_HINTS)}"
          action="${action}" method="POST"/>
  <Redirect method="POST">${action}&amp;silence=${silences + 1}</Redirect>
</Response>`;
}

/**
 * A kimondando mondat TwiML-blokkja.
 *
 * Elsodlegesen <Play> az OpenAI-jal szintetizalt ferfi hanggal. Ha a TTS
 * elszall, <Say>-re esunk vissza, hogy a teszt attol meg lefusson.
 */
async function voiceBlock(speak: string | null, token: string): Promise<string> {
  if (speak === null) return '';
  const c = testCfg();
  const cfg = env();

  const clip = await synth(speak);
  if (clip) {
    const url =
      `https://${escapeXml(cfg.publicHostname)}/test/voice/${clip}.mp3` +
      `?token=${encodeURIComponent(token)}`;
    return `\n  <Play>${url}</Play>`;
  }
  return `\n  <Say voice="${escapeXml(c.sayVoice)}" language="hu-HU">${escapeXml(speak)}</Say>`;
}

/** Elkoszones es bontas. */
async function hangupTwiml(speak: string, token: string): Promise<string> {
  return `<?xml version="1.0" encoding="UTF-8"?>
<Response>${await voiceBlock(speak, token)}
  <Hangup/>
</Response>`;
}

/* ------------------------------------------------------------------ */
/* Beszelgetes-logika                                                  */
/* ------------------------------------------------------------------ */

/**
 * Az elozmeny ujraepitese a futas fajljabol.
 *
 * A <Gather> mintazatnal minden fordulo kulon HTTP-keres, nincs memoriaban
 * tartott session. Ez elonyos is: egy ujrainditas kozben sem vesz el a
 * beszelgetes, mert a lemezen van.
 */
function historyFromRun(run: TestRun): Turn[] {
  return run.turns.map((t) => ({
    role: t.who === 'tester' ? ('assistant' as const) : ('user' as const),
    content: t.text,
  }));
}

/** A futas nullpontja ezredmasodpercben. */
function baseMs(run: TestRun): number {
  const t = new Date(run.createdAt).getTime();
  return Number.isFinite(t) ? t : Date.now();
}

/**
 * A hivas elso TwiML-je.
 *
 * Nem beszelunk: megvarjuk, hogy a hivott fel koszonjon. Igy nem megy
 * egymasra a ket bemutatkozas, es ugy viselkedunk, ahogy egy valodi hivo.
 *
 * Itt allitjuk at a futas nullpontjat is a hivas FELVETELENEK idejere. A
 * `createdAt` eddig a hivasinditas ideje volt, benne a csorgessel, ezert az
 * atirat idobelyegei nem estek egybe a felvetel pozicioival.
 */
async function handleFirstTurn(
  runId: string,
  scenarioKey: string,
  token: string,
): Promise<string> {
  const run = await loadRun(runId);
  if (!run) return await hangupTwiml('Elnézést, technikai hiba történt. Viszonthallásra!', token);

  await updateRun(runId, { createdAt: new Date().toISOString() });
  console.log(`[test] hivas felveve run=${runId} forgatokonyv=${scenarioKey}`);

  return turnTwiml(null, runId, scenarioKey, token, 0);
}

/**
 * A lezaro fazis extra utasitasai.
 *
 * A korlat elerese elott nehany fordulóval ranyomunk a lezarasra, hogy a
 * teszt tenylegesen vegigmenjen a tolcsren (elerhetoseg atadasa), ne pedig
 * a limit vagja el a beszelgetest a legfontosabb pillanatban.
 */
function phaseNote(remaining: number): string {
  if (remaining > 4) return '';
  return `\n\nMOST ZARD LE A BESZELGETEST:
- Legfeljebb ${remaining} valaszod van hatra.
- Ha meg nem kertek el az elerhetosegedet, ajanld fel magadtol.
- Az elerhetoseged: ez a telefonszam, amirol hivsz, es a kovacs.peter kukac kovacsoptika pont hu cim.
- Ezutan koszonj el egy rovid mondattal, es a valaszod vegere ird oda: ${END_MARKER}`;
}

/** Minden tovabbi fordulo: meghallgatjuk, valaszolunk. */
async function handleNextTurn(
  runId: string,
  scenarioKey: string,
  token: string,
  heard: string,
  silences: number,
): Promise<string> {
  const c = testCfg();
  const run = await loadRun(runId);
  if (!run) return await hangupTwiml('Elnézést, technikai hiba történt. Viszonthallásra!', token);

  const startedAt = baseMs(run);
  const testerTurns = run.turns.filter((t) => t.who === 'tester').length;

  if (heard) {
    await appendTurn(runId, { who: 'target', text: heard, atMs: Date.now() - startedAt });
  }

  // Elso sajat megszolalas. Fix szoveg, modellhivas nelkul: nulla varakozas,
  // es a forgatokonyv mindig ugyanugy indul.
  if (testerTurns === 0) {
    const opener = openerFor(scenarioByKey(scenarioKey));
    await appendTurn(runId, {
      who: 'tester',
      text: opener,
      atMs: Date.now() - startedAt,
    });
    return await turnTwiml(opener, runId, scenarioKey, token, 0);
  }

  // Csend: a masik oldal nem szolalt meg. Ketszer probalkozunk ujra, utana
  // lezarjuk - kulonben a hivas a teljes idokorlatig ures maradna.
  //
  // A szamlalo 1-rol indul, mert az elso <Redirect> mar silence=1-et kuld.
  // Igy: 1 -> baratsagos ujraprobalas, 2 -> rovid "Halló?", 3 -> bontas.
  if (!heard) {
    if (silences >= 3) {
      console.log(`[test] befejezes run=${runId} ok=nincs-valasz`);
      await updateRun(runId, { status: 'done' });
      return await hangupTwiml('Úgy tűnik, megszakadt a vonal. Viszonthallásra!', token);
    }
    console.log(`[test] csend run=${runId} (${silences}/2)`);
    return await turnTwiml(
      silences <= 1 ? 'Halló, hallja amit mondok?' : 'Halló?',
      runId,
      scenarioKey,
      token,
      silences,
    );
  }

  // Fordulo-korlat: ket bot kepes vegtelenul udvariaskodni egymassal.
  if (testerTurns >= c.maxTurns) {
    console.log(`[test] befejezes run=${runId} ok=fordulo-korlat`);
    await updateRun(runId, { status: 'done' });
    return await hangupTwiml('Köszönöm szépen, ennyi elég is. Viszonthallásra!', token);
  }

  try {
    const history = historyFromRun(run);
    history.push({ role: 'user', content: heard });

    const prompt =
      buildTesterPrompt(scenarioByKey(scenarioKey)) + phaseNote(c.maxTurns - testerTurns);

    const raw = await reply(history, prompt, {
      // Ket rovid mondat. A hosszabb valasz csak a nema varakozast novelne.
      maxTokens: 90,
      temperature: 0.4,
      timeoutMs: 8_000,
      model: c.model,
    });

    const wantsEnd = raw.includes(END_MARKER);
    const spoken = raw.replace(END_MARKER, '').trim() || 'Értem.';

    await appendTurn(runId, {
      who: 'tester',
      text: spoken,
      atMs: Date.now() - startedAt,
    });

    if (wantsEnd) {
      console.log(`[test] befejezes run=${runId} ok=cel-elerve`);
      await updateRun(runId, { status: 'done' });
      return await hangupTwiml(spoken, token);
    }
    return await turnTwiml(spoken, runId, scenarioKey, token, 0);
  } catch (err) {
    console.error('[test] modellhiba:', err);
    await updateRun(runId, { status: 'failed', error: String(err) });
    return await hangupTwiml('Elnézést, megszakadt a vonal. Viszonthallásra!', token);
  }
}

/**
 * Regi WebSocket-belepesi pont. A Gather-alapu mintara valtas ota nem
 * hasznaljuk, de a server.ts meg importalja - a socketet azonnal zarjuk.
 */
export function handleTestRelay(ws: WebSocket, runId: string, _scenario: string): void {
  console.warn(`[test] elavult /test/relay hivas run=${runId}, bontva`);
  try {
    ws.close(1000, 'deprecated');
  } catch {
    /* mar zarva */
  }
}

/* ------------------------------------------------------------------ */
/* Felvetel                                                            */
/* ------------------------------------------------------------------ */

export async function findRecordingSid(callSid: string): Promise<string | null> {
  const cfg = env();
  try {
    const client = twilio(cfg.twilioAccountSid, cfg.twilioAuthToken);
    const recordings = await client.recordings.list({ callSid, limit: 1 });
    return recordings[0]?.sid ?? null;
  } catch (err) {
    console.error('[test] felvetel lekerdezes hiba:', err);
    return null;
  }
}

/**
 * A felvetel hangfajlja. A Twilio media-URL alap-hitelesitest kivan, ezert
 * a szerver keri le es tovabbitja - igy a token nem kerul a bongeszobe.
 */
export async function fetchRecordingAudio(
  recordingSid: string,
): Promise<{ ok: true; body: Buffer } | { ok: false; status: number }> {
  const cfg = env();
  const url =
    `https://api.twilio.com/2010-04-01/Accounts/${cfg.twilioAccountSid}` +
    `/Recordings/${recordingSid}.mp3`;

  const auth = Buffer.from(`${cfg.twilioAccountSid}:${cfg.twilioAuthToken}`).toString(
    'base64',
  );

  try {
    const res = await fetch(url, {
      headers: { Authorization: `Basic ${auth}` },
      signal: AbortSignal.timeout(30_000),
    });
    if (!res.ok) return { ok: false, status: res.status };
    return { ok: true, body: Buffer.from(await res.arrayBuffer()) };
  } catch (err) {
    console.error('[test] felvetel letoltes hiba:', err);
    return { ok: false, status: 504 };
  }
}

/* ------------------------------------------------------------------ */
/* Webes felulet                                                       */
/* ------------------------------------------------------------------ */

function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** ms -> "1:23" alak, a felvetel idovonalahoz igazitva. */
function clock(ms: number): string {
  const total = Math.max(0, Math.round(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

function layout(body: string): string {
  return `<!DOCTYPE html>
<html lang="hu"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<meta name="robots" content="noindex,nofollow"/>
<title>AXIMBRA — voice agent teszt</title>
<style>
:root{color-scheme:dark}
body{margin:0;background:#07070F;color:#E6E8F0;
 font:15px/1.6 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
.wrap{max-width:760px;margin:0 auto;padding:28px 18px 64px}
h1{font-size:20px;margin:0 0 4px}
.sub{color:#767D9C;font-size:13px;margin-bottom:24px}
.card{background:#0E1020;border:1px solid #1E2238;border-radius:12px;
 padding:16px 18px;margin-bottom:12px}
a{color:#5BC8FF}
button,select{font:inherit;border-radius:9px;padding:10px 16px;border:0}
select{background:#161A2E;color:#E6E8F0;border:1px solid #2A2F4A}
button{background:linear-gradient(90deg,#2BD9FE,#B14BFF);color:#04040C;
 font-weight:600;cursor:pointer}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
.badge{display:inline-block;padding:3px 10px;border-radius:20px;font-size:12px}
.running{background:#3A2E00;color:#FFD75E}
.done{background:#04312A;color:#4BE3C0}
.failed{background:#3A0E14;color:#FF7A8A}
.turn{display:flex;gap:14px;padding:10px 0;border-bottom:1px solid #171B2E}
.turn:last-child{border-bottom:0}
.at{flex:0 0 46px;color:#5A6180;font-size:12px;font-variant-numeric:tabular-nums;
 padding-top:2px}
.who{font-size:11px;letter-spacing:.12em;text-transform:uppercase}
.tester{color:#B14BFF}.target{color:#2BD9FE}
.meta{color:#767D9C;font-size:12px}
audio{width:100%;margin-top:10px}
</style></head><body><div class="wrap">${body}</div></body></html>`;
}

export function renderIndex(runs: TestRun[], token: string): string {
  const q = `?token=${encodeURIComponent(token)}`;

  const options = Object.values(SCENARIOS)
    .map((s) => `<option value="${esc(s.key)}">${esc(s.label)}</option>`)
    .join('');

  const list = runs.length
    ? runs
        .map((r) => {
          const when = new Date(r.createdAt).toLocaleString('hu-HU');
          const dur = r.durationSec === null ? '' : ` · ${r.durationSec}s`;
          return `<div class="card">
  <div class="row" style="justify-content:space-between">
    <div><a href="/test/runs/${esc(r.id)}${q}">${esc(r.scenario)}</a></div>
    <span class="badge ${esc(r.status)}">${esc(r.status)}</span>
  </div>
  <div class="meta">${esc(when)}${esc(dur)} · ${r.turns.length} forduló</div>
</div>`;
        })
        .join('')
    : '<div class="card meta">Még nincs futás.</div>';

  return layout(`<h1>Voice agent teszt</h1>
<div class="sub">A teszt-agent felhívja az éles vonalat, és végigbeszél egy forgatókönyvet.</div>
<div class="card">
  <form method="POST" action="/test/start${q}" class="row">
    <select name="scenario">${options}</select>
    <button type="submit">Teszthívás indítása</button>
  </form>
  <div class="meta" style="margin-top:10px">
    A hívás 1–3 percig tart. A felvétel a hívás után pár perccel érhető el.
  </div>
</div>
<h1 style="font-size:15px;margin:26px 0 10px">Korábbi futások</h1>
${list}`);
}

export function renderRun(run: TestRun, token: string): string {
  const q = `?token=${encodeURIComponent(token)}`;
  const startedAt = new Date(run.createdAt);
  const when = startedAt.toLocaleString('hu-HU');

  const turns = run.turns.length
    ? run.turns
        .map((t) => {
          const who = t.who === 'tester' ? 'Teszt-agent (hívó)' : 'AXIMBRA agent';
          const wall = new Date(startedAt.getTime() + t.atMs).toLocaleTimeString('hu-HU');
          return `<div class="turn">
  <div class="at" title="${esc(wall)}">${esc(clock(t.atMs))}</div>
  <div>
    <div class="who ${esc(t.who)}">${esc(who)}</div>
    <div>${esc(t.text)}</div>
  </div>
</div>`;
        })
        .join('')
    : '<div class="meta">Nincs rögzített forduló.</div>';

  const audio = run.callSid
    ? `<div class="card">
  <div class="who" style="color:#767D9C">Felvétel</div>
  <audio controls preload="none" src="/test/runs/${esc(run.id)}/audio${q}"></audio>
  <div class="meta" style="margin-top:6px">
    Ha nem indul el, a felvétel még készül — próbáld pár perc múlva.
    Kétcsatornás: a két fél külön sávon hallható.
  </div>
</div>`
    : '';

  const error = run.error
    ? `<div class="card"><div class="who failed">Hiba</div><div>${esc(run.error)}</div></div>`
    : '';

  return layout(`<div class="meta"><a href="/test${q}">← Vissza</a></div>
<h1 style="margin-top:12px">${esc(run.scenario)}</h1>
<div class="sub">${esc(when)} · ${esc(run.target)} ·
  <span class="badge ${esc(run.status)}">${esc(run.status)}</span>
  ${run.durationSec === null ? '' : ` · ${run.durationSec}s`}</div>
${error}
${audio}
<div class="card">
  <div class="who" style="color:#767D9C;margin-bottom:6px">Átirat</div>
  <div class="meta" style="margin-bottom:8px">
    A bal oldali idő a hívás felvételétől számít, így egybeesik a felvétel
    pozíciójával. A hívó sorai a kimondás kezdetén, az AXIMBRA agent sorai a
    felismerés végén vannak időbélyegezve. Fölé húzva a pontos óraidő.
  </div>
  ${turns}
</div>`);
}

/* ------------------------------------------------------------------ */
/* Utvonalak                                                           */
/* ------------------------------------------------------------------ */

export interface TestResponse {
  status: number;
  headers: Record<string, string>;
  body: string | Buffer;
}

const HTML = { 'content-type': 'text/html; charset=utf-8' };
const XML = { 'content-type': 'text/xml' };
const TEXT = { 'content-type': 'text/plain' };

/**
 * A /test/* utvonalak kezelese. null = nem ez a modul kezeli a kerest.
 *
 * A `form` parameter a POST-torzs mezoit tartalmazza (Twilio urlencoded).
 */
export async function handleTestRoute(
  method: string,
  path: string,
  query: URLSearchParams,
  form?: URLSearchParams,
): Promise<TestResponse | null> {
  if (!path.startsWith('/test')) return null;

  if (!testAgentEnabled()) {
    return {
      status: 503,
      headers: HTML,
      body: layout('<h1>A teszt-agent nincs bekapcsolva.</h1>'),
    };
  }

  const token = query.get('token');
  if (!tokenMatches(token)) {
    return { status: 404, headers: TEXT, body: 'not found' };
  }
  const t = token!;

  if (method === 'GET' && (path === '/test' || path === '/test/')) {
    return { status: 200, headers: HTML, body: renderIndex(await listRuns(), t) };
  }

  if (method === 'POST' && path === '/test/start') {
    const result = await startTestCall(query.get('scenario') ?? 'alap');
    if (!result.ok) {
      return {
        status: 500,
        headers: HTML,
        body: layout(`<h1>Nem sikerült</h1><div class="card">${esc(result.error)}</div>
<div class="meta"><a href="/test?token=${encodeURIComponent(t)}">← Vissza</a></div>`),
      };
    }
    return {
      status: 303,
      headers: { location: `/test/runs/${result.run.id}?token=${encodeURIComponent(t)}` },
      body: '',
    };
  }

  // A hivas elso TwiML-je.
  if (method === 'POST' && path === '/test/twiml') {
    const runId = query.get('run') ?? '';
    if (!isValidRunId(runId)) {
      return { status: 400, headers: TEXT, body: 'rossz run id' };
    }
    return {
      status: 200,
      headers: XML,
      body: await handleFirstTurn(runId, query.get('scenario') ?? 'alap', t),
    };
  }

  // Minden tovabbi fordulo.
  if (method === 'POST' && path === '/test/turn') {
    const runId = query.get('run') ?? '';
    if (!isValidRunId(runId)) {
      return { status: 400, headers: TEXT, body: 'rossz run id' };
    }
    const heard = (form?.get('SpeechResult') ?? '').trim();
    const silences = Number.parseInt(query.get('silence') ?? '0', 10) || 0;
    return {
      status: 200,
      headers: XML,
      body: await handleNextTurn(
        runId,
        query.get('scenario') ?? 'alap',
        t,
        heard,
        silences,
      ),
    };
  }

  // Hivas vege: idotartam rogzitese, futas lezarasa.
  if (method === 'POST' && path === '/test/status') {
    const runId = query.get('run') ?? '';
    if (isValidRunId(runId)) {
      const secs = Number.parseInt(form?.get('CallDuration') ?? '0', 10) || null;
      const run = await loadRun(runId);
      await updateRun(runId, {
        durationSec: secs,
        status: run?.status === 'failed' ? 'failed' : 'done',
      });
      console.log(`[test] hivas vege run=${runId} ${secs ?? '?'}s`);
    }
    return { status: 204, headers: TEXT, body: '' };
  }

  const voiceMatch = /^\/test\/voice\/([0-9a-f]{16})\.mp3$/.exec(path);
  if (method === 'GET' && voiceMatch) {
    const clip = clips.get(voiceMatch[1]!);
    if (!clip) return { status: 404, headers: TEXT, body: 'lejart hangklip' };
    return {
      status: 200,
      headers: { 'content-type': 'audio/mpeg', 'cache-control': 'no-store' },
      body: clip.buf,
    };
  }

  const audioMatch = /^\/test\/runs\/([0-9a-f]{16})\/audio$/.exec(path);
  if (method === 'GET' && audioMatch) {
    const run = await loadRun(audioMatch[1]!);
    if (!run?.callSid) {
      return { status: 404, headers: TEXT, body: 'nincs felvetel' };
    }

    let sid = run.recordingSid;
    if (!sid) {
      sid = await findRecordingSid(run.callSid);
      if (sid) await updateRun(run.id, { recordingSid: sid });
    }
    if (!sid) {
      return { status: 404, headers: TEXT, body: 'a felvetel meg keszul' };
    }

    const audio = await fetchRecordingAudio(sid);
    if (!audio.ok) {
      return { status: 502, headers: TEXT, body: 'felvetel nem elerheto' };
    }
    return {
      status: 200,
      headers: { 'content-type': 'audio/mpeg', 'cache-control': 'private, max-age=3600' },
      body: audio.body,
    };
  }

  const runMatch = /^\/test\/runs\/([0-9a-f]{16})$/.exec(path);
  if (method === 'GET' && runMatch) {
    const run = await loadRun(runMatch[1]!);
    if (!run) {
      return { status: 404, headers: HTML, body: layout('<h1>Nincs ilyen futás.</h1>') };
    }
    return { status: 200, headers: HTML, body: renderRun(run, t) };
  }

  return { status: 404, headers: TEXT, body: 'not found' };
}
