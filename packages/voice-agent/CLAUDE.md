# Track A — Voice Agent · CLAUDE.md
**Owner: Rushil** · Before you code: re-read this file + root STATUS.md. After you code: update them.

---

## Current state (updated 2026-06-06, session 3)
- Phase: **A2 ready — agent starts clean, LLM + LiveKit confirmed**
- **Agent startup:** ✅ `LLM provider: TrueFoundry (openai/gpt-4o-mini @ https://gateway.truefoundry.ai)` — all pipeline processors link, LiveKit connecting
- **Groq STT:** ✅ English 0.37s exact transcript
- **MiniMax TTS:** ✅ `status_code=0`, `speech-02-hd`, `English_Graceful_Lady`, `api.minimax.io` (no GroupId), 29KB MP3, round-trip verified.
- **LLM:** ✅ TrueFoundry (`openai/gpt-4o-mini @ https://gateway.truefoundry.ai`)
- **VAD:** ✅ `VADProcessor` wired in pipeline, Silero model loaded, emitting `VADUserStartedSpeakingFrame`/`VADUserStoppedSpeakingFrame`
- **LiveKit:** ✅ fully connected, audio input running
- **Run command on this machine:** `arch -arm64 python3 -m app.agent`

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

## MiniMax TTS — confirmed spec (2026-06-06)
```
POST https://api.minimax.io/v1/t2a_v2   ← NO GroupId (that's China-platform only)
Authorization: Bearer {MINIMAX_API_KEY}
model: speech-02-hd | voice: English_Graceful_Lady | output_format: hex
Response: data.data.audio = hex-encoded MP3; base_resp.status_code 0 = OK
```
Audio decode: `bytes.fromhex(data["data"]["audio"])`

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
