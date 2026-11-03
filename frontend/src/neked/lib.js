/**
 * A /neked oldal kapcsolata a sales agenttel: az oldal adatának lekérése és a
 * megnyitás / kattintás jelzése. A komponensek az Emergent-féle demóoldalból
 * jönnek; ez a fájl köti őket a mi szerverünkhöz.
 */

export const SALES = process.env.REACT_APP_SALES_URL || "https://aximbra-sales-production.up.railway.app";

export const fmtNum = (n, lang) => {
  try {
    return new Intl.NumberFormat(lang || "hu").format(Math.round(n));
  } catch {
    return String(Math.round(n));
  }
};

export const fmtHuf = (n, lang) => `${fmtNum(n, lang)} Ft`;

export const mailtoHref = (email, company) =>
  `mailto:${email}?subject=${encodeURIComponent(company)}&body=${encodeURIComponent(window.location.href.split("?")[0] + "\n\n")}`;

let slug = null;
const sent = new Set();
const preview = () => new URLSearchParams(window.location.search).has("preview");

export const setTrackSlug = (s) => {
  slug = s;
};

// A komponensek eseménynevei -> a sales agent eseménytípusai.
const TYPES = { open: "open", demo_click: "demo", live_demo_click: "live", cta_click: "cta" };
const ONCE_PER_VIEW = new Set(["open", "demo_click"]);

/** Soha nem akaszthatja meg az oldalt: ha a kérés elszáll, elnyeljük. */
export const track = (event) => {
  const type = TYPES[event];
  if (!slug || !type || preview()) return;
  const key = `${slug}:${event}`;
  if (ONCE_PER_VIEW.has(event) && sent.has(key)) return;
  sent.add(key);
  try {
    fetch(`${SALES}/public/neked/${encodeURIComponent(slug)}/event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ type }),
      keepalive: true,
    }).catch(() => {});
  } catch {
    /* a számláló nem ronthatja el az oldalt */
  }
};

// Az ajánlat (a tulajdonos döntése), ugyanaz a mondat, mint a levelekben:
// egy hónap ingyen; ha bármi baj van, nem fizetnek semmit, és leállítjuk;
// ha marad, a megegyezett ár 30%-át kérjük, utána havi karbantartási díj jön.
const OFFER = {
  hu: ["Kockázat nélkül", "Egy hónapig ingyen kipróbálható. Ha bármi nem tetszik, nem kell fizetni semmit, és leállítjuk; ha marad, a megegyezett ár 30%-át kérjük, utána havi karbantartási díj jön, amit előre megbeszélünk."],
  en: ["No risk", "You can use the agent free for a month. If anything is not right, you pay nothing and we switch it off; if you keep it, you pay 30% of the agreed price, then a monthly maintenance fee we agree on in advance."],
  sk: ["Bez rizika", "Mesiac ho môžete používať zadarmo. Ak vám niečo nebude vyhovovať, nezaplatíte nič a agenta vypneme; ak si ho necháte, zaplatíte 30 % dohodnutej ceny a potom mesačný poplatok za údržbu, ktorý si dohodneme vopred."],
  ro: ["Fără risc", "Îl puteți folosi gratuit o lună. Dacă ceva nu vă convine, nu plătiți nimic și îl oprim; dacă îl păstrați, plătiți 30% din prețul convenit, apoi o taxă lunară de întreținere, stabilită dinainte."],
  hr: ["Bez rizika", "Mjesec dana ga možete koristiti besplatno. Ako vam nešto ne odgovara, ne plaćate ništa i isključujemo ga; ako ga zadržite, plaćate 30 % dogovorene cijene, a zatim mjesečnu naknadu za održavanje koju dogovaramo unaprijed."],
  sl: ["Brez tveganja", "Mesec dni ga lahko uporabljate brezplačno. Če vam kaj ne ustreza, ne plačate ničesar in ga izklopimo; če ga obdržite, plačate 30 % dogovorjene cene, nato pa mesečno vzdrževalnino, o kateri se vnaprej dogovorimo."],
  fr: ["Sans risque", "Vous l’utilisez gratuitement pendant un mois. Si quelque chose ne vous convient pas, vous ne payez rien et nous l’arrêtons ; si vous le gardez, vous payez 30 % du prix convenu, puis des frais de maintenance mensuels fixés à l’avance."],
  nl: ["Zonder risico", "U gebruikt de agent een maand gratis. Als er iets niet bevalt, betaalt u niets en zetten we hem uit; als u hem houdt, betaalt u 30% van de afgesproken prijs, daarna een maandelijkse onderhoudsvergoeding die we vooraf afspreken."],
  sv: ["Utan risk", "Ni använder agenten gratis i en månad. Om något inte passar betalar ni ingenting och vi stänger av den; om ni behåller den betalar ni 30 % av det överenskomna priset, därefter en månatlig underhållsavgift som vi kommer överens om i förväg."],
  fi: ["Ilman riskiä", "Voitte käyttää agenttia kuukauden ilmaiseksi. Jos jokin ei miellytä, ette maksa mitään ja suljemme sen; jos pidätte sen, maksatte 30 % sovitusta hinnasta ja sen jälkeen kuukausittaisen ylläpitomaksun, josta sovimme etukäteen."],
  pt: ["Sem risco", "Podem usar o agente gratuitamente durante um mês. Se algo não vos agradar, não pagam nada e desligamos o agente; se ficarem com ele, pagam 30% do preço acordado e depois uma mensalidade de manutenção combinada de antemão."],
  de: ["Ohne Risiko", "Sie nutzen den Agenten einen Monat lang kostenlos. Wenn etwas nicht passt, zahlen Sie nichts und wir schalten ihn ab; wenn Sie ihn behalten, zahlen Sie 30 % des vereinbarten Preises, danach eine monatliche Wartungsgebühr, die wir vorab vereinbaren."],
  es: ["Sin riesgo", "Puede usar el agente gratis durante un mes. Si algo no le convence, no paga nada y lo desactivamos; si se lo queda, paga el 30 % del precio acordado y después una cuota mensual de mantenimiento acordada de antemano."],
  it: ["Senza rischi", "Potete usare l’agente gratis per un mese. Se qualcosa non va, non pagate nulla e lo spegniamo; se lo tenete, pagate il 30% del prezzo concordato, poi un canone mensile di manutenzione concordato in anticipo."],
};

export const offerFor = (lang) => OFFER[(lang || "").toLowerCase().slice(0, 2)] || OFFER.en;
