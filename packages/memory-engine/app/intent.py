from __future__ import annotations


async def understand(text: str, allow_llm: bool = True):
    from .router import classify

    return await classify(text)
