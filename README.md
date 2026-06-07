# Yaad

A warm, bilingual voice companion for someone with early dementia, backed by a living memory that runs inside the agent — grounded, temporal, instantly updatable, and available offline.

Built at the **Conversational AI Hackathon — Moss (YC F25) @ Y Combinator** by Rushil, Keshav, and Raghav.

---

## The problem

By the time Alzheimer's progresses far enough, the people who love you become strangers. The tools that exist today are either passive (photo albums, journals) or generic (LLM chatbots with no persistent identity). Neither knows that Leo visits every Sunday, that you took your white pill at 8 this morning, or that the park two blocks away is the one you walked in for forty years.

Yaad is not a chatbot with a microphone. The novel part is the **memory layer**: every spoken answer is grounded in a structured, living record of that specific person's life — people, places, medications, routines, stories. It refuses to invent. It updates in real time. It works without internet.

The demo persona is "Amma," 84 — a fictional but fully seeded life: grandson Leo, daughter Sarah, a daily heart pill, a favourite park, regular visits, and a handful of episodic stories. Every answer the agent gives is traceable to a row in that database.

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────┐
│                        caregiver-web                        │
│   Next.js 15 · TypeScript · :3000                           │
│   Add memories · Graph · Timeline · Dashboard               │
└─────────────────┬───────────────────────────────────────────┘
                  │  POST /memory/write
                  │  GET  /memory/timeline
                  │  GET  /reminders/due
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                      memory-engine                          │
│   FastAPI · Python · :8000                                  │
│   Archetype router → Supabase + Moss                        │
│   Grounding gate · Provenance on every item                 │
└──────────────────┬──────────────────────────────────────────┘
                   │  POST /memory/query
                   │  POST /memory/temporal
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                       voice-agent                           │
│   Pipecat · LiveKit · arm64 Python                          │
│   VAD → Groq STT → memory lookup → LLM → MiniMax TTS       │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│                      vision-server                          │
│   Flask · face_recognition (dlib) · conda Python · :8765   │
│   Browser camera → face match → memory → TTS → audio       │
└─────────────────────────────────────────────────────────────┘
```

Three independently deployable packages share a single frozen API contract (`CONTRACT.md`). The memory engine is the hub; voice-agent and caregiver-web are both clients of it.

---

## Data model

Defined in `packages/memory-engine/app/schemas.py` and exported to `packages/shared/contract.openapi.json`. TypeScript types are generated from that file.

| Entity | Key fields |
|--------|-----------|
| `person` | name, relationship, aliases[], notes, preferences (JSONB), is_reassurance_contact |
| `place` | name, kind (home/familiar/other), lat?, lng?, notes |
| `event` | title, kind, start_ts, end_ts?, place_id?, participant_ids[], notes |
| `medication` | name, schedule_rrule (RFC 5545), notes |
| `med_log` | medication_id, taken_ts, source |
| `story` | title, text, people_ids[], occurred_ts? |
| `episode` | title, occurred_ts, kind, entity_refs[], summary |
| `edge` | from_ref, to_ref, type, weight |
| `safe_zone` | center_place_id, radius_m, contact_ids_ordered[] |
| `location_ping` | ts, lat, lng, inside_zone |
| `alert` | ts, kind (wander/lost), lat, lng, contacts_notified[], status |

Every embeddable row carries `provenance { source, added_by, added_ts }`.

---

## End-to-end data flows

### Voice flow

```
LiveKit room (audio in)
  │
  ▼
VADProcessor  ──── Silero VAD model
  │  emits VADUserStartedSpeakingFrame / VADUserStoppedSpeakingFrame
  ▼
GroqWhisperSTTService  ──── whisper-large-v3-turbo via Groq
  │  buffers utterance; on silence emits TranscriptionFrame{text, language}
  ▼
MemoryContextProcessor
  │
  ├─ Hindi query? → translate to English via LLM (Moss index is English-only)
  │
  ├─ temporal keyword? (pill/taken/today/visit/…)
  │     └─ POST /memory/temporal  → answer_draft (pre-composed, grounded)
  │          ├─ Hindi mode: translate answer_draft → Devanagari via LLM
  │          └─ emit answer_draft verbatim as TextFrame (skip LLM compose)
  │
  └─ semantic query
        └─ POST /memory/query  → {items[], grounded, confidence, answer_draft}
             └─ build messages [SYSTEM_PROMPT + MEMORY_CONTEXT + USER_SAID]
                  └─ stream LLM response → TextFrame chunks
  │
  ▼
