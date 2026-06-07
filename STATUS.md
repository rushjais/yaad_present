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
- Phase: **Archetype router rebuild in progress (2026-06-07)**.
- B7.2 enrichment is legacy. Root cause recorded: Groq rewrote sparse chunks at index time and could attribute another person's biography to the wrong row. `fixtures/enriched_chunks.json` is removed; `scripts/reseed_moss.py` now indexes only stories and `episodes(kind='captured_fact')`.
- New architecture: `router.py` dispatches to identity, relational, temporal_med, temporal_event, preference, remember, or episodic. Structural archetypes use Supabase and `edges_cache`; Moss is only the episodic fallback. Groq is restricted to router classification fallback and capture extraction.
- Contract impact: response shapes unchanged. Additive schema fields: `persons.preferences`, `persons.face_embedding`, `stories.category`; `/health` also reports `moss_doc_count`.
- Fixture fallbacks are gated by `YAAD_DEMO_MODE=1`; default behavior is loud HTTP 500 on real errors.
- **Unsiloed ingestion shipped (2026-06-06):** new `POST /ingest/document` endpoint. Upload a medical PDF → Unsiloed parses → Groq normalizes into typed Yaad records → write_memory + Moss upsert. Smoke test (`scripts/smoke_unsiloed.py`) extracts Aspirin + Metoprolol + Dr. Patel + follow-up appointment from a synthetic discharge summary and they're queryable on the next turn. Earns the §18 Unsiloed sponsor checkbox. Field-name quirks logged in `app/unsiloed.py` (multipart field is `document`, form field is `message`).
- **Bug fixed in passing:** `db.write_memory` was popping `source`/`added_by` AFTER `**payload` spread, so any caller passing those keys hit PGRST204. Pre-existing latent bug; surfaced by ingest, fixed by popping before spread. No existing call sites affected.
- Pitch language updated: dropped "memory graph" framing → **"a living memory that lives inside the agent"** (instant updates, on-device, sub-10ms).
- New tests added: general query corpus, sparse-person hallucination regression, grounding provenance, and latency guard.
- Verification (2026-06-07): `smoke_test.py`, `robustness.py`, `test_general_queries.py`, `test_grounding_integrity.py`, and `test_no_hallucination.py` passed 105/105 against local server; `test_latency.py` passed 1/1. Structural p95 was ~27ms client-side in the run.
- Note: live Supabase has not yet had the additive SQL migration applied (`persons.preferences`, `persons.face_embedding`, `stories.category`). The engine includes deterministic fallback parsing for existing seed rows until the Supabase SQL editor migration is applied; JSONB values take precedence once present.
- **What shipped:** intent classifier (regex+Groq), time-window parser, temporal routing w/ per-medication, capture w/ structured extraction + review queue, Moss session self-heal on startup. Full list in previous STATUS entries.
- **Contract impact:** shapes unchanged. `items[]` may contain graph-expanded neighbors. CONTRACT v1 holds — no breaking changes for A or C.
- **Latency:** regex fast-path sub-20ms. LLM-fallback path ~300ms — Track A fires speculatively on partial transcript.
- **Caveats:** auto-capture still creates `pending_review` proposals plus searchable `captured_fact`; only confirmed captured facts are in Moss.

### Track C — Caregiver Web (Raghav)
- Phase: C4 — care dashboard (next up)
- Done: C0 ✅ · C1 ✅ · C3 ✅ (graph + timeline)
  - C3: `/graph` — react-force-graph-2d, SSR-disabled, Supabase direct query, 5 clean nodes (Leo/Sarah/Amma/Home/Park), 5 edges
  - C3: `/timeline` — date picker, GET /memory/timeline proxy, vertical timeline blocks
  - `.env.local` symlinks to root `.env` for server-side Supabase access
  - C4: medical records upload via Unsiloed — `POST /ingest/document` proxied through `/api/engine/ingest/document/route.ts` (dedicated route, bypasses broken Next.js rewrite for multipart); progressive stage labels during upload
- Next: C5 safety → C6 architecture diagram
- Do NOT re-run seed_amma.py — data is already in Supabase
- ✅ add-fact-live beat fixed (fa02f3c): `POST /memory/write` now upserts to Moss in the same request. Write → queryable in <1s confirmed (837ms in Keshav's test).
- Ingest normalization uses OpenAI gpt-4o-mini (not Groq) to avoid daily TPD limit conflict with voice agent STT

## API keys status
| Service | Status | Notes |
|---|---|---|
| Moss | ✅ LIVE | SessionIndex connected, sub-10ms, index populated |
| Supabase | ✅ LIVE | All 12 tables exist, seeded. URL + key in `.env`. |
| Groq | ⚠ LIVE w/ quota tight | 16 models. Use for LLM (`llama-3.3-70b-versatile`) and STT (`whisper-large-v3`). **2026-06-06: hit 100k TPD on 70b**; rewrite + enrichment moved to `llama-3.1-8b-instant` (separate quota). Reseed enrichment is serialized w/ 0.4s pause to stay under 8b's 6000 TPM. Upgrade to Dev Tier before demo if running multiple test cycles. |
| MiniMax TTS | ✅ LIVE | Track A confirmed `api.minimax.io` (status_code=0, 29KB MP3). Track B docs recommend `api.minimaxi.chat`. Both work; code uses `api.minimax.io`. Model: `speech-02-hd`. |
| Twilio | ❌ REMOVED | Trial toll-free numbers require 3-7d verification before US carrier delivery. Replaced with email-to-SMS via carrier gateway (Gmail SMTP → `<number>@msg.fi.google.com`). Instant, free, looks like a normal SMS. See `location._send_sms_alerts`. |
| Gmail SMTP (email-to-SMS) | ✅ LIVE & WIRED | `EMAIL_FROM` + `EMAIL_APP_PASSWORD` in `.env`. `YAAD_DEMO_RECIPIENT_EMAIL` override routes every alert to one address during demo. End-to-end smoke green: ping → `alerts` row → SMTP send → SMS on Google Fi phone. |
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
- Wander alert delivery: Gmail SMTP → `@msg.fi.google.com` (carrier gateway). End-to-end smoke green; verified SMS landed on Google Fi phone. Twilio path removed (toll-free verification was the blocker).
- Moss `SessionIndex.session()` does NOT reliably resume cloud index in a fresh process. Workaround: `scripts/reseed_moss.py` reseeds from Supabase before each demo.
- `app/main.py` fixture fallback is now gated behind `YAAD_DEMO_MODE=1`.

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
- ~~**Twilio vs push:** for wander alerts~~ — resolved 2026-06-06: email-to-SMS via Gmail SMTP + carrier gateway, smoke green.
