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
- Phase: **B7.1 — Chunks + τ simplification complete (2026-06-06)** ✅
  - See `MEMORY_V2_README.md` for the teammate-facing summary of what changed and why.
- 43/43 tests green: 15 smoke + 28 robustness, p95 = 22ms.
- Pitch language updated: dropped "memory graph" framing → **"a living memory that lives inside the agent"** (instant updates, on-device, sub-10ms).
- **What changed in v2 (in addition to all the v1 work below):**
  1. Killed graph expansion + relational-walk + 4-layer guards. Single hard τ=0.82 relevance gate.
  2. Better Moss chunks: relationships baked into entity text at seed time ("Leo. Amma's grandson, Sarah's son. 22 years old…"). Moss semantic match now answers relational questions without edge walking.
  3. Family-overview chunk for "tell me about my family" — guarantees a high-score target for kinship queries that have no proper noun.
  4. Optional 1-hop query expansion when the user mentions multiple entities (e.g. "Did Leo get into Stanford?"). Replaces graph traversal; still on Moss.
  5. `answer_draft` for semantic queries is now the top chunk text — the voice agent's LLM rewrites it. Temporal still pre-composes (grounded negatives need exact phrasing).
  6. `scripts/reseed_moss.py --wipe` deletes the cloud index before reseeding. Use before demo or after dirty test runs.
  7. `graph.py` trimmed to ~50 lines — entity_text cache only (for capture).
- Event writes now backfill `participant_ids`: `/memory/write` resolves person names mentioned in an event title/notes through Moss (top person hit ≥0.85), including lowercase mentions matched against known names/aliases, then updates the Supabase event row before returning.
- Pre-v2 (still in place): intent classifier (regex+Groq), time-window parser, temporal routing with per-medication, capture w/ structured extraction + review queue, Moss session self-heal on startup.
- **What shipped:**
  1. ✅ `scripts/reseed_moss.py` — Supabase → Moss reseed; runs on server startup hook so each fresh process self-heals (Moss `SessionIndex.session()` does NOT auto-resume the cloud index)
  2. ✅ `app/intent.py` + `app/time_window.py` — single understanding pass; regex fast-path (5 demo phrasings, <1ms) + Groq llama-3.3-70b LLM fallback; relative-time parser (today/yesterday/this morning/last week/before lunch)
  3. ✅ `app/temporal.py` rebuilt — Intent-driven routing, per-medication ("heart pill" → Metoprolol filter), grounded negatives ("you haven't taken your heart pill yet"), time-windowed events
  4. ✅ `app/graph.py` + `app/retrieval.py` rebuilt — edge cache loaded at startup (kills N+1 Supabase round-trips), real 1-hop neighbor expansion into `items[]`, edge-typed sentence generation ("Leo is your grandson"), relational shortcut for 1-entity queries, semantic-floor + implicit-entity guards prevent confabulation
  5. ✅ `app/capture.py` rebuilt (limited) — Groq structured extraction, entity resolution against Moss (top score ≥0.85 → linked), writes BOTH a `captured_fact` (Moss-indexed, retrievable) AND a `pending_review` episode (caregiver confirms before any new entity/edge writes to the canonical tables)
  6. ✅ `tests/robustness.py` — 28 cases across 5 beats; per-beat scorecard
- **Contract impact:** `/memory/query`, `/memory/temporal`, `/memory/capture` response shapes unchanged. `items[]` may now contain graph-expanded neighbors with derived text. CONTRACT v1 holds — no breaking changes for A or C.
- **Latency:** regex fast-path stays sub-20ms server-side (well under contract). LLM-fallback path can spike to ~300ms — Track A should still fire speculatively on partial transcript.
- **Caveats / for the demo:**
  - Auto-capture is intentionally NOT auto-committing. `captured_fact` is retrievable immediately; the structured proposal sits in `episodes(kind='pending_review')` for caregiver confirmation. This is the "demo without the duplicate-Leo risk" path.
  - The reliable add-fact-live beat = Track C's web form (writes directly via `/memory/write`). Capture is the *bonus* "look, it learned from the conversation" beat.
  - Implicit-entity allowlist in `retrieval.py` is hand-curated kinship/place words; extend if Amma's seed grows new entity classes.
- Still needs: TrueFoundry base_url [CONFIRM] (unused by memory engine; tracked here for visibility)

### Track C — Caregiver Web (Raghav)
- Phase: C1 — in progress
- Done: C0 complete — Next.js 15 scaffold, lib/types.ts (from contract), lib/api.ts (all 8 endpoints), page stubs for /, /memories, /timeline, /graph, /safety. Build green, tsc clean.
- Next: C1 add-memory forms (person / event / medication / story → POST /memory/write) — this is the add-fact-live beat
- Do NOT re-run seed_amma.py — data is already in Supabase

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
