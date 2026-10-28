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
// ha marad, csak az ár felét kérjük.
const OFFER = {
  hu: ["Kockázat nélkül", "Egy hónapig ingyen kipróbálható. Ha bármi nem tetszik, nem kell fizetni semmit, és leállítjuk; ha marad, akkor is csak az ár felét kérjük."],
  en: ["No risk", "You can use the agent free for a month. If anything is not right, you pay nothing and we switch it off; if you keep it, you pay only half the price."],
  sk: ["Bez rizika", "Mesiac ho môžete používať zadarmo. Ak vám niečo nebude vyhovovať, nezaplatíte nič a agenta vypneme; ak si ho necháte, zaplatíte len polovicu ceny."],
  ro: ["Fără risc", "Îl puteți folosi gratuit o lună. Dacă ceva nu vă convine, nu plătiți nimic și îl oprim; dacă îl păstrați, plătiți doar jumătate din preț."],
  hr: ["Bez rizika", "Mjesec dana ga možete koristiti besplatno. Ako vam nešto ne odgovara, ne plaćate ništa i isključujemo ga; ako ga zadržite, plaćate samo pola cijene."],
  sl: ["Brez tveganja", "Mesec dni ga lahko uporabljate brezplačno. Če vam kaj ne ustreza, ne plačate ničesar in ga izklopimo; če ga obdržite, plačate le polovico cene."],
  fr: ["Sans risque", "Vous l’utilisez gratuitement pendant un mois. Si quelque chose ne vous convient pas, vous ne payez rien et nous l’arrêtons ; si vous le gardez, vous ne payez que la moitié du prix."],
  nl: ["Zonder risico", "U gebruikt de agent een maand gratis. Als er iets niet bevalt, betaalt u niets en zetten we hem uit; als u hem houdt, betaalt u maar de helft van de prijs."],
  sv: ["Utan risk", "Ni använder agenten gratis i en månad. Om något inte passar betalar ni ingenting och vi stänger av den; om ni behåller den betalar ni bara halva priset."],
  fi: ["Ilman riskiä", "Voitte käyttää agenttia kuukauden ilmaiseksi. Jos jokin ei miellytä, ette maksa mitään ja suljemme sen; jos pidätte sen, maksatte vain puolet hinnasta."],
  pt: ["Sem risco", "Podem usar o agente gratuitamente durante um mês. Se algo não vos agradar, não pagam nada e desligamos o agente; se ficarem com ele, pagam apenas metade do preço."],
  de: ["Ohne Risiko", "Sie nutzen den Agenten einen Monat lang kostenlos. Wenn etwas nicht passt, zahlen Sie nichts und wir schalten ihn ab; wenn Sie ihn behalten, zahlen Sie nur den halben Preis."],
  es: ["Sin riesgo", "Puede usar el agente gratis durante un mes. Si algo no le convence, no paga nada y lo desactivamos; si se lo queda, paga solo la mitad del precio."],
  it: ["Senza rischi", "Potete usare l’agente gratis per un mese. Se qualcosa non va, non pagate nulla e lo spegniamo; se lo tenete, pagate solo metà del prezzo."],
};

export const offerFor = (lang) => OFFER[(lang || "").toLowerCase().slice(0, 2)] || OFFER.en;
