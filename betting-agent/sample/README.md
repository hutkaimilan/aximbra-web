# Minták

| Fájl | Mi ez |
|---|---|
| `odds_sample.json` | **Nem TippmixPro-adat.** Kitalált meccsek The Odds API formátumban, a parancssoros agent `--offline` módjához. |
| `tippmix_ws_bundesliga.json` | Valódi TippmixPro WebSocket-válasz (2026-10-21): Bundesliga 1., bajnokság-áttekintő, piaccsoportok `1380–1390`. |
| `tippmix_ws_match_groups.json` | Valódi válasz egy **két nappal később** kezdődő meccsre (VfB Stuttgart – Mönchengladbach): a meccs piaccsoportjai, a `Szogletek` és `Lapok` csoport. |
| `tippmix_ws_match_bl.json` | Valódi válasz egy **aznap** kezdődő meccsre (Como – Manchester Utd., BL): `Szogletek`, `Lapok`, `Hendikep`, `Felido` csoport. |

Mindegyik `/sports#initialDump` válasz rekordlistája (`MATCH`, `MARKET`, `OUTCOME`,
`MARKET_OUTCOME_RELATION`, `BETTING_OFFER`, …), változtatás nélkül.

## Amit a mintákból tudunk

**Bajnokság-áttekintő** (`tournament-aggregator-groups-overview/<bajnokság>/default-event-info/BOTH/<csoportok>`):
- Csak az alappiacokat adja: 1X2, kétesély, gólszám, mindkét csapat szerez gólt, DNB, európai
  hendikep (`bettingTypeId` 8), és félidős 1X2 / gólszám (`eventPartId` 5 = 1. félidő, 3 = rendes játékidő).
- **Szöglet (1386) és lap (1387) nincs benne**, akkor sem, ha a kérés tartalmazza őket.

**Meccs összes piaca** (két lépés):
1. `/sports/2901/hu/event/<meccsId>/market-groups` → `MARKET_GROUP` rekordok, `groupKey`:
   `Fogadaskeszito`, `NEPSZERU`, `Golok`, `Szogletek`, `Markets_Insights`, `Hendikep`, `Flash`,
   `Gyorspiacok`, `Jatekos`, `Statisztikak`, `Lapok`, `Felido`, `Kombi`.
2. `/sports/2901/hu/<meccsId>/match-odds/market-group/<groupKey>` → a csoport piacai és szorzói.

**A szöglet- és lappiacok csak a meccs napja körül nyílnak meg.** Két nappal előtte a `Szogletek`
csoport üres, a `Lapok`-ban csak játékoslapos piac van; aznap már van szögletszám (`bettingTypeId`
156, 118, 49), csapat-szöglet, szöglet-hendikep (138, 182), lapszám (185, 186), „mindkét csapat
kap lapot” (859), kiállítás (136). Szöglet- vagy lapszelvény ezért csak a meccsnapon készülhet.

**Hendikep — előjel-csapda:**
- Európai (háromesélyes, `bettingTypeId` 8): `Handicap Winner` home −1,0 / away +1,0, de a
  `Handicap Draw` kimenetel `paramFloat1`-je **+1,0** (nem a hazai vonal!). A meccsek egy részén
  a favorit a vendég (home +1,0 / away −1,0). A vonalat mindig a hazai `Handicap Winner`
  kimenetelből vedd, ne a döntetlenből.
- Ázsiai (`bettingTypeId` 48, `Handicap Winner With Money Back On Draw`): negyedes vonalak is
  (pl. −0,75, +1,25). Ezeknél a tét fele az egyik, fele a szomszédos vonalra megy (fél nyerés /
  fél visszajár), ezt a várható érték számításánál külön kell kezelni.

## ESPN

`espn_scoreboard_esp1_20261019.json`: valódi ESPN napi eredménylista (La Liga, 2026-10-19, Getafe –
Rayo Vallecano 1–1), a kiértékelő tesztjéhez; a meccsrekordból csak az állapot, a csapatok, az
eredmény, a statisztika (`wonCorners`) és az események (`details`: gólok perccel, sárga és piros
lapok) maradt meg.
