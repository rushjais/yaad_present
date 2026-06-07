# Yaad - the memory retrieval engine


# (Feedback at the bottom)
Yaad is not ChatGPT with a microphone.

Built for the **Conversational AI Hackathon — Moss (YC F25) @ Y Combinator** by Rushil, Keshav, and Raghav.

---

## The Demo In One Sentence

The caregiver adds a memory, the patient asks a question by voice, Yaad retrieves the right life fact instantly, speaks it back through LiveKit + MiniMax, recognizes a familiar face through the camera, parses medical PDFs into structured memory, and still has cached speech fallbacks when services fail.

---

## Why?

Both Rushil and Keshav's grandparents have dealt with alzheimer's and parkinsons throughout their childhood. The two noticed how taxing the process was on the grandparents and their caregivers (their mom and dad). Senior citizens dealing with conditions like dementia and alzheimer's have rapid memory deterioration, and often need external help to recollect and communicate. When constantly reminded of friends and family, studies show the deterioration process slows, especially when conversation is constant. But caretakers are human and have their own limits. Yaad bridges the gap: input memories, photos, events, and Yaad recollects and semantically matches to remind patients of upcoming events, past memories, and present people. We don't use a SIM [le vector database]. Our memory layer builds on moss for quick retrieval and semantically accurate searching past just keywords. 

For someone with dementia, a generic assistant is dangerous if it invents details. A confident hallucination about a person, medication, visit, or location can become distressing or unsafe. Yaad is designed around the opposite behavior:

- **Grounded-only answers:** if the memory engine cannot cite a row, it refuses.
- **Temporal reasoning:** "Did I take my pills today?" reads today’s `med_logs`, not a vector match.
- **Living memory:** caregiver edits are queryable on the next turn.
- **Human identity graph:** relationships and places are first-class data, not free text.
- **Warm voice:** the final answer is calm and human, but the facts are constrained.

The demo persona is **Amma**, 84: grandson Leo, daughter Sarah, home, Lullwater Park, medication routines, visits, preferences, stories, and safety context.

### Moss Usage

Moss is central to Yaad’s retrieval path. It is used where vector retrieval is strongest and most useful in conversation:

- Indexed: `stories.text`, `episodes(kind='captured_fact').summary`
- Also fed by write-through updates so new conversational memory is available immediately
- Kept alongside Supabase so canonical rows remain the source of truth
- Startup reseed repopulates the in-process Moss session from Supabase
- `/memory/write` upserts relevant new content immediately

This keeps Moss as the fast recall layer for semantic memory while Supabase remains the canonical source of truth for exact facts.

---

## The Memory Engine

The memory engine is where the magic is. We didn't just integrate Moss; we made a framework built to complement it. By taking advantage of Moss's ability to work locally, we created a knowledge graph equipped with filtering and semantic preferences that amplify everything Moss was built for: low latency, retrieval, and accurate results. Our system needs **instant retrieval from our own framework, not the web**, and Moss lets us make that distinction. Built around **archetype separation**, we separate data into streams in our database, so that different functional information is sorted and retrieved in different processes. The router chooses the right substrate before retrieving. This avoids the common RAG failure mode where everything is a vector query and nearest-neighbor text is treated as truth.

---

## Features!

| Area | Status | What it shows |
|---|---:|---|
| Live voice agent | Working | LiveKit room → VAD → Groq STT → memory → TrueFoundry LLM → MiniMax TTS |
| Memory engine | Working | FastAPI archetype router over Supabase + Moss |
| Temporal medication answers | Working | "Did I take my pills today?" reads `med_logs` with absence-aware responses |
| Instant caregiver updates | Working | `/memory/write` writes Supabase and updates Moss in the same request |
| Bilingual voice path | Working | Hindi input translated for English memory retrieval; Hindi output uses Devanagari + MiniMax Hindi voice |
| Vision greeting | Working | Browser camera → face match + recognition of faces for memory retrieval → grounded greeting → TTS audio |
| PDF ingestion (Medical records) | Working | Unsiloed PDF parse → LLM normalization → typed Yaad records |
| Caregiver web | Working | Next.js dashboard, memories, graph, timeline, document upload |



