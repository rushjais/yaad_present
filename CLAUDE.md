# Yaad — Final Production Build Spec (LiveKit + Pipecat + MiniMax)
### Conversational AI Hackathon · Moss (YC F25) @ Y Combinator · 3 people, full-time · ~20h


---

## META-INSTRUCTIONS FOR CLAUDE CODE
### (Andrej Karpathy principles + Yaad conventions)

**Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.**

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### 1. Think Before Coding — Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First — Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

### 3. Surgical Changes — Touch only what you must. Clean up only your own mess.

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

### 4. Goal-Driven Execution — Define success criteria. Loop until verified.

Transform tasks into verifiable goals. For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

Strong success criteria let you loop independently.

### Yaad-specific conventions (merged with Karpathy principles):

The Karpathy principles above are the *how*. Below are Yaad's *what* and *why*.

- **Living docs are part of "done."** A change isn't done until its `CLAUDE.md`/`CONTRACT.md`/`STATUS.md` is updated in the **same commit**. Session bookends: re-read before you code, update after. No silent stubs.
- **Don't assume the contract.** If an endpoint signature is unverified ([CONFIRM]), mark it and surface the blocker.
- **Surface tradeoffs explicitly.** If a feature could be scoped narrower or if build-time is tight, name it in `STATUS.md` — don't silently half-build.
- **Surgical changes to the core.** After Gate 2 (core flawless), the 5 core beats are frozen. New features go in branches. Don't touch the core unless it's a regression fix.
- **Goal-driven on the demo beats.** Each of the 5 beats (who-is-this, pills-today, add-fact-live, wifi-off, Hindi) has a definition of done. Code to those, verify them, stop.

---

---

## 0. CLAUDE.md — read first

**Mission.** Build *Yaad*: a warm, bilingual (Hindi/English) voice companion for someone with early dementia, backed by an **episodic, temporal, self-updating memory graph built on Moss.** Open emotional ("who is this?" → "that's Leo, your grandson"); reveal technical (a memory layer on Moss — temporal state, instant updates, on-device retrieval).

**Why we're building it (keep this in the pitch, restrained):** Rushil's grandmother had Alzheimer's; by the end the hardest part was watching the people who loved her become strangers to her. Yaad is the thing we wish she'd had. Frame the demo as *"memory is beautiful,"* never *"look how sad this disease is."*

**The rule that wins:** Moss is the hero. Every spoken answer is grounded in retrieved memory. Hero beats: (1) instant updates (family adds a fact → usable next sentence), (2) wifi-off still works (on-device), (3) temporal state ("did I take my pills today?"), (4) it's a *graph*, not flat RAG.

**Golden rules:**
1. **Freeze the contract (§3) in hour 1.** All three tracks code against it. Never change it silently.
2. **Grounded-only.** Assert only facts in retrieved memory. Below confidence → "I'm not sure, let me check with the family." Never confabulate a life.
3. **★ Core first** (voice ↔ memory ↔ grounding ↔ instant-update ↔ Hindi). All else is tiered below and comes only after the core is flawless.
4. **Fixture fallback on every external beat (§13).** The demo must never hard-fail on camera.
5. **Safety (§8):** the agent reassures + alerts a human. NEVER turn-by-turn navigation for a disoriented person.
6. **📒 LIVING DOCS (§0.5):** no change is "done" until the Claude files reflect it. This is mandatory, not optional.
7. Secrets in `.env` (§4); rotate all keys post-event.

**Run:** `docker compose up` (or terminals): `memory-engine` `:8000`, `voice-agent` worker, `caregiver-web` `:3000`. Seed: `python scripts/seed_amma.py`.

---

## 0.5 📒 LIVING CLAUDE FILES — self-updating documentation protocol (REQUIRED)

With 3 humans + parallel agents, **stale docs are the #1 cause of drift and merge chaos** — an agent will confidently build against wrong assumptions. So the Claude files are a *living spec the code keeps in sync with itself.*

**The files that must stay current:**
- **Root `CLAUDE.md`** (this file) — mission, contract pointer, stack, golden rules, build status.
- **`packages/<track>/CLAUDE.md`** — one per track. Local context for that track's agent: current file responsibilities, what's built vs stubbed, gotchas, how to run, open questions.
- **`CONTRACT.md`** — the frozen API + schema (§3). Changing it is rare and LOUD (all-hands + regenerate types).
- **`STATUS.md`** — a short live build log: each track's phase (P0…Pn), what's done, what's blocked, what's faked for the demo.

