# Voice AI Receptionist

A production-shaped voice AI receptionist for a dental clinic. It answers the phone, holds a natural spoken conversation, and books real appointments into Google Calendar — checking live availability before it offers a time, and never confirming a booking the calendar did not accept.

Built on [LiveKit Agents](https://github.com/livekit/agents) for Python.

```
Caller ──▶ STT ──▶ LLM ──▶ TTS ──▶ Caller
                    │
                    ├── check_availability ──┐
                    ├── book_appointment_slot ├──▶ Google Calendar API
                    └── request_callback ─────┘
```

## What it does

The agent plays receptionist for *SmileCare Dental Clinic* — open Mon–Sat, 10:00–19:00, thirty-minute slots, four services, bookings up to a week out. Over a call it will:

- **Answer clinic questions** — hours, address, services, the doctor's name.
- **Book an appointment end to end** — collecting the caller's name, service, day and time one question at a time, reading live free/busy data from Google Calendar before offering any slot, then writing the confirmed event.
- **Log a callback** when the caller wants something it genuinely cannot do — cancel, reschedule, look up an existing booking, or ask about pricing and insurance.

It is also built to **fail honestly**, which is most of the engineering:

- It never offers a time it has not confirmed is free, and never invents clinic information.
- It re-checks the calendar immediately before writing, so a slot taken mid-conversation is caught and alternatives are offered instead of double-booking.
- It refuses to diagnose or discuss symptoms, and offers a consultation instead.
- It states plainly what it cannot do rather than inventing a capability to sound helpful.

## Engineering notes

**Spoken input is not clean input.** Callers say "half past two", "tomorrow", "next friday", "book me at 3". `parse_day` and `parse_time` in [`src/calendar_service.py`](src/calendar_service.py) turn that into real dates and times — resolving relative days within a one-week booking window, expanding spoken number words, handling `half past` / `quarter to` qualifiers, and reading a bare "3" as 3 PM because the clinic is shut at 3 AM. Anything that is not a valid half-hour slot start is rejected rather than guessed at, and the rejection is handed back to the LLM as an instruction for what to ask next.

**Tools return instructions, not data.** Each tool's return value tells the model what to do with the result (`"That slot was just taken. Still free: ..."`), which keeps slot-handling logic out of the prompt and makes the failure paths testable.

**Race conditions are handled.** `book_appointment` queries free/busy again between the availability check and the write, so two callers converging on the same slot cannot both be confirmed.

**Timezone-correct throughout.** All datetimes are `Asia/Kolkata`-aware; no naive datetimes reach the Calendar API.

## Stack

| Layer | Choice |
|---|---|
| Orchestration | LiveKit Agents (Python) |
| STT | AssemblyAI Universal 3.5 Pro |
| LLM | Gemma 4 31B via LiveKit Inference |
| TTS | Fish Audio S2.1 Pro |
| Turn detection | LiveKit turn detector, adaptive interruption, preemptive generation |
| Audio | ai-coustics background voice cancellation |
| Booking backend | Google Calendar API (OAuth 2.0) |
| Tests | pytest, plus LiveKit simulation scenarios |

## Testing

Two layers, because conversation quality and parsing correctness fail in different ways.

**Unit tests** cover the day/time parsing and slot logic with no LLM or live session:

```console
uv run pytest
```

**Simulation scenarios** run full multi-turn conversations between a simulated caller and the agent on LiveKit Cloud, then judge each transcript. [`scenarios.yaml`](scenarios.yaml) holds 33 of them, written around the ways a real call goes wrong — a caller on a noisy line repeating themselves, an unusual name that is easy to mishear, an off-grid time like 10:15, a caller changing the service mid-booking, someone pressuring the agent to confirm a booking it never made, and a caller insisting the clinic is open on Sunday.

```console
lk agent simulate --scenarios scenarios.yaml
```

These run in CI on every merge to `main` via `.github/workflows/simulations.yml`.

## Running it

Requires [`uv`](https://docs.astral.sh/uv/) and a [LiveKit Cloud](https://cloud.livekit.io/) project.

```console
uv sync
cp .env.example .env.local     # fill in LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET, CALENDAR_ID
```

For Google Calendar, place an OAuth client `credentials.json` in the project root; the first run opens a browser consent flow and caches `token.json`. Both files are gitignored. Point `CALENDAR_ID` at a throwaway calendar when running simulations so test bookings stay out of the real one.

Talk to the agent in your terminal:

```console
uv run python src/agent.py console
```

Run it for a frontend or a phone number:

```console
uv run python src/agent.py dev      # development
uv run python src/agent.py start    # production
```

A `Dockerfile` is included for deployment to LiveKit Cloud or any container host. Connect any [frontend starter](https://docs.livekit.io/frontends/) or a [SIP trunk](https://docs.livekit.io/telephony/) for real phone calls.

## Layout

```
src/agent.py              Agent definition, prompt, and the three tools
src/calendar_service.py   Google Calendar client, day/time parsing, slot logic
tests/test_calendar.py    Unit tests for parsing and slot validation
scenarios.yaml            33 conversation-level simulation scenarios
```

## License

MIT — see [LICENSE](LICENSE). Built from the [LiveKit Agents Python starter](https://github.com/livekit-examples/agent-starter-python).
