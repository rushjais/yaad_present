# Track A — Voice Agent · CLAUDE.md
**Owner: Rushil** · Before you code: re-read this file + root STATUS.md. After you code: update them.

---

## Current state (updated 2026-06-06, session 1)
- Phase: **A1 in progress** — pipeline scaffold built, Groq Whisper STT wired, MiniMax TTS not yet validated.
- Built: `agent.py`, `transports.py`, `stt_groq.py`, `tts_minimax.py`, `llm.py`, `memory_client.py`, `fallback.py`, `reminders_client.py`, `test_stt_tts.py`.
- Keys confirmed: `GROQ_API_KEY`, `MINIMAX_API_KEY`, `MINIMAX_GROUP_ID` in `.env`.
- **Immediate blocker:** run `python -m app.test_stt_tts` to confirm Groq STT + MiniMax TTS work end-to-end.

## Language scope
**English only.** Drop all Hindi/multilingual logic. The `lang` field exists in the contract but memory engine always returns English — pass `"lang": "en"` on every call. Hindi can be added later without contract changes.

## What Track B has ready for you (all endpoints live on :8000)
- `GET  /health` — confirms memory-engine is up
- `POST /memory/query   {text, lang:"en"}` → `{items, grounded, confidence, answer_draft}`
- `POST /memory/temporal {text, lang:"en"}` → same shape — use for "pills today" / "is X coming"
- `POST /memory/write   {type, payload}` → `{id}`
- `GET  /reminders/due` → `{due:[{kind, text, ref}]}`
- All return fixture payloads until Moss/Supabase keys are set and `seed_amma.py` is run — safe to code against now.

## Grounding system prompt (frozen — use verbatim)
```
You are Yaad, a warm companion for someone with memory loss.
State ONLY facts in the provided MEMORY context.
If empty or low-confidence, say you're not sure and offer to check with the family.
Never invent people, events, or dates.
Short, calm, warm. English only.
```

## File responsibilities
| File | Does |
|---|---|
| `app/agent.py` | Pipeline assembly + entry point (`python -m app.agent`) |
| `app/transports.py` | LiveKit transport + Silero VAD — token generation |
| `app/stt_groq.py` | **Active STT** — Groq Whisper, buffers utterance, auto-detects lang |
| `app/stt_deepgram.py` | Kept as reference; not imported by agent.py |
| `app/test_stt_tts.py` | Standalone smoke test: mic/WAV → Groq STT → MiniMax TTS |
| `app/tts_minimax.py` | MiniMax TTS FrameProcessor — HTTP call, MP3→PCM |
| `app/llm.py` | OpenAILLMService pointed at TrueFoundry gateway |
| `app/memory_client.py` | Async HTTP client → `/memory/query` + `/memory/temporal` |
| `app/fallback.py` | 5-beat fixture responses for demo resilience (§13) |
| `app/reminders_client.py` | Background poller for `/reminders/due` (A5) |

## Pipeline flow
```
LiveKit audio in
  → Silero VAD (barge-in: StartInterruptionFrame cancels TTS)
  → Groq Whisper STT (buffers utterance → transcribes)
  → MemoryContextProcessor  ← /memory/query or /memory/temporal (3s timeout → fixture)
  → TrueFoundry LLM         ← grounding system prompt
  → SentenceAggregator      ← buffers streaming text into sentences
  → MiniMax TTS             ← English, MP3→PCM
  → LiveKit audio out
```

## How to validate before wiring the full pipeline
```bash
cd packages/voice-agent
pip install -r requirements.txt
brew install ffmpeg
# then run the smoke test:
python -m app.test_stt_tts           # records 5s from mic
python -m app.test_stt_tts file.wav  # or pass a WAV
```
Expected: transcript printed, MiniMax speaks it back. If you see "No audio in MiniMax response" — print the full response dict and fix the field name in `tts_minimax.py:62` + `test_stt_tts.py:100`.

## memory_client.py — use this pattern (already in app/memory_client.py)
```python
import httpx, os
BASE = os.getenv("MEMORY_ENGINE_URL", "http://localhost:8000")

async def query(text: str) -> dict:
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/memory/query", json={"text": text, "lang": "en"}, timeout=3.0)
        return r.json()
```

## Fixture fallback contract (fallback.py)
If any memory/TTS call times out (3s) → serve `fixtures/<beat>.json` answer_draft + cached TTS.
Beat → fixture map:
- who-is-this → `fixtures/who_is_leo.json`
- pills-today → `fixtures/pills_today.json`
- add-fact-live → `fixtures/add_fact_live.json`
- wifi-off → `fixtures/wifi_off.json`

## Next steps (in order)
1. ✅ Scaffold `agent.py` + STT + TTS + `memory_client.py` (A0–A1)
2. **Now:** run `test_stt_tts.py` → confirm Groq STT + MiniMax TTS round-trip (A1 blocker)
3. **[CONFIRM]** LiveKit / Pipecat exact transport + VAD setup; pipecat version import paths
4. **[CONFIRM]** TrueFoundry base_url + model name
5. **[CONFIRM]** MiniMax English voice id — validate with `test_stt_tts.py`
6. Plug in real `/memory/query` + grounding prompt + barge-in (A2)
7. Latency pass: speculative fire on partial transcript → <~1s (A3)
8. `fallback.py`: 3s timeout → fixture + cached TTS (A4) — cache TTS clips for wifi-off beat
9. Reminders: scheduler polls `/reminders/due` → proactive TTS (A5)

## [CONFIRM] open items
- **MiniMax:** audio response field (`audio_file` vs `data.audio`), English voice id — surface by running `test_stt_tts.py`
- **LiveKit / Pipecat:** installed version → verify import paths; VAD frame names (`UserStartedSpeakingFrame` / `UserStoppedSpeakingFrame`)
- **TrueFoundry:** `TRUEFOUNDRY_BASE_URL` + model name
- **pydub + ffmpeg:** confirm available on demo machine

## Faked / TODO real
- MiniMax TTS: not tested end-to-end yet
- TrueFoundry LLM: not tested yet
- LiveKit transport: not tested yet
- Hindi/multilingual code in `tts_minimax.py` + `fallback.py`: present but unused (English only for now)
- `reminders_client.py`: wired but not integrated into pipeline output yet (A5)
- `SentenceAggregator`: local implementation — swap for pipecat built-in if version supports it
