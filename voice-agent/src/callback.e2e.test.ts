/**
 * Vegponti teszt a "hivjon vissza" gombra.
 *
 * Amit oriz: egy nyilvanos vegpont, ami telefont csorget, ket modon
 * tamadhato - masok zaklatasa es a Twilio-egyenleg elegetese. A modul
 * egysegtesztjei a keretek logikajat ellenorzik; ez azt, hogy a HTTP-reteg
 * tenylegesen alkalmazza oket, es hogy idegen oldal ne tudjon hivast
 * inditani a latogatoja neveben.
 *
 * A Twilio-hivas szandekosan nem megy ki: a teszt olyan eseteket kuld,
 * amelyek MINDIG az elso, halozat elotti kapun akadnak fenn. Igy a teszt
 * ingyenes es determinisztikus.
 */
import { callbackGreeting } from './prompt.js';
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, type ChildProcess } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import twilio from 'twilio';
import WebSocket from 'ws';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PORT = 18938; // kulon port: a testroute e2e a 18937-et hasznalja, parhuzamosan futnak
const SITE = 'https://aximbra.hu';
const TOKEN = 'e2e-teszt-token';
const HOST = 'voice.e2e-test.example';

let child: ChildProcess;

/** Alairt Twilio-keres - ugyanugy, ahogy a Twilio kuldene a hivas felvetelekor. */
async function twiml(pathAndQuery: string, params: Record<string, string>): Promise<string> {
  const url = `https://${HOST}${pathAndQuery}`;
  const res = await fetch(`http://127.0.0.1:${PORT}${pathAndQuery}`, {
    method: 'POST',
    headers: {
      'content-type': 'application/x-www-form-urlencoded',
      'x-twilio-signature': twilio.getExpectedTwilioSignature(TOKEN, url, params),
    },
    body: new URLSearchParams(params),
  });
  return res.text();
}

async function ask(
  body: unknown,
  origin: string | null = SITE,
): Promise<{ status: number; json: { ok: boolean; reason?: string }; cors: string | null }> {
  const res = await fetch(`http://127.0.0.1:${PORT}/callback`, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
      ...(origin ? { origin } : {}),
    },
    body: typeof body === 'string' ? body : JSON.stringify(body),
  });
  return {
    status: res.status,
    json: (await res.json()) as { ok: boolean; reason?: string },
    cors: res.headers.get('access-control-allow-origin'),
  };
}

