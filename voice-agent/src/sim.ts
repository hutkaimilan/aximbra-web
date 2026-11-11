/**
 * Szoveges hivas-szimulator.
 *
 * A VALODI agent-promptot es -modellt futtatja egy teszt-hivo ellen, telefon
 * nelkul: nincs Twilio-koltseg, nincs beszedfelismeres, csak a ket modell
 * beszelget. Amit mer, az a TARTALOM: tegez-e, mond-e kerdes nelkul arat,
 * siet-e a zarassal, kerdezi-e ketszer a nevet, felsorolja-e az osszes
 * agentet, ha kerik. Az idozites (bekoszones, belevagas) mas kerdes, azt a
 * relay e2e-tesztjei es a valodi hivasok merik.
 *
 * Miert kell: a hibak eddig egyesevel, eles hivasban derultek ki, a
 * tulajdonos telefonjan. Egy promptvaltozas hatasat igy csak ujabb eles
 * hivas mutatta meg - most egy futas tobb tucat beszelgetest ellenoriz,
 * gepi szabalyokkal es egy kulon ertekelo modellel.
 *
 * A szoveg-feldolgozas UGYANAZ, mint a server.ts speakReply-ban: ugyanaz a
 * rendszerprompt, ugyanazok a szurok (bontasjel, tegezes, ismetelt "van meg
 * kerdese"), ugyanaz a tenykinyeres. Ha ott valtozik, itt is kell.
 */
import {
  buildSystemPrompt,
  callbackGreeting,
  lines,
  FACTS_PROMPT,
} from './prompt.js';
import {
  replyStream,
  reply,
  extractFacts,
  emptyFacts,
  mergeFacts,
  chatJson,
  type Turn,
  type CallFacts,
} from './llm.js';
import { END_CALL_MARKER, stripMarker } from './hangup.js';
import { MORE_QUESTIONS_RE, dropPattern, dropSentences, formalize } from './turn.js';
import {
  scenarioByKey,
  openerFor,
  buildTesterPrompt,
  phaseNote,
  END_MARKER,
  type Scenario,
} from './testPrompt.js';
import { env } from './env.js';
import type { Lang } from './routing.js';
import crypto from 'node:crypto';
import { stats } from './limit.js';

const sleep = (ms: number): Promise<void> => new Promise((r) => setTimeout(r, ms));

/**
 * Ha eppen eles hivas fut, a szimulator var: ugyanazon a modell-kereten
 * osztoznak, es egy teszt nem veheti el a kvotat egy valodi hivotol.
 */
async function yieldToLiveCalls(): Promise<void> {
  while (stats().live > 0) await sleep(5_000);
}

export interface SimTurn {
  who: 'agent' | 'caller';
  text: string;
  /** Agentnel: az elso token ideje es a teljes valaszido (ms). */
  ttftMs?: number;
  ms?: number;
}

export interface SimIssue {
  check: string;
  /** A beszelgetes hanyadik sora (0 = koszones). */
  at: number;
  quote: string;
}

export interface SimRun {
  scenario: string;
  mode: 'callback' | 'inbound';
  model: string;
  turns: SimTurn[];
  ended: 'agent' | 'caller' | 'limit' | 'error';
  issues: SimIssue[];
  judge?: { violations: Array<{ rule: string; quote: string }>; score?: number } | null;
  error?: string;
}

export interface SimBatch {
  id: string;
  startedAt: string;
  finishedAt?: string;
  status: 'running' | 'done' | 'failed';
  params: SimParams;
  done: number;
  total: number;
  runs: SimRun[];
  error?: string;
}

export interface SimParams {
  scenarios: string[];
  runs: number;
  model?: string;
  effort?: string;
  /** A teszt-hivo es a tenykinyeres modellje (kulon keret). */
  auxModel?: string;
  testerModel?: string;
  judgeModel?: string;
  judge: boolean;
  maxTurns: number;
  concurrency: number;
}

