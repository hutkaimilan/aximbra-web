/**
 * Vegponti teszt: elindit egy valodi peldanyt, es alairt Twilio-keresekkel
 * ellenorzi a /twiml valaszat.
 *
 * Ez pontosan azt a hibat fogja meg, ami elesben tortent 2026-09-17-en: a
 * relayTwiml a `language` attributumot hasznalta, ami EGYSZERRE allitja a
 * TTS-t es a felismerest. Egy nem +36-tal kezdodo, de magyarul beszelo
 * hivonal ez angolra kapcsolta a felismerest, es a teszt-agent egesz
 * beszelgetese ertelmezhetetlen szoveggé vált (lasd a hiba leirasat a
 * commit-uzenetben). A felismeresnek MINDIG magyarnak kell maradnia,
 * fuggetlenul attol, honnan hiv valaki - csak a koszones es a hang
 * valtozhat a hivo szama szerint.
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

test('relayTwiml: a felismeres mindig magyar, akartol hivja is fel', async (t) => {
  child = spawn(process.execPath, [path.join(HERE, 'server.js')], {
    cwd: HERE,
    env: {
      ...process.env,
      PORT: String(PORT),
      OPENAI_API_KEY: 'sk-test',
      TWILIO_AUTH_TOKEN: TOKEN,
      PUBLIC_HOSTNAME: HOST,
      MAX_CALLS_PER_DAY: '100',
    },
  });
  await new Promise((r) => setTimeout(r, 1200));

  await t.test('magyar (+36) hivo: magyar koszones es magyar felismeres', async () => {
    const xml = await post('/twiml', {
      From: '+36209876543',
      To: '+18024249852',
      CallSid: 'CA0123456789abcdef0123456789abcdef',
      CallStatus: 'ringing',
    });
    assert.match(xml, /transcriptionLanguage="hu-HU"/);
    assert.match(xml, /ttsLanguage="hu-HU"/);
    assert.doesNotMatch(xml, /\blanguage="/, 'a ketertelmu `language` attributum nem terhet vissza');
  });

  await t.test('kulfoldi szam: angol koszones, DE a felismeres akkor is magyar', async () => {
    const xml = await post('/twiml', {
      From: '+19498107263',
      To: '+18024249852',
      CallSid: 'CA1123456789abcdef0123456789abcdef',
      CallStatus: 'ringing',
    });
    // Ez a sor a lenyeg: eleshiba volt, hogy ez korabban "en-US" lett.
    assert.match(xml, /transcriptionLanguage="hu-HU"/);
    assert.match(xml, /ttsLanguage="en-US"/);
    assert.doesNotMatch(xml, /\blanguage="/);
  });

  await t.test('rejtett szam: magyar koszones es magyar felismeres', async () => {
    const xml = await post('/twiml', {
      From: 'anonymous',
      To: '+18024249852',
      CallSid: 'CA2123456789abcdef0123456789abcdef',
      CallStatus: 'ringing',
    });
    assert.match(xml, /transcriptionLanguage="hu-HU"/);
    assert.match(xml, /ttsLanguage="hu-HU"/);
  });

  child.kill();
});
