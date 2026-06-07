"""Programmatic STT + TTS validation — no mic required.

Generates audio via macOS `say` (or optionally OpenAI TTS), sends to Groq Whisper,
then attempts MiniMax TTS and reports the actual response.

Usage:
    python -m app.validate_stt_tts

What it validates:
  1. Groq STT: macOS say → WAV → Groq Whisper → transcript + detected language
  2. MiniMax TTS: text → MiniMax API → report status (key validity, audio field)
  3. Round-trip: Groq STT(MiniMax output) if MiniMax key is valid

English and Hindi phrases both tested.
"""

import asyncio
import io
import os
import subprocess
import sys
import tempfile
import time
import wave

from dotenv import load_dotenv

load_dotenv()

import httpx
from groq import AsyncGroq

GROQ_API_KEY = os.environ["GROQ_API_KEY"].strip()
GROQ_MODEL = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo")

MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "").strip()
MINIMAX_GROUP_ID = os.environ.get("MINIMAX_GROUP_ID", "").strip()
MINIMAX_VOICE_EN = os.environ.get("MINIMAX_VOICE_EN", "Calm_Woman").strip()
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "speech-01-hd").strip()
MINIMAX_URL = "https://api.minimax.io/v1/t2a_v2"

SAMPLE_RATE = 16000


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def say_to_wav(text: str, voice: str = "Samantha") -> bytes:
    """Use macOS `say` to generate AIFF, convert to WAV via ffmpeg."""
    with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as f:
        aiff_path = f.name
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        wav_path = f.name
    try:
        subprocess.run(["say", "-v", voice, "-o", aiff_path, text], check=True, capture_output=True)
        subprocess.run(
            ["ffmpeg", "-y", "-i", aiff_path, "-ar", str(SAMPLE_RATE), "-ac", "1", wav_path],
            check=True, capture_output=True,
        )
        with open(wav_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(aiff_path)
        os.unlink(wav_path)


# ---------------------------------------------------------------------------
# Groq STT
# ---------------------------------------------------------------------------

async def transcribe_wav(wav_bytes: bytes) -> tuple[str, str]:
    client = AsyncGroq(api_key=GROQ_API_KEY)
    t0 = time.perf_counter()
    result = await client.audio.transcriptions.create(
        file=("audio.wav", wav_bytes, "audio/wav"),
        model=GROQ_MODEL,
        response_format="verbose_json",
    )
    elapsed = time.perf_counter() - t0
    text = (result.text or "").strip()
    lang = (getattr(result, "language", None) or "en").strip()
    return text, lang, elapsed


# ---------------------------------------------------------------------------
# MiniMax TTS probe
# ---------------------------------------------------------------------------

async def minimax_synthesize(text: str) -> tuple[bool, str, int, bytes]:
    """Returns (ok, status_msg, status_code, audio_bytes)."""
    payload = {
        "model": MINIMAX_MODEL,
        "text": text,
        "stream": False,
        "voice_setting": {"voice_id": MINIMAX_VOICE_EN, "speed": 1, "vol": 1, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
    }
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.post(
            f"{MINIMAX_URL}?GroupId={MINIMAX_GROUP_ID}",
            headers={"Authorization": f"Bearer {MINIMAX_API_KEY}", "Content-Type": "application/json"},
            json=payload,
        )
    data = r.json()
    base = data.get("base_resp", {})
    code = base.get("status_code", -1)
    msg = base.get("status_msg", "unknown")
    if code != 0:
        return False, msg, code, b""
    audio_hex = (data.get("data") or {}).get("audio", "")
    return bool(audio_hex), msg, code, bytes.fromhex(audio_hex) if audio_hex else b""


# ---------------------------------------------------------------------------
# Validation runs
# ---------------------------------------------------------------------------

async def validate_groq_stt(label: str, text: str, voice: str) -> None:
    print(f"\n── Groq STT: {label} ──")
    print(f"  Input text: {text!r}")
    print("  Generating audio via macOS say...", end=" ", flush=True)
    try:
        wav = say_to_wav(text, voice=voice)
        print(f"OK ({len(wav):,} bytes)")
    except Exception as e:
        print(f"FAIL: {e}")
        return

    print("  Sending to Groq Whisper...", end=" ", flush=True)
    try:
        transcript, lang, elapsed = await transcribe_wav(wav)
        print(f"OK ({elapsed:.2f}s)")
        print(f"  Transcript [{lang}]: {transcript!r}")
    except Exception as e:
        print(f"FAIL: {e}")


async def validate_minimax_tts(label: str, text: str) -> bytes:
    print(f"\n── MiniMax TTS: {label} ──")
    print(f"  Input text: {text!r}")
    print(f"  Voice: {MINIMAX_VOICE_EN!r} | Model: {MINIMAX_MODEL!r}")
    ok, msg, code, audio = await minimax_synthesize(text)
    if ok:
        print(f"  ✓ OK — {len(audio):,} bytes of MP3 audio")
        # Save for STT round-trip
        out = f"/tmp/yaad_minimax_{label.replace(' ','_')}.mp3"
        with open(out, "wb") as f:
            f.write(audio)
        print(f"  Saved: {out}")
    else:
        print(f"  ✗ FAIL — status_code={code} msg={msg!r}")
        if code == 2049:
            print("  → Invalid API key. Get a fresh MiniMax TTS key from portal.minimax.chat")
    return audio


async def main() -> None:
    print("=== Yaad STT + TTS validation (no mic) ===")
    print(f"Groq model:    {GROQ_MODEL}")
    print(f"MiniMax model: {MINIMAX_MODEL}")
    print(f"MiniMax key:   {'set' if MINIMAX_API_KEY else 'MISSING'}")

    # 1. Groq STT — English
    await validate_groq_stt("English", "Who is this person?", voice="Samantha")

    # 2. Groq STT — Hindi (macOS Lekha voice for Hindi)
    await validate_groq_stt("Hindi", "Leo kaun hai?", voice="Lekha")

    # 3. MiniMax TTS — English
    audio_en = await validate_minimax_tts("English", "Who is this person?")

    # 4. If MiniMax worked, run STT round-trip
    if audio_en:
        print("\n── Round-trip: MiniMax audio → Groq STT ──")
        try:
            from pydub import AudioSegment
            audio_seg = AudioSegment.from_mp3(io.BytesIO(audio_en))
            audio_seg = audio_seg.set_frame_rate(SAMPLE_RATE).set_channels(1).set_sample_width(2)
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(SAMPLE_RATE)
                wf.writeframes(audio_seg.raw_data)
            wav_bytes = buf.getvalue()
            transcript, lang, elapsed = await transcribe_wav(wav_bytes)
            print(f"  Transcript [{lang}] ({elapsed:.2f}s): {transcript!r}")
        except Exception as e:
            print(f"  Round-trip failed: {e}")

    print("\n=== Done ===")
    print("\nSummary:")
    print("  Groq STT:   run above — check transcript accuracy")
    print("  MiniMax TTS: see status above (needs valid key if 2049)")
    print("  ffmpeg:     confirmed installed" if subprocess.run(["which","ffmpeg"], capture_output=True).returncode == 0 else "  ffmpeg: NOT FOUND")


if __name__ == "__main__":
    import io, wave
    asyncio.run(main())
