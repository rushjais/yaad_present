# STATUS.md — live build log

Update this in the **same commit** as any change. Session bookends: re-read before you code, update after.

## Contract
- Version: **v1 (FROZEN 2026-06-05, Gate 0)** — see `CONTRACT.md`. Source: `packages/memory-engine/app/schemas.py` → `packages/shared/contract.openapi.yaml`.

## Tracks
### Track A — Voice (Keshav)
- Phase: not started · Done: — · Blocked: — · Can start against the frozen contract + fixture memory-engine.
### Track B — Memory (Rushil)
- Phase: **B0 / Gate 0 DONE** · Done: schemas==contract, all 9 endpoints serving validated fixtures, OpenAPI exported, `seed_amma.py`, 10 smoke tests green, `uvicorn` clean. · Blocked: —
- Next: B1 Moss client + `/memory/write` instant upsert (replace fixtures endpoint-by-endpoint, keep shapes identical).
### Track C — Caregiver Web (Raghav)
- Phase: not started · Done: — · Blocked: — · Can generate `lib/types.ts` from `packages/shared/contract.openapi.yaml` now.

## Faked / TODO real
(log anything mocked for the demo here so it's never mistaken for working)
- **memory-engine: ALL 9 endpoints return canned fixtures** (`packages/memory-engine/fixtures/*.json`). No real Moss/Supabase/retrieval/grounding/temporal/vision/location logic yet — that's B1–B5.
- `/health` returns hardcoded `{moss_ok:true, db_ok:true, latency_ms:8.0}` — not a real probe yet.
- `seed_amma.py` writes JSON to `fixtures/seed_amma.json`; not yet pushed through `/memory/write` to a DB/Moss (no DB at Gate 0).

## [CONFIRM] open items
- Moss: on-device/WASM vs cloud, instant-upsert latency, cross-lingual embeddings, exact SDK calls
- MiniMax: Hindi voice id, streaming TTS, group id
- Deepgram / LiveKit / Pipecat exact calls
- TrueFoundry base_url + model
- Unsiloed parse API
