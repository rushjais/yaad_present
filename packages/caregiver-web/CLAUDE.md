# Track C — Caregiver Web · CLAUDE.md
**Owner: Raghav** · Before you code: re-read this file + root STATUS.md. After you code: update them.

## Current phase: C3 — graph view + timeline (next up)

## What's built — do NOT redo these

### C0 ✅ — scaffold
- Next.js 15, Tailwind 4, TypeScript, react-force-graph-2d in `package.json`
- `lib/types.ts` — hand-typed from `contract.openapi.json`; regenerate with `npm run generate-types`
- `lib/api.ts` — typed wrappers for all 8 endpoints (`queryMemory`, `writeMemory`, `getTimeline`, `getReminders`, `pingLocation`, `getHealth`, etc.)
- `next.config.ts` — rewrites `/api/engine/:path*` → `MEMORY_ENGINE_URL` (default `http://localhost:8000`) so browser never needs to know the engine host
- Page stubs for `/` (dashboard), `/memories`, `/timeline`, `/graph`, `/safety`
- `components/MemoryGraph.tsx` — stub with SSR-disable note
- Build green, tsc clean

### C1 ✅ — add-memory forms (`/memories`)
- Four-tab form: **Person / Event / Medication / Story** → `POST /memory/write`
- Person: name, relationship, notes, aliases:[], is_reassurance_contact checkbox
- Event: title, kind (select), date + time → ISO `start_ts`, notes
- Medication: name, daily time picker → `FREQ=DAILY;BYHOUR=...;BYMINUTE=...` rrule, notes
- Story: title, full text, optional `occurred_ts`
- Inline success ("Saved — Amma can be asked about this now.") and error feedback
- Form resets on success; one-click submit; no multi-step wizards

### Already done by Track B (do NOT redo)
- Supabase seeded: Amma, Leo, Sarah; home + park; 2 meds; events; stories; 5 edges; safe_zone
- `seed_amma.py` has run — **do NOT re-run** (will duplicate data)
- OpenAPI schema at `packages/shared/contract.openapi.json` — frozen

## Memory engine API (running at :8000)
Calls go through Next.js rewrite at `/api/engine/:path*`. Do not call `:8000` directly from the browser.

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

## Next steps (in order)
1. **C3 — Graph view** (`/graph`): wire `MemoryGraph.tsx` with `react-force-graph-2d` (SSR-disabled via `dynamic(..., {ssr:false})`); fetch nodes + edges from Supabase directly or via a new `/memory/graph` endpoint if Keshav adds one
2. **C3 — Timeline** (`/timeline`): `GET /memory/timeline?date=YYYY-MM-DD` → render `TimelineBlock[]` ordered by time
3. **C4 — Care dashboard** (`/`): "topics to reinforce with her" from recent timeline + upcoming reminders. **NO clinical/health score.**
4. **C5 — Safety view** (`/safety`): set home + safe-zone radius on a map; ordered emergency contacts; alert history
5. **C6 — Architecture diagram**: `docs/ARCHITECTURE.md` — Moss at the center, for the pitch

## How to run
```bash
cd packages/caregiver-web
npm install
npm run dev          # :3000 — caregiver web
# memory engine must be running at :8000 for writes to work
```

## Language scope
**English only.** No Hindi/multilingual UI needed.
