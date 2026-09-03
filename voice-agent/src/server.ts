/**
 * AXIMBRA telefonos agent.
 *
 * Ket vegpont:
 *   POST /twiml  - Twilio webhook. Eldonti, fogadjuk-e a hivast, es
 *                  visszaadja a ConversationRelay konfiguraciot.
 *   WS   /relay  - a beszelgetes maga. A Twilio ide kuldi a leiratot,
 *                  es innen varja a kimondando szoveget.
 *
 * A ConversationRelay-t hasznaljuk sajat hangfeldolgozas helyett: a Twilio
 * intezi a beszed-szoveg es szoveg-beszed atalakitast, a felbeszakitast es
 * a puffereles. Nekunk csak a "mit valaszoljon" resz marad. Ez nagysagrenddel
 * kevesebb kod, es kevesebb hely, ahol elromolhat egy elo hivas.
 */

import http from 'node:http';
import crypto from 'node:crypto';
import { WebSocketServer, type WebSocket } from 'ws';

import { env } from './env.js';
import { admitCall, callStarted, callEnded, maxCallSeconds, stats } from './limit.js';
import { reply, summarize, type Turn } from './llm.js';
import { sendSummary } from './email.js';
import { sendContactSms } from './sms.js';
import { handleTestRoute, handleTestRelay } from './testAgent.js';
import {
  GREETING,
  FAILURE_MESSAGE,
  TIME_LIMIT_MESSAGE,
  buildSystemPrompt,
} from './prompt.js';

const cfg = env();

/* ------------------------------------------------------------------ */
/* TwiML                                                               */
/* ------------------------------------------------------------------ */

function escapeXml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

function relayTwiml(host: string): string {
  // A <Language> gyerekelemek nyelvenkent adjak meg a hangot es a
  // felismerest. Ket nyelv van felveve: magyar az alap, angol pedig azert,
  // hogy a hivas kozbeni nyelvvaltas ne ervenytelen konfiguraciora fusson.
  return `<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <ConversationRelay
      url="wss://${escapeXml(host)}/relay"
      welcomeGreeting="${escapeXml(GREETING)}"
      language="hu-HU"
      ttsProvider="${escapeXml(cfg.ttsProvider)}"
      voice="${escapeXml(cfg.ttsVoice)}"
      interruptible="speech"
      interruptSensitivity="${escapeXml(process.env['INTERRUPT_SENSITIVITY'] ?? 'low')}"
      speechTimeout="${escapeXml(process.env['SPEECH_TIMEOUT'] ?? '1500')}"
      ignoreBackchannel="true"
      welcomeGreetingInterruptible="none"
      reportInputDuringAgentSpeech="none">
      <Language code="hu-HU" ttsProvider="${escapeXml(cfg.ttsProvider)}" voice="${escapeXml(cfg.ttsVoice)}" />
      <Language code="en-US" ttsProvider="Google" voice="en-US-Wavenet-F" />
    </ConversationRelay>
  </Connect>
</Response>`;
}


/**
 * Elutasito valasz.
 *
 * Szandekosan beszelunk, nem <Reject>-elunk: egy foglalt jelzes egy
 * marketingoldalon szereplo szamnal ugy hangzik, mintha a ceg nem letezne.
 * Tiz masodperc beszed olcsobb, mint az elvesztett bizalom.
 */
function rejectTwiml(reason: 'daily' | 'concurrent'): string {
  const message =
    reason === 'concurrent'
      ? 'Köszönjük a hívást. Jelenleg minden vonalunk foglalt, kérjük, próbálja újra néhány perc múlva. Viszonthallásra!'
      : 'Köszönjük a hívást. A bemutató vonal mai kerete betelt. Kérjük, írjon nekünk az aximbra kukac gmail pont com címre, vagy próbálja meg holnap. Viszonthallásra!';

  return `<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="${escapeXml(cfg.sayVoice)}" language="${escapeXml(cfg.ttsLanguage)}">${escapeXml(message)}</Say>
  <Hangup/>
</Response>`;
}

