/**
 * Vegponti teszt a relay valaszidejere: mi tortenik, ha a modell lassu vagy
 * hibazik.
 *
 * Egy al-modellszerver (OpenAI-kompatibilis /chat/completions) a modell
 * neve szerint viselkedik (lasd startMock). A relaynek:
 *  - ket masodperc csend utan "Egy pillanat."-ot kell mondania, egyszer;
 *  - 2,5 masodperc utan a tartalek-modellt is el kell inditania,
 *    parhuzamosan, es azt kell kimondania, amelyik ELOBB szolal meg;
 *  - a vesztes modell egyetlen szava sem juthat a vonalra;
 *  - a fo modell hibaja eseten azonnal a tartalekhoz kell fordulnia.
 *
 * Eles meres alapjan: a modell elso tokenje 0,5 s es 9 s kozott jott, egyszer
 * 20 s felett. Egy 20 masodperces csend telefonon "megszakadt a vonal".
 */
import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, type ChildProcess } from 'node:child_process';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import WebSocket from 'ws';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PORT = 18941;
const MOCK_PORT = 18942;

const PRIMARY_TEXT = 'Ezt a fő modell mondja.';
const FALLBACK_TEXT = 'Persze, erre az e-mail rendező való.';

function chunk(text: string): string {
  return `data: ${JSON.stringify({
    id: 'x',
    object: 'chat.completion.chunk',
    created: 0,
    model: 'm',
    choices: [{ index: 0, delta: { content: text }, finish_reason: null }],
  })}\n\n`;
}

function streamText(res: http.ServerResponse, text: string): void {
  res.writeHead(200, { 'content-type': 'text/event-stream' });
  const words = text.split(/(?<= )/u);
  for (const w of words) res.write(chunk(w));
  res.write('data: [DONE]\n\n');
  res.end();
}

/**
 * Al-modell, a modell neve szerint:
 *   lassu  - soha nem valaszol (a kliens szakitja meg)
 *   nema   - fejlecet kuld, tokent soha (a stream nyitva marad)
 *   egyszerlassu - az elso kerese nem valaszol, a tobbi azonnal (PRIMARY_TEXT)
 *   tartalek5 - 5 s utan valaszol (FALLBACK_TEXT)
 *   kesik  - 3,5 s utan valaszol (PRIMARY_TEXT)
 *   egymp  - 1 s utan valaszol (PRIMARY_TEXT)
 *   hiba   - azonnal 503
 *   bontas - azonnal valaszol, elkoszones nelkul, a bontas jelevel
 *   kerdesbont - kerdest tesz fel, es megis a bontas jelet irja utana
 *   gyors  - azonnal valaszol (FALLBACK_TEXT); a nem streamelt hivasokra '{}'
 */
function startMock(): http.Server {
  const seen = new Map<string, number>();
  const srv = http.createServer((req, res) => {
    let body = '';
    req.on('data', (c: Buffer) => (body += c.toString('utf8')));
    req.on('end', () => {
      let parsed: { model?: string; stream?: boolean } = {};
      try {
        parsed = JSON.parse(body) as typeof parsed;
      } catch {
        /* ures */
      }
      const model = parsed.model ?? '';
      if (parsed.stream) seen.set(model, (seen.get(model) ?? 0) + 1);
      if (model === 'lassu') return;
      // Az elso kerese nem valaszol, a masodik azonnal (keresenkent ingadozo kesleltetes).
      if (model === 'egyszerlassu' && seen.get(model) === 1) return;
      if (model === 'nema') {
        // Fejlec igen, token soha: az SDK idokorlatja ezt nem fogja meg.
        res.writeHead(200, { 'content-type': 'text/event-stream' });
        res.flushHeaders();
        return;
      }
      if (model === 'hiba') {
        res.writeHead(503, { 'content-type': 'application/json' });
        res.end(JSON.stringify({ error: { message: 'overloaded', code: 503 } }));
        return;
      }
      if (parsed.stream) {
        const delay =
          model === 'kesik' ? 3_500 : model === 'egymp' ? 1_000 : model === 'tartalek5' ? 5_000 : 0;
        const text =
          model === 'bontas'
            ? 'Köszönöm a tájékoztatást. [[BONT]]'
            : model === 'kerdesbont'
              ? 'Van még kérdése, amiben segíthetek? [[BONT]]'
            : model === 'kesik' || model === 'egymp' || model === 'egyszerlassu'
              ? PRIMARY_TEXT
              : FALLBACK_TEXT;
        const t = setTimeout(() => {
          if (!res.destroyed) streamText(res, text);
        }, delay);
        res.on('close', () => clearTimeout(t));
        return;
      }
      res.writeHead(200, { 'content-type': 'application/json' });
      res.end(
        JSON.stringify({
          id: 'x',
          object: 'chat.completion',
          created: 0,
          model: 'm',
          choices: [{ index: 0, message: { role: 'assistant', content: '{}' }, finish_reason: 'stop' }],
        }),
      );
    });
  });
  srv.listen(MOCK_PORT, '127.0.0.1');
  return srv;
}

