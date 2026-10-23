# Szelvénymodell (Emergent) — módosított felület

Az Emergentben készült Szelvénymodell felülete, a futó előnézet forrástérképéből visszaállítva
(`src/`, eredetiben a `hutkaimilan/mix` repóban). A szerverkód nem érhető el, ezért az adatokat
továbbra is az Emergent-szerver adja: a `betting-agent` szervere a `/emergent/` alatt szolgálja
ki ezt a felületet, és az `/emergent/api/*` kéréseket továbbítja az `EMERGENT_URL`-re.

## Eltérés az eredetitől

A szerver „Győztesek" és „Gólok" szelvénye helyett egyetlen **„Papírforma + gólok"** (`src/lib/combo.js`),
meccsenként egy (Fogadásépítő-)csoporttal:

- **Papírforma-favorit** (TippmixPro-szorzója ≤ 1,70): ő nyer, és mellé gólszám, ha a két csapat formája
  és a várható gól egyértelműen egy irányba mutat.
- **Favorit nélkül** győztes nélkül: gólszám (0,5–7,5 bármelyik vonal), mindkét csapat lő gólt, 2. félidős
  gólszám — csak ami egyértelmű.
- **Egyértelmű:** „több mint L", ha a várható gól (az Emergent-modell és a két csapat utolsó 10 meccse közül
  a kisebb) legalább L + 0,4, és mindkét csapat meccseinek legalább 60%-án L fölött volt; „kevesebb mint L"
  hasonlóan, 0,6-os ráhagyással és 70%-kal. Mindkét csapat lő gólt: mindkettő a meccsei 70%-án lőtt és 60%-án
  kapott gólt, és a várható góljuk 1,1 / 1,0 fölött. 2. félidő: a 2. félidős gólátlag és a várható gól 55%-a
  közül a kisebb legalább L + 0,3, és mindkét csapat 2. félidejeinek 60%-án L fölött volt. 1,25 alatti szorzójú
  gól-tipp nem kerül fel. Minden tipp mellett ott az indoklás.
- **Adatok:** várható gól és győzelmi esély az Emergent-szervertől, forma az Emergent csapatoldaláról,
  minden gólvonal és a félidők a saját TippmixPro-olvasóból (`/api/match-markets`), szorzó és kötéstiltás a
  TippmixPro-tól (`/api/check`). Az esély (két félidős Poisson-modell) csak a rangsorhoz és tájékoztatásnak
  kell; az Emergent-szerver saját visszamérése szerint a Fogadásépítő-esélyek átlagosan 7%-kal térnek el.

## Build

```bash
npm install
npm run build   # → ../betting-agent/static/emergent/
```