test('a visszahivas-vegpont vedve van', async (t) => {
  child = spawn(process.execPath, [path.join(HERE, 'server.js')], {
    cwd: HERE,
    env: {
      ...process.env,
      SMOKE_TEST_SCENARIO: '',
      PORT: String(PORT),
      OPENAI_API_KEY: 'sk-test',
      TWILIO_AUTH_TOKEN: TOKEN,
      TWILIO_ACCOUNT_SID: 'ACe2e0123456789abcdef0123456789ab',
      PUBLIC_HOSTNAME: HOST,
      CALLBACK_FROM: '+18024249852',
      SITE_ORIGINS: SITE,
      MAX_CALLS_PER_DAY: '100',
      MAX_CALLBACKS_PER_DAY: '2',
    },
  });
  await new Promise((r) => setTimeout(r, 1200));

  await t.test('a hibas szam nem indit hivast', async () => {
    const r = await ask({ phone: 'hivj mar fel', lang: 'hu' });
    assert.equal(r.status, 400);
    assert.equal(r.json.reason, 'number');
  });

  await t.test('draga iranyba nem hivunk', async () => {
    // +882: muholdas, perce tobbe kerul, mint az egesz napi keret.
    const r = await ask({ phone: '+88212345678', lang: 'hu' });
    assert.equal(r.status, 400);
    assert.equal(r.json.reason, 'country');
  });

  await t.test('a tul hosszu mezo elakad a regexp elott', async () => {
    const r = await ask({ phone: `+36${'1'.repeat(400)}`, lang: 'hu' });
    assert.equal(r.status, 400);
    assert.equal(r.json.reason, 'number');
  });

  await t.test('a romlott JSON nem doszti le a szolgaltatast', async () => {
    const r = await ask('{ ez nem json', SITE);
    assert.equal(r.status, 400);
    assert.equal(r.json.reason, 'number');
  });

  await t.test('a sajat oldalunk megkapja a CORS-fejlecet', async () => {
    const r = await ask({ phone: 'rossz', lang: 'hu' }, SITE);
    assert.equal(r.cors, SITE);
  });

  await t.test('idegen oldal nem kapja meg', async () => {
    const r = await ask({ phone: 'rossz', lang: 'hu' }, 'https://tamado.example');
    assert.equal(r.cors, null, 'egy idegen lap nem inditkat hivast a latogatoja neveben');
  });

  await t.test('a preflight csak a sajat oldalunknak megy at', async () => {
    const ok = await fetch(`http://127.0.0.1:${PORT}/callback`, {
      method: 'OPTIONS',
      headers: { origin: SITE },
    });
    assert.equal(ok.status, 204);

    const bad = await fetch(`http://127.0.0.1:${PORT}/callback`, {
      method: 'OPTIONS',
      headers: { origin: 'https://tamado.example' },
    });
    assert.equal(bad.status, 403);
  });

  await t.test('GET-tel nem lehet hivast inditani', async () => {
    const res = await fetch(`http://127.0.0.1:${PORT}/callback`, {
      method: 'GET',
      headers: { origin: SITE },
    });
    assert.equal(res.status, 405);
  });

  await t.test('felveve: a kert nyelven szol, es megmondja, miert hivunk', async () => {
    const xml = await twiml('/twiml/callback?lang=hu', {
      CallSid: 'CA9123456789abcdef0123456789abcdef',
      CallStatus: 'in-progress',
      AnsweredBy: 'human',
    });
    assert.match(xml, /<ConversationRelay/);
    assert.match(xml, /ttsLanguage="hu-HU"/);
    assert.match(xml, /transcriptionLanguage="hu-HU"/);
    // A nyelvet a latogato mar kivalasztotta a lapon: itt nincs mit valasztani.
    assert.doesNotMatch(xml, /<Gather/, 'a visszahivasnal nincs nyelvvalaszto menu');
    assert.match(xml, /fix=1/, 'a lapon valasztott nyelvet ne irja felul a felismeres');
    // A koszonest nem a Twilio mondja ki a felvetel pillanataban (a felvevo
    // "Hallo"-ja belevagott): a relay koszon, egy masodperc csend utan vagy a
    // felvevo elso szavara. Ezt a cb=1 jelzi a relaynek.
    assert.doesNotMatch(xml, /welcomeGreeting=/);
    assert.match(xml, /cb=1/);
    // Ez a hivas TOLUNK indult: az elso mondatnak ezt ki kell mondania, es nem
    // koszonhetunk ugy, mintha az Aximbranak koszonnenk.
    assert.match(callbackGreeting('hu'), /visszahívást kért/);
    assert.match(callbackGreeting('hu'), /Az Aximbrától keresem/);
    assert.doesNotMatch(callbackGreeting('hu'), /Jó napot kívánok, Aximbra/);
  });

  await t.test('a hivas az UGYFEL szamat viszi tovabb, nem a sajatunkat', async () => {
    // Eles hiba, 2026-09-23, az elso valodi erdeklodonel. Kimeno hivasnal a
    // Twilio `From` mezojeben MI allunk, es az ugyfel a `To`. A relay a
    // `From`-ot vette hivonak, ezert a hivas utani SMS a sajat szamunkra
    // ment volna ("'To' and 'From' number cannot be the same"), az
    // osszefoglalo pedig a sajat szamunkat irta ugyfelkent - az erdeklodo
    // telefonszama elveszett. Az agent ra is olvasta a hivora a mi
    // szamunkat, sajatjakent.
    const xml = await twiml('/twiml/callback?lang=hu', {
      CallSid: 'CAd123456789abcdef0123456789abcdef',
      CallStatus: 'in-progress',
      AnsweredBy: 'human',
      From: '+18024249852', // mi
      To: '+36301300242',   // az erdeklodo
    });
    assert.match(xml, /peer=%2B36301300242/, 'az ugyfel szamanak at kell menni a relaynek');
    assert.doesNotMatch(xml, /peer=%2B18024249852/, 'a sajat szamunk nem az ugyfele');
    // `cb=1`: a relay ebbol tudja, hogy a visszahivas koszonese hangzott el,
    // nem a bejovo hivase - kulonben a modell ujra bemutatkozik.
    assert.match(xml, /cb=1/);
  });

  await t.test('hianyzo To eseten nem talalunk ki szamot', async () => {
    const xml = await twiml('/twiml/callback?lang=hu', {
      CallSid: 'CAe123456789abcdef0123456789abcdef',
      CallStatus: 'in-progress',
      AnsweredBy: 'human',
      From: '+18024249852',
    });
    assert.doesNotMatch(xml, /peer=/, 'ures To-bol ne szulessen hamis ugyfelszam');
    assert.match(xml, /<ConversationRelay/, 'a beszelgetes ettol meg induljon el');
  });

  await t.test('angolul kert visszahivas angolul szol', async () => {
    const xml = await twiml('/twiml/callback?lang=en', {
      CallSid: 'CAa123456789abcdef0123456789abcdef',
      CallStatus: 'in-progress',
      AnsweredBy: 'human',
    });
    assert.match(xml, /ttsLanguage="en-US"/);
    assert.match(callbackGreeting('en'), /call you back/);
  });

  // A relay-socketen: mikor koszonunk a visszahivasban.
  const relay = async (
    afterSetup: (ws: WebSocket) => void,
  ): Promise<{ texts: string[]; ms: number }> => {
    const ws = new WebSocket(`ws://127.0.0.1:${PORT}/relay?lang=hu&fix=1&cb=1`);
    await new Promise<void>((ok, bad) => { ws.once('open', () => ok()); ws.once('error', bad); });
    const texts: string[] = [];
    const t0 = Date.now();
    let first = -1;
    ws.on('message', (raw) => {
      const m = JSON.parse(String(raw)) as { type?: string; token?: string };
      if (m.type === 'text' && m.token) {
        if (first < 0) first = Date.now() - t0;
        texts.push(m.token);
      }
    });
    ws.send(JSON.stringify({ type: 'setup', from: '+18024249852', callSid: 'CAe2e' }));
    afterSetup(ws);
    await new Promise((r) => setTimeout(r, 1900));
    ws.close();
    return { texts, ms: first };
  };

  await t.test('visszahivas: ha a felvevo hallgat, fel masodpercen belul mi koszonunk', async () => {
    const r = await relay(() => {});
    assert.equal(r.texts.length, 1, `egy koszones: ${JSON.stringify(r.texts)}`);
    assert.match(r.texts[0]!, /Az Aximbrától keresem/);
    assert.ok(r.ms >= 150 && r.ms < 500, `a koszones ${r.ms} ms utan jott`);
  });

  await t.test('visszahivas: ha a felvevo szol elobb, arra rogton koszonunk, egyszer', async () => {
    const r = await relay((ws) => {
      ws.send(JSON.stringify({ type: 'prompt', voicePrompt: 'Halló, Kovács Péter.', last: true }));
    });
    assert.equal(r.texts.length, 1, `egy koszones: ${JSON.stringify(r.texts)}`);
    assert.match(r.texts[0]!, /Az Aximbrától keresem/);
    assert.ok(r.ms < 500, `a koszones ${r.ms} ms utan jott`);
  });

  await t.test('visszahivas: amig a felvevo beszel, nem vagunk bele', async () => {
    const r = await relay((ws) => {
      // 0,1 s: elkezd beszelni (clientSpeaking), a vegleges prompt csak 1,4 s-nal jon.
      setTimeout(() => ws.send(JSON.stringify({ type: 'info', name: 'clientSpeaking', value: 'on' })), 100);
      setTimeout(() => ws.send(JSON.stringify({ type: 'prompt', voicePrompt: 'Halló, Kovács Péter vagyok.', last: true })), 1400);
    });
    assert.equal(r.texts.length, 1, `egy koszones: ${JSON.stringify(r.texts)}`);
    assert.ok(r.ms >= 1350, `a koszones ${r.ms} ms utan jott - a felvevo meg beszelt`);
  });

  await t.test('uzenetrogzitonek nem beszelunk', async () => {
    for (const answeredBy of ['machine_start', 'machine_end_beep', 'fax']) {
      const xml = await twiml('/twiml/callback?lang=hu', {
        CallSid: 'CAb123456789abcdef0123456789abcdef',
        CallStatus: 'in-progress',
        AnsweredBy: answeredBy,
      });
      assert.match(xml, /<Hangup/, `${answeredBy}: bontani kell`);
      assert.doesNotMatch(xml, /<ConversationRelay/, `${answeredBy}: nem beszelgetunk vele`);
    }
  });

  await t.test('alairas nelkul a hivas-TwiML nem kerheto le', async () => {
    const res = await fetch(`http://127.0.0.1:${PORT}/twiml/callback?lang=hu`, {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ CallSid: 'CAc123456789abcdef0123456789abcdef' }),
    });
    assert.equal(res.status, 403);
  });

  await t.test('a health megmondja, hogy a gomb bekapcsolhato-e', async () => {
    const res = await fetch(`http://127.0.0.1:${PORT}/health`);
    const data = (await res.json()) as { callback?: boolean };
    assert.equal(data.callback, true, 'a lap ebbol tudja, hogy megjelenitse-e a gombot');
  });

  child.kill();
});

