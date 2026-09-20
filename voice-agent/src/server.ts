/**
 * AXIMBRA telefonos agent.
 *
 * Vegpontok:
 *   POST /twiml  - Twilio webhook. Eldonti, ki fogadja a hivast (routing.ts):
 *                  magyar szamnal a tulajdonos, kulonben az agent.
 *   POST /twiml/screen, /twiml/screen-done, /twiml/owner-done
 *                - az atkapcsolas lepesei: szures a tulajdonos telefonjan, es
 *                  az agent, ha nem fogadta.
 *   WS   /relay  - a beszelgetes maga. A Twilio ide kuldi a leiratot,
 *                  es innen varja a kimondando szoveget.
 *
 * A ConversationRelay-t hasznaljuk sajat hangfeldolgozas helyett: a Twilio
 * intezi a beszed-szoveg es szoveg-beszed atalakitast, a felbeszakitast es
 * a puffereles. Nekunk csak a "mit valaszoljon" resz marad.
 */

import http from 'node:http';
import crypto from 'node:crypto';
import { WebSocketServer, type WebSocket } from 'ws';

import { env } from './env.js';
import { admitCall, callStarted, callEnded, maxCallSeconds, stats } from './limit.js';
import {
  replyStream,
  summarize,
  extractFacts,
  emptyFacts,
  mergeFacts,
  detectSpokenLang,
  type Turn,
  type CallFacts,
} from './llm.js';
import { sendSummary } from './email.js';
import { sendContactSms } from './sms.js';
import { handleTestRoute, handleTestRelay, startTestCall } from './testAgent.js';
import {
  FAILURE_MESSAGE,
  FACTS_PROMPT,
  buildSystemPrompt,
  lines,
} from './prompt.js';
import {
  routeCall,
  isCallSid,
  ownerDialTwiml,
  screenTwiml,
  screenDoneTwiml,
  languageSwitchMessage,
  takeAccepted,
  HANGUP_TWIML,
  type Lang,
} from './routing.js';
import { escapeXml } from './xml.js';

const cfg = env();

/* ------------------------------------------------------------------ */
/* TwiML                                                               */
/* ------------------------------------------------------------------ */

/** Az angol hang rogzitett; a magyar a Railway valtozokbol jon (env.ts). */
const EN_VOICE = {
  language: 'en-US',
  ttsProvider: 'Google',
  ttsVoice: 'en-US-Wavenet-F',
  sayVoice: 'Google.en-US-Wavenet-F',
};

function relayTwiml(host: string, lang: Lang): string {
  // A <Language> gyerekelemek nyelvenkent adjak meg a hangot es a
  // felismerest. Mindket nyelv mindig fel van veve, hogy a hivas kozbeni
  // nyelvvaltas ne ervenytelen konfiguraciora fusson; a `lang` csak azt
  // donti el, melyiken kezdunk.
  const start =
    lang === 'en'
      ? { language: EN_VOICE.language, ttsProvider: EN_VOICE.ttsProvider, voice: EN_VOICE.ttsVoice }
      : { language: 'hu-HU', ttsProvider: cfg.ttsProvider, voice: cfg.ttsVoice };

  // A `language` attributum EGYSZERRE allitana a TTS-t es a felismerest,
  // ezert a ketto kulon van megadva. A hivoszam viszont csak a KEZDO
  // beallitast donti el - egy tipp, nem tobb: magyar ugyfel hivhat nemet
  // szamrol, angol ugyfel magyarrol.
  //
  // Ket korabbi valtozat mindketteje felig mukodott. Az elso a szambol
  // vezette le a felismerest is: a +36-tal nem kezdodo, de magyarul beszelo
  // hivo atirata hasznalhatatlan lett. A masodik ezert MINDIG `hu-HU`-ra
  // allitotta a felismerest - amivel viszont az angolul beszelo hivo jart
  // pontosan ugyanigy (2026-09-20, `kulfoldi` forgatokonyv: "We hiv fix
  // People Using Email Regularly").
  //
  // Most a hivo elso mondata donti el, nem a szama: a /relay a valodi
  // nyelvet felismeri, es menet kozben atallitja mindkettot (lasd
  // `switchLang`). Ehhez kell, hogy mindket <Language> mindig fel legyen
  // veve - egy nem deklaralt nyelvre a valtas ervenytelen lenne.
  return `<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <ConversationRelay
      url="wss://${escapeXml(host)}/relay?lang=${lang}"
      welcomeGreeting="${escapeXml(lines(lang).greeting)}"
      ttsLanguage="${escapeXml(start.language)}"
      transcriptionLanguage="${escapeXml(start.language)}"
      hints="Aximbra,AI ügynökség,agent,automatizálás,e-mail rendező,érdeklődő minősítő,árajánlat,elérhetőség"
      ttsProvider="${escapeXml(start.ttsProvider)}"
      voice="${escapeXml(start.voice)}"
      interruptible="speech"
      interruptSensitivity="${escapeXml(process.env['INTERRUPT_SENSITIVITY'] ?? 'low')}"
      speechTimeout="${escapeXml(process.env['SPEECH_TIMEOUT'] ?? '1500')}"
      ignoreBackchannel="true"
      welcomeGreetingInterruptible="none"
      reportInputDuringAgentSpeech="none">
      <Language code="hu-HU" ttsProvider="${escapeXml(cfg.ttsProvider)}" voice="${escapeXml(cfg.ttsVoice)}" />
      <Language code="${EN_VOICE.language}" ttsProvider="${EN_VOICE.ttsProvider}" voice="${EN_VOICE.ttsVoice}" />
    </ConversationRelay>
  </Connect>
</Response>`;
}

