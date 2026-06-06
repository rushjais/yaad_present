# STATUS.md — live build log

Update this in the **same commit** as any change. Session bookends: re-read before you code, update after.

## Contract
- Version: v1 — **FROZEN at Gate 0.** See CONTRACT.md.
- OpenAPI: `packages/shared/contract.openapi.json`

## Tracks

### Track A — Voice (Rushil)
- Phase: A0 — ready to start
- Done: memory engine live at :8000, real retrieval verified, all keys confirmed
- **Start here:** scaffold `agent.py` + wire Groq STT + MiniMax TTS echo loop
- Unblocked on: Groq (LLM + STT), MiniMax TTS, LiveKit keys all in `.env`
- Still needs: LiveKit/Pipecat exact transport setup [CONFIRM at office hours]; TrueFoundry base_url [CONFIRM]

### Track B — Memory (Keshav)
- Phase: Gate 1 complete ✅
- Done: all B0–B6 modules built and tested; Supabase seeded (3 persons, 2 places, 2 meds, 3 events, 3 stories, 5 edges, safe_zone); Moss index populated and pushed to cloud; 'Who is Leo?' returns score 1.000
- Next: start server, run smoke_test.py, then support A↔B integration

### Track C — Caregiver Web (Raghav)
- Phase: C0 — ready to start
- Done: Supabase tables created, seeded with Amma's life. OpenAPI + CLAUDE.md ready.
- **Start here:** get `.env` from Keshav (SUPABASE_URL + SUPABASE_SERVICE_KEY), generate types.ts, scaffold Next.js
- Do NOT re-run seed_amma.py — data is already there

## API keys status
| Service | Status | Notes |
|---|---|---|
| Moss | ✅ LIVE | SessionIndex connected, sub-10ms, index populated |
| Supabase | ✅ LIVE | All 12 tables exist, seeded. URL + key in `.env`. |
| Groq | ✅ LIVE | 16 models. Use for LLM (`llama-3.3-70b-versatile`) and STT (`whisper-large-v3`). |
| MiniMax TTS | ✅ LIVE | Use `api.minimaxi.chat` (NOT api.minimax.chat). Model: `speech-02-hd`. Voice: `Wise_Woman`. |
| Twilio | ✅ LIVE | Account active. SMS fires with current keys. |
| LiveKit | ⚠️ UNVERIFIED | Keys in `.env`. wss:// URL not HTTP-testable. Will verify when agent connects. |
| TrueFoundry | ❌ NEEDS base_url | Key in `.env` but workspace URL empty. Use Groq until confirmed. |
| Unsiloed | ❌ NEEDS API URL | `api.unsiloed.ai` DNS fails. `app.unsiloed.ai` is web UI only. Check hackathon Slack. |
| Deepgram | ❌ NO KEY | Using Groq Whisper instead. No action needed. |
| OpenAI | ❌ NO KEY | Optional — vision only. Skip for now. |

## Faked / TODO real
- `fixtures/*.json` — demo fallbacks; voice agent must serve these on 3s timeout
- `fixtures/tts/*.mp3` — NOT YET GENERATED — voice agent must pre-cache TTS for wifi-off beat
- `vision.py` — uses OpenAI placeholder; no key set; fixture fallback always fires
- `capture.py` — explicit-trigger only ("remember this…"), not auto-capture from every utterance
- Twilio SMS fires but only if location alert is triggered — not tested end-to-end yet

## Language
**English only.** `lang` param accepted everywhere but ignored — always English. Hindi is a future add-on; the field is in the contract so it wires later without a breaking change.
