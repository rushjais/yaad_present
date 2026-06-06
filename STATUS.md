# STATUS.md — live build log

Update this in the **same commit** as any change. Session bookends: re-read before you code, update after.

## Contract
- Version: v1 — **FROZEN at Gate 0.** See CONTRACT.md.
- OpenAPI: `packages/shared/contract.openapi.json`

## Tracks

### Track A — Voice (Rushil)
- Phase: not started · Done: — · Blocked: waiting on MiniMax/Deepgram/TrueFoundry [CONFIRM]
- Memory engine stubs ready at :8000 — safe to code memory_client.py against now.

### Track B — Memory (Keshav)
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

## [CONFIRM] open items
- **Moss**: ✅ CONFIRMED — SessionIndex connects, sub-10ms. Keys in .env.
- **Supabase**: ✅ CONFIRMED — all 12 tables created, 0 rows (needs seed_amma.py).
- **Groq**: ✅ CONFIRMED — 16 models, key works.
- **MiniMax**: ✅ CONFIRMED — use `api.minimaxi.chat` (NOT api.minimax.chat). TTS works with `speech-02-hd` + `voice_id`. English voice: `Wise_Woman`. Audio confirmed 84KB for short text. config.py has `minimax_base_url` defaulting to correct endpoint.
- **Twilio**: ✅ CONFIRMED — account active, SMS ready.
- **TrueFoundry**: ❌ NEEDS base_url + model name. Key in .env (`default-aeeqzarfyu46mbck1y9iyyf7`) but workspace URL unknown — ask at office hours or from hackathon materials. Using Groq as primary LLM in the meantime.
- **Unsiloed**: ❌ `api.unsiloed.ai` does not resolve. `app.unsiloed.ai` is the web UI (returns HTML). Need correct API base URL — check hackathon Slack / onboarding materials.
- **Deepgram**: ❌ No key. Using Groq for STT (Track A).
- **LiveKit/Pipecat**: Keys in .env, wss:// URL not HTTP-testable — will verify when voice agent starts.
