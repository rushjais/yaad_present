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
    VADUserStartedSpeakingFrame,
)
from pipecat.pipeline.pipeline import Pipeline  # type: ignore
from pipecat.pipeline.runner import PipelineRunner  # type: ignore
from pipecat.pipeline.task import PipelineParams, PipelineTask  # type: ignore
from pipecat.processors.audio.vad_processor import VADProcessor  # type: ignore
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor  # type: ignore

from .fallback import get_fixture
from .lang_toggle import LanguageState, start_lang_listener
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
    "The person you are SPEAKING TO is the one named Amma in the memory context. "
    "Always address her as 'you' / 'your' — never say 'Amma' as if she is not there. "
    "Example: if a chunk says 'Amma loves jasmine tea' you say 'You love jasmine tea.' "
    "State ONLY facts in the provided MEMORY context. "
    "If the context is empty or confidence is low, say you're not sure and offer to check with the family. "
    "Never invent people, events, or dates. "
    "Short, calm, warm. "
    "STRICT LANGUAGE RULE: detect the language the user spoke from [USER SAID] and reply ONLY in that language. "
    "English input → English reply only. Hindi input → Hindi reply only, using Devanagari script only (never Roman transliteration). "
    "The MEMORY context is always in English; translate facts into the user's language as needed. "
    "IDENTITY RULE: when asked who someone is, search ALL items in the MEMORY context for a person entry "
    "containing a relationship word (e.g. grandson, daughter, son, neighbour). If found, ALWAYS "
    "lead with that relationship expressed in the user's language, then add one warm detail. "
    "Never open with an event, a date, or a note. "
    "If NO relationship word is in the MEMORY CONTEXT, do NOT invent one — give the safe refusal "
    "in the user's language."
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
    if lang == "hi":
        lang_hint = (
            "[LANGUAGE: user spoke Hindi — you MUST reply entirely in Hindi using Devanagari script. "
            "DO NOT use Roman transliteration. DO NOT mix in English words.]\n\n"
        )
    else:
        lang_hint = "[LANGUAGE: user spoke English — reply ONLY in English.]\n\n"
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

    def __init__(self, memory_client: MemoryClient, llm, tracker: LatencyTracker,
                 lang_state: LanguageState | None = None) -> None:
        super().__init__()
        self._memory = memory_client
        self._llm = llm
        self._tracker = tracker
        self._lang_state = lang_state

    async def _translate_to_english(self, hindi_text: str) -> str:
        """Translate a Hindi query to English for Moss retrieval.

        Uses the same LLM already in the pipeline — no extra API key or import.
        Returns the original text on any error (graceful fallback).
        """
        msgs = [
            {"role": "system", "content": "Translate the following Hindi query to English. Return ONLY the translation, no explanation."},
            {"role": "user", "content": hindi_text},
        ]
        try:
            async with asyncio.timeout(2.0):
                out = []
                async for chunk in self._llm.complete(msgs):
                    out.append(chunk)
                return "".join(out).strip() or hindi_text
        except Exception:
            return hindi_text  # fallback: query in Hindi (will return 0 items but won't crash)

    async def _translate_draft_to_hindi(self, english_draft: str) -> str:
        """Translate a pre-composed English answer_draft to Hindi Devanagari.

        Preserves negation exactly: "not yet" → "अभी नहीं", "nothing" → "कुछ नहीं".
        Used on the temporal path when the user spoke Hindi — the draft is assembled
        by the memory engine in English and must be surfaced in the user's language.
        Returns the original draft on any error so the answer is never silently lost.
        """
        msgs = [
            {
                "role": "system",
                "content": (
                    "Translate the following short English sentence to Hindi using Devanagari script only. "
                    "Preserve all negation exactly: 'not yet' → 'अभी नहीं', 'nothing' → 'कुछ नहीं', "
                    "'no' → 'नहीं'. Do NOT recompose or paraphrase — translate faithfully. "
                    "Return ONLY the Hindi translation, no explanation."
                ),
            },
            {"role": "user", "content": english_draft},
        ]
        try:
            async with asyncio.timeout(3.0):
                out = []
                async for chunk in self._llm.complete(msgs):
                    out.append(chunk)
                return "".join(out).strip() or english_draft
        except Exception:
            return english_draft  # preserve original on failure

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if not isinstance(frame, TranscriptionFrame):
            await self.push_frame(frame, direction)
            return

        # Toggle is source of truth; Groq auto-detect is a safety net.
        toggle_lang = self._lang_state.lang if self._lang_state else "en"
        detected_lang = (getattr(frame, "language", None) or "en").strip().lower()
        is_hindi = (toggle_lang == "hi") or (detected_lang == "hindi")
        mem_lang = "hi" if is_hindi else "en"
        logger.info("[%s] Transcript: %s", "HI" if is_hindi else "EN", frame.text)
        self._tracker.reset()

        # For Hindi queries: translate to English before hitting memory so Moss
        # semantic search matches English chunks. The original Hindi text is kept
        # for the LLM response-composition step (language hint).
        query_text = frame.text
        if is_hindi:
            query_text = await self._translate_to_english(frame.text)
            logger.info("Hindi→English for memory: %r", query_text)

        # Memory query — track endpoint to distinguish temporal verbatim vs semantic hint.
        t0 = time.perf_counter()
        used_temporal = _is_temporal(query_text)
        try:
            async with asyncio.timeout(3.0):
                if used_temporal:
                    resp = await self._memory.temporal(query_text, "en")
                else:
                    resp = await self._memory.query(query_text, "en")
        except Exception as e:
            logger.warning("Memory failed (%s) — fixture fallback", e)
            resp = get_fixture(query_text)
        self._tracker.memory = time.perf_counter() - t0

        answer_draft = (resp.get("answer_draft") or "").strip()

        if used_temporal and answer_draft:
            # TEMPORAL PATH — answer_draft pre-composes absence facts like
            # "not yet taken" that have no semantic chunk. Emit verbatim for
            # English; translate to Hindi Devanagari for Hindi users so TTS
            # picks the correct voice and the speaker hears their language.
            logger.info("temporal answer_draft — emitting %s, skipping LLM re-composition", "after Hindi translation" if is_hindi else "verbatim")
            self._tracker.llm = 0.0
            if is_hindi:
                answer_draft = await self._translate_draft_to_hindi(answer_draft)
            await self.push_frame(TextFrame(answer_draft))
        else:
            # SEMANTIC PATH — use original transcript (Hindi if spoken in Hindi)
            # so the LLM sees what the user actually said and responds in kind.
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
# Flush on clause-internal punctuation once we have enough text so TTS starts
# speaking the first clause while the LLM is still generating the rest.
_CLAUSE_ENDS = {",", ";", ":"}
_CLAUSE_MIN_LEN = 50  # characters


