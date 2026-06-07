# Track A — Voice Agent · CLAUDE.md
**Owner: Rushil** · Before you code: re-read this file + root STATUS.md. After you code: update them.

---

## Current state (updated 2026-06-06, session end)
- Phase: **A2 complete — all components live and validated**
- **Agent startup:** ✅ `LLM provider: TrueFoundry (openai/gpt-4o-mini @ https://gateway.truefoundry.ai)`
- **Groq STT:** ✅ English 0.37s exact transcript
- **MiniMax TTS:** ✅ `status_code=0`, `speech-02-hd`, `English_Graceful_Lady`, `api.minimax.io` (no GroupId), 29KB MP3, round-trip verified
- **VAD:** ✅ `VADProcessor` wired, Silero loaded, `VADUserStartedSpeakingFrame`/`VADUserStoppedSpeakingFrame`
- **LiveKit:** ✅ fully connected to `yaad-demo`, audio input running
- **answer_draft routing:** ✅ `answer_draft` populated → emit verbatim (skips LLM); null → LLM from items[]
- **--local mode:** ✅ `arch -arm64 python3 -m app.agent --local` (sounddevice mic/speakers)

## Language scope
**English only.** Always pass `"lang": "en"`. Hindi deferred.

## Keys confirmed (from Track B — copy into your .env)
| Service | Key var | Endpoint / notes |
|---|---|---|
| **Groq STT** | `GROQ_API_KEY` | `whisper-large-v3-turbo` via Groq |
| **MiniMax TTS** | `MINIMAX_API_KEY` | `POST https://api.minimax.io/v1/t2a_v2` — NO GroupId. model `speech-02-hd`, voice `English_Graceful_Lady`. Track B also documents `api.minimaxi.chat`; both work. |
| **TrueFoundry** | `TRUEFOUNDRY_API_KEY` | `gateway.truefoundry.ai`, model `openai/gpt-4o-mini` — confirmed working |
| **LiveKit** | `LIVEKIT_URL/KEY/SECRET` | `wss://keepsake-y39026vu.livekit.cloud`, room `yaad-demo` |

## What Track B has ready (all endpoints live on :8000)
- `POST /memory/query   {text, lang:"en"}` → `{items, grounded, confidence, answer_draft}`
- `POST /memory/temporal {text, lang:"en"}` → same shape (answer_draft pre-composed for temporal)
- `POST /memory/write   {type, payload}` → `{id}`
- `GET  /reminders/due` → `{due:[{kind, text, ref}]}`
- B7 `items[]` may contain graph-expanded neighbors — treat `items[].text` as authoritative, do NOT reparse.
- Intent LLM-fallback path can spike ~300ms — fire speculatively on partial transcript (A3).

## Grounding system prompt (frozen — use verbatim)
```
You are Yaad, a warm companion for someone with memory loss.
State ONLY facts in the provided MEMORY context.
If empty or low-confidence, say you're not sure and offer to check with the family.
Never invent people, events, or dates.
Short, calm, warm. English only.
```

## answer_draft routing (implemented in MemoryContextProcessor)
- `answer_draft` populated → **emit verbatim, skip LLM** (temporal path — grounded negatives like "not yet taken" must not be re-composed)
- `answer_draft` null → compose from items[] via LLM (semantic path)

## File responsibilities
| File | Does |
|---|---|
| `app/agent.py` | Pipeline + entry point. `--local` flag for mic/speakers mode. LLM in `MemoryContextProcessor`. |
| `app/transports.py` | LiveKit transport + Silero VAD factory |
| `app/local_transport.py` | Sounddevice-based local audio transport (arm64 native) |
| `app/stt_groq.py` | ✅ Groq Whisper STT — buffers utterance, VAD-triggered, emits TranscriptionFrame |
| `app/stt_deepgram.py` | Kept as reference; not used |
| `app/tts_minimax.py` | MiniMax TTS — key read at `__init__` (not module level), hex-decode, latency logging |
| `app/llm.py` | LLM factory: TrueFoundry → OpenAI → Anthropic, raises if none configured |
| `app/memory_client.py` | HTTP client → `/memory/query` + `/memory/temporal` |
| `app/fallback.py` | 5-beat fixture responses for demo resilience |
| `app/reminders_client.py` | Background poller for `/reminders/due` (A5) |
| `app/validate_stt_tts.py` | Programmatic validation: macOS say → Groq STT + MiniMax TTS (no mic) |

## Pipeline flow
```
LiveKit audio in (or sounddevice mic in --local mode)
  → VADProcessor (Silero VAD → VADUserStartedSpeakingFrame / VADUserStoppedSpeakingFrame)
  → Groq Whisper STT (buffers utterance → transcribes, logs STT time)
  → MemoryContextProcessor:
      answer_draft? → emit verbatim (temporal path, skip LLM)
      else         → /memory/query + LLM streaming → TextFrame (semantic path)
  → SentenceAggregator
  → MiniMax TTS → TTSAudioRawFrame (logs [LATENCY] line)
  → LiveKit audio out (or sounddevice speakers in --local mode)
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
Track B also documents `api.minimaxi.chat` as working — both domains accepted.

## How to run
```bash
arch -arm64 python3 -m app.agent           # LiveKit mode (yaad-demo room)
arch -arm64 python3 -m app.agent --local   # local mic + speakers
python -m app.validate_stt_tts             # validate STT+TTS without mic
```

## Next steps (A3 onwards)
1. ✅ A0–A2 complete
2. **A3:** latency pass — fire memory query speculatively on partial transcript; target <1s end-to-end
3. **A4:** pre-cache TTS clips for all 4 fixture beats (wifi-off demo requires cached audio)
4. **A5:** wire reminders into pipeline speech output

## Faked / TODO real
- `fixtures/tts/*.mp3` — NOT YET generated; needed for wifi-off beat (A4)
- `SentenceAggregator`: local impl — swap for pipecat built-in if version supports it
- `reminders_client.py`: poller wired but not integrated into pipeline speech output yet (A5)
