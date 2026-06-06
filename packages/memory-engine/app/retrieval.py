"""
B2 — Composed retrieval scoring.
score = α·semantic + β·recency + γ·salience + δ·graph_proximity
recency = exp(−λ·Δt_hours)

Every result carries provenance. Ungrounded → safe refusal via grounding.py.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from .config import settings
from .schemas import EntityType, Provenance, RetrievedItem


def _recency_score(added_ts: str | None) -> float:
    if not added_ts:
        return 0.5
    try:
        ts = datetime.fromisoformat(added_ts.replace("Z", "+00:00"))
        delta_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        return math.exp(-settings.recency_lambda * delta_hours)
    except Exception:
        return 0.5


def _salience(metadata: dict) -> float:
    """Simple salience: persons and med_logs are high-salience for this patient."""
    kind = metadata.get("type", "")
    if kind in ("person", "med_log"):
        return 1.0
    if kind in ("medication", "episode"):
        return 0.8
    return 0.5


def _compose_score(
    semantic: float,
    recency: float,
    salience: float,
    graph_prox: float,
) -> float:
    s = settings
    return (
        s.alpha * semantic
        + s.beta * recency
        + s.gamma * salience
        + s.delta * graph_prox
    )


async def query_memory(text: str, lang: str = "en") -> dict:
    """
    Full retrieval pipeline:
    1. Moss semantic search
    2. 1-hop graph expansion
    3. Composed scoring + sort
    4. Grounding check
    Returns MemoryQueryResponse-compatible dict.
    """
    from .moss_client import moss
    from .graph import get_neighbors, graph_proximity_score
    from .grounding import assess_grounding

    raw = await moss.query(text, top_k=15, lang=lang)

    items: list[RetrievedItem] = []
    for r in raw:
        meta = r.get("metadata", {})
        prov_raw = meta.get("provenance", {})
        provenance = Provenance(
            source=prov_raw.get("source", "unknown"),
            added_by=prov_raw.get("added_by", "unknown"),
            added_ts=datetime.fromisoformat(
                prov_raw.get("added_ts", "2025-01-01T00:00:00+00:00").replace("Z", "+00:00")
            ),
        )

        neighbors = await get_neighbors(r["id"])
        gp = graph_proximity_score(neighbors, r["id"])
        recency = _recency_score(prov_raw.get("added_ts"))
        salience = _salience(meta)
        score = _compose_score(r.get("score", 0.0), recency, salience, gp)

        items.append(RetrievedItem(
            ref=r["id"],
            type=EntityType(meta.get("type", "episode")),
            text=r.get("text", ""),
            score=score,
            provenance=provenance,
        ))

    items.sort(key=lambda x: x.score, reverse=True)
    top = items[:5]

    return assess_grounding(top, text)