**The discipline (enforce in every commit and every agent run):**
1. **Definition of done includes docs.** A change is incomplete until the relevant `CLAUDE.md`/`CONTRACT.md`/`STATUS.md` is updated *in the same commit.* If you added a file, changed a signature, stubbed something, or discovered a gotcha — write it down now.
2. **Session bookends.** Every agent/human, at the **start** of a work session, re-reads root `CLAUDE.md` + its `packages/<track>/CLAUDE.md` + `STATUS.md`. At the **end**, updates them. Put this literally in each track's `CLAUDE.md` header: *"Before you code: re-read this file + STATUS.md. After you code: update them."*
3. **Contract changes are announced.** If `CONTRACT.md` must change, update it, regenerate `contract.openapi.yaml` + TS types, bump a version line, and post it in `STATUS.md` so the other tracks/agents re-read before continuing.
4. **No silent stubs.** Anything faked for the demo (a fixture, a hardcoded value, a mocked endpoint) is logged in `STATUS.md` under "Faked / TODO real" so it's not mistaken for working.
5. **Agents self-document.** When you spin up a Claude Code agent on a track, instruct it: *"Keep this package's CLAUDE.md and STATUS.md accurate as you work; treat them as part of the deliverable."*

**Why:** this is what lets three parallel agents and three humans hand work back and forth for 20 hours without re-reading each other's code — the docs are always the truth.

---

## 1. Product in one screen
**Core loop (See/Hear → Retrieve on Moss → Ground → Speak):** user speaks (or shows a photo) → voice agent transcribes + detects intent/language → calls memory-engine → Moss-backed graph retrieval + temporal/recency/grounding → grounded context + confidence + provenance → LLM phrases a warm grounded answer → MiniMax speaks it (Hindi/English). Family edits memory in the web app → written to Supabase + indexed in Moss instantly → usable next turn.

**Demo persona:** "Amma," 84 — seeded fictional life (grandson Leo, daughter Sarah, meds, routine, episodes, home + a familiar park).

**Demo beats:** who-is-this · pills-today (temporal) · add-fact-live (instant update) · wifi-off (on-device) · Hindi exchange · (optional) photo recognition · (optional) wander alert.

---

## 2. Architecture & repo layout
Monorepo, three full-time track workspaces + frozen contract + living docs. Polyglot: Python (memory + voice), TypeScript (web).
```
yaad/
  CLAUDE.md                  # this file (living)
  CONTRACT.md                # frozen API + schema (§3) — single source of truth
  STATUS.md                  # live build log (§0.5)
  docs/ARCHITECTURE.md       # the system diagram for the pitch (Moss at the center)
  docker-compose.yml  .env.example
  fixtures/                  # demo fallback payloads (§13)
  scripts/ (seed_amma.py, smoke_test.py)
  packages/
    memory-engine/           # TRACK B — Python/FastAPI [OWNER: Keshav]
      CLAUDE.md              # ← living, track-local
      app/ (main, moss_client, graph, retrieval, temporal, grounding,
            capture, intent, time_window, schemas, db, location, vision, reminders)
      tests/
    voice-agent/             # TRACK A — Python/Pipecat+LiveKit [OWNER: Rushil]
      CLAUDE.md              # ← living, track-local
      (agent, transports[CONFIRM], tts_minimax, stt_groq,
       llm[CONFIRM], memory_client, reminders_client, fallback)
    caregiver-web/           # TRACK C — Next.js/TS [OWNER: Raghav]
      CLAUDE.md              # ← living, track-local
      app/((dashboard), memories, timeline, graph, safety)
      lib/(api.ts, types.ts), components/(MemoryGraph.tsx)
  packages/shared/contract.openapi.yaml
```
**Glue (compile-time enforcement):** `memory-engine/app/schemas.py` (Pydantic) is the source of truth → export `contract.openapi.yaml` → generate `caregiver-web/lib/types.ts` (`openapi-typescript`). Drift fails the web build. The voice agent imports the same Pydantic models.

---

