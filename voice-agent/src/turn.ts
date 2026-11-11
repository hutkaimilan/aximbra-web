/**
 * Mikor fejezte be a hivo a mondatat?
 *
 * A ConversationRelay a csendbol dont: ha a hivo `speechTimeout` ideig hallgat,
 * a felismert szoveget vegleges mondatkent kuldi. Aki gondolkodik beszed
 * kozben ("Megjon a termek. Teszem azt,"), az ennel tovabb is hallgathat - es
 * ilyenkor az agent egy felmondatra valaszolt, belevagott a hivoba. Egy eles
 * hivasban a hivo ezt mondta: "Ne, ne, ne, pofazol bele."
 *
 * Ez a modul csak a szovegbol becsul. Ha a mondat befejezetlennek tunik, a
 * hivas egy rovid ideig var a folytatasra, mielott valaszolna.
 */

/** Ennyit varunk egy befejezetlennek tuno mondat folytatasara (ms). */
export const HOLD_MS = 1800;

/** Rovid, de onmagukban teljes valaszok - ezekre nem varunk. */
const COMPLETE_SHORT = new Set([
  'igen', 'nem', 'jó', 'jo', 'rendben', 'értem', 'ertem', 'persze', 'köszönöm',
  'koszonom', 'oké', 'oke', 'ok', 'okés', 'hello', 'halló', 'hallo', 'szia',
  'viszontlátásra', 'viszonthallásra', 'ennyi', 'nincs', 'van', 'pontosan',
  'yes', 'no', 'okay', 'sure', 'thanks', 'bye', 'right', 'exactly',
]);

/**
 * Szavak, amik utan a mondat nem erhet veget: kotoszavak, nevelok,
 * toltelekszavak. Ha a felismert szoveg ezek egyikevel zarul, a hivo
 * folytatni fogja.
 */
const DANGLING = new Set([
  'a', 'az', 'egy', 'és', 'es', 'meg', 'hogy', 'de', 'mert', 'tehát', 'tehat',
  'ugye', 'ami', 'amit', 'amire', 'amely', 'akkor', 'szóval', 'szoval', 'hát',
  'hat', 'például', 'peldaul', 'mint', 'vagy', 'illetve', 'is', 'pedig', 'ha',
  'amikor', 'ahol', 'aki', 'ööö', 'öö', 'ő', 'hmm', 'izé', 'ize', 'teszem',
  'mondjuk', 'valamint', 'továbbá', 'tovabba', 'csak', 'így', 'igy',
  'the', 'and', 'so', 'because', 'but', 'or', 'that', 'which', 'like', 'um', 'uh',
  'with', 'to', 'of', 'for', 'if', 'when',
]);