SentenceAggregator  ──── buffers TextFrames until sentence-ending punctuation
  │
  ▼
MiniMaxTTSService
  │  detects Devanagari → Wise_Woman voice + language_boost:Hindi
  │  otherwise → English_Graceful_Lady
  │  POST https://api.minimax.io/v1/t2a_v2 → hex-encoded MP3 → PCM
  │
  ▼
LiveKit room (audio out)
```

**Barge-in:** Silero VAD emits `VADUserStartedSpeakingFrame` mid-response; Pipecat propagates `StartInterruptionFrame` to cancel in-flight TTS and LLM work.

**Fixture fallback:** `MemoryContextProcessor` wraps every memory call in a 3s timeout. On failure, `fallback.py` pattern-matches the query to one of five pre-written fixture responses (Leo, Sarah, pills, Hindi-Leo, default) so the demo never hard-fails.

**Latency tracking:** a `LatencyTracker` dataclass accumulates STT, memory, LLM, and TTS times per turn; logs `[LATENCY]` at the end of every response.

**Hindi path:** query translated to English for memory retrieval; reply composed in Hindi via explicit `[LANGUAGE]` anchor in the LLM prompt; Devanagari detected by Unicode block U+0900–U+097F to route TTS voice.

---

### Vision flow

The terminal process cannot obtain macOS camera permission, but Chrome already has it. The vision server bridges this by serving a browser page that owns the camera:

```
Chrome browser  ──── getUserMedia({video:true})
  │  "Capture" click → drawImage to canvas → toDataURL('image/jpeg')
  │
  ▼  POST /match  {image: dataURL}
Flask vision-server (:8765, conda Python)
  │
  ├─ base64-decode JPEG → RGB numpy array
  ├─ face_recognition.face_encodings(rgb)
  │    (dlib CNN model, x86_64/Rosetta)
  ├─ face_recognition.face_distance(reference_encodings, live_encoding)
  └─ min distance < 0.6 → matched name; else "unknown"
  │
  ▼  POST /greet  {name}  (if known person)
  ├─ POST /memory/query {"text": "who is {name}?", "lang": "en"}
  │    → {grounded, answer_draft, items[]}
  │
  ├─ grounded=True? → POST TrueFoundry LLM
  │    system: Yaad grounding prompt + "rephrase into ONE warm spoken sentence"
  │    user:   answer_draft (grounded facts only)
  │    → composed sentence
  │
  └─ POST https://api.minimax.io/v1/t2a_v2
       voice: English_Graceful_Lady, model: speech-02-hd
       → hex MP3 → base64
  │
  ▼  JSON  {name, text, audio_base64}
Browser
  │  new Audio("data:audio/mp3;base64,…").play()
  │  fallback: show "▶ Play" button if autoplay blocked
```

Reference photos live in `packages/voice-agent/references/` (filename stem = person label). Each reference is encoded once at load time; distances are printed to terminal on every match.

---

## Memory engine: archetype routing and the grounding design

This is the differentiating layer. The core claim is: **the agent only states facts it can cite**. Every response carries `grounded` (bool), `confidence` (float), and `provenance` (source table + who added it + when). Below the confidence threshold, the answer is a safe refusal — never a hallucination.

### Archetype router (`app/router.py`)

A query goes through classification before any data is touched:

```
classify(query)
  │
  ├─ _force_refusal()         → nonsense / out-of-scope → episodic (returns refusal)
  ├─ remember_phrases         → "remember" archetype (triggers capture)
  ├─ _looks_medical()         → temporal_med
  ├─ _looks_event()           → temporal_event
  ├─ _looks_relational()      → relational
  ├─ _preference_key()        → preference
  ├─ entities or identity kw  → identity
  └─ none of the above        → Groq LLM fallback (llama-3.1-8b-instant, JSON mode)
                                 falls back to episodic on any error
