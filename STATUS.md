# STATUS.md — live build log

Update this in the **same commit** as any change. Session bookends: re-read before you code, update after.

## Contract
- Version: v1 — **FROZEN at Gate 0.** See CONTRACT.md.
- OpenAPI: `packages/shared/contract.openapi.json`

## Tracks

### Track A — Voice (Keshav)
- Phase: not started · Done: — · Blocked: waiting on MiniMax/Deepgram/TrueFoundry [CONFIRM]
- Memory engine stubs ready at :8000 — safe to code memory_client.py against now.

### Track B — Memory (Rushil)
- Phase: B0–B6 complete + Moss SDK wired
- Done: all modules built; moss_client.py now uses real SDK (SessionIndex, sub-10ms, instant upsert)
- Blocked: needs MOSS_PROJECT_ID + MOSS_PROJECT_KEY (from portal.getmoss.dev) + Supabase keys to run seed_amma.py
- Next: get keys → pip install moss → seed_amma.py → smoke_test.py → Gate 1

### Track C — Caregiver Web (Raghav)
- Phase: not started · Done: — · Blocked: waiting on Supabase keys
- OpenAPI + package CLAUDE.md ready — can scaffold and generate types.ts now.

## Faked / TODO real
- ALL `/memory/query`, `/memory/temporal` responses are fixture stubs until Moss keys are set and seed_amma.py is run.
- `vision.py` uses OpenAI VLM placeholder — on-device approach [CONFIRM].
- Twilio SMS in `location.py` won't fire without real keys.
- `capture.py` is explicit-trigger only ("remember this…") — not live auto-capture.
- fixtures/tts/*.mp3 files not yet generated — needed for wifi-off beat (voice agent caches TTS).

## Language
**English only.** Hindi / multilingual is a future add-on. `lang` param exists in the contract schema but is currently ignored — always English. No changes needed to wire it later.

## [CONFIRM] open items (resolve at office hours)
- **Moss**: ✅ confirmed — on-device SDK, SessionIndex, sub-10ms, instant upsert. Need MOSS_PROJECT_ID + MOSS_PROJECT_KEY from portal.getmoss.dev
- **Supabase**: keys needed — SUPABASE_URL + SUPABASE_SERVICE_KEY (Track B seed + Track C)
- **MiniMax**: English voice id, streaming TTS endpoint, group id (Track A)
- **Deepgram / LiveKit / Pipecat**: exact streaming STT + partial-transcript events. Docs: https://docs.moss.dev/docs/integrations/pipecat and https://docs.moss.dev/docs/integrations/livekit (Track A)
- **TrueFoundry**: base_url + model name (Track A)
- **Twilio vs push**: for wander alerts (Track B location.py)
