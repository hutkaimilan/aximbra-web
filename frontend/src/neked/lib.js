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
// ha marad, az igény alapján felbecsült összeg 40%-át kérjük (az első ügyfél ingyen, referenciáért; utána 14 ügyfél).
const OFFER = {
  hu: ["Kockázat nélkül", "Az első ügyfelünk bármelyik agentet teljesen ingyen kapja meg, cserébe egy referenciáért. A következő 14 ügyfélnek egy hónapig ingyen kipróbálható; ha marad, az igény alapján felbecsült összegnek csak a 40%-át kérjük, a havi karbantartási díjról előre megállapodunk."],
  en: ["No risk", "Our first customer gets any agent completely free, in exchange for a reference. For the next 14 customers: use it free for a month; if you keep it, you pay just 40% of the price we estimate from your needs, and we agree the monthly maintenance fee in advance."],
  sk: ["Bez rizika", "Náš prvý zákazník dostane ľubovoľného agenta úplne zadarmo, výmenou za referenciu. Ďalších 14 zákazníkov ho môže mesiac používať zadarmo; ak si ho nechajú, zaplatia len 40 % z ceny odhadnutej podľa ich potrieb a mesačný poplatok za údržbu si dohodneme vopred."],
  ro: ["Fără risc", "Primul nostru client primește orice agent complet gratuit, în schimbul unei referințe. Următorii 14 clienți îl pot folosi gratuit o lună; dacă îl păstrează, plătesc doar 40% din prețul estimat în funcție de nevoile lor, iar taxa lunară de întreținere o stabilim dinainte."],
  hr: ["Bez rizika", "Naš prvi kupac dobiva bilo kojeg agenta potpuno besplatno, u zamjenu za referencu. Sljedećih 14 kupaca može ga mjesec dana koristiti besplatno; ako ga zadrže, plaćaju samo 40 % cijene procijenjene prema njihovim potrebama, a mjesečnu naknadu za održavanje dogovaramo unaprijed."],
  sl: ["Brez tveganja", "Naša prva stranka dobi katerega koli agenta popolnoma brezplačno, v zameno za referenco. Naslednjih 14 strank ga lahko mesec dni uporablja brezplačno; če ga obdržijo, plačajo le 40 % cene, ocenjene glede na njihove potrebe, mesečno vzdrževalnino pa se dogovorimo vnaprej."],
  fr: ["Sans risque", "Notre premier client reçoit l’agent de son choix entièrement gratuitement, en échange d’une référence. Pour les 14 clients suivants : un mois d’essai gratuit ; si vous le gardez, vous ne payez que 40 % du prix estimé selon vos besoins, et nous convenons à l’avance des frais de maintenance mensuels."],
  nl: ["Zonder risico", "Onze eerste klant krijgt een agent naar keuze volledig gratis, in ruil voor een referentie. De volgende 14 klanten gebruiken de agent een maand gratis; als u hem houdt, betaalt u slechts 40% van de prijs die we op basis van uw behoeften inschatten, en de maandelijkse onderhoudsvergoeding spreken we vooraf af."],
  sv: ["Utan risk", "Vår första kund får valfri agent helt gratis, mot en referens. De följande 14 kunderna använder agenten gratis i en månad; om ni behåller den betalar ni bara 40 % av det pris vi uppskattar utifrån era behov, och den månatliga underhållsavgiften kommer vi överens om i förväg."],
  fi: ["Ilman riskiä", "Ensimmäinen asiakkaamme saa minkä tahansa agentin täysin ilmaiseksi referenssiä vastaan. Seuraavat 14 asiakasta voivat käyttää agenttia kuukauden ilmaiseksi; jos pidätte sen, maksatte vain 40 % tarpeidenne perusteella arvioidusta hinnasta, ja kuukausittaisesta ylläpitomaksusta sovimme etukäteen."],
  pt: ["Sem risco", "O nosso primeiro cliente recebe qualquer agente totalmente grátis, em troca de uma referência. Os 14 clientes seguintes podem usar o agente gratuitamente durante um mês; se ficarem com ele, pagam apenas 40% do preço estimado segundo as vossas necessidades, e a mensalidade de manutenção combinamos de antemão."],
  de: ["Ohne Risiko", "Unser erster Kunde erhält einen beliebigen Agenten völlig kostenlos, im Gegenzug für eine Referenz. Die nächsten 14 Kunden nutzen den Agenten einen Monat lang kostenlos; wenn Sie ihn behalten, zahlen Sie nur 40 % des nach Ihrem Bedarf geschätzten Preises, die monatliche Wartungsgebühr vereinbaren wir vorab."],
  es: ["Sin riesgo", "Nuestro primer cliente recibe cualquier agente totalmente gratis, a cambio de una referencia. Los 14 clientes siguientes pueden usarlo gratis durante un mes; si se lo quedan, pagan solo el 40 % del precio estimado según sus necesidades, y la cuota mensual de mantenimiento la acordamos de antemano."],
  zh: ["零风险", "我们的第一位客户可完全免费获得任意一个代理，作为交换请为我们提供推荐评价。接下来的14位客户可免费试用一个月；如继续使用，只需支付根据您的需求估算价格的40%，每月维护费用提前商定。"],
  it: ["Senza rischi", "Il nostro primo cliente riceve un agente a scelta completamente gratis, in cambio di una referenza. I 14 clienti successivi possono usarlo gratis per un mese; se lo tenete, pagate solo il 40% del prezzo stimato in base alle vostre esigenze, e il canone mensile di manutenzione lo concordiamo in anticipo."],
};

export const offerFor = (lang) => OFFER[(lang || "").toLowerCase().slice(0, 2)] || OFFER.en;
