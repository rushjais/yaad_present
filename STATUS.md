# STATUS.md — live build log

Update this in the **same commit** as any change. Session bookends: re-read before you code, update after.

## Contract
- Version: v1 — **FROZEN at Gate 0.** See CONTRACT.md.
- OpenAPI: `packages/shared/contract.openapi.json`

## Tracks

### Track A — Voice (Rushil)
- Phase: **A2 complete — all components live**
- **Validated this session:**
  - **MiniMax TTS:** ✅ `status_code=0`, `speech-02-hd`, `English_Graceful_Lady`, 29,440 bytes MP3, round-trip "Who is this person?" exact
  - **Groq STT:** ✅ English 0.38s exact
  - **Agent:** ✅ Silero VAD loaded, TrueFoundry LLM confirmed, pipeline linked, LiveKit connected `yaad-demo`, audio input started
  - **Pipeline:** ✅ `LiveKitInputTransport → VADProcessor → GroqWhisperSTTService → MemoryContextProcessor → SentenceAggregator → MiniMaxTTSService → LiveKitOutputTransport`
  - **answer_draft routing:** ✅ implemented — `answer_draft` populated → emit verbatim (temporal/absence path, skips LLM); `answer_draft` null → compose from items[] via LLM (semantic path)
- **Run command:** `arch -arm64 python3 -m app.agent`
- **Next:** A3 — full live echo test (speak → VAD → STT → memory → TTS playback); latency pass; A4 TTS clip cache for wifi-off.

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
- **MiniMax TTS:** ✅ working — `status_code=0`, `speech-02-hd`, `English_Graceful_Lady`, no GroupId, `api.minimax.io`.

## Language
**English only.** `lang` param exists in contract but always pass `"en"`. Hindi add-on later.

## [CONFIRM] open items
- **Moss:** ✅ on-device SDK confirmed (sub-10ms). Need `MOSS_PROJECT_ID` + `MOSS_PROJECT_KEY`.
- **Supabase:** keys needed — `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`.
- **MiniMax TTS (A):** ✅ confirmed working — `status_code=0`, 29KB MP3, round-trip STT exact.
- **LiveKit / Pipecat (A):** ✅ resolved. VADProcessor wired (`pipecat.processors.audio.vad_processor`), emits `VADUserStartedSpeakingFrame`/`VADUserStoppedSpeakingFrame`.
- **TrueFoundry LLM (A):** ✅ confirmed — `openai/gpt-4o-mini @ https://gateway.truefoundry.ai`
- **Groq STT (A):** ✅ confirmed (English 0.37s).
- **Twilio vs push:** for wander alerts (`location.py`).
