# Track B — Memory Engine · CLAUDE.md
**Owner: Keshav** · Before you code: re-read this file + root STATUS.md. After you code: update them.

## Current phase: B7.1 — Chunks + τ simplification **complete** ✅ (2026-06-06)

43/43 tests green: 15 smoke + 28 robustness. p95 = 22ms server-side.

### v2 architecture (this is what's live)
Read `MEMORY_V2_README.md` at repo root for the teammate-facing version.

The big shift: we used to walk a graph (edges + 1-hop expansion in retrieval.py). We don't anymore. Instead:
1. **Better Moss chunks** at seed time bake relationships into the text. Leo's chunk literally says *"Leo. Amma's grandson, Sarah's son. 22…"*. Moss semantic match on "Leo's mom" returns Leo's chunk; the downstream LLM reads "Sarah's son" and answers Sarah. Zero edge code.
2. **Single hard τ relevance gate** in `retrieval.py` (TAU=0.82). Below τ → safe refusal. No `_OFF_TOPIC_HINTS`, no `_IMPLICIT_ENTITY_WORDS`, no entity-name-in-top check. One rule.
3. **One-hop query expansion** when the user mentions multiple entities and one isn't represented — fires a second Moss query. Graph-like behavior, still on Moss.
4. **Family-overview chunk** ("Amma's family includes: Leo (grandson…)…") guarantees a target for kinship queries without proper nouns.
5. **answer_draft for semantic queries = top chunk text** (LLM downstream rewrites). Temporal still pre-composes grounded negatives.

### What still does what
- `intent.py` — hybrid regex+Groq, unchanged from v1.
- `time_window.py` — unchanged.
- `temporal.py` — unchanged: per-medication routing, grounded negatives, time windows.
- `capture.py` — unchanged: Groq structured extraction → captured_fact + pending_review.
- `graph.py` — trimmed to ~50 lines, entity_text cache only (used by capture).
- `retrieval.py` — rewritten lean: Moss → τ → optional expansion → items[].
- `/memory/write` event side effect — after saving an event, `main.py` resolves person names in `payload.title`/`payload.notes` through Moss (first person hit in top 8 with score ≥0.85) and backfills `participant_ids` on the Supabase row. Lowercase caregiver entries are covered by case-insensitive matching against known person names/aliases before Moss verification.
- `scripts/reseed_moss.py` person chunks include stored `relationship` when the person has no edge-derived relationship phrase, so caregiver-added people retain relationship context after reseed.

| Beat | Robustness score |
|---|---|
| 1 who-is (grounded variants) | 7/7 |
| 1 who-is (refused — anti-confab) | 5/5 |
| 2 pills today (phrasing variants) | 7/7 |
| 5 relational (graph walks) | 5/5 |

Gate 1 (B0–B6) was structurally complete but **demo-fragile**. Smoke test exposed three real problems:
1. **Moss session doesn't resume the cloud index** on a fresh server process — `query("Leo")` returned 0 results despite a successful seed-time push. Workaround: `scripts/reseed_moss.py` reseeds from Supabase before each demo.
2. **Retrieval has no understanding step** — every layer (temporal, retrieval, capture) does its own ad-hoc parsing. Regex temporal misses paraphrases; graph proximity is a score boost no one consumes; capture is string-match on "remember this".
3. **No per-beat acceptance** — the smoke test checks "endpoint returns JSON", not "the actual demo line works under 30 phrasings". Result: "Gate 1 verified" rotted without detection.

## B7 architecture — what we're building

```
   query/transcript
         │
         ▼
   app/intent.py          ← single understanding pass (regex fast-path + Groq fallback)
         │
   typed Intent {kind, entities[], time_window, medication_hint, confidence}
         │
   ┌─────┴───────┬──────────┬──────────────┬─────────────┐
   ▼             ▼          ▼              ▼             ▼
temporal      retrieval   graph         capture       (general)
(per-med +    (Moss +     (1-hop        (structured
 time-win)    expansion)   expansion     extraction
                           into items[]) + entity
                                          resolution)
   │             │          │              │             │
   └─────────────┴────┬─────┴──────────────┴─────────────┘
                      ▼
                grounding.py (τ=0.45)
                      │
                      ▼
              MemoryQueryResponse
```

