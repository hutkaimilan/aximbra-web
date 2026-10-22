/**
 * A hivas bontasa elkoszones utan.
 *
 * Eddig a vonalat csak a hivo tudta letenni: az agent elkoszont, aztan
 * csendben tartotta a hivast, amig a masik oldal ra nem unt. Most a modell
 * a bucsumondata VEGERE egy jelet tesz (END_CALL_MARKER), mi azt kiszurjuk
 * a kimondott szovegbol, es miutan a bucsu elhangzott, bontjuk a hivast.
 *
 * A jel tokenenkent erkezik, tehat kettevagva is johet ("[[BO" + "NT]]").
 * A szuro ezert visszatartja a szoveg vegen azt a reszt, ami a jel eleje
 * lehet, es csak akkor engedi tovabb, ha kiderult, hogy megsem az.
 */

export const END_CALL_MARKER = '[[BONT]]';

export class MarkerFilter {
  private pending = '';
  found = false;

  /** A kimondhato szoveg ebbol a darabbol. A jel es ami utana jon, eltunik. */
  push(delta: string): string {
    if (this.found) return '';
    this.pending += delta;
    const at = this.pending.indexOf(END_CALL_MARKER);
    if (at >= 0) {
      this.found = true;
      const out = this.pending.slice(0, at);
      this.pending = '';
      return out;
    }
    const keep = partialSuffix(this.pending, END_CALL_MARKER);
    const out = this.pending.slice(0, this.pending.length - keep);
    this.pending = this.pending.slice(this.pending.length - keep);
    return out;
  }

  /** A stream vegen: ami visszatartva maradt, megsem jel volt. */
  flush(): string {
    if (this.found) return '';
    const out = this.pending;
    this.pending = '';
    return out;
  }
}

/** Milyen hosszu a `text` vege, ami a `marker` eleje lehet. */
function partialSuffix(text: string, marker: string): number {
  for (let n = Math.min(text.length, marker.length - 1); n > 0; n--) {
    if (marker.startsWith(text.slice(-n))) return n;
  }
  return 0;
}

/** A teljes valaszbol a jel nelkuli szoveg, a tortenetbe es a naplokba. */
export function stripMarker(text: string): string {
  return text.split(END_CALL_MARKER).join('').trim();
}

/**
 * Mennyit varjunk a bontassal, hogy a bucsu vegig elhangozzon.
 *
 * A Twilio a szoveget menet kozben olvassa fel, de a felolvasas lassabb a
 * modell kimeneténel: kb. 13 karakter masodpercenkent. Inkabb egy kicsit
 * tovabb varunk, mint hogy a "viszonthallasra" fele lemaradjon.
 */
export function hangupDelayMs(spoken: string): number {
  return Math.min(12_000, Math.max(2_500, 1_200 + spoken.length * 80));
}