class SentenceAggregator(FrameProcessor):
    """Buffer streaming TextFrames; flush on sentence or long-clause boundaries.

    Also discards any stale buffer when a new user turn starts, preventing
    leftover text from a previous (unpunctuated) LLM response from being
    prepended to the next turn's audio.
    """

    def __init__(self) -> None:
        super().__init__()
        self._buf = ""

    async def _flush(self) -> None:
        if self._buf.strip():
            await self.push_frame(TextFrame(self._buf.strip()))
        self._buf = ""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, TextFrame):
            self._buf += frame.text
            tail = self._buf.rstrip()
            if tail and tail[-1] in _SENTENCE_ENDS:
                await self._flush()
            elif tail and tail[-1] in _CLAUSE_ENDS and len(self._buf) >= _CLAUSE_MIN_LEN:
                await self._flush()
        elif isinstance(frame, VADUserStartedSpeakingFrame):
            # New user turn — discard any stale buffer from the previous response
            # so its tail doesn't get spoken while the user is already talking.
            self._buf = ""
            await self.push_frame(frame, direction)
        elif isinstance(frame, EndFrame):
            await self._flush()
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def _build_pipeline(transport) -> tuple:
    """Build shared pipeline components (VAD, STT, memory, LLM, TTS).

    Returns (pipeline, memory_client, lang_state).  Callers pass lang_state
    to start_lang_listener() so the 'h' toggle works while audio runs.
    """
    tracker = LatencyTracker()
    lang_state = LanguageState(default="en")
    vad = VADProcessor(vad_analyzer=create_vad())
    stt = create_stt(tracker=tracker, lang_state=lang_state)
    memory_client = MemoryClient()
    llm = create_llm()
    memory_processor = MemoryContextProcessor(memory_client, llm, tracker, lang_state=lang_state)
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
    return pipeline, memory_client, lang_state


async def run_agent(room_name: str) -> None:
    """LiveKit mode — connects to the given room."""
    transport = create_transport(room_name)
    pipeline, memory_client, lang_state = _build_pipeline(transport)
    start_lang_listener(lang_state)

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
    pipeline, memory_client, lang_state = _build_pipeline(transport)
    start_lang_listener(lang_state)

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