## System Architecture

```
┌───────────────────────────────────────────────────────────────────┐
│                          caregiver-web                            │
│     Next.js 15 · TypeScript · dashboard/graph / timeline         │
│     Add people, stories, medication logs, events, PDFs             │
└───────────────────────┬───────────────────────────────────────────┘
                        │
                        │ POST /memory/write
                        │ POST /ingest/document
                        │ GET  /memory/timeline
                        ▼
┌───────────────────────────────────────────────────────────────────┐
│                         memory-engine                             │
│     FastAPI · Supabase canonical store · Moss episodic index       │
│     Archetype router · grounding gate · provenance everywhere      │
│                                                                   │
│     identity       → Supabase persons/places                      │
│     relational     → edges_cache                                  │
│     temporal_med   → med_logs + medications                       │
│     temporal_event → events + participants                        │
│     preference     → persons.preferences JSONB                    │
│     episodic       → Moss stories + captured facts                │
│     remember       → capture extraction                           │
└───────────────────────┬───────────────────────────────────────────┘
                        │
                        │ POST /memory/query
                        │ POST /memory/temporal
                        ▼
┌───────────────────────────────────────────────────────────────────┐
│                           voice-agent                             │
│     Pipecat · LiveKit · Silero VAD · Groq Whisper STT              │
│     TrueFoundry LLM composition · MiniMax TTS                      │
│     Cached MP3 fallback for demo resilience                        │
└───────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────┐
│                          vision-server                            │
│     Flask · browser camera · face_recognition/dlib                 │
│     Face match → memory query → grounded greeting → audio          │
└───────────────────────────────────────────────────────────────────┘
```

The services share a frozen API contract in `CONTRACT.md` and generated OpenAPI schema in `packages/shared/contract.openapi.json`.

---


## Why This Is Not Just RAG

Yaad is not a single vector search wrapped in an LLM prompt. It is a routed memory system:

- **Structured facts stay structured.** Names, relationships, medications, events, and preferences are looked up from the right table or graph edge instead of being inferred from nearest neighbors.
- **Moss handles semantic recall.** It retrieves episodic memory, story text, and captured facts quickly enough for live conversation.
- **Grounding is enforced after retrieval.** The engine refuses when no grounded item is found rather than inventing a plausible answer.
- **Writes are immediate.** New facts become queryable on the next turn because the write path updates both Supabase and the live memory layer.
- **The voice layer is downstream.** The memory engine returns grounded items and a draft; the voice agent composes the final spoken response from those facts.

That split avoids the usual RAG failure mode: one embedding index becomes the source of truth for everything, and “close enough” text gets mistaken for a fact.

### Query Archetypes

| Archetype | Data source | Example | Why it matters |
|---|---|---|---|
| `identity` | Supabase `persons`, `places` | "Who is Leo?" | Exact/alias lookup beats fuzzy name retrieval |
| `relational` | In-memory `edges_cache` | "Who is my grandson?" | Relationships are graph facts |
| `temporal_med` | `med_logs`, `medications` | "Did I take my pill today?" | Time state is not semantic similarity |
| `temporal_event` | `events`, participants | "Is Sarah visiting today?" | Calendar facts stay structured |
| `preference` | `persons.preferences` | "What is my favorite music?" | Categorical facts are deterministic |
| `episodic` | Moss `SessionIndex` | "Tell me the garden story" | Stories need semantic recall |
| `remember` | capture pipeline | "Remember that..." | Explicit capture creates reviewable memory |

### Grounding Contract

The most important part: the memory source refuses to hallucinate. If it can't match with confidence:

{
  "answer_draft": "I'm not sure about that right now. Let me check with the family."
}

A follow-up can be logged for the caregiver, but the answer itself stays grounded. Yaad lets the family handle the obscure. AI can only help when it's sure.



