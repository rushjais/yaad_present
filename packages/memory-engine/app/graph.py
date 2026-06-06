"""
B2 — Entity/episode/edge graph + 1-hop traversal.
Entities and edges are stored in Supabase; graph traversal expands results at query time.
"""
from __future__ import annotations

from typing import Any


async def get_neighbors(ref: str, depth: int = 1) -> list[dict]:
    """
    Return entities connected to `ref` via edges, up to `depth` hops.
    Currently 1-hop only (depth > 1 reserved for future).
    """
    from .config import settings
    try:
        from supabase import create_client
        client = create_client(settings.supabase_url, settings.supabase_service_key)
        res = (
            client.table("edges")
            .select("*")
            .or_(f"from_ref.eq.{ref},to_ref.eq.{ref}")
            .execute()
        )
        edges = res.data or []
    except Exception:
        return []

    neighbor_refs = set()
    for e in edges:
        if e["from_ref"] == ref:
            neighbor_refs.add(e["to_ref"])
        else:
            neighbor_refs.add(e["from_ref"])

    return [{"ref": r, "weight": _edge_weight(edges, ref, r)} for r in neighbor_refs]


def _edge_weight(edges: list[dict], ref: str, neighbor: str) -> float:
    for e in edges:
        if (e["from_ref"] == ref and e["to_ref"] == neighbor) or \
           (e["to_ref"] == ref and e["from_ref"] == neighbor):
            return float(e.get("weight", 1.0))
    return 1.0


async def write_edge(from_ref: str, to_ref: str, edge_type: str, weight: float = 1.0) -> None:
    """Store a relationship edge in Supabase."""
    import uuid
    from .config import settings
    try:
        from supabase import create_client
        client = create_client(settings.supabase_url, settings.supabase_service_key)
        client.table("edges").upsert({
            "id": str(uuid.uuid4()),
            "from_ref": from_ref,
            "to_ref": to_ref,
            "type": edge_type,
            "weight": weight,
        }).execute()
    except Exception:
        pass


def graph_proximity_score(neighbor_weights: list[dict], ref: str) -> float:
    """Score boost for items connected to a high-weight hub. Max 1.0."""
    if not neighbor_weights:
        return 0.0
    total = sum(n["weight"] for n in neighbor_weights)
    return min(total / (len(neighbor_weights) * 2), 1.0)
