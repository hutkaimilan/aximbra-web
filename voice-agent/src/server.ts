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
  normalizeNumber,
  languageMenuTwiml,
  langFromDigits,
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

/**
 * Nyelvenkent a hang, egy helyen.
 *
 * A magyar a Railway valtozoibol jon, hogy kod nelkul cserelheto legyen; a
 * tobbi rogzitett. Egy uj nyelv igy egyetlen sor ide, nem szet-szort
 * elagazasok fel tucat fajlban - pontosan ez tette korabban konnyuve, hogy
 * a felolvasas es a felismeres eszrevetlenul szetcsusszon.
 */
interface VoiceCfg {
  language: string;
  ttsProvider: string;
  ttsVoice: string;
  sayVoice: string;
}

function voiceFor(lang: Lang): VoiceCfg {
  if (lang === 'en') {
    return {
      language: 'en-US',
      ttsProvider: 'Google',
      ttsVoice: 'en-US-Wavenet-F',
      sayVoice: 'Google.en-US-Wavenet-F',
    };
  }
  if (lang === 'de') {
    return {
      language: 'de-DE',
      ttsProvider: 'Google',
      ttsVoice: 'de-DE-Wavenet-C',
      sayVoice: 'Google.de-DE-Wavenet-C',
    };
  }
  return {
    language: cfg.ttsLanguage,
    ttsProvider: cfg.ttsProvider,
    ttsVoice: cfg.ttsVoice,
    sayVoice: cfg.sayVoice,
  };
}

/** A felkinalt nyelvek. A ConversationRelay mindegyiket deklaralja. */
const ALL_LANGS: Lang[] = ['hu', 'en', 'de'];

