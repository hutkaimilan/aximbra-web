/**
 * Vegponti teszt: a /test oldal legordulo menuje tenylegesen azt a
 * forgatokonyvet inditja-e el, amit kivalasztottak.
 *
 * Elesben kiderult, hogy nem: a bongeszo <form method="POST"> a <select>
 * erteket a POST-torzsben kuldi, a /test/start kezelo viszont a lekerdezes-
 * stringbol (`query.get('scenario')`) probalta kiolvasni - ami ott sosem
 * szerepelt, csak a token. Minden inditas csendben az "alap" forgatokonyvre
 * esett vissza, akkor is, ha a menuben mast valasztottak. Erre az arult el,
 * hogy a "Korabbi futasok" kozott soha nem jelent meg mas cimke.
 *
 * A Twilio-hivast szandekosan ervenytelen adatokkal futtatjuk: a hivas maga
 * elbukik, de a futas mar korabban, a helyes cimkevel letrejott - ezt
 * ellenorizzuk.
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawn, type ChildProcess } from 'node:child_process';
import path from 'node:path';
import fs from 'node:fs/promises';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PORT = 18937;
const TOKEN = 'testroute-e2e-token';

test('a legordulo menuben valasztott forgatokonyv inditja a hivast, nem mindig az alap', async (t) => {
  const runsDir = await fs.mkdtemp(path.join(os.tmpdir(), 'aximbra-test-runs-'));
  const child: ChildProcess = spawn(process.execPath, [path.join(HERE, 'server.js')], {
    cwd: HERE,
    env: {
      ...process.env,
      PORT: String(PORT),
      OPENAI_API_KEY: 'sk-test',
      TEST_AGENT_TOKEN: TOKEN,
      TEST_AGENT_FROM: '+19498107263',
      TEST_AGENT_TARGET: '+18024249852',
      TEST_RUNS_DIR: runsDir,
      PUBLIC_HOSTNAME: 'voice.testroute-e2e.example',
      // Ervenytelen, de alaki - a Twilio SDK igy engedi elinditani a hivast,
      // ami aztan halozati/hitelesitesi hibaval elbukik. A futas rekordja
      // (helyes cimkevel) mar ekkor letezik.
      TWILIO_ACCOUNT_SID: 'AC00000000000000000000000000000000',
      TWILIO_AUTH_TOKEN: 'invalid',
    },
  });
  await new Promise((r) => setTimeout(r, 1200));

  try {
    // Pontosan azt kuldjuk, amit a bongeszo <form method="POST"> kuldene: a
    // scenario a POST-torzsben van, a token a lekerdezes-stringben.
    await fetch(`http://127.0.0.1:${PORT}/test/start?token=${TOKEN}`, {
      method: 'POST',
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ scenario: 'kulfoldi' }),
    });

    // A hivasinditas maga elbukik (hibas Twilio-hitelesites), de a futas
    // rekordja mar a helyes cimkevel jott letre - lasd startTestCall().
    const files = await fs.readdir(runsDir);
    assert.equal(files.length, 1, 'pontosan egy futas jott letre');
    const saved = JSON.parse(await fs.readFile(path.join(runsDir, files[0]!), 'utf8'));
    assert.equal(saved.scenario, 'English caller (foreign number)');
  } finally {
    child.kill();
    await fs.rm(runsDir, { recursive: true, force: true });
  }
});