const REJECT_MESSAGES: Record<Lang, Record<'daily' | 'concurrent', string>> = {
  hu: {
    concurrent:
      'Köszönjük a hívást. Jelenleg minden vonalunk foglalt, kérjük, próbálja újra néhány perc múlva. Viszonthallásra!',
    daily:
      'Köszönjük a hívást. A bemutató vonal mai kerete betelt. Kérjük, írjon nekünk az aximbra kukac gmail pont com címre, vagy próbálja meg holnap. Viszonthallásra!',
  },
  en: {
    concurrent:
      'Thank you for calling. All our lines are busy right now, please try again in a few minutes. Goodbye!',
    daily:
      "Thank you for calling. Today's limit for this demo line has been reached. Please email us at aximbra at gmail dot com, or try again tomorrow. Goodbye!",
  },
};

/**
 * Elutasito valasz.
 *
 * Szandekosan beszelunk, nem <Reject>-elunk: egy foglalt jelzes egy
 * marketingoldalon szereplo szamnal ugy hangzik, mintha a ceg nem letezne.
 */
function rejectTwiml(reason: 'daily' | 'concurrent', lang: Lang): string {
  const voice = lang === 'en' ? EN_VOICE.sayVoice : cfg.sayVoice;
  const language = lang === 'en' ? EN_VOICE.language : cfg.ttsLanguage;

  return `<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="${escapeXml(voice)}" language="${escapeXml(language)}">${escapeXml(REJECT_MESSAGES[lang][reason])}</Say>
  <Hangup/>
</Response>`;
}

/** Az agenthez kapcsolas, a napi es egyideju keret ellenorzesevel. */
function agentTwiml(host: string, lang: Lang, from: string): string {
  const verdict = admitCall();

  if (!verdict.allowed) {
    console.log(
      `[http] hivas elutasitva (${verdict.reason}) from=${from} ` +
        `${verdict.count}/${verdict.limit}`,
    );
    return rejectTwiml(verdict.reason, lang);
  }

  console.log(
    `[http] hivas elfogadva lang=${lang} from=${from} ${verdict.count}/${verdict.limit}`,
  );
  return relayTwiml(host, lang);
}

/** A Twilio altal hivott utvonalak. Mind alairt POST. */
const TWIML_PATHS = new Set(['/twiml', '/twiml/screen', '/twiml/screen-done', '/twiml/owner-done']);