/* ------------------------------------------------------------------ */
/* Twilio signature                                                     */
/* ------------------------------------------------------------------ */

/**
 * Twilio keres-alairas ellenorzese.
 *
 * Sajat implementacio a twilio SDK helyett: a teljes SDK behuzasa egyetlen
 * HMAC miatt felesleges fuggoseg. Az algoritmus dokumentalt es stabil.
 *
 * A publikus hostot env-bol vesszuk, nem a Host fejlecbol: proxy mogott a
 * fejlec hamisithato, es akkor az alairas-ellenorzes megkerulheto lenne.
 */
function validTwilioSignature(
  signature: string | undefined,
  url: string,
  params: URLSearchParams,
): boolean {
  if (!signature) return false;

  const sorted = [...params.keys()].sort();
  let payload = url;
  for (const key of sorted) {
    payload += key + (params.get(key) ?? '');
  }

  const expected = crypto
    .createHmac('sha1', cfg.twilioAuthToken)
    .update(Buffer.from(payload, 'utf8'))
    .digest('base64');

  const a = Buffer.from(signature);
  const b = Buffer.from(expected);
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

function readBody(req: http.IncomingMessage): Promise<string> {
  return new Promise((resolve, reject) => {
    let data = '';
    let size = 0;
    req.on('data', (chunk: Buffer) => {
      size += chunk.length;
      // Egy Twilio webhook nehany kilobajt. A felso hatar egy elgepelt
      // vagy rosszindulatu keres ellen ved.
      if (size > 64 * 1024) {
        reject(new Error('tul nagy keres'));
        req.destroy();
        return;
      }
      data += chunk.toString('utf8');
    });
    req.on('end', () => resolve(data));
    req.on('error', reject);
  });
}

/* ------------------------------------------------------------------ */
/* HTTP                                                                 */
/* ------------------------------------------------------------------ */

const server = http.createServer((req, res) => {
  const rawUrl = req.url ?? '/';
  const path = rawUrl.split('?')[0]!;
  const query = new URLSearchParams(rawUrl.includes('?') ? rawUrl.slice(rawUrl.indexOf('?') + 1) : '');

  // A teszt-agent sajat utvonalai. Kulon modulban, hogy egy hiba itt ne
  // erintse az eles hivasfogadast.
  if (path.startsWith('/test')) {
    void (async () => {
      try {
        // A Twilio urlencoded torzsben kuldi a SpeechResult-ot es a
        // CallDuration-t. GET-nel nincs torzs, ezert csak POST-nal olvassuk.
        const form =
          req.method === 'POST'
            ? new URLSearchParams(await readBody(req))
            : undefined;

        const out = await handleTestRoute(req.method ?? 'GET', path, query, form);
        if (!out) {
          res.writeHead(404, { 'content-type': 'text/plain' });
          res.end('not found');
          return;
        }
        res.writeHead(out.status, out.headers);
        res.end(out.body);
      } catch (err) {
        console.error('[test] utvonal hiba:', err);
        res.writeHead(500, { 'content-type': 'text/plain' });
        res.end('hiba');
      }
    })();
    return;
  }

  if (req.method === 'GET' && (path === '/health' || path === '/')) {
    res.writeHead(200, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ ok: true, ...stats() }));
    return;
  }

  if (req.method === 'POST' && path === '/twiml') {
    void (async () => {
      try {
        const raw = await readBody(req);
        const params = new URLSearchParams(raw);

        const host = cfg.publicHostname || req.headers.host || '';
        if (!host) {
          res.writeHead(500, { 'content-type': 'text/plain' });
          res.end('nincs hostname');
          return;
        }

        if (cfg.validateSignature) {
          const ok = validTwilioSignature(
            req.headers['x-twilio-signature'] as string | undefined,
            `https://${cfg.publicHostname}/twiml`,
            params,
          );
          if (!ok) {
            console.warn('[http] ervenytelen Twilio alairas, elutasitva');
            res.writeHead(403, { 'content-type': 'text/plain' });
            res.end('forbidden');
            return;
          }
        }

        // A limit-ellenorzes az alairas UTAN fut: alairas nelkuli keres ne
        // tudja elfogyasztani a napi keretet.
        const verdict = admitCall();
        const from = params.get('From') ?? '<ismeretlen>';

        if (!verdict.allowed) {
          console.log(
            `[http] hivas elutasitva (${verdict.reason}) from=${from} ` +
              `${verdict.count}/${verdict.limit}`,
          );
          res.writeHead(200, { 'content-type': 'text/xml' });
          res.end(rejectTwiml(verdict.reason));
          return;
        }

        console.log(
          `[http] hivas elfogadva from=${from} ${verdict.count}/${verdict.limit}`,
        );
        res.writeHead(200, { 'content-type': 'text/xml' });
        res.end(relayTwiml(host));
      } catch (err) {
        console.error('[http] /twiml hiba:', err);
        res.writeHead(500, { 'content-type': 'text/xml' });
        res.end(
          `<?xml version="1.0" encoding="UTF-8"?><Response><Say voice="${escapeXml(cfg.sayVoice)}" language="${escapeXml(cfg.ttsLanguage)}">${escapeXml(FAILURE_MESSAGE)}</Say><Hangup/></Response>`,
        );
      }
    })();
    return;
  }

  res.writeHead(404, { 'content-type': 'text/plain' });
  res.end('not found');
});

