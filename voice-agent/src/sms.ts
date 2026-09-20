/**
 * Hivas utani SMS kuldese a hivo szamara.
 *
 * Fail-soft, ugyanaz az elv, mint az email.ts-ben: ha az SMS nem megy ki,
 * naplozzuk, de nem dobunk hibat. Egy sikertelen SMS nem indokolja, hogy a
 * hivas lezarasa elszalljon.
 */

import twilio from 'twilio';
import { env } from './env.js';
import { normalizeNumber, type Lang } from './routing.js';

const CONTACT_MESSAGE: Record<Lang, string> = {
  hu: 'AXIMBRA - koszonjuk a hivast! Irjon nekunk: aximbra@gmail.com',
  en: 'AXIMBRA - thank you for calling! Write to us: aximbra@gmail.com',
};

/** Egyszeru E.164 ellenorzes: + jel es 8-15 szamjegy. */
function looksLikeE164(value: string): boolean {
  return /^\+[1-9]\d{7,14}$/.test(value);
}

/**
 * A beepitett hivastesztelo sajat szama, ha van ilyen beallitva.
 *
 * Az onnan "erkezo" hivas egy robot, nem erdeklodo: nincs kinek megkoszonni
 * a hivast, es a szam kulfoldi, ezert a Twilio a regio-engedelyek miatt
 * vissza is utasitja (Error 21408). Emiatt minden teszthivas egy hibastack-et
 * hagyott a naplokban - eppen ott, ahol a valodi hibakat keressuk.
 *
 * A process.env-bol olvassuk, nem az env() gyorsitotarbol: ez a dontes
 * onmagaban ertheto kell legyen, es igy tesztelheto is.
 */
export function isTestHarnessNumber(to: string): boolean {
  const own = normalizeNumber(process.env['TEST_AGENT_FROM'] ?? '');
  return own !== '' && normalizeNumber(to) === own;
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

  if (isTestHarnessNumber(to)) {
    console.log('[sms] teszthivas: a koszono SMS kihagyva');
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
