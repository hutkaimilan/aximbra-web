/**
 * Teszt-agent: felhivja a sajat voice agentunket, es erdeklodo ugyfelet
 * jatszik. A beszelgetes felvetele es leirata visszanezheto.
 *
 * Miert kell: minden uj voice agent utan valakinek fel kell hivnia es
 * vegigbeszelnie a forgatokonyvet. Ez az a munka, amit gep is el tud vegezni.
 *
 * Ket hivaslab van:
 *   - a MI labunk (ez a fajl): kimeno hivas, sajat ConversationRelay-jel
 *   - a TESZTELT lab: a rendes /twiml vegpont, valtozatlanul
 * Mindketto ugyanezen a szerveren fut, de teljesen kulon utvonalon.
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
    // A teszt-agent hangja. Szandekosan MAS, mint az eles agente, hogy a
    // ketcsatornas felvetelen azonnal hallatszon, ki beszel.
    // Env-bol jon, hogy kod nelkul cserelheto legyen.
    ttsProvider: process.env['TEST_TTS_PROVIDER']?.trim() || 'Google',
    ttsVoice: process.env['TEST_TTS_VOICE']?.trim() || 'hu-HU-Chirp3-HD-Charon',
  };
}

export function testAgentEnabled(): boolean {
  const c = testCfg();
  const cfg = env();
  // Twilio-hitelesites kell a hivasinditashoz es a felvetel letoltesehez.
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
/* TwiML a mi labunkhoz                                                */
/* ------------------------------------------------------------------ */

function escapeXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

export function testTwiml(runId: string, scenarioKey: string): string {
  const cfg = env();
  const c = testCfg();
  const host = cfg.publicHostname;

  // A <Pause> csak annyi, hogy a vonal felepuljon. Korabban 4 masodperc volt,
  // de az tul sok: a masik oldal addigra elmondta a koszonojet a csendbe, es
  // utana mindketto varakozott. Egy masodperc eleg.
  //
  // speechTimeout: mennyi csend utan tekintjuk befejezettnek a masik mondatat.
  // Bot-bot beszelgetesnel ez mindket oldalon hozzaadodik a valaszidohoz,
  // ezert ugyanaz az ertek, mint az eles agenten (1000 ms), nem tobb.
  return `<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Pause length="1"/>
  <Connect>
    <ConversationRelay
      url="wss://${escapeXml(host)}/test/relay?run=${escapeXml(runId)}&amp;scenario=${escapeXml(scenarioKey)}"
      welcomeGreeting="${escapeXml(TESTER_OPENER)}"
      language="hu-HU"
      ttsProvider="${escapeXml(c.ttsProvider)}"
      voice="${escapeXml(c.ttsVoice)}"
      interruptible="none"
      speechTimeout="1000"
      ignoreBackchannel="true"
      welcomeGreetingInterruptible="none"
      reportInputDuringAgentSpeech="none">
      <Language code="hu-HU" ttsProvider="${escapeXml(c.ttsProvider)}" voice="${escapeXml(c.ttsVoice)}" />
    </ConversationRelay>
  </Connect>
</Response>`;
}

/* ------------------------------------------------------------------ */
/* A teszt-agent beszelgetese                                          */
/* ------------------------------------------------------------------ */

interface TesterSession {
  runId: string;
  history: Turn[];
  systemPrompt: string;
  startedAt: number;
  turns: number;
  busy: boolean;
  closed: boolean;
  timer: NodeJS.Timeout | null;
}

