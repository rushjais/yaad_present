# Voice + Vision Deployment Map

Everything that must be running for the voice pipeline and the vision (face-match) pipeline to work end to end. Read this before a demo or a deploy.

---

## What "voice" touches — service map

```
                     ┌─────────────────────────────────┐
                     │         LiveKit Cloud            │
                     │   wss://keepsake-y39026vu        │
                     │        room: yaad-demo           │
                     └──────────┬──────────┬────────────┘
                    audio in    │          │   audio out
                                │          │
                     ┌──────────▼──────────▼────────────┐
                     │         voice-agent               │
                     │  arch -arm64 python3 -m app.agent │
                     │                                   │
                     │  VAD (Silero, in-process)         │
                     │         │                         │
                     │         ▼                         │
                     │  Groq Whisper STT ───────────────►│── GROQ_API_KEY
                     │         │                         │
                     │         ▼                         │
                     │  MemoryContextProcessor ─────────►│── MEMORY_ENGINE_URL
                     │    POST /memory/query             │     (memory-engine :8000)
                     │    POST /memory/temporal          │
                     │         │                         │
                     │         ▼                         │
                     │  TrueFoundry LLM ────────────────►│── TRUEFOUNDRY_*
                     │  (semantic path only)             │
                     │         │                         │
                     │         ▼                         │
                     │  MiniMax TTS ────────────────────►│── MINIMAX_API_KEY
                     │  POST api.minimax.io/v1/t2a_v2    │
                     │         │                         │
                     └──────────────────────────────────-┘
                                │
                        PCM audio out → LiveKit
```

```
                     ┌─────────────────────────────────┐
                     │      memory-engine :8000         │
                     │   uvicorn app.main:app           │
                     │                                  │
                     │  Supabase ──────────────────────►│── SUPABASE_URL
                     │  (persons, med_logs, events…)    │   SUPABASE_SERVICE_KEY
                     │                                  │
                     │  Moss SessionIndex (in-process)──►│── MOSS_API_KEY
                     │  (stories, captured_facts)       │   MOSS_INDEX
                     │                                  │
                     │  Groq (router LLM fallback) ────►│── GROQ_API_KEY
                     └─────────────────────────────────┘
```

```
                     ┌─────────────────────────────────┐
                     │     vision-server :8765          │
                     │  conda python3 -m app.vision_server│
                     │                                  │
                     │  face_recognition (dlib, x86_64) │
                     │  references/*.jpg  ──────────────── local files
                     │         │                        │
                     │         ▼                        │
                     │  POST /memory/query ────────────►│── MEMORY_ENGINE_URL
                     │         │                        │
                     │         ▼                        │
                     │  TrueFoundry LLM ───────────────►│── TRUEFOUNDRY_*
                     │         │                        │
                     │         ▼                        │
                     │  MiniMax TTS ───────────────────►│── MINIMAX_API_KEY
                     └─────────────────────────────────┘
                               ▲
                     Chrome browser (getUserMedia)
                     http://localhost:8765
```

---

## Services at a glance

| Service | Role | Where it runs | Env vars needed |
|---------|------|--------------|-----------------|
| **LiveKit** | Real-time audio transport — carries mic audio in and TTS audio out | LiveKit Cloud (already provisioned) | `LIVEKIT_URL` `LIVEKIT_API_KEY` `LIVEKIT_API_SECRET` |
| **Groq** | STT (Whisper) + router LLM fallback | Groq Cloud | `GROQ_API_KEY` |
| **TrueFoundry** | LLM gateway (gpt-4o-mini) — semantic compose + Hindi translation | TrueFoundry Cloud | `TRUEFOUNDRY_BASE_URL` `TRUEFOUNDRY_API_KEY` `TRUEFOUNDRY_MODEL` |
| **MiniMax** | TTS — English_Graceful_Lady + Wise_Woman (Hindi) | `api.minimax.io` | `MINIMAX_API_KEY` |
| **memory-engine** | Archetype-routed memory: Supabase + Moss | local :8000 (or deployed) | see below |
| **Supabase** | Persistent store for all 11 entity types | Supabase Cloud | `SUPABASE_URL` `SUPABASE_SERVICE_KEY` |
| **Moss** | In-process episodic vector index (stories + captured facts) | inside memory-engine process | `MOSS_API_KEY` `MOSS_INDEX` |
| **vision-server** | Browser camera → face match → grounded greeting → TTS | local :8765 | same as above |

---

## LiveKit — what it does and how it connects

LiveKit is the real-time audio transport. It is **not** a processing service — it moves raw audio between the room and the agent.

**Connection flow:**
1. `transports.py` calls `AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)` and mints a JWT for the identity `yaad-agent` with `room_join=True` for room `yaad-demo`.
2. `LiveKitTransport` connects to `LIVEKIT_URL` (WebSocket) using that token.
3. The room receives audio from whichever participant joins (phone app, browser, another agent).
4. `transport.input()` emits `InputAudioRawFrame` chunks at 16 kHz into the Pipecat pipeline.
5. `transport.output()` plays back `OutputAudioRawFrame` PCM (32 kHz, mono, int16) into the room.

