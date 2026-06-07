from __future__ import annotations

from datetime import datetime
from typing import Any

from ..config import settings
from ..schemas import EntityType, Provenance, RetrievedItem
from .common import refused, response


async def execute(query: str, meta: dict[str, Any] | None = None) -> dict:
    if (meta or {}).get("source") == "force_refuse":
        return refused()

    from ..moss_client import moss

    hits = await moss.query(query, top_k=8)
    survivors = []
    for hit in hits:
        md = hit.get("metadata") or {}
        if md.get("type") == "story":
            pass
        elif md.get("type") == "episode" and md.get("kind") == "captured_fact":
            pass
        else:
            continue
        if float(hit.get("score", 0.0)) >= settings.episodic_tau:
            survivors.append(hit)

    if not survivors:
        return refused()

    items = []
    for hit in survivors[:6]:
        md = hit.get("metadata") or {}
        entity_type = EntityType.episode if md.get("type") == "episode" else EntityType.story
        items.append(RetrievedItem(
            ref=hit["id"],
            type=entity_type,
            text=hit.get("text") or "",
            score=float(hit.get("score", 0.0)),
            provenance=_prov(md, "episodes" if entity_type == EntityType.episode else "stories"),
        ))
    return response(items, confidence=items[0].score)


def _prov(meta: dict, source: str) -> Provenance:
    raw = meta.get("provenance") or {}
    if not isinstance(raw, dict):
        raw = {}
    added_ts = raw.get("added_ts") or "2025-01-01T00:00:00+00:00"
    return Provenance(
        source=source,
        added_by=str(raw.get("added_by") or "system"),
        added_ts=datetime.fromisoformat(str(added_ts).replace("Z", "+00:00")),
    )