## 3. THE FROZEN CONTRACT (freeze hour 1 → write to CONTRACT.md)
**Data model (Supabase; embeddable rows also indexed in Moss):** person `{id,name,relationship,aliases[],notes,photo_ref?,is_reassurance_contact,alert_priority?}` · place `{id,name,kind:home|familiar|other,lat?,lng?,notes}` · event `{id,title,kind,start_ts,end_ts?,place_id?,participant_ids[],notes}` · medication `{id,name,schedule_rrule,notes}` · med_log `{id,medication_id,taken_ts,source}` · story `{id,title,text,people_ids[],occurred_ts?}` · episode `{id,title,occurred_ts,kind,entity_refs[],summary}` · edge `{id,from_ref,to_ref,type,weight}` · interaction `{id,ts,lang,query,response,retrieved_refs[],grounded,confidence}` · safe_zone `{id,center_place_id,radius_m,contact_ids_ordered[]}` · location_ping `{id,ts,lat,lng,inside_zone}` · alert `{id,ts,kind:wander|lost,lat,lng,contacts_notified[],status}`. Every embeddable row carries `embedding` + `provenance{source,added_by,added_ts}`.

**Memory-engine API:**
- `POST /memory/query {text,lang}` → `{items:RetrievedItem[],grounded,confidence,answer_draft|null}` (`RetrievedItem={ref,type,text,score,provenance}`; if `grounded=false`, draft = safe refusal).
- `POST /memory/temporal {text,lang}` → same shape, routed through temporal logic.
- `POST /memory/write {type,payload}` → `{id}` (Supabase **and** instant Moss index — powers add-fact-live).
- `POST /memory/capture {transcript}` → `{created_refs[]}` (autonomous capture, §10).
- `GET /memory/timeline?date=` → `{blocks:TimelineBlock[]}`.
- `GET /reminders/due?ts=` → `{due:[{medication|event, text}]}` (§12).
- `POST /location/ping {lat,lng}` → `{inside_zone,nearest_place,action:none|reassure|alert,reassurance_text?,contacts?}` (§8).
- `POST /vision/recognize {image_b64}` → `{match:RetrievedItem|null,answer_draft}` (§11).
- `GET /health` → `{moss_ok,db_ok,latency_ms}`.

**Latency contract:** `/memory/query` p95 < 60ms server-side (Moss ~10ms [CONFIRM]); voice agent fires speculatively on partial transcript.

---

## 4. Environment (`.env.example`)
```
MOSS_API_KEY=        # [CONFIRM on-device/WASM vs cloud]
MOSS_INDEX=yaad_amma
DEEPGRAM_API_KEY=
MINIMAX_API_KEY=     MINIMAX_GROUP_ID=   # TTS Hindi/English [CONFIRM voice id]
LIVEKIT_URL=  LIVEKIT_API_KEY=  LIVEKIT_API_SECRET=
TRUEFOUNDRY_API_KEY= # gateway→model [CONFIRM base_url+model]
SUPABASE_URL=  SUPABASE_SERVICE_KEY=
UNSILOED_API_KEY=
TWILIO_ACCOUNT_SID=  TWILIO_AUTH_TOKEN=  TWILIO_FROM=
```

---

## 5. TRACK B — Memory Engine [OWNER: Keshav]
Turn Moss retrieval into a grounded, temporal, traversable memory graph behind the §3 API. **Keep `packages/memory-engine/CLAUDE.md` + STATUS.md current as you go (§0.5).**

**Phases B0–B6 (initial build) — complete.** See git history through `ce57744`.

**Phase B7 — Robustness rebuild (in progress, 2026-06-06):** the Gate-1 retrieval logic was demo-fragile (regex temporal misses paraphrases, graph proximity never surfaced neighbors, capture was string-match only). Rebuilding the understanding layer so the demo holds under off-script phrasings — see STATUS.md "Track B" and `packages/memory-engine/CLAUDE.md` "B7 architecture" for the full plan. Key adds:
- `app/intent.py` — hybrid (regex fast-path + Groq LLM fallback) → typed `Intent` consumed by all routers
- `app/time_window.py` — relative-time parser ("yesterday", "this morning", "before lunch") in user-local tz
- `temporal.py` rebuilt on `Intent` + per-medication routing; grounded negatives
- `graph.py` + `retrieval.py` — real 1-hop expansion (neighbors appear in `items[]`); edge-type surfaced in text; relational shortcut
- `capture.py` — Groq structured extraction + entity resolution (Moss-match top score ≥0.85 → UPDATE, not INSERT); edge creation; capture-confidence gate
- `tests/robustness.py` — 30+ phrasings per demo beat, all must be grounded; adversarial set must be safe-refused
- `scripts/reseed_moss.py` — idempotent Supabase → Moss reseed (the cloud `SessionIndex` does not reliably resume — empirically 0 results after server restart)

