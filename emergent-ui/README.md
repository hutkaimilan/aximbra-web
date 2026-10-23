# Szelvénymodell (Emergent) — módosított felület

Az Emergentben készült Szelvénymodell felülete, a futó előnézet forrástérképéből visszaállítva
(`src/`, eredetiben a `hutkaimilan/mix` repóban). A szerverkód nem érhető el, ezért az adatokat
továbbra is az Emergent-szerver adja: a `betting-agent` szervere a `/emergent/` alatt szolgálja
ki ezt a felületet, és az `/emergent/api/*` kéréseket továbbítja az `EMERGENT_URL`-re.

## Eltérés az eredetitől

A szerver „Győztesek" és „Gólok" szelvénye helyett **négy „Papírforma szelvény"** (`src/lib/combo.js`),
mindegyik más meccsekből, meccsenként egy (Fogadásépítő-)csoporttal:

- **Alap:** a papírforma-favorit győzelme (TippmixPro-szorzója ≤ 1,70), a gólszám (0,5–7,5 bármelyik vonal)
  és a „mindkét csapat lő gólt", ha egyértelmű.
- **Minden más** (1. és 2. félidő gólszáma, szöglet, lap) csak szinte biztosan: a modell szerint legalább 85%,
  és mindkét csapat utolsó meccseinek legalább 80%-án bejött; csak alaptipp mellé, meccsenként egy.
- **Egyértelmű:** „több mint L", ha a várható érték (az Emergent-modell és a két csapat utolsó 10 meccse
  közül a kisebb) legalább L + ráhagyás (gól 0,4; félidő 0,3; szöglet 1,0; lap 0,7), és mindkét csapat
  meccseinek legalább 60%-án L fölött volt; „kevesebb mint L" hasonlóan (gól 0,6; félidő 0,5; szöglet 1,5;
  lap 1,0 ráhagyás, 70%). Mindkét csapat lő gólt: mindkettő a meccsei 70%-án lőtt és 60%-án kapott gólt, a
  várható góljuk 1,1 / 1,0 fölött. 1,25 alatti szorzójú tipp nem kerül fel; egymásnak ellentmondó tipp
  (a modell szerint együtt jóval ritkább) nem kerül egy csoportba. Minden tipp mellett ott az indoklás.
- Ha a beállított esélyt egyik kombináció sem éri el, a szelvények a legesélyesebb csoportokból állnak,
  narancssárga címkével.
- **Adatok:** várható gól/szöglet/lap és győzelmi esély az Emergent-szervertől, forma az Emergent
  csapatoldaláról, minden vonal a saját TippmixPro-olvasóból (`/api/match-markets`), szorzó és kötéstiltás a
  TippmixPro-tól (`/api/check`). Az esély (két félidős Poisson, szöglet/lap negatív binomiális) csak a
  rangsorhoz és tájékoztatásnak kell; az Emergent-szerver saját visszamérése szerint a Fogadásépítő-esélyek
  átlagosan 7%-kal térnek el.

## Build

```bash
npm install
npm run build   # → ../betting-agent/static/emergent/
```