```

Classification is **regex first** (sub-20ms), LLM fallback only when regex is ambiguous (~300ms, gated by `groq_api_key` presence). Named entities are extracted from the query by matching known person/place names from Supabase plus capitalized spans.

### Archetype substrates

Each archetype reads from a specific data source — there is no single index:

| Archetype | Data source | What it answers |
|-----------|-------------|-----------------|
| `identity` | Supabase `persons` + `places`, alias matching | "Who is Leo?" / "Where do I live?" |
| `relational` | In-process `edges_cache` (loaded from `edges` table) | "How is Sarah related to me?" |
| `temporal_med` | Supabase `med_logs` window query + medication row | "Did I take my pill today?" |
| `temporal_event` | Supabase `events` window query + participant lookup | "When is Sarah coming?" |
| `preference` | `persons.preferences` JSONB column | "What does Leo like to eat?" |
| `episodic` | Moss `SessionIndex` over `stories` + `episodes(kind='captured_fact')` | "Do you remember when…?" |
| `remember` | `capture.py` → structured extraction → Supabase + Moss | "Remember that Leo got a promotion." |

Moss is used **only for episodic content** (stories, captured facts). Structural entities (persons, places, medications, events) are retrieved from Supabase by exact/alias match — not by vector similarity. This eliminates the hallucination risk that comes from embedding-nearest-neighbor retrieval on named entities.

### Grounding gate (`app/grounding.py`)

Every archetype calls `assess_grounding(items, query, lang)` before returning:

```python
if not items:
    return grounded=False, confidence=0.0, answer_draft=SAFE_REFUSAL

top_score = items[0].score
grounded = top_score >= settings.episodic_tau

if grounded:
    answer_draft = join(item.text for item in items[:3])
else:
    answer_draft = SAFE_REFUSAL   # "I'm not sure. Let me check with the family."
```

`answer_draft` is the pre-composed text the voice agent emits verbatim on the **temporal path** — it is never re-composed by the LLM, so negatives like "not yet taken" can't be flipped or softened.

### Absence facts

`temporal_med` explicitly handles the case where no log exists. Rather than returning zero items (which would produce a generic refusal), it synthesises a `med_log` item with `source: "absence"` and `score: 0.95`, with text like `"No heart pill logged today."` The resulting `answer_draft` is `"I don't see your heart pill logged today."` — grounded in the absence of a record, not in silence.

### Instant-update path (`/memory/write`)

When the caregiver adds a fact through the web app, the handler:
1. Writes to Supabase (canonical store)
2. Upserts the rendered chunk to Moss in the same HTTP request
3. Reloads the `edges_cache`

The next voice query can find the fact without a server restart or reseed. Confirmed at ~837ms end-to-end in testing.

### Startup self-heal

Moss `SessionIndex` does not reliably resume its in-process state after a process restart. On startup, `main.py` calls `reseed_moss()` — which reads all `stories` and `episodes(kind='captured_fact')` from Supabase and upserts them into the current Moss session. Cost: ~3–5s. This is why `/memory/query` works immediately after `uvicorn` starts, without a separate reseed step.

### No-confabulation rules (enforced in code, not just prompt)

- `grounded=false` → `answer_draft` = safe refusal, always. The LLM is never asked to compose from an empty or low-confidence context.
- The LLM is **never in the storage path**: seeding, reseeding, ingesting, and writing all use raw Supabase payloads. Groq's role is router classification and capture extraction — it never rewrites stored data.
- Structural archetypes return `items=[], grounded=false` on empty lookup. They do not fall through to Moss.
- Provenance is mandatory on every `RetrievedItem`: `{source, added_by, added_ts}`.

---

## Document ingestion (`/ingest/document`)

Upload a medical PDF → the response is queryable on the next voice turn:

```
POST /ingest/document  (multipart, field: "document")
  │
  ├─ Unsiloed: upload PDF → doc_id
  ├─ Unsiloed: chat(doc_id, structured prompt) → raw extraction
  │
  ├─ OpenAI gpt-4o-mini (or Groq fallback):
  │    normalize raw extraction → {medications, events, persons, summary}
  │
  ├─ For each medication/event/person:
  │    write_memory() → Supabase row + Moss upsert
  │
  └─ Full extraction stored as a `story` row for free-text retrieval