test('kikapcsolt visszahivas eseten a vegpont nem letezik funkciokent', async (t) => {
  const port = PORT + 1;
  const off = spawn(process.execPath, [path.join(HERE, 'server.js')], {
    cwd: HERE,
    env: {
      ...process.env,
      SMOKE_TEST_SCENARIO: '',
      PORT: String(port),
      OPENAI_API_KEY: 'sk-test',
      TWILIO_AUTH_TOKEN: 'e2e-teszt-token',
      PUBLIC_HOSTNAME: 'voice.e2e-test.example',
      // Nincs TWILIO_ACCOUNT_SID -> nincs kimeno hivas.
      TWILIO_ACCOUNT_SID: '',
      SITE_ORIGINS: SITE,
    },
  });
  await new Promise((r) => setTimeout(r, 1200));

  await t.test('a keres 503-at kap, nem egy fel-mukodo urlapot', async () => {
    const res = await fetch(`http://127.0.0.1:${port}/callback`, {
      method: 'POST',
      headers: { 'content-type': 'application/json', origin: SITE },
      body: JSON.stringify({ phone: '+36301234567', lang: 'hu' }),
    });
    assert.equal(res.status, 503);
    assert.equal(((await res.json()) as { reason?: string }).reason, 'disabled');
  });

  await t.test('es a health sem hazudik rola', async () => {
    const res = await fetch(`http://127.0.0.1:${port}/health`);
    assert.equal(((await res.json()) as { callback?: boolean }).callback, false);
  });

  off.kill();
});
