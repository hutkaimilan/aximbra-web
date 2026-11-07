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
// ha marad, az igény alapján felbecsült összeg 20%-át kérjük (az első 15 ügyfélnek).
const OFFER = {
  hu: ["Kockázat nélkül", "Az első 15 ügyfelünknek: egy hónapig ingyen kipróbálható. Ha bármi nem tetszik, nem kell fizetni semmit, és leállítjuk; ha marad, az igény alapján felbecsült összegnek csak a 20%-át kérjük, a havi karbantartási díjról előre megállapodunk."],
  en: ["No risk", "For our first 15 customers: use the agent free for a month. If anything is not right, you pay nothing and we switch it off; if you keep it, you pay just 20% of the price we estimate from your needs, and we agree the monthly maintenance fee in advance."],
  sk: ["Bez rizika", "Pre prvých 15 zákazníkov: mesiac ho môžete používať zadarmo. Ak vám niečo nebude vyhovovať, nezaplatíte nič a agenta vypneme; ak si ho necháte, zaplatíte len 20 % z ceny odhadnutej podľa vašich potrieb a mesačný poplatok za údržbu si dohodneme vopred."],
  ro: ["Fără risc", "Pentru primii 15 clienți: îl puteți folosi gratuit o lună. Dacă ceva nu vă convine, nu plătiți nimic și îl oprim; dacă îl păstrați, plătiți doar 20% din prețul estimat în funcție de nevoile dumneavoastră, iar taxa lunară de întreținere o stabilim dinainte."],
  hr: ["Bez rizika", "Za prvih 15 kupaca: mjesec dana ga možete koristiti besplatno. Ako vam nešto ne odgovara, ne plaćate ništa i isključujemo ga; ako ga zadržite, plaćate samo 20 % cijene procijenjene prema vašim potrebama, a mjesečnu naknadu za održavanje dogovaramo unaprijed."],
  sl: ["Brez tveganja", "Za prvih 15 strank: mesec dni ga lahko uporabljate brezplačno. Če vam kaj ne ustreza, ne plačate ničesar in ga izklopimo; če ga obdržite, plačate le 20 % cene, ocenjene glede na vaše potrebe, mesečno vzdrževalnino pa se vnaprej dogovorimo."],
  fr: ["Sans risque", "Pour nos 15 premiers clients : vous l’utilisez gratuitement pendant un mois. Si quelque chose ne vous convient pas, vous ne payez rien et nous l’arrêtons ; si vous le gardez, vous ne payez que 20 % du prix estimé selon vos besoins, et nous convenons à l’avance des frais de maintenance mensuels."],
  nl: ["Zonder risico", "Voor onze eerste 15 klanten: u gebruikt de agent een maand gratis. Als er iets niet bevalt, betaalt u niets en zetten we hem uit; als u hem houdt, betaalt u slechts 20% van de prijs die we op basis van uw behoeften inschatten, en de maandelijkse onderhoudsvergoeding spreken we vooraf af."],
  sv: ["Utan risk", "För våra första 15 kunder: ni använder agenten gratis i en månad. Om något inte passar betalar ni ingenting och vi stänger av den; om ni behåller den betalar ni bara 20 % av det pris vi uppskattar utifrån era behov, och den månatliga underhållsavgiften kommer vi överens om i förväg."],
  fi: ["Ilman riskiä", "Ensimmäisille 15 asiakkaalle: voitte käyttää agenttia kuukauden ilmaiseksi. Jos jokin ei miellytä, ette maksa mitään ja suljemme sen; jos pidätte sen, maksatte vain 20 % tarpeidenne perusteella arvioidusta hinnasta, ja kuukausittaisesta ylläpitomaksusta sovimme etukäteen."],
  pt: ["Sem risco", "Para os nossos primeiros 15 clientes: podem usar o agente gratuitamente durante um mês. Se algo não vos agradar, não pagam nada e desligamos o agente; se ficarem com ele, pagam apenas 20% do preço estimado segundo as vossas necessidades, e a mensalidade de manutenção combinamos de antemão."],
  de: ["Ohne Risiko", "Für unsere ersten 15 Kunden: Sie nutzen den Agenten einen Monat lang kostenlos. Wenn etwas nicht passt, zahlen Sie nichts und wir schalten ihn ab; wenn Sie ihn behalten, zahlen Sie nur 20 % des nach Ihrem Bedarf geschätzten Preises, die monatliche Wartungsgebühr vereinbaren wir vorab."],
  es: ["Sin riesgo", "Para nuestros primeros 15 clientes: puede usar el agente gratis durante un mes. Si algo no le convence, no paga nada y lo desactivamos; si se lo queda, paga solo el 20 % del precio estimado según sus necesidades, y la cuota mensual de mantenimiento la acordamos de antemano."],
  zh: ["零风险", "我们的前15位客户：可免费试用一个月。如有任何不满意，无需付费，我们会停用该代理；如继续使用，只需支付根据您的需求估算价格的20%，每月维护费用提前商定。"],
  it: ["Senza rischi", "Per i nostri primi 15 clienti: potete usare l’agente gratis per un mese. Se qualcosa non va, non pagate nulla e lo spegniamo; se lo tenete, pagate solo il 20% del prezzo stimato in base alle vostre esigenze, e il canone mensile di manutenzione lo concordiamo in anticipo."],
};

export const offerFor = (lang) => OFFER[(lang || "").toLowerCase().slice(0, 2)] || OFFER.en;