let mock: http.Server;
before(() => {
  mock = startMock();
});
after(() => {
  mock.close();
});

/** Egy fordulo a megadott fo/tartalek modellel; a vonalra kuldott szovegek idobelyeggel. */
async function turn(
  primary: string,
  fallback: string,
  listenMs: number,
): Promise<Array<{ text: string; at: number }> & { closedByServer?: boolean }> {
  const child: ChildProcess = spawn(process.execPath, [path.join(HERE, 'server.js')], {
    cwd: HERE,
    env: {
      ...process.env,
      SMOKE_TEST_SCENARIO: '',
      PORT: String(PORT),
      OPENAI_API_KEY: 'sk-test',
      LLM_BASE_URL: `http://127.0.0.1:${MOCK_PORT}/v1`,
      LLM_API_KEY: 'test',
      VOICE_MODEL: primary,
      FALLBACK_MODEL: fallback,
      AUX_MODEL: 'gyors',
      VOICE_REASONING_EFFORT: '',
      TWILIO_AUTH_TOKEN: 'e2e',
      TWILIO_ACCOUNT_SID: 'ACe2e0123456789abcdef0123456789ab',
      PUBLIC_HOSTNAME: 'voice.e2e-test.example',
      MAX_CALLS_PER_DAY: '100',
    },
  });
  const exited = new Promise<void>((ok) => child.once('exit', () => ok()));
  try {
    await new Promise((r) => setTimeout(r, 1200));
    const ws = new WebSocket(`ws://127.0.0.1:${PORT}/relay?lang=hu&fix=1`);
    await new Promise<void>((ok, bad) => {
      ws.once('open', () => ok());
      ws.once('error', bad);
    });
    const got: Array<{ text: string; at: number }> & { closedByServer?: boolean } = [];
    let t0 = 0;
    let closing = false;
    ws.on('close', () => {
      if (!closing) got.closedByServer = true;
    });
    ws.on('message', (raw) => {
      const m = JSON.parse(String(raw)) as { type?: string; token?: string };
      if (m.type === 'text' && m.token) got.push({ text: m.token, at: Date.now() - t0 });
    });
    ws.send(JSON.stringify({ type: 'setup', from: '+36301234567', callSid: 'CAe2e' }));
    t0 = Date.now();
    ws.send(JSON.stringify({ type: 'prompt', voicePrompt: 'Az e-mailek kezelése miatt keresem.', last: true }));
    await new Promise((r) => setTimeout(r, listenMs));
    closing = true;
    ws.close();
    return got;
  } finally {
    child.kill();
    await exited;
  }
}

const said = (got: Array<{ text: string }>): string => got.map((g) => g.text).join('');
const firstAt = (got: Array<{ text: string; at: number }>, re: RegExp): number | undefined =>
  got.find((g) => re.test(g.text))?.at;

test('a fo modell nem szol: "egy pillanat", majd 2,5 s utan a tartalek beszel', async () => {
  const got = await turn('lassu', 'gyors', 5_000);
  const pause = firstAt(got, /egy pillanat/i);
  assert.ok(pause !== undefined, `nem hangzott el "egy pillanat": ${JSON.stringify(got)}`);
  assert.ok(pause >= 1_800 && pause < 2_450, `"egy pillanat" ${pause} ms utan`);
  assert.equal(got.filter((g) => /egy pillanat/i.test(g.text)).length, 1, 'csak egyszer');
  assert.match(said(got), /e-mail rendező való/, `a tartalek valasza nem jott meg: ${JSON.stringify(got)}`);
  const answer = firstAt(got, /Persze/);
  assert.ok(answer !== undefined && answer >= 2_400 && answer < 3_600, `a tartalek ${answer} ms utan szolalt meg`);
});