```

Events without an absolute date are dropped rather than fabricated. Persons extracted from medical docs get `relationship: "doctor"` or the role from the document — family ties are never guessed.

---

## Wander safety

`POST /location/ping {lat, lng}` evaluates whether the patient is inside their safe zone. On exit:

1. Creates an `alert` row in Supabase
2. Sends SMS via Gmail SMTP → carrier gateway (e.g. `number@msg.fi.google.com`) — Twilio was removed because toll-free numbers require 3–7 day US carrier verification
3. Returns a Moss-personalized reassurance line: "You're near [familiar place]. You're safe. I've let [contact] know — they're on the way."

The agent never gives turn-by-turn navigation to a disoriented person. Lost → reassure + keep-in-place + alert a human.

---

## Tech stack

### Memory engine (`packages/memory-engine`)
| Component | Technology |
|-----------|-----------|
| API framework | FastAPI (Python) |
| Persistent store | Supabase (PostgreSQL) |
| Episodic index | Moss `SessionIndex` (vector, in-process) |
| Router classification LLM | Groq `llama-3.1-8b-instant` (fallback path only) |
| Capture extraction | Groq `llama-3.1-8b-instant` |
| Document normalization | OpenAI `gpt-4o-mini` (Groq fallback) |
| Document parsing | Unsiloed |
| SMS alerts | Gmail SMTP → carrier gateway |

### Voice agent (`packages/voice-agent`)
| Component | Technology |
|-----------|-----------|
| Pipeline framework | Pipecat |
| Real-time transport | LiveKit |
| VAD | Silero (via Pipecat) |
| STT | Groq Whisper `whisper-large-v3-turbo` |
| LLM | TrueFoundry gateway → `openai/gpt-4o-mini` |
| TTS | MiniMax `speech-02-hd` · voices: `English_Graceful_Lady` / `Wise_Woman` |
| Local audio | sounddevice (--local mode, arm64 only) |
| Python runtime | arm64 native (`arch -arm64 python3`) |

### Vision server (`packages/voice-agent/app/vision_server.py`)
| Component | Technology |
|-----------|-----------|
| Server | Flask 3.1 |
| Face recognition | `face_recognition` 1.3 (dlib 20, CNN model) |
| Image decode | OpenCV (BGR→RGB), Pillow |
| Python runtime | conda x86_64 (`~/anaconda3/bin/python3`, Rosetta 2) |

### Caregiver web (`packages/caregiver-web`)
| Component | Technology |
|-----------|-----------|
| Framework | Next.js 15 (App Router) |
| Language | TypeScript |
| Styling | Tailwind CSS 4 |
| Memory graph | react-force-graph-2d |
| Type generation | openapi-typescript from `contract.openapi.json` |

---

## The two-runtime split

The voice agent and the vision server run under different Python runtimes on the same machine:

**Voice agent — arm64 native Python**
Pipecat's audio processing (VAD, local sounddevice transport) requires a native arm64 binary on Apple Silicon. Running under Rosetta introduces frame-timing issues. Invoked as `arch -arm64 python3 -m app.agent`.

**Vision server — conda Python (x86_64/Rosetta)**
`face_recognition` depends on dlib, which builds a different binary for x86_64 and arm64. The conda installation on this machine is x86_64. The `arch -arm64` flag cannot run an x86_64 binary (`Bad CPU type in executable`). The vision server runs under `~/anaconda3/bin/python3` (x86_64, Rosetta 2).

**Camera bridge**
The terminal process cannot request macOS camera permission. Chrome already has it. The vision server at `:8765` serves an HTML page that runs `getUserMedia`, captures a frame, and POSTs a JPEG to the server. The server never touches a camera device — only the browser does. This sidesteps the permission problem entirely.

---

## Repository layout

```
yaad/
├── CONTRACT.md                  # Frozen API + schema (source of truth)
├── STATUS.md                    # Live build log — updated every commit
├── CLAUDE.md                    # Build spec and meta-instructions
├── docker-compose.yml
├── fixtures/                    # Demo fallback payloads (served on timeout)
├── scripts/
│   ├── seed_amma.py             # Initial Supabase seed (run once)
│   ├── reseed_moss.py           # Repopulate Moss from Supabase
│   ├── dedupe_supabase_seed.py  # Remove duplicate rows after repeated seeds
│   └── smoke_wander.py          # End-to-end wander alert test
├── packages/
│   ├── memory-engine/           # Track B — FastAPI memory service
│   │   ├── app/
│   │   │   ├── main.py          # FastAPI routes + startup reseed
│   │   │   ├── router.py        # Archetype classifier
│   │   │   ├── archetypes/      # identity, relational, temporal_med,
│   │   │   │                    #   temporal_event, preference, episodic
│   │   │   ├── grounding.py     # Grounding gate + safe refusal
│   │   │   ├── db.py            # Supabase read/write helpers
│   │   │   ├── moss_client.py   # Moss SessionIndex wrapper
│   │   │   ├── edges_cache.py   # In-process edge/relation cache
│   │   │   ├── chunks.py        # Chunk text renderer (person/place/story/…)
│   │   │   ├── capture.py       # Transcript → structured extraction → Moss
│   │   │   ├── ingest.py        # PDF → Unsiloed → Groq normalize → write
│   │   │   ├── temporal.py      # Timeline queries
│   │   │   ├── time_window.py   # Relative-time parser ("today", "yesterday")
│   │   │   ├── location.py      # Safe-zone evaluation + SMS alerts
│   │   │   ├── reminders.py     # /reminders/due logic
│   │   │   ├── intent.py        # (legacy) intent helpers
│   │   │   └── retrieval.py     # (legacy) pre-archetype retrieval path
│   │   └── tests/
│   │       ├── robustness.py          # 30+ phrasing variants per demo beat
│   │       ├── test_grounding_integrity.py
│   │       ├── test_no_hallucination.py
│   │       ├── test_latency.py
│   │       └── test_general_queries.py
│   │
│   ├── voice-agent/             # Track A — Pipecat voice pipeline
│   │   ├── app/
│   │   │   ├── agent.py         # Pipeline definition + entry point
│   │   │   ├── stt_groq.py      # Groq Whisper STT service
│   │   │   ├── tts_minimax.py   # MiniMax TTS Pipecat service
│   │   │   ├── memory_client.py # HTTP client to /memory/query + /temporal
│   │   │   ├── llm.py           # LLM factory (TrueFoundry / OpenAI / Anthropic)
│   │   │   ├── transports.py    # LiveKit transport + Silero VAD factory
│   │   │   ├── local_transport.py # sounddevice mic/speakers (--local mode)
│   │   │   ├── lang_toggle.py   # 'h' key terminal toggle EN↔HI
│   │   │   ├── fallback.py      # Fixture responses on memory timeout
│   │   │   ├── reminders_client.py # Background poller for /reminders/due
│   │   │   ├── vision_match.py  # CLI face-match: references/ → dlib → name
│   │   │   └── vision_server.py # Flask server: browser camera → match → greet
│   │   └── references/          # Reference photos (filename stem = label)
│   │
│   └── caregiver-web/           # Track C — Next.js caregiver dashboard
│       ├── app/
│       │   ├── (dashboard)/page.tsx  # Reminders, upcoming events, system health
│       │   ├── memories/page.tsx     # Add person/event/medication/story/PDF
│       │   ├── graph/page.tsx        # Force-directed memory graph
│       │   ├── timeline/page.tsx     # Date-filtered timeline
│       │   └── safety/page.tsx       # [stub] Geofence + contacts
│       ├── app/api/
│       │   ├── graph/route.ts        # Server: Supabase → nodes + edges
│       │   ├── upcoming/route.ts     # Server: next 7 days of events
│       │   ├── priority/route.ts     # Server: LLM-generated caregiver prompts
│       │   └── engine/ingest/document/route.ts  # Proxy for PDF upload
│       ├── components/MemoryGraph.tsx  # react-force-graph-2d (SSR-disabled)
│       └── lib/
│           ├── api.ts            # Typed wrappers for all memory-engine endpoints
│           └── types.ts          # Generated from contract.openapi.json
└── packages/shared/
    └── contract.openapi.json    # Generated from schemas.py (source of truth)
