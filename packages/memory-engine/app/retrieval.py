"""
B7.1 — Retrieval v2: Moss chunks + single τ + intent routing.

What changed vs v1:
- Dropped graph expansion (no more neighbors shoveled into items[]).
- Dropped composite scoring (α·sem + β·rec + γ·sal + δ·gp). Pure Moss
  semantic. Recency lives in the captured-fact upsert timestamp;
  relationships live in the chunk text (set at seed time).
- Single τ relevance gate. Below τ → grounded=false, safe refusal.
  No more layered _OFF_TOPIC_HINTS / _IMPLICIT_ENTITY_WORDS /
  _entity_name_in_top guards.
- `answer_draft` is NOT pre-composed for semantic queries — voice agent's
  LLM composes from items[]. Temporal still pre-composes because grounded
  negatives need exact phrasing.
- Optional one-hop query expansion: if Moss's top chunk mentions an entity
  the question references that ISN'T already in our top-k, fire one more
  Moss query for it. Graph-like behavior without a graph engine.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .config import settings
from .schemas import EntityType, Provenance, RetrievedItem


# Single hard relevance gate. Moss returns ~0.70-1.00 for any query;
# legitimate matches cluster ≥0.82. Tune via CONFIDENCE_THRESHOLD env if needed.
TAU = 0.82
# Hard floor for the SECOND-hop expansion query — looser since we're
# now scoping to a known entity name.
TAU_EXPANSION = 0.78


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


def _moss_hits_to_items(hits: list[dict]) -> list[RetrievedItem]:
    out: list[RetrievedItem] = []
    for h in hits:
        meta = h.get("metadata", {}) or {}
        out.append(RetrievedItem(
            ref=h["id"],
            type=_entity_type_from_meta(meta),
            text=h.get("text", ""),
            score=float(h.get("score", 0.0)),
            provenance=_provenance_from_meta(meta),
        ))
    return out


def _refused(message: str) -> dict:
    return {
        "items": [], "grounded": False, "confidence": 0.0,
        "answer_draft": message,
    }


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

async def query_memory(text: str, lang: str = "en") -> dict:
    """v2 retrieval:
       1. understand → Intent
       2. Route temporal/remember to dedicated handlers
       3. Else: Moss query → τ filter → optional 1-hop expansion
       4. Return items + (for semantic) NO answer_draft — LLM composes
    """
    from .grounding import safe_refusal
    from .intent import understand
    from .moss_client import moss

    intent = await understand(text)

    if intent.kind in ("temporal_med", "temporal_event"):
        from .temporal import execute
        return await execute(intent, lang)

    if intent.kind == "remember":
        try:
            from .capture import capture_from_intent
            return await capture_from_intent(intent, lang)
        except ImportError:
            pass  # fall through to semantic

    # Pure semantic. Moss does the work.
    raw = await moss.query(text, top_k=8, lang=lang)
    survivors = [h for h in raw if float(h.get("score", 0.0)) >= TAU]

    # Bail before expansion: if NOTHING cleared τ, this is off-topic. Don't
    # let expansion lower the bar.
    if not survivors:
        return _refused(safe_refusal(lang))

    # Optional one-hop query expansion: if the user mentioned multiple
    # entities and one isn't represented, fire a 2nd Moss query for it.
    if intent.entities and len(intent.entities) >= 2:
        survivors = await _expand_for_missing_entities(intent.entities, survivors, lang)

    items = _moss_hits_to_items(survivors[:6])

    # Semantic answer: do NOT pre-compose. Voice agent's LLM composes the
    # spoken answer using items[]. We hand back a minimal draft string for
    # callers that don't run an LLM (smoke tests, dashboard).
    minimal_draft = items[0].text  # first chunk; LLM downstream will rewrite

    return {
        "items": [i.model_dump() for i in items],
        "grounded": True,
        "confidence": round(items[0].score, 3),
        "answer_draft": minimal_draft,
    }


# ---------------------------------------------------------------------------
# One-hop query expansion
# ---------------------------------------------------------------------------

async def _expand_for_missing_entities(entities: list[str],
                                        existing: list[dict],
                                        lang: str) -> list[dict]:
    """If the question mentions multiple entities (e.g. 'Did Leo get into
    Stanford?'), make sure all of them are represented in the results by
    firing a focused Moss query for any that aren't.
    """
    from .moss_client import moss

    have_text = " ".join((h.get("text") or "").lower() for h in existing)
    out = list(existing)
    seen_ids = {h["id"] for h in existing}

    for ent in entities[1:]:  # skip the first — it's almost always covered
        if ent.lower() in have_text:
            continue
        extra = await moss.query(ent, top_k=3, lang=lang)
        for e in extra:
            if e["id"] in seen_ids:
                continue
            if float(e.get("score", 0.0)) >= TAU_EXPANSION:
                out.append(e)
                seen_ids.add(e["id"])

    out.sort(key=lambda h: float(h.get("score", 0.0)), reverse=True)
    return out