### What's confirmed working right now (post-B7 will update this)
- Server boots: `moss_ok=true`, `db_ok=true`
- `/memory/temporal` "did I take my pills today?" → grounded=true (Supabase path)
- `/memory/query` "Who is Leo?" → **broken** (Moss session empty until reseed)
- All other Moss-backed queries → safe-refusal until reseed

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
| `app/main.py` | ✅ BUILT | FastAPI app. All 9 endpoints. try/except → real logic or fixture fallback. `/memory/write` also handles instant Moss upsert and event participant backfill. ⚠ silent fixture fallback hides real errors — will be gated behind `YAAD_DEMO_MODE=1` in a follow-up. |
| `app/config.py` | ✅ BUILT | Pydantic settings. Accepts MOSS_PROJECT_ID or MOSS_ID. Strips whitespace from all values. |
| `app/db.py` | ✅ BUILT | Supabase client: write_memory, update_event_participants, fetch_med_logs_today, fetch_upcoming_events, db_ping. |
| `app/moss_client.py` | ✅ BUILT | Moss SessionIndex: upsert (instant, local), upsert_batch, query, push_index. Metadata must be str→str. ⚠ `session(index_name=...)` does NOT reliably resume cloud index — reseed before demo. |
| `app/intent.py` | 🚧 B7 BUILDING | Single understanding pass per query. Hybrid regex fast-path + Groq LLM fallback. Returns typed `Intent`. Consumed by temporal, capture, graph routers. |
| `app/time_window.py` | 🚧 B7 BUILDING | Relative-time parser: "today"/"yesterday"/"this morning"/"before lunch" → (start_ts, end_ts) user-local. |
| `app/graph.py` | 🔁 B7 REBUILDING | Was: 1-hop traversal as score boost only. Becoming: edge-index dict (kill N²); real neighbor expansion into items[]; edge-type-aware text; relational shortcut walks edge path for Intent.kind=relational. |
| `app/retrieval.py` | 🔁 B7 REBUILDING | Was: pure semantic + composed scoring. Becoming: consumes Intent + emits expanded items[] via graph; relational queries return path-derived text. Scoring weights unchanged (α/β/γ/δ). |
| `app/grounding.py` | ✅ BUILT | Confidence gate τ=0.45 → safe refusal. Provenance on every item. (Unchanged in B7.) |
| `app/temporal.py` | 🔁 B7 REBUILDING | Was: regex intent routing. Becoming: consumes Intent + per-medication routing ("heart pill" vs "BP pill"); time-windowed events; **grounded negatives** ("you haven't taken your heart pill yet" = grounded on absence). |
| `app/capture.py` | 🔁 B7 REBUILDING | Was: string-match "remember this". Becoming: Groq structured extraction → entity resolution (Moss top score ≥0.85 → UPDATE existing, not INSERT) → edge creation → episode + interaction row. Capture-confidence gate. |
| `app/reminders.py` | ✅ BUILT | `/reminders/due`: rrule med schedule + 30-min event window. |
| `app/location.py` | ✅ BUILT | Wander safety: haversine vs safe_zone → reassure + Twilio alert. NEVER navigates. |
| `app/vision.py` | ✅ BUILT | Optional: image → VLM describe → Moss match. Fixture fallback. No OpenAI key yet. |
| `app/unsiloed.py` | ✅ BUILT | Unsiloed REST client: `upload(bytes, filename) → doc_id`, `chat(doc_id, message) → str`. Field names: multipart `document`, form-data `message` (NOT `file`/`question` — Unsiloed quirk, confirmed 2026-06-06). |
| `app/ingest.py` | ✅ BUILT | High-level: PDF → Unsiloed parse → Groq normalize → typed records → write_memory + Moss upsert. Auto-commits medications + events (with absolute dates) + persons + a story for the doc summary. |
| `tests/smoke_test.py` | ✅ BUILT | 20-case grounding/latency table. Still authoritative for endpoint contract. |
| `tests/robustness.py` | 🚧 B7 BUILDING | 30+ phrasings per demo beat (ground-truth → grounded; adversarial → safe-refused). Per-beat pass/fail = ship readiness. |
| `scripts/seed_amma.py` | ✅ RAN | Initial seeded. Do NOT re-run — append-only, duplicates rows. |
| `scripts/reseed_moss.py` | 🚧 B7 BUILDING | Reads Supabase → upserts to Moss → verifies query("Leo") ≥0.9 before exit. Safe to re-run any time. |
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

## .env gotchas — read this first
The `.env` is being corrupted by editor sync (Cursor/Windsurf) on every session. **Run this before starting any work:**
```bash
python3 -c "
import re
content = open('.env').read()
fixed = content.replace('sk-apiiH6H2', 'sk-api-iH6H2')
lines = []
for line in fixed.splitlines(keepends=True):
    s = line.strip()
    if not s or s.startswith('#'): lines.append(line); continue
    m = re.match(r'([A-Z0-9_]+)\s*=\s*(.*)', s)
    if m: lines.append(m.group(1) + '=' + m.group(2).strip().rstrip('/') + '\n')
    else: lines.append(line)
open('.env', 'w').writelines(lines)
"
```
- `MINIMAX_API_KEY` loses its dash: `sk-apiiH6H2` → must be `sk-api-iH6H2`. Wrong key = silent 1004 auth fail.
- Spaces around `=` and MOSS_ID/MOSS_API_KEY aliases — config.py handles these automatically.
- Always read from root `.env` (not packages/memory-engine/.env — there isn't one).

## Next steps for Track B (B7 execution order)
1. `scripts/reseed_moss.py` — restore Moss index from Supabase. Verify `query("Leo")` ≥0.9 before exit.
2. `app/intent.py` + `app/time_window.py` — foundation for everything else.
3. Rebuild `app/temporal.py` on Intent + time-window.
4. Rebuild `app/graph.py` + `app/retrieval.py` — real expansion.
5. Rebuild `app/capture.py` — structured extraction + entity resolution.
6. `tests/robustness.py` — 30+ phrasings per beat. Green here = ship ready.
7. Final commit + push.

Deferred (B8+ if time): `YAAD_DEMO_MODE=1` flag for the silent-fixture fallback in `main.py`, vision module needs OpenAI key.

## Open items
- `vision.py`: needs OpenAI key or on-device VLM — fixture fallback fires for now
- Twilio SMS: fires with current keys but location alert not tested end-to-end
- TrueFoundry: key in `.env` but `TRUEFOUNDRY_BASE_URL` still unknown — not used by memory engine
- Moss `SessionIndex` cloud resume: needs SDK followup; `reseed_moss.py` is the workaround
- `main.py` silent fixture fallback: gate behind `YAAD_DEMO_MODE=1`
