"""MiniMax TTS service — bilingual Hindi/English.

[CONFIRM] at sponsor table:
- Exact endpoint URL (currently: https://api.minimax.chat/v1/t2a_v2)
- Hindi voice_id (e.g. 'female-shaonv' or locale-specific id)
- English voice_id (e.g. 'male-qn-jingying' or locale-specific id)
- Response field name for audio ('audio_file' vs 'data.audio')
- Whether streaming endpoint exists (would reduce latency further)
- Model name ('speech-01-hd' vs 'speech-01-turbo')
"""

import asyncio
import base64
import io
import logging
import os
from typing import AsyncGenerator

import httpx
from pydub import AudioSegment  # requires ffmpeg installed

# [CONFIRM] pipecat import paths
from pipecat.frames.frames import (  # type: ignore
    AudioRawFrame,
    Frame,
    TextFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection  # type: ignore

logger = logging.getLogger(__name__)

# [CONFIRM] these env values at sponsor table
MINIMAX_API_KEY = os.environ.get("MINIMAX_API_KEY", "")
MINIMAX_GROUP_ID = os.environ.get("MINIMAX_GROUP_ID", "")
MINIMAX_VOICE_EN = os.environ.get("MINIMAX_VOICE_EN", "male-qn-jingying")   # [CONFIRM]
MINIMAX_VOICE_HI = os.environ.get("MINIMAX_VOICE_HI", "female-shaonv")      # [CONFIRM]
MINIMAX_MODEL = os.environ.get("MINIMAX_MODEL", "speech-01-hd")             # [CONFIRM]
MINIMAX_URL = "https://api.minimax.chat/v1/t2a_v2"                          # [CONFIRM]
OUTPUT_SAMPLE_RATE = 24000


def _contains_hindi(text: str) -> bool:
    return any(0x0900 <= ord(c) <= 0x097F for c in text)


def _mp3_to_pcm(mp3_bytes: bytes) -> bytes:
    audio = AudioSegment.from_mp3(io.BytesIO(mp3_bytes))
    audio = audio.set_frame_rate(OUTPUT_SAMPLE_RATE).set_channels(1).set_sample_width(2)
    return audio.raw_data


class MiniMaxTTSService(FrameProcessor):
    """Converts TextFrame → PCM AudioRawFrame via MiniMax TTS API.

    Sits after the LLM in the pipeline. Expects individual sentence-level
    TextFrames (use a SentenceAggregator upstream if needed).
    """

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if not isinstance(frame, TextFrame) or not frame.text.strip():
            await self.push_frame(frame, direction)
            return

        await self.push_frame(TTSStartedFrame())
        try:
            pcm = await self._synthesize(frame.text)
            await self.push_frame(AudioRawFrame(audio=pcm, sample_rate=OUTPUT_SAMPLE_RATE, num_channels=1))
        except Exception as e:
            logger.error("MiniMax TTS error: %s", e)
        finally:
            await self.push_frame(TTSStoppedFrame())

    async def _synthesize(self, text: str) -> bytes:
        voice_id = MINIMAX_VOICE_HI if _contains_hindi(text) else MINIMAX_VOICE_EN
        payload = {
            "model": MINIMAX_MODEL,
            "text": text,
            "voice_setting": {"voice_id": voice_id, "speed": 1.0, "vol": 1.0},
            "audio_setting": {"sample_rate": OUTPUT_SAMPLE_RATE, "format": "mp3"},  # [CONFIRM] format
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                f"{MINIMAX_URL}?GroupId={MINIMAX_GROUP_ID}",
                headers={"Authorization": f"Bearer {MINIMAX_API_KEY}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            data = r.json()

        # [CONFIRM] response field — may be 'audio_file', 'data', or nested
        mp3_b64 = data.get("audio_file") or data.get("data", {}).get("audio", "")
        if not mp3_b64:
            raise ValueError(f"No audio in MiniMax response: {list(data.keys())}")
        return _mp3_to_pcm(base64.b64decode(mp3_b64))
