"""
B7 — Graph: edge cache + neighbor expansion + relational walks.

What changed vs Gate-1:
- Per-query Supabase round-trips (N+1, ~2s p95) → in-memory edge cache loaded
  once at startup, refreshed after every write_memory.
- `get_neighbors()` returns enough info to expand into RetrievedItems —
  not just a weight for score-boost. Edges actually surface in answers.
- New `walk_relationship(from_ref, to_ref)` for relational queries:
  "Leo's mom" walks Leo → ? : son_of → Sarah and returns the edge type.
- `format_edge_phrase()` renders edge types as human text ("grandson_of"
  → "your grandson").
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional

from .config import settings


# ---------------------------------------------------------------------------
# Cache structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Edge:
    from_ref: str
    to_ref: str
    type: str
    weight: float


_lock = asyncio.Lock()
# ref → list of edges where ref is `from_ref` OR `to_ref`
_edges_by_ref: dict[str, list[Edge]] = {}
# ref → cached display text (so expansion doesn't round-trip)
_entity_text: dict[str, str] = {}
_loaded = False


def _client():
    from supabase import create_client
    return create_client(settings.supabase_url, settings.supabase_service_key)


def _person_text(p: dict) -> str:
    aliases = p.get("aliases") or []
    alias_str = f" (also called {', '.join(aliases)})" if aliases else ""
    return f"{p['name']} — {p.get('relationship', 'unknown')}{alias_str}. {p.get('notes', '')}"


def _place_text(pl: dict) -> str:
    return f"{pl['name']} ({pl.get('kind', 'place')}): {pl.get('notes', '')}"


def _med_text(m: dict) -> str:
    return f"Medication: {m['name']}. {m.get('notes', '')}"


def _event_text(e: dict) -> str:
    return f"Event: {e['title']}. {e.get('notes', '')}"


def _story_text(s: dict) -> str:
    return f"Story — {s['title']}: {s.get('text', '')}"


async def load_cache(force: bool = False) -> None:
    """Load all edges + entity display text into memory.
    Called once at startup; safe to re-call to refresh after a write_memory.
    """
    global _loaded
    async with _lock:
        if _loaded and not force:
            return
        client = _client()

        edges = client.table("edges").select("*").execute().data or []
        by_ref: dict[str, list[Edge]] = {}
        for e in edges:
            edge = Edge(
                from_ref=e["from_ref"],
                to_ref=e["to_ref"],
                type=e.get("type", "related"),
                weight=float(e.get("weight", 1.0)),
            )
            by_ref.setdefault(edge.from_ref, []).append(edge)
            by_ref.setdefault(edge.to_ref, []).append(edge)
        _edges_by_ref.clear()
        _edges_by_ref.update(by_ref)

        text: dict[str, str] = {}
        for p in (client.table("persons").select("*").execute().data or []):
            text[f"person:{p['id']}"] = _person_text(p)
        for pl in (client.table("places").select("*").execute().data or []):
            text[f"place:{pl['id']}"] = _place_text(pl)
        for m in (client.table("medications").select("*").execute().data or []):
            text[f"medication:{m['id']}"] = _med_text(m)
        for e in (client.table("events").select("*").execute().data or []):
            text[f"event:{e['id']}"] = _event_text(e)
        for s in (client.table("stories").select("*").execute().data or []):
            text[f"story:{s['id']}"] = _story_text(s)
        _entity_text.clear()
        _entity_text.update(text)

        _loaded = True


# ---------------------------------------------------------------------------
# Read API (cache-only — no DB)
# ---------------------------------------------------------------------------

def get_neighbors_cached(ref: str) -> list[Edge]:
    """All edges incident on `ref`. Read-only — no I/O."""
    return list(_edges_by_ref.get(ref, []))


def get_entity_text(ref: str) -> Optional[str]:
    """Cached display text for an entity ref, or None if we don't have it."""
    return _entity_text.get(ref)


def graph_proximity_score(ref: str) -> float:
    """Centrality boost: refs with more edges are more salient."""
    edges = _edges_by_ref.get(ref, [])
    if not edges:
        return 0.0
    return min(sum(e.weight for e in edges) / (len(edges) * 2), 1.0)


def walk_relationship(from_ref: str, to_ref: str) -> Optional[str]:
    """Return the edge type if `from_ref` and `to_ref` are directly connected,
    else None. (1-hop only.)
    """
    for e in _edges_by_ref.get(from_ref, []):
        if e.from_ref == from_ref and e.to_ref == to_ref:
            return e.type
        if e.to_ref == from_ref and e.from_ref == to_ref:
            return _invert_edge_type(e.type)
    return None


# ---------------------------------------------------------------------------
# Edge-type rendering
# ---------------------------------------------------------------------------

_EDGE_PHRASE = {
    "grandson_of":      "your grandson",
    "granddaughter_of": "your granddaughter",
    "daughter_of":      "your daughter",
    "son_of":           "her son",
    "mother_of":        "her mother",
    "father_of":        "her father",
    "sister_of":        "her sister",
    "brother_of":       "her brother",
    "wife_of":          "her wife",
    "husband_of":       "her husband",
    "lives_at":         "where she lives",
    "frequents":        "where she walks",
    "accepted_to":      "where they were accepted",
    "studies_at":       "where they study",
    "related":          "connected to her",
}

_INVERSE = {
    "grandson_of":      "grandmother_of",
    "granddaughter_of": "grandmother_of",
    "daughter_of":      "mother_of",
    "son_of":           "mother_of",
    "mother_of":        "daughter_of",
    "father_of":        "daughter_of",
    "lives_at":         "home_of",
    "frequents":        "frequented_by",
}


def _invert_edge_type(t: str) -> str:
    return _INVERSE.get(t, t)


def format_edge_phrase(edge_type: str) -> str:
    """'grandson_of' → 'your grandson'. Fallback: the raw type."""
    return _EDGE_PHRASE.get(edge_type, edge_type.replace("_", " "))


# ---------------------------------------------------------------------------
# Legacy compat — old retrieval.py callsites still work
# ---------------------------------------------------------------------------

async def get_neighbors(ref: str, depth: int = 1) -> list[dict]:
    """Deprecated — kept so old callsites still work. Reads from cache."""
    if not _loaded:
        await load_cache()
    return [
        {"ref": e.to_ref if e.from_ref == ref else e.from_ref,
         "weight": e.weight,
         "type": e.type}
        for e in _edges_by_ref.get(ref, [])
    ]


async def write_edge(from_ref: str, to_ref: str, edge_type: str, weight: float = 1.0) -> None:
    """Store a relationship edge in Supabase and refresh cache."""
    import uuid
    client = _client()
    client.table("edges").upsert({
        "id": str(uuid.uuid4()),
        "from_ref": from_ref,
        "to_ref": to_ref,
        "type": edge_type,
        "weight": weight,
    }).execute()
    await load_cache(force=True)
