# AXIMBRA

Premium dark, neon AI agency marketing site (Hungarian). React (CRA) frontend + FastAPI backend for two live LLM demos.

## Stack
- Frontend: React 19, custom WebGL plasma shader, Lenis smooth scroll, IntersectionObserver reveals.
- Backend: FastAPI. Live demo endpoint `/api/demo/lead`, the in-page Gmail agent under
  `/api/agent/email/*`, and `/api/voice/health` (server-side proxy to the voice service). A mailbox pass
  reads up to `MAX_EMAILS` (50) emails, `RUN_CONCURRENCY` (5) at a time — sequentially it would be 50 Gmail
  round trips plus 50 model calls end to end.

## The demo and the product are not the same thing

The page at `/demo/email-agent` is a demo, and its limits are deliberate: the run
lives in memory, expires after 30 minutes, and every connection starts from zero.
The system that is sold is the opposite on purpose — an app or site only the
customer can reach, with no automatic disconnect, a pass every two hours, and a
five-month look-back on the first connection. The page says so (`agent.product`
in `frontend/src/i18n/agent.js`), because a visitor who is not told will read the
demo's limits as the product's.

**None of that per-customer machinery is in this repository.** It needs accounts,
stored Google refresh tokens, a database and a scheduler, and it inverts the
privacy promise this site makes about the demo — so it is built per customer,
with its own privacy notice, not bolted onto the public demo.

## Environment variables

