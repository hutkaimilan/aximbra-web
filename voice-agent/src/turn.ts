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

/**
 * Visszahivasban MI hivtuk az ugyfelet, ott a "Köszönöm a hívást" tevedes
 * (szimulator, 2026-11-11: a visszahivas igy zarult). A szoveg a
 * SentenceDropFilter utan egesz mondatokban jon, igy a tobbszavas csere
 * nem esik szet a streamelt darabok hataran.
 */
const CALLBACK_WORDING: Array<[RegExp, string]> = [
  [/köszön(öm|jük)(,? szépen)?,? (?:a hívást|a hívását|hogy (?:fel)?hívott)/giu, 'köszön$1$2 a beszélgetést'],
  [/thank you for calling/giu, 'thank you for your time'],
  [/thanks for calling/giu, 'thanks for your time'],
];

export function callbackWording(text: string): string {
  let out = text;
  for (const [re, rep] of CALLBACK_WORDING) {
    out = out.replace(re, (...args: unknown[]) => {
      const m = String(args[0]);
      const r = rep.replace(/\$(\d)/gu, (_x, n: string) => String(args[Number(n)] ?? ''));
      const upper = m[0] !== undefined && m[0] !== m[0].toLowerCase();
      return upper ? r.charAt(0).toUpperCase() + r.slice(1) : r;
    });
  }
  return out;
}

/**
 * A koszonesben mar elhangzott "Miben segithetek?" ujra nem hangzik el:
 * eles hivas (2026-11-12) - a hivo minden felmondatara ("Először is.")
 * ugyanezzel felelt. Helyette egy rovid "Hallgatom." A "Miben segíthetek
 * még?" (zaro kerdes) ezt nem erinti.
 */
export function polishReply(text: string): string {
  return text.replace(/(?<![\p{L}])([mM])iben segíthetek(?: (?:Önnek|önnek|Önöknek))?\s*\?/gu, (_m, c: string) =>
    c === 'M' ? 'Hallgatom.' : 'hallgatom.',
  );
}

/** "Van meg kerdese?" es rokonai - egy hivasban egyszer hangozhat el. */
// A "Van még esetleg kérdése" alakot a korabbi minta nem ismerte fel
// (szimulator, 2026-11-11), igy a "mar elhangzott" vedelem sem kapcsolt be.
export const MORE_QUESTIONS_RE =
  /(?<![\p{L}])(?:van|lenne|volna) (?:még|esetleg)(?: még| esetleg)? (?:más |egyéb |bármi )?kérdés\p{L}*|segíthetek még|még valamiben|még miben|\bany (?:other|more|further) questions\b|\banything else\b/iu;

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
  /**
   * @param relaxed  Ha MINDEN mondat kiesne, ezzel a gyengebb mintaval
   *                 szurunk ujra, mielott az eredetit engednenk ki. (Pl.
   *                 "<ar>. Van meg kerdese?" - az ar maradjon, ne mindketto.)
   */
  constructor(
    private readonly drop: RegExp | null,
    private readonly relaxed: RegExp | null = null,
  ) {}
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
    if (this.emitted) return keepRest;
    // Egyetlen mondat sem maradt. Elobb a gyengebb mintaval probaljuk
    // (dropSentences ugyanigy dont, igy a tortenet is ezt rogziti)...
    const all = this.dropped + rest;
    if (this.relaxed) {
      const g = new SentenceDropFilter(this.relaxed);
      const kept = g.push(all) + g.flush();
      if (kept.trim() && g.emitted) return kept;
    }
    // ...es ha az sem hagy semmit, inkabb az eredeti hangzik el, mint a csend.
    return all;
  }
}