```

---

## Setup

### Prerequisites

- Python 3.11+ (arm64 native) for the voice agent
- Anaconda / conda (x86_64) for the vision server
- Node.js 18+ for caregiver-web
- A running Supabase project (all 12 tables from `schemas.py`)
- API keys: see `.env.example`

Copy `.env.example` to `.env` and fill in all values before running anything.

**Required keys:**
```
MOSS_API_KEY=
MOSS_INDEX=yaad_amma
GROQ_API_KEY=
MINIMAX_API_KEY=
LIVEKIT_URL=        LIVEKIT_API_KEY=    LIVEKIT_API_SECRET=
TRUEFOUNDRY_BASE_URL=  TRUEFOUNDRY_MODEL=  TRUEFOUNDRY_API_KEY=
SUPABASE_URL=       SUPABASE_SERVICE_KEY=
UNSILOED_API_KEY=
MEMORY_ENGINE_URL=http://localhost:8000
EMAIL_FROM=         EMAIL_APP_PASSWORD=   # for wander SMS alerts
```

### 1. Seed the database (once)

```bash
# From repo root — only run this once; running again duplicates rows.
python scripts/seed_amma.py
```

### 2. Memory engine

```bash
cd packages/memory-engine
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
# Startup reseeds Moss automatically (~3-5s); watch for "[startup] Moss session reseeded"
```

Verify: `curl http://localhost:8000/health` should return `{"moss_ok": true, "db_ok": true, ...}`.

