"""Track A — Yaad voice agent pipeline.

Pipeline:
  LiveKit audio in
  → Groq Whisper STT  (buffers utterance, auto-detects lang)
  → MemoryContextProcessor  (memory query + LLM call → TextFrame stream)
  → SentenceAggregator
  → MiniMax TTS
  → LiveKit audio out

Barge-in: SileroVAD in the transport emits StartInterruptionFrame on new speech,
which Pipecat propagates to cancel in-flight work downstream.

[CONFIRM] pipecat version-specific import paths throughout this file.
"""

import asyncio
import dataclasses
import logging
import os
import time

from dotenv import load_dotenv

# [CONFIRM] pipecat import paths — adjust for installed version
from pipecat.frames.frames import (  # type: ignore
    EndFrame,
    Frame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline  # type: ignore
from pipecat.pipeline.runner import PipelineRunner  # type: ignore
from pipecat.pipeline.task import PipelineParams, PipelineTask  # type: ignore
from pipecat.processors.audio.vad_processor import VADProcessor  # type: ignore
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # type: ignore

from .fallback import get_fixture
from .llm import create_llm
from .memory_client import MemoryClient
from .reminders_client import poll_reminders
from .stt_groq import create_stt
from .transports import create_transport, create_vad
from .tts_minimax import MiniMaxTTSService

load_dotenv()
logger = logging.getLogger(__name__)

# §6 grounding system prompt — English only (language scoped per CLAUDE.md)
SYSTEM_PROMPT = (
    "You are Yaad, a warm companion for someone with memory loss. "
    "State ONLY facts in the provided MEMORY context. "
    "If the context is empty or confidence is low, say you're not sure and offer to check with the family. "
    "Never invent people, events, or dates. "
    "Short, calm, warm. English only."
)

_TEMPORAL_KW = {
    "pill", "pills", "medicine", "medication", "tablet", "dose",
    "took", "taken", "today", "yesterday", "morning", "evening",
    "coming", "visit", "appointment",
}


def _is_temporal(text: str) -> bool:
    return any(kw in text.lower() for kw in _TEMPORAL_KW)


def _format_memory_context(resp: dict) -> str:
    if not resp.get("grounded") or not resp.get("items"):
        return ""
    return "\n".join(f"- {item['text']}" for item in resp["items"][:5])


def _build_messages(user_text: str, memory_resp: dict) -> list[dict]:
    ctx = _format_memory_context(memory_resp)
    if ctx:
        user_content = f"[MEMORY CONTEXT]\n{ctx}\n\n[USER SAID]: {user_text}"
    else:
        draft = memory_resp.get("answer_draft", "")
        user_content = (
            f"[MEMORY CONTEXT — low confidence]\nSuggested response: {draft}\n\n[USER SAID]: {user_text}"
            if draft else user_text
        )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ---------------------------------------------------------------------------
# Per-turn latency tracker (shared across processors, reset each turn)
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class LatencyTracker:
    stt: float = 0.0
    memory: float = 0.0
    llm: float = 0.0
    tts: float = 0.0

    def log(self) -> None:
        total = self.stt + self.memory + self.llm + self.tts
        logger.info(
            "[LATENCY] STT %.2fs | memory %.2fs | LLM %.2fs | TTS %.2fs | total %.2fs",
            self.stt, self.memory, self.llm, self.tts, total,
        )

    def reset(self) -> None:
        self.stt = self.memory = self.llm = self.tts = 0.0


# ---------------------------------------------------------------------------
# Main turn processor: memory lookup → LLM call → emit TextFrames
# ---------------------------------------------------------------------------

class MemoryContextProcessor(FrameProcessor):
    """On TranscriptionFrame: queries memory, calls LLM, streams TextFrames.

    Replaces the pipecat LLMService in the pipeline — avoids [CONFIRM] import
    issues and allows provider switching (TrueFoundry / OpenAI / Anthropic).
    """

    def __init__(self, memory_client: MemoryClient, llm, tracker: LatencyTracker) -> None:
        super().__init__()
        self._memory = memory_client
        self._llm = llm
        self._tracker = tracker

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if not isinstance(frame, TranscriptionFrame):
            await self.push_frame(frame, direction)
            return

        logger.info("Transcript: %s", frame.text)
        self._tracker.reset()

        # Memory query
        t0 = time.perf_counter()
        try:
            async with asyncio.timeout(3.0):
                if _is_temporal(frame.text):
                    resp = await self._memory.temporal(frame.text, "en")
                else:
                    resp = await self._memory.query(frame.text, "en")
        except Exception as e:
            logger.warning("Memory failed (%s) — fixture fallback", e)
            resp = get_fixture(frame.text)
        self._tracker.memory = time.perf_counter() - t0

        # LLM streaming
        messages = _build_messages(frame.text, resp)
        t1 = time.perf_counter()
        first_token = True
        try:
            async for chunk in self._llm.complete(messages):
                if first_token:
                    self._tracker.llm = time.perf_counter() - t1
                    first_token = False
                await self.push_frame(TextFrame(chunk))
        except Exception as e:
            logger.error("LLM error: %s", e)
            await self.push_frame(TextFrame("I'm sorry, I'm having trouble thinking right now."))


# ---------------------------------------------------------------------------
# Sentence aggregator
# ---------------------------------------------------------------------------

_SENTENCE_ENDS = {".", "!", "?", "…"}


class SentenceAggregator(FrameProcessor):
    """Buffer streaming TextFrames; flush on sentence-ending punctuation."""

    def __init__(self) -> None:
        super().__init__()
        self._buf = ""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, TextFrame):
            self._buf += frame.text
            if self._buf.rstrip() and self._buf.rstrip()[-1] in _SENTENCE_ENDS:
                await self.push_frame(TextFrame(self._buf.strip()))
                self._buf = ""
        elif isinstance(frame, EndFrame):
            if self._buf.strip():
                await self.push_frame(TextFrame(self._buf.strip()))
                self._buf = ""
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

async def run_agent(room_name: str) -> None:
    tracker = LatencyTracker()
    transport = create_transport(room_name)
    vad = VADProcessor(vad_analyzer=create_vad())
    stt = create_stt(tracker=tracker)
    memory_client = MemoryClient()
    llm = create_llm()
    memory_processor = MemoryContextProcessor(memory_client, llm, tracker)
    sentence_agg = SentenceAggregator()
    tts = MiniMaxTTSService(tracker=tracker)

    pipeline = Pipeline(
        [
            transport.input(),   # LiveKit audio in → UserAudioRawFrame
            vad,                 # VADProcessor → VADUserStartedSpeakingFrame / VADUserStoppedSpeakingFrame
            stt,                 # Groq Whisper STT → TranscriptionFrame
            memory_processor,    # memory + LLM → TextFrame (streaming)
            sentence_agg,        # buffer into sentences
            tts,                 # MiniMax TTS → AudioRawFrame (logs latency)
            transport.output(),  # LiveKit audio out
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),
    )

    reminder_queue: asyncio.Queue = asyncio.Queue()
    asyncio.create_task(poll_reminders(reminder_queue))

    runner = PipelineRunner()
    await runner.run(task)
    await memory_client.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    room = os.environ.get("LIVEKIT_ROOM", "yaad-demo")
    asyncio.run(run_agent(room))
