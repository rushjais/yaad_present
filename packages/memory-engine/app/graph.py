"""
B7.1 — Graph cache (trimmed): entity-text lookup only.

What used to live here (edges, walks, relation phrasing) was killed in v2:
relationships live in the Moss chunk text (set at seed time), so retrieval
never needs to walk a graph. The only remaining job of this module is to
let `capture.py` look up an existing entity's display text after it
resolves an extracted name against Moss.

Cache is loaded once at startup, refreshed after every `write_memory`.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from .config import settings


_lock = asyncio.Lock()
_entity_text: dict[str, str] = {}     # ref → display text (e.g. "person:abc" → "Leo. Amma's grandson…")
_loaded = False


def _client():
    from supabase import create_client
    return create_client(settings.supabase_url, settings.supabase_service_key)


# Chunk-text helpers — keep in sync with scripts/reseed_moss.py so the cache
# matches what Moss is actually indexing. (Capture uses these only to render
# fallback labels for entity refs; Moss text is the source of truth for
# retrieval.)
def _person_label(p: dict) -> str:
    return p.get("name", "person")


def _place_label(pl: dict) -> str:
    return pl.get("name", "place")


def _med_label(m: dict) -> str:
    return m.get("name", "medication")


async def load_cache(force: bool = False) -> None:
    """Load entity display labels into memory. ~1s on startup, free thereafter."""
    global _loaded
    async with _lock:
        if _loaded and not force:
            return
        client = _client()
        text: dict[str, str] = {}
        for p in (client.table("persons").select("*").execute().data or []):
            text[f"person:{p['id']}"] = _person_label(p)
        for pl in (client.table("places").select("*").execute().data or []):
            text[f"place:{pl['id']}"] = _place_label(pl)
        for m in (client.table("medications").select("*").execute().data or []):
            text[f"medication:{m['id']}"] = _med_label(m)
        _entity_text.clear()
        _entity_text.update(text)
        _loaded = True


def get_entity_text(ref: str) -> Optional[str]:
    """Display label for an entity ref (used by capture to attribute proposals)."""
    return _entity_text.get(ref)
