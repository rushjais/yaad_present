# Track A — Voice Agent · CLAUDE.md
**Owner: Rushil** · Before you code: re-read this file + root STATUS.md. After you code: update them.

## Current phase: A0 — start now

## Keys confirmed — copy these into your code
| Service | Key var in `.env` | Endpoint / notes |
|---|---|---|
| **Groq LLM** | `GROQ_API_KEY` | `https://api.groq.com/openai/v1` — OpenAI-compatible. Model: `llama-3.3-70b-versatile` |
| **Groq STT** | `GROQ_API_KEY` | `https://api.groq.com/openai/v1/audio/transcriptions` — model `whisper-large-v3`. No Deepgram needed. |
| **MiniMax TTS** | `MINIMAX_API_KEY`, `MINIMAX_GROUP_ID` | `POST https://api.minimaxi.chat/v1/t2a_v2` — model `speech-02-hd`, voice `Wise_Woman`. **Use `api.minimaxi.chat`, NOT `api.minimax.chat`.** |
| **LiveKit** | `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | Keys in `.env`. Transport setup: [CONFIRM at office hours]. |
| **TrueFoundry** | `TRUEFOUNDRY_API_KEY` | Key in `.env` but `TRUEFOUNDRY_BASE_URL` is empty — use Groq until confirmed. |

## Memory engine (Track B) — live at :8000
All endpoints return fixture JSON until the server is running with Moss/Supabase keys. Real grounded data is live once `uvicorn` starts.

### Call pattern — copy this exactly
```python
import httpx, os
BASE = os.getenv("MEMORY_ENGINE_URL", "http://localhost:8000")

async def query(text: str) -> dict:
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/memory/query",
                         json={"text": text, "lang": "en"}, timeout=3.0)
        return r.json()

async def temporal(text: str) -> dict:
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/memory/temporal",
                         json={"text": text, "lang": "en"}, timeout=3.0)
        return r.json()
```

Response shape: `{items: [{ref, type, text, score, provenance}], grounded: bool, confidence: float, answer_draft: str|null}`

- `grounded=True` + `items` non-empty → use `items` as LLM context
- `grounded=False` → `answer_draft` is already a safe refusal — speak it directly, skip LLM

## Grounding system prompt (use verbatim — frozen)
```
You are Yaad, a warm companion for someone with memory loss.
State ONLY facts in the provided MEMORY context.
If the context is empty or low-confidence, say you're not sure and offer to check with the family.
Never invent people, events, or dates.
Short, calm, warm. English only.
```

## Fixture fallback — required for demo resilience
If any memory/TTS call times out (3s) → serve the matching fixture + cached TTS.

| Demo beat | Fixture file | Trigger phrase |
|---|---|---|
| who-is-this | `fixtures/who_is_leo.json` | "Who is this?" / "Who is Leo?" |
| pills-today | `fixtures/pills_today.json` | "Did I take my pills?" |
| add-fact-live | `fixtures/add_fact_live.json` | "Tell me about Leo's birthday" |
| wifi-off | `fixtures/wifi_off.json` | Any query when memory engine is unreachable |

Header `X-Yaad-Source: live | cached` on every response.

**Pre-cache TTS clips for the 4 fixtures** before the demo. These are needed for the wifi-off beat.

## Language scope
**English only.** Pass `"lang": "en"` on every memory call. Hindi is a future add-on.

## Your next steps (in order)
1. **[CONFIRM at office hours]** LiveKit/Pipecat exact transport + VAD setup
2. **[CONFIRM at office hours]** TrueFoundry base_url + model (use Groq in the meantime)
3. Scaffold `agent.py` + `transports.py` + `memory_client.py` (copy pattern above). Hit fixture stubs to verify the loop. (A0)
4. Wire Groq Whisper STT + MiniMax TTS echo loop — speak → transcribe → speak back. (A1)
5. Plug in real `/memory/query` + grounding prompt + barge-in on VAD. (A2)
6. Latency pass: fire memory query speculatively on partial transcript → target <~1s end-to-end. (A3)
7. `fallback.py`: 3s timeout on any call → fixture JSON + cached TTS + `X-Yaad-Source: cached`. (A4)
8. Proactive reminders: scheduler polls `GET /reminders/due` at medication times → proactive TTS. (A5)
9. Pre-cache TTS audio for all 4 fixture beats (needed for wifi-off demo).

## Phase: A0 — update this section as you build
