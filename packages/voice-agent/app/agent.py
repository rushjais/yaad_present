"""Track A — Yaad voice agent pipeline.

Pipeline:
  LiveKit audio in
  → Groq Whisper STT (multilingual, auto-detects Hindi/English)
  → MemoryContextProcessor  ← queries memory-engine, injects grounding context
  → TrueFoundry LLM         ← grounding system prompt, short warm answers
  → MiniMax TTS             ← Hindi/English bilingual
  → LiveKit audio out

Barge-in: SileroVAD in the transport emits StartInterruptionFrame on new speech,
which Pipecat propagates to cancel in-flight TTS automatically.

[CONFIRM] pipecat version-specific import paths throughout this file.
"""

import asyncio
import logging
import os

from dotenv import load_dotenv

# [CONFIRM] pipecat import paths — adjust for installed version
from pipecat.frames.frames import (  # type: ignore
    Frame,
    LLMMessagesFrame,
    TranscriptionFrame,
    TextFrame,
    EndFrame,
)
from pipecat.pipeline.pipeline import Pipeline  # type: ignore
from pipecat.pipeline.runner import PipelineRunner  # type: ignore
from pipecat.pipeline.task import PipelineTask, PipelineParams  # type: ignore
from pipecat.processors.frame_processor import FrameProcessor, FrameDirection  # type: ignore

from .fallback import get_fixture
from .llm import create_llm
from .memory_client import MemoryClient
from .reminders_client import poll_reminders
from .stt_groq import create_stt  # switched from stt_deepgram (Deepgram not working)
from .transports import create_transport
from .tts_minimax import MiniMaxTTSService

load_dotenv()
logger = logging.getLogger(__name__)

# §6 grounding system prompt — verbatim from CLAUDE.md
SYSTEM_PROMPT = (
    "You are Yaad, a warm companion for someone with memory loss. "
    "State ONLY facts in the provided MEMORY context. "
    "If the context is empty or confidence is low, say you're not sure and offer to check with the family. "
    "Never invent people, events, or dates. "
    "Be short, calm, and warm. "
    "Match the user's language (English, Hindi, or Hinglish)."
)

# Keywords that signal a temporal query → route to /memory/temporal
_TEMPORAL_KW = {
    "pill", "pills", "medicine", "medication", "tablet", "dose",
    "dawai", "dawa",  # Hindi equivalents
    "took", "taken", "today", "yesterday", "morning", "evening",
    "coming", "visit", "appointment",
}


def _is_temporal(text: str) -> bool:
    return any(kw in text.lower() for kw in _TEMPORAL_KW)


def _map_lang(deepgram_lang: str | None) -> str:
    """Map Deepgram language code to our CONTRACT lang enum: en|hi|hi-en."""
    if not deepgram_lang:
        return "en"
    if deepgram_lang.startswith("hi"):
        return "hi"
    return "en"


def _format_memory_context(resp: dict) -> str:
    """Build a concise memory context block from a QueryResponse."""
    if not resp.get("grounded") or not resp.get("items"):
        # answer_draft is the safe refusal when grounded=False
        return ""
    lines = [f"- {item['text']}" for item in resp["items"][:5]]
    return "\n".join(lines)


def _build_user_message(user_text: str, memory_resp: dict) -> str:
    ctx = _format_memory_context(memory_resp)
    if ctx:
        return f"[MEMORY CONTEXT]\n{ctx}\n\n[USER SAID]: {user_text}"
    # grounded=False case: pass safe refusal hint to LLM
    draft = memory_resp.get("answer_draft", "")
    if draft:
        return f"[MEMORY CONTEXT — low confidence]\nSuggested response: {draft}\n\n[USER SAID]: {user_text}"
    return user_text


class MemoryContextProcessor(FrameProcessor):
    """Intercepts TranscriptionFrames, queries memory-engine, emits LLMMessagesFrame.

    On memory timeout or error, falls back to canned fixtures (§13).
    Does NOT maintain multi-turn history — each turn is fresh with its memory
    context. Fine for the demo; extend if continuity is needed.
    """

    def __init__(self, memory_client: MemoryClient) -> None:
        super().__init__()
        self._memory = memory_client

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if not isinstance(frame, TranscriptionFrame):
            await self.push_frame(frame, direction)
            return

        lang = _map_lang(getattr(frame, "language", None))
        logger.info("Transcript [%s]: %s", lang, frame.text)

        try:
            async with asyncio.timeout(3.0):
                if _is_temporal(frame.text):
                    resp = await self._memory.temporal(frame.text, lang)
                else:
                    resp = await self._memory.query(frame.text, lang)
            logger.debug("Memory grounded=%s confidence=%.2f", resp.get("grounded"), resp.get("confidence", 0))
        except Exception as e:
            logger.warning("Memory query failed (%s) — using fixture fallback", e)
            resp = get_fixture(frame.text)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(frame.text, resp)},
        ]
        await self.push_frame(LLMMessagesFrame(messages))


# ---------------------------------------------------------------------------
# Sentence aggregator — collect streaming TextFrames into sentences for TTS.
# [CONFIRM] if pipecat has a built-in SentenceAggregator, prefer that.
# ---------------------------------------------------------------------------

_SENTENCE_ENDS = {".", "!", "?", "।", "…"}


class SentenceAggregator(FrameProcessor):
    """Buffer streaming LLM TextFrames; flush on sentence-ending punctuation."""

    def __init__(self) -> None:
        super().__init__()
        self._buf = ""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, TextFrame):
            self._buf += frame.text
            # flush when we hit a sentence boundary
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
# Pipeline assembly + runner
# ---------------------------------------------------------------------------

async def run_agent(room_name: str) -> None:
    transport = create_transport(room_name)
    stt = create_stt()
    memory_client = MemoryClient()
    memory_processor = MemoryContextProcessor(memory_client)
    llm = create_llm()
    sentence_agg = SentenceAggregator()
    tts = MiniMaxTTSService()

    pipeline = Pipeline(
        [
            transport.input(),   # LiveKit audio in
            stt,                 # Deepgram STT → TranscriptionFrame
            memory_processor,    # memory query → LLMMessagesFrame
            llm,                 # TrueFoundry LLM → TextFrame (streaming)
            sentence_agg,        # aggregate sentences → TextFrame
            tts,                 # MiniMax TTS → AudioRawFrame
            transport.output(),  # LiveKit audio out
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(allow_interruptions=True),  # enables barge-in
    )

    # A5: proactive reminders — background task
    reminder_queue: asyncio.Queue = asyncio.Queue()
    asyncio.create_task(poll_reminders(reminder_queue))

    runner = PipelineRunner()
    await runner.run(task)
    await memory_client.aclose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    room = os.environ.get("LIVEKIT_ROOM", "yaad-demo")
    asyncio.run(run_agent(room))
