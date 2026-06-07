"""Groq Whisper STT — always-on, utterance-complete gating.

Buffers audio between VAD start/stop. Sends the full utterance to
Groq Whisper once silence exceeds stop_secs (set to 2s in transports.py).

Two filters before forwarding a TranscriptionFrame:
  1. no_speech filter  — drops segments where Whisper itself says it heard
                         nothing (no_speech_prob > 0.6 on every segment).
  2. completeness gate — drops utterances that are not a real query:
                         fewer than 3 words, OR a known Whisper hallucination.
                         Prevents coughs, background noise, and Whisper's
                         tendency to generate fluent filler ("Thank you.",
                         "Bye.") from near-silence.
"""

import asyncio
import io
import json
import logging
import os
import time
import wave
from typing import TYPE_CHECKING

from groq import AsyncGroq

from .lang_toggle import LanguageState

from pipecat.frames.frames import (  # type: ignore
    AudioRawFrame,
    Frame,
    OutputTransportMessageFrame,
    TextFrame,
    TranscriptionFrame,
    UserAudioRawFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # type: ignore

if TYPE_CHECKING:
    from .agent import LatencyTracker

logger = logging.getLogger(__name__)

GROQ_MODEL = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo")

_MIN_SPEECH_MS = 400          # drop utterances shorter than this
_NO_SPEECH_THRESHOLD = 0.6   # drop if every segment is flagged as silence
_MIN_WORDS = 3                # drop if fewer than this many words

# Whisper hallucinations on near-silence — exact lowercased matches.
_HALLUCINATIONS: frozenset[str] = frozenset({
    "thank you.", "thank you", "thank you very much.", "thank you very much",
    "thanks for watching.", "thanks for watching",
    "bye.", "bye", "bye bye.", "bye bye",
    "you.", "you",
    ".", "..", "...",
    "okay.", "okay", "ok.", "ok",
    "hmm.", "hmm", "hm.", "hm",
    "uh.", "uh", "um.", "um",
    "ah.", "ah",
    "so.", "so",
    "right.", "right",
    "yeah.", "yeah",
    "no.", "no",
    "yes.", "yes",
    "sure.", "sure",
    "good.", "good",
})


def _pcm_to_wav(pcm: bytes, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm)
    return buf.getvalue()


def _no_speech_only(result) -> bool:
    segments = getattr(result, "segments", None) or []
    if not segments:
        return False
    return all(
        getattr(seg, "no_speech_prob", 0.0) > _NO_SPEECH_THRESHOLD
        for seg in segments
    )


def _is_complete(text: str) -> bool:
    """Return True only if the transcription looks like a real utterance."""
    stripped = text.strip().lower().rstrip(" .,!?")
    if stripped in _HALLUCINATIONS or text.strip().lower() in _HALLUCINATIONS:
        return False
    words = text.split()
    if len(words) < _MIN_WORDS:
        return False
    return True


class GroqWhisperSTTService(FrameProcessor):
    def __init__(self, tracker=None, lang_state: LanguageState | None = None) -> None:
        super().__init__()
        self._client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"].strip())
        self._buffer: bytearray = bytearray()
        self._buffering: bool = False
        self._sample_rate: int = 16000
        self._task: asyncio.Task | None = None
        self._tracker = tracker
        self._lang_state = lang_state
        logger.info("STT ready — always-on, 2s silence gate, min %d words", _MIN_WORDS)

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, VADUserStartedSpeakingFrame):
            if self._task and not self._task.done():
                self._task.cancel()
            self._buffer = bytearray()
            self._buffering = True
            await self.push_frame(frame, direction)

        elif isinstance(frame, (AudioRawFrame, UserAudioRawFrame)) and self._buffering:
            self._buffer.extend(frame.audio)
            if hasattr(frame, "sample_rate") and frame.sample_rate:
                self._sample_rate = frame.sample_rate

        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            self._buffering = False
            min_bytes = int(self._sample_rate * 2 * _MIN_SPEECH_MS / 1000)
            if len(self._buffer) >= min_bytes:
                self._task = asyncio.create_task(self._transcribe(bytes(self._buffer)))
            else:
                logger.debug("Utterance too short (%d bytes) — dropped", len(self._buffer))
            await self.push_frame(frame, direction)

        else:
            await self.push_frame(frame, direction)

    async def _transcribe(self, pcm: bytes) -> None:
        wav = _pcm_to_wav(pcm, self._sample_rate)
        t0 = time.perf_counter()

        active_lang = self._lang_state.lang if self._lang_state else None
        kwargs: dict = {
            "file": ("audio.wav", wav, "audio/wav"),
            "model": GROQ_MODEL,
            "response_format": "verbose_json",
        }
        if active_lang == "hi":
            kwargs["language"] = "hi"

        try:
            result = await self._client.audio.transcriptions.create(**kwargs)
            if self._tracker:
                self._tracker.stt = time.perf_counter() - t0

            if _no_speech_only(result):
                logger.debug("STT: no_speech — dropped")
                return

            text = (result.text or "").strip()
            if not text:
                return

            lang = (getattr(result, "language", None) or "en").strip()
            logger.info("Groq [lang=%s]: %s", lang.upper(), text)

            if not _is_complete(text):
                logger.debug("STT: incomplete/hallucination — dropped: %r", text)
                return

            # Push live transcript to frontend via data channel
            try:
                msg = json.dumps({"type": "transcript", "text": text})
                await self.push_frame(OutputTransportMessageFrame(message=msg))
            except Exception as _e:
                logger.debug("Data frame push failed: %s", _e)

            try:
                frame = TranscriptionFrame(text, "", "0", language=lang)
            except TypeError:
                frame = TranscriptionFrame(text, "", "0")
            await self.push_frame(frame)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("Groq STT error: %s", e)


def create_stt(tracker=None, lang_state: LanguageState | None = None) -> "GroqWhisperSTTService":
    return GroqWhisperSTTService(tracker=tracker, lang_state=lang_state)
