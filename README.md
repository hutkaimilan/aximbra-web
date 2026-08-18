# AXIMBRA

Premium dark, neon AI agency marketing site (Hungarian). React (CRA) frontend + FastAPI backend for two live LLM demos.

## Stack
- Frontend: React 19, custom WebGL plasma shader, Lenis smooth scroll, IntersectionObserver reveals.
- Backend: FastAPI, two demo endpoints (`/api/demo/email`, `/api/demo/lead`) calling an OpenAI model.

## Environment variables

Backend (`backend/.env`):
- `OPENAI_API_KEY` — required for the two live demos (E-mail rendező, Érdeklődő-minősítő). Never exposed client-side.
- `MONGO_URL`, `DB_NAME` — present in template but unused (no database is used by this app).
- `CORS_ORIGINS` — comma-separated allowed origins (default `*`).

Frontend (`frontend/.env`):
- `REACT_APP_BACKEND_URL` — base URL of the backend; all API calls use `${REACT_APP_BACKEND_URL}/api`.

## Live demo guardrails (server-side)
- Daily cost ceiling: **4 USD/day** (in-memory, resets daily).
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

## Media
Drop `episteme-demo.mp4`, `episteme-poster.jpg`, and `episteme-hivas.mp3` into `frontend/public/media/`. Until then the case-study section shows dashed-border placeholders and works the moment the files appear.

## OPEN QUESTIONS
- Live demo model: defaulted to `gpt-5.4-mini` (cheap, fast classification) via the user's own `OPENAI_API_KEY`. Change in `backend/server.py` if a different model is desired.
- Cost accounting uses a fixed per-call estimate (`EST_COST_PER_CALL_USD`) since exact token cost is not read back; adjust if precise metering is needed.
- Rate-limit / cost state is in-memory (per process). On Railway with multiple replicas each replica tracks its own counters; use a shared store (e.g. Redis) if you scale horizontally.
