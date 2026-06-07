from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any


def _data_path(name: str) -> str:
    return os.path.join(os.path.dirname(__file__), "data", name)


def load_relationship_words() -> dict[str, dict[str, str]]:
    with open(_data_path("relationship_words.json")) as f:
        return json.load(f)


@dataclass
class EdgesCache:
    edges: list[dict] = field(default_factory=list)
    persons_by_ref: dict[str, dict] = field(default_factory=dict)
    places_by_ref: dict[str, dict] = field(default_factory=dict)
    relationship_words: dict[str, dict[str, str]] = field(default_factory=load_relationship_words)
    loaded: bool = False

    async def load(self, *, force: bool = False) -> None:
        if self.loaded and not force:
            return
        from .db import fetch_edges, fetch_persons, fetch_places

        persons = await fetch_persons()
        places = await fetch_places()
        self.edges = await fetch_edges()
        self.persons_by_ref = {f"person:{p['id']}": p for p in persons}
        self.places_by_ref = {f"place:{p['id']}": p for p in places}
        self.relationship_words = load_relationship_words()
        self.loaded = True

    async def patient_ref(self) -> str | None:
        await self.load()
        for ref, row in self.persons_by_ref.items():
            if str(row.get("relationship") or "").lower() == "self":
                return ref
            if str(row.get("name") or "").lower() == "amma":
                return ref
        return None

    async def name_for_ref(self, ref: str) -> str:
        await self.load()
        row = self.persons_by_ref.get(ref) or self.places_by_ref.get(ref) or {}
        return str(row.get("name") or row.get("title") or ref)

    async def row_for_ref(self, ref: str) -> dict | None:
        await self.load()
        return self.persons_by_ref.get(ref) or self.places_by_ref.get(ref)

    async def refs_for_relation(self, owner_ref: str, relationship_word: str) -> list[str]:
        await self.load()
        spec = self.relationship_words.get(relationship_word.lower())
        if not spec:
            return []
        edge_type = spec["edge_type"]
        return [e["from_ref"] for e in self.edges if e.get("type") == edge_type and e.get("to_ref") == owner_ref]

    async def refs_from(self, from_ref: str, edge_type: str) -> list[str]:
        await self.load()
        return [e["to_ref"] for e in self.edges if e.get("from_ref") == from_ref and e.get("type") == edge_type]

    async def relations_between(self, left_ref: str, right_ref: str) -> list[dict]:
        await self.load()
        return [
            e for e in self.edges
            if (e.get("from_ref") == left_ref and e.get("to_ref") == right_ref)
            or (e.get("from_ref") == right_ref and e.get("to_ref") == left_ref)
        ]

    async def relation_words(self) -> list[str]:
        await self.load()
        words = set(self.relationship_words.keys())
        for edge in self.edges:
            edge_type = edge.get("type")
            for word, spec in self.relationship_words.items():
                if spec.get("edge_type") == edge_type:
                    words.add(word)
        return sorted(words, key=len, reverse=True)


edges_cache = EdgesCache()