/* ------------------------------------------------------------------ */
/* Gepi szabalyok                                                       */
/* ------------------------------------------------------------------ */

/** Szohatarral, ekezetes betukre is (a \b csak ASCII-t ismer). */
const W = (alts: string): RegExp => new RegExp(`(?<![\\p{L}])(?:${alts})(?![\\p{L}])`, 'iu');

export const INFORMAL_RE = W(
  [
    'nálatok', 'nektek', 'titeket', 'benneteket', 'veletek', 'tőletek', 'hozzátok', 'rólatok',
    'nálad', 'neked', 'téged', 'veled', 'tőled', 'hozzád', 'rólad',
    'szeretnél', 'szeretnéd', 'szeretnétek', 'tudod', 'tudnád', 'tudnál', 'tudnátok', 'tudjátok',
    'mondd', 'mondjátok', 'csinálod', 'csináljátok', 'csináltok', 'ajánlanál', 'küldd',
    'küldjétek', 'beszéljétek', 'kérlek', 'szia', 'sziasztok', 'hallod', 'figyelj', 'nézd',
    'nézzétek', 'gondolod', 'akarod', 'akarsz', 'akartok', 'vagytok', 'lennél', 'kérdezel',
    'kérdeznél', 'hívtál', 'hívsz', 'szólj', 'írj', 'használtok', 'dolgoztok', 'foglalkoztok',
    'maradj', 'várj', 'mesélj', 'meséld', 'nyugodtan írj', 'segíthetek neked',
  ].join('|'),
);

const PRICE_SAID_RE = /(?<![\p{L}])(?:forint\p{L}*|ft)(?![\p{L}])|(?<![\p{L}])\p{L}*(?:ezer|millió)(?![\p{L}])/iu;
const PRICE_ASKED_RE =
  /mennyibe|(?<![\p{L}])ár(?:a|at|ak|áról|ban|ért|on|ai|ra)?(?![\p{L}])|költ|díj|fizet|drága|olcsó|kedvezmény|price|cost|how much|fee|budget|(?<![\p{L}])pay/iu;
const CLOSING_RE =
  /kihez címezzem|melyik cégnél|hogy hívják|mi a (?:neve|cég)|mi az ön neve|a nevét|küldjem|(?<![\p{L}])sms|ajánlatot (?:küld|össze|készít|kér)|elküldöm|felírom|felírhatom|who should i address|which company|send (?:it|you)|text message/iu;
const NAME_ASK_RE = /kihez címezzem|melyik cégnél|hogy hívják|mi a neve|mi az ön neve|a nevét|who should i address|your name/iu;
const QUESTION_RE =
  /\?|(?<![\p{L}])(?:mennyibe|hogyan|milyen|mikor|hol|miért|melyik|tudna|lehetne|van-e|kell-e|how|what|when|where|why|which)(?![\p{L}])/iu;
const OFFER_REQUEST_RE =
  /ajánlat|küldjenek|küldjön|küldjék|küldené|elérhetőség|felír|címem|a számom|hívjanak|keressenek|kollég|visszahív|quote|send me|my email|call me back|contact/iu;
const CALLER_DONE_RE =
  /nincs (?:több|más) kérdés|ennyi (?:lenne|volt|elég)|mindent (?:értek|megértettem)|minden világos|ez (?:minden|elég)|that'?s (?:all|everything)|no (?:more|other) questions/iu;
const REGREET_RE = /jó napot|üdvözlöm|(?<![\p{L}])miben segíthetek|(?<![\p{L}])szia(?![\p{L}])/iu;
const LIST_ASK_RE = /összes|mindet|mindegyik|all (?:of )?(?:the|your) agents/iu;
const LIST_STEMS: RegExp[] = [
  /e-?mail rendez/iu, /adminisztrác/iu, /kutatás/iu, /érdeklődő/iu, /tartalom/iu,
  /webshop/iu, /értékesítő/iu, /üzemeltet/iu, /nis ?2|nis kettő/iu, /ügyfélszolgálat/iu,
  /toborz/iu, /dokumentum/iu, /pénzügyi/iu, /több-?agent|multi/iu,
];

