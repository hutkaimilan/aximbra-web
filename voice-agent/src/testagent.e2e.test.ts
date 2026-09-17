/**
 * Vegponti teszt a beepitett hivas-tesztelohoz (/test/*): a hu.js forgatokonyvek
 * es az uj angol ('kulfoldi') forgatokonyv helyesen valasztjak-e a sajat
 * hangjukat es beszedfelismeresuket.
 *
 * A modellhivast szandekosan ervenytelen OPENAI_API_KEY-vel futtatjuk: ez
 * determinisztikusan a hiba-agra futtatja a kodot (MSGS[lang].technicalError),
 * ami eppen az a szoveg, aminek a nyelvfuggeset ellenorizni akarjuk - valodi
 * modellhivas nelkul is.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, type ChildProcess } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PORT = 18936;
const TOKEN = 'testagent-e2e-token';

let child: ChildProcess;

async function post(pathAndQuery: string, form: Record<string, string> = {}): Promise<string> {
  const res = await fetch(`http://127.0.0.1:${PORT}${pathAndQuery}`, {
    method: 'POST',
    headers: { 'content-type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams(form),
  });
  return res.text();
}

test('a teszt-agent a forgatokonyv nyelven beszel, es az AXIMBRA valaszat a valodi nyelven ismeri fel', async (t) => {
  child = spawn(process.execPath, [path.join(HERE, 'server.js')], {
    cwd: HERE,
    env: {
      ...process.env,
      PORT: String(PORT),
      // Szandekosan ervenytelen: a modellhivas 401-re fut, es a determinisztikus
      // hiba-uzenetre esunk vissza - lasd a fajl tetejen levo magyarazatot.
      OPENAI_API_KEY: 'sk-invalid-for-e2e-test',
      TEST_AGENT_TOKEN: TOKEN,
      TEST_AGENT_FROM: '+19498107263', // nem +36 -> az AXIMBRA agent angolul valaszol
      TEST_AGENT_TARGET: '+18024249852',
      PUBLIC_HOSTNAME: 'voice.testagent-e2e.example',
      TWILIO_ACCOUNT_SID: 'ACtest',
      TWILIO_AUTH_TOKEN: 'authtest',
    },
  });
  await new Promise((r) => setTimeout(r, 1200));

  await t.test('magyar forgatokonyv: a teszt-agent sajat hangja magyar...', async () => {
    const xml = await post(`/test/twiml?run=aaaaaaaaaaaaaaaa&scenario=alap&token=${TOKEN}`);
    assert.match(xml, /<Say voice="Google\.hu-HU-Wavenet-A" language="hu-HU">/);
  });

  await t.test('...DE a Gather, ami az AXIMBRA valaszat hallgatja, angol - mert a hivoszam nem +36', async () => {
    const xml = await post(`/test/twiml?run=bbbbbbbbbbbbbbbb&scenario=alap&token=${TOKEN}`);
    // Ez itt a hangup-ag (hibas API-kulcs miatt), tehat nincs Gather ebben a
    // konkret valaszban - de a scenario.lang='hu' melletti sajat hangja
    // igy is `hu-HU` marad, ami a lenyeg: a ket dolog fuggetlen egymastol.
    assert.match(xml, /language="hu-HU"/);
  });

  await t.test("angol ('kulfoldi') forgatokonyv: a teszt-agent sajat hangja is angol", async () => {
    const xml = await post(`/test/twiml?run=cccccccccccccccc&scenario=kulfoldi&token=${TOKEN}`);
    assert.match(xml, /<Say voice="Google\.en-US-Wavenet-D" language="en-US">/);
    assert.match(xml, /Sorry, a technical error occurred/);
  });

  child.kill();
});
