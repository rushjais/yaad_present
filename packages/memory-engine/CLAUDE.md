# Track B — Memory Engine · CLAUDE.md
**Owner: Keshav** · Before you code: re-read this file + root STATUS.md. After you code: update them.

## Current phase: Gate 1 complete ✅
All modules built and verified. Supabase seeded. Moss index live. Real retrieval working.

## What's confirmed working right now
- `'Who is Leo?'` → Moss returns 3 results at score 0.94–1.00
- Supabase: all 12 tables created and populated
- Moss: SessionIndex connected, pushed to cloud, sub-10ms in-process
- Server stubs all endpoints — start with `uvicorn app.main:app --reload --port 8000`

## How to run
```bash
cd packages/memory-engine
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start server (from repo root — loads .env from there)
cd ../..
uvicorn packages.memory_engine.app.main:app --reload --port 8000

# Or from packages/memory-engine (simpler):
cd packages/memory-engine
uvicorn app.main:app --reload --port 8000

# Smoke test (server must be running on :8000)
cd packages/memory-engine
pytest tests/smoke_test.py -s -v

# Quick curl check
curl http://localhost:8000/health
curl -X POST http://localhost:8000/memory/query \
  -H 'Content-Type: application/json' \
  -d '{"text":"Who is Leo?","lang":"en"}'
```

## File responsibilities
| File | Status | What it does |
|---|---|---|
| `app/schemas.py` | ✅ BUILT | Pydantic contract — single source of truth. OpenAPI generated from this. |
| `app/main.py` | ✅ BUILT | FastAPI app. All 9 endpoints. try/except → real logic or fixture fallback. |
| `app/config.py` | ✅ BUILT | Pydantic settings. Accepts MOSS_PROJECT_ID or MOSS_ID. Strips whitespace from all values. |
| `app/db.py` | ✅ BUILT | Supabase client: write_memory, fetch_med_logs_today, fetch_upcoming_events, db_ping. |
| `app/moss_client.py` | ✅ BUILT | Moss SessionIndex: upsert (instant, local), upsert_batch, query, push_index. Metadata must be str→str. |
| `app/graph.py` | ✅ BUILT | 1-hop entity/episode/edge traversal from Supabase edges table. |
| `app/retrieval.py` | ✅ BUILT | Composed scoring: α·sem + β·recency + γ·salience + δ·graph_prox. |
| `app/grounding.py` | ✅ BUILT | Confidence gate τ=0.45 → safe refusal. Provenance on every item. |
| `app/temporal.py` | ✅ BUILT | Time-intent router: "pills today" → med_log, "is X coming" → events. |
| `app/capture.py` | ✅ BUILT | Explicit "remember this…" → extract entity → write Moss + Supabase. |
| `app/reminders.py` | ✅ BUILT | `/reminders/due`: rrule med schedule + 30-min event window. |
| `app/location.py` | ✅ BUILT | Wander safety: haversine vs safe_zone → reassure + Twilio alert. NEVER navigates. |
| `app/vision.py` | ✅ BUILT | Optional: image → VLM describe → Moss match. Fixture fallback. No OpenAI key yet. |
| `tests/smoke_test.py` | ✅ BUILT | 20-case grounding/latency table. |
| `scripts/seed_amma.py` | ✅ RAN | Already seeded. Do NOT re-run — will duplicate data. |
| `scripts/migrate_supabase.sql` | ✅ RAN | All 12 tables created. Safe to re-run (IF NOT EXISTS). |

## Moss — confirmed and wired
- **SDK**: `pip install moss`
- **Auth**: `MossClient(MOSS_PROJECT_ID, MOSS_PROJECT_KEY)` — both in `.env`
- **Gotcha**: `DocumentInfo.metadata` must be `dict[str, str]` — all values must be strings. Non-strings are json-serialized in `_clean_meta()`. This is a PyO3 constraint in the Moss SDK.
- **On-device**: SessionIndex runs in-process via Rust core — no sidecar, no network per query
- **wifi-off beat**: load the session before demo; then wifi can drop and queries still work

## Retrieval scoring
`score = α·semantic(0.5) + β·recency(0.25) + γ·salience(0.15) + δ·graph_prox(0.10)`
`recency = exp(−λ·Δt_hours)` where λ=0.01

## Grounding rule (HARD — do not weaken)
`grounded=True` only if top score ≥ τ=0.45. If `grounded=False`, `answer_draft` = safe refusal.
LLM in voice agent uses ONLY facts in `items[]`. Never invents people/events/dates.

## .env gotchas
- The `.env` file sometimes has spaces around `=` (e.g. `KEY= value`). config.py strips them automatically.
- Moss vars may appear as `MOSS_ID` / `MOSS_API_KEY` (legacy) — config.py aliases them to MOSS_PROJECT_ID / MOSS_PROJECT_KEY.
- Always read from `root/.env` (not packages/memory-engine/.env — there isn't one).

## Next steps for Track B
1. Start server + run smoke test: `uvicorn app.main:app --reload --port 8000` then `pytest tests/smoke_test.py -s -v`
2. Build `app/unsiloed.py` — upload PDF → extract structured data → `/memory/write` each entity. API details in STATUS.md. The intake flow: `POST /api/v1/playground/upload-document` (multipart, field `document`) → `document_id`; then `POST /api/v1/playground/chat-with-document` (**form data**, not JSON, fields `document_id` + `message`).
3. A↔B integration: support Rushil wiring `memory_client.py` to the live server

## Open items
- `unsiloed.py`: not yet built — API confirmed, see STATUS.md for call details
- `vision.py`: needs OpenAI key or on-device VLM — fixture fallback fires for now
- `capture.py`: explicit-trigger only — not live auto-capture
- Twilio SMS: fires with current keys but location alert not tested end-to-end
- TrueFoundry: key in `.env` but `TRUEFOUNDRY_BASE_URL` still unknown — not used by memory engine
