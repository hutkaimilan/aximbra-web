/**
 * Kornyezeti valtozok betoltese es validalasa.
 *
 * Elv: a hianyzo kotelezo valtozo azonnali, hangos indulasi hiba legyen, ne
 * egy rejtelmes 500-as valasz az elso valodi hivasnal. Egy telefonvonalnal a
 * nema meghibasodas a legrosszabb kimenetel: a hivo azt latja, hogy a ceg nem
 * veszi fel a telefont.
 */

function required(name: string): string {
  const value = process.env[name];
  if (!value || value.trim() === '') {
    throw new Error(
      `Hianyzo kotelezo kornyezeti valtozo: ${name}. ` +
        `Allitsd be a Railway service Variables lapjan.`,
    );
  }
  return value.trim();
}

function optional(name: string, fallback: string): string {
  const value = process.env[name];
  return value && value.trim() !== '' ? value.trim() : fallback;
}

function intOption(name: string, fallback: number, min: number, max: number): number {
  const raw = process.env[name];
  if (!raw || raw.trim() === '') return fallback;
  const parsed = Number.parseInt(raw.trim(), 10);
  if (!Number.isFinite(parsed) || parsed < min || parsed > max) {
    console.warn(
      `[env] ${name}="${raw}" ervenytelen (megengedett: ${min}-${max}), ` +
        `helyette az alapertelmezes: ${fallback}`,
    );
    return fallback;
  }
  return parsed;
}

export interface Env {
  port: number;
  openaiApiKey: string;
  model: string;
  twilioAuthToken: string;
  publicHostname: string;
  validateSignature: boolean;
  /** Hivas utani SMS kuldeshez kell (Twilio REST API azonositas). */
  twilioAccountSid: string;
  /** Errol a szamrol megy ki a hivas utani SMS a hivonak. */
  twilioSmsFrom: string;
  /** Igaz, ha van eleg adat SMS kuldesehez. */
  smsEnabled: boolean;
  maxCallsPerDay: number;
  maxCallSeconds: number;
  notifyEmail: string;
  resendApiKey: string;
  resendFrom: string;
  /** <ConversationRelay> TTS szolgaltato: Google | Amazon | ElevenLabs */
  ttsProvider: string;
  /** <ConversationRelay> hang-ID, prefix NELKUL (pl. hu-HU-Wavenet-A) */
  ttsVoice: string;
  /** <Say> hangnev, prefixSZEL (pl. Google.hu-HU-Wavenet-A) */
  sayVoice: string;
  ttsLanguage: string;
  /** Hany projekt van jelenleg folyamatban. Ez szabja meg a hataridosavot. */
  currentProjects: number;
}

let cached: Env | null = null;

export function env(): Env {
  if (cached) return cached;

  const twilioAuthToken = optional('TWILIO_AUTH_TOKEN', '');
  const publicHostname = optional('PUBLIC_HOSTNAME', '');
  const notifyEmail = optional('NOTIFY_EMAIL', '');
  const resendApiKey = optional('RESEND_API_KEY', '');
  const twilioAccountSid = optional('TWILIO_ACCOUNT_SID', '');
  const twilioSmsFrom = optional('TWILIO_SMS_FROM', '+18024249852');

  const built: Env = {
    port: intOption('PORT', 8080, 1, 65535),
    openaiApiKey: required('OPENAI_API_KEY'),
    model: optional('VOICE_MODEL', 'gpt-4.1-mini'),

    // A signature-ellenorzeshez az auth token kell (nem az API secret).
    twilioAuthToken,

    // A Twilio a sajat POST-jat ezzel a hosttal irja ala. Railway mogott a
    // kereses proxyzva erkezik, ezert a Host fejlec nem megbizhato.
    publicHostname,

    // Alairas-ellenorzes csak akkor lehetseges, ha mindketto megvan.
    validateSignature: twilioAuthToken !== '' && publicHostname !== '',

    twilioAccountSid,
    twilioSmsFrom,
    // SMS-hez az Account SID es az Auth Token egyutt kell.
    smsEnabled: twilioAccountSid !== '' && twilioAuthToken !== '',

    maxCallsPerDay: intOption('MAX_CALLS_PER_DAY', 15, 0, 100000),
    maxCallSeconds: intOption('MAX_CALL_SECONDS', 240, 30, 3600),

    notifyEmail,
    resendApiKey,
    resendFrom: optional('RESEND_FROM', 'onboarding@resend.dev'),

    // FONTOS: a <Say> es a <ConversationRelay> MASKEPP nevezi a hangokat.
    //   <Say>              -> voice="Google.hu-HU-Wavenet-A"   (prefixszel)
    //   <ConversationRelay>-> ttsProvider="Google" + voice="hu-HU-Wavenet-A"
    // A ket forma osszekeverese ervenytelen kombinacio, amire a Twilio
    // hibat kuld es BONTJA a hivast. Ezert kulon valtozo mindkettonek.
    ttsProvider: optional('TTS_PROVIDER', 'Google'),
    ttsVoice: optional('TTS_VOICE', 'hu-HU-Wavenet-A'),
    sayVoice: optional('SAY_VOICE', 'Google.hu-HU-Wavenet-A'),
    ttsLanguage: optional('TTS_LANGUAGE', 'hu-HU'),

    // Kezzel allitod a Railway Variables lapjan, amikor uj munkat vallalsz.
    // Adatbazis helyett ez a legolcsobb megoldas egyetlen szamra, ami
    // havonta ha ketszer valtozik.
    currentProjects: intOption('CURRENT_PROJECTS', 0, 0, 50),
  };

  cached = built;

  if (!built.validateSignature) {
    console.warn(
      '[env] A Twilio signature-ellenorzes KI van kapcsolva ' +
        '(TWILIO_AUTH_TOKEN vagy PUBLIC_HOSTNAME hianyzik). ' +
        'Eles uzemben allitsd be mindkettot.',
    );
  }

  if (built.notifyEmail === '' || built.resendApiKey === '') {
    console.warn(
      '[env] Hivas-osszefoglalo email KI van kapcsolva ' +
        '(NOTIFY_EMAIL vagy RESEND_API_KEY hianyzik). ' +
        'Az osszefoglalo ilyenkor csak a logba kerul.',
    );
  }

  if (!built.smsEnabled) {
    console.warn(
      '[env] Hivas utani SMS KI van kapcsolva ' +
        '(TWILIO_ACCOUNT_SID hianyzik). A hivo nem kap SMS-t hivas utan.',
    );
  }

  return built;
}
