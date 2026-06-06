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
- Phase: B0–B6 complete (Gate 0 through eval harness)
- Done: schemas.py, main.py (fixture stubs), config.py, db.py, moss_client.py, graph.py, retrieval.py, grounding.py, temporal.py, capture.py, reminders.py, location.py, vision.py, smoke_test.py, seed_amma.py, fixtures/*, docker-compose.yml, .env.example, CONTRACT.md frozen, package CLAUDE.md for all 3 tracks
- Blocked: Moss [CONFIRM] — moss_client.py uses REST; swap for SDK at office hours. Real retrieval won't work until Moss keys are set.
- Next: confirm Moss SDK → wire real retrieval → run seed_amma.py → run smoke_test.py

### Track C — Caregiver Web (Raghav)
- Phase: not started · Done: — · Blocked: waiting on Supabase keys
- OpenAPI + package CLAUDE.md ready — can scaffold and generate types.ts now.

## Faked / TODO real
- ALL `/memory/query`, `/memory/temporal` responses are fixture stubs until Moss keys are set and seed_amma.py is run.
- `vision.py` uses OpenAI VLM placeholder — on-device approach [CONFIRM].
- Twilio SMS in `location.py` won't fire without real keys.
- `capture.py` is explicit-trigger only ("remember this…") — not live auto-capture.
- fixtures/tts/*.mp3 files not yet generated — needed for wifi-off beat (voice agent caches TTS).

## [CONFIRM] open items (resolve at office hours)
- **Moss**: on-device/WASM vs cloud, exact SDK calls (moss_client.py built for REST), cross-lingual embedding support, instant-upsert latency target
- **MiniMax**: Hindi voice id, streaming TTS endpoint, group id (Track A)
- **Deepgram / LiveKit / Pipecat**: exact streaming STT call + partial-transcript events (Track A)
- **TrueFoundry**: base_url + model name (Track A)
- **Unsiloed**: parse API for document ingestion (Track C stretch)
- **Twilio vs push**: for wander alerts (Track B location.py)
