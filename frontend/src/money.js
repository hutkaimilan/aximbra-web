/** Egy ár, nyolc nyelv, négyféle pénznem.
 *
 *  Az árak forintban vannak kitalálva, es forintban is maradnak: a szerzodes
 *  forintban kotodik. A latogato viszont a sajat penznemeben erti meg, hogy
 *  sok-e vagy keves - egy nemet cegvezetonek a "290 000 Ft" nem szam, hanem
 *  rejtveny. Ezert a nyelvi fajlokban mar nem szoveg all, hanem a forintosszeg
 *  ("120000", "150000-400000", "900000+"), es a megjelenitéskor valtjuk at.
 *
 *  Miert nem nyelvenkent beirt szoveg: nyolc fajl x tizenot ar szaznal tobb
 *  helyen ugyanaz a szam. Egyetlen aremeles utan a felet biztosan elfelejtenenk
 *  atirni, es a nemet lapon honapokig a regi ar allna.
 */

/** Hany forint egy egyseg. Kozelito, szandekosan kerek ertekek - a lapon ki is
 *  irjuk, hogy mivel szamoltunk, igy a latogato tudja ellenorizni. Napi
 *  arfolyamot szandekosan nem huzunk le: egy arlista nem tozsde, es egy
 *  kulso API kiesese nem teheti arak nelkulive a lapot. */
export const RATES = { EUR: 400, RON: 80 };

/** Melyik nyelv melyik penznemben lat. A szlovak euro (2009 ota), nem korona. */
export const CURRENCY_BY_LANG = {
  hu: "HUF", en: "EUR", de: "EUR", es: "EUR",
  fr: "EUR", it: "EUR", ro: "RON", sk: "EUR",
};

export const currencyFor = (lang) => CURRENCY_BY_LANG[lang] || "EUR";

/** "150000-400000" | "900000+" | "120000" -> { from, to, open } */
export function parseToken(token) {
  const s = String(token ?? "").trim();
  if (!s) return null;
  if (s.endsWith("+")) {
    const v = Number(s.slice(0, -1));
    return Number.isFinite(v) ? { from: v, to: null, open: true } : null;
  }
  const parts = s.split("-");
  const from = Number(parts[0]);
  if (!Number.isFinite(from)) return null;
  if (parts.length === 1) return { from, to: null, open: false };
  const to = Number(parts[1]);
  return Number.isFinite(to) ? { from, to, open: false } : null;
}

/** Kerekites, hogy az atvaltas ne hazudjon pontossagot. A 150 000 Ft-bol nem
 *  "374,63 euro" lesz, hanem "375 euro" - es a lapon ott all, hogy kozelito. */
function roundNice(v) {
  const step = v < 1000 ? 5 : v < 10000 ? 50 : 500;
  return Math.round(v / step) * step;
}

/** Ezres tagolas. Angolul vesszo, mindenhol mashol szokoz - ez a ket szokas
 *  fedi le mind a nyolc nyelvet. */
function group(n, lang) {
  const s = String(Math.round(n));
  const sep = lang === "en" ? "," : " ";
  return s.replace(/\B(?=(\d{3})+(?!\d))/g, sep);
}

/** A magyar lapon megmaradt tomor alak: "150–400 eFt", "400 eFt – 1,2 MFt".
 *  Tizenket kartyan ez fer el, a teljes alak nem. */
function hufCompact(v) {
  const mega = v >= 1_000_000;
  const num = mega ? v / 1_000_000 : v / 1000;
  const text = String(Math.round(num * 10) / 10).replace(".", ",");
  return { text, unit: mega ? "MFt" : "eFt" };
}

function hufRange(from, to) {
  const a = hufCompact(from);
  if (to == null) return `${a.text} ${a.unit}`;
  const b = hufCompact(to);
  // Azonos egysegnel egyszer irjuk ki ("150–400 eFt"), kulonbozonel ketszer,
  // kulonben a "400–1,2 MFt" azt allitana, hogy 400 millio forinttol indul.
  return a.unit === b.unit
    ? `${a.text}–${b.text} ${a.unit}`
    : `${a.text} ${a.unit} – ${b.text} ${b.unit}`;
}

function withSymbol(text, currency, lang) {
  if (currency === "EUR") return lang === "en" ? `€${text}` : `${text} €`;
  if (currency === "RON") return `${text} RON`;
  return `${text} Ft`;
}

/**
 * @param {string} token   forintosszeg: "120000" | "150000-400000" | "900000+"
 * @param {string} lang    nyelvkod
 * @param {"compact"|"full"} style  a kartyakon tomor, a csomagoknal teljes
 * @returns {string} a kesz ar, "-tol" nelkul - azt a hivo teszi ra, mert
 *          nyelvenkent mas a szorend ("ab 2 250 €" vs "2 250 € felett")
 */
export function formatPrice(token, lang, style = "full") {
  const p = parseToken(token);
  if (!p) return "";
  const currency = currencyFor(lang);

  if (currency === "HUF") {
    if (style === "compact") return hufRange(p.from, p.to);
    const a = group(p.from, lang);
    return p.to == null ? withSymbol(a, "HUF", lang)
      : `${a}–${group(p.to, lang)} Ft`;
  }

  const rate = RATES[currency];
  const a = group(roundNice(p.from / rate), lang);
  if (p.to == null) return withSymbol(a, currency, lang);
  const b = group(roundNice(p.to / rate), lang);
  // A jelet egyszer tesszuk ki a tartomanyra: "375–1 000 €", nem "375 € – 1 000 €".
  return lang === "en"
    ? `${withSymbol(a, currency, lang)}–${b}`
    : `${a}–${withSymbol(b, currency, lang)}`;
}

/** Igaz, ha ezen a nyelven atvaltott arakat mutatunk - csak ilyenkor van
 *  ertelme kiirni, hogy milyen arfolyammal szamoltunk. */
export const isConverted = (lang) => currencyFor(lang) !== "HUF";
