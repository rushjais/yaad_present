# CONTRACT.md — FROZEN API + DATA SCHEMA

> Status: **FROZEN at Gate 0 (v1).**
> Source of truth = `packages/memory-engine/app/schemas.py` → exported to
> `packages/shared/contract.openapi.yaml` (run `python export_openapi.py`) → generates
> `packages/caregiver-web/lib/types.ts`.
> Changing this is rare and LOUD: edit `schemas.py`, re-export the OpenAPI, regenerate
> TS types, **bump the version below**, and post the change in `STATUS.md` so every track re-reads.

**Version:** v1 (frozen 2026-06-05, Gate 0)

---

## Conventions
- All `*_ts` fields are timezone-aware **ISO 8601** datetimes (e.g. `2026-06-05T08:00:00Z`).
- `lang` ∈ `"en" | "hi" | "hi-en"` (English / Hindi / Hinglish).
- **Embeddable rows** (indexed in Moss) carry `embedding: float[] | null` + `provenance`.
  Embeddable: `person, place, event, medication, story, episode`.
  Operational (no embedding/provenance): `med_log, edge, interaction, safe_zone, location_ping, alert`.
- `provenance = { source: str, added_by: str, added_ts: datetime }` — on every embeddable row & every `RetrievedItem`.

## Data model (Supabase rows; embeddable ones also indexed in Moss)

| type | fields |
|---|---|
| **person** | `id, name, relationship, aliases[], notes?, photo_ref?, is_reassurance_contact, alert_priority?, embedding?, provenance` |
| **place** | `id, name, kind:home\|familiar\|other, lat?, lng?, notes?, embedding?, provenance` |
| **event** | `id, title, kind, start_ts, end_ts?, place_id?, participant_ids[], notes?, embedding?, provenance` |
| **medication** | `id, name, schedule_rrule, notes?, embedding?, provenance` |
| **med_log** | `id, medication_id, taken_ts, source` |
| **story** | `id, title, text, people_ids[], occurred_ts?, embedding?, provenance` |
| **episode** | `id, title, occurred_ts, kind, entity_refs[], summary, embedding?, provenance` |
| **edge** | `id, from_ref, to_ref, type, weight` |
| **interaction** | `id, ts, lang, query, response, retrieved_refs[], grounded, confidence` |
| **safe_zone** | `id, center_place_id, radius_m, contact_ids_ordered[]` |
| **location_ping** | `id, ts, lat, lng, inside_zone` |
| **alert** | `id, ts, kind:wander\|lost, lat, lng, contacts_notified[], status` |

`EntityType` (for `/memory/write` and `RetrievedItem.type`) = `person | place | event | medication | med_log | story | episode`.

## Shared response objects
- **`RetrievedItem`** = `{ ref, type:EntityType, text, score, provenance }`
- **`QueryResponse`** = `{ items: RetrievedItem[], grounded: bool, confidence: float, answer_draft: str|null }`
  (if `grounded=false`, `answer_draft` is the **safe refusal**.)
- **`TimelineBlock`** = `{ start_ts, end_ts?, title, kind, refs[], summary }`
- **`DueReminder`** = `{ type:"medication"|"event", ref, text, due_ts }`

## Endpoints

| method | path | request | response |
|---|---|---|---|
| POST | `/memory/query` | `{ text, lang }` | `QueryResponse` |
| POST | `/memory/temporal` | `{ text, lang }` | `QueryResponse` (routed through temporal logic) |
| POST | `/memory/write` | `{ type:EntityType, payload:object }` | `{ id }` |
| POST | `/memory/capture` | `{ transcript }` | `{ created_refs: string[] }` |
| GET  | `/memory/timeline` | `?date=` | `{ blocks: TimelineBlock[] }` |
| GET  | `/reminders/due` | `?ts=` | `{ due: DueReminder[] }` |
| POST | `/location/ping` | `{ lat, lng }` | `{ inside_zone, nearest_place?, action:none\|reassure\|alert, reassurance_text?, contacts? }` |
| POST | `/vision/recognize` | `{ image_b64 }` | `{ match: RetrievedItem\|null, answer_draft }` |
| GET  | `/health` | — | `{ moss_ok, db_ok, latency_ms }` |

`/memory/write.payload` is a row of the given `type` **without** the server-assigned `id`; its shape matches that entity's model above.

## Latency contract
`/memory/query` p95 **< 60ms** server-side (Moss ~10ms [CONFIRM]). The voice agent fires speculatively on the partial transcript.

---
*Gate 0 (current):* every endpoint is implemented and returns realistic **fixture** data validated against these models. No real Moss/Supabase logic yet — see `STATUS.md` → "Faked / TODO real".
