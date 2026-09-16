/**
 * Kit csengessen a hivas: a tulajdonost vagy az agentet.
 *
 * A dontes a hivo szaman mulik. A nyelvet a hivas elejen meg nem ismerjuk,
 * a szamot viszont a Twilio mar a webhookban elkuldi, es egy +36-os szam eleg
 * jo jel arra, hogy a hivo magyarul beszel.
 *
 *   +36 szam             -> a tulajdonos mobilja; ha nem fogadja, az agent, magyarul
 *   mas orszag szama     -> agent, angol koszonessel
 *   rejtett / hibas szam -> agent, magyarul: nem tudjuk, ki hiv, az oldal
 *                           kozonsege magyar, es az agent atvalt, ha angolul szolnak
 *   a tulajdonos maga    -> agent, magyarul - kulonben a sajat telefonjarol
 *                           soha nem tudna kiprobalni
 *
 * A tulajdonos csak az 1-es gombbal fogadja a hivast (hivasszures). Enelkul a
 * kikapcsolt telefon hangpostaja "felvenne", es a hivo az agent helyett egy
 * hangpostan kotne ki.
 */

import { escapeXml } from './xml.js';

export type Lang = 'hu' | 'en';
export type Route = { to: 'owner' } | { to: 'agent'; lang: Lang };

const E164 = /^\+[1-9]\d{6,14}$/;
const CALL_SID = /^CA[0-9a-f]{32}$/;

export function normalizeNumber(raw: string | null | undefined): string {
  return (raw ?? '').replace(/[\s().-]/g, '');
}

export function isE164(value: string): boolean {
  return E164.test(value);
}

export function isCallSid(value: string): boolean {
  return CALL_SID.test(value);
}

/** `ownerPhone` ures: nincs atkapcsolas, minden hivas az agenthez megy. */
export function routeCall(from: string | null | undefined, ownerPhone: string): Route {
  const n = normalizeNumber(from);
  if (!isE164(n)) return { to: 'agent', lang: 'hu' };
  if (!n.startsWith('+36')) return { to: 'agent', lang: 'en' };
  if (ownerPhone === '' || n === ownerPhone) return { to: 'agent', lang: 'hu' };
  return { to: 'owner' };
}

/* ------------------------------------------------------------------ */
/* Ki fogadta a hivast                                                  */
/* ------------------------------------------------------------------ */

/**
 * A hivasok, amelyeket a tulajdonos az 1-es gombbal fogadott.
 *
 * Kulon nyilvantartas kell, mert a Twilio ezt nem mondja meg: ha a szuresnel
 * bontunk (nem nyomott gombot, vagy a hangposta vette fel), a <Dial> action
 * ugyanugy DialCallStatus=completed-et kap, mint egy vegigbeszelt hivasnal.
 *
 * Memoriaban, ugyanazzal az indoklassal, mint a limit.ts: egy peldany fut. Ha
 * a kontener egy hivas kozben ujraindul, a hivo a beszelgetes utan az agenthez
 * kerul - kellemetlen, de nem vesz el hivas.
 */
const accepted = new Map<string, number>();
const ACCEPTED_TTL_MS = 3 * 60 * 60 * 1000;

export function markAccepted(callSid: string, now = Date.now()): void {
  for (const [sid, at] of accepted) {
    if (now - at > ACCEPTED_TTL_MS) accepted.delete(sid);
  }
  accepted.set(callSid, now);
}

/** Igaz, ha fogadta - es egyben torli, mert egy hivasra egyszer kerdezunk. */
export function takeAccepted(callSid: string): boolean {
  return accepted.delete(callSid);
}

/* ------------------------------------------------------------------ */
/* TwiML                                                               */
/* ------------------------------------------------------------------ */

export interface OwnerDial {
  host: string;
  ownerPhone: string;
  ringSeconds: number;
  /** A bejovo (szulo) hivas azonositoja. Ellenorizve, mert URL-be kerul. */
  callSid: string;
  /** A Twilio-szam, amit a hivo tarcsazott (a webhook `To` mezoje). */
  calledNumber: string;
}

export function ownerDialTwiml(o: OwnerDial): string {
  // A tulajdonos telefonjan a Twilio-szam latszik, nem a hivoe. Egy
  // kulfoldrol erkezo, de magyar hivoszamot mutato hivast a szolgaltatok
  // hamisitottnak nezhetik es eldobhatjak. A szambol az is kiderul, hogy a
  // hivas az oldalrol jon.
  const called = normalizeNumber(o.calledNumber);
  const callerId = isE164(called) ? ` callerId="${escapeXml(called)}"` : '';

  return `<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Dial timeout="${o.ringSeconds}" answerOnBridge="true"${callerId} action="https://${escapeXml(o.host)}/twiml/owner-done" method="POST">
    <Number url="https://${escapeXml(o.host)}/twiml/screen?parent=${escapeXml(o.callSid)}" method="POST">${escapeXml(o.ownerPhone)}</Number>
  </Dial>
</Response>`;
}

/** Amit a tulajdonos hall, mielott a hivo bekapcsolodik. A hivo kozben kicsongest hall. */
export function screenTwiml(host: string, parent: string, sayVoice: string, language: string): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather numDigits="1" timeout="8" action="https://${escapeXml(host)}/twiml/screen-done?parent=${escapeXml(parent)}" method="POST">
    <Say voice="${escapeXml(sayVoice)}" language="${escapeXml(language)}" loop="2">AXIMBRA-hívás magyar számról. Ha fogadod, nyomd meg az egyest.</Say>
  </Gather>
  <Hangup/>
</Response>`;
}

/**
 * A szures eredmenye. Ures valasz = a szures veget ert, a Twilio osszekapcsol.
 * Barmi mas gomb vagy hibas azonosito: bontjuk ezt a labat, es az owner-done
 * az agenthez viszi a hivot.
 */
export function screenDoneTwiml(digits: string, parent: string): string {
  if (digits === '1' && isCallSid(parent)) {
    markAccepted(parent);
    return `<?xml version="1.0" encoding="UTF-8"?>
<Response/>`;
  }
  return `<?xml version="1.0" encoding="UTF-8"?>
<Response><Hangup/></Response>`;
}

export const HANGUP_TWIML = `<?xml version="1.0" encoding="UTF-8"?>
<Response><Hangup/></Response>`;
