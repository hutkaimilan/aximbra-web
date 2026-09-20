/**
 * Vegponti teszt: elindit egy valodi peldanyt, es alairt Twilio-keresekkel
 * ellenorzi a /twiml valaszat.
 *
 * Ket eleshibat orzunk itt egyszerre, mert egymasbol kovetkeztek:
 *
 * 1. (2026-09-17) A relayTwiml a `language` attributumot hasznalta, ami
 *    EGYSZERRE allitja a TTS-t es a felismerest. Egy nem +36-os, de magyarul
 *    beszelo hivonal a felismeres angolra allt, es az egesz atirat
 *    ertelmezhetetlen lett.
 * 2. (2026-09-20) A javitas ezert MINDIG `hu-HU`-ra allitotta a felismerest -
 *    amivel az angolul beszelo hivo jart pontosan ugyanigy. A `kulfoldi`
 *    forgatokonyv atirata ezt mutatta: "We hiv fix People Using Email
 *    Regularly".
 *
 * A mostani mukodes: a hivoszam csak a KEZDO nyelvet tippeli meg, a ketto
 * egyutt mozog, es a hivas kozben a hivo elso mondata allithatja at
 * (server.ts, `maybeSwitchLang`). Ehhez ket dolog kell a TwiML-ben, es ezt
 * ellenorzi a teszt: a ketertelmu `language=` nem terhet vissza, es MINDKET
 * nyelv `<Language>` gyerekkent fel kell legyen veve - egy nem deklaralt
 * nyelvre a valtas ervenytelen lenne.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, type ChildProcess } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import twilio from 'twilio';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const TOKEN = 'e2e-teszt-token';
const HOST = 'voice.e2e-test.example';
const PORT = 18933;

let child: ChildProcess;

async function post(pathAndQuery: string, params: Record<string, string>): Promise<string> {
  const body = new URLSearchParams(params);
  const url = `https://${HOST}${pathAndQuery}`;
  const signature = twilio.getExpectedTwilioSignature(TOKEN, url, params);
  const res = await fetch(`http://127.0.0.1:${PORT}${pathAndQuery}`, {
    method: 'POST',
    headers: {
      'content-type': 'application/x-www-form-urlencoded',
      'x-twilio-signature': signature,
    },
    body,
  });
  return res.text();
}

/** Amit minden hivasnal el kell varni, barmilyen nyelven indul. */
function assertSwitchable(xml: string): void {
  assert.doesNotMatch(xml, /\blanguage="/, 'a ketertelmu `language` attributum nem terhet vissza');
  assert.match(xml, /<Language code="hu-HU"/, 'hu-HU nelkul nem lehet magyarra valtani');
  assert.match(xml, /<Language code="en-US"/, 'en-US nelkul nem lehet angolra valtani');
}

test('relayTwiml: a felolvasas es a felismeres egyutt indul, es valthato', async (t) => {
  child = spawn(process.execPath, [path.join(HERE, 'server.js')], {
    cwd: HERE,
    env: {
      ...process.env,
      // Egy teszt soha nem inditson valodi telefonhivast, meg akkor
      // sem, ha a futtato gepen veletlenul be van allitva.
      SMOKE_TEST_SCENARIO: '',
      PORT: String(PORT),
      OPENAI_API_KEY: 'sk-test',
      TWILIO_AUTH_TOKEN: TOKEN,
      PUBLIC_HOSTNAME: HOST,
      MAX_CALLS_PER_DAY: '100',
    },
  });
  await new Promise((r) => setTimeout(r, 1200));

  await t.test('magyar (+36) hivo: vegig magyarul indul', async () => {
    const xml = await post('/twiml', {
      From: '+36209876543',
      To: '+18024249852',
      CallSid: 'CA0123456789abcdef0123456789abcdef',
      CallStatus: 'ringing',
    });
    assert.match(xml, /ttsLanguage="hu-HU"/);
    assert.match(xml, /transcriptionLanguage="hu-HU"/);
    assertSwitchable(xml);
  });

  await t.test('kulfoldi szam: vegig angolul indul - a felismeres is', async () => {
    const xml = await post('/twiml', {
      From: '+19498107263',
      To: '+18024249852',
      CallSid: 'CA1123456789abcdef0123456789abcdef',
      CallStatus: 'ringing',
    });
    // Ez volt a 2026-09-20-i hiba: itt `hu-HU` allt, es az angolul beszelo
    // hivo minden mondatat magyar felismero irta at.
    assert.match(xml, /ttsLanguage="en-US"/);
    assert.match(xml, /transcriptionLanguage="en-US"/);
    assertSwitchable(xml);
  });

  await t.test('rejtett szam: magyarul indul, mert az oldal kozonsege magyar', async () => {
    const xml = await post('/twiml', {
      From: 'anonymous',
      To: '+18024249852',
      CallSid: 'CA2123456789abcdef0123456789abcdef',
      CallStatus: 'ringing',
    });
    assert.match(xml, /ttsLanguage="hu-HU"/);
    assert.match(xml, /transcriptionLanguage="hu-HU"/);
    assertSwitchable(xml);
  });

  await t.test('a felolvasas es a felismeres soha nem csuszik szet indulaskor', async () => {
    for (const from of ['+36209876543', '+19498107263', 'anonymous', '+4915112345678']) {
      const xml = await post('/twiml', {
        From: from,
        To: '+18024249852',
        CallSid: 'CA3123456789abcdef0123456789abcde' + (from.length % 10),
        CallStatus: 'ringing',
      });
      const tts = /ttsLanguage="([^"]+)"/.exec(xml)?.[1];
      const stt = /transcriptionLanguage="([^"]+)"/.exec(xml)?.[1];
      assert.equal(stt, tts, `${from}: ${String(tts)} felolvasas, de ${String(stt)} felismeres`);
    }
  });

  child.kill();
});
