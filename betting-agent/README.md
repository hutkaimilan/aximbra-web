# Fogadáskészítő agent (TippmixPro)

Bajnokok Ligája, Európa-liga, Premier League, La Liga és Bundesliga meccseire
kiszámolja a **valós esélyeket**, megmondja tippenként a **legkisebb
Tippmix-szorzót**, amelynél még megéri, és a beírt Tippmix-szorzókból a
TippmixPro feltételeinek megfelelő **szelvényt** rak össze téttel együtt.

Csak a Python standard könyvtárát használja, külső csomag nem kell.

## Amit tudnod kell, mielőtt használod

- **A Tippmix árrése magas.** A nagy meccseken jellemzően 6–10% az 1X2-n, egy
  éles irodánál (Pinnacle) 2–3%. Ezért a legtöbb tipp a Tippmixen hosszú távon
  veszteséges, és az agent a legtöbb napon azt fogja mondani, hogy kevés vagy
  semmi nem éri meg. Ez nem hiba, hanem az eredmény.
- **A kötés a veszteséget is szorozza.** Öt, egyenként −8%-os láb együtt kb.
  −34%. Ezért a kötésbe csak olyan láb kerül, amely egyenként is eléri a
  megkövetelt előnyt.
- **Az esély becslés, nem tudás.** A forrása a legélesebb piac záró előtti ára.
  Ez a legjobb nyilvános becslés, de a meccs kimenetele ettől még véletlen:
  pozitív várható értékű szelvény is sokszor egymás után veszíthet.

## Hogyan számol

1. **Szorzók** a [The Odds API](https://the-odds-api.com)-ból: tíz iroda, köztük
   Pinnacle, Betfair-tőzsde, Matchbook (`odds_api.py`).
2. **Árrés eltávolítása** hatványmódszerrel, amely kezeli a favourite–longshot
   torzítást (`fair.py`). Ha van Pinnacle, az az irányadó; ha nincs, a többi éles
   piac átlaga; ha az sincs, az összes iroda mediánja, „alacsony" bizalommal és
   +2% megkövetelt előnnyel.
3. **Poisson-gólmodell a piachoz illesztve** (`poisson.py`): várható gólok,
   legvalószínűbb eredmények, és olyan piacok, amelyeket nem kértünk le (mindkét
   csapat gólt szerez, 1,5 / 3,5 gól). Ezeket „modell" forrásúnak jelöli, és 6%
   előnyt követel hozzájuk 3% helyett.
4. **Szelvény** (`slip.py`): várható érték, negyed Kelly szerinti tét, és a
   korlátok:
   - fogadásonként max. a keret 2%-a, tervenként összesen max. 5%-a,
   - TippmixPro: min. tét, max. tét, max. nyeremény, max. eseményszám, kötés
     (egyes esemény csak N-es kötésben),
   - egy meccsről egy szelvényen egy tipp, két kötés nem épít ugyanarra a meccsre,
     egyeseknél meccsenként a legjobb tipp.

## Beállítás

```bash
export ODDS_API_KEY=...   # ingyenes kulcs: https://the-odds-api.com (havi 500 kredit)
```

Egy teljes futás 10 kredit (5 bajnokság × 2 piac), az ingyenes keretből ~50
futás jön ki havonta. 30 percen belüli újrafuttatás a gyorsítótárból megy, nem
fizet újra.

## Használat

```bash
cd betting-agent

# 1. Elemzés: szorzók letöltése, esélyek, kitöltendő táblázat
python3 agent.py elemzes
#    → out/elemzes-<dátum>.md és out/tippmix_kitoltendo.csv

# 2. A TippmixPro appban nézd meg a szorzókat. A táblázat tippmix_szorzo
#    oszlopába csak oda írj, ahol a Tippmix legalább a min_szorzo-t adja.
#    Ha egy esemény csak kötésben játszható, a kotes oszlopba írd a számot.

# 3. Szelvény a kitöltött táblázatból (API-hívás nélkül)
python3 agent.py szelveny --tabla out/tippmix_kitoltendo.csv --keret 50000

# Célszorzós kötés (csak értékes lábakból):
python3 agent.py szelveny --tabla out/tippmix_kitoltendo.csv --keret 50000 --cel-szorzo 5
```

Kulcs nélkül, kitalált mintameccsekkel:

```bash
python3 agent.py elemzes --offline sample/odds_sample.json
```

Egyéb kapcsolók: `--liga soccer_epl soccer_spain_la_liga` (csak ezek),
`--negativ-is` (a célszorzóhoz negatív lábat is felhasznál — megmutatja, mennyit
veszítesz vele), `--regi-is` (6 óránál régebbi elemzésből is számol).

## Miért nem tölti le a Tippmix-szorzókat?

A TippmixPro-nak nincs nyilvános API-ja; a weboldal lekaparása a felhasználási
feltételekbe ütközhet, és bármikor eltörik. A csapatnevek automatikus
párosítása (angol forrás ↔ magyar Tippmix-név) pedig csendben rossz meccshez
rendelhetne egy szorzót. A kitöltendő táblázat soronként azonosít, így ez nem
fordulhat elő, és a második lépés nem költ kvótát.

## A TippmixPro-szabályok

Alapértékek (`config.py`), környezeti változóval felülírhatók:

| Szabály | Érték | Változó |
|---|---|---|
| Minimális tét kombinációnként | 200 Ft | `TIPPMIX_MIN_STAKE` |
| Maximális tét | 100 000 Ft | `TIPPMIX_MAX_STAKE` |
| Maximális nyeremény fogadásonként | 1 000 000 Ft | `TIPPMIX_MAX_PAYOUT` |
| Események száma egy szelvényen | max. 20 | `TIPPMIX_MAX_EVENTS` |

Ezek nyilvános összefoglalókból származnak (2018-as részvételi szabályzat,
2026-os cikkek), nem a Szerencsejáték Zrt. friss szabályzatából. Ahol a források
eltértek (min. tét 100 vagy 200 Ft; max. nyeremény 1 vagy 2 millió Ft), a
szigorúbbat választottuk: így legfeljebb kimarad egy szelvény, de nem javasol
olyat, amit a rendszer nem fogad el. Érdemes egyszer a hivatalos szabályzatban
ellenőrizni.

A stratégia változói: `BET_MIN_EDGE_MARKET` (0.03), `BET_MIN_EDGE_MODEL` (0.06),
`BET_KELLY_FRACTION` (0.25), `BET_MAX_BET_SHARE` (0.02), `BET_MAX_DAILY_SHARE`
(0.05), `BET_MAX_COMBO_LEGS` (4), `BET_MAX_AGE_HOURS` (6), `BET_DAYS_AHEAD` (4).

## Amit nem csinál

- **Élő fogadás**: a szorzók percről percre mozognak, ez a folyamat ahhoz lassú.
- **Hírek, sérülések külön elemzése**: az éles piac ára ezeket általában
  órákon belül tartalmazza, gyorsabban, mint bármilyen hírösszefoglaló. A
  kezdőcsapat kihirdetése (kezdés előtt ~1 óra) viszont mozgathatja: ezért
  érdemes az elemzést a kezdés előtt nem sokkal futtatni.
- **Garancia**: nincs. A tétkorlátok azért vannak, hogy egy rossz sorozat ne
  vigye el a keretet.

A Szerencsejáték Zrt. oldalán befizetési és időkorlát is beállítható.

## Tesztek

```bash
python3 -m pytest -q tests
```
