# Track A — Voice Agent · CLAUDE.md
**Owner: Rushil** · Before you code: re-read this file + root STATUS.md. After you code: update them.

---

## Current state (updated 2026-06-06, session 2)
- Phase: **A1 complete / A2 blocked on LLM key**
- **Groq STT: ✅ validated** — "Who is this person?" → exact transcript, 0.46s, English detected
- **MiniMax TTS: ✗ key invalid** (status_code=2049). Response format confirmed and decoder fixed. Need fresh key.
- **LLM: no key set** — `create_llm()` will raise on startup. Set any one of: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or TrueFoundry vars.
- **ffmpeg: ✅ installed** (v8.1.1)
- Pipeline integrates LLM directly (no pipecat LLM service — avoids version import issues)

## Language scope
**English only.** Always pass `"lang": "en"`. Hindi deferred.

## What Track B has ready (all endpoints live on :8000)
- `POST /memory/query   {text, lang:"en"}` → `{items, grounded, confidence, answer_draft}`
- `POST /memory/temporal {text, lang:"en"}` → same shape
- `POST /memory/write   {type, payload}` → `{id}`
- `GET  /reminders/due` → `{due:[{kind, text, ref}]}`
- All return fixture payloads until Moss/Supabase keys are set.

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
| `app/agent.py` | Pipeline + entry point (`python -m app.agent`). LLM integrated into `MemoryContextProcessor`. |
| `app/transports.py` | LiveKit transport + Silero VAD |
| `app/stt_groq.py` | ✅ Groq Whisper STT — buffers utterance, times STT, emits TranscriptionFrame |
| `app/stt_deepgram.py` | Kept as reference; not used |
| `app/tts_minimax.py` | MiniMax TTS — hex-decode confirmed, times TTS, logs latency line |
| `app/llm.py` | LLM factory: TrueFoundry → OpenAI → Anthropic, raises if none configured |
| `app/memory_client.py` | HTTP client → `/memory/query` + `/memory/temporal` |
| `app/fallback.py` | 5-beat fixture responses for demo resilience |
| `app/reminders_client.py` | Background poller for `/reminders/due` (A5) |
| `app/validate_stt_tts.py` | Programmatic validation: macOS say → Groq STT + MiniMax TTS probe (no mic) |
| `app/test_stt_tts.py` | Mic-based or WAV-file STT+TTS test |

## Pipeline flow
```
LiveKit audio in
  → Silero VAD (barge-in: StartInterruptionFrame cancels TTS)
  → Groq Whisper STT (buffers utterance → transcribes, logs STT time)
  → MemoryContextProcessor (memory query "en" + LLM streaming → TextFrame, logs memory+LLM time)
  → SentenceAggregator (buffers into sentences)
  → MiniMax TTS (logs TTS time + full [LATENCY] line)
  → LiveKit audio out
```

Latency log format (per turn):
```
[LATENCY] STT 0.46s | memory 0.05s | LLM 0.60s | TTS 0.50s | total 1.61s
```

## LLM auto-detection (llm.py)
```
1. TRUEFOUNDRY_BASE_URL + TRUEFOUNDRY_API_KEY + TRUEFOUNDRY_MODEL → TrueFoundry
2. OPENAI_API_KEY                                                   → gpt-4o
3. ANTHROPIC_API_KEY                                                → claude-haiku-4-5-20251001
4. none                                                             → RuntimeError with clear message
```

## MiniMax TTS confirmed response format
```python
# Confirmed via API probe 2026-06-06 (status_code=2049 but response shape verified)
data["data"]["audio"]  # hex-encoded MP3 string  ← NOT base64, NOT audio_file
mp3_bytes = bytes.fromhex(data["data"]["audio"])
```
**Key issue:** current `MINIMAX_API_KEY` is invalid for T2A endpoint (status_code=2049).
→ Get fresh key from portal.minimax.chat and update `.env`.

## How to validate
```bash
# Validate Groq STT + MiniMax probe (no mic):
python -m app.validate_stt_tts

# Mic test when you have audio input:
python -m app.test_stt_tts
python -m app.test_stt_tts path/to/file.wav
```

## Next steps
1. ✅ Groq STT validated
2. ✅ MiniMax response format confirmed; decoder fixed
3. **Now:** get a valid LLM key → `python -m app.agent` should start cleanly
4. **Now:** get valid MiniMax TTS key → re-run `validate_stt_tts.py` for full round-trip
5. A3 latency pass once A2 is running
6. A4: cache TTS clips for wifi-off beat
7. A5: wire reminders into pipeline output

## [CONFIRM] open items
- **MiniMax:** need fresh API key (current invalid). Voice ID `Calm_Woman` assumed — confirm with working key.
- **LLM:** set any one key (see LLM auto-detection above)
- **LiveKit / Pipecat:** import paths; VAD frame names — pending full pipeline run
- **Groq STT:** ✅ confirmed

## Faked / TODO real
- MiniMax TTS: key invalid — decoder fixed, pending valid key
- TrueFoundry: not configured — LLM falls back to OpenAI/Anthropic if those keys are set
- LiveKit transport: not tested (requires room + keys)
- `SentenceAggregator`: local impl — swap for pipecat built-in if version supports it
- Reminders: poller wired but not integrated into pipeline speech output yet (A5)
