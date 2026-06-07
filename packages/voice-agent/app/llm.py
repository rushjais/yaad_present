"""LLM provider factory — auto-detects credentials at startup.

Priority:
  1. TrueFoundry  — if TRUEFOUNDRY_BASE_URL + TRUEFOUNDRY_API_KEY + TRUEFOUNDRY_MODEL set
  2. OpenAI direct — elif OPENAI_API_KEY set  (model: gpt-4o)
  3. Anthropic     — elif ANTHROPIC_API_KEY set (via messages API)
  4. Error         — raises with a clear message listing which vars to set

Each provider exposes the same interface:
    async def complete(messages: list[dict]) -> AsyncIterator[str]
so callers don't need to know which is active.
"""

import logging
import os
from collections.abc import AsyncIterator
from typing import Protocol

logger = logging.getLogger(__name__)


class LLMProvider(Protocol):
    async def complete(self, messages: list[dict]) -> AsyncIterator[str]: ...


# ---------------------------------------------------------------------------
# OpenAI-compatible provider (covers TrueFoundry + OpenAI)
# ---------------------------------------------------------------------------

class OpenAICompatProvider:
    def __init__(self, api_key: str, model: str, base_url: str | None = None) -> None:
        import openai
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = openai.AsyncOpenAI(**kwargs)
        self._model = model

    async def complete(self, messages: list[dict]) -> AsyncIterator[str]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            stream=True,
            max_tokens=256,
            temperature=0.4,
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta


# ---------------------------------------------------------------------------
# Anthropic provider
# ---------------------------------------------------------------------------

class AnthropicProvider:
    def __init__(self, api_key: str) -> None:
        import anthropic
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = "claude-haiku-4-5-20251001"

    async def complete(self, messages: list[dict]) -> AsyncIterator[str]:
        # Anthropic separates system prompt from messages
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        user_msgs = [m for m in messages if m["role"] != "system"]
        async with self._client.messages.stream(
            model=self._model,
            max_tokens=256,
            system=system,
            messages=user_msgs,
        ) as stream:
            async for text in stream.text_stream:
                yield text


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_llm() -> LLMProvider:
    tf_url = os.environ.get("TRUEFOUNDRY_BASE_URL", "").strip()
    tf_key = os.environ.get("TRUEFOUNDRY_API_KEY", "").strip()
    tf_model = os.environ.get("TRUEFOUNDRY_MODEL", "").strip()
    oai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    ant_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()

    if tf_url and tf_key and tf_model:
        logger.info("LLM provider: TrueFoundry (%s @ %s)", tf_model, tf_url)
        return OpenAICompatProvider(api_key=tf_key, model=tf_model, base_url=tf_url)

    if oai_key:
        logger.info("LLM provider: OpenAI direct (gpt-4o)")
        return OpenAICompatProvider(api_key=oai_key, model="gpt-4o")

    if ant_key:
        logger.info("LLM provider: Anthropic (claude-haiku-4-5-20251001)")
        return AnthropicProvider(api_key=ant_key)

    raise RuntimeError(
        "No LLM configured. Set one of:\n"
        "  TrueFoundry: TRUEFOUNDRY_BASE_URL + TRUEFOUNDRY_API_KEY + TRUEFOUNDRY_MODEL\n"
        "  OpenAI:      OPENAI_API_KEY\n"
        "  Anthropic:   ANTHROPIC_API_KEY"
    )
