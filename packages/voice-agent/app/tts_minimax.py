"""MiniMax TTS service — English + Hindi, international endpoint.

Spec: POST https://api.minimax.io/v1/t2a_v2   (NO GroupId — .io endpoint)
Language detection: checks for Devanagari characters in the response text.
  Devanagari → Hindi voice (MINIMAX_VOICE_HI) + language_boost:"Hindi"
  Otherwise  → English voice (MINIMAX_VOICE_EN)

[CONFIRM] MINIMAX_VOICE_HI: "Wise_Woman" is multilingual and confirmed on
  the China platform; verify it works on api.minimax.io for Hindi.
  If it returns 1004/wrong voice, override MINIMAX_VOICE_HI in .env.
"""

import logging
import os
import time

import httpx

from pipecat.frames.frames import (  # type: ignore
    Frame,
    TextFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # type: ignore

logger = logging.getLogger(__name__)

# Non-secret config — safe to read at module level
MINIMAX_VOICE_EN = os.environ.get("MINIMAX_VOICE_EN", "English_Graceful_Lady").strip()
MINIMAX_VOICE_HI = os.environ.get("MINIMAX_VOICE_HI", "Wise_Woman").strip()  # [CONFIRM] on .io
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "speech-02-hd").strip()
MINIMAX_URL = "https://api.minimax.io/v1/t2a_v2"  # NO GroupId — .io international endpoint
OUTPUT_SAMPLE_RATE = 24000  # MiniMax native PCM rate; no ffmpeg needed


def _contains_devanagari(text: str) -> bool:
    return any(0x0900 <= ord(c) <= 0x097F for c in text)


class MiniMaxTTSService(FrameProcessor):
    def __init__(self, tracker=None) -> None:
        super().__init__()
        self._tracker = tracker
        # Read key at __init__ time (after load_dotenv() has run in agent.py)
        self._api_key = os.environ.get("MINIMAX_API_KEY", "").strip()

        # Startup diagnostics — always log key length so missing keys surface immediately
        key_len = len(self._api_key)
        if self._api_key:
            logger.info("MiniMax key loaded: %d chars", key_len)
        else:
            raise RuntimeError(
                "MINIMAX_API_KEY is empty — set it in packages/voice-agent/.env. "
                "Agent cannot start without a TTS key."
            )

        # Persistent HTTP client: reuses the TCP+TLS connection to api.minimax.io
        # instead of opening a new one per request. Saves ~150-300ms per TTS call.
        self._http = httpx.AsyncClient(
            timeout=15.0,
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
        )

    async def cleanup(self) -> None:
        await self._http.aclose()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if not isinstance(frame, TextFrame) or not frame.text.strip():
            await self.push_frame(frame, direction)
            return

        await self.push_frame(TTSStartedFrame())
        t0 = time.perf_counter()
        try:
            pcm = await self._synthesize(frame.text)
            if self._tracker:
                self._tracker.tts = time.perf_counter() - t0
                self._tracker.log()
            await self.push_frame(TTSAudioRawFrame(audio=pcm, sample_rate=OUTPUT_SAMPLE_RATE, num_channels=1))
        except Exception as e:
            logger.error("MiniMax TTS error: %s", e)
        finally:
            await self.push_frame(TTSStoppedFrame())

    async def _synthesize(self, text: str) -> bytes:
        is_hindi = _contains_devanagari(text)
        voice_id = MINIMAX_VOICE_HI if is_hindi else MINIMAX_VOICE_EN
        if is_hindi:
            logger.debug("Hindi detected — voice=%s language_boost=Hindi", voice_id)
        payload = {
            "model": MINIMAX_MODEL,
            "text": text,
            "stream": False,
            "output_format": "hex",
            **({"language_boost": "Hindi"} if is_hindi else {}),
            "voice_setting": {"voice_id": voice_id, "speed": 1, "vol": 1, "pitch": 0},
            "audio_setting": {
                "sample_rate": OUTPUT_SAMPLE_RATE,
                "format": "pcm",   # raw 16-bit signed PCM — no ffmpeg needed
                "channel": 1,
            },
        }
        r = await self._http.post(MINIMAX_URL, json=payload)
        r.raise_for_status()
        data = r.json()

        base = data.get("base_resp", {})
        if base.get("status_code") != 0:
            raise ValueError(
                f"MiniMax error {base.get('status_code')}: {base.get('status_msg')} | "
                f"URL={MINIMAX_URL} | full_keys={list(data.keys())}"
            )

        audio_hex = (data.get("data") or {}).get("audio", "")
        if not audio_hex:
            raise ValueError(f"No audio in MiniMax response. Keys: {list(data.keys())}")
        return bytes.fromhex(audio_hex)  # raw 16-bit signed PCM at OUTPUT_SAMPLE_RATE
