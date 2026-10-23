# Szelvénymodell (Emergent) — módosított felület

Az Emergentben készült Szelvénymodell felülete, a futó előnézet forrástérképéből visszaállítva
(`src/`, eredetiben a `hutkaimilan/mix` repóban). A szerverkód nem érhető el, ezért az adatokat
továbbra is az Emergent-szerver adja: a `betting-agent` szervere a `/emergent/` alatt szolgálja
ki ezt a felületet, és az `/emergent/api/*` kéréseket továbbítja az `EMERGENT_URL`-re.

## Eltérés az eredetitől

- A szerver „Győztesek" és „Gólok" szelvénye helyett egyetlen **„Győztes + gólok"** (`src/lib/combo.js`):
  meccsenként Fogadásépítő-csoport a favorit győzelméből és a vele együtt legvalószínűbb gól-tippből.
  Az együttes esély a szerver győzelmi esélye × a gól-tipp feltételes esélye a meccs
  Dixon–Coles-mátrixából; a szorzót és a kötéstiltást a TippmixPro adja (`/api/check`).
  Az Emergent-szerver saját visszamérése szerint a Fogadásépítő-esélyei átlagosan 7%-kal térnek el
  a valóságtól, ezért ennek a szelvénynek a becsült esélye is pontatlanabb a többinél.

## Build

```bash
npm install
npm run build   # → ../betting-agent/static/emergent/
```
