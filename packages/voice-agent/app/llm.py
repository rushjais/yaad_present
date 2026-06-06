"""TrueFoundry LLM service (OpenAI-compatible gateway).

[CONFIRM] at sponsor table:
- TRUEFOUNDRY_BASE_URL (e.g. https://llm.truefoundry.com/api/inference/openai)
- TRUEFOUNDRY_MODEL (e.g. openai-main/gpt-4o-mini or claude-3-haiku via gateway)
- Whether the gateway supports streaming (required for low latency)
"""

import os

# [CONFIRM] pipecat import path
from pipecat.services.openai import OpenAILLMService  # type: ignore


def create_llm() -> OpenAILLMService:
    return OpenAILLMService(
        api_key=os.environ["TRUEFOUNDRY_API_KEY"],
        # [CONFIRM] base_url at sponsor table
        base_url=os.environ.get(
            "TRUEFOUNDRY_BASE_URL",
            "https://llm.truefoundry.com/api/inference/openai",
        ),
        # [CONFIRM] model name at sponsor table
        model=os.environ.get("TRUEFOUNDRY_MODEL", "openai-main/gpt-4o-mini"),
    )
