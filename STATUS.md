# STATUS.md — live build log

Update this in the **same commit** as any change. Session bookends: re-read before you code, update after.

## Contract
- Version: v1 — **FROZEN at Gate 0.** See CONTRACT.md.
- OpenAPI: `packages/shared/contract.openapi.json`

## Tracks

### Track A — Voice (Rushil)
- Phase: **A2 ready — pipeline starts clean, LLM confirmed, LiveKit connecting**
- Done: pipeline scaffold + pipecat 1.3.0 import paths fixed, Groq STT ✅, LLM ✅ TrueFoundry confirmed, agent starts and links all processors, LiveKit connecting with real URL.
- **Validated this session:**
  - **Agent startup:** ✅ `LLM provider: TrueFoundry (openai/gpt-4o-mini @ https://gateway.truefoundry.ai)` — past LLM line, no import errors
  - **Pipeline links:** ✅ `LiveKitInputTransport → GroqWhisperSTTService → MemoryContextProcessor → SentenceAggregator → MiniMaxTTSService → LiveKitOutputTransport`
  - **LiveKit:** ✅ Connecting to wss://keepsake-y39026vu.livekit.cloud (real URL confirmed in .env)
  - **Groq STT English:** ✅ "Who is this person?" → exact transcript, **0.37s**
  - **MiniMax TTS:** ✗ `status_code=1004` "login fail: Please carry the API secret key" — key reaches server but auth format rejected. Try auth without `Bearer` prefix. May need a TTS-specific key (current key may be chat-only).
  - **ffmpeg:** ✅ v8.1.1
- **Run command on this machine:** `arch -arm64 python3 -m app.agent` (Python universal binary defaults to x86_64 slice; must force arm64 where pipecat/numpy packages are installed)
- **Deprecation warnings (non-blocking):** `PipelineTask` → `PipelineWorker`, `PipelineRunner` → `WorkerRunner.add_workers()` in pipecat 1.3.0. Works as-is; update in A3 pass.
- **Remaining blocker:** MiniMax TTS auth — try `Authorization: {key}` (no Bearer) and/or get TTS-specific key.
- **Next:** fix MiniMax auth → full echo test (speak → STT → LLM → TTS) → A3 latency pass.

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
- **MiniMax TTS:** status 1004 (auth format rejected). Decoder confirmed correct (hex). Pending auth fix.
- **VAD:** `SileroVADAnalyzer` imported but not yet wired — pipecat 1.3.0 removed VAD from transport params; now uses event-based `VADController`. STT buffer won't trigger until VAD emits `UserStartedSpeakingFrame`. Fix in A3.

## Language
**English only.** `lang` param exists in contract but always pass `"en"`. Hindi add-on later.

## [CONFIRM] open items
- **Moss:** ✅ on-device SDK confirmed (sub-10ms). Need `MOSS_PROJECT_ID` + `MOSS_PROJECT_KEY`.
- **Supabase:** keys needed — `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`.
- **MiniMax TTS (A):** ✗ status 1004 — try `Authorization: {key}` without `Bearer` prefix; or get TTS-specific key. Response format confirmed: `data["data"]["audio"]` (hex MP3).
- **LiveKit / Pipecat (A):** ✅ import paths fixed for 1.3.0. VAD wiring still needed (VADController, see Faked above).
- **TrueFoundry LLM (A):** ✅ confirmed — `openai/gpt-4o-mini @ https://gateway.truefoundry.ai`
- **Groq STT (A):** ✅ confirmed (English 0.37s).
- **Twilio vs push:** for wander alerts (`location.py`).