## Voice Pipeline

```
LiveKit audio
  → Silero VAD
  → Groq Whisper STT
  → MemoryContextProcessor
      → /memory/temporal for medication/calendar queries
      → /memory/query for identity, preference, relational, episodic queries
      → fixture fallback on timeout
  → TrueFoundry LLM composition for semantic answers
  → MiniMax TTS
  → LiveKit audio out
```

## Vision Pipeline

The vision server avoids macOS terminal camera-permission issues by letting Chrome own the camera:

```
Chrome getUserMedia
  → canvas JPEG
  → POST /match
  → face_recognition encoding
  → nearest reference face
  → POST /greet
  → memory query
  → grounded greeting
  → MiniMax or cached MP3
  → browser audio playback
```

Reference files live in:

```text
packages/voice-agent/references/
```

The filename stem becomes the spoken label:

```text
leo.jpg → Leo
```

---

## Caregiver Web

The web app is the family-facing control panel.

Current surfaces:

- **Dashboard:** priorities, reminders, upcoming events, system context
- **Memories:** add person, event, medication, story, or medical document
- **Graph:** force-directed view over people, places, and edges
- **Timeline:** date-filtered memory timeline
- **Safety:** geofence/backend exists; UI is currently prototype-grade

The important demo surface is **add-fact-live**: a caregiver writes a new fact, the memory engine commits it to Supabase and Moss, and voice can retrieve it on the next turn.

---

## Document Ingestion

Medical document flow:

```
PDF upload
  → Unsiloed parse
  → structured extraction prompt
  → OpenAI/Groq normalization
  → medications/events/persons/stories
  → Supabase rows
  → Moss episodic upsert
```


---




## Tech Stack

### Memory Engine

| Layer | Technology |
|---|---|
| API | FastAPI, Pydantic v2 |
| Canonical data | Supabase/Postgres |
| Episodic vector index | Moss `SessionIndex` |
| Router fallback | Groq `llama-3.1-8b-instant` |
| Capture extraction | Groq |
| PDF parsing | Unsiloed |
| PDF normalization | OpenAI `gpt-4o-mini` or Groq fallback |
| Alerts | Gmail SMTP → carrier gateway |

### Voice + Vision

| Layer | Technology |
|---|---|
| Voice orchestration | Pipecat |
| Realtime transport | LiveKit |
| VAD | Silero |
| STT | Groq Whisper |
| LLM composition | TrueFoundry gateway |
| TTS | MiniMax |
| Face recognition | `face_recognition`, dlib |
| Browser vision bridge | Flask + Chrome `getUserMedia` |

### Web

| Layer | Technology |
|---|---|
| Framework | Next.js 15 App Router |
| Language | TypeScript |
| Styling | Tailwind CSS 4 |
| Graph | react-force-graph-2d |
| Types | openapi-typescript |



## Guardrails

Yaad is designed for a sensitive domain. The product rules are explicit:

- Never invent people, events, medications, locations, or relationships.
- Never correct or argue with the patient.
- Never expose fake clinical scores.
- Never navigate a lost patient turn-by-turn.
- Prefer safe refusal over a plausible guess.
- Every memory item must cite provenance.
- LLMs compose from retrieved facts; they do not become the source of truth.

## Feedback (In case the sponsors would like some :)  
We loved Moss's retrieval and api capability. Our only struggle was trying to resume an index in a fresh process with SessionIndex.session(). We struggled and opted to reseed with Supabase at startup instead. A "patterns we don't recommend" page in the docs would have saved us a full router rebuild.

Livekit integrated well into our project. The workflow was a little confusing to navigate at first, but after some struggling with WebRTC we figured it out. Second, livekit-client adds ~120 KB gzipped to a patient-web bundle that should ideally be under 100 KB total; a slimmer  entry point would help mobile-first products a lot.



Unsiloed: We noticed latency on the product, and created a parallel processing system to call the api while proceeding with other functions to sidestep waiting times. The parsing results were great and exactly what our system needed. 


