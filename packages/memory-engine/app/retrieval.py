from __future__ import annotations


async def query_memory(text: str, lang: str = "en") -> dict:
    from .router import dispatch

    return await dispatch(text, lang)
