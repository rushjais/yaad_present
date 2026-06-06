# Track C — Caregiver Web · CLAUDE.md
**Owner: Raghav** · Before you code: re-read this file + root STATUS.md. After you code: update them.

## Current phase: C0 — start now

## First thing to do
Get `.env` from Keshav. You need two values: `SUPABASE_URL` and `SUPABASE_SERVICE_KEY`.
Everything else (Moss, Groq, MiniMax) is not needed by the web app.

## What's already done — do NOT redo these
- Supabase: all 12 tables exist and are populated with Amma's life
  - Persons: Amma, Leo (grandson), Sarah (daughter)
  - Places: 142 Elmwood Ave (home), Lullwater Park
  - Medications: heart pill (8am), blood pressure pill (8pm)
  - Events: Sunday visit with Leo, Sarah's lunch, Lullwater walk
  - Stories: Leo's chess win, monsoon memory, Sarah's housewarming
  - Edges: 5 relationships wired in the graph
  - Safe zone: 500m radius around home
- `seed_amma.py` has already run — **do NOT re-run it** (will duplicate data)
- OpenAPI schema at `packages/shared/contract.openapi.json` — frozen

## Generate types first
```bash
cd packages/caregiver-web
npx openapi-typescript ../../packages/shared/contract.openapi.json -o lib/types.ts
```

## Memory engine API (running at :8000)
Base URL: `http://localhost:8000` (dev) or `MEMORY_ENGINE_URL` env var.

### Endpoints you'll use
| Endpoint | What for |
|---|---|
| `POST /memory/write {type, payload}` | Add a memory → drives add-fact-live demo beat |
| `GET  /memory/timeline?date=YYYY-MM-DD` | Timeline blocks for the timeline view |
| `GET  /reminders/due?ts=<iso>` | Upcoming meds + events for care dashboard |
| `POST /location/ping {lat, lng}` | Wander safety — inside_zone + action |
| `GET  /health` | Status indicator |

### Write payload shapes
```ts
// Person (triggers instant Moss index)
{ type: "person", payload: { name, relationship, aliases?, notes?, is_reassurance_contact?, alert_priority? } }

// Event
{ type: "event", payload: { title, kind, start_ts, end_ts?, notes? } }

// Medication
{ type: "medication", payload: { name, schedule_rrule, notes? } }

// Mark pill taken
{ type: "med_log", payload: { medication_id, taken_ts, source } }

// Story / memory
{ type: "story", payload: { title, text, people_ids?, occurred_ts? } }
```

## add-fact-live — the hero demo beat
`POST /memory/write` → Track B writes to Supabase AND upserts to Moss instantly → voice agent answers in the next sentence.

**This is what the judges will remember.** Make the "Add memory" form:
- One click to submit (no multi-step wizards)
- Show a visual confirmation that the fact is now "in memory"
- Ideally have a "Try it" button that triggers a voice query right after

## Your next steps (in order)
1. Get `.env` from Keshav (SUPABASE_URL + SUPABASE_SERVICE_KEY)
2. `npx openapi-typescript ../../packages/shared/contract.openapi.json -o lib/types.ts`
3. Scaffold Next.js app + typed `lib/api.ts` pointing at memory engine (C0)
4. Build add-memory forms: person / event / story → `POST /memory/write` — **one-click fast** (C1)
5. Graph view: `MemoryGraph.tsx` using react-force-graph, pull entities + edges from Supabase (C3)
6. Timeline view: `GET /memory/timeline` → render blocks by day (C3)
7. Care dashboard: "things to talk about with her today" from timeline + upcoming events. **NO clinical/health scores.** (C4)
8. Safety view: set home + safe-zone on map, ordered emergency contacts, show location + alert history (C5)
9. Architecture diagram: `docs/ARCHITECTURE.md` — Moss at the center, for the pitch (C6)

## Language scope
**English only.** No Hindi/multilingual UI needed. Language is a future add-on.

## Phase: C0 — update this section as you build
