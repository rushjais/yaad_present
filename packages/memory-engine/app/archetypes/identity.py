from __future__ import annotations

import re
from typing import Any

from .. import chunks
from ..edges_cache import edges_cache
from ..schemas import EntityType
from .common import item, norm, refused, response

_QUESTION_WORDS = {
    "who", "what", "when", "where", "why", "how", "tell", "remind", "about",
    "amma", "did", "have", "is", "are", "the", "my", "her", "his", "does",
}


async def execute(query: str, meta: dict[str, Any] | None = None) -> dict:
    meta = meta or {}
    q = query.lower()

    if any(word in q for word in ("address", "home", "where do i live")) and not meta.get("entities"):
        result = await _patient_home()
        if result:
            return response([result], result.text)

    person_matches = await _match_persons(query, meta.get("entities") or [])
    if person_matches:
        items = [
            item(
                ref=f"person:{row['id']}",
                entity_type=EntityType.person,
                text=chunks.render("person", row),
                source="persons",
                row=row,
                score=1.0 if len(person_matches) == 1 else 0.88,
            )
            for row in person_matches
        ]
        return response(items, confidence=items[0].score)

    place_matches = await _match_places(query, meta.get("entities") or [])
    if place_matches:
        items = [
            item(
                ref=f"place:{row['id']}",
                entity_type=EntityType.place,
                text=chunks.render("place", row),
                source="places",
                row=row,
                score=1.0 if len(place_matches) == 1 else 0.88,
            )
            for row in place_matches
        ]
        return response(items, confidence=items[0].score)

    return refused()


async def _match_persons(query: str, candidates: list[str]) -> list[dict]:
    from ..db import fetch_persons

    rows = await fetch_persons()
    names = [*candidates, *_proper_candidates(query)]
    out: list[dict] = []
    seen: set[str] = set()
    q_norm = norm(query)
    for row in rows:
        aliases = [row.get("name"), *(row.get("aliases") or [])]
        row_hit = False
        for alias in aliases:
            alias_norm = norm(str(alias or ""))
            if not alias_norm:
                continue
            if alias_norm in {norm(n) for n in names} or _contains_norm(q_norm, alias_norm):
                row_hit = True
                break
        if row_hit and row["id"] not in seen:
            out.append(row)
            seen.add(row["id"])
    return out


async def _match_places(query: str, candidates: list[str]) -> list[dict]:
    from ..db import fetch_places

    rows = await fetch_places()
    names = [*candidates, *_proper_candidates(query)]
    q_norm = norm(query)
    out: list[dict] = []
    for row in rows:
        name = norm(str(row.get("name") or ""))
        if name and (name in {norm(n) for n in names} or _contains_norm(q_norm, name)):
            out.append(row)
        elif "park" in q_norm and "park" in name:
            out.append(row)
        elif "home" in q_norm and str(row.get("kind") or "").lower() == "home":
            out.append(row)
    return out


def _proper_candidates(query: str) -> list[str]:
    out = []
    for match in re.finditer(r"\b[A-Z][A-Za-z_]*(?:\s+[A-Z][A-Za-z_]*){0,2}\b", query):
        value = match.group(0)
        if norm(value) not in _QUESTION_WORDS:
            out.append(value)
    return out


def _contains_norm(haystack: str, needle: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", haystack) is not None


async def _patient_home():
    patient_ref = await edges_cache.patient_ref()
    if not patient_ref:
        return None
    place_refs = await edges_cache.refs_from(patient_ref, "lives_at")
    if not place_refs:
        return None
    row = await edges_cache.row_for_ref(place_refs[0])
    if not row:
        return None
    return item(f"place:{row['id']}", EntityType.place, chunks.render("place", row), "places", row, 1.0)
