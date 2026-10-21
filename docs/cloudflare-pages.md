# aximbra.hu a Cloudflare Pages-en

A weboldal (a `frontend/` mappa) statikus: a build után csak fájlokat kell
kiszolgálni. Eddig ezt a Railway `aximbra-web` szolgáltatása csinálta
(`serve -s build`). A Cloudflare Pages ugyanezt ingyen csinálja, és a
Railway-től függetlenül épít és telepít a GitHubról. Ha a Railway telepítése
áll, a weboldal attól még frissül. Ha a Railway teljesen leáll, a weboldal
akkor is betölt; csak az élő demók nem válaszolnak.

Az agentek (aximbra-api, aximbra-sales, aximbra-voice, aximbra-video,
aximbra-webshop) maradnak a Railway-en.

## 1. A projekt létrehozása (egyszer)

Cloudflare irányítópult → **Workers & Pages** → **Create** → **Pages** →
**Connect to Git** → GitHub → `hutkaimilan/aximbra-web`.

| Beállítás | Érték |
|---|---|
| Project name | `aximbra-web` |
| Production branch | `main` |
| Framework preset | `Create React App` |
| Build command | `yarn build` |
| Build output directory | `build` |
| Root directory (Advanced) | `frontend` |

**Environment variables (Production):**

| Név | Érték |
|---|---|
| `NODE_VERSION` | `22` |
| `REACT_APP_BACKEND_URL` | `https://aximbra-api-production.up.railway.app` |
| `REACT_APP_SITE_URL` | `https://aximbra.hu` |

Nincs benne titok: ezek a címek a kész oldal JavaScriptjében amúgy is
nyilvánosan látszanak.

**Save and Deploy.** Kb. 2–3 perc alatt kész; a cím ilyen lesz:
`aximbra-web.pages.dev`.

## 2. Ellenőrzés a pages.dev címen

- a főoldal, nyelvek (`/en`, `/de`, …), `/demo/...`, `/impresszum`,
  `/neked/barmi` mind betölt (az oldalak a JavaScriptből épülnek, a Pages
  minden ismeretlen címre az index.html-t adja);
- az élő demók (e-mail agent, dokumentum-elemző, telefon) a pages.dev címen
  CORS miatt hibázhatnak — ez várható, mert a szerverek csak az aximbra.hu-t
  engedik. A domain átállítása után ugyanaz az eredet, ugyanúgy működnek.

## 3. A domain átállítása

Pages projekt → **Custom domains** → **Set up a custom domain** →
`aximbra.hu`, majd ugyanígy `www.aximbra.hu`. A DNS is a Cloudflare-nél van,
ezért a Cloudflare felajánlja a rekordok átírását: **Activate domain**.

Ez a két rekordot (most: `aximbra.hu` → A 69.46.46.24 és
`www` → CNAME `mmh2yo9s.up.railway.app`) a Pages-re állítja át.

## Visszaállás

A Railway `aximbra-web` szolgáltatás közben tovább fut. Ha bármi nem jó:
Cloudflare DNS → a két rekord vissza a fenti értékekre (vagy a Pages
projektben a custom domain törlése, és a régi rekordok visszaírása). Pár perc.

Néhány nap stabil működés után a Railway `aximbra-web` szolgáltatás leállítható.

## Tudnivalók

- A `frontend/public/_headers` adja a gyorsítótár-szabályokat (a Railway
  figyelmen kívül hagyja).
- Minden `main`-re küldött commit új
  telepítést indít. A korábbi telepítések a Pages-ben megmaradnak, egy
  kattintással visszaállíthatók (**Deployments** → **Rollback**).
- Ingyenes csomag: havi 500 build, fájlonként 25 MB. Az oldal ~20 fájl, 15 MB.
- Ha egy új funkció a weboldalon és egy agentben is változik (pl. a /neked
  oldal és a sales agent), a kettő külön időben élesedik: a weboldal azonnal,
  az agent a Railway telepítése után.
