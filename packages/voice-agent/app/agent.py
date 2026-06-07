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

# load_dotenv FIRST — before any local imports that read env vars at module level.
# tts_minimax.py and others capture constants on import; if .env isn't loaded yet
# those constants are empty strings. This ordering fixes the "Bearer " bug.
from dotenv import load_dotenv
load_dotenv()

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
from .local_transport import LocalAudioTransport
from .memory_client import MemoryClient
from .reminders_client import poll_reminders
from .stt_groq import create_stt
from .transports import create_transport, create_vad
from .tts_minimax import MiniMaxTTSService

logger = logging.getLogger(__name__)

# §6 grounding system prompt — English + Hindi
SYSTEM_PROMPT = (
    "You are Yaad, a warm companion for someone with memory loss. "
    "State ONLY facts in the provided MEMORY context. "
    "If the context is empty or confidence is low, say you're not sure and offer to check with the family. "
    "Never invent people, events, or dates. "
    "Short, calm, warm. "
    "LANGUAGE RULE: respond in the same language the user spoke. "
    "If the user spoke Hindi, reply fully in Hindi (Devanagari script). "
    "The MEMORY context is in English — translate your answer into Hindi if needed. "
    "IDENTITY RULE: when asked who someone is ('Who is X?', 'Kaun hai X?', 'Yeh kaun hai?'), "
    "search ALL items in the MEMORY context for a person entry containing a relationship word "
    "(grandson, daughter, son, daughter-in-law, pota, beti, beta, nati, etc.). If found, ALWAYS "
    "lead with that relationship in the user's language, then add one warm detail. "
    "Never open with an event, a date, or a note. "
    "If NO relationship word is in the MEMORY CONTEXT, do NOT invent one — give the safe refusal "
    "in the user's language ('I\\'m not sure' / 'Mujhe pata nahi, main family se poochhunga')."
)

_TEMPORAL_KW = {
    "pill", "pills", "medicine", "medication", "tablet", "dose",
    "took", "taken", "today", "yesterday", "morning", "evening",
    "coming", "visit", "appointment", "doctor", "checkup", "schedule",
}


def _is_temporal(text: str) -> bool:
    return any(kw in text.lower() for kw in _TEMPORAL_KW)


def _format_memory_context(resp: dict) -> str:
    if not resp.get("grounded") or not resp.get("items"):
        return ""
    return "\n".join(f"- {item['text']}" for item in resp["items"][:5])


def _build_messages_semantic(user_text: str, memory_resp: dict, lang: str = "en") -> list[dict]:
    """Build LLM messages for the SEMANTIC path.

    lang: "hi" → adds an explicit Hindi instruction so the LLM replies in Devanagari
          even when the memory context (and most of its training) is English.
    """
    ctx = _format_memory_context(memory_resp)
    lang_hint = "[LANGUAGE: user spoke Hindi — reply fully in Hindi / Devanagari]\n\n" if lang == "hi" else ""
    user_content = (
        f"{lang_hint}[MEMORY CONTEXT]\n{ctx}\n\n[USER SAID]: {user_text}"
        if ctx else f"{lang_hint}{user_text}"
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

        # Detect language from Groq's transcription (used for memory query + LLM language hint)
        detected_lang = (getattr(frame, "language", None) or "en").strip().lower()
        mem_lang = "hi" if detected_lang == "hindi" else "en"

        # Memory query — track which endpoint was used so we know if answer_draft
        # is a pre-composed temporal fact (must speak verbatim) or a semantic hint.
        t0 = time.perf_counter()
        used_temporal = _is_temporal(frame.text)
        try:
            async with asyncio.timeout(3.0):
                if used_temporal:
                    resp = await self._memory.temporal(frame.text, mem_lang)
                else:
                    resp = await self._memory.query(frame.text, mem_lang)
        except Exception as e:
            logger.warning("Memory failed (%s) — fixture fallback", e)
            resp = get_fixture(frame.text)
        self._tracker.memory = time.perf_counter() - t0

        answer_draft = (resp.get("answer_draft") or "").strip()

        if used_temporal and answer_draft:
            # TEMPORAL PATH — answer_draft pre-composes absence facts like
            # "not yet taken" that have no semantic chunk. Emit verbatim;
            # LLM re-composition would silently drop the negation.
            logger.info("temporal answer_draft — emitting verbatim, skipping LLM")
            self._tracker.llm = 0.0
            await self.push_frame(TextFrame(answer_draft))
        else:
            # SEMANTIC PATH — compose grounded answer from items[] via LLM.
            messages = _build_messages_semantic(frame.text, resp, lang=mem_lang)
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

def _build_pipeline(transport) -> tuple:
    """Build shared pipeline components (VAD, STT, memory, LLM, TTS)."""
    tracker = LatencyTracker()
    vad = VADProcessor(vad_analyzer=create_vad())
    stt = create_stt(tracker=tracker)
    memory_client = MemoryClient()
    llm = create_llm()
    memory_processor = MemoryContextProcessor(memory_client, llm, tracker)
    sentence_agg = SentenceAggregator()
    tts = MiniMaxTTSService(tracker=tracker)

    pipeline = Pipeline(
        [
            transport.input(),   # audio in
            vad,                 # VADProcessor → VADUserStartedSpeakingFrame / VADUserStoppedSpeakingFrame
            stt,                 # Groq Whisper STT → TranscriptionFrame
            memory_processor,    # memory query + LLM (or answer_draft bypass) → TextFrame
            sentence_agg,        # buffer into sentences
            tts,                 # MiniMax TTS → TTSAudioRawFrame
            transport.output(),  # audio out
        ]
    )
    return pipeline, memory_client


async def run_agent(room_name: str) -> None:
    """LiveKit mode — connects to the given room."""
    transport = create_transport(room_name)
    pipeline, memory_client = _build_pipeline(transport)

    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))
    reminder_queue: asyncio.Queue = asyncio.Queue()
    asyncio.create_task(poll_reminders(reminder_queue))

    runner = PipelineRunner()
    await runner.run(task)
    await memory_client.aclose()


async def run_agent_local() -> None:
    """Local mode — mic + speakers via sounddevice, no LiveKit."""
    logger.info("Local audio mode — speak into your mic, Yaad will reply through speakers.")
    transport = LocalAudioTransport()
    pipeline, memory_client = _build_pipeline(transport)

    task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=True))
    reminder_queue: asyncio.Queue = asyncio.Queue()
    asyncio.create_task(poll_reminders(reminder_queue))

    runner = PipelineRunner()
    await runner.run(task)
    await memory_client.aclose()


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="Yaad voice agent")
    parser.add_argument("--local", action="store_true", help="Use local mic/speakers instead of LiveKit")
    args = parser.parse_args()

    if args.local:
        asyncio.run(run_agent_local())
    else:
        room = os.environ.get("LIVEKIT_ROOM", "yaad-demo")
        asyncio.run(run_agent(room))
