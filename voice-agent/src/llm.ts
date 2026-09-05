/**
 * OpenAI-reteg.
 *
 * Harom kulon feladat, harom kulon beallitas:
 *   replyStream() - eles hivas kozben. Tokenenkent adja vissza a valaszt,
 *                   hogy a ConversationRelay mar az elso szavaknal
 *                   elkezdhesse a felolvasast. Ez a hivas erzekelt
 *                   varakozasat masodpercekrol tizedmasodpercekre viszi le.
 *   reply()       - ott, ahol nincs ertelme a streamnek (teszt-agent: a
 *                   TwiML-t ugyis egyben kell visszaadni).
 *   summarize()   - hivas utan, egyszer. Strukturalt JSON.
 *
 * Latencia a fo megkotes: telefonon minden masodperc csend ugy hangzik,
 * mintha megszakadt volna a vonal.
 */

import OpenAI from 'openai';
import { env } from './env.js';
import { SUMMARY_PROMPT } from './prompt.js';

export interface Turn {
  role: 'user' | 'assistant';
  content: string;
}

export interface ReplyOptions {
  model?: string;
  maxTokens?: number;
  temperature?: number;
  timeoutMs?: number;
  /** Felbeszakitaskor ezzel allitjuk le a mar futo streamet. */
  signal?: AbortSignal;
}

let client: OpenAI | null = null;

function openai(): OpenAI {
  if (!client) {
    client = new OpenAI({
      apiKey: env().openaiApiKey,
      timeout: 12_000,
      // Streamnel az ujraprobalas felmondat utan ujrakezdene a szoveget,
      // ezert a retryt hivasonkent allitjuk, nem globalisan.
      maxRetries: 0,
    });
  }
  return client;
}

function buildMessages(
  history: Turn[],
  systemPrompt: string,
): OpenAI.Chat.ChatCompletionMessageParam[] {
  return [
    { role: 'system', content: systemPrompt },
    ...history.map((t) => ({ role: t.role, content: t.content }) as const),
  ];
}

/**
 * Egy beszelgetesi fordulo valasza, egyben.
 *
 * A teljes eddigi tortenetet elkuldjuk minden alkalommal: a modell allapot
 * nelkuli, a "memoria" maga a tortenet.
 */
export async function reply(
  history: Turn[],
  systemPrompt: string,
  opts: ReplyOptions = {},
): Promise<string> {
  const completion = await openai().chat.completions.create(
    {
      model: opts.model ?? env().model,
      messages: buildMessages(history, systemPrompt),
      max_tokens: opts.maxTokens ?? 220,
      // Alacsony homerseklet: telefonos felvetelnel a kiszamithatosag
      // tobbet er, mint a valtozatossag. Magas ertek mellett a modell
      // hajlamos ujra bemutatkozni es korbe-korbe kerdezni.
      temperature: opts.temperature ?? 0.3,
    },
    { timeout: opts.timeoutMs ?? 12_000, maxRetries: 1, signal: opts.signal },
  );

  const text = completion.choices[0]?.message?.content?.trim();
  if (!text) throw new Error('Ures valasz a modelltol');
  return text;
}

/**
 * Ugyanaz, de tokenenkent.
 *
 * `onDelta` minden szovegdarabra meghivodik, ahogy erkezik. A fuggveny a
 * teljes osszefuzott szoveggel ter vissza.
 *
 * Felbeszakitasnal az `opts.signal` abortalodik: ilyenkor a ciklus kivetelt
 * dob, es a MAR KIMONDOTT resz a hivo felelossege (o gyujti az `onDelta`
 * darabokat). Ezert nem dobunk el semmit itt.
 */
export async function replyStream(
  history: Turn[],
  systemPrompt: string,
  onDelta: (delta: string) => void,
  opts: ReplyOptions = {},
): Promise<string> {
  const stream = await openai().chat.completions.create(
    {
      model: opts.model ?? env().model,
      messages: buildMessages(history, systemPrompt),
      max_tokens: opts.maxTokens ?? 220,
      temperature: opts.temperature ?? 0.3,
      stream: true,
    },
    { timeout: opts.timeoutMs ?? 12_000, maxRetries: 0, signal: opts.signal },
  );

  let full = '';
  for await (const chunk of stream) {
    const delta = chunk.choices[0]?.delta?.content;
    if (!delta) continue;
    full += delta;
    onDelta(delta);
  }

  if (!full.trim()) throw new Error('Ures valasz a modelltol');
  return full.trim();
}

/* ------------------------------------------------------------------ */
/* Hivas kozbeni tenyek                                                 */
/* ------------------------------------------------------------------ */

/**
 * Amit a hivas soran mar biztosan megtudtunk.
 *
 * MIERT KELL EZ: a teljes beszelgetes amugy is elmegy a modellnek minden
 * fordulonal, tehat az informacio "ott van". A gond az, hogy egy zajos,
 * beszedfelismerobol szarmazo atiratban egy konkret adat nem ugrik ki: az
 * e-mail cim ugy hangzik el, hogy "kovacs pont peter kukac ...", nem pedig
 * @ jellel. Egy valodi felvetelen emiatt az agent MASODSZOR is elkerte az
 * e-mail cimet, pedig mar lediktaltak neki.
 *
 * A megoldas nem uj memoria, hanem KIEMELES: a mar ismert adatokat
 * kigyujtjuk, es a rendszerprompt elejere tesszuk, kifejezett tiltassal.
 */
export interface CallFacts {
  nev: string | null;
  ceg: string | null;
  email: string | null;
  telefon: string | null;
  feladat: string | null;
  cegmeret: string | null;
  volumen: string | null;
  jelenlegi_megoldas: string | null;
  idozites: string | null;
  dontesi_kor: string | null;
}