function words(text: string): number {
  return text.split(/\s+/).filter(Boolean).length;
}

function similarity(a: string, b: string): number {
  const A = new Set(a.toLowerCase().split(/\W+/u).filter(Boolean));
  const B = new Set(b.toLowerCase().split(/\W+/u).filter(Boolean));
  if (A.size === 0 || B.size === 0) return 0;
  let inter = 0;
  for (const x of A) if (B.has(x)) inter += 1;
  return inter / Math.min(A.size, B.size);
}

/** A beszelgetes gepi ellenorzese. Csak az AGENT sorait vizsgalja. */
export function checkTranscript(turns: SimTurn[], scenarioKey: string): SimIssue[] {
  const issues: SimIssue[] = [];
  const add = (check: string, at: number, quote: string): void => {
    issues.push({ check, at, quote: quote.slice(0, 220) });
  };

  let priceAsked = false;
  let askedMore = 0;
  let nameAsks = 0;
  let listAsked = false;
  let listAnswered = false;
  let questionStreak = 0;
  let callerRequestedOffer = false;
  let dataAsked = false;

  for (let i = 0; i < turns.length; i += 1) {
    const t = turns[i]!;
    if (t.who === 'caller') {
      if (PRICE_ASKED_RE.test(t.text)) priceAsked = true;
      if (LIST_ASK_RE.test(t.text)) listAsked = true;
      if (OFFER_REQUEST_RE.test(t.text)) callerRequestedOffer = true;
      if (/adat|gdpr|biztonság|tárol|titok|privacy|data/iu.test(t.text)) dataAsked = true;
      continue;
    }
    if (i === 0) continue; // a koszones rogzitett szoveg

    const text = t.text;
    const prev = [...turns.slice(0, i)].reverse().find((x) => x.who === 'caller');
    const prevText = prev?.text ?? '';

    const informal = INFORMAL_RE.exec(text);
    if (informal) add('tegezes', i, `"${informal[0]}" - ${text}`);

    if (!priceAsked && PRICE_SAID_RE.test(text)) add('ar_kerdes_nelkul', i, text);

    const closing = CLOSING_RE.test(text);
    const callerAsks = QUESTION_RE.test(prevText) && !CALLER_DONE_RE.test(prevText);
    if (closing && callerAsks && !OFFER_REQUEST_RE.test(prevText)) {
      add('zaras_kerdes_kozben', i, text);
    }
    if (closing && askedMore === 0 && !callerRequestedOffer && !CALLER_DONE_RE.test(prevText)) {
      add('zaras_van_meg_kerdese_nelkul', i, text);
    }

    if (NAME_ASK_RE.test(text)) {
      nameAsks += 1;
      if (nameAsks > 1) add('nev_tobbszor', i, text);
    }

    if (MORE_QUESTIONS_RE.test(text)) {
      askedMore += 1;
      if (askedMore > 1) add('van_meg_kerdese_tobbszor', i, text);
    }

    if (/folytassam/iu.test(text)) add('folytassam', i, text);

    if (listAsked && !listAnswered && (scenarioKey === 'lista' || LIST_ASK_RE.test(prevText))) {
      listAnswered = true;
      const hit = LIST_STEMS.filter((r) => r.test(text)).length;
      if (hit < 13) add('lista_hianyos', i, `${hit}/14 agent: ${text}`);
    } else if (words(text) > 75) {
      add('tul_hosszu', i, `${words(text)} szo: ${text}`);
    }

    if (/\d/.test(text.replace(/NIS ?2/giu, ''))) add('szamjegy', i, text);

    if ((text.match(/\?/g) ?? []).length > 1) add('tobb_kerdes', i, text);

    if (REGREET_RE.test(text)) add('ujra_koszon', i, text);

    if (/bizalmas/iu.test(text) && !dataAsked) add('adatkezeles_ismetles', i, text);

    if (/aximbra kukac gmail|aximbra@gmail/iu.test(text) && !/hova|írhat|e-?mail ?cím(?:e|ük)|where|write/iu.test(prevText)) {
      add('sajat_email_felkinalva', i, text);
    }

    // Kikerdezes: harom egymast koveto agent-valasz vege kerdes.
    if (/\?\s*$/u.test(text) && !MORE_QUESTIONS_RE.test(text) && !NAME_ASK_RE.test(text)) {
      questionStreak += 1;
      if (questionStreak >= 3) add('kikerdezes', i, text);
    } else {
      questionStreak = 0;
    }

    const prevAgent = [...turns.slice(1, i)].reverse().find((x) => x.who === 'agent');
    if (prevAgent && similarity(prevAgent.text, text) > 0.85 && words(text) > 6) {
      add('ismetles', i, text);
    }
  }
  return issues;
}

