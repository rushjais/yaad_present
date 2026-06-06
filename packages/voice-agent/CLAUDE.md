# Track A — Voice Agent · CLAUDE.md
**Owner: Keshav** · Before you code: re-read this file + root STATUS.md. After you code: update them.

## What Track B has ready for you
- `GET  http://localhost:8000/health` — confirms memory-engine is up
- `POST http://localhost:8000/memory/query   {text, lang}` → `{items, grounded, confidence, answer_draft}`
- `POST http://localhost:8000/memory/temporal {text, lang}` → same shape (use for "pills today" / "is X coming")
- `POST http://localhost:8000/memory/write   {type, payload}` → `{id}`
- `GET  http://localhost:8000/reminders/due` → `{due:[{kind,text,ref}]}`
- All return fixture payloads until Moss/Supabase keys are configured — safe to code against now.

## Grounding system prompt (use this verbatim — frozen)
```
You are Yaad, a warm companion for someone with memory loss.
State ONLY facts in the provided MEMORY context.
If empty or low-confidence, say you're not sure and offer to check with the family.
Never invent people, events, or dates.
Short, calm, warm. Match the user's language (English/Hindi/Hinglish).
```

## memory_client.py — call pattern
```python
import httpx, os
BASE = os.getenv("MEMORY_ENGINE_URL", "http://localhost:8000")

async def query(text: str, lang: str = "en") -> dict:
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/memory/query", json={"text": text, "lang": lang}, timeout=3.0)
        return r.json()

async def temporal(text: str, lang: str = "en") -> dict:
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/memory/temporal", json={"text": text, "lang": lang}, timeout=3.0)
        return r.json()
```

## Fixture fallback contract (fallback.py)
If any memory/TTS/vision call times out (3s) → serve `fixtures/<beat>.json` answer_draft + cached TTS.
Beat → fixture map: who-is-this → `fixtures/who_is_leo.json`, pills-today → `fixtures/pills_today.json`, add-fact-live → `fixtures/add_fact_live.json`, hindi → `fixtures/hindi.json`, wifi-off → `fixtures/wifi_off.json`.
Header `X-Yaad-Source: live | cached` on every response.

## [CONFIRM] items for Keshav
- MiniMax: Hindi voice id, streaming TTS, group id
- Deepgram: exact streaming STT call + partial-transcript event
- LiveKit / Pipecat: exact transport + VAD setup
- TrueFoundry: base_url + model name for the LLM gateway

## Phase: not started — update this file as you build