export function emptyFacts(): CallFacts {
  return {
    nev: null,
    ceg: null,
    email: null,
    telefon: null,
    feladat: null,
    cegmeret: null,
    volumen: null,
    jelenlegi_megoldas: null,
    idozites: null,
    dontesi_kor: null,
  };
}

const FACT_KEYS = Object.keys(emptyFacts()) as (keyof CallFacts)[];

function cleanFact(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const t = value.trim();
  if (t === '') return null;
  // A modell hajlamos ures ertek helyett szoveget irni.
  const empty = ['null', 'nem hangzott el', 'ismeretlen', 'nincs', '-', 'n/a'];
  if (empty.includes(t.toLowerCase())) return null;
  if (t.length > 200) return t.slice(0, 200);
  return t;
}

/**
 * Egy mar ismert tenyt SOHA nem irunk felul ureesel.
 *
 * A kinyeres nem determinisztikus: ha egy fordulonal a modell nem talalja
 * meg az e-mail cimet, attol az meg elhangzott. Csak bovitunk, illetve
 * ertelmes uj ertekre cserelunk.
 */
export function mergeFacts(prev: CallFacts, next: Partial<CallFacts>): CallFacts {
  const out: CallFacts = { ...prev };
  for (const key of FACT_KEYS) {
    const v = cleanFact(next[key]);
    if (v !== null) out[key] = v;
  }
  return out;
}

/**
 * Kigyujti a beszelgetesbol a mar elhangzott adatokat.
 *
 * SZANDEKOSAN a valasz KIKULDESE UTAN fut, hattarben: igy nem novel
 * varakozast a vonalon. Ennek ara, hogy a frissites egy fordulot kesik -
 * ami eleg, mert a kovetkezo kerdes elott mar rendelkezesre all.
 *
 * Hiba eseten null-t ad vissza, es a hivo megtartja a korabbi tenyeket.
 * A hivas soha nem allhat meg amiatt, hogy ez a lepes elszallt.
 */
export async function extractFacts(
  history: Turn[],
  factsPrompt: string,
  opts: ReplyOptions = {},
): Promise<Partial<CallFacts> | null> {
  if (history.length === 0) return null;

  const transcript = history
    .map((t) => `${t.role === 'user' ? 'HÍVÓ' : 'AGENT'}: ${t.content}`)
    .join('\n');

  try {
    const completion = await openai().chat.completions.create(
      {
        model: opts.model ?? env().model,
        messages: [
          { role: 'system', content: factsPrompt },
          { role: 'user', content: transcript },
        ],
        response_format: { type: 'json_object' },
        max_tokens: opts.maxTokens ?? 300,
        temperature: 0,
      },
      { timeout: opts.timeoutMs ?? 10_000, maxRetries: 0, signal: opts.signal },
    );

    const raw = completion.choices[0]?.message?.content;
    if (!raw) return null;
    return JSON.parse(raw) as Partial<CallFacts>;
  } catch (err) {
    console.error('[llm] tenykinyeres sikertelen:', err);
    return null;
  }
}

export interface Summary {  nev: string;
  ceg: string;
  iparag: string;
  feladat: string;
  cegmeret: string;
  volumen: string;
  jelenlegi_megoldas: string;
  idozites: string;
  dontesi_kor: string;
  koltsegvetes_jel: string;
  elerhetoseg: string;
  javasolt_kategoria: string;
  minosites: string;
  indoklas: string;
  kovetkezo_lepes: string;
}

/**
 * Hivas utani strukturalt osszefoglalo.
 *
 * Ez mar nem latencia-erzekeny (a hivo letette), ezert nagyobb a keret es
 * hosszabb a timeout.
 */
export async function summarize(history: Turn[]): Promise<Summary | null> {
  if (history.length === 0) return null;

  const transcript = history
    .map((t) => `${t.role === 'user' ? 'HÍVÓ' : 'AGENT'}: ${t.content}`)
    .join('\n');

  try {
    const completion = await openai().chat.completions.create(
      {
        model: env().model,
        messages: [
          { role: 'system', content: SUMMARY_PROMPT },
          { role: 'user', content: transcript },
        ],
        response_format: { type: 'json_object' },
        max_tokens: 700,
        temperature: 0,
      },
      { timeout: 30_000, maxRetries: 1 },
    );

    const raw = completion.choices[0]?.message?.content;
    if (!raw) return null;

    const parsed = JSON.parse(raw) as Partial<Summary>;

    const fallback = 'nem hangzott el';
    return {
      nev: parsed.nev ?? fallback,
      ceg: parsed.ceg ?? fallback,
      iparag: parsed.iparag ?? fallback,
      feladat: parsed.feladat ?? fallback,
      cegmeret: parsed.cegmeret ?? fallback,
      volumen: parsed.volumen ?? fallback,
      jelenlegi_megoldas: parsed.jelenlegi_megoldas ?? fallback,
      idozites: parsed.idozites ?? fallback,
      dontesi_kor: parsed.dontesi_kor ?? fallback,
      koltsegvetes_jel: parsed.koltsegvetes_jel ?? 'Nem megítélhető',
      elerhetoseg: parsed.elerhetoseg ?? fallback,
      javasolt_kategoria: parsed.javasolt_kategoria ?? 'Nem egyértelmű',
      minosites: parsed.minosites ?? 'D',
      indoklas: parsed.indoklas ?? fallback,
      kovetkezo_lepes: parsed.kovetkezo_lepes ?? 'Visszahívás',
    };
  } catch (err) {
    console.error('[llm] osszefoglalo sikertelen:', err);
    return null;
  }
}