/* ------------------------------------------------------------------ */
/* WebSocket                                                            */
/* ------------------------------------------------------------------ */

const wss = new WebSocketServer({ noServer: true });

server.on('upgrade', (req, socket, head) => {
  const rawUrl = req.url ?? '';
  const path = rawUrl.split('?')[0];

  // A teszt-agent sajat relay-utvonala. Kulon session-kezeles, kulon prompt.
  if (path === '/test/relay') {
    const query = new URLSearchParams(
      rawUrl.includes('?') ? rawUrl.slice(rawUrl.indexOf('?') + 1) : '',
    );
    const runId = query.get('run') ?? '';
    const scenario = query.get('scenario') ?? 'alap';

    if (!/^[0-9a-f]{16}$/.test(runId)) {
      socket.destroy();
      return;
    }

    wss.handleUpgrade(req, socket, head, (ws) => {
      handleTestRelay(ws, runId, scenario);
    });
    return;
  }

  if (path !== '/relay') {
    socket.destroy();
    return;
  }
  wss.handleUpgrade(req, socket, head, (ws) => {
    wss.emit('connection', ws, req);
  });
});

interface Session {
  history: Turn[];
  from: string;
  callSid: string;
  startedAt: number;
  /** Igaz, amig egy modellhivas fut. Vedelem az atfedo valaszok ellen. */
  busy: boolean;
  timer: NodeJS.Timeout | null;
  closed: boolean;
  /** A hivas elejen rogzitett prompt: hivas kozben nem valtozhat. */
  systemPrompt: string;
}

