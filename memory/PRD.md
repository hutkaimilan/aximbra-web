# AXIMBRA — PRD

## Original problem statement
Premium, dark, neon-lit single-page marketing site for AXIMBRA, a Budapest AI agency. All copy in Hungarian (verbatim). React frontend, no database. Two of twelve agents are live LLM demos. Deployment target: Railway.

## Architecture
- **Frontend:** React 19 (CRA), custom raw-WebGL plasma shader (6-octave fBm) with CSS radial fallback, Lenis smooth scroll, IntersectionObserver scroll-reveals, framer-motion available. Fonts: Chakra Petch / Sora / JetBrains Mono.
- **Backend:** FastAPI, two endpoints `/api/demo/email` + `/api/demo/lead` calling OpenAI (`gpt-5.4-mini`) via emergentintegrations with the user's own `OPENAI_API_KEY`. Strict Pydantic Literal schemas, up to 3 attempts, Hungarian fallback. In-memory guardrails: 4 USD/day, 8 runs/session, 20 req/IP/hour, 4000-char input cap. **No database used.**

## User personas
- Hungarian SME owners/managers evaluating whether to commission an AI agent for a repetitive task.

## Core requirements (static)
- Exact Hungarian copy, dark neon palette, intro animation every load, WebGL hero, liquid buttons, 3D tilt cards, scroll reveals, prefers-reduced-motion support, mobile-first, keyboard-accessible with cyan focus ring.

## Implemented (2026-06-18)
- Intro overlay (letter-by-letter 3D reveal), WebGL plasma hero + fallback, fixed shrinking nav, hero, 12 agent tilt cards, 6-step process rail with scroll-fill + amber human-gate pill, EPISTEME case study with audio player (real MP3) + phone card, contact card, footer, editorial marquee.
- Two live LLM demos wired to backend (OpenAI, user key), inline expandable, 3 Hungarian sample inputs each.
- 8-language switcher (dropdown, native names, `<html lang>` sync, localStorage persistence, deep-merge fallback lang→en→hu).
- Website-package pricing block (3 cards, middle featured "Legnépszerűbb", net-price note, mailto CTA with package name).
- Header call-bar mail button; audio player with preload=none + error fallback.
- FOUR demo websites (restaurant/salon/clinic/law-firm) on react-router routes with distinct art directions, homepage "Referenciák" link section, back links, language switch on demos (HU/EN authored, EN fallback for other 6).
- All iterations pass testing 100%.

## Fixed (2026-07)
- **Demo back-navigation returns to exact scroll position**: previously the demo pages' "← Vissza az AXIMBRA-hoz" link (`DemoBar.jsx`, `<Link to="/">`) always landed at the top of the homepage. Now: `References.jsx` saves `window.scrollY` to `sessionStorage["aximbra:return"]` on demo-card click; `App.js`/`Site` restores it on mount (Lenis/window `scrollTo`, immediate), skips the ~2.6s intro overlay on return (`Intro` `skip` prop, avoids `body.lock` overriding scroll), and adds `.App.restore` class forcing all `.reveal` elements instantly visible (IntersectionObserver didn't re-fire after the programmatic jump, leaving content at opacity:0). Verified: open any of the 4 demos, press back → lands at exact same scrollY with References fully visible.
- P0: Mobile horizontal overflow at 380px — root cause was the nav bar (logo + lang-select + KAPCSOLAT button) exceeding viewport width and clipping the KAPCSOLAT button. Added `@media (max-width:480px)` block in `index.css` tightening nav padding, gap, logo/button/lang-select sizing. Verified 0px scroll overflow on home + all 4 demo pages at 380px.

## Added (2026-07)
- **Mobile hamburger menu** (`Nav.jsx`): burger button + slide-down `.nav-drawer` shown ≤900px containing nav links, call-bar link and KAPCSOLAT button. Bar keeps logo + lang-select + burger. Fixed stacking-context so logo/close-X paint above drawer. 0px overflow at 380px.
- **Video poster** `frontend/public/media/episteme-poster.jpg` — abstract neon waveform (generated, on-brand, non-photorealistic). Wired via existing `poster` attr on case-study `<video>`.
- **Copy-link button** REMOVED from reference demo cards (2026-07, user: felesleges). Cards keep the scroll-save onClick for exact back-navigation.
- **Real phone in Kapcsolat block** (`Contact.jsx`): replaced disabled "Telefonos agent — hamarosan" with clickable `tel:+18024249852` (+1 802 424 9852) + note "Magyarul és angolul is beszél · egy AI agent veszi fel" (hu) / EN equivalent. Contact form intentionally NOT added (mailto stays).
- **Drawer auto-close** (`Nav.jsx`): mobile drawer closes on outside tap (pointerdown outside nav) and on scroll/wheel/touchmove.
- **Hero phone highlight** (`Hero.jsx`): clickable `tel:+18024249852` pill with pulsing "AI" badge + note "Egy AI agent veszi fel · magyarul és angolul is" (hu/en). 0px overflow at 380px. (Animated card previews + 6-language demo translation explicitly declined by user — market is HU, HU+EN enough.)
- **Live hero status indicator** (`Hero.jsx` + backend `/api/voice/health`): backend proxies the external voice-agent health endpoint (`https://aximbra-voice-production.up.railway.app/health`) server-side to avoid CORS. Hero shows a real status pill — GREEN "ÉLŐ TELEFON-AGENT · ma N hívás" (+ "M aktív most" if live>0) when reachable & ok, GREY "TELEFON-AGENT NEM ELÉRHETŐ" when unreachable. Auto-refresh every 30s. Daily call count rendered small/non-dominant (11px dim). When `live>0` the pill gets a `talking` class → `statusFlash` glow animation + faster dot pulse. Verified online, offline (grey), talking (live>0 flash), 0px overflow at 380px. (Footer duplication + fake uptime timeline explicitly declined by user.)

## Backlog / remaining
- P1: Drop real media files into `frontend/public/media/` (episteme-demo.mp4, episteme-hivas.mp3 present; poster now added).
- P2: Shared rate-limit store (Redis) if backend runs multiple Railway replicas.
- P2: Precise token-based cost metering instead of fixed per-call estimate.

## Open questions
- Live-demo model defaulted to `gpt-5.4-mini`; change in server.py if desired.