/** Ugyanez kesz szovegre (a tortenetbe ez kerul). */
export function dropSentences(text: string, drop: RegExp | null, relaxed: RegExp | null = null): string {
  if (!drop) return text;
  const f = new SentenceDropFilter(drop, relaxed);
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
// Az angol kerdoszavak csak mondat elejen szamitanak: a "Thanks, that's what
// I needed." nem kerdes, hanem lezaras.
export const CALLER_ASKED_RE =
  /\?|(?<![\p{L}])(?:mennyibe|mennyi|hogyan|milyen|mikor|hol|miért|melyik|mi történik|tudna|lehetne|van-e|kell-e)(?![\p{L}])|(?:^|[.!,;]\s*)(?:how|what|when|where|why|which|can you|could you|do you|does it|is it|are you|will it|would it)(?![\p{L}])/iu;

/**
 * Kerdezte-e mar a hivo az arat (barmikor a hivasban).
 *
 * Szandekosan tag: ha ez tevesen "nem"-et mondana, a lenti szuro egy jogos
 * arvalaszt nyelne le, es a hivo hiaba kerdezne ujra. Ezert minden
 * penzre, arra, koltsegre utalo szo "kerdeznek" szamit.
 */
// "mennyi", de nem "mennyiség" es nem "mennyi idő": a "mennyiségről" szo
// miatt a szimulatorban kerdes nelkul hangzott el az ar.
export const PRICE_ASKED_RE =
  /mennyi(?!ség|\s+id[őe])|mibe kerül|kerül|(?<![\p{L}])ár(?:a|at|ak|áról|ban|ért|on|ai|ra|ok|akat)?(?![\p{L}])|árak|árajánlat|költ|díj|fizet|pénz|drága|olcsó|kedvezmény|keret|forint|ezer|millió|price|cost|how much|fee|budget|pay|cheap|expensive|discount/iu;

/** Arat vagy az ajanlat szazalekat kimondo mondat. */
export const PRICE_SAID_RE =
  /(?<![\p{L}])(?:forint\p{L}*|ft)(?![\p{L}])|\p{L}*(?:ezer|millió)(?![\p{L}])|százalék|forint|percent|thousand|million/iu;

/** A hivo csak nyugtazott ("Értem.", "Rendben, köszönöm.") - nem kerdezett, nem mesel. */
export const CALLER_ACK_RE =
  /^(?:[\s,.!]*(?:hát|na|oké|okés|ok|jó|jól van|értem|rendben|világos|köszönöm|köszönöm szépen|köszi|aha|értettem|szuper|nagyszerű|remek|tökéletes|értem köszönöm|okay|all right|alright|thanks|thank you|got it|i see|right|great|fine))+[\s,.!]*$/iu;

/** Nemleges valasz a "Van meg kerdese?"-re ("Nincs, köszönöm."). */
export const CALLER_NO_MORE_RE =
  /^[\s,.!]*(?:köszönöm,?\s*)?(?:nem|nincs|nincsen|semmi|egyelőre nem|most nem|nem igazán|no|nope|nothing|not really)(?![\p{L}])/iu;

/**
 * A hivo jelezte, hogy vegzett.
 *
 * Szohatarral es mondatveggel: a korabbi, laza minta a "Mennyi lenne?"
 * kerdesben az "ennyi lenne"-t, az "ez elég nehéz" mondatban az "ez elég"-et
 * talalta meg, es lezarasnak vette - pont a hivo kerdesei kozben engedte
 * volna a "Van meg kerdese?"-t es az ajanlatot (szimulator, 2026-11-11).
 */
export const CALLER_DONE_RE = new RegExp(
  [
    'nincs (?:több|más|egyéb) kérdés',
    '(?:több|más|egyéb) kérdésem nincs',
    '(?<![\\p{L}])(?:ennyi|ez) (?:lenne|volt|lett volna|minden|elég)(?=\\s*(?:[.!,]|$))',
    'minden világos',
    'mindent (?:értek|értettem|megértettem)',
    'viszont(?:látásra|hallásra)',
    'majd (?:jelentkezem|jelentkezünk|visszahívom|visszahívjuk|visszaszólok|visszaszólunk|keresem|keressük|hívom|hívjuk)',
    '(?:akkor|majd) (?:meg|fel)(?:keres|hív)(?:lek|lak|em|om|ük|juk|sük)(?![\\p{L}])',
    '(?:jelentkezni|keresni|hívni) fog(?:ok|unk|lak|om|juk)',
    'átgondolom|átgondoljuk|meggondolom|meggondoljuk|megbeszélem|megbeszéljük',
    // A mondat koszonettel zarul ("... a számomon lehet elérni. Köszönöm
    // szépen!"): a hivo bucsuzik (szimulator, 2026-11-11 - erre az agent
    // elkoszones nelkul bontott).
    '(?:köszönöm|köszönjük|köszi|thank you|thanks)(?: szépen| a (?:segítséget|tájékoztatást|választ|türelmét|beszélgetést))?[\\s.!]*$',
    "that'?s (?:all|everything|it|what i needed)(?![\\p{L}])",
    'no (?:more|other|further) questions',
    'nothing else',
    "i'?ll (?:think about it|get back to you)",
    'goodbye',
    '(?<![\\p{L}])bye(?![\\p{L}])',
  ].join('|'),
  'iu',
);

/**
 * A hivo maga kert ajanlatot, visszahivast vagy embert.
 *
 * Csak a kifejezett keres szamit. A korabbi minta minden "kolléga",
 * "visszahív" es "ajánlat" szora rakapcsolt - igy egy visszahivasban a
 * "visszahívást kértem" vagy a "a kollégáim nem érnek rá" az egesz hivasra
 * feloldotta a zarast.
 */
export const OFFER_REQUEST_RE = new RegExp(
  [
    // Kuldesre keres, felszolito/feltételes alakban ("Küldjenek...").
    '(?<![\\p{L}])(?:küldjenek|küldjön|küldjék|küldené|küldenék|küldenének|küldhetné|küldhetnék|küldhetnének|küldjétek|küldj)(?![\\p{L}])',
    // Ajanlatot / reszleteket ker. A "kér" nem lehet a "kérdez" eleje:
    // "Azt kérdezném, mi van az ajánlatban" nem keres.
    '(?:kér(?!dez|dés)|küld)\\p{L}*[^.?!]{0,40}(?:ár)?(?:ajánlat|részlet|összefoglal|tájékoztat)',
    '(?:ár)?ajánlat\\p{L}*[^.?!]{0,30}(?:kér(?!dez|dés)|küld|kap)',
    '(?<![\\p{L}])(?:hívjanak|keressenek)(?![\\p{L}])',
    '(?:hívjon|keressen) (?:vissza|meg|fel)',
    'visszahívna|visszahívnának|visszahívhatna|visszahívhatnának|visszahívnátok',
    'elérhetőség',
    '(?<![\\p{L}])felír',
    '(?<![\\p{L}])a számom',
    // A hivo megadja az elerhetoseget: kapcsolatot ker.
    '(?:lehet|tudnak|tudják|tudja|tudnának) (?:engem )?elérni|(?<![\\p{L}])elérhető vagyok|e-?mail ?címem|(?<![\\p{L}])a címem|telefonszámom',
    "my (?:e-?mail|number|phone number) is|reach me",
    // Tovabblepni akar ("Akkor mi a következő lépés?", szimulator v9).
    'mi a következő|hogyan tovább|hogyan (?:tudunk|lehet) továbblépni|mi(?:t kell| a teendő) (?:most|ezután|innentől)',
    "what(?:'s| is) (?:the )?next|next steps?|how do we (?:proceed|move forward)",
    '(?:beszél|kapcsol)\\p{L}*[^.?!]{0,30}(?:kollég|ember|munkatárs|ügyintéz)',
    '(?:kollég|ember|munkatárs|ügyintéz)\\p{L}*[^.?!]{0,20}(?:beszél|kapcsol)',
    'quote|proposal|get back to me',
    // "Could you send some more details to my email" (szimulator, kulfoldi)
    'send\\b[^.?!]{0,30}\\b(?:details|information|info|summary|brochure|offer|it over|to my e-?mail)',
    '(?:e-?mail|text|call|contact|send) me(?![\\p{L}])',
    '(?:speak|talk) (?:to|with) (?:a |an |someone|somebody|a real)',
  ].join('|'),
  'iu',
);

/** Zaro lepes: nev/ceg kerdese, ajanlat, SMS vagy e-mail felajanlasa. */
export const CLOSING_RE =
  /kihez címezzem|melyik cégnél|hogy hívják|mi a (?:neve|cég)|mi az ön neve|a nevét|cég ?nev|melyik (?:cég|szerviz|üzlet|iroda|vállalkozás|szalon|rendelő|bolt|étterem|pékség|stúdió)\p{L}*(?:ről|ből|tól|től| neve)|küldjem|(?<![\p{L}])sms|ajánlatot (?:küld|össze|készít)|elküldöm az ajánlat|felírhatom|felírom|who should i address|which company|your name|text message|send (?:it|you|the quote)/iu;

/**
 * Nev- vagy cegnevkerdes. Egy hivasban legfeljebb EGYSZER hangozhat el: a
 * szimulatorban az agent a hivo "Értem."-jere szo szerint megismetelte
 * ("Melyik cégnél dolgozik...?"), elesben pedig harmadszor is - a hivo
 * tolakodasnak erezte.
 */
export const NAME_ASK_RE =
  /kihez címezzem|melyik cégnél|hogy hívják|mi a (?:neve|cég)|mi az ön neve|a nevét|cég ?nev|melyik (?:cég|szerviz|üzlet|iroda|vállalkozás|szalon|rendelő|bolt|étterem|pékség|stúdió)\p{L}*(?:ről|ből|tól|től| neve)|who should i address|which company|your name/iu;

/**
 * A felelossegi valasz ket mondata. A promptban szo szerint all, arra az
 * esetre, ha a hivo megkerdezi, ki felel a hibaert - a modell viszont az
 * adattarolasi, sot a hataridore vonatkozo kerdesekre is elmondta
 * (szimulator, 2026-11-11, negy hivasban).
 *  - A hibajavitas mondata csak akkor, ha a hivo a hibarol kerdezett.
 *  - A jovahagyas mondata egyszer elhangozhat magatol is (ez a fo
 *    ervunk), de ismetelni csak kerdesre lehet.
 */
export const BUGFIX_SAID_RE =
  /hibát találunk|keretében (?:mi )?javítjuk|if we find a (?:bug|fault|problem)|we fix it within/iu;
export const APPROVAL_SAID_RE = /semmit nem küld ki magától|does not send anything out (?:by|on) its own/iu;
/** A hivo a hibarol, a felelossegrol vagy a kockazatrol kerdez. */
export const ERROR_ASKED_RE =
  /hib[aáái]|téved|elront|rossz|felel|baj|kár(?:t|ért|osod)|kockázat|mistake|wrong|error|fault|bug|responsib|liab|fail|risk/iu;

/**
 * "Érdekli esetleg, hogyan működik...?" - ajanlkozo kerdes, nem a hivo
 * helyzetere vonatkozik. A szimulatorban rendszeresen igy zarta a
 * valaszait, a hivo pedig minden alkalommal kenytelen volt "Értem."-mel
 * felelni. A hivo maga kerdez, ha erdekli.
 */
export const NUDGE_RE =
  /(?:^\s*|,\s*)(?:érdekli(?: esetleg)?,? (?:hogy|hogyan|mennyi|milyen|mi )|szeretné(?: esetleg)? tudni|szeretné,? ha (?:\p{L}+ )?(?:elmondanám|bemutatnám|ismertetném|részletezném)|elmondjam|részletezzem|bemutassam|would you like to (?:know|hear) (?:more|how|what|about)|do you want to (?:know|hear) (?:more|how|what|about))[^.!?]*\?\s*$/iu;

/**
 * A modell a sajat szabalyait mondja ki ("Mivel a nevét és a cégét már
 * megadta, más teendőnk nincs."). Ez a hivonak ertelmetlen es gepies.
 */
export const META_RE = /^\s*mivel (?:a nevét|a cégét|a cégnevet|már (?:megadta|ismerem|tudom))/iu;

/** Elhangzott-e elkoszones (a bontas elott kotelezo). */
// A "további szép napot kívánok!" is elkoszones: a szimulatorban emiatt
// ketszer koszont el ("... szép napot kívánok! Köszönöm a beszélgetést,
// viszonthallásra!").
export const GOODBYE_SAID_RE =
  /viszont(?:látásra|hallásra)|viszlát|szép (?:napot|estét|hétvégét|délutánt)|jó munkát|minden jót|good ?bye|(?<![\p{L}])bye(?![\p{L}])|have a (?:nice|good|great|lovely) (?:day|evening|weekend)|take care/iu;

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
/**
 * Vegzett-e a hivo: az utolso mondata lezaras, nem kerdes es nem meseles.
 *
 *  - Ha kerdez, nem vegzett - akkor sem, ha a mondataban "értem" is van.
 *  - A puszta "Értem." csak akkor lezaras, ha mi nem kerdeztunk elotte:
 *    a kerdesunkre adott "Értem." nem valasz, hanem elakadas.
 *  - A "Van meg kerdese?"-re adott "Nincs" / "Értem, köszönöm" lezaras.
 */
export function callerIsWrapping(history: ReadonlyArray<{ role: string; content: string }>): boolean {
  let lastCaller = '';
  let lastAgent = '';
  for (let i = history.length - 1; i >= 0; i -= 1) {
    const t = history[i]!;
    if (!lastCaller && t.role === 'user') {
      lastCaller = t.content.trim();
      continue;
    }
    if (lastCaller && t.role === 'assistant') {
      lastAgent = t.content.trim();
      break;
    }
  }
  if (!lastCaller) return false;
  if (CALLER_ASKED_RE.test(lastCaller)) return false;
  if (CALLER_DONE_RE.test(lastCaller)) return true;
  const ack = CALLER_ACK_RE.test(lastCaller);
  if (MORE_QUESTIONS_RE.test(lastAgent)) return ack || CALLER_NO_MORE_RE.test(lastCaller);
  if (!ack) return false;
  const weAsked = /\?\s*$/u.test(lastAgent);
  return !weAsked || /köszön|thank/iu.test(lastCaller);
}

export function dropPattern(
  history: ReadonlyArray<{ role: string; content: string }>,
  secondsLeft?: number,
): RegExp | null {
  return dropRules(history, secondsLeft).strict;
}

/**
 * A kiszurendo mondatok mintai: `strict` a teljes, `relaxed` ugyanez az ar
 * nelkul. Ha a valasz minden mondata kiesne (pl. "<ar>. Van meg kerdese?"),
 * a `relaxed` donti el, mi marad - az eredeti szoveg csak vegso esetben.
 */
export function dropRules(
  history: ReadonlyArray<{ role: string; content: string }>,
  secondsLeft?: number,
): { strict: RegExp; relaxed: RegExp | null } {
  const askedMore = history.some((t) => t.role === 'assistant' && MORE_QUESTIONS_RE.test(t.content));
  const callerTexts = history.filter((t) => t.role === 'user').map((t) => t.content);
  const lastCaller = callerTexts[callerTexts.length - 1] ?? '';
  const callerWrapping = callerIsWrapping(history);
  const timeUp = secondsLeft !== undefined && secondsLeft < 75;
  // Kifejezett ajanlat-/visszahivas-keres MOST, illetve korabban a hivasban.
  const offerNow = OFFER_REQUEST_RE.test(lastCaller);
  const offerEarlier = callerTexts.some((c) => OFFER_REQUEST_RE.test(c));
  const callerAsks = CALLER_ASKED_RE.test(lastCaller);

  const parts: string[] = [REGREET_SENTENCE_RE.source, NUDGE_RE.source, META_RE.source];
  if (!ERROR_ASKED_RE.test(lastCaller)) {
    parts.push(BUGFIX_SAID_RE.source);
    if (history.some((t) => t.role === 'assistant' && APPROVAL_SAID_RE.test(t.content))) {
      parts.push(APPROVAL_SAID_RE.source);
    }
  }
  const moreOk = !askedMore && (callerWrapping || offerNow || timeUp);
  if (!moreOk) parts.push(MORE_QUESTIONS_RE.source);
  // Ha a zaras mar elkezdodott ("Van meg kerdese?" vagy nevkerdes elhangzott),
  // a folytatasa (az SMS/ajanlat nyugtazasa, elkoszones) mehet - kulonben a
  // hivo "Kiss István, Kiss Hajstúdió" valasza utan az "Az ajánlatot SMS-ben
  // elküldöm" mondat kiesne.
  const closingStarted = history.some(
    (t) => t.role === 'assistant' && (MORE_QUESTIONS_RE.test(t.content) || NAME_ASK_RE.test(t.content)),
  );
  // Korabbi keres (vagy megkezdett zaras) utan is csak akkor zarhatunk, ha
  // a hivo eppen nem kerdez: a kerdesere elobb valaszolunk, a nevkerdes nem
  // kerul a valasz vegere.
  const closingOk = callerWrapping || timeUp || offerNow || ((offerEarlier || closingStarted) && !callerAsks);
  if (!closingOk) parts.push(CLOSING_RE.source);
  // A nevet/cegnevet egyszer kerdezzuk meg - akkor sem ujra, ha nem felelt.
  if (history.some((t) => t.role === 'assistant' && NAME_ASK_RE.test(t.content))) {
    parts.push(NAME_ASK_RE.source);
  }
  const build =(ps: string[]): RegExp => new RegExp(ps.map((p) => `(?:${p})`).join('|'), 'iu');
  // Arat csak akkor, ha kerdezik (a "kerdezte" teszt szandekosan tag).
  if (!callerTexts.some((c) => PRICE_ASKED_RE.test(c))) {
    return { strict: build([...parts, PRICE_SAID_RE.source]), relaxed: build(parts) };
  }
  return { strict: build(parts), relaxed: null };
}
