/**
 * "Hivjon vissza" - a latogato megadja a sajat szamat, es az agent hivja fel.
 *
 * Miert kell: a hirdetett szam amerikai (+1). Egy magyar cegvezeto nem
 * tarcsaz amerikai szamot egy elso talalkozasnal. Bejovo hivast viszont
 * felvesz - kulonosen azt, amit egy perce o maga kert. Uj telefonszam nelkul
 * ez teszi elerhetove az agentet a hazai kozonsegnek.
 *
 * VISSZAELES. Egy nyilvanos gomb, ami tetszoleges szamot felhiv, ket modon
 * tamadhato: valaki masok szamat csorgeti vele, vagy elegeti a Twilio
 * egyenleget. Negy fuggetlen korlat all ellene:
 *
 *   1. szamonkent napi egy hivas   -> zaklatasra alkalmatlan
 *   2. napi osszes hivasszam       -> a koltseg felulrol zart
 *   3. orszag-elotag szurés        -> nincs dragan hivhato, egzotikus irany
 *   4. a meglevo `admitCall` keret -> a hivas ugyanabbol a napi keretbol megy,
 *                                     mint a bejovo hivasok
 *
 * TAROLAS: memoriaban, ugyanazzal az indoklassal, mint a limit.ts - egyetlen
 * peldany fut, es az ujrainduls utani nehany extra hivas nehany centbe kerul.
 * Ha ez valaha szamit, ez a modul cserelheto Redisre a hivo kod erintese
 * nelkul.
 */

/** Budapest-lokalis datum kulcs (YYYY-MM-DD). A nap itt forduljon, ne UTC-ben. */
function todayKey(): string {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Budapest',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).format(new Date());
}

/**
 * Ahova hivhatunk. Nem "minden orszag mineusz a rosszak": engedelyezo lista,
 * mert egy elfelejtett premium irany tobbe kerul, mint az osszes elmaradt
 * hivas egyutt. A lap nyolc nyelve es a kornyezo orszagok vannak benne.
 *
 * A +1 (USA/Kanada) bent van, mert az oldal angol kozonsege onnan jon. Ezen
 * belul van nehany dragabb karibi korzet; a szamonkenti es a napi korlat
 * miatt a legrosszabb eset igy is nehany dollar.
 */
export const ALLOWED_PREFIXES = [
  '+36',  // Magyarorszag
  '+43',  // Ausztria
  '+421', // Szlovakia
  '+420', // Csehorszag
  '+40',  // Romania
  '+385', // Horvatorszag
  '+386', // Szlovenia
  '+49',  // Nemetorszag
  '+41',  // Svajc
  '+33',  // Franciaorszag
  '+32',  // Belgium
  '+31',  // Hollandia
  '+39',  // Olaszorszag
  '+34',  // Spanyolorszag
  '+351', // Portugalia
  '+48',  // Lengyelorszag
  '+44',  // Egyesult Kiralysag
  '+353', // Irorszag
  '+45',  // Dania
  '+46',  // Svedorszag
  '+47',  // Norvegia
  '+358', // Finnorszag
  '+1',   // USA / Kanada
] as const;

const E164 = /^\+[1-9]\d{6,14}$/;

/** Magyar mobil-korzetek, a `06` es a `+36` nelkuli alakhoz. */
const HU_MOBILE = /^(20|30|31|50|70)\d{7}$/;

/**
 * A latogato altal beirt szambol E.164 alak, vagy `null`.
 *
 * Azert engedekeny, mert a magyar felhasznalo tobbfelekeppen irja le a sajat
 * szamat, es egy "ervenytelen szam" uzenet miatt nem fog masodszor
 * probalkozni:
 *
 *   +36 30 123 4567 -> +36301234567
 *   0036301234567   -> +36301234567
 *   06 30 123 4567  -> +36301234567
 *   30 123 4567     -> +36301234567   (magyar mobil-korzet, orszaghivo nelkul)
 */
export function toE164(raw: string | null | undefined): string | null {
  let s = (raw ?? '').replace(/[\s().\-/]/g, '');
  if (s === '') return null;

  if (s.startsWith('00')) s = `+${s.slice(2)}`;
  // A 06 magyar belfoldi elotag - csak akkor, ha nem mar nemzetkozi alak.
  else if (s.startsWith('06')) s = `+36${s.slice(2)}`;
  else if (!s.startsWith('+') && HU_MOBILE.test(s)) s = `+36${s}`;
  else if (!s.startsWith('+') && s.startsWith('36')) s = `+${s}`;

  return E164.test(s) ? s : null;
}

export function isAllowedDestination(e164: string): boolean {
  return ALLOWED_PREFIXES.some((p) => e164.startsWith(p));
}

export type CallbackVerdict =
  | { ok: true; to: string }
  | { ok: false; reason: 'number' | 'country' | 'repeat' | 'daily' };

interface State {
  day: string;
  total: number;
  /** Szamonkent hany hivas ment ma. Naponta urul. */
  perNumber: Map<string, number>;
}

const state: State = { day: todayKey(), total: 0, perNumber: new Map() };

function rollDay(): void {
  const today = todayKey();
  if (state.day !== today) {
    state.day = today;
    state.total = 0;
    state.perNumber.clear();
  }
}

/**
 * Eldonti, indithatunk-e visszahivast, es ha igen, elkonyveli.
 *
 * A konyveles ITT tortenik, nem a hivas sikere utan: aki nem veszi fel, az is
 * fogyaszt a keretbol. Kulonben egy nem letezo szam korlatlanul ujrahivhato
 * lenne, es minden probalkozas penzbe kerul.
 *
 * @param raw     a latogato altal beirt szam
 * @param maxPerDay  napi osszes visszahivas (0 = a funkcio ki van kapcsolva)
 */
export function admitCallback(raw: string | null | undefined, maxPerDay: number): CallbackVerdict {
  const to = toE164(raw);
  if (!to) return { ok: false, reason: 'number' };
  if (!isAllowedDestination(to)) return { ok: false, reason: 'country' };

  rollDay();

  if (maxPerDay <= 0 || state.total >= maxPerDay) return { ok: false, reason: 'daily' };
  if ((state.perNumber.get(to) ?? 0) >= 1) return { ok: false, reason: 'repeat' };

  state.total += 1;
  state.perNumber.set(to, (state.perNumber.get(to) ?? 0) + 1);
  return { ok: true, to };
}

/**
 * Visszaad egy elkonyvelt keretet. Akkor hivjuk, ha a hivas indítása maga
 * nem sikerult (halozati hiba, Twilio elutasitas): ilyenkor nem tortent
 * hivas, tehat nem is fogyott a keret, es a latogato ujra probalkozhat.
 */
export function refundCallback(to: string): void {
  rollDay();
  state.total = Math.max(0, state.total - 1);
  const n = (state.perNumber.get(to) ?? 0) - 1;
  if (n <= 0) state.perNumber.delete(to);
  else state.perNumber.set(to, n);
}

export function callbackStats(): { day: string; total: number; numbers: number } {
  rollDay();
  return { day: state.day, total: state.total, numbers: state.perNumber.size };
}

/** Csak teszthez: nullazza a napi szamlalokat. */
export function resetCallbackState(): void {
  state.day = todayKey();
  state.total = 0;
  state.perNumber.clear();
}
