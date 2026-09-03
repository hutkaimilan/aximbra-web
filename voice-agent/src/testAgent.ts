/**
 * Teszt-agent: felhivja a sajat voice agentunket, es erdeklodo ugyfelet
 * jatszik. A beszelgetes felvetele es idobelyeges leirata visszanezheto.
 *
 * MIERT NEM ConversationRelay a mi oldalunkon:
 * Ket ConversationRelay-vezerelt hivaslab osszekotese nem mukodott. A hivas
 * felepult, 3 percig elt, de a felvetel 3 masodperc hangot tartalmazott es az
 * atirat ures maradt: egyik oldal beszedfelismeroje sem ismerte fel a masik
 * szintetikus hangjat beszedkent. A ConversationRelay valodi emberi hangra van
 * tervezve, nem ket TTS osszekapcsolasara.
 *
 * A megoldas: a mi labunk klasszikus <Say> + <Gather input="speech"> parost
 * hasznal. Ez a bevett mintazat hang felismeresere, es nem versenyzik egy
 * masik elo AI-munkamenettel. A TESZTELT oldal valtozatlan marad.
 *
 * Kovetkezmeny: a beszelgetes allapota nem egy tartos WebSocketben el, hanem
 * fordulonkent uj HTTP-keres erkezik. Az elozmenyt ezert a futas fajljabol
 * epitjuk ujra minden fordulonal - a runId az egyetlen, ami osszekoti oket.
 */

import twilio from 'twilio';
import type { WebSocket } from 'ws';

import { env } from './env.js';
import { reply, type Turn } from './llm.js';
import {
  buildTesterPrompt,
  scenarioByKey,
  SCENARIOS,
  TESTER_OPENER,
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
    maxTurns: Number.parseInt(process.env['TEST_MAX_TURNS'] ?? '14', 10),
    maxSeconds: Number.parseInt(process.env['TEST_MAX_SECONDS'] ?? '180', 10),
    // <Say> hang: prefixSZEL. Env-bol jon, hogy kod nelkul cserelheto legyen.
    sayVoice: process.env['TEST_SAY_VOICE']?.trim() || 'Google.hu-HU-Wavenet-A',
  };
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
      // A hivas vegen ertesulunk rola, hogy lezarhassuk a futast. Enelkul a
      // status orokre 'running' maradna, mint a korabbi verzioban.
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
 * Egy forduloi valasz: kimondjuk a szoveget, majd hallgatunk.
 *
 * speechTimeout="auto" - a Twilio maga donti el, mikor fejezte be a masik a
 * mondatot. Fix erteknel vagy levagtuk a valaszat, vagy feleslegesen vartunk.
 *
 * A <Gather> utani <Redirect> akkor fut le, ha nem erkezett beszed: ilyenkor
 * ujra probalkozunk, nem bontunk azonnal. A csend-szamlalot URL-ben visszuk
 * tovabb, mert a kereseknek nincs kozos memoriajuk.
 */
function turnTwiml(
  speak: string,
  runId: string,
  scenarioKey: string,
  token: string,
  silences: number,
): string {
  const c = testCfg();
  const cfg = env();
  const q =
    `run=${encodeURIComponent(runId)}` +
    `&amp;scenario=${encodeURIComponent(scenarioKey)}` +
    `&amp;token=${encodeURIComponent(token)}`;

  return `<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather input="speech" language="hu-HU" speechTimeout="auto"
          action="https://${escapeXml(cfg.publicHostname)}/test/turn?${q}"
          method="POST">
    <Say voice="${escapeXml(c.sayVoice)}" language="hu-HU">${escapeXml(speak)}</Say>
  </Gather>
  <Redirect method="POST">https://${escapeXml(cfg.publicHostname)}/test/turn?${q}&amp;silence=${silences + 1}</Redirect>
</Response>`;
}

/** Elkoszones es bontas. */
function hangupTwiml(speak: string): string {
  const c = testCfg();
  return `<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="${escapeXml(c.sayVoice)}" language="hu-HU">${escapeXml(speak)}</Say>
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

/** A hivas elso TwiML-je: bemutatkozunk, majd hallgatunk. */
async function handleFirstTurn(
  runId: string,
  scenarioKey: string,
  token: string,
): Promise<string> {
  const run = await loadRun(runId);
  if (!run) return hangupTwiml('Elnézést, technikai hiba történt. Viszonthallásra!');

  await appendTurn(runId, { who: 'tester', text: TESTER_OPENER, atMs: 0 });
  console.log(`[test] elso fordulo run=${runId} forgatokonyv=${scenarioKey}`);

  return turnTwiml(TESTER_OPENER, runId, scenarioKey, token, 0);
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
  if (!run) return hangupTwiml('Elnézést, technikai hiba történt. Viszonthallásra!');

  const startedAt = new Date(run.createdAt).getTime();
  const atMs = Date.now() - startedAt;

  // Csend: a masik oldal nem szolalt meg. Ketszer probalkozunk ujra, utana
  // lezarjuk - kulonben a hivas a teljes idokorlatig ures maradna.
  //
  // A szamlalo 1-rol indul, mert az elso <Redirect> mar silence=1-et kuld.
  // Igy: 1 -> baratsagos ujraprobalas, 2 -> rovid "Halló?", 3 -> bontas.
  if (!heard) {
    if (silences >= 3) {
      console.log(`[test] befejezes run=${runId} ok=nincs-valasz`);
      await updateRun(runId, { status: 'done' });
      return hangupTwiml('Úgy tűnik, megszakadt a vonal. Viszonthallásra!');
    }
    console.log(`[test] csend run=${runId} (${silences}/2)`);
    return turnTwiml(
      silences <= 1 ? 'Halló, hallja amit mondok?' : 'Halló?',
      runId,
      scenarioKey,
      token,
      silences,
    );
  }

  await appendTurn(runId, { who: 'target', text: heard, atMs });

  // Fordulo-korlat: ket bot kepes vegtelenul udvariaskodni egymassal.
  const testerTurns = run.turns.filter((t) => t.who === 'tester').length;
  if (testerTurns >= c.maxTurns) {
    console.log(`[test] befejezes run=${runId} ok=fordulo-korlat`);
    await updateRun(runId, { status: 'done' });
    return hangupTwiml('Köszönöm szépen, ennyi elég is. Viszonthallásra!');
  }

  try {
    const history = historyFromRun(run);
    history.push({ role: 'user', content: heard });

    const raw = await reply(history, buildTesterPrompt(scenarioByKey(scenarioKey)));
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
      return hangupTwiml(spoken);
    }
    return turnTwiml(spoken, runId, scenarioKey, token, 0);
  } catch (err) {
    console.error('[test] modellhiba:', err);
    await updateRun(runId, { status: 'failed', error: String(err) });
    return hangupTwiml('Elnézést, megszakadt a vonal. Viszonthallásra!');
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

  const res = await fetch(url, {
    headers: { Authorization: `Basic ${auth}` },
    signal: AbortSignal.timeout(30_000),
  });

  if (!res.ok) return { ok: false, status: res.status };
  return { ok: true, body: Buffer.from(await res.arrayBuffer()) };
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
          // Ketfele ido: a felvetelen valo pozicio, es a valos ora.
          // Az elso a visszahallgatashoz kell, a masodik a naplokhoz.
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
    A bal oldali idő a felvételen belüli pozíció. Fölé húzva a pontos óraidő.
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
