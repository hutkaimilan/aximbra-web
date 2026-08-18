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
- Intro overlay (letter-by-letter 3D reveal), WebGL plasma hero + fallback, fixed shrinking nav, hero, 12 agent tilt cards, 6-step process rail with scroll-fill + amber human-gate pill, 8-row pricing table (stacks < 780px), EPISTEME case study with media placeholders + phone card, contact card, footer, editorial marquee.
- Two live LLM demos wired to backend, inline expandable, 3 Hungarian sample inputs each, full-width span when open.
- Backend guardrails + schema validation. `yarn build` passes. Testing agent: backend 100%, frontend 100%.

## Backlog / remaining
- P1: Drop real media files into `frontend/public/media/` (episteme-demo.mp4, episteme-poster.jpg, episteme-hivas.mp3).
- P2: Shared rate-limit store (Redis) if backend runs multiple Railway replicas.
- P2: Precise token-based cost metering instead of fixed per-call estimate.

## Open questions
- Live-demo model defaulted to `gpt-5.4-mini`; change in server.py if desired.