Backend (`backend/.env`):
- `OPENAI_API_KEY` — required for the live demos (Érdeklődő-minősítő, E-mail rendező agent). Never exposed client-side.
- `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `AGENT_REDIRECT_URI`, `FRONTEND_URL` — required by the
  in-page Gmail agent (`/api/agent/email/*`). Without them the agent reports itself as unconfigured.
- `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `LEAD_TO`, `LEAD_FROM` — the contact form
  (`/api/contact`). **Without all of `SMTP_HOST`, `SMTP_USER`, `SMTP_PASSWORD` and a recipient the form does
  not appear at all**: `/api/contact/status` reports `configured: false` and the page keeps the mailto and
  phone buttons. That is deliberate — a form that says "thanks, we'll be in touch" while the mail goes
  nowhere loses customers silently. `LEAD_TO` defaults to `SMTP_USER`, `LEAD_FROM` too. Port 465 uses
  implicit TLS, anything else STARTTLS.
  With a Gmail account: turn on 2-step verification, create an *app password*
  (myaccount.google.com/apppasswords), then set `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=465`,
  `SMTP_USER=<the address>`, `SMTP_PASSWORD=<the 16-character app password>`. The regular account
  password will not work, and the app password is not the account password — it can be revoked on its own.
  **On Railway below the Pro plan outbound SMTP is blocked**, so this path cannot deliver there. The API
  probes the SMTP port at boot and keeps the form hidden if it is closed (the log says so).
- `RESEND_API_KEY`, `RESEND_FROM`, `LEAD_TO` — the contact form over Resend's HTTPS API, which works on
  every Railway plan and **takes precedence over SMTP** when the key is set. Without a verified domain
  Resend only delivers to the Resend account's own address, so `LEAD_TO` must be that address.
  `RESEND_FROM` defaults to `AXIMBRA <onboarding@resend.dev>`. The voice agent already holds a key and
  its owner's address (`RESEND_API_KEY`, `NOTIFY_EMAIL` on `aximbra-voice`).
- `AGENT_PUBLIC` — whether strangers may hand the agent their mailbox. Defaults to `true`; set it to
  `false` to keep the agent working for your own testing while the page says plainly that it is not open
  yet. See **Before the Gmail agent goes public** below.
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
- Daily cost ceiling: **4 USD/day** by default (in-memory, resets daily), shared by the demos and the Gmail
  agent. Tunable without a deploy via `DEMO_DAILY_CEILING_USD`, and the per-call estimate via
  `DEMO_EST_COST_PER_CALL_USD`. **Worth doing the sum:** the agent reads up to 50 emails per run, so at the
  default estimate one run is ~0.50 USD and about eight runs close every demo for the day — the lead
  qualifier included. The estimate is deliberately conservative and the real spend is expected to be well
  under it; measure a run, then lower the estimate or raise the ceiling.
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

## Two ways in: the example inbox, and a real Gmail account
`POST /api/agent/email/sample` runs the agent over `backend/sample_inbox.py` — ten invented but realistic
Hungarian business emails — with no Google account involved. It is the **default** entry point, and the
Gmail connect is one click behind it.

The reason is not squeamishness about OAuth. `gmail.readonly` is a restricted scope, so until the app
passes Google's security assessment every visitor meets a full-screen red *"Google hasn't verified this
app"* warning — and a stranger will not hand their mailbox to an agency they met a minute ago regardless.
The demo's job is to show what the agent does, and the example inbox does that instantly, on a phone, with
nothing to hand over. The classification and the drafting are the real thing: same prompts, same live model
calls, same output.

The sample inbox is chosen, not filler: something that needs an answer today, something that only looks
urgent, an automated notice, a phishing attempt, a newsletter, a missing subject line, and one whose
substance is in an attachment. An inbox where everything matters would prove nothing about triage, and a
test asserts the mix stays that way. Dates are stored relative to the run, so nothing ages into obviously
stale.

A sample session holds `creds: None` — absent, not unused — and `/draft/save` and `/draft/send` both return
409 on it. The reply text is still written for real; there is simply no mailbox to put it in and no real
recipient to send to. The run is public and spends model credits, so it carries the same per-IP limit as
the other demos.

When the visitor does choose the Google route, the page states what Google will show them **before** they
go, including that the warning is about the app's verification status and not about their account. Hiding
that would waste their time and look worse when it appeared.

## Reply drafting
The agent classifies the mailbox during the run, and writes a reply draft only when the visitor asks for
one — the per-email button in an expanded row. Drafting is the most expensive call here (longer output than
a classification) and most of a mailbox needs no answer, so it is on demand rather than part of the run.

- `POST /api/agent/email/draft` takes `{id, tone}` — an email id **from this session's own run**, never raw
  text. That keeps a leaked session token from turning the endpoint into a free LLM proxy.
- `tone` is `hivatalos` or `kozvetlen`; anything else is a 422.
- Drafts are cached per email *and* tone in the session, so re-opening one costs nothing.
- `MAX_DRAFTS_PER_SESSION` (6) caps distinct drafts per visitor, on top of the shared daily ceiling.
- The draft text always ends with an AI-draft notice; the schema appends it even when the model omits it.
- The prompt forbids inventing facts: unknown values come back as `[dátum]`-style placeholders, and the
  signature is `[a te neved]` rather than a made-up name.

### Writing the draft into Gmail
The draft can also be written into the visitor's Gmail **Drafts**, behind two independent gates. Both are
required; neither has a default that opens it.

1. **Permission, at connect time.** An unticked checkbox on the connect screen. Ticking it asks Google for
   `gmail.compose` alongside `gmail.readonly` (`GET /connect?drafts=true`); leaving it alone asks for read
   access only. The choice travels in the OAuth state so the callback rebuilds the flow with the same
   scopes — a mismatch there makes Google reject the exchange. The session records what Google *granted*,
   not what was asked: a visitor can untick a scope on the consent screen, so `can_draft` comes from the
   credentials, and the save button never appears for a session that cannot use it.
2. **Confirmation, per email.** `POST /draft/save` requires `confirm: true` and refuses without it. In the
   UI this is a second click on a separate control that names the recipient first — not a `confirm()`
   dialog. This is the only call in the whole agent that changes the mailbox.

The draft is threaded onto the original conversation: Gmail's `threadId` plus real `In-Reply-To` and
`References` headers, because without the headers other mail clients show the reply as an unrelated
message. Re-confirming after a reword **updates** the same draft instead of leaving near-duplicates, and
rewording clears the saved badge so it never sits next to text that was not saved.

### Sending
`POST /draft/send` sends the reply the user has already read, behind the same permission gate plus its own
final confirmation. It is built as *save the draft, then send that draft* rather than composing a fresh
message: what goes out is the draft the user confirmed, with the threading it already has, and there is no
path that sends text nobody has seen.

`SafeGmailProxy` is what keeps this to one path. It refuses `send` by default and the refusal travels down
the chain — a Resource reached through a refusing proxy refuses too — so the mailbox pass and the draft
save physically cannot send. Only a proxy built with `allow_send=True` can, and a test asserts there is
**exactly one** such construction in the file and that it sits inside `send_draft`. Adding a second one is
therefore a deliberate act that fails the suite.

Other guards: an email already answered in this session returns 409, so a double click or a replayed
request cannot send twice; a failed send does not mark it sent, so a retry stays possible; and the send
never happens without `confirm: true`.

Existing mail is still never altered — no labelling, starring, trashing or modifying — held by a test.
`gmail.modify` is still never requested.

**The AI-draft notice is stripped from anything that reaches Gmail.** It exists to tell the person reading
the *page* that the text was machine-written, before they accept it. Once they have read it and chosen to
send or save it, the message is theirs; shipping "this is an AI draft" to their customer would be nonsense,
and in a saved draft it would sit there waiting to go out by accident.

Be straight about the trade-off, because the page is: Google has **no draft-only scope**, so
`gmail.compose` covers both drafting and sending. The grant is what makes sending possible at all, Google's
consent screen says so, and the checkbox text says so before it can be ticked.

## Planned: a scheduled run every 2 hours
Wanted for the product version ("when the web app is done"), not buildable on the demo's architecture.
Four things block it, and each one is a design decision rather than a setting:

1. **The grant is deliberately temporary.** `access_type="online"` means Google returns no refresh token, so
   the credentials die with the visit — by design, and it is why the page can promise nothing outlives the
   session. An unattended run two hours later needs `access_type="offline"`, which is a different promise to
   the user and a different consent screen.
2. **Nothing is stored.** Sessions live in memory with a 30-minute TTL and die on every redeploy. A schedule
   needs durable, encrypted refresh-token storage, which means a database and a real account per user —
   the thing the demo deliberately does not have.
3. **A re-read every 2 hours is the wrong shape.** Twelve runs a day × 50 emails is 600 classifications per
   user per day, mostly of the same emails over and over. A scheduled run has to be **incremental**: store
   Gmail's `historyId` (or the last run's timestamp) per user and classify only what arrived since. That is
   roughly a tenth of the cost and the only version that scales past one user.
4. **Google verification gets stricter.** Ongoing offline access to a restricted scope for real users is a
   heavier review than a demo asking for one-shot online access.

Sketch, once accounts exist: a worker (Railway cron, or a loop service) wakes per user, refreshes the token,
asks Gmail for changes since the stored `historyId`, classifies only those, appends to that user's stored
results, and updates the marker. Per-user daily caps replace the single shared ceiling, because one shared
budget across scheduled users empties in minutes.

## Before the Gmail agent goes public
`gmail.readonly` is a Google **restricted** scope. Offering it to the public needs all three of:

1. **A named data controller.** The visitor hands over their mailbox and has to be able to see who is
   receiving it — a registered company, or an identified natural person. "AXIMBRA · Budapest" is a brand,
   not an identity.
2. **A published privacy notice**, reachable from the page, covering what is read, that the text goes to
   the OpenAI API, the 30-minute retention and how to revoke.
3. **Google OAuth app verification.** Until the app is verified, visitors get a full-screen "Google hasn't
   verified this app" warning and the project is capped at 100 users — and if it is still in *testing*
   mode, only explicitly listed test users can connect at all.

Until those exist, run with `AGENT_PUBLIC=false`. The connect button is then replaced by a short notice
saying the agent is not open yet and offering a live walkthrough by email, and `/connect` returns 503 —
the flow is blocked server-side, not merely hidden in the UI, which anyone could bypass by calling the
endpoint directly.

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