/* ------------------------------------------------------------------ */
/* Ertekelo modell                                                      */
/* ------------------------------------------------------------------ */

const JUDGE_PROMPT = `Egy AI telefonos ügynök (AGENT, az AXIMBRA munkatársa) beszélgetését értékeled egy érdeklődővel (HÍVÓ). Szigorú vagy: a tulajdonos minden apró hibát kifogásol.

CSAK AZ AGENT SORAIT értékeld. A HÍVÓ mondhat bármit (tegezhet is) — az nem hiba. A HÍVÓ szavait soha ne tulajdonítsd az agentnek.

Ezeket a hibákat keresd az AGENT soraiban:
1. Tegezés: bármilyen tegező alak ("nálatok", "szeretnél", "neked", "mondd", "kérlek"). Az egyes szám első személy ("folytassam", "küldjem") NEM tegezés.
2. Kéretlen ár: árat mondott, mielőtt a hívó az árra rákérdezett volna.
3. Siettetett zárás: ajánlatot, SMS-t vagy e-mailt ajánlott fel, vagy nevet/céget kérdezett, miközben a hívó még kérdezett vagy mesélt, illetve mielőtt megkérdezte volna, van-e még kérdése (kivéve, ha a hívó maga kért ajánlatot vagy visszahívást).
4. A nevet/céget többször kérdezte.
5. A "Van még kérdése?" többször hangzott el.
6. Kitalált adat: ár, határidő vagy állítás, ami nincs az alábbi árlistában (az egyedi és a telefonos agentnek nincs fix ára).
7. Két agent árát összevonta egy közös sávba.
8. Nem válaszolt a hívó kérdésére, kitért, vagy mást válaszolt.
9. Kikérdezés: három vagy több egymást követő válasza a hívó helyzetére vonatkozó kérdéssel zárult.
10. Újra köszönt, újra bemutatkozott, vagy megismételte az adatkezelési mondatot.
11. Túl hosszú válasz telefonhoz (három mondatnál több), kivéve, ha a hívó az összes agent felsorolását kérte.
12. Felsorolás közben megkérdezte, folytassa-e, pedig a hívó az összeset kérte; vagy nem sorolta fel mindet.
13. Bontani akart (elköszönt), miközben a hívónak még volt kérdése.
14. Magyartalan, gépies vagy nyelvtanilag hibás mondat; számjegyek használata kimondott szám helyett.

ÁRLISTA (forintban): e-mail rendező, belső adminisztrációs agent, kutatás-monitor: 150 000–400 000, 2–3 hét. Érdeklődő-minősítő, tartalom-agent: 400 000–1 200 000. Webshop-asszisztens, értékesítő agent: 600 000–1 500 000. IT-üzemeltetési, NIS2: 600 000–2 000 000. Ügyfélszolgálati: 1 500 000–4 000 000. Toborzó: 1 700 000–3 900 000. Dokumentum-elemző, pénzügyi asszisztens: 2 000 000–4 000 000. Több-agentes rendszer: 6 000 000–15 000 000, 7–12 hét. Weboldal: 120 000 (egyoldalas), 290 000 (többoldalas), 900 000-től (egyedi). Az első 15 ügyfélnek egy hónap ingyen, utána a becsült ár 20%-a, a havidíjról előre megállapodnak. Az agentek 150 000 Ft-tól indulnak.

CSAK JSON-t adj vissza:
{"violations": [{"rule": "a szabály száma és neve", "quote": "az AGENT pontos mondata"}], "score": 1-10}
Ha nincs hiba, a violations üres lista. Ne találj ki hibát: csak azt írd, amit idézni tudsz az AGENT soraiból.`;

