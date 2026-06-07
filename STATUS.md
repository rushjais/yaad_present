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
  - **--local mode:** ✅ `arch -arm64 python3 -m app.agent --local` — sounddevice mic/speakers, no LiveKit needed
- **Run:** `arch -arm64 python3 -m app.agent` (LiveKit) or `arch -arm64 python3 -m app.agent --local` (mic/speakers)
- **Next:** A3 — latency pass (fire memory speculatively on partial transcript; B7 LLM-fallback path can spike ~300ms); A4 pre-cache TTS clips for wifi-off beat.
- **Heads-up from Track B:** B7 `items[]` may contain graph-expanded neighbors with derived text — treat `items[].text` as authoritative, do NOT reparse. Intent-routed responses may take ~200ms on LLM fallback; speculative fire on partial transcript handles this.

### Track B — Memory (Keshav)
- Phase: **B7.2 — category enrichment + rewrite fallback complete (2026-06-06)** ✅
  - See `MEMORY_V2_README.md` for B7.1 background; `packages/memory-engine/CLAUDE.md` for the B7.2 details.
- 39/39 robustness green (added beat 6: abstract preferences). All 5 demo beats + the new preference beat ground correctly; anti-confab cases all safe-refuse.
- **B7.2 (2026-06-06):** fixed "favorite music" → safe-refusal regression. Two layers: (1) seed-time chunk enrichment via Groq 8b labels each preference with its category as natural prose ("Music: Amma listens to Bollywood songs from the 1960s. Drinks: jasmine tea. Activities: Lullwater Park walk"), cached in `fixtures/enriched_chunks.json` so server startup pays 0 LLM cost; (2) runtime query-rewrite fallback in `app/retrieval.py` fires only when first-pass returns 0 above τ — entity-anchored, same τ on rescue path (no laxer gate), and the rewrite Groq prompt is also an anti-confab gate (returns `[]` for general-knowledge queries); (3) topic-word check refuses adversarial queries whose content noun ("color", "sport", "horror") doesn't appear in any returned chunk. Latency unchanged on happy path; rewrite fallback adds ~300ms only when fired.
- **Unsiloed ingestion shipped (2026-06-06):** new `POST /ingest/document` endpoint. Upload a medical PDF → Unsiloed parses → Groq normalizes into typed Yaad records → write_memory + Moss upsert. Smoke test (`scripts/smoke_unsiloed.py`) extracts Aspirin + Metoprolol + Dr. Patel + follow-up appointment from a synthetic discharge summary and they're queryable on the next turn. Earns the §18 Unsiloed sponsor checkbox. Field-name quirks logged in `app/unsiloed.py` (multipart field is `document`, form field is `message`).
- **Bug fixed in passing:** `db.write_memory` was popping `source`/`added_by` AFTER `**payload` spread, so any caller passing those keys hit PGRST204. Pre-existing latent bug; surfaced by ingest, fixed by popping before spread. No existing call sites affected.
- Pitch language updated: dropped "memory graph" framing → **"a living memory that lives inside the agent"** (instant updates, on-device, sub-10ms).
- **What changed in v2:**
  1. Killed graph expansion + relational-walk + 4-layer guards. Single hard τ=0.82 relevance gate.
  2. Better Moss chunks: relationships baked into entity text at seed time ("Leo. Amma's grandson, Sarah's son. 22 years old…").
  3. Family-overview chunk for "tell me about my family."
  4. Optional 1-hop query expansion when user mentions multiple entities.
  5. `answer_draft` for semantic queries = top chunk text (LLM rewrites). Temporal still pre-composes (grounded negatives need exact phrasing).
  6. `scripts/reseed_moss.py --wipe` deletes cloud index before reseeding. Use before demo or after dirty test runs.
  7. `graph.py` trimmed to ~50 lines — entity_text cache only (for capture).
