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
/* Nyelvvalaszto menu                                                   */
/* ------------------------------------------------------------------ */

/**
 * A hivas elejen a hivo maga valasztja ki a nyelvet, gombnyomassal.
 *
 * Ez az egyetlen teljesen megbizhato jel. A hivoszam nem az (magyar ugyfel
 * hivhat nemet szamrol), es a beszedbol valo felismeres sem az, mert a
 * felismeronek mar a hivo elso szava elott el kell dontenie, milyen nyelvre
 * alljon - es ha rosszul dont, a hivo mondata visszafejthetetlenne valik
 * ("Hello. Hi. Amit Mondock."). Egy gombnyomas ezt a kort atvagja: a
 * DTMF-jel nyelvfuggetlen.
 *
 * Elobb magyarul hangzik el mindket lehetoseg, aztan ugyanaz angolul - a
 * hazai kozonseg igy azonnal ert mindent, a kulfoldi pedig kivarja a masodik
 * felet. Barmikor lehet gombot nyomni, a Gather nem varja meg a szoveg vegét.
 */
export const MENU_HU =
  'Jó napot kívánok, Aximbra! Ha magyarul szeretné folytatni, nyomja meg az egyes gombot. ' +
  'Ha angolul szeretné folytatni, nyomja meg a kettes gombot.';

export const MENU_EN =
  'Hello, this is Aximbra. To continue in Hungarian, press one. ' +
  'To continue in English, press two.';

export interface LanguageMenu {
  host: string;
  huVoice: string;
  enVoice: string;
  /** Hany masodpercig varunk gombnyomasra, mielott magyarul folytatjuk. */
  timeoutSeconds: number;
}

export function languageMenuTwiml(m: LanguageMenu): string {
  return `<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Gather numDigits="1" timeout="${m.timeoutSeconds}" action="https://${escapeXml(m.host)}/twiml/lang" method="POST">
    <Say voice="${escapeXml(m.huVoice)}" language="hu-HU">${escapeXml(MENU_HU)}</Say>
    <Say voice="${escapeXml(m.enVoice)}" language="en-US">${escapeXml(MENU_EN)}</Say>
  </Gather>
  <Redirect method="POST">https://${escapeXml(m.host)}/twiml/lang</Redirect>
</Response>`;
}

/**
 * A megnyomott gomb nyelve, es hogy a hivo valasztott-e egyaltalan.
 *
 * Gombnyomas nelkul magyarul folytatjuk - az oldal kozonsege magyar -, de
 * `chosen: false`-szal, mert ez nem a hivo dontese volt. Ilyenkor a
 * beszedbol valo felismeres meg korrigalhat; egy megnyomott gombot viszont
 * semmi nem irhat felul.
 */
export function langFromDigits(digits: string | null | undefined): {
  lang: Lang;
  chosen: boolean;
} {
  const d = (digits ?? '').trim();
  if (d === '1') return { lang: 'hu', chosen: true };
  if (d === '2') return { lang: 'en', chosen: true };
  return { lang: 'hu', chosen: false };
}

/* ------------------------------------------------------------------ */
/* Nyelvvaltas hivas kozben                                             */
/* ------------------------------------------------------------------ */

/** A ConversationRelay nyelvkodjai. A TwiML `<Language code=...>`-ai ezek. */
export const RELAY_LANG_CODE: Record<Lang, string> = { hu: 'hu-HU', en: 'en-US' };

/**
 * A ConversationRelay-nek kuldheto uzenet, ami a mar folo hivason atallitja
 * a nyelvet.
 *
 * MINDKETTOT egyszerre allitja: amit felolvasunk (`ttsLanguage`) es amit
 * felismerunk (`transcriptionLanguage`). Ez szandekos - a ketto szetcsuszasa
 * volt maga a hiba, amit ez az egesz megold: a hivo nyelven kell hallgatni
 * es a hivo nyelven kell valaszolni, nem a hivoszama szerint.
 */
export function languageSwitchMessage(next: Lang): string {
  return JSON.stringify({
    type: 'language',
    ttsLanguage: RELAY_LANG_CODE[next],
    transcriptionLanguage: RELAY_LANG_CODE[next],
  });
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
