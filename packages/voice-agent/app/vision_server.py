"""Browser-based face-match + greeting server.

The browser owns the camera (Chrome has macOS permission; the terminal doesn't).
GET  /       — live <video> preview + Capture button
POST /match  — {image: dataURL} → {name, distances}
POST /greet  — {name} → {name, text, audio_base64}  (memory → LLM → MiniMax TTS)

Run from packages/voice-agent/:
    ~/anaconda3/bin/python3 -m app.vision_server

Then open http://localhost:8765 in Chrome.

Dev helpers:
    ~/anaconda3/bin/python3 -m app.vision_server --test-memory Leo
    ~/anaconda3/bin/python3 -m app.vision_server --test-greet Leo
"""

import base64
import io
import json
import os
import sys
from pathlib import Path

import httpx
import numpy as np
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from PIL import Image

# Load keys from packages/voice-agent/.env (explicit path — works regardless of CWD)
load_dotenv(Path(__file__).parent.parent / ".env")

try:
    from app.vision_match import match_rgb  # python3 -m app.vision_server
except ImportError:
    from vision_match import match_rgb      # python3 app/vision_server.py

PORT = 8765
MINIMAX_URL   = "https://api.minimax.io/v1/t2a_v2"
MINIMAX_VOICE = os.environ.get("MINIMAX_VOICE_EN", "English_Graceful_Lady").strip()
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL",    "speech-02-hd").strip()

# Agent's grounding system prompt — kept verbatim from agent.py §6
_SYSTEM_PROMPT = (
    "You are Yaad, a warm companion for someone with memory loss. "
    "The person you are SPEAKING TO is the one named Amma in the memory context. "
    "Always address her as 'you' / 'your' — never say 'Amma' as if she is not there. "
    "State ONLY facts in the provided MEMORY context. "
    "If the context is empty or confidence is low, say you're not sure and offer to check with the family. "
    "Never invent people, events, or dates. "
    "Short, calm, warm."
)

# Vision-specific suffix: turns facts into a greeting sentence
_COMPOSE_SUFFIX = (
    " Rephrase the facts below into ONE warm, natural spoken sentence telling Amma who just walked in. "
    "Use ONLY the facts given — add nothing, invent nothing, no embellishment. "
    "Address Amma in second person ('you', 'your'); refer to the visitor in third person. "
    "Output the sentence only — no quotes, no preamble."
)

app = Flask(__name__)


# ── Step 1: memory query ──────────────────────────────────────────────────────

def query_memory_for_name(name: str) -> dict:
    """POST /memory/query — exact same request/response shape as memory_client.py."""
    url = os.environ.get("MEMORY_ENGINE_URL", "http://localhost:8000").strip()
    r = httpx.post(
        f"{url}/memory/query",
        json={"text": f"who is {name}?", "lang": "en"},
        timeout=10.0,
    )
    r.raise_for_status()
    return r.json()


# ── Step 2: compose ───────────────────────────────────────────────────────────

def compose_greeting(name: str, answer_draft: str | None, grounded: bool) -> str:
    """One warm sentence about the visitor, grounded-only.

    Falls back to a safe neutral line if not grounded or facts are absent.
    Falls back to a template if TrueFoundry keys are missing.
    """
    if not grounded or not answer_draft:
        return "I'm not sure who that is, Amma — let me check with the family."

    base_url = os.environ.get("TRUEFOUNDRY_BASE_URL", "").strip().rstrip("/")
    model    = os.environ.get("TRUEFOUNDRY_MODEL",    "openai/gpt-4o-mini").strip()
    api_key  = os.environ.get("TRUEFOUNDRY_API_KEY",  "").strip()
    if not (base_url and api_key):
        return f"Amma, {name} is here to see you."

    r = httpx.post(
        f"{base_url}/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT + _COMPOSE_SUFFIX},
                {"role": "user",   "content": answer_draft},
            ],
            "max_tokens": 80,
            "temperature": 0.4,
        },
        timeout=15.0,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


# ── Step 3: TTS ───────────────────────────────────────────────────────────────

def synthesize_tts(text: str) -> bytes:
    """MiniMax TTS via raw HTTP — same params as tts_minimax.py. Returns MP3 bytes."""
    api_key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("MINIMAX_API_KEY not set")

    r = httpx.post(
        MINIMAX_URL,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model":         MINIMAX_MODEL,
            "text":          text,
            "stream":        False,
            "output_format": "hex",
            "voice_setting": {"voice_id": MINIMAX_VOICE, "speed": 1, "vol": 1, "pitch": 0},
            "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
        },
        timeout=20.0,
    )
    r.raise_for_status()
    data = r.json()

    status = data.get("base_resp", {})
    if status.get("status_code") != 0:
        raise RuntimeError(f"MiniMax error {status.get('status_code')}: {status.get('status_msg')}")

    audio_hex = (data.get("data") or {}).get("audio", "")
    if not audio_hex:
        raise RuntimeError(f"No audio in MiniMax response; keys={list(data.keys())}")
    return bytes.fromhex(audio_hex)  # MP3 bytes


# ── HTML page (Step 4: auto-greet after face match) ───────────────────────────

