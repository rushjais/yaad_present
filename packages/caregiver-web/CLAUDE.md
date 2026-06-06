# Track C — Caregiver Web · CLAUDE.md
**Owner: Raghav** · Before you code: re-read this file + root STATUS.md. After you code: update them.

## What Track B has ready for you
OpenAPI schema: `packages/shared/contract.openapi.json` — run `openapi-typescript` against this to generate `lib/types.ts`.

### Key endpoints
| Endpoint | Use |
|---|---|
| `POST /memory/write {type, payload}` | Add person / event / medication / story — drives add-fact-live beat |
| `POST /memory/query {text, lang}` | Search memories |
| `GET  /memory/timeline?date=` | Timeline blocks for the timeline view |
| `GET  /reminders/due` | Upcoming meds + events for dashboard |
| `POST /location/ping {lat,lng}` | Wander safety — inside_zone + action |
| `GET  /health` | Status indicator |

### Write payload shapes (from schemas.py)
```ts
// Person
{ type: "person", payload: { name, relationship, aliases?, notes?, photo_ref?, is_reassurance_contact?, alert_priority? } }

// Event
{ type: "event", payload: { title, kind, start_ts, end_ts?, place_id?, participant_ids?, notes? } }

// Medication
{ type: "medication", payload: { name, schedule_rrule, notes? } }

// Med log (mark pill taken)
{ type: "med_log", payload: { medication_id, taken_ts, source } }

// Story
{ type: "story", payload: { title, text, people_ids?, occurred_ts? } }
```

## add-fact-live — this is the hero beat
`POST /memory/write` → Track B writes to Supabase AND upserts to Moss instantly → voice agent can answer in the next sentence.
Make the "Add memory" form one-click fast. No multi-step wizards.

## Generate types
```bash
cd packages/caregiver-web
npx openapi-typescript ../../packages/shared/contract.openapi.json -o lib/types.ts
```

## [CONFIRM] items for Raghav
- Supabase: keys in .env (SUPABASE_URL, SUPABASE_SERVICE_KEY)
- Memory engine URL: set NEXT_PUBLIC_MEMORY_ENGINE_URL=http://localhost:8000

## Phase: not started — update this file as you build