**What LiveKit does NOT do:** transcription, LLM, TTS, memory — it is pure audio plumbing.

**Current room:** `yaad-demo` on `wss://keepsake-y39026vu.livekit.cloud`

**Confirmed working:** LiveKit connected, audio input started, room `yaad-demo` verified (STATUS.md A2).

**To join as a listener / test participant:** use the LiveKit Agents Playground or any LiveKit-compatible client pointed at the same URL + room. The agent joins automatically when it starts.

---

## Environment variables — full list for voice + vision

All of these live in `packages/voice-agent/.env` (and `packages/memory-engine/.env` for the memory engine side — or a shared root `.env` symlinked).

```bash
# ── LiveKit (audio transport) ──────────────────────────────────────────────
LIVEKIT_URL=wss://keepsake-y39026vu.livekit.cloud
LIVEKIT_API_KEY=<your key>
LIVEKIT_API_SECRET=<your secret>
LIVEKIT_ROOM=yaad-demo

# ── Groq (STT + router LLM fallback) ──────────────────────────────────────
GROQ_API_KEY=<your key>
# Model used for STT: whisper-large-v3-turbo (hardcoded in stt_groq.py)
# Model used for router LLM fallback: llama-3.1-8b-instant (hardcoded in router.py)

# ── TrueFoundry (LLM gateway → gpt-4o-mini) ───────────────────────────────
TRUEFOUNDRY_BASE_URL=https://gateway.truefoundry.ai
TRUEFOUNDRY_API_KEY=<your key>
TRUEFOUNDRY_MODEL=openai/gpt-4o-mini

# ── MiniMax (TTS) ──────────────────────────────────────────────────────────
MINIMAX_API_KEY=<your key>
MINIMAX_VOICE_EN=English_Graceful_Lady   # optional — this is the default
MINIMAX_MODEL=speech-02-hd               # optional — this is the default
# Endpoint hardcoded: https://api.minimax.io/v1/t2a_v2  (NO GroupId)
# Hindi voice: Wise_Woman (triggered by Devanagari detection)

# ── Memory engine ──────────────────────────────────────────────────────────
MEMORY_ENGINE_URL=http://localhost:8000  # change to deployed URL if remote

# ── Supabase (used by memory-engine) ──────────────────────────────────────
SUPABASE_URL=<your project url>
SUPABASE_SERVICE_KEY=<your service key>

# ── Moss (used by memory-engine, in-process) ───────────────────────────────
MOSS_API_KEY=<your key>
MOSS_INDEX=yaad_amma

# ── Optional / demo-only ────────────────────────────────────────────────────
YAAD_DEMO_MODE=1           # set to return fixture responses instead of HTTP 500
YAAD_SKIP_RESEED=1         # set to skip Moss startup reseed (useful in tests)
EMAIL_FROM=<gmail address>  # for wander SMS alerts via Gmail SMTP
EMAIL_APP_PASSWORD=<app password>
YAAD_DEMO_RECIPIENT_EMAIL= # routes all wander alerts to one address during demo
```

---

## What must be running for voice to work

### Minimum (LiveKit mode)

All three of these must be up before `app.agent` starts:

```
1. memory-engine at :8000        (uvicorn)
2. Supabase                      (cloud — always up)
3. LiveKit room yaad-demo        (cloud — always up)
```

The following are called at request time (no pre-start needed, just keys in .env):

```
4. Groq Cloud                    (STT on every utterance)
5. TrueFoundry / gpt-4o-mini     (LLM on semantic queries)
6. MiniMax api.minimax.io        (TTS on every response)
```

### Start order

```bash
# 1. memory-engine first — voice agent hits it immediately on first utterance
cd packages/memory-engine
source .venv/bin/activate
uvicorn app.main:app --port 8000
# Wait for: "[startup] Moss session reseeded" before starting voice agent

# 2. voice agent
cd packages/voice-agent
arch -arm64 python3 -m app.agent
# Connects to LiveKit room yaad-demo
# Press 'h' to toggle Hindi mode

# Local mode (no LiveKit — mic + speakers directly)
arch -arm64 python3 -m app.agent --local
```

### If memory-engine is unreachable

The voice agent has a 3-second timeout on every memory call. On timeout, `fallback.py` pattern-matches the query and returns a pre-written fixture response. The demo never hard-fails — audio still plays, the answer is just from fixtures.

---

## What must be running for vision (face match + greeting) to work

### Additional requirements on top of voice

```
1. vision-server at :8765        (Flask, conda Python)
2. Chrome browser                (terminal can't get macOS camera permission)
3. references/*.jpg              (at least one reference photo)
```

The vision server calls the same memory-engine and TrueFoundry/MiniMax endpoints as the voice agent — no additional keys needed.

