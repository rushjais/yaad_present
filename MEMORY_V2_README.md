# Memory Engine v2 — for Rushil + Raghav

**TL;DR**
- We over-built a graph engine. Killing the graph traversal layer; Moss does the lift.
- **Contract is unchanged** — your code keeps working. Two heads-ups below.
- **Pitch line changes**: drop "memory graph on Moss". Use "living memory on Moss — instant updates, on-device, sub-10ms".
- ETA: ~2h. I'll post when it lands on `main`.

---

## Why this is changing

Pitch reality check came in: calling what we built a *knowledge graph* is shaky because it's vector search underneath. The "graph" claim invites a question we can't strongly answer ("what makes this a graph vs. RAG?"). Worse, our 1-hop graph expansion was shoveling neighbor entities into `items[]` regardless of whether the question was about them — so the voice agent's LLM was getting *Sarah* in the context when the user asked about *Leo*. That's confabulation-by-context.

The fix is architecturally simpler:

1. **Better chunks.** Every entity's Moss chunk bakes its relationships into the text:
   > "Leo, Amma's grandson and Sarah's son, 22, studies CS at Georgia Tech, visits Sundays, loves chess."

   The relationship IS the text. Moss semantic match on "Leo's mom" naturally returns Leo's chunk; the LLM reads "Sarah's son" and answers Sarah. No edge walk needed.

2. **Single τ relevance gate.** One hard threshold. Below it → safe refusal, period. Killing the 4-layer guard mess (off-topic word list, implicit-entity allowlist, entity-in-top, semantic floor).

3. **Multihop = query expansion, not graph traversal.** When a Moss chunk references another entity the question needs, fire a *second* Moss query for it. One extra hop, all via Moss. Replaces edge-walking.

4. **The LLM reasons, the engine retrieves.** Memory engine returns clean chunks + scores + provenance. The voice agent's LLM composes the answer. Stop pre-composing `answer_draft` for semantic queries — the LLM does it better with raw context.

---

## What's NOT changing

- **API contract.** `MemoryQueryResponse`, `MemoryTemporalResponse`, `/memory/write`, `/memory/capture`, `/reminders/due`, `/location/ping`, `/health` — all unchanged shapes.
- **Endpoints stay where they are**: `:8000`.
- **Latency budget**: regex-path stays sub-20ms; LLM-fallback still ~300ms.
- **Pending review queue for capture**: still `episodes(kind='pending_review')`. Track C dashboard plan unchanged.
- **Add-fact-live**, **wifi-off**, **pills-today**, **who-is**, **relational** — all 5 demo beats still work.

---

## Rushil — Track A (Voice) — TWO things

### 1. `answer_draft` is now usually null/minimal for `/memory/query`

Before: I was returning a pre-composed sentence in `answer_draft` for semantic queries (e.g. "Sarah is your daughter. Leo is your grandson."). The voice agent could just speak it.

After: For semantic queries, `answer_draft` will be a short hint or null. **Your LLM (Groq) composes the spoken answer from `items[]` using the grounding prompt.** This is better because:
- The LLM picks tone, length, and warmth — not me
- Fewer templated-sounding answers
- The grounding prompt in your `agent.py` already handles this exact pattern

`/memory/temporal` will still pre-compose answer_draft because grounded negatives ("you haven't taken your heart pill yet") need to be spoken verbatim — there's no semantic chunk for an absence.

**Action**: if your current code does `tts.speak(response['answer_draft'])`, swap to: if `answer_draft` is populated → use it; else → pass `items[]` to your grounding LLM. Both paths land in the same TTS output.

### 2. `items[]` is now leaner — just top-k Moss hits

Before: items could include graph-expanded neighbors at lower scores ("here's Sarah because she's connected to Leo").

After: items are pure Moss top-k. If the question needs a second entity, retrieval fires a second Moss query and includes those hits too. Either way, every item in `items[]` is semantically relevant to the question — no more neighbor pollution.

**Action**: none. If anything, your grounding prompt gets cleaner context.

---

## Raghav — Track C (Caregiver Web) — ONE thing

### `MemoryGraph.tsx` — keep, reframe

The dashboard graph view stays. It's a great visual for the pitch — "look at Amma's family + places + meds, all connected." What changes is the *language*:
- ❌ Don't say "the graph the agent uses to traverse memory"
- ✅ Say "the structure of Amma's memory, visualized" or "what the memory contains"

The graph isn't the engine — it's the inventory. That's still a strong dashboard story.

The rest of your scope (forms → `/memory/write`, timeline, pending-review confirmation, safety view) is **unchanged**. The `episodes(kind='pending_review')` filter for the confirm-capture UI is still the play.

---

## What's getting deleted in code

For visibility, not anything you need to track:
- `app/graph.py`: drop `_edges_by_ref`, `walk_relationship`, `format_edge_phrase`, `_RELATION_SENTENCE`, `_INVERSE`. Keep `_entity_text` cache (used for second-hop query expansion + capture entity resolution).
- `app/retrieval.py`: drop `_relational_walk`, graph expansion loop, multi-layer guards (`_OFF_TOPIC_HINTS`, `_IMPLICIT_ENTITY_WORDS`, `_entity_name_in_top`). Replace with single τ gate + query-expansion hop.
- `scripts/reseed_moss.py`: chunks rewritten to bake relationships into entity text.

Total: ~400 lines removed, ~80 added. Net cleaner.

---

## Pitch language (use this)

**Instead of**: "an episodic, temporal memory graph on Moss"
**Use**: "a living memory that lives inside the agent — instant updates usable mid-conversation, fully on-device, sub-10ms so it never breaks the flow of talking"

**Instead of**: "search engines organize information; we organize a human life as a graph"
**Use**: "search engines retrieve documents; Moss lets us retrieve a life — instantly, on-device, in the time it takes a person to take a breath"

The three demo beats ARE Moss's headline features applied to a human life:
- **Add-fact-live** = Moss instant index updates
- **Wifi-off** = Moss on-device, sub-10ms
- **Pills-today / temporal** = Moss-grounded retrieval + structured DB filtering

That's a stronger story than "we built a graph database in a hackathon."

---

## Timeline

- Now → ~2h: I refactor + re-run smoke + robustness
- Commit lands on `main` with a `feat(b7.1): simplify retrieval to chunks+τ` message
- I'll ping with a summary of test results

Questions: ask Keshav.