function twimlFor(
  path: string,
  params: URLSearchParams,
  query: URLSearchParams,
  host: string,
): string {
  const from = params.get('From') ?? '<ismeretlen>';

  switch (path) {
    case '/twiml': {
      const route = routeCall(params.get('From'), cfg.ownerPhone);
      const callSid = params.get('CallSid') ?? '';

      // Azonosito nelkul nem tudnank kovetni, fogadta-e a hivast - ilyenkor
      // inkabb az agent veszi fel, mint hogy a hivo elveszjen.
      if (route.to === 'owner' && isCallSid(callSid)) {
        console.log(`[http] atkapcsolas a tulajdonoshoz from=${from}`);
        return ownerDialTwiml({
          host,
          ownerPhone: cfg.ownerPhone,
          ringSeconds: cfg.ownerRingSeconds,
          callSid,
          calledNumber: params.get('To') ?? '',
        });
      }
      return agentTwiml(host, route.to === 'agent' ? route.lang : 'hu', from);
    }

    case '/twiml/screen':
      return screenTwiml(host, query.get('parent') ?? '', cfg.sayVoice, cfg.ttsLanguage);

    case '/twiml/screen-done':
      return screenDoneTwiml(params.get('Digits') ?? '', query.get('parent') ?? '');

    case '/twiml/owner-done': {
      if (takeAccepted(params.get('CallSid') ?? '')) return HANGUP_TWIML;

      // A hivo letette, mig csengett: nincs kit az agenthez kapcsolni, es a
      // napi keretbol sem vonunk le erte.
      const status = params.get('CallStatus') ?? '';
      if (status === 'completed' || status === 'canceled') return HANGUP_TWIML;

      console.log(
        `[http] a tulajdonos nem fogadta (${params.get('DialCallStatus') ?? '?'}), ` +
          `agent veszi at from=${from}`,
      );
      return agentTwiml(host, 'hu', from);
    }

    default:
      return HANGUP_TWIML;
  }
}