To reseed Moss manually (e.g. after dirty test runs):
```bash
python scripts/reseed_moss.py --wipe
```

### 3. Voice agent

Requires arm64 native Python. Do not run under conda/Rosetta.

```bash
cd packages/voice-agent
pip install -r requirements.txt       # into your arm64 Python env

# LiveKit mode (connects to room defined by LIVEKIT_ROOM in .env)
arch -arm64 python3 -m app.agent

# Local mic + speakers (no LiveKit required, useful for development)
arch -arm64 python3 -m app.agent --local
```

Press `h` in the terminal to toggle between English and Hindi.

### 4. Vision server

Runs under conda Python (x86_64). face_recognition must be installed in that environment.

```bash
pip install face_recognition --break-system-packages   # into conda env
# dlib builds from source; takes ~5 minutes the first time

cd packages/voice-agent
~/anaconda3/bin/python3 -m app.vision_server
# Open http://localhost:8765 in Chrome
```

Place reference photos in `packages/voice-agent/references/` — filename stem becomes the label (`leo.jpg` → "Leo"). At least one clear frontal face per file.

CLI face-match (no browser, no audio):
```bash
# From packages/voice-agent/
~/anaconda3/bin/python3 -m app.vision_match /path/to/photo.jpg
~/anaconda3/bin/python3 -m app.vision_match --camera   # capture from webcam
```

### 5. Caregiver web

```bash
cd packages/caregiver-web
# .env.local must exist and contain SUPABASE_URL + SUPABASE_SERVICE_KEY
# (simplest: symlink to root .env)
ln -sf ../../.env .env.local
npm install
npm run dev    # http://localhost:3000
```

Memory engine must be running at `:8000` for writes and reads to work. The Next.js config proxies `/api/engine/*` → `MEMORY_ENGINE_URL`.

### Running the full stack

```bash
# Terminal 1 — memory engine
cd packages/memory-engine && source .venv/bin/activate
uvicorn app.main:app --port 8000

# Terminal 2 — voice agent (LiveKit)
cd packages/voice-agent
arch -arm64 python3 -m app.agent

# Terminal 3 — vision server
cd packages/voice-agent
~/anaconda3/bin/python3 -m app.vision_server

# Terminal 4 — caregiver web
cd packages/caregiver-web && npm run dev
```

### Running tests

```bash
cd packages/memory-engine
source .venv/bin/activate

pytest tests/smoke_test.py -s -v
pytest tests/robustness.py -s -v           # 30+ phrasing variants per demo beat
pytest tests/test_grounding_integrity.py -s -v
pytest tests/test_no_hallucination.py -s -v
pytest tests/test_latency.py -s -v
```

All five suites must pass before demo. Latency test verifies p95 < 60ms server-side on structural archetypes.

---

## API reference (summary)

Full schema: `packages/shared/contract.openapi.json`.

| Endpoint | Input | Output |
|----------|-------|--------|
| `POST /memory/query` | `{text, lang}` | `{items[], grounded, confidence, answer_draft}` |
| `POST /memory/temporal` | `{text, lang}` | same shape, routed through temporal logic |
| `POST /memory/write` | `{type, payload}` | `{id}` — writes Supabase + Moss |
| `POST /memory/capture` | `{transcript}` | `{created_refs[]}` |
| `GET  /memory/timeline` | `?date=YYYY-MM-DD` | `{blocks[]}` |
| `GET  /reminders/due` | `?ts=<iso>` | `{due[{kind, text, ref}]}` |
| `POST /location/ping` | `{lat, lng}` | `{inside_zone, action, reassurance_text?}` |
| `POST /ingest/document` | multipart PDF | `{created_refs[], summary, raw_extraction}` |
| `GET  /health` | — | `{moss_ok, db_ok, latency_ms, moss_doc_count}` |

`RetrievedItem` shape:
```json
{
  "ref": "person:uuid",
  "type": "person",
  "text": "Leo. grandson. 22 years old...",
  "score": 1.0,
  "provenance": {"source": "persons", "added_by": "seed_script", "added_ts": "…"}
}
```