async function judgeRun(turns: SimTurn[], model?: string): Promise<SimRun['judge']> {
  const transcript = turns.map((t) => `${t.who === 'agent' ? 'AGENT' : 'HÍVÓ'}: ${t.text}`).join('\n');
  const out = (await chatJson(JUDGE_PROMPT, transcript, { model, maxTokens: 1500 })) as
    | { violations?: unknown; score?: unknown }
    | null;
  if (!out || !Array.isArray(out.violations)) return null;
  const violations = out.violations
    .filter((v): v is { rule: unknown; quote: unknown } => typeof v === 'object' && v !== null)
    .map((v) => ({ rule: String(v.rule ?? ''), quote: String(v.quote ?? '') }));
  return { violations, score: typeof out.score === 'number' ? out.score : undefined };
}

/* ------------------------------------------------------------------ */
/* Egy szimulalt hivas                                                  */
/* ------------------------------------------------------------------ */

function isQuotaError(err: unknown): boolean {
  const e = err as { status?: number } | null;
  return !!e && e.status === 429;
}

/** Egy agent-fordulo - pontosan ugy, ahogy a server.ts speakReply kesziti. */
async function agentTurn(
  history: Turn[],
  facts: CallFacts,
  from: string,
  lang: Lang,
  model?: string,
  effort?: string,
): Promise<{ text: string; ended: boolean; ttftMs: number; ms: number }> {
  const dropRe = dropPattern(history);
  const prompt = buildSystemPrompt(env().currentProjects, facts, from, lang, history);
  const t0 = Date.now();
  let ttft = -1;
  const run = (m?: string): Promise<string> =>
    replyStream(
      history,
      prompt,
      () => {
        if (ttft < 0) ttft = Date.now() - t0;
      },
      { maxTokens: 700, temperature: 0.3, timeoutMs: 20_000, model: m, reasoningEffort: effort },
    );
  // Ugyanaz a ket lepes, mint elesben: fo modell, hiba eseten a tartalek.
  let full: string;
  try {
    full = await run(model);
  } catch (err) {
    const fb = env().fallbackModel || undefined;
    if (isQuotaError(err) && !fb) throw err;
    full = await run(fb ?? model);
  }
  return {
    text: dropSentences(formalize(stripMarker(full)), dropRe),
    ended: full.includes(END_CALL_MARKER),
    ttftMs: ttft,
    ms: Date.now() - t0,
  };
}

async function callerTurn(
  scenario: Scenario,
  history: Turn[],
  remaining: number,
  model?: string,
): Promise<{ text: string; ended: boolean }> {
  // A teszt-hivo szemszogebol az agent a "user", o maga az "assistant".
  const flipped: Turn[] = history.map((t) => ({
    role: t.role === 'assistant' ? 'user' : 'assistant',
    content: t.content,
  }));
  const raw0 = await reply(flipped, buildTesterPrompt(scenario) + phaseNote(remaining, scenario), {
    maxTokens: 700,
    temperature: 0.4,
    timeoutMs: 20_000,
    // A teszt-hivo a hatter-modellen: ne egye a beszelgeto modell keretet.
    model: model ?? (env().auxModel || undefined),
  });
  // Nehany modell (pl. Gemma) a gondolatmenetet is a valaszba irja - az nem
  // a hivo mondata, es a tesztelt agentet osszezavarna.
  const raw = raw0
    .replace(/<thought>[\s\S]*?<\/thought>/giu, '')
    .replace(/<thought>[\s\S]*$/iu, '')
    .trim();
  return { text: raw.replace(END_MARKER, '').trim(), ended: raw.includes(END_MARKER) };
}

