# STATUS.md — live build log

Update this in the **same commit** as any change. Session bookends: re-read before you code, update after.

## Contract
- Version: v1 — **FROZEN at Gate 0.** See CONTRACT.md.
- OpenAPI: `packages/shared/contract.openapi.json`

## Tracks

### Track A — Voice (Rushil)
- Phase: **A1 complete / A2 blocked on LLM key**
- Done: pipeline scaffold, Groq STT validated ✅, MiniMax response format confirmed (need fresh key), LLM provider auto-detection (TrueFoundry → OpenAI → Anthropic), latency logging per turn.
- **Validated this session:**
  - Groq STT English: ✅ "Who is this person?" → exact transcript, **0.46s**
  - Groq STT Hindi: ⚠️ needs Devanagari input — romanized text misidentified as Spanish (not blocking; English-only for now)
  - MiniMax TTS: ✗ `status_code=2049` (invalid API key). **Need fresh key from portal.minimax.chat.** Response format confirmed: `data["data"]["audio"]` — hex-encoded MP3.
  - ffmpeg: ✅ v8.1.1 installed
- **Blocker for A2:** need one LLM key (`OPENAI_API_KEY` or `ANTHROPIC_API_KEY` or TrueFoundry vars). Current `.env` has none configured.
- **Blocker for MiniMax TTS:** fresh API key needed (current key is invalid for T2A endpoint).
- Next: get LLM key → test full pipeline without LiveKit (agent.py with mocked transport) → get valid MiniMax key → A3 latency pass.

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
- **MiniMax TTS:** key invalid (status 2049). Response format known; decoder fixed (hex not base64). Working pending new key.
- **LLM:** no key configured — pipeline will raise on startup until one is set.

## Language
**English only.** `lang` param exists in contract but always pass `"en"`. Hindi add-on later.

## [CONFIRM] open items
- **Moss:** ✅ on-device SDK confirmed (sub-10ms). Need `MOSS_PROJECT_ID` + `MOSS_PROJECT_KEY`.
- **Supabase:** keys needed — `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`.
- **MiniMax TTS (A):** ✗ current key invalid (status 2049). Get fresh key from portal.minimax.chat. Response format confirmed: `data["data"]["audio"]` (hex MP3). Voice ID to validate with working key.
- **LLM (A):** set `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, or TrueFoundry vars. Any one unblocks the pipeline.
- **LiveKit / Pipecat (A):** import paths; VAD frame names — confirm when running full pipeline.
- **Groq STT (A):** ✅ confirmed working (English 0.46s). Hindi needs Devanagari text when re-enabled.
- **Twilio vs push:** for wander alerts (`location.py`).