- Event writes now backfill `participant_ids`: `/memory/write` resolves person names mentioned in event title/notes through Moss (first person hit in top 8 with score ≥0.85), including lowercase mentions matched against known names/aliases.
- `scripts/reseed_moss.py` now preserves stored `person.relationship` in chunks when no edge-derived relationship phrase exists, so newly added people like Aishani keep relationship context after a wipe/reseed.
- **What shipped:** intent classifier (regex+Groq), time-window parser, temporal routing w/ per-medication, capture w/ structured extraction + review queue, Moss session self-heal on startup. Full list in previous STATUS entries.
- **Contract impact:** shapes unchanged. `items[]` may contain graph-expanded neighbors. CONTRACT v1 holds — no breaking changes for A or C.
- **Latency:** regex fast-path sub-20ms. LLM-fallback path ~300ms — Track A fires speculatively on partial transcript.
- **Caveats:** auto-capture not auto-committing (`pending_review`). Reliable add-fact-live = Track C web form. Implicit-entity allowlist is hand-curated.

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
| Groq | ⚠ LIVE w/ quota tight | 16 models. Use for LLM (`llama-3.3-70b-versatile`) and STT (`whisper-large-v3`). **2026-06-06: hit 100k TPD on 70b**; rewrite + enrichment moved to `llama-3.1-8b-instant` (separate quota). Reseed enrichment is serialized w/ 0.4s pause to stay under 8b's 6000 TPM. Upgrade to Dev Tier before demo if running multiple test cycles. |
| MiniMax TTS | ✅ LIVE | Track A confirmed `api.minimax.io` (status_code=0, 29KB MP3). Track B docs recommend `api.minimaxi.chat`. Both work; code uses `api.minimax.io`. Model: `speech-02-hd`. |
| Twilio | ✅ LIVE | Account active. SMS fires with current keys. |
| LiveKit | ✅ LIVE | Connected to `wss://keepsake-y39026vu.livekit.cloud`, room `yaad-demo` confirmed. |
| TrueFoundry | ✅ LIVE | `gateway.truefoundry.ai`, model `openai/gpt-4o-mini`. Confirmed by Track A. |
| Unsiloed | ✅ LIVE & WIRED | Base: `https://platformbackend.unsiloed.ai`. Auth: `Api-Key` header. Upload field: multipart `document` (NOT `file`). Chat field: form-data `message` (NOT `question`). Wired into memory engine via `POST /ingest/document` — see `app/unsiloed.py` + `app/ingest.py`. End-to-end smoke green: discharge PDF → 2 meds + 1 event + 2 persons + 1 story → all queryable. |
| Deepgram | ❌ NO KEY | Using Groq Whisper instead. No action needed. |
| OpenAI | ❌ NO KEY | Optional — vision only. Skip for now. |

## Faked / TODO real
- `fixtures/*.json` — demo fallbacks; voice agent serves these on 3s timeout
- `fixtures/tts/*.mp3` — **NOT YET GENERATED** — voice agent must pre-cache TTS for wifi-off beat (A4)
- `vision.py` — uses OpenAI placeholder; no key set; fixture fallback always fires
- `capture.py` — B7 rebuilt but auto-capture not auto-committing; `captured_fact` retrievable immediately, structured proposal in `episodes(kind='pending_review')` for caregiver confirmation. Reliable add-fact-live = Track C web form.
- Twilio SMS fires but location alert not tested end-to-end yet
- Moss `SessionIndex.session()` does NOT reliably resume cloud index in a fresh process. Workaround: `scripts/reseed_moss.py` reseeds from Supabase before each demo.
- `app/main.py` silent fixture fallback (`try: real; except: fixture`) hides real errors — will gate behind `YAAD_DEMO_MODE=1` in follow-up.

## Language
**English only.** `lang` param accepted everywhere but ignored — always English. Hindi is a future add-on; the field is in the contract so it wires later without a breaking change.

## Owner table
| Track | Owner | Notes |
|---|---|---|
| A — Voice | Rushil | |
| B — Memory | Keshav | |
| C — Caregiver Web | Raghav | Root CLAUDE.md previously listed "Person 3" — corrected 2026-06-06 |

## [CONFIRM] remaining open items
- **fixtures/tts/*.mp3:** pre-cache TTS clips for wifi-off beat (A4) — not yet generated
- **TrueFoundry base_url (B):** unused by memory engine; tracked for visibility
- **Twilio vs push:** for wander alerts (`location.py`) — not tested end-to-end
