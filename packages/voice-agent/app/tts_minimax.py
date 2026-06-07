"""MiniMax TTS service — English, international endpoint.

Spec: POST https://api.minimax.io/v1/t2a_v2   (NO GroupId — .io endpoint)
Headers: Authorization: Bearer {MINIMAX_API_KEY}
Body fields per official .io OpenAPI:
  model: "speech-02-hd"
  output_format: "hex"
  voice_setting.voice_id: "English_Graceful_Lady"
Response: data.audio = hex-encoded MP3; base_resp.status_code 0 = OK, 1004 = auth fail.

Key is read at __init__ time (not module level) so load_dotenv() in agent.py
has already run before MiniMaxTTSService is instantiated.
"""

import io
import logging
import os
import time

import httpx
from pydub import AudioSegment  # requires: brew install ffmpeg

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
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "speech-02-hd").strip()
MINIMAX_URL = "https://api.minimax.io/v1/t2a_v2"  # NO GroupId — .io international endpoint
OUTPUT_SAMPLE_RATE = 32000


def _mp3_to_pcm(mp3_bytes: bytes) -> bytes:
    audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
    audio = audio.set_frame_rate(OUTPUT_SAMPLE_RATE).set_channels(1).set_sample_width(2)
    return audio.raw_data


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
        payload = {
            "model": MINIMAX_MODEL,
            "text": text,
            "stream": False,
            "output_format": "hex",
            "voice_setting": {"voice_id": MINIMAX_VOICE_EN, "speed": 1, "vol": 1, "pitch": 0},
            "audio_setting": {
                "sample_rate": OUTPUT_SAMPLE_RATE,
                "bitrate": 128000,
                "format": "mp3",
                "channel": 1,
            },
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                MINIMAX_URL,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload,
            )
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
        return _mp3_to_pcm(bytes.fromhex(audio_hex))