---

## What is and isn't built

### Built and working

- Full voice pipeline: VAD → Groq STT → archetype-routed memory → LLM compose or answer_draft bypass → MiniMax TTS → LiveKit
- Archetype router with 7 routes; regex fast-path + Groq LLM fallback
- Grounding gate: every response has `grounded`, `confidence`, `provenance`; refusal on low confidence
- Temporal medication queries: both "taken" and "not yet taken" cases, with absence-grounded answer
- Instant-update: `/memory/write` upserts to Moss in the same request; voice agent can query the new fact in <1s
- Hindi ↔ English routing: query translation, Hindi answer_draft translation, Devanagari-triggered TTS voice switch
- 5-beat fixture fallback on 3s memory timeout
- Startup Moss self-heal (reseed from Supabase on every process start)
- Vision server: browser camera → face_recognition (dlib) → memory query → LLM greeting → MiniMax TTS → browser audio
- Caregiver web: add-memory forms (person/event/medication/story), graph view, timeline, care dashboard with reminders
- Medical PDF ingestion: Unsiloed parse → Groq/OpenAI normalize → write to Supabase + Moss
- Wander alerts: safe-zone evaluation + Gmail SMTP → carrier-gateway SMS
- Latency instrumentation: per-turn STT/memory/LLM/TTS breakdown logged to console

### Roadmap (not yet built)

- **TTS pre-cache for wifi-off beat** — `fixtures/tts/*.mp3` not generated. The wifi-off demo beat requires pre-synthesized audio clips. When the memory engine is unreachable, fixture text is returned but no audio plays.
- **A3 speculative memory query** — firing the memory call on partial transcript (before STT completes) to shave latency. Not yet wired; the pipeline fires only on final `TranscriptionFrame`.
- **A5 proactive reminders in pipeline** — `reminders_client.py` polls `/reminders/due` but the result is not injected into the Pipecat pipeline as speech. Poller runs, announcements do not.
- **Safety view (C5)** — `packages/caregiver-web/app/safety/page.tsx` is a page stub. The geofence schema and backend are complete; the map UI and contact ordering UI are not built.
- **Architecture diagram (C6)** — `docs/ARCHITECTURE.md` planned but not created.
- **Caregiver preferences editor** — `persons.preferences` JSONB is supported by the schema and `preference` archetype; there is no UI for editing preferences in the caregiver web.
- **Hindi multilingual memory** — the `lang` parameter is accepted everywhere but ignored; the engine always queries in English. Hindi input is translated to English before hitting Moss. True Hindi-stored memory is a future addition.
- **Auto-capture from conversation** — `/memory/capture` is wired and functional for explicit "remember that…" utterances. Autonomous background capture from free conversation (detecting memorable facts automatically) creates `pending_review` proposals rather than committing directly.
- **`face_embedding` field** — `persons.face_embedding` is in the schema; it is not populated. The vision match works by comparing against files in `references/`, not against embeddings stored in the database.

---

## Key design decisions

**Structural data out of the vector index.** Person names, medication schedules, and event dates are retrieved by exact/alias match from Supabase, not by embedding similarity. Vector search (Moss) is reserved for stories and episodic facts where semantic matching is the right operation. This eliminates the risk of a "Leo" query returning a chunk about a different person who happened to mention Leo's name.

**answer_draft bypass on temporal queries.** The temporal archetype pre-composes the answer (`"Yes, you took your heart pill at 8:00am"` / `"I don't see your heart pill logged today"`). The voice agent emits this verbatim rather than passing it through the LLM. An LLM re-composing a negation ("not yet taken") risks softening or inverting it. Pre-composed drafts prevent this.

**Absence as a grounded fact.** When no medication log exists for a time window, the temporal archetype does not return zero items (which would produce a generic refusal). It returns a synthetic `med_log` item with `source: "absence"` — the absence of a record is itself a grounded, citable fact. The agent can say "I don't see your pill logged" with the same confidence as "You took it at 8."

**Demo fixture fallback at every external call.** The voice agent wraps every memory, LLM, and TTS call in a timeout. On failure it returns a fixture response matching the query topic. The demo can run its five beats even if the memory engine or TTS service is unreachable.

**Two-runtime split.** The voice agent runs natively on arm64 (required for audio). The vision server runs under x86_64 conda (required for dlib). The browser bridges camera permission. Three processes, one demo.
