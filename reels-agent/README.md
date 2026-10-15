# AXIMBRA Reels-agent

A videós agent új változata, külön szolgáltatásként. **Szakaszokban épül**, mert
az előző próbálkozás azon bukott el, hogy minden egyszerre került élesbe, és az
iPhone-os feltöltés sosem működött.

| Szakasz | Mit tud | Állapot |
|---|---|---|
| 1 | Feltöltés (iCloud-album, fotóválasztó, egyenként) + médiatár + telefonos hibanapló | ez van most |
| 2 | TikTok/Reels montázs a feltöltött anyagból, elemenkénti utasítással | később |
| 3 | Trendfigyelő, narráció, feliratok, 9:16 biztonságos sáv, letöltés | később |
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

## Változók

| Változó | Mire kell |
|---|---|
| `ADMIN_PASSWORD` | a panel HTTP Basic jelszava (a felhasználónév bármi) |
| `MEDIA_DIR` | a tár helye a köteten (alap: `/data/media`) |
| `MAX_UPLOAD_MB` | egy fájl felső mérete (alap: 600) |
| `CLIP_WORKERS` | egyszerre ennyi videót alakít át (alap: 2) |
| `LIBRARY_KEEP` | ennyi elem fölött a 48 óránál régebbiek törlődnek (alap: 500) |
| `ALBUM_MAX_ITEMS` | egy albumból ennyi elem (alap: 300) |

## Tesztek

```
cd reels-agent && python -m pytest tests -q
```
