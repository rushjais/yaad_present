# STATUS.md — live build log

Update this in the **same commit** as any change. Session bookends: re-read before you code, update after.

## Contract
- Version: v1 — **FROZEN at Gate 0.** See CONTRACT.md.
- OpenAPI: `packages/shared/contract.openapi.json`

## Tracks

### Track A — Voice (Rushil)
- Phase: **A1 in progress** · Done: full pipeline scaffold (`agent.py`, `transports.py`, `stt_groq.py`, `tts_minimax.py`, `llm.py`, `memory_client.py`, `fallback.py`), **STT switched Deepgram → Groq Whisper** (Deepgram not working; Groq key confirmed), standalone `test_stt_tts.py`.
- Blocked: MiniMax response field [CONFIRM] (`audio_file` vs `data.audio`) — run `python -m app.test_stt_tts` to surface. LiveKit + TrueFoundry not yet tested.
- Next: run echo test → confirm MiniMax audio shape → A2 wire full pipeline → A3 latency pass.

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
- **voice-agent MiniMax TTS:** not yet validated end-to-end — run `test_stt_tts.py` first.

## Language
**English only.** Hindi / multilingual is a future add-on. `lang` param exists in the contract schema but is currently ignored — always pass `"en"`. No contract changes needed to add it later.

## [CONFIRM] open items
- **Moss:** ✅ confirmed — on-device SDK, SessionIndex, sub-10ms, instant upsert. Need `MOSS_PROJECT_ID` + `MOSS_PROJECT_KEY` from portal.getmoss.dev.
- **Supabase:** keys needed — `SUPABASE_URL` + `SUPABASE_SERVICE_KEY` (Track B seed + Track C).
- **MiniMax (A):** audio response field (`audio_file` vs `data.audio`) — run `test_stt_tts.py` to surface. English voice id + group id (group id confirmed in `.env`).
- **LiveKit / Pipecat (A):** exact pipecat version → verify import paths; VAD frame names (`UserStartedSpeakingFrame` / `UserStoppedSpeakingFrame`); livekit-api token generation import.
- **TrueFoundry (A):** `TRUEFOUNDRY_BASE_URL` + model name.
- **Groq (A):** ✅ confirmed working. ~~Deepgram~~ dropped.
- **Twilio vs push:** for wander alerts (`location.py`).
- **Pipecat `TextFrame` type (A):** confirm `OpenAILLMService` emits standard `TextFrame` so `SentenceAggregator` + `MiniMaxTTSService` catch it correctly.
