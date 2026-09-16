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

/** A tájékoztató hatálybalépése. Frissítsd, ha érdemi változás történik. */
export const LEGAL_UPDATED = "2026. szeptember 16.";

/** Adatfeldolgozók — mind a kódból, nem emlékezetből. */
export const PROCESSORS = [
  {
    name: "Railway Corp.",
    role: "Tárhely és futtatókörnyezet (a weboldal és az API)",
    where: "Amszterdam, Hollandia (EU)",
  },
  {
    name: "OpenAI, L.L.C.",
    role: "Nyelvi modell — a demókban beküldött szövegek feldolgozása",
    where: "Egyesült Államok",
  },
  {
    name: "Google LLC",
    role: "Gmail API — csak akkor, ha te magad csatlakoztatod a fiókodat",
    where: "Egyesült Államok",
  },
  {
    name: "Twilio Inc.",
    role: "Az oldalon szereplő telefonszám: hívásfogadás és átkapcsolás",
    where: "Egyesült Államok",
  },
  {
    name: "Resend (Plus Five Five, Inc.)",
    role: "A hívás-összefoglaló e-mail kiküldése az adatkezelőnek",
    where: "Egyesült Államok",
  },
];
