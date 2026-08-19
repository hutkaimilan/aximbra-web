/**
 * Hivas-limitek.
 *
 * Ket fuggetlen korlat vedi a koltseget:
 *   1. napi hivasszam  -> hany hivast fogadunk el egy naptari napon
 *   2. hivashossz      -> mennyi ideig tarthat egy beszelgetes
 *
 * A ket korlat szandekosan fuggetlen: ha az egyik logika elromlik, a masik
 * meg mindig hataroljq a kitettseget.
 *
 * TAROLAS: memoriaban. Ez tudatos dontes, nem hanyagsag.
 *   - Elony: nulla kulso fugges, nulla latencia, nulla extra szolgaltatas.
 *   - Ar: a szamlalo nullazodik, ha a konteneri ujraindul, es tobb peldany
 *     eseten peldanyonkent kulon szamol.
 *   - Miert elfogadhato: egyetlen peldany fut, a Railway ritkan indit ujra,
 *     es a rosszabbik eset (nehany extra hivas egy deploy utan) nehany
 *     centbe kerul. Ha ez valaha szamit, a resetDay/increment fuggvenyeket
 *     kell Redisre cserelni - a hivo kod valtozatlan maradhat.
 */

import { env } from './env.js';

/** Budapest-lokalis datum kulcs (YYYY-MM-DD). */
function todayKey(): string {
  // A hivasok magyar idozonaban erkeznek; a nap ott forduljon, ne UTC-ben,
  // kulonben a keret ejjel 2-kor nullazodna helyi ido szerint.
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Budapest',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
}

const state = {
  day: todayKey(),
  count: 0,
};

/** Egyidejuleg elo hivasok szama. Vedelem a parhuzamos terheles ellen. */
let liveCalls = 0;
const MAX_CONCURRENT_CALLS = 3;

export type Verdict =
  | { allowed: true; count: number; limit: number }
  | { allowed: false; reason: 'daily' | 'concurrent'; count: number; limit: number };

/**
 * Eldonti, fogadjuk-e a hivast, es ha igen, elkonyveli.
 *
 * Fontos: a szamlalot ITT noveljuk, nem a WebSocket megnyitasakor. Aki
 * felveszi a telefont es azonnal leteszi, az is fogyaszt a keretbol -
 * kulonben egy ujrahivogato script korlatlanul tudna TwiML-t generaltatni.
 */
export function admitCall(): Verdict {
  const limit = env().maxCallsPerDay;

  // 0 = kikapcsolt napi korlat (a fejlesztoi teszteles kedveert).
  if (limit === 0) {
    return { allowed: true, count: state.count, limit: 0 };
  }

  const today = todayKey();
  if (state.day !== today) {
    state.day = today;
    state.count = 0;
  }

  if (liveCalls >= MAX_CONCURRENT_CALLS) {
    return {
      allowed: false,
      reason: 'concurrent',
      count: state.count,
      limit,
    };
  }

  if (state.count >= limit) {
    return { allowed: false, reason: 'daily', count: state.count, limit };
  }

  state.count += 1;
  return { allowed: true, count: state.count, limit };
}

export function callStarted(): void {
  liveCalls += 1;
}

export function callEnded(): void {
  liveCalls = Math.max(0, liveCalls - 1);
}

export function maxCallSeconds(): number {
  return env().maxCallSeconds;
}

export function stats(): { day: string; count: number; live: number } {
  return { day: state.day, count: state.count, live: liveCalls };
}
