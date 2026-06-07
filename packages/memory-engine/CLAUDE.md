# Track B - Memory Engine

Owner: Keshav. Before coding, re-read this file and root `STATUS.md`. After coding, update both when behavior changes.

## Current Phase

Archetype router rebuild on `claude/memory-archetype-rebuild`.

The memory engine now routes by subject/substrate:

| Archetype | Substrate |
|---|---|
| `identity` | Supabase `persons` / `places` name and alias lookup |
| `relational` | In-process `edges_cache` loaded from `edges` |
| `temporal_med` | Supabase `med_logs` window query + medication row matching |
| `temporal_event` | Supabase `events` window query + participant lookup |
| `preference` | `persons.preferences JSONB` |
| `episodic` | Moss over `stories` and `episodes(kind='captured_fact')` only |

Moss is no longer the index for persons, places, medications, or events. Those are structured lookups. Groq is allowed only for router classification fallback and capture extraction; it must never rewrite stored or indexed data.

## How To Run

```bash
cd packages/memory-engine
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Supported invocation. Avoid importing through a hyphenated package path.
uvicorn app.main:app --reload --port 8000

# Optional, before demo or after dirty tests:
python ../../scripts/reseed_moss.py --wipe

pytest tests/smoke_test.py -s -v
pytest tests/robustness.py -s -v
pytest tests/test_general_queries.py -s -v
```

`/health` exposes `moss_doc_count`; after startup reseed it should be at least one when stories exist.

## Extension Data

Domain word lists live in JSON, not Python literals:

| File | Purpose |
|---|---|
| `app/data/preference_keys.json` | Recommended preference keys and keyword aliases |
| `app/data/relationship_words.json` | Relationship words, edge types, display phrases |
| `app/data/router_aliases.json` | Router trigger words for meds, events, identity, remember |

Add terms there first. New entities, edges, medications, and aliases should be data changes, not code changes.

## Contributor Rules

1. No LLM in the storage path. Seeding, reseeding, writing, and ingesting must write canonical row data unmodified.
2. Single source of truth per concern. Chunk text -> `chunks.py`. Edge words -> `relationship_words.json`. Preference/med/event aliases -> JSON data files.
3. Data tables, not Python literals. Domain string lists with five or more entries belong in JSON.
4. Archetypes refuse, never invent. Empty structured lookup means `items=[]`, `grounded=false`, and safe refusal.
5. Provenance always points to a row/table: `persons`, `persons.preferences`, `places`, `medications`, `med_logs`, `events`, `stories`, or `episodes`.
6. Loud by default. Fixture fallback requires `YAAD_DEMO_MODE=1`; otherwise endpoint errors raise HTTP 500.
7. Test failure modes. Every archetype needs a positive case and an absent/sparse-data case.

## Legacy

The old B7.2 semantic/enrichment path is archived under `packages/memory-engine/.archived-legacy/` and `scripts/reseed_moss.legacy.py`. It is kept for audit only. Do not revive `_enrich_chunk` or `fixtures/enriched_chunks.json`; that path caused hallucinated person chunks.

## Open Dependencies

Track C: caregiver-web needs a preferences editor on the person form - schema lives in `persons.preferences JSONB`, recommended keys in `app/archetypes/preference.py:RECOMMENDED_KEYS`.
