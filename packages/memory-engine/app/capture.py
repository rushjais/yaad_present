"""
B5 — Episodic memory capture.
Explicit trigger: "remember this..." or "don't forget..." → extract entities → write to Moss + Supabase.
Honest scope: explicit-trigger only. Reliable live-update beat is the caregiver web form.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from .schemas import MemoryCaptureResponse

_TRIGGER = re.compile(
    r"(remember|don'?t forget|keep in mind|note that|make a note)\b",
    re.IGNORECASE,
)


async def capture_from_transcript(transcript: str) -> MemoryCaptureResponse:
    if not _TRIGGER.search(transcript):
        return MemoryCaptureResponse(created_refs=[])

    extracted = _extract_fact(transcript)
    if not extracted:
        return MemoryCaptureResponse(created_refs=[])

    ref = await _store_episode(extracted)
    return MemoryCaptureResponse(created_refs=[ref])


def _extract_fact(text: str) -> str | None:
    # Strip trigger phrase, return the remainder as the fact text
    cleaned = _TRIGGER.sub("", text).strip(" ,.:!?")
    return cleaned if len(cleaned) > 5 else None


async def _store_episode(text: str) -> str:
    episode_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    ref = f"episode:{episode_id}"

    payload = {
        "id": episode_id,
        "title": text[:60],
        "occurred_ts": now.isoformat(),
        "kind": "captured_fact",
        "entity_refs": [],
        "summary": text,
        "provenance": {
            "source": "voice_capture",
            "added_by": "voice_agent",
            "added_ts": now.isoformat(),
        },
    }

    # Write to Supabase
    try:
        from .db import write_memory
        await write_memory("episode", payload)
    except Exception:
        pass

    # Index in Moss for immediate retrieval
    try:
        from .moss_client import moss
        await moss.upsert(ref, text, {
            "type": "episode",
            "provenance": payload["provenance"],
        })
    except Exception:
        pass

    return ref
