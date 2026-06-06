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

## Language scope
**English only.** No Hindi/multilingual UI needed for now. Language is a future add-on.

## Your next steps (in order)
1. **[CONFIRM]** Get Supabase keys → fill `.env` (SUPABASE_URL, SUPABASE_SERVICE_KEY)
2. Generate types: `npx openapi-typescript ../../packages/shared/contract.openapi.json -o lib/types.ts`
3. Scaffold Next.js app + typed `lib/api.ts` (C0)
4. Build add-memory forms: person / event / medication / story → `POST /memory/write` — **one-click fast, this is the add-fact-live beat** (C1)
5. Run `python ../../scripts/seed_amma.py` to populate Amma's life (needs Supabase + Moss keys)
6. Graph view: `MemoryGraph.tsx` (react-force-graph) + `/memory/timeline` timeline (C3)
7. Care dashboard: "topics to reinforce with her" — **NO clinical/health score** (C4)
8. Safety view: set home + safe-zone on map, ordered contacts, location + alert history (C5)
9. Architecture diagram `docs/ARCHITECTURE.md` — Moss at center (C6)

## Phase: not started — update this file as you build
