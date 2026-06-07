"""
B7 — Retrieval: Moss semantic + real graph expansion + intent routing.

What changed vs Gate-1:
- Reads from `graph._edges_by_ref` (in-memory) — no per-hit Supabase round-trip.
  Kills the N+1 problem that was causing 2.5s p95.
- Top-K Moss hits trigger 1-hop neighbor expansion: neighbors are materialized
  as RetrievedItems with their cached text. "Tell me about Leo" now returns
  Leo *and* Sarah (his mom) *and* the chess story.
- Edge type surfaced in answer text.
- Relational shortcut: when Intent.kind=relational, walk edges between entity
  pairs and answer with the relationship, not just the entity.
- Grounding gate split: raw Moss semantic ≥ `SEMANTIC_FLOOR` AND composite
  ≥ τ. Fixes the "Who is the president?" confabulation where high recency +
  salience pushed an unrelated entity over τ.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Optional

from .config import settings
from .schemas import EntityType, Provenance, RetrievedItem


SEMANTIC_FLOOR = 0.85       # raw Moss score required for grounding=true.
                            # Moss is uniformly generous (~0.80 for any query),
                            # so a true match clears 0.85+. Below that → suspect.
NEIGHBOR_FACTOR = 0.7


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def _recency_score(added_ts: str | None) -> float:
    if not added_ts:
        return 0.5
    try:
        ts = datetime.fromisoformat(added_ts.replace("Z", "+00:00"))
        delta_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        return math.exp(-settings.recency_lambda * delta_hours)
    except Exception:
        return 0.5


def _salience(meta: dict) -> float:
    kind = meta.get("type", "")
    if kind in ("person", "med_log"):
        return 1.0
    if kind in ("medication", "episode"):
        return 0.8
    return 0.5


def _compose(semantic: float, recency: float, salience: float, graph_prox: float) -> float:
    s = settings
    return s.alpha * semantic + s.beta * recency + s.gamma * salience + s.delta * graph_prox


def _provenance_from_meta(meta: dict) -> Provenance:
    prov_raw = meta.get("provenance", {}) or {}
    if isinstance(prov_raw, str):
        prov_raw = {}
    return Provenance(
        source=prov_raw.get("source", "unknown"),
        added_by=prov_raw.get("added_by", "unknown"),
        added_ts=datetime.fromisoformat(
            (prov_raw.get("added_ts") or "2025-01-01T00:00:00+00:00").replace("Z", "+00:00")
        ),
    )


def _entity_type_from_meta(meta: dict) -> EntityType:
    t = meta.get("type", "episode")
    try:
        return EntityType(t)
    except Exception:
        return EntityType.episode


def _ref_to_type(ref: str) -> EntityType:
    kind = ref.split(":", 1)[0]
    try:
        return EntityType(kind)
    except Exception:
        return EntityType.episode


def _inverted_phrase(edge_type: str) -> str:
    from .graph import _INVERSE
    return _INVERSE.get(edge_type, edge_type)


# ---------------------------------------------------------------------------
# Pre-grounding guards
# ---------------------------------------------------------------------------

_OFF_TOPIC_HINTS = (
    "president", "prime minister", "weather", "stock", "news",
    "2 plus 2", "what is 2", "what's 2", "color of",
)

# Concepts that ARE in our graph even if no proper noun was extracted.
# A query mentioning any of these is "about" the graph and shouldn't be
# rejected for missing an entity name.
_IMPLICIT_ENTITY_WORDS = (
    "family", "grandson", "granddaughter", "daughter", "son", "mother",
    "father", "sister", "brother", "husband", "wife",
    "home", "house", "garden", "park", "neighborhood",
    "medication", "pill", "pills", "medicine",
)


def _looks_off_topic(intent, text: str) -> bool:
    t = text.lower()
    for hint in _OFF_TOPIC_HINTS:
        if hint in t:
            return True
    # If the query has no proper-noun entity AND no kinship/place anchor AND
    # no time/medication signal → no hook into the graph → treat as off-topic.
    if (intent.kind in ("general", "relational", "who_is")
            and not intent.entities
            and intent.time_window is None
            and not intent.medication_hint
            and not any(w in t for w in _IMPLICIT_ENTITY_WORDS)):
        return True
    return False


def _entity_name_in_top(name: str, top_hit: dict) -> bool:
    """The top Moss hit must actually mention the named entity. Catches the
    'Who is the president?' → Leo confabulation where Moss returned Leo
    because the question matches the *shape* of "who is X" semantically.
    """
    text = (top_hit.get("text") or "").lower()
    return name.lower() in text


def _refused(message: str) -> dict:
    return {
        "items": [],
        "grounded": False,
        "confidence": 0.0,
        "answer_draft": message,
    }


# ---------------------------------------------------------------------------
# Main query path
# ---------------------------------------------------------------------------

async def query_memory(text: str, lang: str = "en") -> dict:
    """Full retrieval pipeline:
    1. understand → intent
    2. Moss semantic search
    3. 1-hop graph expansion via cached edges
    4. Composed scoring + grounding floor
    5. Relational shortcut when applicable
    """
    from .graph import (
        load_cache, get_neighbors_cached, get_entity_text, graph_proximity_score,
        format_edge_phrase,
    )
    from .grounding import assess_grounding, safe_refusal
    from .intent import understand
    from .moss_client import moss

    await load_cache()
    intent = await understand(text)

    if intent.kind in ("temporal_med", "temporal_event"):
        from .temporal import execute
        return await execute(intent, lang)

    if intent.kind == "remember":
        try:
            from .capture import capture_from_intent
            return await capture_from_intent(intent, lang)
        except ImportError:
            pass  # capture not yet rebuilt — fall through to semantic

    raw = await moss.query(text, top_k=10, lang=lang)
    if not raw:
        return {
            "items": [], "grounded": False, "confidence": 0.0,
            "answer_draft": safe_refusal(lang),
        }

    # Pre-grounding guards (kill confabulation before scoring):
    #   1. "general" intent with no entities → off-topic question, refuse
    #   2. "who_is" intent with a named entity → top hit's text MUST contain
    #      the entity name (or a known alias)
    if _looks_off_topic(intent, text):
        return _refused(safe_refusal(lang))

    if intent.kind == "who_is" and intent.entities:
        # Check the top 3 hits — a freshly-captured fact about the entity
        # might not be #1 if older entities semantically match the question
        # shape better.
        if not any(_entity_name_in_top(intent.entities[0], h) for h in raw[:3]):
            return _refused(safe_refusal(lang))

    # Relational shortcut — only when there's clearly ONE subject. If the
    # query mentions two entities (e.g. "Did Leo get into Stanford?") it's a
    # fact question, not a relationship question; fall through to semantic.
    if intent.kind == "relational" and len(intent.entities) == 1:
        relational = await _relational_walk(intent.entities[0], raw)
        if relational is not None:
            return relational

    # Standard semantic + expansion
    primary: list[RetrievedItem] = []
    primary_refs: set[str] = set()

    for r in raw:
        meta = r.get("metadata", {}) or {}
        semantic = float(r.get("score", 0.0))
        ref = r["id"]
        primary_refs.add(ref)

        gp = graph_proximity_score(ref)
        prov = meta.get("provenance") if isinstance(meta.get("provenance"), dict) else {}
        recency = _recency_score(prov.get("added_ts"))
        salience = _salience(meta)
        composite = _compose(semantic, recency, salience, gp)

        primary.append(RetrievedItem(
            ref=ref,
            type=_entity_type_from_meta(meta),
            text=r.get("text", ""),
            score=composite,
            provenance=_provenance_from_meta(meta),
        ))

    primary.sort(key=lambda i: i.score, reverse=True)

    # Expand neighbors of the top 2 hits — materialize as RetrievedItems
    expanded: list[RetrievedItem] = []
    for parent in primary[:2]:
        for edge in get_neighbors_cached(parent.ref):
            neighbor_ref = edge.to_ref if edge.from_ref == parent.ref else edge.from_ref
            if neighbor_ref in primary_refs:
                continue
            neighbor_text = get_entity_text(neighbor_ref)
            if not neighbor_text:
                continue
            phrase = format_edge_phrase(
                edge.type if edge.from_ref == parent.ref else _inverted_phrase(edge.type)
            )
            expanded.append(RetrievedItem(
                ref=neighbor_ref,
                type=_ref_to_type(neighbor_ref),
                text=f"{neighbor_text}  (relation: {phrase})",
                score=parent.score * NEIGHBOR_FACTOR,
                provenance=Provenance(
                    source="graph_expansion",
                    added_by="graph",
                    added_ts=datetime.now(timezone.utc),
                ),
            ))
            primary_refs.add(neighbor_ref)

    combined = primary + expanded
    combined.sort(key=lambda i: i.score, reverse=True)
    top = combined[:6]

    # Grounding gate: raw Moss semantic floor on the top semantic hit.
    # Bypass the floor when the query has a kinship/place anchor — those are
    # legitimately concept-level queries that score lower (~0.80) but should
    # still resolve via expansion.
    top_raw_semantic = float(raw[0].get("score", 0.0))
    t_low = text.lower()
    has_implicit = any(w in t_low for w in _IMPLICIT_ENTITY_WORDS)
    grounded_by_semantic = top_raw_semantic >= SEMANTIC_FLOOR or has_implicit

    result = assess_grounding(top, text)
    if not grounded_by_semantic:
        result["grounded"] = False
        result["confidence"] = round(top_raw_semantic, 3)
        result["answer_draft"] = safe_refusal(lang)
    return result


# ---------------------------------------------------------------------------
# Relational walk
# ---------------------------------------------------------------------------

async def _relational_walk(entity_name: str, raw_hits: list[dict]) -> Optional[dict]:
    """If `entity_name` resolves to a ref via Moss, walk its edges and return
    a relational answer composed of (entity + 1-hop neighbors). None → caller
    falls back to semantic.

    Direction matters:
      edge `Leo --grandson_of--> Amma` means
        - "Leo IS Amma's grandson"  (forward, subject=Leo)
        - "Amma IS Leo's grandmother" (inverted, subject=Amma)
    We resolve relative to the queried entity and produce natural text per
    neighbor.
    """
    from .graph import get_neighbors_cached, get_entity_text

    entity_ref: Optional[str] = None
    for hit in raw_hits:
        if hit["metadata"].get("type") == "person" and entity_name.lower() in (hit.get("text") or "").lower():
            entity_ref = hit["id"]
            break
    if entity_ref is None:
        return None

    neighbors = get_neighbors_cached(entity_ref)
    if not neighbors:
        return None

    items: list[RetrievedItem] = [RetrievedItem(
        ref=entity_ref,
        type=EntityType.person,
        text=get_entity_text(entity_ref) or "",
        score=1.0,
        provenance=Provenance(source="graph_walk", added_by="graph",
                              added_ts=datetime.now(timezone.utc)),
    )]

    parts: list[str] = []
    for edge in neighbors:
        neighbor_ref = edge.to_ref if edge.from_ref == entity_ref else edge.from_ref
        neighbor_text = get_entity_text(neighbor_ref)
        if not neighbor_text:
            continue
        neighbor_name = _short_name(neighbor_text)

        # The edge stored direction determines the sentence.
        if edge.from_ref == entity_ref:
            # entity is the subject of edge.type
            sentence = _sentence_for(entity_name, edge.type, neighbor_name, forward=True)
        else:
            sentence = _sentence_for(entity_name, edge.type, neighbor_name, forward=False)

        parts.append(sentence)
        items.append(RetrievedItem(
            ref=neighbor_ref,
            type=_ref_to_type(neighbor_ref),
            text=neighbor_text,
            score=0.9,
            provenance=Provenance(source="graph_walk", added_by="graph",
                                  added_ts=datetime.now(timezone.utc)),
        ))

    return {
        "items": [i.model_dump() for i in items],
        "grounded": True,
        "confidence": 0.95,
        "answer_draft": " ".join(parts) or f"{entity_name} is in your family.",
    }


def _short_name(text: str) -> str:
    """First token of entity text — 'Sarah — daughter…' → 'Sarah'."""
    head = text.split('—', 1)[0].split('(', 1)[0].split(':', 1)[0].strip()
    return head or text[:20]


# Maps (edge_type, forward) → "X is <PHRASE> Y" pattern.
# forward = True: X has edge_type to Y (X is the subject in the edge)
# forward = False: Y has edge_type to X (we're asking about Y, edge is from X)
_RELATION_SENTENCE = {
    ("grandson_of",      True):  "{x} is {y}'s grandson.",
    ("grandson_of",      False): "{x} is {y}'s grandmother.",
    ("granddaughter_of", True):  "{x} is {y}'s granddaughter.",
    ("granddaughter_of", False): "{x} is {y}'s grandmother.",
    ("daughter_of",      True):  "{x} is {y}'s daughter.",
    ("daughter_of",      False): "{x} is {y}'s mother.",
    ("son_of",           True):  "{x} is {y}'s son.",
    ("son_of",           False): "{x} is {y}'s mother.",
    ("mother_of",        True):  "{x} is {y}'s mother.",
    ("mother_of",        False): "{x} is {y}'s daughter.",
    ("father_of",        True):  "{x} is {y}'s father.",
    ("father_of",        False): "{x} is {y}'s daughter.",
    ("sister_of",        True):  "{x} is {y}'s sister.",
    ("sister_of",        False): "{x} is {y}'s sister.",
    ("brother_of",       True):  "{x} is {y}'s brother.",
    ("brother_of",       False): "{x} is {y}'s sister.",
    ("lives_at",         True):  "{x} lives at {y}.",
    ("lives_at",         False): "{y} lives at {x}.",
    ("frequents",        True):  "{x} often visits {y}.",
    ("frequents",        False): "{y} often visits {x}.",
}


def _sentence_for(subject: str, edge_type: str, other: str, forward: bool) -> str:
    template = _RELATION_SENTENCE.get((edge_type, forward))
    if template:
        return template.format(x=subject, y=other)
    # Fallback — readable but generic.
    verb = "is connected to" if forward else "is connected to"
    return f"{subject} {verb} {other} ({edge_type.replace('_', ' ')})."
