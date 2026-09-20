/**
 * Vegponti teszt: elindit egy valodi peldanyt, es alairt Twilio-keresekkel
 * ellenorzi a /twiml valaszat.
 *
 * A nyelvvalasztas tortenete harom eles hibabol all, es mindharom azert
 * tortent, mert a nyelvet KITALALNI probaltuk:
 *
 * 1. (2026-09-17) Egy `language` attributum allitotta a felolvasast es a
 *    felismerest is. A nem +36-os, de magyarul beszelo hivo atirata
 *    hasznalhatatlan lett.
 * 2. (2026-09-20) A javitas a felismerest `hu-HU`-ra szogezte - amivel az
 *    angolul beszelo hivo jart ugyanigy: "We hiv fix People Using Email
 *    Regularly".
 * 3. (2026-09-20) A hivoszam szerinti angol indulas mellett a magyar hivo
 *    mondatabol "Hello. Hi. Amit Mondock." lett, amibol mar a
 *    nyelvfelismeres sem tudott visszatalalni.
 *
 * Ezert dont most a HIVO, gombnyomassal. A DTMF-jel nyelvfuggetlen: nincs
 * mit felreismerni rajta. Amit a teszt orzik:
 *   - a hivas nyelvvalaszto menuvel kezd, mindket nyelven,
 *   - a gomb valasztja a nyelvet, es a valasztas `fix=1`-gyel vedve van,
 *   - gomb nelkul magyarul folytatjuk, de vedelem nelkul, hogy a
 *     beszedfelismeres meg korrigalhasson,
 *   - a felolvasas es a felismeres soha nem csuszik szet,
 *   - mindket nyelv `<Language>` gyerekkent fel van veve, kulonben a hivas
 *     kozbeni valtas ervenytelen nyelvre mutatna.
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

async function post(
  pathAndQuery: string,
  params: Record<string, string>,
  port: number = PORT,
): Promise<string> {
  const body = new URLSearchParams(params);
  const url = `https://${HOST}${pathAndQuery}`;
  const signature = twilio.getExpectedTwilioSignature(TOKEN, url, params);
  const res = await fetch(`http://127.0.0.1:${port}${pathAndQuery}`, {
    method: 'POST',
    headers: {
      'content-type': 'application/x-www-form-urlencoded',
      'x-twilio-signature': signature,
    },
    body,
  });
  return res.text();
}

/** Amit minden osszekapcsolasnal el kell varni, barmelyik nyelven. */
function assertSwitchable(xml: string): void {
  assert.doesNotMatch(xml, /\blanguage="/, 'a ketertelmu `language` attributum nem terhet vissza');
  assert.match(xml, /<Language code="hu-HU"/, 'hu-HU nelkul nem lehet magyarra valtani');
  assert.match(xml, /<Language code="en-US"/, 'en-US nelkul nem lehet angolra valtani');
}

function ring(sid: string): Record<string, string> {
  return { From: '+19498107263', To: '+18024249852', CallSid: sid, CallStatus: 'ringing' };
}

test('a hivas nyelvvalaszto menuvel kezd, es a gomb dont', async (t) => {
  child = spawn(process.execPath, [path.join(HERE, 'server.js')], {
    cwd: HERE,
    env: {
      ...process.env,
      SMOKE_TEST_SCENARIO: '',
      PORT: String(PORT),
      OPENAI_API_KEY: 'sk-test',
      TWILIO_AUTH_TOKEN: TOKEN,
      PUBLIC_HOSTNAME: HOST,
      MAX_CALLS_PER_DAY: '100',
    },
  });
  await new Promise((r) => setTimeout(r, 1200));

  await t.test('elobb magyarul, aztan ugyanaz angolul', async () => {
    const xml = await post('/twiml', ring('CA0123456789abcdef0123456789abcdef'));

    assert.match(xml, /<Gather numDigits="1"/);
    assert.match(xml, /action="https:\/\/[^"]+\/twiml\/lang"/);

    const hu = xml.indexOf('language="hu-HU"');
    const en = xml.indexOf('language="en-US"');
    assert.ok(hu > -1 && en > -1, 'mindket nyelven el kell hangoznia');
    assert.ok(hu < en, 'a magyar szoveg jon elobb');

    // Mindket nyelvu szoveg mindket gombot felkinalja - aki csak az egyiket
    // erti, annak is tudnia kell, mit nyomjon.
    assert.match(xml, /nyomja meg az egyes gombot/);
    assert.match(xml, /nyomja meg a kettes gombot/);
    assert.match(xml, /press one/);
    assert.match(xml, /press two/);

    // A beszelgetes meg nem indulhat el: elobb valasztani kell.
    assert.doesNotMatch(xml, /<ConversationRelay/);
  });

  await t.test('1-es gomb: magyar, es a valasztas vedve van', async () => {
    const xml = await post('/twiml/lang', {
      ...ring('CA1123456789abcdef0123456789abcdef'),
      Digits: '1',
    });
    assert.match(xml, /ttsLanguage="hu-HU"/);
    assert.match(xml, /transcriptionLanguage="hu-HU"/);
    assert.match(xml, /\/relay\?lang=hu&amp;fix=1/, 'a valasztott nyelv nem irhato felul');
    assertSwitchable(xml);
  });

  await t.test('2-es gomb: angol, es a valasztas vedve van', async () => {
    const xml = await post('/twiml/lang', {
      ...ring('CA2123456789abcdef0123456789abcdef'),
      Digits: '2',
    });
    assert.match(xml, /ttsLanguage="en-US"/);
    assert.match(xml, /transcriptionLanguage="en-US"/);
    assert.match(xml, /\/relay\?lang=en&amp;fix=1/);
    assertSwitchable(xml);
  });

  await t.test('gomb nelkul: magyar, de a felismeres meg korrigalhat', async () => {
    const xml = await post('/twiml/lang', ring('CA3123456789abcdef0123456789abcdef'));
    assert.match(xml, /ttsLanguage="hu-HU"/);
    assert.match(xml, /transcriptionLanguage="hu-HU"/);
    assert.doesNotMatch(xml, /fix=1/, 'ez nem a hivo dontese volt, nem is vedjuk');
    assertSwitchable(xml);
  });

  await t.test('ismeretlen gomb ugyanaz, mint a gomb nelkul', async () => {
    for (const d of ['0', '9', '#', '']) {
      const xml = await post('/twiml/lang', {
        ...ring('CA4123456789abcdef0123456789abcde' + (d === '' ? '0' : d.charCodeAt(0) % 10)),
        Digits: d,
      });
      assert.match(xml, /ttsLanguage="hu-HU"/, `gomb=${d}`);
      assert.doesNotMatch(xml, /fix=1/, `gomb=${d}`);
    }
  });

  await t.test('a felolvasas es a felismeres soha nem csuszik szet', async () => {
    for (const d of ['1', '2', '']) {
      const xml = await post('/twiml/lang', {
        ...ring('CA5123456789abcdef0123456789abcde' + (d === '' ? '3' : d)),
        Digits: d,
      });
      const tts = /ttsLanguage="([^"]+)"/.exec(xml)?.[1];
      const stt = /transcriptionLanguage="([^"]+)"/.exec(xml)?.[1];
      assert.equal(stt, tts, `gomb=${d}: ${String(tts)} felolvasas, de ${String(stt)} felismeres`);
    }
  });

  child.kill();
});