/* ------------------------------------------------------------------ */
/* Twilio signature                                                     */
/* ------------------------------------------------------------------ */

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

  if (path.startsWith('/test')) {
    void (async () => {
      try {
        const form =
          req.method === 'POST' ? new URLSearchParams(await readBody(req)) : undefined;

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

  if (req.method === 'POST' && TWIML_PATHS.has(path)) {
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
          // A Twilio a teljes URL-t irja ala, a query stringgel egyutt - a
          // szuresi lepesek a hivas azonositojat ott viszik tovabb.
          const ok = validTwilioSignature(
            req.headers['x-twilio-signature'] as string | undefined,
            `https://${cfg.publicHostname}${rawUrl}`,
            params,
          );
          if (!ok) {
            console.warn(`[http] ervenytelen Twilio alairas (${path}), elutasitva`);
            res.writeHead(403, { 'content-type': 'text/plain' });
            res.end('forbidden');
            return;
          }
        }

        res.writeHead(200, { 'content-type': 'text/xml' });
        res.end(twimlFor(path, params, query, host));
      } catch (err) {
        console.error(`[http] ${path} hiba:`, err);
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

  if (path === '/test/relay') {
    const query = new URLSearchParams(
      rawUrl.includes('?') ? rawUrl.slice(rawUrl.indexOf('?') + 1) : '',
    );
    const runId = query.get('run') ?? '';

    if (!/^[0-9a-f]{16}$/.test(runId)) {
      socket.destroy();
      return;
    }

    wss.handleUpgrade(req, socket, head, (ws) => {
      handleTestRelay(ws, runId, query.get('scenario') ?? 'alap');
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
  /**
   * A hivas NYELVE, ahogy eppen all. A hivoszambol indul, es a hivo elso
   * mondata utan atallhat - ezert nem konstans, es ezert kell mindenhol
   * innen olvasni, nem a belepeskori ertekbol.
   */
  lang: Lang;
  /**
   * Hany nyelvfelismeres futott mar le. Nem logikai jelzo: egy "Hallo"-bol
   * nem lehet nyelvet allapitani, es ha az elso probalkozas utan feladnank,
   * az ilyen hivas vegig a hivoszambol tippelt nyelven maradna.
   */
  langChecks: number;
  from: string;
  callSid: string;
  startedAt: number;
  /** Meg fel nem dolgozott hivoi mondatok. Sosem dobunk el egyet sem. */
  queue: string[];
  /** Igaz, amig a feldolgozo ciklus fut. */
  draining: boolean;
  /** Igaz, amig egy valasz eppen kimenoben van (stream vagy TTS). */
  speaking: boolean;
  /** Az eppen futo modellhivas leallitasa felbeszakitaskor. */
  abort: AbortController | null;
  /** Amit az aktualis fordulobol mar kikuldtunk a Twilionak. */
  streamed: string;
  timer: NodeJS.Timeout | null;
  closed: boolean;
  /** Amit a hivas soran mar megtudtunk a hivorol. */
  facts: CallFacts;
  /** Igaz, amig egy tenykinyeres fut: nem inditunk parhuzamosan masikat. */
  extracting: boolean;
}

wss.on('connection', (ws: WebSocket, req: http.IncomingMessage) => {
  callStarted();

  // A relayTwiml a hivoszambol tippelt nyelvet teszi az URL-be. Ez csak a
  // KEZDO ertek: amint a hivo megszolal, a `maybeSwitchLang` felulirhatja.
  const relayQuery = new URLSearchParams((req.url ?? '').split('?')[1] ?? '');
  const startLang: Lang = relayQuery.get('lang') === 'en' ? 'en' : 'hu';
  // Fuggveny, nem valtozo: a nyelv menet kozben valtozhat, es egy elmentett
  // `lines(lang)` ettol csendben a regi nyelven maradna.
  const say = (): ReturnType<typeof lines> => lines(s.lang);

  const s: Session = {
    // A welcomeGreeting-et a Twilio mondja ki, nem mi. Ha nem tesszuk be a
    // tortenetbe, a modell nem tud rola, hogy mar koszontunk - es az elso
    // valaszaban ujra bemutatkozik. Pontosan ez tortent elesben.
    history: [{ role: 'assistant', content: lines(startLang).greeting }],
    lang: startLang,
    langChecks: 0,
    from: '<ismeretlen>',
    callSid: '<ismeretlen>',
    startedAt: Date.now(),
    queue: [],
    draining: false,
    speaking: false,
    abort: null,
    streamed: '',
    timer: null,
    closed: false,
    facts: emptyFacts(),
    extracting: false,
  };

  const send = (text: string, last = false): void => {
    if (ws.readyState !== ws.OPEN) return;
    ws.send(JSON.stringify({ type: 'text', token: text, last }));
  };

  /**
   * Nyelvvaltas a mar folo hivason.
   *
   * Csak olyan nyelvre szabad valtani, amelyik `<Language>` gyerekkent
   * szerepel a TwiML-ben - a relayTwiml mindkettot mindig felveszi.
   */
  const switchLang = (next: Lang): void => {
    if (next === s.lang || ws.readyState !== ws.OPEN) return;
    s.lang = next;
    ws.send(languageSwitchMessage(next));
    console.log(`[ws] nyelvvaltas -> ${next} callSid=${s.callSid}`);
  };

  /**
   * Jol tippeltunk-e a hivoszambol? A hivo sajat mondata donti el.
   *
   * A valasz KIMONDASA ELOTT fut, mert egy rossz nyelvu elso mondat jobban
   * hallatszik, mint egy fel masodpercnyi szunet - es mert a hivo kovetkezo
   * mondatat is mar a jo felismerovel akarjuk atirni.
   *
   * Addig probalkozik, amig hatarozott valaszt nem kap, de legfeljebb
   * LANG_CHECK_LIMIT-szer: egy "Hallo" mindket nyelven letezik, es ha az
   * elso probalkozas utan feladnank, az ilyen hivas vegig rossz nyelven
   * menne. A felso korlat azert kell, hogy egy vegig ertelmezhetetlen hivas
   * ne fizessen minden fordulora egy plusz modellhivast.
   *
   * Barmilyen hiba eseten marad a tippelt nyelv es megy tovabb a hivas: ez
   * a lepes soha nem allithatja meg a beszelgetest.
   */
  const LANG_CHECK_LIMIT = 3;

  const maybeSwitchLang = async (utterance: string): Promise<void> => {
    if (s.langChecks >= LANG_CHECK_LIMIT) return;
    s.langChecks += 1;
    try {
      const spoken = await detectSpokenLang(utterance);
      if (!spoken) return;
      s.langChecks = LANG_CHECK_LIMIT; // hatarozott valasz: tobbet nem kerdezunk
      switchLang(spoken);
    } catch (err) {
      console.error('[ws] nyelvfelismeres hiba:', err);
    }
  };

  /** Egy fordulo kimondasa, tokenenkent tovabbitva. */
  const speakReply = async (): Promise<void> => {
    const ac = new AbortController();
    s.abort = ac;
    s.streamed = '';
    s.speaking = true;

    try {
      const full = await replyStream(
        s.history,
        buildSystemPrompt(cfg.currentProjects, s.facts, s.from, s.lang),
        (delta) => {
          s.streamed += delta;
          send(delta, false);
        },
        { signal: ac.signal, maxTokens: 200, temperature: 0.3, timeoutMs: 12_000 },
      );
      send('', true);
      s.history.push({ role: 'assistant', content: full });
    } catch (err) {
      if (ac.signal.aborted) {
        // Felbeszakitottak. Amit tenylegesen kimondtunk, az kerul a
        // tortenetbe - kulonben a modell azt hinne, hogy elmondta a
        // teljes mondatot, es arra epitene a kovetkezo valaszat.
        const said = s.streamed.trim();
        if (said) s.history.push({ role: 'assistant', content: said });
        console.log(`[ws] felbeszakitva callSid=${s.callSid}`);
        return;
      }

      console.error('[ws] modellhiba:', err);
      if (s.streamed.trim()) {
        // Mar beszeltunk: a felmondatot lezarjuk, nem kezdunk uj szoveget.
        send('', true);
        s.history.push({ role: 'assistant', content: s.streamed.trim() });
      } else {
        send(say().failure, true);
        s.history.push({ role: 'assistant', content: say().failure });
      }
    } finally {
      s.speaking = false;
      s.abort = null;
    }
  };

  /**
   * A mar elhangzott adatok frissitese, HATTERBEN.
   *
   * Szandekosan nem varjuk meg: a valasz mar kiment a vonalra, mire ez
   * elindul. Igy nulla varakozast ad a hivasnak. Cserebe a frissites egy
   * fordulot kesik - ami eleg, mert a kovetkezo kerdes elott keszen van.
   *
   * Ha elszall, a korabbi tenyek megmaradnak. A hivas soha nem all meg
   * emiatt.
   */
  const refreshFacts = (): void => {
    if (s.extracting || s.closed) return;
    s.extracting = true;

    void (async () => {
      try {
        const found = await extractFacts(s.history, FACTS_PROMPT, {
          maxTokens: 300,
          timeoutMs: 10_000,
        });
        if (found) s.facts = mergeFacts(s.facts, found);
      } catch (err) {
        console.error('[ws] tenyfrissites hiba:', err);
      } finally {
        s.extracting = false;
      }
    })();
  };

  /**
   * A varakozo mondatok feldolgozasa.
   *
   * Ha a hivo beszel, mikozben a modell dolgozik, a mondata a sorba kerul,
   * es a kovetkezo fordulonal ossze van vonva. A korabbi verzio ilyenkor
   * NEMAN ELDOBTA a mondatot - a hivo ugy erezte, nem figyelnek ra.
   */
  const drain = async (): Promise<void> => {
    if (s.draining) return;
    s.draining = true;
    try {
      while (s.queue.length > 0 && !s.closed) {
        const text = s.queue.splice(0, s.queue.length).join(' ').trim();
        if (!text) continue;
        // A valasz elott, nem utana: a nyelvet meg az elso megszolalasunk
        // elott helyre kell tenni, kulonben a hivo egy rossz nyelvu mondatot
        // kap, es a sajat kovetkezo mondatat is rossz felismero irja at.
        await maybeSwitchLang(text);
        s.history.push({ role: 'user', content: text });
        await speakReply();
        refreshFacts();
      }
    } finally {
      s.draining = false;
    }
  };

  // Hivashossz-korlat. A timer a socket megnyitasakor indul, nem a setup
  // uzenetnel: a Twilio innentol szamlaz.
  s.timer = setTimeout(() => {
    if (s.closed) return;
    console.log(`[ws] idokorlat lejart callSid=${s.callSid}`);
    // Ha eppen beszelunk, elobb elvagjuk - kulonben ket szoveg keveredne.
    s.abort?.abort();
    s.queue.length = 0;
    send(say().timeLimit, true);
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

      // Felbeszakitas: a hivo belevagott a mondatunkba. A Twilio megmondja,
      // meddig jutottunk a felolvasasban.
      if (type === 'interrupt') {
        const said =
          typeof msg['utteranceUntilInterrupt'] === 'string'
            ? msg['utteranceUntilInterrupt'].trim()
            : '';

        if (s.speaking) {
          if (said) s.streamed = said;
          s.abort?.abort();
          return;
        }

        // A stream mar lezarult, de a TTS meg jatszott. A tortenet utolso
        // sajat mondatat visszavagjuk arra, ami tenylegesen elhangzott.
        const last = s.history[s.history.length - 1];
        if (last && last.role === 'assistant' && said) {
          last.content = said;
        }
        return;
      }

      if (type === 'error') {
        console.error('[ws] ConversationRelay hiba:', msg['description'] ?? msg);
        return;
      }

      if (type !== 'prompt') return;

      // A ConversationRelay reszleges leiratokat is kuldhet; csak a
      // veglegesre valaszolunk, kulonben felmondatokra reagalnank.
      if (msg['last'] === false) return;

      const text = typeof msg['voicePrompt'] === 'string' ? msg['voicePrompt'].trim() : '';
      if (!text) return;

      s.queue.push(text);
      await drain();
    })();
  });

  ws.on('close', () => {
    if (s.closed) return;
    s.closed = true;

    s.abort?.abort();
    if (s.timer) {
      clearTimeout(s.timer);
      s.timer = null;
    }
    callEnded();

    const durationSec = Math.round((Date.now() - s.startedAt) / 1000);
    console.log(`[ws] hivas vege callSid=${s.callSid} ${durationSec}s`);

    // Az osszefoglalo a hivas utan fut. A bevezeto koszonest kihagyjuk
    // belole: nem informacio, csak zajt vinne az osszefoglaloba.
    const transcript = s.history.slice(1);

    void (async () => {
      try {
        const summary = await summarize(transcript);
        await sendSummary(summary, transcript, {
          from: s.from,
          durationSec,
          callSid: s.callSid,
        });
      } catch (err) {
        console.error('[ws] osszefoglalo kuldes hiba:', err);
      }
      try {
        await sendContactSms(s.from, s.lang);
      } catch (err) {
        console.error('[ws] SMS kuldes hiba:', err);
      }
    })();
  });

  ws.on('error', (err) => {
    console.error('[ws] socket hiba:', err);
  });
});

/* ------------------------------------------------------------------ */

/**
 * Fustteszt inditas utan: egy valodi teszthivas, automatikusan.
 *
 * A beepitett hivastesztelot eddig csak kezzel, a weboldalrol lehetett
 * elinditani - vagyis egy nyelvi vagy hangbeallitasi regresszio csak akkor
 * derult ki, ha valaki eszebe jutott ranezni. Pont ez tortent ketszer
 * egymas utan a felismeres nyelvevel.
 *
 * ALAPBOL KI VAN KAPCSOLVA. Csak akkor fut, ha a SMOKE_TEST_SCENARIO
 * valtozo egy forgatokonyv kulcsat tartalmazza (pl. `alap`), es akkor is
 * deploy-onkent pontosan egyszer: egy indulas, egy hivas. Valodi hivas,
 * valodi koltseggel, ezert nem alapertelmezes - es a napi hivaskeret
 * (MAX_CALLS_PER_DAY) ugyanugy vonatkozik ra.
 *
 * A hivas eredmenye a szokasos helyre kerul: `[test] ...` sorok, a vegen a
 * teljes `[atirat]`. Nem dobunk hibat semmilyen agon: egy sikertelen
 * fustteszt nem akadalyozhatja meg, hogy a szolgaltatas elinduljon.
 */
function scheduleSmokeTest(): void {
  const scenario = process.env['SMOKE_TEST_SCENARIO']?.trim() ?? '';
  if (!scenario) return;

  // Rovid varakozas: a hivas azonnal visszahiv a sajat /test/twiml
  // vegpontunkra, aminek addigra fogadokepesnek kell lennie.
  setTimeout(() => {
    void (async () => {
      try {
        console.log(`[smoke] fustteszt indul forgatokonyv=${scenario}`);
        const res = await startTestCall(scenario);
        if (!res.ok) console.error(`[smoke] nem indult el: ${res.error}`);
      } catch (err) {
        console.error('[smoke] kivetel:', err);
      }
    })();
  }, 5_000).unref();
}

server.listen(cfg.port, '0.0.0.0', () => {
  console.log(`[start] AXIMBRA voice agent fut a ${cfg.port} porton`);
  console.log(
    `[start] napi keret=${cfg.maxCallsPerDay} hivashossz=${cfg.maxCallSeconds}s ` +
      `modell=${cfg.model} alairas-ellenorzes=${cfg.validateSignature} ` +
      `atkapcsolas=${cfg.ownerPhone !== ''}`,
  );
  scheduleSmokeTest();
});

process.on('SIGTERM', () => {
  console.log('[stop] SIGTERM, leallas');
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 10_000);
});