test('a fo modell keson szolalna meg: a tartalek nyer, a ket valasz nem keveredik', async () => {
  const got = await turn('kesik', 'gyors', 6_000);
  const text = said(got);
  assert.match(text, /e-mail rendező való/);
  assert.doesNotMatch(text, /fő modell/, `a vesztes modell szava is kiment: ${text}`);
  const answer = firstAt(got, /Persze/);
  assert.ok(answer !== undefined && answer < 3_600, `a tartalek ${answer} ms utan szolalt meg`);
});

test('gyors fo modell: nincs "egy pillanat", nincs tartalek', async () => {
  const got = await turn('egymp', 'gyors', 4_000);
  const text = said(got);
  assert.match(text, /fő modell mondja/);
  assert.doesNotMatch(text, /egy pillanat|e-mail rendező/i, `felesleges kitoltes vagy tartalek: ${text}`);
});

test('a fo modell hibaja: a tartalek azonnal indul', async () => {
  const got = await turn('hiba', 'gyors', 3_000);
  const answer = firstAt(got, /Persze/);
  assert.ok(answer !== undefined && answer < 1_500, `a tartalek ${answer} ms utan szolalt meg: ${JSON.stringify(got)}`);
  assert.doesNotMatch(said(got), /egy pillanat/i);
});

test('mindket modell hibazik: a hivo a hibauzenetet hallja, nem csendet', async () => {
  const got = await turn('hiba', 'hiba', 3_000);
  assert.match(said(got), /megszakadt a kapcsolat/i, `nincs hibauzenet: ${JSON.stringify(got)}`);
});

test('fejlec van, token nincs: a tartalek beszel, nem nema a vonal', async () => {
  const got = await turn('nema', 'gyors', 4_500);
  const answer = firstAt(got, /Persze/);
  assert.ok(answer !== undefined && answer < 3_600, `a tartalek ${answer} ms utan szolalt meg: ${JSON.stringify(got)}`);
});

test('egyik modell sem szolal meg: 11 s utan hibauzenet, nem orokos csend', async () => {
  const got = await turn('nema', 'nema', 13_500);
  const fail = firstAt(got, /megszakadt a kapcsolat/i);
  assert.ok(fail !== undefined, `nincs hibauzenet: ${JSON.stringify(got)}`);
  assert.ok(fail >= 10_800 && fail < 12_500, `a hibauzenet ${fail} ms utan jott`);
});

test('bontas elkoszones nelkul: a rogzitett elkoszones potolja', async () => {
  const got = await turn('bontas', 'gyors', 9_000);
  const text = said(got);
  assert.match(text, /Köszönöm a tájékoztatást\./);
  assert.match(text, /viszonthallásra/i, `nincs elkoszones a bontas elott: ${text}`);
  assert.doesNotMatch(text, /\[\[BONT\]\]/, 'a bontas jele nem hangozhat el');
  assert.equal(got.closedByServer, true, 'elkoszones utan nem bontott');
});

test('kerdes utan nincs bontas, es nincs pótolt elkoszones sem', async () => {
  const got = await turn('kerdesbont', 'gyors', 6_000);
  const text = said(got);
  assert.match(text, /Van még kérdése/);
  assert.doesNotMatch(text, /viszonthallásra/i, `kerdes utan elkoszont: ${text}`);
  assert.notEqual(got.closedByServer, true, 'kerdes utan bontott');
});

test('lassu fo modell, lassu tartalek: a fo modell masodik kerese nyer', async () => {
  const got = await turn('egyszerlassu', 'tartalek5', 5_500);
  const text = said(got);
  const answer = firstAt(got, /fő modell/);
  assert.ok(answer !== undefined && answer >= 2_400 && answer < 3_600, `a valasz ${answer} ms utan jott: ${text}`);
  assert.doesNotMatch(text, /e-mail rendező/, `a lassu tartalek is beszelt: ${text}`);
});
