/**
 * Hivas utani SMS kuldese a hivo szamara.
 *
 * Fail-soft, ugyanaz az elv, mint az email.ts-ben: ha az SMS nem megy ki,
 * naplozzuk, de nem dobunk hibat. Egy sikertelen SMS nem indokolja, hogy a
 * hivas lezarasa elszalljon.
 */

import twilio from 'twilio';
import { env } from './env.js';
import type { Lang } from './routing.js';

const CONTACT_MESSAGE: Record<Lang, string> = {
  hu: 'AXIMBRA - koszonjuk a hivast! Irjon nekunk: aximbra@gmail.com',
  en: 'AXIMBRA - thank you for calling! Write to us: aximbra@gmail.com',
};

/** Egyszeru E.164 ellenorzes: + jel es 8-15 szamjegy. */
function looksLikeE164(value: string): boolean {
  return /^\+[1-9]\d{7,14}$/.test(value);
}

let client: ReturnType<typeof twilio> | null = null;

function twilioClient(): ReturnType<typeof twilio> {
  if (!client) {
    const cfg = env();
    client = twilio(cfg.twilioAccountSid, cfg.twilioAuthToken);
  }
  return client;
}

export async function sendContactSms(to: string, lang: Lang = 'hu'): Promise<void> {
  const cfg = env();

  if (!cfg.smsEnabled) return;

  if (!looksLikeE164(to)) {
    console.warn(`[sms] ervenytelen cimzett, kihagyva: ${to}`);
    return;
  }

  try {
    const message = await twilioClient().messages.create({
      to,
      from: cfg.twilioSmsFrom,
      body: CONTACT_MESSAGE[lang],
    });
    console.log(`[sms] elkuldve to=${to} sid=${message.sid}`);
  } catch (err) {
    console.error('[sms] kivetel:', err);
  }
}
