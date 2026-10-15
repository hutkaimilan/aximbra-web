# AXIMBRA Reels-agent

A videós agent új változata, külön szolgáltatásként. **Szakaszokban épül**, mert
az előző próbálkozás azon bukott el, hogy minden egyszerre került élesbe, és az
iPhone-os feltöltés sosem működött.

| Szakasz | Mit tud | Állapot |
|---|---|---|
| 1 | Feltöltés a fotóválasztóból + médiatár + telefonos hibanapló | **kész, telefonon bizonyítva** |
| 2 | TikTok/Reels montázs a feltöltött anyagból, elemenkénti utasítással, letöltés | **kész** |
| 3 | Narráció (női/férfi/nincs), felirat, trendfigyelő | később |
| 4 | `/api/inbox` és posztolás átvétele a régi agenttől — csak jóváhagyás után | később |

A régi `video-agent/` és az `aximbra-video` szolgáltatás **változatlan**; ez a
mappa egy önálló Railway-szolgáltatás (`aximbra-reels`) saját kötettel.

## A feltöltés: Fotó feltöltése → Fotótár → kijelölés

Egy gomb, a telefon saját fotóválasztója. Amit a telefon átad, azt a felület
**azonnal, egyenként** tölti fel, és a tárban gyűlik — így többször is
rányomhatsz, az elemek összeadódnak.

Amit a felület tesz, hogy ez sok elemnél is átmenjen:

* **nincs `accept` attribútum** a file inputon. A pontos típuslista iPhone-on
  kiszürkíti a HEIC-fotókat és sok videót, és a böngészőt átalakításra
  kényszeríti — pont ettől hasal el. A típust a szerver dönti el
  (`library.decide_type`), a HEIC-et a szerver alakítja JPEG-re.
* **fájlonként külön feltöltés**, 4 MB-os darabokban, darabonkénti
  újrapróbálással: egy hibás elem a többit nem viszi magával, és egy kérés sem
  fut bele a Railway 5 perces korlátjába.
* **a videó átalakítása a kérés után, a háttérben** fut: a feltöltés azonnal
  visszatér, különben az iPhone böngészője kb. egy perc csend után feladja.

Amit a felület **nem** tud megoldani: ha a telefon egyetlen elem előkészítésén
elakad, az **egész kijelölést eldobja**, és az oldal nulla fájlt kap
(`WKFileUploadPanel.mm: _processPickerResults → failureBlock → _cancel`). Ez a
WebKitben van, nem JavaScriptből. Ilyenkor a panel előhozza, mit kell a
telefonon átállítani (Fotók → *Eredetik letöltése és megtartása*; Átvitel →
*Eredetik megtartása*), mert ezek szüntetik meg a leggyakoribb okot: az
iCloudból letöltendő, illetve átalakítandó eredetit.

Vészkijáratként (a lap alján, összecsukva) megmaradt a megosztott iCloud-album
linkje: abból a szerver tölti le az elemeket, a telefon kihagyásával.

## A videó

Egy gomb: **🎬 Videó készítése**. A tár kész elemeiből montázs készül, a
feltöltés sorrendjében, a fotók és a klipek **keverve** (nem a klipek a végén).

* **Ütemre vágva.** A jelenethosszak egy ismétlődő mintát követnek
  (rövid-rövid-hosszú), 0,38 és 2,2 mp között, a kért teljes hosszhoz igazítva.
* **Átmenetek:** kemény vágás, ráközelítés/-húzás és oldalra húzás állóképen,
  villanás minden 5., áttűnés minden 7. vágásnál.
* **Klipnél a legjobb pillanat**, nem az eleje: az ffmpeg `signalstats` szűrője
  képkockánként megadja a mozgást (YDIF) és a részletességet (YSTD), és a
  legerősebb ablak kezdetéről vágunk (`library.hot_moment`).
* **Álló (9:16) videón a szöveg a telefon által levágott széleken belül marad:**
  balra 64 px, jobbra 100 px, fent 100 px a logónak, az alsó negyed szabad
  (`render.SAFE`, és teszt méri meg a képpontokat).
* **Zene nincs rajta** — licenc. A kész videót letöltöd, és a TikTokban teszel
  alá hangot.

### Elemenkénti utasítások

A tárban egy elemre koppintva írhatsz utasítást; a rendező ezeket érti meg
(ékezettel és anélkül is):

| Amit írsz | Mit csinál |
|---|---|
| `ez legyen a nyitókép` | ez lesz az első jelenet |
| `legyen az utolsó` | ez lesz az utolsó |
| `hagyd ki` | nem kerül bele |
| `csak a 3. mp-től`, `from 4s`, `1:05-től` | innen vágunk a klipből |
| `írd rá: AXIMBRA` | felirat a biztonságos sávon belül |
| `maradjon tovább` | hosszabb jelenet |

### Miért nincs benne nyelvi modell

Az előző agent minden gyártásnál a Gemini ingyenes keretére támaszkodott; ha az
elfogyott, nem lett videó. Ez a rendező a te utasításaidból és a fájlok mért
tulajdonságaiból dolgozik, tehát **mindig lefut, kulcs és költség nélkül**. A
szövegíró modell később ráépíthető: csak a jelenetek `text` mezőjét és a
sorrendet kell felülírnia.

## Változók

| Változó | Mire kell |
|---|---|
| `ADMIN_PASSWORD` | a panel HTTP Basic jelszava (a felhasználónév bármi) |
| `MEDIA_DIR` | a tár helye a köteten (alap: `/data/media`) |
| `MAX_UPLOAD_MB` | egy fájl felső mérete (alap: 600) |
| `CLIP_WORKERS` | egyszerre ennyi videót alakít át (alap: 2) |
| `LIBRARY_KEEP` | ennyi elem fölött a 48 óránál régebbiek törlődnek (alap: 500) |
| `ALBUM_MAX_ITEMS` | egy albumból ennyi elem (alap: 300) |
| `VIDEO_DIR` | a kész videók helye a köteten (alap: `/data/videos`) |

## Tesztek

```
cd reels-agent && python -m pytest tests -q
```