export function handleTestRelay(ws: WebSocket, runId: string, scenarioKey: string): void {
  const c = testCfg();
  const scenario = scenarioByKey(scenarioKey);

  // Ez a sor mondja meg, hogy a mi labunk egyaltalan felallt-e. Ha hivas utan
  // nincs a logban, akkor a WebSocket be sem jott (rossz URL, rossz run id).
  console.log(`[test] relay csatlakozott run=${runId} forgatokonyv=${scenario.key}`);

  const s: TesterSession = {
    runId,
    history: [],
    systemPrompt: buildTesterPrompt(scenario),
    startedAt: Date.now(),
    turns: 0,
    busy: false,
    closed: false,
    timer: null,
  };

  // A nyito mondatot a Twilio mondja ki (welcomeGreeting), de a modell
  // elozmenyeben is szerepelnie kell, kulonben ujra bemutatkozna.
  s.history.push({ role: 'assistant', content: TESTER_OPENER });
  void appendTurn(runId, { who: 'tester', text: TESTER_OPENER, atMs: 0 });

  const send = (text: string, last = true): void => {
    if (ws.readyState !== ws.OPEN) return;
    ws.send(JSON.stringify({ type: 'text', token: text, last }));
  };

  const finish = (reason: string): void => {
    if (s.closed) return;
    s.closed = true;
    if (s.timer) clearTimeout(s.timer);
    console.log(`[test] befejezes run=${runId} ok=${reason}`);
    setTimeout(() => {
      if (ws.readyState === ws.OPEN) ws.close(1000, reason);
    }, 4_000);
  };

  // Kemeny felso korlat: ket bot kepes vegtelenul udvariaskodni egymassal.
  s.timer = setTimeout(() => finish('idokorlat'), c.maxSeconds * 1_000);

  ws.on('message', (data) => {
    void (async () => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(data.toString()) as Record<string, unknown>;
      } catch {
        return;
      }

      if (msg['type'] !== 'prompt') return;
      if (msg['last'] === false) return;

      const heard =
        typeof msg['voicePrompt'] === 'string' ? msg['voicePrompt'].trim() : '';
      if (!heard || s.busy || s.closed) return;

      s.busy = true;
      s.history.push({ role: 'user', content: heard });
      void appendTurn(runId, {
        who: 'target',
        text: heard,
        atMs: Date.now() - s.startedAt,
      });

      try {
        s.turns += 1;
        if (s.turns > c.maxTurns) {
          send('Köszönöm szépen, ennyi elég is. Viszonthallásra!');
          finish('fordulo-korlat');
          return;
        }

        const raw = await reply(s.history, s.systemPrompt);
        const wantsEnd = raw.includes(END_MARKER);
        const spoken = raw.replace(END_MARKER, '').trim();

        s.history.push({ role: 'assistant', content: raw });
        void appendTurn(runId, {
          who: 'tester',
          text: spoken,
          atMs: Date.now() - s.startedAt,
        });

        if (spoken) send(spoken);
        if (wantsEnd) finish('cel-elerve');
      } catch (err) {
        console.error('[test] modellhiba:', err);
        send('Elnézést, megszakadt a vonal. Viszonthallásra!');
        finish('modellhiba');
      } finally {
        s.busy = false;
      }
    })();
  });

  ws.on('close', () => {
    if (s.timer) clearTimeout(s.timer);
    const durationSec = Math.round((Date.now() - s.startedAt) / 1000);
    console.log(`[test] hivas vege run=${runId} ${durationSec}s`);
    void updateRun(runId, { status: 'done', durationSec });
  });

  ws.on('error', (err) => {
    console.error('[test] socket hiba:', err);
    void updateRun(runId, { status: 'failed', error: String(err) });
  });
}

/* ------------------------------------------------------------------ */
/* Felvetel                                                            */
/* ------------------------------------------------------------------ */

/** A hivashoz tartozo felvetel SID-je, ha mar elkeszult. */
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
 * a szerver kéri le es tovabbitja - igy a token nem kerul a bongeszobe.
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
.turn{padding:9px 0;border-bottom:1px solid #171B2E}
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
  const when = new Date(run.createdAt).toLocaleString('hu-HU');

  const turns = run.turns.length
    ? run.turns
        .map((t) => {
          const who = t.who === 'tester' ? 'Teszt-agent (hívó)' : 'AXIMBRA agent';
          const sec = Math.round(t.atMs / 1000);
          return `<div class="turn">
  <div class="who ${esc(t.who)}">${esc(who)} · ${sec}s</div>
  <div>${esc(t.text)}</div>
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

/**
 * A /test/* utvonalak kezelese. null = nem ez a modul kezeli a kerest.
 */
export async function handleTestRoute(
  method: string,
  path: string,
  query: URLSearchParams,
): Promise<TestResponse | null> {
  if (!path.startsWith('/test')) return null;

  if (!testAgentEnabled()) {
    return { status: 503, headers: HTML, body: layout('<h1>A teszt-agent nincs bekapcsolva.</h1>') };
  }

  const token = query.get('token');
  if (!tokenMatches(token)) {
    return { status: 404, headers: { 'content-type': 'text/plain' }, body: 'not found' };
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

  const audioMatch = /^\/test\/runs\/([0-9a-f]{16})\/audio$/.exec(path);
  if (method === 'GET' && audioMatch) {
    const run = await loadRun(audioMatch[1]!);
    if (!run?.callSid) {
      return { status: 404, headers: { 'content-type': 'text/plain' }, body: 'nincs felvetel' };
    }

    let sid = run.recordingSid;
    if (!sid) {
      sid = await findRecordingSid(run.callSid);
      if (sid) await updateRun(run.id, { recordingSid: sid });
    }
    if (!sid) {
      return { status: 404, headers: { 'content-type': 'text/plain' }, body: 'a felvetel meg keszul' };
    }

    const audio = await fetchRecordingAudio(sid);
    if (!audio.ok) {
      return { status: 502, headers: { 'content-type': 'text/plain' }, body: 'felvetel nem elerheto' };
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

  if (method === 'POST' && path === '/test/twiml') {
    const runId = query.get('run') ?? '';
    if (!isValidRunId(runId)) {
      return { status: 400, headers: { 'content-type': 'text/plain' }, body: 'rossz run id' };
    }
    return {
      status: 200,
      headers: { 'content-type': 'text/xml' },
      body: testTwiml(runId, query.get('scenario') ?? 'alap'),
    };
  }

  return { status: 404, headers: { 'content-type': 'text/plain' }, body: 'not found' };
}
