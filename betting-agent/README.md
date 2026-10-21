# Fogadáskészítő agent (TippmixPro)

Bajnokok Ligája, Európa-liga, Premier League, La Liga, Bundesliga és portugál
bajnokság. Két felülete van:

- **Weboldal** (`web.py`): a TippmixPro aktuális szorzói sorozatonként külön,
  meccsenként magyar elemzéssel (ki nyer, várható gólok, lő-e mindkét csapat),
  szelvénykészítő Fogadásépítős változatokkal, szelvény a TippmixPro saját
  kötéstiltás-ellenőrzésével, és kattintható csapatok a korábbi eredményeikkel.
- **Parancssor** (`agent.py`): ugyanaz a számolás, kézzel kitöltött táblázattal.

## Weboldal

| Mit mutat | Honnan |
|---|---|
| Szorzók: 1X2, kétesély, gólszám 2,5, mindkét csapat gólt szerez, DNB | a TippmixPro saját felülete (`sportsapi.tippmixpro.hu`, ugyanaz a csatorna, amit a böngésző használ) |
| Kötéstiltás, Fogadásépítő-szorzó egy meccsen belül, minimális tét | a TippmixPro szelvény-ellenőrzője (`bettingOptionsV2`) |
| Csapatok korábbi meccsei minden sorozatból | ESPN nyilvános JSON |
| Valós esély, várható érték, értékkereső | The Odds API (Pinnacle, Betfair-tőzsde) — opcionális |

### Szelvénykészítő

A fő fülön tetszőleges sorozatokból (egy, több vagy mind), minden sorozat
fülén csak abból a sorozatból. Kiválasztható a kezdőnap és hogy 1, 2 vagy 3
napra szóljon (budapesti idő szerint); alapból az első olyan nap, ahol legalább
3 meccs van. Öt stratégia, mindegyik a legesélyesebb meccsekből (`builder.py`):

| Változat | Meccsenként |
|---|---|
| Biztos tippek | a legvalószínűbb kétesély (nyer vagy döntetlen) |
| Győztesek | a favorit győzelme |
| Győztes + gólok | győztes + a vele együtt legvalószínűbb gólszám (Fogadásépítő) |
| Gólos szelvény | győztes nélkül: a legvalószínűbb gólszám + „mindkét csapat szerez gólt” pár |
| Teljes Fogadásépítő | győztes + gólszám + „mindkét csapat szerez gólt” |
| Bármiből a legbiztosabb | a legnagyobb (visszamért) esélyű tipp bármelyik ellenőrzött piacból — kétesély, gólszám, hendikep, 1. félidő… —, legalább 1,20-as szorzóval |

Piacok a TippmixPro-ról: 1X2, kétesély, gólszám, mindkét csapat szerez gólt, DNB, háromesélyes
hendikep (a vonal mindig a hazai kimenetelből: a döntetlen paramétere a vendég vonala), 1X2 és
gólszám az 1. félidőre (a félidős gólvárható érték a visszamért félidős aránnyal). Szöglet és lap
még nincs: ezek csak a meccsnapon nyílnak meg, és csapatszintű modellt igényelnek (lásd sample/README.md).

Esély-mód (`resolve_min_prob`):

| Mód | Célszorzó nélkül | Célszorzóval |
|---|---|---|
| Automatikus (60%) — alap | a legnagyobb szorzó, amelynek esélye legalább 60% | a legnagyobb esélyű szelvény, amely eléri a célt (60% alatt narancssárga címke) |
| legalább 70% / 80% | a legnagyobb szorzó a küszöb fölött | csak ha a cél és a küszöb együtt teljesíthető |
| 60% alatti is | az n legesélyesebb csoport | a legnagyobb esélyű szelvény, amely eléri a célt |

A választás pontos keresés a legesélyesebb 10 csoport összes (legfeljebb 6 meccses)
kombinációján, nem mohó hozzáadás: az egy utolsó nagy lábbal jócskán túllőne a célon.

1,10 alatti szorzójú csoport nem kerül szelvényre: szinte semmit nem ad hozzá,
csak egy újabb helyet, ahol a szelvény elbukhat.

Az egy meccsen belüli tippek együttes esélyét a meccs gólmodelljének
eredménymátrixából számolja (a tippek összefüggenek), a csoport szorzóját a
TippmixPro Fogadásépítője adja. Célszorzóval addig vesz hozzá meccset, amíg el
nem éri (legfeljebb 6). Egy csapat egy szelvényen csak egyszer szerepel, és
minden szelvényt a TippmixPro kötéstiltás-ellenőrzése jóváhagy; tiltott pár
esetén a gyengébb csoportot a következő legesélyesebbel cseréli.

