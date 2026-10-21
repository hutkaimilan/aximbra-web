/**
 * Az adatkezelő azonosítása — egy helyen.
 *
 * Ez a kettő (impresszum, adatkezelési tájékoztató) az a két oldal, ahol egy
 * elírás nem kozmetikai hiba, ezért az adatok nem másolódnak szét a
 * komponensek közé. Az e-mail és a városnév a contact.js-ből jön, hogy a
 * lábléc és a jogi oldalak ne tudjanak elcsúszni egymástól.
 */
export const CONTROLLER = {
  // Természetes személy, nem gazdasági társaság. A tájékoztató ezt kimondja,
  // mert egy „Kft." látszatát kelteni pont az a bizalmi hiba lenne, amit ezek
  // az oldalak orvosolni hivatottak.
  name: "Hutkai Milán",
  addressLine: "Nagysándor József utca 16.",
  postcode: "1195",
  city: "Budapest",
  country: "Magyarország",
  // Adószám / nyilvántartási szám: amint van, ide kerül, és a két oldalon
  // magától megjelenik. Üresen hagyva egyik oldal sem állít róla semmit.
  taxNumber: "",
};

export const CONTROLLER_ADDRESS =
  `${CONTROLLER.postcode} ${CONTROLLER.city}, ${CONTROLLER.addressLine}, ${CONTROLLER.country}`;

/** Ugyanaz a cím az angol tájékoztatóhoz, angol címsorrenddel. */
export const CONTROLLER_ADDRESS_EN =
  `${CONTROLLER.addressLine}, ${CONTROLLER.postcode} ${CONTROLLER.city}, Hungary`;

/** Ugyanaz a cím a német oldalakhoz (Impressum, Datenschutzerklärung). */
export const CONTROLLER_ADDRESS_DE =
  `${CONTROLLER.addressLine}, ${CONTROLLER.postcode} ${CONTROLLER.city}, Ungarn`;

/** A tájékoztató hatálybalépése. Frissítsd, ha érdemi változás történik. */
export const LEGAL_UPDATED = "2026. október 21.";
export const LEGAL_UPDATED_EN = "21 October 2026";
export const LEGAL_UPDATED_DE = "21. Oktober 2026";

/** Adatfeldolgozók — mind a kódból, nem emlékezetből. Az angol oszlopok az
 *  angol fordításhoz kellenek; a két nyelv egy sorban áll, hogy ne csússzon el. */
export const PROCESSORS = [
  {
    name: "Railway Corp.",
    role: "Futtatókörnyezet: az API és az agentek (bemutatók, telefon, űrlapok)",
    where: "Amszterdam, Hollandia (EU)",
    roleEn: "Runtime: the API and the agents (demos, phone, forms)",
    whereEn: "Amsterdam, the Netherlands (EU)",
    roleDe: "Laufzeitumgebung: API und Agenten (Demos, Telefon, Formulare)",
    whereDe: "Amsterdam, Niederlande (EU)",
  },
  {
    name: "Cloudflare, Inc.",
    role: "A weboldal kiszolgálása és a domain névfeloldása (DNS)",
    where: "Egyesült Államok; a kiszolgálás a látogatóhoz legközelebbi adatközpontból",
    roleEn: "Serving the website and the domain's name resolution (DNS)",
    whereEn: "United States; served from the data centre nearest the visitor",
    roleDe: "Auslieferung der Website und Namensauflösung der Domain (DNS)",
    whereDe: "Vereinigte Staaten; Auslieferung aus dem nächstgelegenen Rechenzentrum",
  },
  {
    name: "Google LLC (Gemini API)",
    role: "Nyelvi modell — a demókban beküldött szövegek, a feltöltött dokumentumok és a csatlakoztatott levelek feldolgozása",
    where: "Egyesült Államok",
    roleEn: "Language model (Gemini API) — processing the text submitted to the demos, uploaded documents and the connected emails",
    whereEn: "United States",
    roleDe: "Sprachmodell (Gemini-API) — Verarbeitung der in den Demos eingegebenen Texte, hochgeladener Dokumente und der verbundenen E-Mails",
    whereDe: "Vereinigte Staaten",
  },
  {
    name: "Google LLC",
    role: "Gmail API — csak akkor, ha te magad csatlakoztatod a fiókodat",
    where: "Egyesült Államok",
    roleEn: "Gmail API — only if you connect your account yourself",
    whereEn: "United States",
    roleDe: "Gmail-API — nur, wenn Sie Ihr Konto selbst verbinden",
    whereDe: "Vereinigte Staaten",
  },
  {
    name: "Twilio Inc.",
    role: "Az oldalon szereplő telefonszám: hívásfogadás és átkapcsolás",
    where: "Egyesült Államok",
    roleEn: "The phone number on the site: answering and forwarding calls",
    whereEn: "United States",
    roleDe: "Die Telefonnummer auf der Website: Anrufannahme und Weiterleitung",
    whereDe: "Vereinigte Staaten",
  },
  {
    name: "Resend (Plus Five Five, Inc.)",
    // Az ajánlatkérő űrlap is ezen megy, amint a Resend-kulcs be van állítva:
    // a Railway a Pro csomag alatt nem enged ki SMTP-t.
    role: "E-mailek kiküldése az adatkezelőnek: hívás-összefoglaló és az ajánlatkérő űrlap üzenete",
    where: "Egyesült Államok",
    roleEn: "Sending emails to the controller: call summaries and enquiry form messages",
    whereEn: "United States",
    roleDe: "Versand von E-Mails an den Verantwortlichen: Anrufzusammenfassungen und Nachrichten aus dem Anfrageformular",
    whereDe: "Vereinigte Staaten",
  },
];