export async function simulateCall(
  scenarioKey: string,
  opts: {
    model?: string;
    effort?: string;
    auxModel?: string;
    testerModel?: string;
    judgeModel?: string;
    judge: boolean;
    maxTurns: number;
  },
): Promise<SimRun> {
  const scenario = scenarioByKey(scenarioKey);
  const lang: Lang = scenario.lang === 'en' ? 'en' : 'hu';
  // A magyar erdeklodok jellemzoen a weboldalrol kernek visszahivast; a
  // kulfoldi hivo bejovo hivassal jon.
  const mode: SimRun['mode'] = lang === 'hu' ? 'callback' : 'inbound';
  const from = mode === 'callback' ? '+36301234567' : '+447700900123';
  const model = opts.model ?? env().model;

  const turns: SimTurn[] = [];
  const history: Turn[] = [];
  let facts: CallFacts = emptyFacts();
  const run: SimRun = { scenario: scenario.key, mode, model, turns, ended: 'limit', issues: [] };

  const greeting = mode === 'callback' ? callbackGreeting(lang) : lines(lang).greeting;
  history.push({ role: 'assistant', content: greeting });
  turns.push({ who: 'agent', text: greeting });

  let callerText = openerFor(scenario);
  let callerEnded = false;
  try {
    for (let i = 0; i < opts.maxTurns; i += 1) {
      await yieldToLiveCalls();
      // Kis szunet fordulonkent: a percenkenti keret szuk.
      await sleep(1_500);
      history.push({ role: 'user', content: callerText });
      turns.push({ who: 'caller', text: callerText });

      const a = await agentTurn(history, facts, from, lang, opts.model, opts.effort);
      history.push({ role: 'assistant', content: a.text });
      turns.push({ who: 'agent', text: a.text, ttftMs: a.ttftMs, ms: a.ms });

      const found = await extractFacts(history, FACTS_PROMPT, {
        maxTokens: 300,
        timeoutMs: 15_000,
        model: opts.auxModel,
      });
      if (found) facts = mergeFacts(facts, found);

      if (a.ended) {
        run.ended = 'agent';
        break;
      }
      if (callerEnded) {
        run.ended = 'caller';
        break;
      }
      const tester = opts.testerModel ?? opts.auxModel;
      let c: { text: string; ended: boolean };
      try {
        c = await callerTurn(scenario, history, opts.maxTurns - i - 1, tester);
      } catch (err) {
        if (isQuotaError(err)) throw err;
        await sleep(3_000);
        c = await callerTurn(scenario, history, opts.maxTurns - i - 1, tester);
      }
      callerText = c.text || (lang === 'en' ? 'Okay.' : 'Értem.');
      // A hivo elkoszont: meg egy agent-fordulo jar ra (elesben is igy van).
      callerEnded = c.ended;
    }
  } catch (err) {
    run.ended = 'error';
    run.error = String(err);
    if (isQuotaError(err)) run.error = `KVOTA (429): ${String(err)}`;
  }

  run.issues = checkTranscript(turns, scenario.key);
  if (opts.judge && turns.length > 2) {
    run.judge = await judgeRun(turns, opts.judgeModel);
  }
  return run;
}

/* ------------------------------------------------------------------ */
/* Futtatas hatterben, eredmeny memoriaban                              */
/* ------------------------------------------------------------------ */

const batches = new Map<string, SimBatch>();

export function getSimBatch(id: string): SimBatch | null {
  return batches.get(id) ?? null;
}

export function runningSimBatch(): SimBatch | null {
  for (const b of batches.values()) if (b.status === 'running') return b;
  return null;
}

