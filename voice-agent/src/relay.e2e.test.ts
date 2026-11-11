/**
 * Vegponti teszt a relay valaszidejere: mi tortenik, ha a modell lassu.
 *
 * Egy al-modellszerver (OpenAI-kompatibilis /chat/completions) a "lassu"
 * modellnel nem kuld semmit, a "gyors" (tartalek) modellnel azonnal valaszol.
 * A relaynek ket masodperc utan "Egy pillanat."-ot kell mondania, het
 * masodperc utan pedig a tartalek-modell valaszat - nema vonal helyett.
 *
 * Eles meres alapjan: a modell elso tokenje 0,7 s es 9 s kozott jott, egyszer
 * 20 s felett. Egy 20 masodperces csend telefonon "megszakadt a vonal".
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, type ChildProcess } from 'node:child_process';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import WebSocket from 'ws';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PORT = 18941;
const MOCK_PORT = 18942;

function chunk(text: string): string {
  return `data: ${JSON.stringify({
    id: 'x',
    object: 'chat.completion.chunk',
    created: 0,
    model: 'm',
    choices: [{ index: 0, delta: { content: text }, finish_reason: null }],
  })}\n\n`;
}

/** Al-modell: "lassu" = soha nem valaszol, minden mas azonnal. */
function startMock(): http.Server {
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
      if (parsed.model === 'lassu') return; // nem valaszol: a kliens szakitja meg
      if (parsed.stream) {
        res.writeHead(200, { 'content-type': 'text/event-stream' });
        res.write(chunk('Persze, '));
        res.write(chunk('erre az e-mail rendező való.'));
        res.write('data: [DONE]\n\n');
        res.end();
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

test('lassu modell: "egy pillanat", majd a tartalek valasza', async () => {
  const mock = startMock();
  const child: ChildProcess = spawn(process.execPath, [path.join(HERE, 'server.js')], {
    cwd: HERE,
    env: {
      ...process.env,
      SMOKE_TEST_SCENARIO: '',
      PORT: String(PORT),
      OPENAI_API_KEY: 'sk-test',
      LLM_BASE_URL: `http://127.0.0.1:${MOCK_PORT}/v1`,
      LLM_API_KEY: 'test',
      VOICE_MODEL: 'lassu',
      FALLBACK_MODEL: 'gyors',
      AUX_MODEL: 'gyors',
      VOICE_REASONING_EFFORT: '',
      TWILIO_AUTH_TOKEN: 'e2e',
      TWILIO_ACCOUNT_SID: 'ACe2e0123456789abcdef0123456789ab',
      PUBLIC_HOSTNAME: 'voice.e2e-test.example',
      MAX_CALLS_PER_DAY: '100',
    },
  });
  try {
    await new Promise((r) => setTimeout(r, 1200));
    const ws = new WebSocket(`ws://127.0.0.1:${PORT}/relay?lang=hu&fix=1`);
    await new Promise<void>((ok, bad) => {
      ws.once('open', () => ok());
      ws.once('error', bad);
    });
    const got: Array<{ text: string; at: number }> = [];
    let t0 = 0;
    ws.on('message', (raw) => {
      const m = JSON.parse(String(raw)) as { type?: string; token?: string };
      if (m.type === 'text' && m.token) got.push({ text: m.token, at: Date.now() - t0 });
    });
    ws.send(JSON.stringify({ type: 'setup', from: '+36301234567', callSid: 'CAe2e' }));
    t0 = Date.now();
    ws.send(JSON.stringify({ type: 'prompt', voicePrompt: 'Az e-mailek kezelése miatt keresem.', last: true }));
    await new Promise((r) => setTimeout(r, 9_000));
    ws.close();

    const pause = got.find((g) => /egy pillanat/i.test(g.text));
    assert.ok(pause, `nem hangzott el "egy pillanat": ${JSON.stringify(got)}`);
    assert.ok(pause.at >= 1_800 && pause.at < 3_000, `"egy pillanat" ${pause.at} ms utan`);
    assert.equal(got.filter((g) => /egy pillanat/i.test(g.text)).length, 1, 'csak egyszer');

    const answer = got.filter((g) => !/egy pillanat/i.test(g.text)).map((g) => g.text).join('');
    assert.match(answer, /e-mail rendező/, `a tartalek valasza nem jott meg: ${JSON.stringify(got)}`);
    const first = got.find((g) => /Persze/.test(g.text));
    assert.ok(first && first.at >= 6_800 && first.at < 8_500, `a tartalek ${first?.at} ms utan szolalt meg`);
  } finally {
    child.kill();
    mock.close();
  }
});
