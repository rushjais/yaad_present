# CONTRACT.md — FROZEN API + DATA SCHEMA

> Status: **FROZEN at Gate 0.**
> Source of truth = `packages/memory-engine/app/schemas.py` → exported to `packages/shared/contract.openapi.json` → generates `packages/caregiver-web/lib/types.ts`.
> Changes are rare and LOUD — all-hands, regenerate types, bump version, post in STATUS.md.

**Version:** v1 (frozen Gate 0)

---

## Data model

Every embeddable row carries `provenance{source, added_by, added_ts}`.

| Entity | Fields |
|---|---|
| `person` | id, name, relationship, aliases[], notes, photo_ref?, is_reassurance_contact, alert_priority? |
| `place` | id, name, kind(home\|familiar\|other), lat?, lng?, notes |
| `event` | id, title, kind, start_ts, end_ts?, place_id?, participant_ids[], notes |
| `medication` | id, name, schedule_rrule, notes |
| `med_log` | id, medication_id, taken_ts, source |
| `story` | id, title, text, people_ids[], occurred_ts? |
| `episode` | id, title, occurred_ts, kind, entity_refs[], summary |
| `edge` | id, from_ref, to_ref, type, weight |
| `interaction` | id, ts, lang, query, response, retrieved_refs[], grounded, confidence |
| `safe_zone` | id, center_place_id, radius_m, contact_ids_ordered[] |
| `location_ping` | id, ts, lat, lng, inside_zone |
| `alert` | id, ts, kind(wander\|lost), lat, lng, contacts_notified[], status |

---

## API endpoints

```
POST /memory/query     {text, lang}     → {items:RetrievedItem[], grounded, confidence, answer_draft|null}
POST /memory/temporal  {text, lang}     → same shape, routed via temporal logic
POST /memory/write     {type, payload}  → {id}
POST /memory/capture   {transcript}     → {created_refs[]}
GET  /memory/timeline  ?date=           → {blocks:TimelineBlock[]}
GET  /reminders/due    ?ts=             → {due:[{kind, text, ref}]}
POST /location/ping    {lat, lng}       → {inside_zone, nearest_place, action, reassurance_text?, contacts?}
POST /vision/recognize {image_b64}      → {match:RetrievedItem|null, answer_draft}
POST /ingest/document  (multipart file) → {created_refs[], summary, raw_extraction}
GET  /health                            → {moss_ok, db_ok, latency_ms}
```

`/ingest/document` is **additive** (added 2026-06-06, Unsiloed sponsor beat) — v1 contract preserved, no breaking change for Tracks A or C.

## RetrievedItem shape
```json
{
  "ref": "person:uuid",
  "type": "person",
  "text": "...",
  "score": 0.96,
  "provenance": {"source": "seed", "added_by": "seed_script", "added_ts": "2025-01-01T00:00:00Z"}
}
```

## Latency contract
- `/memory/query` p95 < 60ms server-side (Moss ~10ms [CONFIRM])
- `/memory/write` → Moss upsert answerable < 1s (instant-update beat)

## Grounding contract
- `grounded=true` only if top item score ≥ τ (default 0.45, set via CONFIDENCE_THRESHOLD)
- `grounded=false` → `answer_draft` = safe refusal, never fabrication
- Every item carries provenance — auditable

## Full schema
See `packages/shared/contract.openapi.json` (generated from `schemas.py`).
Generate TS types: `npx openapi-typescript packages/shared/contract.openapi.json -o packages/caregiver-web/lib/types.ts`