wss.on('connection', (ws: WebSocket) => {
  callStarted();

  const s: Session = {
    history: [],
    from: '<ismeretlen>',
    callSid: '<ismeretlen>',
    startedAt: Date.now(),
    busy: false,
    timer: null,
    closed: false,
    systemPrompt: buildSystemPrompt(cfg.currentProjects),
  };

  const send = (text: string, last = false): void => {
    if (ws.readyState !== ws.OPEN) return;
    ws.send(JSON.stringify({ type: 'text', token: text, last }));
  };

  // Hivashossz-korlat. A timer a socket megnyitasakor indul, nem a setup
  // uzenetnel: a Twilio innentol szamlaz.
  s.timer = setTimeout(() => {
    if (s.closed) return;
    console.log(`[ws] idokorlat lejart callSid=${s.callSid}`);
    send(TIME_LIMIT_MESSAGE, true);
    // Hat masodperc, hogy a mondat elhangozzon, mielott bontunk.
    setTimeout(() => {
      if (ws.readyState === ws.OPEN) ws.close(1000, 'time limit');
    }, 6_000);
  }, maxCallSeconds() * 1_000);

  ws.on('message', (data) => {
    void (async () => {
      let msg: Record<string, unknown>;
      try {
        msg = JSON.parse(data.toString()) as Record<string, unknown>;
      } catch {
        console.warn('[ws] ertelmezhetetlen uzenet');
        return;
      }

      const type = msg['type'];

      if (type === 'setup') {
        s.from = typeof msg['from'] === 'string' ? msg['from'] : s.from;
        s.callSid = typeof msg['callSid'] === 'string' ? msg['callSid'] : s.callSid;
        console.log(`[ws] setup from=${s.from} callSid=${s.callSid}`);
        return;
      }

      if (type !== 'prompt') return;

      // A ConversationRealy reszleges leiratokat is kuldhet; csak a
      // veglegesre valaszolunk, kulonben felmondatokra reagalnank.
      if (msg['last'] === false) return;

      const text = typeof msg['voicePrompt'] === 'string' ? msg['voicePrompt'].trim() : '';
      if (!text) return;

      // Ha meg fut egy korabbi valasz, ezt a fordulot eldobjuk. Ket
      // parhuzamos valasz osszekeveredve erkezne a hivohoz.
      if (s.busy) {
        console.warn('[ws] atfedo prompt eldobva');
        return;
      }

      s.busy = true;
      s.history.push({ role: 'user', content: text });

      try {
        const answer = await reply(s.history, s.systemPrompt);
        s.history.push({ role: 'assistant', content: answer });
        send(answer, true);
      } catch (err) {
        console.error('[ws] modellhiba:', err);
        send(FAILURE_MESSAGE, true);
      } finally {
        s.busy = false;
      }
    })();
  });

  ws.on('close', () => {
    if (s.closed) return;
    s.closed = true;

    if (s.timer) {
      clearTimeout(s.timer);
      s.timer = null;
    }
    callEnded();

    const durationSec = Math.round((Date.now() - s.startedAt) / 1000);
    console.log(`[ws] hivas vege callSid=${s.callSid} ${durationSec}s`);

    // Az osszefoglalo a hivas utan fut. Nem varunk ra: a socket mar zart,
    // a hivo letette. Hiba eseten a fuggveny magaban naploz.
    void (async () => {
      const summary = await summarize(s.history);
      await sendSummary(summary, s.history, {
        from: s.from,
        durationSec,
        callSid: s.callSid,
      });
      // Kulon lepes, kulon hibakezeles: az SMS elmaradasa ne akadalyozza
      // az osszefoglalo emailt, es forditva.
      await sendContactSms(s.from);
    })();
  });

  ws.on('error', (err) => {
    console.error('[ws] socket hiba:', err);
  });
});

/* ------------------------------------------------------------------ */

server.listen(cfg.port, '0.0.0.0', () => {
  console.log(`[start] AXIMBRA voice agent fut a ${cfg.port} porton`);
  console.log(
    `[start] napi keret=${cfg.maxCallsPerDay} hivashossz=${cfg.maxCallSeconds}s ` +
      `modell=${cfg.model} alairas-ellenorzes=${cfg.validateSignature}`,
  );
});

// Railway SIGTERM-et kuld deploykor. Rendezett leallas: a folyamatban levo
// hivasok ne szakadjanak meg felmondatban.
process.on('SIGTERM', () => {
  console.log('[stop] SIGTERM, leallas');
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 10_000);
});