_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Yaad — Face Match</title>
  <style>
    body    { font-family: sans-serif; padding: 24px; background: #fafafa; }
    h2      { margin-bottom: 16px; }
    video   { border: 1px solid #ccc; border-radius: 4px; display: block; margin-bottom: 12px; }
    button  { padding: 10px 24px; font-size: 15px; cursor: pointer; border-radius: 4px;
              background: #1a73e8; color: #fff; border: none; }
    button:hover { background: #1558b0; }
    #play-btn    { background: #2e7d32; margin-top: 12px; display: block; }
    #play-btn:hover { background: #1b5e20; }
    pre     { margin-top: 18px; font-size: 15px; background: #f0f0f0; padding: 14px;
              border-radius: 6px; min-height: 48px; white-space: pre-wrap; }
  </style>
</head>
<body>
  <h2>Yaad — Face Match</h2>
  <video id="video" autoplay playsinline width="480"></video>
  <button id="capture">Capture</button>
  <canvas id="canvas" style="display:none"></canvas>
  <pre id="result">Press Capture to identify.</pre>

  <script>
    navigator.mediaDevices.getUserMedia({video: true})
      .then(s => { document.getElementById('video').srcObject = s; })
      .catch(e => { document.getElementById('result').textContent = 'Camera error: ' + e.message; });

    document.getElementById('capture').onclick = async () => {
      const video  = document.getElementById('video');
      const canvas = document.getElementById('canvas');
      const result = document.getElementById('result');

      // Remove any leftover play button from a previous capture
      const old = document.getElementById('play-btn');
      if (old) old.remove();

      canvas.width  = video.videoWidth;
      canvas.height = video.videoHeight;
      canvas.getContext('2d').drawImage(video, 0, 0);
      const dataURL = canvas.toDataURL('image/jpeg', 0.9);

      result.textContent = 'Matching…';
      try {
        // Step 1: face match (unchanged)
        const mResp = await fetch('/match', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({image: dataURL})
        });
        const mData = await mResp.json();
        const dist  = Object.entries(mData.distances || {})
                        .map(([k, v]) => k + '=' + v.toFixed(4)).join('  ');

        result.textContent = 'Name:      ' + mData.name + '\\n' +
                             'Distances: ' + (dist || '(none)');

        const known = mData.name && mData.name !== 'no face detected' && mData.name !== 'unknown';
        if (!known) return;

        // Step 2-3: fetch grounded greeting + audio
        result.textContent += '\\n\\nFetching greeting…';
        const gResp = await fetch('/greet', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({name: mData.name})
        });
        const gData = await gResp.json();

        result.textContent = 'Name:      ' + mData.name + '\\n' +
                             'Distances: ' + (dist || '(none)') + '\\n\\n' +
                             '💬 ' + gData.text;

        if (!gData.audio_base64) return;

        // Step 4: autoplay; fall back to a button if browser blocks it
        const audio = new Audio('data:audio/mp3;base64,' + gData.audio_base64);
        audio.play().catch(() => {
          const btn = document.createElement('button');
          btn.id          = 'play-btn';
          btn.textContent = '▶ Play greeting';
          btn.onclick     = () => { audio.play(); btn.remove(); };
          document.body.appendChild(btn);
        });

      } catch (e) {
        result.textContent = 'Error: ' + e.message;
      }
    };
  </script>
</body>
</html>"""


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return _HTML, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.post("/match")
def match_endpoint():
    """Unchanged: face recognition only, no LLM, no TTS."""
    body = request.get_json(force=True)
    dataurl = body.get("image", "")
    if "," not in dataurl:
        return jsonify({"error": "invalid image payload"}), 400

    _, b64 = dataurl.split(",", 1)
    rgb = np.array(Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB"))

    name, distances = match_rgb(rgb)
    if name is None:
        return jsonify({"name": "no face detected", "distances": {}})
    return jsonify({"name": name, "distances": distances})


@app.post("/greet")
def greet_endpoint():
    """Memory → LLM compose → MiniMax TTS. Returns {name, text, audio_base64}."""
    body = request.get_json(force=True)
    name = (body.get("name") or "").strip()

    if not name or name in ("unknown", "no face detected"):
        return jsonify({"name": name, "text": "I'm not sure who that is, Amma.", "audio_base64": ""})

    mem     = query_memory_for_name(name)
    text    = compose_greeting(name, mem.get("answer_draft"), mem.get("grounded", False))
    mp3     = synthesize_tts(text)
    audio64 = base64.b64encode(mp3).decode()
    return jsonify({"name": name, "text": text, "audio_base64": audio64})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--test-memory":
        name = sys.argv[2]
        print(f"Querying memory engine for: {name!r}")
        print(f"URL: {os.environ.get('MEMORY_ENGINE_URL', 'http://localhost:8000')}")
        print()
        resp = query_memory_for_name(name)
        print(f"grounded  : {resp.get('grounded')}")
        print(f"confidence: {resp.get('confidence')}")
        print(f"items     : {len(resp.get('items', []))}")
        if resp.get("answer_draft"):
            print(f"draft     : {resp['answer_draft']!r}")
        print()
        print(json.dumps(resp, indent=2))
        sys.exit(0)

    if len(sys.argv) == 3 and sys.argv[1] == "--test-greet":
        name = sys.argv[2]
        print(f"Testing full greet flow for: {name!r}")
        print()
        mem = query_memory_for_name(name)
        print(f"grounded  : {mem.get('grounded')}")
        print(f"draft     : {mem.get('answer_draft')!r}")
        print()
        sentence = compose_greeting(name, mem.get("answer_draft"), mem.get("grounded", False))
        print(f"composed  : {sentence!r}")
        sys.exit(0)

    print(f"Open http://localhost:{PORT} in Chrome")
    app.run(host="0.0.0.0", port=PORT, debug=False)
