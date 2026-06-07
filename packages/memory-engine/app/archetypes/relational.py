from __future__ import annotations

import re
from typing import Any

from .. import chunks
from ..edges_cache import edges_cache
from ..schemas import EntityType
from .common import item, refused, response
from .identity import _match_persons


async def execute(query: str, meta: dict[str, Any] | None = None) -> dict:
    meta = meta or {}
    q = query.lower()
    patient_ref = await edges_cache.patient_ref()
    if not patient_ref:
        return refused()

    if "family" in q:
        refs = []
        await edges_cache.load()
        for edge in edges_cache.edges:
            if edge.get("to_ref") == patient_ref and str(edge.get("from_ref", "")).startswith("person:"):
                refs.append(edge["from_ref"])
        return await _items_for_refs(refs)

    relation_word = meta.get("relationship_word") or await _relation_word(q)
    if relation_word:
        if relation_word in {"address", "home"}:
            refs = await edges_cache.refs_from(patient_ref, "lives_at")
            return await _items_for_refs(refs)
        refs = await edges_cache.refs_for_relation(patient_ref, relation_word)
        return await _items_for_refs(refs)

    people = await _match_persons(query, meta.get("entities") or [])
    if people:
        refs = [f"person:{p['id']}" for p in people]
        items = []
        for ref in refs:
            row = await edges_cache.row_for_ref(ref)
            if row:
                items.append(item(ref, EntityType.person, chunks.render("person", row), "persons", row, 0.95))
        return response(items)

    return refused()


async def _relation_word(query_lower: str) -> str | None:
    words = await edges_cache.relation_words()
    for word in words:
        if re.search(r"(?<!\w)" + re.escape(word.lower()) + r"(?!\w)", query_lower):
            return word
    return None


async def _items_for_refs(refs: list[str]) -> dict:
    out = []
    seen = set()
    for ref in refs:
        if ref in seen:
            continue
        seen.add(ref)
        row = await edges_cache.row_for_ref(ref)
        if not row:
            continue
        if ref.startswith("person:"):
            out.append(item(ref, EntityType.person, chunks.render("person", row), "persons", row, 1.0))
        elif ref.startswith("place:"):
            out.append(item(ref, EntityType.place, chunks.render("place", row), "places", row, 1.0))
    return response(out)
