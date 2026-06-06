"""Groq Whisper STT service for Pipecat.

Replaces DeepgramSTTService. Non-streaming pattern: buffers audio frames
during speech, sends the full utterance to Groq Whisper on UserStoppedSpeakingFrame.

Whisper auto-detects language — works for Hindi and English with no extra config.

[CONFIRM] at event:
- Frame names: UserStartedSpeakingFrame / UserStoppedSpeakingFrame may differ
  by pipecat version — check pipecat.frames.frames if import fails.
- TranscriptionFrame constructor signature (3 vs 4 positional args).
- GROQ_STT_MODEL: "whisper-large-v3-turbo" (fast, multilingual) or
  "whisper-large-v3" (slightly more accurate, same languages).
"""

import asyncio
import io
import logging
import os
import time
import wave
from typing import TYPE_CHECKING

from groq import AsyncGroq

# [CONFIRM] pipecat import paths
from pipecat.frames.frames import (  # type: ignore
    AudioRawFrame,
    Frame,
    TranscriptionFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # type: ignore

if TYPE_CHECKING:
    from .agent import LatencyTracker

logger = logging.getLogger(__name__)

GROQ_MODEL = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo")


def _pcm_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


class GroqWhisperSTTService(FrameProcessor):
    """Buffers raw audio between VAD start/stop events, then transcribes via Groq.

    Emits TranscriptionFrame with text + detected language (passed to
    MemoryContextProcessor for lang-aware memory queries).
    """

    def __init__(self, tracker=None) -> None:
        super().__init__()
        self._client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"].strip())
        self._buffer: bytearray = bytearray()
        self._buffering: bool = False
        self._sample_rate: int = 16000
        self._task: asyncio.Task | None = None
        self._tracker = tracker
        self._speech_start: float = 0.0

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, UserStartedSpeakingFrame):
            # Cancel any stale transcription from a previous utterance (barge-in).
            if self._task and not self._task.done():
                self._task.cancel()
            self._buffer = bytearray()
            self._buffering = True
            self._speech_start = time.perf_counter()
            await self.push_frame(frame, direction)

        elif isinstance(frame, AudioRawFrame) and self._buffering:
            self._buffer.extend(frame.audio)
            # Audio consumed here — not pushed downstream.

        elif isinstance(frame, UserStoppedSpeakingFrame):
            self._buffering = False
            if self._buffer:
                self._task = asyncio.create_task(self._transcribe(bytes(self._buffer)))
            await self.push_frame(frame, direction)

        else:
            await self.push_frame(frame, direction)

    async def _transcribe(self, pcm: bytes) -> None:
        wav = _pcm_to_wav(pcm, self._sample_rate)
        t0 = time.perf_counter()
        try:
            result = await self._client.audio.transcriptions.create(
                file=("audio.wav", wav, "audio/wav"),
                model=GROQ_MODEL,
                response_format="verbose_json",  # returns detected language
            )
            if self._tracker:
                self._tracker.stt = time.perf_counter() - t0

            text = (result.text or "").strip()
            if not text:
                return
            lang = (getattr(result, "language", None) or "en").strip()
            logger.info("Groq [%s]: %s", lang, text)

            # [CONFIRM] TranscriptionFrame signature varies by pipecat version.
            try:
                frame = TranscriptionFrame(text, "", "0", language=lang)
            except TypeError:
                frame = TranscriptionFrame(text, "", "0")
            await self.push_frame(frame)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Groq STT error: %s", e)


def create_stt(tracker=None) -> "GroqWhisperSTTService":
    return GroqWhisperSTTService(tracker=tracker)