export function startSimBatch(params: SimParams): SimBatch {
  const id = crypto.randomBytes(6).toString('hex');
  const jobs: string[] = [];
  for (const s of params.scenarios) for (let r = 0; r < params.runs; r += 1) jobs.push(s);
  const batch: SimBatch = {
    id,
    startedAt: new Date().toISOString(),
    status: 'running',
    params,
    done: 0,
    total: jobs.length,
    runs: [],
  };
  batches.set(id, batch);
  // A regi eredmenyek ne gyuljenek a vegtelensegig.
  if (batches.size > 20) {
    const oldest = [...batches.keys()][0];
    if (oldest && oldest !== id) batches.delete(oldest);
  }

  void (async () => {
    let next = 0;
    let quotaHit = false;
    const worker = async (): Promise<void> => {
      while (!quotaHit) {
        const k = next;
        next += 1;
        if (k >= jobs.length) return;
        const r = await simulateCall(jobs[k]!, {
          model: params.model,
          effort: params.effort,
          auxModel: params.auxModel,
          testerModel: params.testerModel,
          judgeModel: params.judgeModel,
          judge: params.judge,
          maxTurns: params.maxTurns,
        });
        batch.runs.push(r);
        batch.done += 1;
        if (r.error?.startsWith('KVOTA')) quotaHit = true;
      }
    };
    try {
      await Promise.all(Array.from({ length: Math.max(1, params.concurrency) }, () => worker()));
      batch.status = quotaHit ? 'failed' : 'done';
      if (quotaHit) batch.error = 'A modell kvotaja elfogyott (429) - a futas leallt.';
    } catch (err) {
      batch.status = 'failed';
      batch.error = String(err);
    } finally {
      batch.finishedAt = new Date().toISOString();
      console.log(`[sim] kesz id=${id} ${batch.done}/${batch.total} status=${batch.status}`);
    }
  })();

  return batch;
}


/* ------------------------------------------------------------------ */
/* Valaszido-meres: egyetlen fordulo, tobbszor                          */
/* ------------------------------------------------------------------ */

export interface ProbeResult {
  model: string;
  effort: string;
  ttftMs: number[];
  totalMs: number[];
  errors: string[];
  sample: string;
}

/**
 * Ugyanazt az elso valaszt keri `n`-szer, egymas utan, es meri, mikor jon az
 * elso token. A valodi rendszerpromptot es egy valodi elso hivoi mondatot
 * hasznal. Sorban fut, kis szunettel, hogy ne egye meg a percenkenti keretet.
 */
export async function probeLatency(opts: { model?: string; effort?: string; n: number }): Promise<ProbeResult> {
  const history: Turn[] = [
    { role: 'assistant', content: callbackGreeting('hu') },
    {
      role: 'user',
      content: 'Jó napot, Kovács Péter vagyok a győri Kovács Optikától. Az e-mail-kezelés automatizálása miatt keresem önöket.',
    },
  ];
  const prompt = buildSystemPrompt(env().currentProjects, emptyFacts(), '+36301234567', 'hu', history);
  const out: ProbeResult = {
    model: opts.model ?? env().model,
    effort: opts.effort ?? '',
    ttftMs: [],
    totalMs: [],
    errors: [],
    sample: '',
  };
  for (let i = 0; i < opts.n; i += 1) {
    const t0 = Date.now();
    let ttft = -1;
    try {
      const full = await replyStream(
        history,
        prompt,
        () => {
          if (ttft < 0) ttft = Date.now() - t0;
        },
        { maxTokens: 700, temperature: 0.3, timeoutMs: 30_000, model: opts.model, reasoningEffort: opts.effort },
      );
      out.ttftMs.push(ttft);
      out.totalMs.push(Date.now() - t0);
      if (!out.sample) out.sample = full;
    } catch (err) {
      out.errors.push(String(err).slice(0, 200));
    }
    await new Promise((r) => setTimeout(r, 2500));
  }
  return out;
}
