# Track B — Memory Engine · CLAUDE.md
**Owner: Rushil** · Before you code: re-read this file + root STATUS.md. After you code: update them.

## Current phase
B1 complete (db.py + moss_client.py). B2–B6 complete (graph, retrieval, grounding, temporal, capture, reminders, location, vision, smoke_test). Gate 0 stubs live on all endpoints.

## File responsibilities
| File | Status | What it does |
|---|---|---|
| `app/schemas.py` | ✅ BUILT | Pydantic contract — single source of truth. Generate OpenAPI from this. |
| `app/main.py` | ✅ BUILT | FastAPI app. Fixture stubs on all endpoints; lazy-imports real modules. |
| `app/config.py` | ✅ BUILT | Pydantic settings from .env. Scoring weights, confidence threshold τ. |
| `app/db.py` | ✅ BUILT | Supabase client: write_memory, fetch helpers, db_ping. |
| `app/moss_client.py` | ✅ BUILT [CONFIRM] | Moss HTTP client: upsert, upsert_batch, query, ping. Swap for SDK if provided. |
| `app/graph.py` | ✅ BUILT | 1-hop entity/episode/edge traversal from Supabase edges table. |
| `app/retrieval.py` | ✅ BUILT | Composed scoring: α·sem + β·recency + γ·salience + δ·graph_prox. |
| `app/grounding.py` | ✅ BUILT | Confidence gate τ → safe refusal. Provenance on every item. Anti-confabulation. |
| `app/temporal.py` | ✅ BUILT | Time-intent router: pills_today → med_log, upcoming → events, fallback → retrieval. |
| `app/capture.py` | ✅ BUILT | Explicit "remember this…" trigger → extract → write Moss + Supabase. |
| `app/reminders.py` | ✅ BUILT | /reminders/due: polls medications (rrule) + upcoming events in 30-min window. |
| `app/location.py` | ✅ BUILT | Wander safety: haversine distance vs safe_zone → reassure + alert. NEVER navigates. |
| `app/vision.py` | ✅ BUILT [CONFIRM] | Optional: snapshot → VLM describe → Moss match → person ref. Fixture fallback. |
| `tests/smoke_test.py` | ✅ BUILT | 20-case grounding/latency table. Run: pytest tests/smoke_test.py -s -v |
| `scripts/seed_amma.py` | ✅ BUILT | Seeds Amma's full life (persons, places, meds, events, stories, edges) to Supabase + Moss. |

## How to run
```bash
# Install
cd packages/memory-engine && python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Env
cp ../../.env.example ../../.env  # fill in keys

# Start (dev)
uvicorn app.main:app --reload --port 8000

# Seed Amma
python ../../scripts/seed_amma.py

# Smoke test (server must be running)
pytest tests/smoke_test.py -s -v

# Verify stubs work without keys
curl http://localhost:8000/health
curl -X POST http://localhost:8000/memory/query -H 'Content-Type: application/json' -d '{"text":"Who is Leo?","lang":"en"}'
```

## [CONFIRM] open items (needed at office hours)
- **Moss SDK**: on-device/WASM vs cloud, exact Python SDK calls vs REST, cross-lingual embedding support, instant upsert latency. `moss_client.py` currently uses REST — swap if SDK provided.
- **Moss wifi-off mode**: WASM sidecar port? Or bundle index locally? Affects demo beat 4.
- **Vision**: on-device embedding (CLIP?) vs hosted VLM. Currently uses OpenAI gpt-4o-mini as fallback.

## Retrieval scoring
`score = α·semantic(0.5) + β·recency(0.25) + γ·salience(0.15) + δ·graph_prox(0.10)`
`recency = exp(−λ·Δt_hours)` where λ=0.01 (tunes from .env: RECENCY_LAMBDA)
Confidence threshold τ=0.45 (CONFIDENCE_THRESHOLD). Below → grounded=False → safe refusal.

## Grounding rule (HARD)
Every `/memory/query` and `/memory/temporal` response is grounded=True only if top score ≥ τ.
If grounded=False: answer_draft = safe refusal ("I'm not sure, let me check with the family.").
LLM in voice agent must use ONLY facts in `items[]`. Never invent people/events/dates.

## Faked / TODO real
- Fixtures in `fixtures/*.json` are demo fallbacks — not real Moss/Supabase data.
- `vision.py` uses OpenAI VLM as placeholder; needs [CONFIRM] on-device approach.
- Twilio SMS in `location.py` requires real keys; SMS won't fire without them.
- `capture.py` is explicit-trigger only — not live auto-capture from every utterance.

## Data model summary (from §3 contract)
Tables: persons, places, events, medications, med_logs, stories, episodes, edges, interactions, safe_zones, location_pings, alerts. Every embeddable row has `provenance{source,added_by,added_ts}`.
OpenAPI: `packages/shared/contract.openapi.json` (generated from schemas.py at Gate 0).