```bash
# 3. vision-server (conda Python — do NOT use arch -arm64 python3)
cd packages/voice-agent
~/anaconda3/bin/python3 -m app.vision_server

# Open in Chrome (not Safari — needs getUserMedia)
open http://localhost:8765
```

### Reference photo requirements

- File: `packages/voice-agent/references/<name>.jpg` (or .png/.jpeg)
- Filename stem = the label the agent speaks ("leo.jpg" → "Leo")
- One clear frontal face per file
- Multiple reference files = multiple people it can recognise
- Current: `references/leo.jpg` only

### Vision call chain (every Capture click)

```
Browser Capture click
  → POST /match  {image: dataURL}       ← face_recognition, no network call
  → if name != "unknown":
      POST /greet  {name}
        → POST http://localhost:8000/memory/query  {text:"who is Leo?", lang:"en"}
        → POST https://gateway.truefoundry.ai/v1/chat/completions
        → POST https://api.minimax.io/v1/t2a_v2
      ← JSON {name, text, audio_base64}
  → HTML5 Audio.play()  (or ▶ Play button if autoplay blocked)
```

---

## Full-stack startup checklist

Run through this in order before a demo:

```
□ root .env populated with all keys above
□ packages/memory-engine/.env or symlink present
□ packages/voice-agent/.env or symlink present
□ packages/caregiver-web/.env.local → symlink to root .env

□ memory-engine started (uvicorn :8000)
□ curl http://localhost:8000/health  →  moss_ok:true, db_ok:true

□ vision-server started (conda :8765) — if using face match
□ Chrome open at http://localhost:8765  →  camera preview visible
□ references/leo.jpg present

□ caregiver-web started (npm run dev :3000) — if using add-fact-live demo
□ http://localhost:3000  →  dashboard loads, no JS errors

□ voice agent started (arch -arm64 python3 -m app.agent)
□ LiveKit connected — look for:
    "LiveKit transport connected"
    "Audio input started"
□ Speak "who is Leo?" — confirm grounded answer plays back
□ Speak in Hindi — confirm Devanagari TTS voice switches
```

---

## Fixture fallback — what survives if a service dies

| Service goes down | What happens |
|------------------|-------------|
| memory-engine | 3s timeout → `fallback.py` fixture (Leo, Sarah, pills, Hindi) — voice continues |
| Groq STT | No transcript → no response (pipeline stalls — cannot fallback STT) |
| TrueFoundry LLM | `answer_draft` path still works (temporal queries unaffected); semantic queries error → "I'm having trouble thinking right now." |
| MiniMax TTS | No audio out — pipeline stalls |
| memory-engine + all | All 5 fixture beats still answer; wifi-off beat requires this |
| vision-server | Browser shows error; voice agent unaffected (separate process) |

**Fixtures pre-loaded in `fallback.py`:** Leo (English + Hindi), Sarah, pills, default refusal.

**Not yet pre-cached:** TTS audio for the wifi-off beat (`fixtures/tts/*.mp3` not generated — roadmap item A4). Currently the fixture text is returned but no audio plays when MiniMax is unreachable.

---

## Python runtime split — why two different Pythons

| Process | Runtime | Why |
|---------|---------|-----|
| `voice-agent` (`app.agent`) | `arch -arm64 python3` | Pipecat's audio stack (Silero VAD, sounddevice local transport) requires a native arm64 binary on Apple Silicon. Running under Rosetta breaks frame timing. |
| `vision-server` (`app.vision_server`) | `~/anaconda3/bin/python3` (x86_64, Rosetta) | `face_recognition` / dlib built for x86_64. `arch -arm64` cannot run an x86_64 binary. The conda install on this machine is x86_64. |
| `memory-engine` | Any Python 3.11+ | No platform restriction — uvicorn is platform-agnostic. |

The two agent processes never talk to each other directly. Both call the memory engine at `:8000`. The vision server returns audio to the browser; the voice agent returns audio to the LiveKit room. They are parallel, independent pipelines.

---

## Deploying memory-engine to a remote host

If you move memory-engine off localhost, change `MEMORY_ENGINE_URL` in both `.env` files:

```bash
# voice-agent .env
MEMORY_ENGINE_URL=https://your-deployed-engine.example.com

# vision-server reads the same env var at startup
```

The memory engine requires outbound access to:
- Supabase (HTTPS)
- Moss API (HTTPS)
- Groq API (HTTPS, for router LLM fallback)
- OpenAI / Groq (HTTPS, for document normalization)
- Gmail SMTP (for wander SMS alerts)

The voice agent requires outbound access to:
- LiveKit WebSocket (`wss://`)
- Groq API (STT)
- TrueFoundry HTTPS (LLM)
- MiniMax HTTPS (TTS)
- memory-engine (HTTP or HTTPS)

The vision server requires outbound access to:
- memory-engine (HTTP or HTTPS)
- TrueFoundry HTTPS (LLM compose)
- MiniMax HTTPS (TTS)
- No camera access needed server-side (browser handles it)
