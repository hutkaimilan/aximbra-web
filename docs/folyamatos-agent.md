# A folyamatos agent — hol tart, és mi hiányzik

A nyilvános demó és ez a rendszer **nem ugyanaz**, és szándékosan nem is
kapcsolható össze. A demó semmit nem tárol; ez tokent őriz, hogy két óra múlva
magától megnézhesse a postafiókot. Aki ezt megveszi, a saját telepítését kapja,
saját adatkezelési tájékoztatóval.

## Ami elkészült (`backend/continuous/`)

| Fájl | Mit csinál |
| --- | --- |
| `store.py` | SQLite-tár: fiókok, **titkosított** refresh token, `history_id`, és levelenként a megállapítás |
| `worker.py` | esedékesség, első pásztázás öt hónapra, utána csak az új, osztályozás, hibakezelés |
| `gmail.py` | friss hozzáférés a tárolt tokenből, `history`-alapú növekményes lekérdezés, levélbetöltés |

17 teszt fedi, köztük: a token nem olvasható ki a fájlból, a levéltörzs nem
kerül az adatbázisba, ugyanaz a levél nem osztályozódik kétszer, elfogyott napi
keretnél a könyvjelző nem lép előre, visszavont hozzáférés után a fiók megáll.

## Ami hiányzik ahhoz, hogy éles legyen

1. **Offline OAuth.** A demó `access_type=online`-nal kér jogot, tehát nincs
   refresh token. Ehhez külön beleegyező folyamat kell (`access_type=offline`,
   `prompt=consent`), és a Google-nál az alkalmazás verifikációja.
2. **Az ügyfél felülete.** Bejelentkezés, a megállapítások listája, kereső,
   „lecsatlakozom" gomb. Ma csak a motor van meg.
3. **Tartós lemez.** A konténer fájlrendszere újraindításkor eltűnik: a
   `CONTINUOUS_DB_PATH` egy Railway-volume-ra kell mutasson.
4. **Kulcskezelés.** A `CONTINUOUS_KEY` elvesztése annyi, hogy minden fióknak
   újra kell csatlakoznia. Mentés kell róla, az adatbázistól külön helyen.
5. **Saját adatkezelési tájékoztató.** Az ittani azt állítja, hogy nem tárolunk
   semmit — ez a rendszer ezt megszegné. Külön szöveg kell, külön adatkezelővel.

## Beállítások

| Változó | Alapérték | Mit jelent |
| --- | --- | --- |
| `CONTINUOUS_ENABLED` | `false` | enélkül a motor el sem indul |
| `CONTINUOUS_KEY` | — | Fernet-kulcs a tokenek titkosításához; hiányában hibával leáll |
| `CONTINUOUS_DB_PATH` | `/data/continuous.sqlite3` | tartós lemezen legyen |
| `CONTINUOUS_INTERVAL_MINUTES` | `120` | kétóránként |
| `CONTINUOUS_BACKFILL_MONTHS` | `5` | az első pásztázás mélysége |
| `CONTINUOUS_MAX_PER_RUN` | `120` | egy futásban ennyi levél |

## Amit a rendszer nem csinál, és nem is fog

Nem ír a postafiókba, nem címkéz, nem töröl, és nem küld levelet. Az olvasási
hatókört egy teszt is őrzi: ha bárki `gmail.compose`-t vagy küldést írna ebbe a
modulba, a suite elbukik.