**Acceptance:** every query returns grounded items w/ provenance; ungrounded → safe refusal; a `/memory/write` retrievable < 1s; "pills today" reflects a just-logged dose; p95 within contract; **all 5 demo beats stay grounded across 30+ phrasing variants** (robustness.py green); **track CLAUDE.md + STATUS.md match the code.**

---

## 6. TRACK A — Voice Agent (LiveKit + Pipecat + MiniMax) [OWNER: Rushil]
Warm, low-latency, barge-in voice loop that grounds every answer. **Keep `packages/voice-agent/CLAUDE.md` + STATUS.md current.**
Pipeline: `LiveKit → VAD → Deepgram STT → intent/lang → memory_client.query()/temporal() (speculative) → LLM (TrueFoundry) w/ grounding prompt → MiniMax TTS → playback`, **barge-in** on VAD.
**Grounding system prompt:** "You are Yaad, a warm companion for someone with memory loss. State ONLY facts in the provided MEMORY context. If empty/low-confidence, say you're not sure and offer to check with the family. Never invent people/events/dates. Short, calm, warm. Match the user's language (English/Hindi/Hinglish)."
- **A0:** pipeline vs memory stubs (unblock early). **A1:** Deepgram + MiniMax echo loop [CONFIRM both; CONFIRM MiniMax Hindi voice]. **A2:** real memory calls + grounding + barge-in. **A3:** latency pass (speculative + streaming) → <~1s; build the latency overlay. **A4:** `fallback.py` fixtures on timeout. **A5:** proactive reminders via `/reminders/due` (§12).
**Acceptance:** "who is Leo?" warm + grounded <~1s; interrupt halts TTS; kill memory-engine → 5 beats still answer from fixtures; Hindi Q → Hindi A; **docs match code.**

---

## 7. TRACK C — Caregiver Web + Seeding + Dashboard + Timeline + Graph + Safety [OWNER: Raghav]
The family's window. **Keep `packages/caregiver-web/CLAUDE.md` + STATUS.md current.**
- **C0:** Next.js scaffold; `types.ts` from OpenAPI; typed `api.ts`.
- **C1 — add-memory forms** (person/event/med/story) → `/memory/write` (drives add-fact-live; one-click fast).
- **C2 — seed `seed_amma.py`** — rich, real-feeling persona.
- **C3 — graph view** (`MemoryGraph.tsx`, react-force-graph) + **timeline** (`/memory/timeline`).
- **C4 — care dashboard:** "topics to reinforce with her" (caregiver guidance) — **NO fake clinical/health score.**
- **C5 — safety view (§8):** set home + safe-zone on a map; ordered contacts; live location + alert history.
- **C6 — `docs/ARCHITECTURE.md` diagram** (Moss at the center) for the pitch.

**Acceptance:** adding "Leo's birthday is Saturday" is answerable by the agent in seconds; graph + timeline render; safety view sets a geofence; **docs match code.**

---

## 8. Wander-safety module ("being lost" feature — SAFE version only)
Detect when Amma leaves her safe zone or signals she's lost → **reassure + alert a human with her location.** The agent is comfort + alarm, never a navigator.
Flow: caregiver sets home + `safe_zone{radius_m,contacts_ordered}` → app `POST /location/ping` periodically + on a lost-utterance → `location.py` decides `none|reassure|alert` → reassure with a **Moss-personalized** line ("You're near [familiar place]. You're safe. I've let [contact] know — they're on the way.") → on alert, SMS/push the ordered contacts **with her location** (Twilio for demo) → dashboard shows location + alerts.
**HARD GUARDRAIL (comment in code + state in pitch):** Yaad never directs a disoriented person through streets/intersections. Lost → reassure + keep-in-place + alert a trusted human. Optional/supporting — build after the ★ core; competes with vision for the *one* optional wow.

## 9. Multilingual (Hindi/English)
MiniMax multilingual TTS [CONFIRM Hindi voice]; lang detect on transcript; cross-lingual retrieval (Hindi query matches English-stored memories via Moss embeddings [CONFIRM]). One Hindi exchange in the demo — authentic to the grandmother + a sponsor flex.

