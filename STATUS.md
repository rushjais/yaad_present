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
- **Heads-up:** when Track B's B7 rebuild lands, `/memory/query` and `/memory/temporal` accept the same shape but return richer `items[]` (graph-expanded neighbors + edge-typed text). Treat `items[].text` as authoritative; do NOT reparse. `Intent`-routed responses may take up to ~200ms when the regex fast-path misses (LLM fallback) — fire speculatively on partial transcript as A3 already plans.

### Track B — Memory (Keshav)
- Phase: **B7 — Robustness rebuild (in progress, 2026-06-06)**
- Gate 1 (B0–B6) closed. Smoke test exposed: regex-only temporal misses paraphrases, graph proximity never surfaces neighbors, capture is string-match only, and the Moss `SessionIndex` does not reliably resume the cloud index after a server restart (`query("Leo")` → 0 results despite cloud push).
- **What's changing (executing now):**
  1. `scripts/reseed_moss.py` — idempotent Supabase → Moss reseed; verifies `query("Leo")` ≥0.9 before exit (workaround for the resume issue)
  2. `app/intent.py` + `app/time_window.py` — single understanding pass; hybrid regex + Groq fallback; relative-time parsing
  3. `app/temporal.py` rebuilt — per-medication routing, grounded negatives, time-windowed events
  4. `app/graph.py` + `app/retrieval.py` rebuilt — real 1-hop expansion into `items[]`, edge-type surfaced in text, relational shortcut, N² → dict
  5. `app/capture.py` rebuilt — Groq structured extraction, entity resolution before write (no more duplicate Leo), edge creation, capture-confidence gate
  6. `tests/robustness.py` — 30+ phrasings per beat; full pass = ship-ready
- **Behavioral / contract impact:**
  - `/memory/query` and `/memory/temporal` response shape **unchanged** (same `MemoryQueryResponse`) — but `items[]` may now contain graph-expanded neighbors with derived text. CONTRACT v1 still holds.
  - `/memory/capture` now writes edges + episodes in addition to the entity; `created_refs[]` will be longer.
  - p95 latency: regex fast-path stays <60ms; LLM-fallback path can spike to ~200ms — Track A should keep speculative firing.
- **No breaking changes for A or C.**
- Still needs: TrueFoundry base_url [CONFIRM] (unused by memory engine; tracked here for visibility)

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
| Unsiloed | ✅ LIVE | Base: `https://platformbackend.unsiloed.ai`. Auth: `Api-Key` header (not `Authorization: Bearer`). Upload: multipart `POST /api/v1/playground/upload-document` field `document` → `document_id`. Query: **form data** (not JSON) `POST /api/v1/playground/chat-with-document` fields `document_id` + `message` → structured response. Tested: extracted "Aspirin 100mg daily at 8am" from test PDF. |
| Deepgram | ❌ NO KEY | Using Groq Whisper instead. No action needed. |
| OpenAI | ❌ NO KEY | Optional — vision only. Skip for now. |

## Faked / TODO real
- `fixtures/*.json` — demo fallbacks; voice agent must serve these on 3s timeout
- `fixtures/tts/*.mp3` — NOT YET GENERATED — voice agent must pre-cache TTS for wifi-off beat
- `vision.py` — uses OpenAI placeholder; no key set; fixture fallback always fires
- `capture.py` — being rebuilt in B7. Until then: explicit-trigger only ("remember this…"), no entity resolution (duplicates Leo on every capture). Add-fact-live should go through Track C's web form until B7 ships.
- Twilio SMS fires but only if location alert is triggered — not tested end-to-end yet
- Moss `SessionIndex.session(index_name=...)` does NOT reliably resume the cloud index in a fresh process. Smoke test 2026-06-06 showed `query("Leo")` → 0 results despite a successful cloud push at seed time. Workaround: `scripts/reseed_moss.py` reseeds from Supabase before each demo. Track for SDK followup.
- `app/main.py` uses `try: real; except: fixture` — silent fixture fallback hides real errors as confident-looking demo answers. Will be gated behind `YAAD_DEMO_MODE=1` in a follow-up.

## Language
**English only.** `lang` param accepted everywhere but ignored — always English. Hindi is a future add-on; the field is in the contract so it wires later without a breaking change.

## Owner table (truth)
| Track | Owner | Notes |
|---|---|---|
| A — Voice | Rushil | Root CLAUDE.md previously listed Keshav here — corrected 2026-06-06 |
| B — Memory | Keshav | Root CLAUDE.md previously listed Rushil here — corrected 2026-06-06 |
| C — Caregiver Web | Raghav | Root CLAUDE.md previously listed "Person 3" — corrected 2026-06-06 |
