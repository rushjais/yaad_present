"""Standalone test: Groq Whisper STT + MiniMax TTS.

No Pipecat, no LiveKit, no LLM, no memory — just validates the two audio services.

Usage:
  # Record 5s from mic:
  python -m app.test_stt_tts

  # Use a WAV file instead:
  python -m app.test_stt_tts path/to/audio.wav

Run once speaking English, once speaking Hindi to confirm both languages work.
Transcript and MiniMax voice selection are printed so you can verify.

Requirements beyond requirements.txt:
  pip install sounddevice numpy   (for mic recording)
  brew install ffmpeg             (for pydub MP3 decode)

[CONFIRM] MiniMax audio response field if you get "No audio in response" error.
"""

import asyncio
import base64
import io
import os
import sys
import wave

from dotenv import load_dotenv

load_dotenv()

import httpx
from groq import AsyncGroq

try:
    import sounddevice as sd
    import numpy as np
    HAS_SOUNDDEVICE = True
except ImportError:
    HAS_SOUNDDEVICE = False

# ---------------------------------------------------------------------------
# Config — pulled from .env
# ---------------------------------------------------------------------------

GROQ_API_KEY = os.environ["GROQ_API_KEY"].strip()
GROQ_MODEL = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo")

MINIMAX_API_KEY = os.environ["MINIMAX_API_KEY"].strip()
MINIMAX_GROUP_ID = os.environ["MINIMAX_GROUP_ID"].strip()
MINIMAX_VOICE_EN = os.environ.get("MINIMAX_VOICE_EN", "male-qn-jingying").strip()
MINIMAX_VOICE_HI = os.environ.get("MINIMAX_VOICE_HI", "female-shaonv").strip()
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "speech-01-hd").strip()
MINIMAX_URL = "https://api.minimax.chat/v1/t2a_v2"  # [CONFIRM]

RECORD_SECS = 5
SAMPLE_RATE = 16000


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def pcm_to_wav(pcm: bytes, sample_rate: int = SAMPLE_RATE) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def record_mic(duration: int = RECORD_SECS) -> bytes:
    if not HAS_SOUNDDEVICE:
        raise RuntimeError("sounddevice not installed. Run: pip install sounddevice numpy")
    print(f"\nRecording {duration}s from mic... speak now")
    audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype="int16")
    sd.wait()
    print("Done recording.")
    return pcm_to_wav(audio.tobytes())


def load_wav(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def mp3_to_pcm(mp3_bytes: bytes, sample_rate: int = 24000) -> bytes:
    from pydub import AudioSegment
    audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
    audio = audio.set_frame_rate(sample_rate).set_channels(1).set_sample_width(2)
    return audio.raw_data


def play_audio(pcm: bytes, sample_rate: int = 24000) -> None:
    if not HAS_SOUNDDEVICE:
        out_path = "/tmp/yaad_tts_output.mp3"
        print(f"sounddevice not available — audio not played. (PCM bytes: {len(pcm)})")
        return
    audio = np.frombuffer(pcm, dtype=np.int16)
    print("Playing...")
    sd.play(audio, samplerate=sample_rate)
    sd.wait()


# ---------------------------------------------------------------------------
# Groq STT
# ---------------------------------------------------------------------------

async def transcribe(wav_bytes: bytes) -> tuple[str, str]:
    """Return (transcript_text, detected_language_code)."""
    client = AsyncGroq(api_key=GROQ_API_KEY)
    result = await client.audio.transcriptions.create(
        file=("audio.wav", wav_bytes, "audio/wav"),
        model=GROQ_MODEL,
        response_format="verbose_json",
    )
    text = (result.text or "").strip()
    lang = (getattr(result, "language", None) or "en").strip()
    return text, lang


# ---------------------------------------------------------------------------
# MiniMax TTS
# ---------------------------------------------------------------------------

def _contains_hindi(text: str) -> bool:
    return any(0x0900 <= ord(c) <= 0x097F for c in text)


async def synthesize(text: str) -> bytes:
    """Return MP3 bytes from MiniMax TTS.

    Confirmed response shape (probed 2026-06-06):
      data["data"]["audio"] — hex-encoded MP3 (NOT base64).
    Needs a valid TTS key — current key returns status_code=2049.
    """
    print(f"  MiniMax voice: {MINIMAX_VOICE_EN!r}")
    payload = {
        "model": MINIMAX_MODEL,
        "text": text,
        "stream": False,
        "voice_setting": {"voice_id": MINIMAX_VOICE_EN, "speed": 1, "vol": 1, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.post(
            f"{MINIMAX_URL}?GroupId={MINIMAX_GROUP_ID}",
            headers={"Authorization": f"Bearer {MINIMAX_API_KEY}", "Content-Type": "application/json"},
            json=payload,
        )
        r.raise_for_status()
        data = r.json()

    base = data.get("base_resp", {})
    if base.get("status_code") != 0:
        raise ValueError(
            f"MiniMax error {base.get('status_code')}: {base.get('status_msg')}\n"
            f"Response keys: {list(data.keys())}"
        )
    audio_hex = (data.get("data") or {}).get("audio", "")
    if not audio_hex:
        raise ValueError(f"No audio field. Response keys: {list(data.keys())}")
    return bytes.fromhex(audio_hex)


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------

async def run_test(wav_path: str | None = None) -> None:
    print("=== Yaad STT+TTS smoke test ===")
    print(f"Groq model : {GROQ_MODEL}")
    print(f"MiniMax model: {MINIMAX_MODEL}")

    # 1. Get audio
    if wav_path:
        print(f"\nLoading WAV: {wav_path}")
        wav_bytes = load_wav(wav_path)
    else:
        wav_bytes = record_mic()

    # 2. Transcribe
    print("\nSending to Groq Whisper...")
    text, lang = await transcribe(wav_bytes)
    print(f"  Transcript ({lang}): {text!r}")

    if not text:
        print("\nEmpty transcript — check your audio input.")
        print("Tips:")
        print("  - Speak clearly during the recording window.")
        print("  - Try passing a known-good WAV: python -m app.test_stt_tts path/to/file.wav")
        return

    # 3. Synthesize
    print("\nSending to MiniMax TTS...")
    mp3 = await synthesize(text)
    print(f"  Got {len(mp3):,} bytes of MP3 audio.")

    # 4. Play back
    pcm = mp3_to_pcm(mp3)
    play_audio(pcm)

    print("\n✓ Test complete.")
    print("  To test Hindi: speak Hindi in the recording window, or pass a Hindi WAV file.")


if __name__ == "__main__":
    wav = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(run_test(wav))
