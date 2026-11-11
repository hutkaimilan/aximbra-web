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
  private emitted = false;
  private dropped = '';
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
      if (this.drop.test(sentence)) {
        this.dropped += sentence;
      } else {
        out += sentence;
      }
    }
    if (out) this.emitted = true;
    return out;
  }
  flush(): string {
    if (!this.drop) return '';
    const rest = this.buf;
    this.buf = '';
    const keepRest = rest && !this.drop.test(rest) ? rest : '';
    if (keepRest) this.emitted = true;
    // Ha egyetlen mondat sem maradt, inkabb az eredeti hangzik el, mint a
    // csend (dropSentences ugyanigy dont, igy a tortenet is ezt rogziti).
    if (!this.emitted) return this.dropped + rest;
    return keepRest;
  }
}

/** Ugyanez kesz szovegre (a tortenetbe ez kerul). */
export function dropSentences(text: string, drop: RegExp | null): string {
  if (!drop) return text;
  const f = new SentenceDropFilter(drop);
  const out = (f.push(text) + f.flush()).trim();
  // Ha minden mondat kiesne, az eredeti marad: a nema valasz rosszabb.
  return out || text;
}

/**
 * Kerdezett-e a hivo az utolso mondataban.
 *
 * Ha igen, a "Van meg kerdese?" nem mehet ki: a hivo meg kerdez, a zaro
 * kerdes ilyenkor siettetes. A tulajdonos kerese: "Legyen levezetve vegig a
 * beszelgetes, es a legvegen kerdezze meg." A szimulatorban a modell mar a
 * hivo masodik kerdese utan feltette.
 */
export const CALLER_ASKED_RE =
  /\?|(?<![\p{L}])(?:mennyibe|mennyi|hogyan|milyen|mikor|hol|miért|melyik|mi történik|tudna|lehetne|van-e|kell-e|how|what|when|where|why|which)(?![\p{L}])/iu;

/**
 * Kerdezte-e mar a hivo az arat (barmikor a hivasban).
 *
 * Szandekosan tag: ha ez tevesen "nem"-et mondana, a lenti szuro egy jogos
 * arvalaszt nyelne le, es a hivo hiaba kerdezne ujra. Ezert minden
 * penzre, arra, koltsegre utalo szo "kerdeznek" szamit.
 */
export const PRICE_ASKED_RE =
  /mennyi|mibe kerül|kerül|(?<![\p{L}])ár(?:a|at|ak|áról|ban|ért|on|ai|ra|ok|akat)?(?![\p{L}])|árak|árajánlat|költ|díj|fizet|pénz|drága|olcsó|kedvezmény|keret|forint|ezer|millió|price|cost|how much|fee|budget|pay|cheap|expensive|discount/iu;

/** Arat vagy az ajanlat szazalekat kimondo mondat. */
export const PRICE_SAID_RE =
  /(?<![\p{L}])(?:forint\p{L}*|ft)(?![\p{L}])|\p{L}*(?:ezer|millió)(?![\p{L}])|százalék|forint|percent|thousand|million/iu;

/** A hivo csak nyugtazott ("Értem.", "Rendben, köszönöm.") - nem kerdezett, nem mesel. */
export const CALLER_ACK_RE =
  /^(?:[\s,.!]*(?:hát|na|oké|okés|ok|jó|jól van|értem|rendben|világos|köszönöm|köszönöm szépen|köszi|aha|értettem|szuper|nagyszerű|remek|tökéletes|értem köszönöm|okay|all right|alright|thanks|thank you|got it|i see|right|great|fine))+[\s,.!]*$/iu;

/** A hivo jelezte, hogy vegzett. */
export const CALLER_DONE_RE =
  /nincs (?:több|más)|ennyi (?:lenne|volt|elég)|minden világos|ez (?:minden|elég)|nincs kérdés|viszont(?:látásra|hallásra)|that'?s (?:all|everything)|no (?:more|other|further) questions|nothing else|goodbye|(?<![\p{L}])bye(?![\p{L}])/iu;

/** A hivo maga kert ajanlatot, visszahivast vagy embert. */
export const OFFER_REQUEST_RE =
  /ajánlat|küldj|küldjenek|küldjön|küldjék|küldené|elérhetőség|felír|a számom|hívjanak|hívjon|keressenek|keressen|visszahív|kolléga|quote|proposal|send me|call me|contact me|colleague/iu;

/** Zaro lepes: nev/ceg kerdese, ajanlat, SMS vagy e-mail felajanlasa. */
export const CLOSING_RE =
  /kihez címezzem|melyik cégnél|hogy hívják|mi a (?:neve|cég)|mi az ön neve|a nevét|küldjem|(?<![\p{L}])sms|ajánlatot (?:küld|össze|készít)|elküldöm az ajánlat|felírhatom|felírom|who should i address|which company|your name|text message|send (?:it|you|the quote)/iu;

/** Ujrakoszones egy kulon mondatban ("Üdvözlöm, Kiss úr."). */
export const REGREET_SENTENCE_RE =
  /^\s*(?:üdvözlöm|jó napot(?: kívánok)?|szép napot|hello|hi)(?:[\s,]+(?:\p{Lu}\p{L}*\s+)?(?:úr|asszony|hölgyem|uram|\p{Lu}\p{L}*))?\s*[.!]\s*$/iu;

/**
 * A kiszurendo mondatok egy mintaban. Mindegyik egy olyan hiba, amit a
 * promptszabaly a szimulatorban vagy eles hivasban nem fogott meg:
 *  - ujrakoszones ("Üdvözlöm, Kiss úr.") a hivas kozepen;
 *  - "Van meg kerdese?": csak egyszer, es csak ha a hivo nyugtazott vagy
 *    vegzett - nem a kerdesei kozben;
 *  - zaro lepes (nev, ajanlat, SMS): csak ha a hivo nyugtazott, vegzett,
 *    maga kert ajanlatot / visszahivast, vagy fogy az ido. A tulajdonos
 *    panasza szo szerint: "egybol kuldeni akarja az ajanlatot";
 *  - ar, amig a hivo nem kerdezte.
 */
export function dropPattern(
  history: ReadonlyArray<{ role: string; content: string }>,
  secondsLeft?: number,
): RegExp | null {
  const askedMore = history.some((t) => t.role === 'assistant' && MORE_QUESTIONS_RE.test(t.content));
  const callerTexts = history.filter((t) => t.role === 'user').map((t) => t.content);
  const lastCaller = callerTexts[callerTexts.length - 1] ?? '';
  const callerWrapping = CALLER_ACK_RE.test(lastCaller) || CALLER_DONE_RE.test(lastCaller);
  const timeUp = secondsLeft !== undefined && secondsLeft < 75;

  const parts: string[] = [REGREET_SENTENCE_RE.source];
  const moreOk = !askedMore && (callerWrapping || OFFER_REQUEST_RE.test(lastCaller) || timeUp);
  if (!moreOk) parts.push(MORE_QUESTIONS_RE.source);
  const closingOk = callerWrapping || timeUp || callerTexts.some((c) => OFFER_REQUEST_RE.test(c));
  if (!closingOk) parts.push(CLOSING_RE.source);
  // Arat csak akkor, ha kerdezik (a "kerdezte" teszt szandekosan tag).
  if (!callerTexts.some((c) => PRICE_ASKED_RE.test(c))) parts.push(PRICE_SAID_RE.source);
  return new RegExp(parts.map((p) => `(?:${p})`).join('|'), 'iu');
}
