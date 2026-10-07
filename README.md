# SmileCare Voice AI Receptionist

[![Tests](https://github.com/aJ23101/voice-ai-receptionist/actions/workflows/tests.yml/badge.svg)](https://github.com/aJ23101/voice-ai-receptionist/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

A browser-based voice receptionist for a fictional dental clinic. It answers
questions, checks live Google Calendar availability, and books appointments
only after the calendar accepts them.

**[Deploy the browser demo on Vercel](https://vercel.com/new)** ·
**[Browse the source](https://github.com/aJ23101/voice-ai-receptionist)**

Vercel assigns the public demo URL after the first deployment. Add that URL to
the repository's **About → Website** field so recruiters can find it. This is
an interactive portfolio project, not a real clinic service.

## The experience

- Speak naturally to ask about the clinic or request an appointment.
- The receptionist checks Google Calendar before offering a time.
- It checks again just before booking to avoid confirming a slot taken during
  the conversation.
- Unsupported requests, including cancellations, pricing, and medical advice,
  are handled honestly and routed to a callback request.
- A purpose-built browser UI connects to the LiveKit agent over WebRTC.

> **Demo safety:** Use a dedicated test Google Calendar and fictional details.
> The demo can write calendar events. Do not enter real patient, medical, or
> other sensitive information.

## Architecture

```text
Browser (React + LiveKit WebRTC)
        │
        ├── Turnstile challenge
        ▼
Token API (FastAPI on Render)
  - verifies the challenge
  - rate-limits requests
  - issues a short-lived, room-scoped token
        │
        ▼
LiveKit Cloud agent (Python)
  ├── LiveKit Inference: AssemblyAI STT, Gemma LLM, Fish Audio TTS
  └── Google Calendar: availability, booking, callback events
```

The browser never receives LiveKit API secrets. The token service restricts
cross-origin requests to the published site, validates Cloudflare Turnstile,
limits requests per client, and issues tokens for a single demo room with
media publishing enabled and data publishing disabled.

## Stack

| Area | Technology |
|---|---|
| Voice agent | LiveKit Agents for Python |
| Speech | AssemblyAI Universal 3.5 Pro, Gemma 4 31B, Fish Audio S2.1 Pro |
| Browser | React, TypeScript, Vite, LiveKit React components |
| Calendar | Google Calendar API, OAuth for local development or a service account in cloud |
| Demo authentication | FastAPI, Cloudflare Turnstile, short-lived LiveKit tokens |
| Hosting | LiveKit Cloud, Vercel, Render |
| Quality | pytest, Ruff, TypeScript build, LiveKit conversation simulations |

## Run locally

### 1. Configure the agent and calendar

Install [uv](https://docs.astral.sh/uv/) and create a LiveKit Cloud project.
Then:

```console
uv sync
```

Copy `.env.example` to `.env.local` and set the LiveKit credentials and a
dedicated test `CALENDAR_ID`. For local calendar development, place a Google
OAuth client file named `credentials.json` in the repository root; the first
calendar request opens the consent flow and saves `token.json`.

Run the agent:

```console
uv run python src/agent.py dev
```

For the hosted agent, use a Google service account instead of interactive
OAuth. Set `GOOGLE_SERVICE_ACCOUNT_JSON` to its JSON key and share the
dedicated test calendar with the service account's email address. When this
variable is present, the agent uses it without reading local OAuth files.

### 2. Start the token API

Create a Cloudflare Turnstile widget for `localhost` and put its **secret**
key in `.env.local`. Set:

```text
TURNSTILE_ALLOWED_HOSTNAME=localhost
FRONTEND_ORIGIN=http://localhost:5173
LIVEKIT_AGENT_NAME=voice-ai-receptionist
```

Start the API in a second terminal:

```console
uv run uvicorn src.token_server:app --env-file .env.local --reload --port 8000
```

### 3. Start the browser app

Copy `web/.env.example` to `web/.env.local`, set the public Turnstile site
key, then:

```console
cd web
npm ci
npm run dev
```

Open the local URL printed by Vite. The browser app uses the local token API;
the agent and calendar still need valid credentials.

## Publish the recruiter demo

The repository is public already. To make the browser demo accessible:

1. **Deploy the agent to LiveKit Cloud.** Install the LiveKit CLI, then run
   `lk cloud auth` and `lk agent create` from the repository. The current
   deployment workflow and CLI commands are documented in the
   [LiveKit agent deployment guide](https://docs.livekit.io/deploy/agents/quickstart/).
2. **Configure the deployed agent secrets.** Add `GOOGLE_SERVICE_ACCOUNT_JSON`
   and `CALENDAR_ID` to the LiveKit Cloud agent secrets. Use a separate,
   throwaway Google Calendar, enable the Google Calendar API, and share the
   calendar with the service account. Never use a real clinic calendar for
   this public demo.
3. **Import the repository into Vercel.** Choose
   `aJ23101/voice-ai-receptionist`, then set the project **Root Directory** to
   `web`. Vercel detects Vite; use `npm run build` and `dist` if it asks for
   build settings. Deploy once to get the project's production hostname.
4. **Create a Cloudflare Turnstile widget.** Add the production hostname
   assigned to your Vercel project (for example, `your-project.vercel.app`) as
   an allowed hostname. Keep the site key for Vercel; keep the secret key
   private for Render.
5. **Deploy the token API to Render.** Create a Render Blueprint from
   `render.yaml`. Add `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`,
   `TURNSTILE_SECRET_KEY`, `TURNSTILE_ALLOWED_HOSTNAME`, and `FRONTEND_ORIGIN`
   when prompted. Use the exact Vercel hostname (without `https://`) for
   `TURNSTILE_ALLOWED_HOSTNAME` and the full site origin for `FRONTEND_ORIGIN`.
   Do not expose API secrets as Vite variables.
6. **Set the frontend variables in Vercel.** Under **Project → Settings →
   Environment Variables**, add these for the **Production** environment:
   - `VITE_TOKEN_ENDPOINT_URL`: the Render URL ending in `/api/token`
   - `VITE_TURNSTILE_SITE_KEY`: the public Turnstile site key

   Redeploy after adding or changing build-time variables. Keep the variables
   out of preview deployments; the API only allows the configured production
   hostname and origin.
7. **Publish and link it.** Redeploy the production branch in Vercel, open the
   generated `https://<your-project>.vercel.app` URL, and test the call flow.
   Set the deployed URL as the repository's **About → Website** link so it is
   visible at the top of GitHub.

Render's free service may sleep while idle, so the first token request can
take longer. Keep API secrets in Render and LiveKit Cloud; only the token API
URL and public Turnstile site key belong in Vercel's frontend environment.

### Optional conversation simulations

The LiveKit simulations use real inference and can create calendar events.
To enable them, add `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`,
`GOOGLE_SERVICE_ACCOUNT_JSON`, and a dedicated test `CALENDAR_ID` as GitHub
Actions secrets. Without those secrets the workflow skips the simulations.

```console
lk agent simulate --scenarios scenarios.yaml
```

## Tests and checks

```console
uv run pytest
uv run ruff check .
```

Browser checks:

```console
cd web
npm ci
npm run lint
npm run build
```

Unit tests cover spoken date/time parsing, headless Google Calendar
authentication, token grants, Turnstile verification, origin restrictions, and
token endpoint rate limits. Conversation simulations exercise the full
agent behavior on LiveKit Cloud.

## Project layout

```text
src/agent.py                 LiveKit agent, instructions, and tools
src/calendar_service.py      Google Calendar, parsing, and slot validation
src/token_server.py          Turnstile-protected demo token endpoint
tests/                       Calendar and token-service tests
web/                         React browser demo
web/token-api/               Minimal locked dependencies for Render
scenarios.yaml               Conversation-level simulation scenarios
```

## License

MIT. See [LICENSE](LICENSE).