function relayTwiml(host: string, lang: Lang, chosen: boolean): string {
  // A <Language> gyerekelemek nyelvenkent adjak meg a hangot es a
  // felismerest. Mindket nyelv mindig fel van veve, hogy a hivas kozbeni
  // nyelvvaltas ne ervenytelen konfiguraciora fusson; a `lang` csak azt
  // donti el, melyiken kezdunk.
  const start = voiceFor(lang);

  // A `language` attributum EGYSZERRE allitana a TTS-t es a felismerest,
  // ezert a ketto kulon van megadva - de MINDIG egyutt mozog.
  //
  // A nyelvet rendes esetben a hivo valasztotta ki gombnyomassal (lasd
  // languageMenuTwiml). Ilyenkor `chosen` igaz, es a hivas vegig azon a
  // nyelven megy: egy megnyomott gombot nem irhat felul se a hivoszam, se a
  // beszedfelismeres.
  //
  // Ha nem nyomott gombot, magyarul folytatjuk, es a beszedbol allunk at, ha
  // kell. Miert eppen magyarul? Mert a felismeres hibaja NEM szimmetrikus:
  //
  //   angol beszed, magyar felismero:
  //     "We hiv fix People Using Email Regularly" - az angol szavak
  //     atjonnek, a nyelv felismerheto marad.
  //   magyar beszed, angol felismero:
  //     "Hello. Hi. Amit Mondock." - ez mar semmilyen nyelvre nem hasonlit,
  //     es angolnak olvasva megis hihetonek tunik. Innen nincs ut vissza.
  //
  // Mindket <Language> mindig fel van veve, kulonben a hivas kozbeni valtas
  // ervenytelen nyelvre mutatna.
  return `<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <ConversationRelay
      url="wss://${escapeXml(host)}/relay?lang=${lang}${chosen ? '&amp;fix=1' : ''}"
      welcomeGreeting="${escapeXml(lines(lang).greeting)}"
      ttsLanguage="${escapeXml(start.language)}"
      transcriptionLanguage="${escapeXml(start.language)}"
      hints="Aximbra,AI ügynökség,agent,automatizálás,e-mail rendező,érdeklődő minősítő,árajánlat,elérhetőség"
      ttsProvider="${escapeXml(start.ttsProvider)}"
      voice="${escapeXml(start.ttsVoice)}"
      interruptible="speech"
      interruptSensitivity="${escapeXml(process.env['INTERRUPT_SENSITIVITY'] ?? 'low')}"
      speechTimeout="${escapeXml(process.env['SPEECH_TIMEOUT'] ?? '1500')}"
      ignoreBackchannel="true"
      welcomeGreetingInterruptible="none"
      reportInputDuringAgentSpeech="none">
${ALL_LANGS.map((l) => {
        const v = voiceFor(l);
        return `      <Language code="${escapeXml(v.language)}" ttsProvider="${escapeXml(v.ttsProvider)}" voice="${escapeXml(v.ttsVoice)}" />`;
      }).join('\n')}
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
  de: {
    concurrent:
      'Danke für Ihren Anruf. Gerade sind alle Leitungen belegt, bitte versuchen Sie es in ein paar Minuten noch einmal. Auf Wiederhören!',
    daily:
      'Danke für Ihren Anruf. Das heutige Kontingent dieser Demo-Leitung ist ausgeschöpft. Schreiben Sie uns bitte an aximbra at gmail dot com, oder versuchen Sie es morgen wieder. Auf Wiederhören!',
  },
};

/**
 * Elutasito valasz.
 *
 * Szandekosan beszelunk, nem <Reject>-elunk: egy foglalt jelzes egy
 * marketingoldalon szereplo szamnal ugy hangzik, mintha a ceg nem letezne.
 */
function rejectTwiml(reason: 'daily' | 'concurrent', lang: Lang): string {
  const v = voiceFor(lang);
  const voice = v.sayVoice;
  const language = v.language;

  return `<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say voice="${escapeXml(voice)}" language="${escapeXml(language)}">${escapeXml(REJECT_MESSAGES[lang][reason])}</Say>
  <Hangup/>
</Response>`;
}

/**
 * Az agenthez kapcsolas, a napi es egyideju keret ellenorzesevel.
 *
 * A `lang` a hivoszambol jott tipp. Az elutasito uzenet hasznalja - ott ez az
 * egyetlen jel, es a mondat ugyis egyszer hangzik el. A BESZELGETES viszont
 * mindig magyarul indul, fuggetlenul a szamtol: lasd a relayTwiml-t.
 */
function agentTwiml(host: string, lang: Lang, from: string, forced: Lang | null): string {
  const verdict = admitCall();

  if (!verdict.allowed) {
    console.log(
      `[http] hivas elutasitva (${verdict.reason}) from=${from} ` +
        `${verdict.count}/${verdict.limit}`,
    );
    return rejectTwiml(verdict.reason, lang);
  }

  console.log(
    `[http] hivas elfogadva from=${from} ${verdict.count}/${verdict.limit}` +
      (forced ? ` nyelv=${forced} (sajat szam)` : ' -> nyelvvalaszto'),
  );

  // Kulon nyelvi szamon nincs mit valasztani: aki azt tarcsazta, mar
  // dontott. Mindenki mas a menuvel kezd.
  if (forced) return relayTwiml(host, forced, true);

  return languageMenuTwiml({
    host,
    voices: { hu: voiceFor('hu').sayVoice, en: voiceFor('en').sayVoice, de: voiceFor('de').sayVoice },
    timeoutSeconds: MENU_TIMEOUT_SECONDS,
  });
}

/**
 * Hany masodpercig var a menu gombnyomasra.
 *
 * Eleg hosszu ahhoz, hogy a masodik (angol) mondat is vegigmenjen, es a
 * hivo utana meg gondolkodhasson egy kicsit. Utana magyarul folytatjuk.
 */
const MENU_TIMEOUT_SECONDS = 6;

/** A Twilio altal hivott utvonalak. Mind alairt POST. */
const TWIML_PATHS = new Set([
  '/twiml',
  '/twiml/lang',
  '/twiml/screen',
  '/twiml/screen-done',
  '/twiml/owner-done',
]);

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
      // A HIVOTT szam az egyetlen biztos nyelvi jel, ami a hivas elejen
      // rendelkezesre all: aki az angol szamot tarcsazza, angolul var
      // valaszt. Ha nincs kulon angol szam beallitva, magyarul indulunk, es
      // a hivo elso mondatabol allunk at (lasd relayTwiml).
      // Ha van kulon angol szam es azt tarcsaztak, a menu felesleges.
      const dialled = normalizeNumber(params.get('To'));
      const forced: Lang | null =
        cfg.englishPhone !== '' && dialled === cfg.englishPhone ? 'en' : null;

      return agentTwiml(host, route.to === 'agent' ? route.lang : 'hu', from, forced);
    }

    case '/twiml/lang': {
      // A nyelvvalaszto menu valasza. Gomb nelkul (idotullepes) magyarul
      // folytatjuk, de ugy, hogy a beszedfelismeres meg korrigalhat.
      const { lang, chosen } = langFromDigits(params.get('Digits'));
      console.log(
        `[http] nyelvvalasztas ${chosen ? `gomb=${params.get('Digits') ?? ''}` : 'nincs gomb'}` +
          ` -> ${lang} from=${from}`,
      );
      return relayTwiml(host, lang, chosen);
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
      // Ide csak magyar szamrol erkezo hivo jut el (a tulajdonoshoz csak
      // azokat kapcsoljuk), ezert magyarul veszi at az agent.
      return agentTwiml(host, 'hu', from, null);
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
  /**
   * Igaz, ha menet kozben nyelvet valtottunk, es a valtast kivalto hivoi
   * mondat meg nincs tisztazva: azt rossz nyelvu felismero irta at, tehat
   * nem tudjuk, mi hangzott el.
   */
  needsRepeat: boolean;
  /**
   * Eldontott nyelvvaltas, ami meg nem lepett eletbe, mert eppen beszelunk.
   * Mondat kozepen valtani hangot hallhatoan rosszabb, mint megvarni a
   * pont vegét.
   */
  pendingLang: Lang | null;
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
  const asked = relayQuery.get('lang');
  const startLang: Lang = asked === 'en' ? 'en' : asked === 'de' ? 'de' : 'hu';
  // `fix=1`: a hivo gombnyomassal valasztott nyelvet. Ezt semmi nem irhatja
  // felul - egy szandekos dontest felulbiralni rosszabb, mint barmi, amit a
  // felismeres nyerhetne vele.
  const langFixed = relayQuery.get('fix') === '1';
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
    needsRepeat: false,
    pendingLang: null,
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

    // Beszed kozben nem valtunk: a mar folyo mondat masik hangon fejezodne
    // be. A drain alkalmazza, amint a fordulo lezarult.
    if (s.speaking) {
      s.pendingLang = next;
      return;
    }

    s.lang = next;
    ws.send(languageSwitchMessage(next));
    // Amit a hivo eddig mondott, azt a MASIK nyelv felismeroje irta at, es
    // abbol nem lehet visszafejteni, mi hangzott el ("Hello. Hi. Amit
    // Mondock."). Nem talalgatunk: megkerjuk, hogy mondja ujra.
    s.needsRepeat = true;
    console.log(`[ws] nyelvvaltas -> ${next} callSid=${s.callSid}`);
  };

  /**
   * Magyarul indult a hivas gombnyomas nelkul - tenyleg magyarul beszel?
   *
   * Aki gombot nyomott, azt nem kerdojelezzuk meg: `langFixed` eseten ez a
   * fuggveny nem csinal semmit.
   *
   * HATTERBEN fut, a valaszra NEM varunk. Az elso valtozat megvarta, hogy
   * atjojjon a valasz, masfel masodperces korlattal - es eppen ezt nem
   * birta el egy valodi kor az OpenAI-hoz: a 2026-09-20-i fusttesztben
   * `APIConnectionTimeoutError` lett belole, valtas nelkul, es a hivas
   * vegig rossz nyelven ment. A ket hibaag nem egyenrangu: egy kesobb
   * megerkezo valtas egyetlen mondatba kerul, egy elmaradt valtas az egesz
   * hivasba. Ezert inkabb varunk rea egy fordulot, es adunk neki elegendo
   * idot.
   *
   * Addig probalkozik, amig hatarozott valaszt nem kap, de legfeljebb
   * LANG_CHECK_LIMIT-szer: egy "Hallo" mindket nyelven letezik, es ha az
   * elso probalkozas utan feladnank, az ilyen hivas vegig rossz nyelven
   * menne. A felso korlat azert kell, hogy egy vegig ertelmezhetetlen hivas
   * ne fizessen minden fordulora egy plusz modellhivast.
   *
   * Barmilyen hiba eseten marad a magyar, es megy tovabb a hivas: ez a
   * lepes soha nem allithatja meg es nem lassithatja a beszelgetest.
   */
  const LANG_CHECK_LIMIT = 3;
  const LANG_CHECK_TIMEOUT_MS = 6_000;

  const maybeSwitchLang = (utterance: string): void => {
    if (langFixed || s.langChecks >= LANG_CHECK_LIMIT) return;
    s.langChecks += 1;

    void (async () => {
      const startedAt = Date.now();
      try {
        const spoken = await detectSpokenLang(utterance, {
          timeoutMs: LANG_CHECK_TIMEOUT_MS,
        });
        // A valos idozites naplozva, mert az elso valtozat pont ezen bukott
        // el: masfel masodpercre volt beallitva, es nem fert bele.
        console.log(
          `[ws] nyelvfelismeres lang=${spoken ?? 'bizonytalan'} ` +
            `ido=${Date.now() - startedAt}ms callSid=${s.callSid}`,
        );
        if (!spoken || s.closed) return;
        s.langChecks = LANG_CHECK_LIMIT; // hatarozott valasz: tobbet nem kerdezunk
        switchLang(spoken);
      } catch (err) {
        // Nem hatasa a hivasra: a kovetkezo fordulo ujra probalkozik.
        console.warn('[ws] nyelvfelismeres nem jott vissza:', err);
      }
    })();
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
        // Elinditjuk, de nem varunk ra: a valasz azonnal indul, a nyelvvaltas
        // pedig akkor lep eletbe, amikor megjon - jellemzoen a kovetkezo
        // fordulora. Lasd a fuggveny magyarazatat.
        maybeSwitchLang(text);
        s.history.push({ role: 'user', content: text });
        await speakReply();

        // A beszed alatt eldontott valtas most lephet eletbe.
        if (s.pendingLang) {
          const next = s.pendingLang;
          s.pendingLang = null;
          switchLang(next);
        }

        if (s.needsRepeat && !s.closed) {
          s.needsRepeat = false;
          // A felreirt kerdes es a ra adott, mar rossz nyelvu valasz kikerul
          // a tortenetbol: egyik sem tortent meg ugy, ahogy ott all, es a
          // modell kesobb erre epitene.
          s.history.splice(-2, 2);
          const askAgain = say().switched;
          send(askAgain, true);
          s.history.push({ role: 'assistant', content: askAgain });
          continue;
        }

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
        console.log(
          `[ws] setup from=${s.from} callSid=${s.callSid} ` +
            `nyelv=${s.lang}${langFixed ? ' (valasztott)' : ' (alapertelmezett)'}`,
        );
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
        //
        // Ez az ag korabban NEM naplozott semmit, es pontosan emiatt volt
        // nehez megtalalni, miert erkeztek felbevagott mondatok a masik
        // oldalra ("Wie viele Personen sind bei Ihnen mit E"). Egy csonkolt
        // valasz nem tunhet el nyomtalanul.
        const last = s.history[s.history.length - 1];
        if (last && last.role === 'assistant' && said && said !== last.content) {
          console.log(
            `[ws] felbeszakitva felolvasas kozben callSid=${s.callSid} ` +
              `${said.length}/${last.content.length} karakter hangzott el`,
          );
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