Kulcs nélkül az esélyek a TippmixPro saját szorzóiból jönnek (árrés nélkül),
ezért a várható érték a Tippmix árrése miatt negatív — a felület ki is írja.

### Visszamérés és kalibráció („Mennyire pontos?” fül)

`calibrate.py` a football-data.co.uk ingyenes táblázataiból (PL, La Liga, Bundesliga, portugál
liga; záró piaci átlagszorzók és eredmények) minden régi meccsre ugyanazt számolja, mint élesben
az oldal, és összeveti a valós eredménnyel. A korrekciót (isotonic regresszió) a 2024/25-ös
évadon illeszti, a 2025/26-oson méri; csak ott használja, ahol a külön évadon valóban javít.
Egy piac (és a hozzá tartozó szelvénystratégia) akkor ajánlható, ha a mérési évadon az átlagos
eltérés legfeljebb 3% — különben a szelvénykészítő kikapcsolja. Az eredmény a `calibration.json`,
amit évadonként egyszer újra kell futtatni:

```bash
python3 calibrate.py   # ~30 s, a CSV-ket az out/football-data/ alá menti
```

**Fontos:** a TippmixPro-csatorna nem dokumentált, nyilvános API. Bármikor
megváltozhat; ilyenkor az oldal a legutóbbi sikeres adatot mutatja „elavult"
jelzéssel és kiírja a hibát. Csak kérésre és 3 perces gyorsítótárral kérdez,
vagyis annyi terhelést okoz, mint egy böngésző. A fogadást a TippmixPro-n kell
leadni.

### Erőforrás

Egy Python-folyamat (standard könyvtár + `websockets`), nincs böngésző,
adatbázis vagy nyelvi modell. ~40 MB memória; Railway-en alvó módban fut,
forgalom nélkül nem fogyaszt. Az első kérés ébredés után néhány másodperc.

### Környezeti változók

| Változó | Kötelező | Mire |
|---|---|---|
| `APP_PASSWORD` | nem | belépési jelszó; üresen vagy hiányában az oldal jelszó nélkül, bárki számára nyitott |
| `ODDS_API_KEY` | nem | valós esély és értékkereső (ingyenes: the-odds-api.com) |
| `ODDS_CACHE_MINUTES` | nem | ennyi percig nem kér újra a The Odds API-tól (alap: 120) |
| `TIPPMIX_CACHE_SECONDS` | nem | TippmixPro-gyorsítótár (alap: 180) |
| `APP_SECRET` | nem | munkamenet-kulcs; alapból a jelszóból származik |

Egy The Odds API-frissítés 12 kredit (6 sorozat × 2 piac). Az ingyenes havi 500
kreditből a 2 órás gyorsítótárral bőven kitart, de egy újraindulás (telepítés,
ébredés alvásból) törli a gyorsítótárat.

### Helyi futtatás

```bash
pip install -r requirements.txt
APP_PASSWORD=valami python3 web.py      # http://localhost:8080
```

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

## Parancssor

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

## Csapatnév-egyeztetés

A TippmixPro, az ESPN és a The Odds API másként írja a neveket („Bayern
München" / „Bayern Munich", „1. FC Köln" / „FC Cologne"). Meccset ezért mindig
a kezdési idő és mindkét csapatnév együtt párosít (`names.py`): ugyanabban a
percben két meccs csapatai nem hasonlítanak egymásra. Ahol nincs biztos pár, ott
nincs valós esély — azt a tippet nem nevezi értékesnek.

## A TippmixPro-szabályok

Alapértékek (`config.py`), környezeti változóval felülírhatók:

| Szabály | Érték | Változó |
|---|---|---|
| Minimális tét kombinációnként | 100 Ft (a weboldal a TippmixPro-tól kérdezi) | `TIPPMIX_MIN_STAKE` |
| Maximális tét | 100 000 Ft | `TIPPMIX_MAX_STAKE` |
| Maximális nyeremény fogadásonként | 1 000 000 Ft | `TIPPMIX_MAX_PAYOUT` |
| Események száma egy szelvényen | max. 20 | `TIPPMIX_MAX_EVENTS` |

A minimális tétet és a kötéstiltást a TippmixPro maga adja vissza. A többi szám
nyilvános összefoglalókból származik (2018-as részvételi szabályzat, 2026-os
cikkek); ahol a források eltértek (max. nyeremény 1 vagy 2 millió Ft), a
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