/** A mondat vegerol levagjuk a zaro irasjelet, es kisbetusitunk. */
function words(text: string): string[] {
  return text
    .toLowerCase()
    .replace(/[.!?…"„”'’]+$/u, '')
    .split(/\s+/u)
    .map((w) => w.replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, ''))
    .filter(Boolean);
}

/**
 * Igaz, ha a szoveg valoszinuleg egy felbehagyott mondat, amit a hivo
 * folytatni fog. Kerdesre (?) es egyertelmu lezarasra soha nem igaz.
 */
export function looksUnfinished(raw: string): boolean {
  const text = raw.trim();
  if (!text) return false;
  if (/[?]$/u.test(text)) return false;

  // Vesszo, gondolatjel, kettospont, harom pont a vegen: a mondat folytatodik.
  if (/[,;:\-–—]$/u.test(text) || /(\.\.\.|…)$/u.test(text)) return true;

  const w = words(text);
  if (w.length === 0) return false;

  const last = w[w.length - 1]!;
  if (w.length === 1) {
    if (COMPLETE_SHORT.has(last)) return false;
    // Egyetlen betu vagy toltelek ("A", "Ööö"): biztosan nem a teljes mondat.
    if (last.length <= 2 || DANGLING.has(last)) return true;
    return false;
  }

  if (DANGLING.has(last)) return true;
  // "teszem azt" - a folytatas jon.
  if (w.length >= 2 && w[w.length - 2] === 'teszem' && last === 'azt') return true;
  return false;
}

/**
 * Utolso vedvonal a tegezes ellen.
 *
 * A promptszabaly a fo vedelem; ez csak az egyertelmu, szo szerint csereltheto
 * tegezo nevmasokat javitja a kimenetben ("nalatok" -> "Önöknél"). Igealakot
 * ("szeretnel") nem probal javitani: ott a csere nyelvtanilag rossz mondatot
 * adna. A tulajdonos kifejezetten megtiltotta, hogy az agent barkit tegezzen.
 */
const FORMAL: Record<string, string> = {
  nálatok: 'Önöknél',
  nektek: 'Önöknek',
  titeket: 'Önöket',
  benneteket: 'Önöket',
  veletek: 'Önökkel',
  tőletek: 'Önöktől',
  hozzátok: 'Önökhöz',
  rólatok: 'Önökről',
  nálad: 'Önnél',
  neked: 'Önnek',
  téged: 'Önt',
  veled: 'Önnel',
  tőled: 'Öntől',
  hozzád: 'Önhöz',
  rólad: 'Önről',
  // Gyakori tegezo igealakok -> magazo (E/3, T/3) megfelelojuk. Mindegyik
  // egyertelmu masodik szemelyu alak, a csere utan a mondat nyelvtanilag
  // helyes marad. (A tesztekben a modell pl. "Nálatok nagyjából mennyi
  // e-mail érkezik?"-et irt; a szimulator tobb ilyet is talalt.)
  szeretnél: 'szeretne',
  szeretnéd: 'szeretné',
  szeretnétek: 'szeretnék',
  tudod: 'tudja',
  tudnád: 'tudná',
  tudnál: 'tudna',
  tudnátok: 'tudnák',
  tudjátok: 'tudják',
  mondd: 'mondja',
  mondjátok: 'mondják',
  kérlek: 'kérem',
  nézd: 'nézze',
  gondolod: 'gondolja',
  akarod: 'akarja',
  akarsz: 'akar',
  akartok: 'akarnak',
  vagytok: 'vannak',
  csinálod: 'csinálja',
  csináljátok: 'csinálják',
  csináltok: 'csinálnak',
  használtok: 'használnak',
  használjátok: 'használják',
  dolgoztok: 'dolgoznak',
  foglalkoztok: 'foglalkoznak',
  küldd: 'küldje',
  küldjétek: 'küldjék',
  írj: 'írjon',
  szólj: 'szóljon',
  várj: 'várjon',
  mesélj: 'meséljen',
  ajánlanál: 'ajánlana',
  lennél: 'lenne',
  kérdezel: 'kérdez',
  hívtál: 'hívott',
  hívsz: 'hív',
  maradj: 'maradjon',
  hallod: 'hallja',
  figyelj: 'figyeljen',
};

const FORMAL_RE = new RegExp(`(?<![\\p{L}])(${Object.keys(FORMAL).join('|')})(?![\\p{L}])`, 'giu');

/** Egy kesz szovegreszben lecsereli a tegezo nevmasokat. */
export function formalize(text: string): string {
  return text.replace(FORMAL_RE, (m) => {
    const rep = FORMAL[m.toLowerCase()] ?? m;
    // Mondat eleji nagybetu megmarad ("Mondd," -> "Mondja,").
    const upper = m[0] !== undefined && m[0] !== m[0].toLowerCase();
    return upper ? rep.charAt(0).toUpperCase() + rep.slice(1) : rep;
  });
}

/**
 * Streamelt kimenethez: a szo vegeig visszatartja a szoveget, hogy egy
 * ket darabban erkezo szo ("nála" + "tok") is cserelodjon.
 */
export class FormalFilter {
  private buf = '';
  push(delta: string): string {
    this.buf += delta;
    const cut = Math.max(this.buf.lastIndexOf(' '), this.buf.lastIndexOf('\n'));
    if (cut < 0) return '';
    const out = this.buf.slice(0, cut + 1);
    this.buf = this.buf.slice(cut + 1);
    return formalize(out);
  }
  flush(): string {
    const out = formalize(this.buf);
    this.buf = '';
    return out;
  }
}

/** "Van meg kerdese?" es rokonai - egy hivasban egyszer hangozhat el. */
export const MORE_QUESTIONS_RE =
  /\b(van|lenne) (még|esetleg)( még)? (más |egyéb )?(kérdése|kérdés)\b|\bany (other|more) questions\b|\banything else (i can|to) help\b/iu;

/**
 * Mondatonkent szuri a streamelt kimenetet: az `drop` mintara illeszkedo
 * mondat nem megy ki. Csak akkor kapcsoljuk be, ha a mondat mar elhangzott a
 * hivasban - a promptszabaly ("egyszer kerdezd") egy teszthivasban harom
 * egymast koveto valasznal sem tartott.
 *
 * Amig a szuro aktiv, a szoveg mondatonkent megy ki, nem tokenenkent: ez a
 * felolvasas inditasat egy mondatnyit kesleltetheti.
 */
export class SentenceDropFilter {
  private buf = '';
  constructor(private readonly drop: RegExp | null) {}
  push(delta: string): string {
    if (!this.drop) return delta;
    this.buf += delta;
    let out = '';
    for (;;) {
      const m = /[.!?…](\s+)/u.exec(this.buf);
      if (!m) break;
      const end = m.index + m[0].length;
      const sentence = this.buf.slice(0, end);
      this.buf = this.buf.slice(end);
      if (!this.drop.test(sentence)) out += sentence;
    }
    return out;
  }
  flush(): string {
    if (!this.drop) return '';
    const rest = this.buf;
    this.buf = '';
    return this.drop.test(rest) ? '' : rest;
  }
}

/** Ugyanez kesz szovegre (a tortenetbe ez kerul). */
export function dropSentences(text: string, drop: RegExp | null): string {
  if (!drop) return text;
  const f = new SentenceDropFilter(drop);
  return (f.push(text) + f.flush()).trim();
}