/**
 * A kulon angol szam: aki azt tarcsazta, mar dontott, neki a menu csak
 * idorablas lenne.
 */
const EN_PORT = 18934;
const EN_NUMBER = '+441234567890';

test('ENGLISH_PHONE_NUMBER: menu nelkul, egyenesen angolul', async (t) => {
  const en = spawn(process.execPath, [path.join(HERE, 'server.js')], {
    cwd: HERE,
    env: {
      ...process.env,
      SMOKE_TEST_SCENARIO: '',
      PORT: String(EN_PORT),
      OPENAI_API_KEY: 'sk-test',
      TWILIO_AUTH_TOKEN: TOKEN,
      PUBLIC_HOSTNAME: HOST,
      MAX_CALLS_PER_DAY: '100',
      ENGLISH_PHONE_NUMBER: EN_NUMBER,
    },
  });
  await new Promise((r) => setTimeout(r, 1200));

  await t.test('az angol szamon nincs menu, csak angol beszelgetes', async () => {
    const xml = await post(
      '/twiml',
      {
        From: '+36209876543', // magyar szam, megis az angol vonalat hivta
        To: EN_NUMBER,
        CallSid: 'CA6123456789abcdef0123456789abcdef',
        CallStatus: 'ringing',
      },
      EN_PORT,
    );
    assert.doesNotMatch(xml, /<Gather/, 'itt nincs mit valasztani');
    assert.match(xml, /ttsLanguage="en-US"/);
    assert.match(xml, /transcriptionLanguage="en-US"/);
    assert.match(xml, /fix=1/, 'a szam maga a dontes');
    assertSwitchable(xml);
  });

  await t.test('a masik szamon valtozatlanul jon a menu', async () => {
    const xml = await post('/twiml', ring('CA7123456789abcdef0123456789abcdef'), EN_PORT);
    assert.match(xml, /<Gather numDigits="1"/);
  });

  en.kill();
});
