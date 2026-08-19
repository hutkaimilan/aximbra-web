/**
 * OpenAI-reteg.
 *
 * Ket kulon feladat, ket kulon beallitas:
 *   reply()   - beszelgetes kozben, minden fordulonal. Rovid, gyors, olcso.
 *   summarize() - hivas utan, egyszer. Strukturalt JSON.
 *
 * Latencia a fo megkotes a reply()-nal: telefonon minden masodperc csend
 * ugy hangzik, mintha megszakadt volna a vonal. Ezert alacsony a
 * max_tokens es rovid a timeout - inkabb rovid valasz, mint keso valasz.
 */

import OpenAI from 'openai';
import { env } from './env.js';
import { SUMMARY_PROMPT } from './prompt.js';

export interface Turn {
  role: 'user' | 'assistant';
  content: string;
}

let client: OpenAI | null = null;

function openai(): OpenAI {
  if (!client) {
    client = new OpenAI({
      apiKey: env().openaiApiKey,
      // Rovid timeout: ha 12 masodperc alatt nincs valasz, a hivo mar
      // ugy erzi, megszakadt a vonal. Jobb hibauzenetet mondani.
      timeout: 12_000,
      maxRetries: 1,
    });
  }
  return client;
}

/**
 * Egy beszelgetesi fordulo valasza.
 *
 * A teljes eddigi tortenetet elkuldjuk minden alkalommal: a modell allapot
 * nelkuli, a "memoria" maga a tortenet. Ez az oka annak, hogy nem kell
 * kulon emlekezet-reteg egy hivason belul.
 */
export async function reply(history: Turn[], systemPrompt: string): Promise<string> {
  const messages: OpenAI.Chat.ChatCompletionMessageParam[] = [
    { role: 'system', content: systemPrompt },
    ...history.map((t) => ({ role: t.role, content: t.content }) as const),
  ];

  const completion = await openai().chat.completions.create({
    model: env().model,
    messages,
    // 220 token ~ 3-4 magyar mondat. Telefonon ennel hosszabb valasz
    // mar tul sok - a hivo kozbevag, es osszekeveredik a fonal.
    max_tokens: 220,
    temperature: 0.6,
  });

  const text = completion.choices[0]?.message?.content?.trim();
  if (!text) {
    throw new Error('Ures valasz a modelltol');
  }
  return text;
}

export interface Summary {
  nev: string;
  ceg: string;
  iparag: string;
  feladat: string;
  mennyiseg: string;
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
 * hosszabb a timeout. JSON-modot kenyszeritunk, hogy ne kelljen a valaszbol
 * kodblokkokat hamozni.
 */
export async function summarize(history: Turn[]): Promise<Summary | null> {
  if (history.length === 0) return null;

  const transcript = history
    .map((t) => `${t.role === 'user' ? 'HÍVÓ' : 'AGENT'}: ${t.content}`)
    .join('\n');

  try {
    const completion = await openai().chat.completions.create({
      model: env().model,
      messages: [
        { role: 'system', content: SUMMARY_PROMPT },
        { role: 'user', content: transcript },
      ],
      response_format: { type: 'json_object' },
      max_tokens: 700,
      temperature: 0,
    }, { timeout: 30_000 });

    const raw = completion.choices[0]?.message?.content;
    if (!raw) return null;

    const parsed = JSON.parse(raw) as Partial<Summary>;

    // Minden mezot kitoltunk: a hianyzo kulcs a kesobbi email-sablonban
    // "undefined"-kent jelenne meg, ami zavaro.
    const fallback = 'nem hangzott el';
    return {
      nev: parsed.nev ?? fallback,
      ceg: parsed.ceg ?? fallback,
      iparag: parsed.iparag ?? fallback,
      feladat: parsed.feladat ?? fallback,
      mennyiseg: parsed.mennyiseg ?? fallback,
      elerhetoseg: parsed.elerhetoseg ?? fallback,
      javasolt_kategoria: parsed.javasolt_kategoria ?? 'Nem egyértelmű',
      minosites: parsed.minosites ?? 'D',
      indoklas: parsed.indoklas ?? fallback,
      kovetkezo_lepes: parsed.kovetkezo_lepes ?? 'Visszahívás',
    };
  } catch (err) {
    // Az osszefoglalo elmaradasa nem kritikus: a teljes atirat a logban
    // marad, abbol kezzel is kiolvashato minden.
    console.error('[llm] osszefoglalo sikertelen:', err);
    return null;
  }
}
