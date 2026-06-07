# STATUS.md — live build log

Update this in the **same commit** as any change. Session bookends: re-read before you code, update after.

## Contract
- Version: v1 — **FROZEN at Gate 0.** See CONTRACT.md.
- OpenAPI: `packages/shared/contract.openapi.json`

## Tracks

### Track A — Voice (Rushil)
- Phase: **A2 complete — VAD live, pipeline fully connected, waiting on MiniMax key**
- **Validated this session:**
  - **Agent startup:** ✅ VAD loads (`Silero VAD model loaded`), LLM `TrueFoundry (openai/gpt-4o-mini @ https://gateway.truefoundry.ai)`, LiveKit **fully connected** (`wss://keepsake-y39026vu.livekit.cloud`), audio input started
  - **Pipeline:** ✅ `LiveKitInputTransport → VADProcessor → GroqWhisperSTTService → MemoryContextProcessor → SentenceAggregator → MiniMaxTTSService → LiveKitOutputTransport`
  - **VAD params:** `confidence=0.7 start_secs=0.2 stop_secs=0.2 min_volume=0.6` — active
  - **Groq STT:** ✅ English 0.42s exact transcript
  - **MiniMax TTS:** ✗ `status_code=1004` — full wire confirmed: URL `https://api.minimax.io/v1/t2a_v2` ✅ (no GroupId), model `speech-02-hd` ✅, voice `English_Graceful_Lady` ✅, Bearer ✅. **Root cause: key in root `.env` is `sk-apii...` (missing `-` after `api`; should be `sk-api-iH6H2...`).** The voice-agent `.env` was deleted and tests now fall through to root `.env` which has a malformed key.
  - **ffmpeg:** ✅ v8.1.1
- **Run command on this machine:** `arch -arm64 python3 -m app.agent`
- **Only remaining blocker:** Fix MiniMax key in root `.env`. Current value starts `sk-apii...` (missing `-`). Correct value from sponsor: `sk-api-iH6H2XXH1_l8sc41GIfQ...`. Create `packages/voice-agent/.env` with the correct key so tests don't fall back to root `.env`.
- **Next:** swap in working MiniMax key → full echo test (speak → STT → LLM → TTS playback) → A3 latency pass.

### Track B — Memory (Keshav)
- Phase: **B0–B6 complete + Moss SDK wired**
- Done: all modules built; `moss_client.py` now uses real SDK (SessionIndex, sub-10ms, instant upsert).
- Blocked: needs `MOSS_PROJECT_ID` + `MOSS_PROJECT_KEY` (from portal.getmoss.dev) + Supabase keys to run `seed_amma.py`.
- Next: get keys → `pip install moss` → `seed_amma.py` → `smoke_test.py` → Gate 1.

### Track C — Caregiver Web (Raghav)
- Phase: not started · Done: — · Blocked: waiting on Supabase keys.
- OpenAPI + package CLAUDE.md ready — can scaffold and generate `types.ts` now.

## Faked / TODO real
- ALL `/memory/query`, `/memory/temporal` responses are fixture stubs until Moss keys are set and `seed_amma.py` is run.
- `vision.py` uses OpenAI VLM placeholder — on-device approach [CONFIRM].
- Twilio SMS in `location.py` won't fire without real keys.
- `capture.py` is explicit-trigger only ("remember this…") — not live auto-capture.
- `fixtures/tts/*.mp3` not yet generated — needed for wifi-off beat (voice agent caches TTS clips).
- **MiniMax TTS:** status 1004 persists. Code fully correct per .io spec (no GroupId, speech-02-hd, English_Graceful_Lady, Bearer). Root cause: key in root `.env` = `sk-apii...` (malformed — missing `-`). Fix: put correct key `sk-api-iH6H2...` in `packages/voice-agent/.env`.

## Language
**English only.** `lang` param exists in contract but always pass `"en"`. Hindi add-on later.

## [CONFIRM] open items
- **Moss:** ✅ on-device SDK confirmed (sub-10ms). Need `MOSS_PROJECT_ID` + `MOSS_PROJECT_KEY`.
- **Supabase:** keys needed — `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`.
- **MiniMax TTS (A):** ✗ status 1004. Full spec applied: `api.minimax.io` (no GroupId), `speech-02-hd`, `English_Graceful_Lady`, `output_format: hex`, Bearer. Key in root `.env` is `sk-apii...` (missing `-`); should be `sk-api-iH6H2...`. Create `packages/voice-agent/.env` with the correct key.
- **LiveKit / Pipecat (A):** ✅ resolved. VADProcessor wired (`pipecat.processors.audio.vad_processor`), emits `VADUserStartedSpeakingFrame`/`VADUserStoppedSpeakingFrame`.
- **TrueFoundry LLM (A):** ✅ confirmed — `openai/gpt-4o-mini @ https://gateway.truefoundry.ai`
- **Groq STT (A):** ✅ confirmed (English 0.37s).
- **Twilio vs push:** for wander alerts (`location.py`).
