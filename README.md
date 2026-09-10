# AXIMBRA

Premium dark, neon AI agency marketing site (Hungarian). React (CRA) frontend + FastAPI backend for two live LLM demos.

## Stack
- Frontend: React 19, custom WebGL plasma shader, Lenis smooth scroll, IntersectionObserver reveals.
- Backend: FastAPI. Live demo endpoint `/api/demo/lead`, the in-page Gmail agent under
  `/api/agent/email/*`, and `/api/voice/health` (server-side proxy to the voice service).

## Environment variables

Backend (`backend/.env`):
- `OPENAI_API_KEY` — required for the live demos (Érdeklődő-minősítő, E-mail rendező agent). Never exposed client-side.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `AGENT_REDIRECT_URI`, `FRONTEND_URL` — required by the
  in-page Gmail agent (`/api/agent/email/*`). Without them the agent reports itself as unconfigured.
- `AGENT_SESSION_KEY` — Fernet key for the agent session token. Only needed with more than one replica;
  otherwise a per-process key is generated.
- `MONGO_URL`, `DB_NAME` — present in template but unused (no database is used by this app).
- `CORS_ORIGINS` — comma-separated allowed origins (default `*`). Credentialed CORS is enabled only when
  explicit origins are named; the wildcard default runs without it (the session travels in a header).

Frontend (`frontend/.env`):
- `REACT_APP_BACKEND_URL` — base URL of the backend; all API calls use `${REACT_APP_BACKEND_URL}/api`.
- `REACT_APP_SITE_URL` — the site's own public origin, used for canonical and `og:url`. Without it those
  fall back to the origin the page is served from, which is correct but means a staging deploy
  advertises itself as canonical. Set it once the production domain is live.

## Live demo guardrails (server-side)
- Daily cost ceiling: **4 USD/day** (in-memory, resets daily), shared by the demos and the Gmail agent.
- 8 runs per session, 20 requests per IP per hour, 4000 character input cap.
- Every model response is validated against a strict Pydantic schema; up to 2 retries, then a graceful Hungarian fallback message.

## Local run
- Backend: `uvicorn server:app --host 0.0.0.0 --port 8001` (from `backend/`).
- Frontend: `yarn install && yarn start` (from `frontend/`).

## Railway deployment
- Deploy backend and frontend as two services.
- Set `OPENAI_API_KEY` on the backend service.
- Set `REACT_APP_BACKEND_URL` on the frontend service to the backend's public URL.
- Build the frontend with `yarn build`; serve the static `build/` output.
- No Vercel configuration is included.

## Contact details
`frontend/src/contact.js` is the single source of truth for AXIMBRA's email, phone and city. Import from
there rather than writing an address inline — the site previously carried AXIMBRA's address in some places
and EPISTEME's (a separate project) in others, which read as two different companies. EPISTEME's own
number stays in the case study, where it belongs.

## SEO
`frontend/src/seo.js` sets title, description, canonical, Open Graph, Twitter and JSON-LD per route and per
language; `public/index.html` holds only the Hungarian defaults for the first paint and for crawlers that
do not run JS. The four reference demos are `noindex` — they portray invented businesses and must not
surface in search results or be mistaken for the businesses they depict.

**Still open:** the eight languages all render at the same URL, so there is nothing for `hreflang` to point
at and only one language can be indexed. Fixing that means language-prefixed routes (`/en/...`), which is a
routing change, not a metadata one.

## Demo sites are labelled as demos
Every page under `/demo/` carries a sticky notice saying the business is invented and that nothing typed
into it is sent or stored (`frontend/src/demos/DemoBar.jsx`). The AEGIS contact form never submits
anywhere: it validates, requires an explicit demo-consent checkbox, clears itself and says plainly that
nothing was sent.

## Media
Drop `episteme-demo.mp4`, `episteme-poster.jpg`, and `episteme-hivas.mp3` into `frontend/public/media/`. Until then the case-study section shows dashed-border placeholders and works the moment the files appear.

## Demo websites & client-side routing
Four standalone demo sites live under client-side routes: `/demo/etterem`, `/demo/szalon`, `/demo/rendelo`, `/demo/ugyvedi` (react-router-dom 6.30.1). The AXIMBRA homepage links to them from the "Referenciák" section. Because these are SPA routes, the static server must fall back to `index.html` for unknown paths (SPA fallback). On Railway, serve the built `frontend/build` with a static server that rewrites all non-file requests to `index.html` (e.g. `serve -s build`).

## OPEN QUESTIONS
- Live demo model: defaulted to `gpt-5.4-mini` (cheap, fast classification) via the user's own `OPENAI_API_KEY`. Change in `backend/server.py` if a different model is desired.
- Cost accounting uses a fixed per-call estimate (`EST_COST_PER_CALL_USD`) since exact token cost is not read back; adjust if precise metering is needed.
- Rate-limit / cost state is in-memory (per process). On Railway with multiple replicas each replica tracks its own counters; use a shared store (e.g. Redis) if you scale horizontally.

## Tests
- Backend: `python -m pytest` from `backend/`. The suite is fully offline — the OpenAI call is stubbed, so
  it needs no API key and spends nothing. It covers validation, schema enforcement, the session/cost
  limits, the graceful 502/503 paths, and the Gmail agent's read-only guarantees.
- Frontend: no test suite yet; `yarn build` is the only gate.

## Known external dependencies (migration leftovers)
The project was migrated off the Emergent platform. Two references to that platform's hosts remain:
- `src/demos/Etterem.jsx` and `src/demos/Szalon.jsx` load hero images from
  `static.prod-images.emergentagent.com`. If that CDN disappears, those reference demos show broken
  images. Self-host the images under `frontend/public/` to remove the dependency.
- The dev-only `@emergentbase/visual-edits` package was removed from `package.json`: it was pinned to a
  bare tarball URL (`assets.emergent.sh`), which made every `yarn install` — deploys included — depend on
  that host staying up. `craco.config.js` already handles its absence (visual editing is simply off).
