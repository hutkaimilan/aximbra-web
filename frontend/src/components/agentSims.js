// A szimulációk szerkezete: hány elem, milyen kategóriák, milyen tárgysorok.
// Nincs hálózat és nincs tárolás.
//
// Az elbeszélő szöveg (indítógomb, összegzés, indoklások, audit-napló) NEM itt
// van, hanem az i18n/sims.js-ben, nyelvenként — azt a látogató olvassa. Ami itt
// maradt, az a mintalevelek tárgysora és feladója: magyar mintaadat, ahogy a
// példa postafiók is, és a panel tetején ez ki is van írva.
const sims = {
  "0": {
    total: 40,
    items: [
      {
        t: "Leállt a rendszer, nem tudunk dolgozni",
        s: "Dunavár Logisztika",
        cat: "m"
      },
      {
        t: "Számlán dupla tétel szerepel",
        s: "Kovács és Társa Kft.",
        cat: "m"
      },
      {
        t: "Azonnali szállítás kellene holnapra",
        s: "Pannon Webshop",
        cat: "m"
      },
      {
        t: "Árajánlat 200 db pólóra",
        s: "Rendezvény Bt.",
        cat: "c"
      },
      {
        t: "Együttműködési ajánlat",
        s: "Marketing Zrt.",
        cat: "c"
      },
      {
        t: "Számlázási cím módosítása",
        s: "Tóth Anna",
        cat: "c"
      },
      {
        t: "Hírlevél leiratkozás",
        s: "—",
        cat: "dim"
      },
      {
        t: "Automatikus válasz: szabadságon",
        s: "—",
        cat: "dim"
      },
      {
        t: "Reklám: SEO szolgáltatás",
        s: "—",
        cat: "dim"
      }
    ],
    picks: [
      {
        t: "Leállt a rendszer",
        cat: "m"
      },
      {
        t: "Dupla számlatétel",
        cat: "m"
      },
      {
        t: "Azonnali szállítás",
        cat: "m"
      }
    ]
  },
  "1": {
    total: 12,
    items: [
      {
        t: "Könyvelőiroda, 40 fő",
        s: "Van keret, idén indul, ő dönt",
        cat: "m"
      },
      {
        t: "Gyártó cég, dokumentum-automatizálás",
        s: "Döntéshozó, keret rendben",
        cat: "m"
      },
      {
        t: "Webshop ügyfélszolgálat",
        s: "Tulajdonos dönt, később",
        cat: "c"
      },
      {
        t: "Étterem foglalási rendszer",
        s: "Érdeklődik, nincs időpont",
        cat: "c"
      },
      {
        t: "Kisvállalkozás, hírlevél",
        s: "Kis keret",
        cat: "c"
      },
      {
        t: "Ingatlaniroda, chat",
        s: "Tájékozódik",
        cat: "c"
      },
      {
        t: "Egyetemista, szakdolgozat",
        s: "Nincs cég, ingyen kérné",
        cat: "dim"
      },
      {
        t: "Ügynökség, viszonteladás",
        s: "Nem illeszkedik",
        cat: "dim"
      },
      {
        t: "Álláskeresés",
        s: "Nem ügyfél",
        cat: "dim"
      }
    ],
    picks: [
      {
        t: "Könyvelőiroda, 40 fő",
        cat: "m"
      },
      {
        t: "Gyártó cég",
        cat: "m"
      }
    ]
  },
  "2": {
    total: 18,
    items: [
      {
        t: "Szállítólevél #2043 → számla",
        s: "Dunavár Logisztika",
        cat: "c"
      },
      {
        t: "Szállítólevél #2044 → számla",
        s: "Pannon Webshop",
        cat: "c"
      },
      {
        t: "Bevételezés → készlet",
        s: "Raktár A",
        cat: "c"
      },
      {
        t: "Szállítólevél #2051 → számla",
        s: "összeg eltér",
        cat: "a"
      },
      {
        t: "Bevételezés → készlet",
        s: "Raktár B",
        cat: "c"
      },
      {
        t: "Szállítólevél #2060 → számla",
        s: "mennyiség eltér",
        cat: "a"
      },
      {
        t: "Ismétlődő átvezetések",
        s: "rutin",
        cat: "dim"
      }
    ],
    picks: [
      {
        t: "Szállítólevél #2051",
        cat: "a"
      },
      {
        t: "Szállítólevél #2060",
        cat: "a"
      }
    ]
  },
  "3": {
    total: 6,
    items: [
      {
        t: "Fő versenytárs árlista",
        s: "+12% áremelés",
        cat: "m"
      },
      {
        t: "Jogszabály-adatbázis",
        s: "nincs változás",
        cat: "dim"
      },
      {
        t: "Közbeszerzési portál",
        s: "nincs változás",
        cat: "dim"
      },
      {
        t: "Iparági hírek",
        s: "nincs változás",
        cat: "dim"
      },
      {
        t: "Google Cégprofil",
        s: "nincs változás",
        cat: "dim"
      },
      {
        t: "Piaci elemzések",
        s: "nincs változás",
        cat: "dim"
      }
    ],
    picks: [
      {
        t: "Fő versenytárs",
        cat: "m"
      }
    ]
  },
  "4": {
    total: 340,
    items: [
      {
        t: "Kérdés: Meddig érvényes a garancia?",
        s: "ügyfél",
        cat: "c"
      },
      {
        t: "Áttekintés: teljes dokumentumtár",
        s: "340 oldal",
        cat: "dim"
      },
      {
        t: "Találat: Garancia szabályzat",
        s: "12. o.",
        cat: "c"
      },
      {
        t: "Találat: ÁSZF",
        s: "4. o.",
        cat: "c"
      },
      {
        t: "Találat: Termékadatlap",
        s: "2. o.",
        cat: "c"
      }
    ],
    picks: [
      {
        t: "Garancia szabályzat",
        cat: "c"
      },
      {
        t: "ÁSZF",
        cat: "c"
      },
      {
        t: "Termékadatlap",
        cat: "c"
      }
    ],
    afterBarCat: "a"
  },
  "5": {
    total: 5,
    items: [
      {
        t: "Brief: tavaszi akció, −20%",
        s: "megrendelő",
        cat: "c"
      },
      {
        t: "Minta: előző hírlevél",
        s: "hangnem",
        cat: "dim"
      },
      {
        t: "Minta: termékleírás",
        s: "hangnem",
        cat: "dim"
      },
      {
        t: "Minta: közösségi poszt",
        s: "hangnem",
        cat: "dim"
      }
    ],
    approve: true,
    afterBarCat: "a",
    picks: []
  },
  "6": {
    total: 2,
    items: [
      {
        t: "Agent: Segíthetek? Láttam, a futócipőt nézed.",
        s: "",
        cat: "c"
      },
      {
        t: "Vevő: Bizonytalan vagyok a méretben.",
        s: "",
        cat: "c"
      },
      {
        t: "Agent: 42-es van készleten, ingyenes csere.",
        s: "készlet OK",
        cat: "c"
      },
      {
        t: "Agent: A sportzoknit is ajánlom hozzá, −15%.",
        s: "upsell",
        cat: "c"
      }
    ],
    picks: [
      {
        t: "Futócipő 42",
        cat: "c"
      },
      {
        t: "Sportzokni csomag",
        cat: "c"
      }
    ]
  },
  "7": {
    total: 14,
    items: [
      {
        t: "1–3. oldal: felek, tárgy",
        s: "",
        cat: "c"
      },
      {
        t: "4–7. oldal: díjazás",
        s: "",
        cat: "c"
      },
      {
        t: "8–11. oldal: felmondás",
        s: "",
        cat: "c"
      },
      {
        t: "12–14. oldal: záró rendelkezések",
        s: "",
        cat: "c"
      }
    ],
    picks: [
      {
        t: "Szerződő felek",
        cat: "c"
      },
      {
        t: "Összeg",
        cat: "c"
      },
      {
        t: "Időtartam",
        cat: "c"
      },
      {
        t: "Felmondási idő",
        cat: "c"
      },
      {
        t: "Kötbér",
        cat: "c"
      },
      {
        t: "Illetékesség",
        cat: "c"
      },
      {
        t: "Automatikus megújulás — 30 nap felmondási idő. Naptárba tenni.",
        cat: "m"
      }
    ]
  },
  "8": {
    total: 240,
    items: [
      {
        t: "Bér és járulék",
        s: "",
        cat: "c"
      },
      {
        t: "Bérleti díj",
        s: "",
        cat: "c"
      },
      {
        t: "Alapanyag",
        s: "",
        cat: "c"
      },
      {
        t: "Szoftver-előfizetések",
        s: "+180%",
        cat: "m"
      },
      {
        t: "Marketing",
        s: "",
        cat: "c"
      },
      {
        t: "Egyéb",
        s: "",
        cat: "dim"
      }
    ],
    afterBarCat: "m",
    picks: [
      {
        t: "Új CRM licenc",
        cat: "m"
      },
      {
        t: "Analitika eszköz",
        cat: "m"
      },
      {
        t: "Projektmenedzsment — dupla számlázás",
        cat: "m"
      }
    ]
  },
  "9": {
    total: 60,
    items: [
      {
        t: "8 releváns tapasztalat, pontos profil",
        s: "",
        cat: "c"
      },
      {
        t: "Erős szakmai háttér",
        s: "",
        cat: "c"
      },
      {
        t: "Illeszkedő készségek",
        s: "",
        cat: "c"
      },
      {
        t: "Részben illeszkedő",
        s: "",
        cat: "c"
      },
      {
        t: "Kevés tapasztalat",
        s: "",
        cat: "dim"
      },
      {
        t: "Más szakterület",
        s: "",
        cat: "dim"
      }
    ],
    picks: [
      {
        t: "1. jelölt",
        cat: "c"
      },
      {
        t: "2. jelölt",
        cat: "c"
      },
      {
        t: "3. jelölt",
        cat: "c"
      }
    ]
  },
  "10": {
    total: 2400,
    items: [
      {
        t: "03:12 — szolgáltatás kiesés",
        s: "web-01",
        cat: "c"
      },
      {
        t: "04:41 — szolgáltatás kiesés",
        s: "web-03",
        cat: "c"
      },
      {
        t: "05:20 — ismeretlen adatbázis-hiba",
        s: "db-01",
        cat: "m"
      },
      {
        t: "INFO sorok",
        s: "rutin",
        cat: "dim"
      },
      {
        t: "DEBUG sorok",
        s: "rutin",
        cat: "dim"
      },
      {
        t: "Health-check",
        s: "rendben",
        cat: "dim"
      }
    ],
    picks: [
      {
        t: "03:12 kiesés",
        cat: "c"
      },
      {
        t: "04:41 kiesés",
        cat: "c"
      },
      {
        t: "DB hiba",
        cat: "m"
      }
    ]
  },
  "11": {
    total: 8,
    items: [
      {
        t: "Beérkezés",
        s: "Ajánlatkérés: 500 db egyedi doboz",
        cat: "c"
      },
      {
        t: "Dokumentum-elemző",
        s: "Kinyert: mennyiség, méret, határidő",
        cat: "c"
      },
      {
        t: "Pénzügyi ellenőrzés",
        s: "Anyagköltség + munkadíj kalkulálva",
        cat: "c"
      },
      {
        t: "Ajánlatíró",
        s: "Ajánlat: nettó 1 250 000 Ft",
        cat: "c"
      },
      {
        t: "Független ellenőr ⟲ VISSZAKÜLDVE",
        s: "rossz ÁFA-kulcs (20% → 27%)",
        cat: "m"
      },
      {
        t: "Ajánlatíró (javítás)",
        s: "ÁFA javítva: 27%",
        cat: "c"
      },
      {
        t: "Emberi jóváhagyás",
        s: "Jóváhagyva",
        cat: "a"
      },
      {
        t: "Kiküldés",
        s: "Ajánlat elküldve az ügyfélnek",
        cat: "c"
      }
    ],
    picks: []
  }
};

/** A szerkezet és a felület nyelvén lévő szöveg egyben.
 *  Az indoklások sorrendje kötött: az i18n reasons[i] a picks[i]-hez tartozik. */
export function simFor(kind, text) {
  const base = sims[kind];
  if (!base) return null;
  if (!text) return base;
  const merged = { ...base, ...text };
  if (base.picks) {
    merged.picks = base.picks.map((p, i) => ({ ...p, reason: (text.reasons || [])[i] || '' }));
  }
  return merged;
}

export default sims;
