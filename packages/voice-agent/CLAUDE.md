# Track A — Voice Agent · CLAUDE.md
**Owner: Keshav** · Before you code: re-read this file + root STATUS.md. After you code: update them.

## Language scope
**English only for now.** Drop all Hindi/multilingual logic. Language can be added later — the `lang` field exists in the contract but the memory engine currently ignores it and always returns English. Pass `"lang": "en"` on every call.

## What Track B has ready for you (all endpoints live on :8000)
- `GET  /health` — confirms memory-engine is up
- `POST /memory/query   {text, lang:"en"}` → `{items, grounded, confidence, answer_draft}`
- `POST /memory/temporal {text, lang:"en"}` → same shape — use for "pills today" / "is X coming"
- `POST /memory/write   {type, payload}` → `{id}`
- `GET  /reminders/due` → `{due:[{kind, text, ref}]}`
- All return fixture payloads until Moss/Supabase keys are in `.env` — safe to code against right now.

## Grounding system prompt (use verbatim — frozen)
```
You are Yaad, a warm companion for someone with memory loss.
State ONLY facts in the provided MEMORY context.
If empty or low-confidence, say you're not sure and offer to check with the family.
Never invent people, events, or dates.
Short, calm, warm. English only.
```

## memory_client.py — copy this exactly
```python
import httpx, os
BASE = os.getenv("MEMORY_ENGINE_URL", "http://localhost:8000")

async def query(text: str) -> dict:
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/memory/query", json={"text": text, "lang": "en"}, timeout=3.0)
        return r.json()

async def temporal(text: str) -> dict:
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/memory/temporal", json={"text": text, "lang": "en"}, timeout=3.0)
        return r.json()
```

## Fixture fallback contract (fallback.py)
If any memory/TTS/vision call times out (3s) → serve `fixtures/<beat>.json` answer_draft + cached TTS.
Beat → fixture map:
- who-is-this → `fixtures/who_is_leo.json`
- pills-today → `fixtures/pills_today.json`
- add-fact-live → `fixtures/add_fact_live.json`
- wifi-off → `fixtures/wifi_off.json`

Header `X-Yaad-Source: live | cached` on every response.

## Your next steps (in order)
1. **[CONFIRM at office hours]** Deepgram streaming STT exact call + partial-transcript event name
2. **[CONFIRM at office hours]** LiveKit / Pipecat exact transport + VAD setup
3. **[CONFIRM at office hours]** TrueFoundry base_url + model name
4. **[CONFIRM at office hours]** MiniMax streaming TTS (English voice id + group id)
5. Scaffold `agent.py` + `transports.py` + `memory_client.py` (copy pattern above) against fixture stubs (A0)
6. Wire Deepgram STT + MiniMax echo loop — speak in → transcribed → spoken back (A1)
7. Plug in real `/memory/query` + grounding prompt + barge-in (A2)
8. Latency pass: speculative fire on partial transcript → <~1s (A3)
9. `fallback.py`: 3s timeout → fixture + cached TTS, `X-Yaad-Source` header (A4)
10. Reminders: scheduler polls `/reminders/due` → proactive TTS (A5)
11. Cache TTS clips for the 4 fixture beats (needed for wifi-off demo)

## Phase: not started — update this file as you build
