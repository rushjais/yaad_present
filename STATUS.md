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
  - **MiniMax TTS:** ✗ `status_code=1004` (login fail) — confirmed: Bearer header ✅, GroupId ✅, domain `api.minimax.io` ✅ — **key does not have T2A API access** (chat-only key). Need a key with TTS permissions from the MiniMax account.
  - **ffmpeg:** ✅ v8.1.1
- **Run command on this machine:** `arch -arm64 python3 -m app.agent`
- **Only remaining blocker:** MiniMax key with T2A API access. Get from MiniMax account settings → API Keys → ensure T2A is enabled.
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
- **MiniMax TTS:** key lacks T2A API access (status 1004). Auth format confirmed correct (Bearer + GroupId + api.minimax.io). Need MiniMax key with TTS permissions.

## Language
**English only.** `lang` param exists in contract but always pass `"en"`. Hindi add-on later.

## [CONFIRM] open items
- **Moss:** ✅ on-device SDK confirmed (sub-10ms). Need `MOSS_PROJECT_ID` + `MOSS_PROJECT_KEY`.
- **Supabase:** keys needed — `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`.
- **MiniMax TTS (A):** ✗ key lacks T2A access (status 1004). Auth format ✅ confirmed: `Bearer {key}`, `GroupId` in URL, domain `api.minimax.io`. Response format ✅ confirmed: `data["data"]["audio"]` (hex MP3). Get a key with TTS permissions from MiniMax account.
- **LiveKit / Pipecat (A):** ✅ resolved. VADProcessor wired (`pipecat.processors.audio.vad_processor`), emits `VADUserStartedSpeakingFrame`/`VADUserStoppedSpeakingFrame`.
- **TrueFoundry LLM (A):** ✅ confirmed — `openai/gpt-4o-mini @ https://gateway.truefoundry.ai`
- **Groq STT (A):** ✅ confirmed (English 0.37s).
- **Twilio vs push:** for wander alerts (`location.py`).