## 10. Episodic memory capture (autonomous-ish) — `/memory/capture`
Conversation → detect a memorable fact ("Leo got into Stanford") → extract entities/episode → write to Moss → later retrievable. **Honest note:** reliable live auto-capture is the riskiest beat; ship the buildable version (extract on explicit "remember this…" + caregiver review), keep the add-fact-via-web as the *reliable* live-update beat. Log any scripting in STATUS.md.

## 11. Vision beat (OPTIONAL — build last)
Single-shot: capture one frame → `/vision/recognize` → match a *pre-registered* photo/face → person ref → answer_draft ("that's Leo…"). On-device embedding [CONFIRM] or hosted VLM. **Never continuous.** Fixture fallback. Pick vision OR wander if time is tight.

## 12. Proactive reminders — `/reminders/due`
Time-based: at a med time / before an event, the agent proactively says it ("It's 8 — time for your white heart pill; Sarah visits at 3"). Scheduler polls `/reminders/due`; routes through the same grounded TTS path. One reminder beat in the demo.

## 13. Demo resilience / fixtures & fallback (the Hindsight lesson)
Capture the 5 beats into `fixtures/`. `voice-agent/fallback.py`: 3s timeout on any memory/vision/TTS call → serve the matching fixture (+ cached TTS) so the demo flows even if a service dies. Header live/cached indicator. Record on the live path; rehearse the fixture path.

## 14. Build order & parallelization (3 full-time tracks)
**Hour 0–1.5 (all-hands):** freeze CONTRACT → write CONTRACT.md; export OpenAPI; stub memory-engine w/ fixtures; **verify Moss on-device + instant-update at office hours**; create the three `packages/*/CLAUDE.md` + STATUS.md. Then fork.
**Parallel from 1.5** — each owner full-time + one supervised Claude Code agent against the frozen contract (agents do scaffolding/boilerplate **and keep their package CLAUDE.md/STATUS.md current**; humans own hard logic + integration; no two agents in one module). Integrate A↔B by ~hour 7.5; **★ core flawless by ~hour 11.5** (protect this). Then one optional (vision OR wander) + reminders + polish + resilience + record.

## 15. Demo script (~90s)
Why (grandmother, restrained) → "who is this?" → "did I take my pills today?" → add-fact-live → wifi-off → reveal ("a memory graph on Moss — search engines organize information; we organize a human life") + Hindi line → close ("we gave a family their memories back") + sponsor thanks (Moss, MiniMax, LiveKit, Unsiloed).

## 16. Definition of done
✅ 5 beats live AND from fixtures · ✅ grounded-only verified · ✅ instant-update <1s · ✅ temporal "pills today" · ✅ wifi-off · ✅ Hindi exchange · ✅ latency overlay + eval table · ✅ (opt) vision or wander + a reminder · ✅ 90s video + fixture path rehearsed · ✅ **all Claude files (root + 3 package CLAUDE.md + CONTRACT.md + STATUS.md) match the shipped code.**

## 17. Guardrails & ethics
Consent (family-managed, dignity-first) · grounded-only · confidence gate · provenance/auditable · augments-not-replaces · NO fake clinical metrics · NEVER correct/distress the patient · wander = reassure + alert human, never navigate · on-device privacy.

## 18. Sponsor checklist
Moss = hero (graph layer + instant updates + on-device) · MiniMax = voice (Hindi) · LiveKit = real-time transport/barge-in · Unsiloed = ingest a medical doc into structured memory · TrueFoundry = LLM gateway · AWS = host. Target: best-use-of-Moss / best-use-of-MiniMax.

## 19. First-place levers (keep in mind while building)
Present Yaad as a capability *built on* Moss (a memory graph), not an app that uses it. Land one flawless live signature beat (add-fact-live). Emotion → engineering in the same 90s. Show, don't tell (let it talk). Make it adopt-able ("a pattern any Moss dev could reuse").

## 20. [CONFIRM] at the event
Moss (on-device/WASM + instant upsert + cross-lingual embeddings + SDK) · MiniMax (Hindi voice id + streaming TTS + group id) · Deepgram / LiveKit / Pipecat exact calls · TrueFoundry base_url + model · Unsiloed parse API · push vs Twilio for alerts.
