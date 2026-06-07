from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ..grounding import safe_refusal
from ..schemas import EntityType, Provenance, RetrievedItem


def provenance(row: dict | None, source: str) -> Provenance:
    raw = (row or {}).get("provenance") or {}
    if not isinstance(raw, dict):
        raw = {}
    added_ts = raw.get("added_ts") or datetime.now(timezone.utc).isoformat()
    return Provenance(
        source=source,
        added_by=str(raw.get("added_by") or "system"),
        added_ts=datetime.fromisoformat(str(added_ts).replace("Z", "+00:00")),
    )


def item(ref: str, entity_type: EntityType, text: str, source: str, row: dict | None = None,
         score: float = 1.0) -> RetrievedItem:
    return RetrievedItem(
        ref=ref,
        type=entity_type,
        text=text,
        score=score,
        provenance=provenance(row, source),
    )


def response(items: list[RetrievedItem], answer: str | None = None,
             confidence: float | None = None) -> dict[str, Any]:
    if not items:
        return refused()
    conf = confidence if confidence is not None else max(i.score for i in items)
    return {
        "items": [i.model_dump() for i in items],
        "grounded": True,
        "confidence": round(float(conf), 3),
        "answer_draft": answer if answer is not None else " ".join(i.text for i in items[:3]),
    }


def refused(message: str | None = None) -> dict[str, Any]:
    return {
        "items": [],
        "grounded": False,
        "confidence": 0.0,
        "answer_draft": message or safe_refusal("en"),
    }


def norm(value: str) -> str:
    return " ".join(value.replace("_", " ").lower().split())
