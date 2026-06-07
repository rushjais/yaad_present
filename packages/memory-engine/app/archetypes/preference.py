from __future__ import annotations

import json
import os
import re
from typing import Any

from ..schemas import EntityType
from .common import item, refused, response
from .identity import _match_persons

RECOMMENDED_KEYS = [
    "music", "food", "drink", "hobby", "activity", "place",
    "color", "tv_show", "book", "study", "work", "pet",
]


def _load_aliases() -> dict:
    path = os.path.join(os.path.dirname(__file__), "..", "data", "preference_keys.json")
    with open(path) as f:
        return json.load(f)


async def execute(query: str, meta: dict[str, Any] | None = None) -> dict:
    meta = meta or {}
    key = meta.get("preference_key") or preference_key_for_query(query)
    person = await _subject_person(query, meta)
    if not person:
        return refused()
    prefs = person.get("preferences") or {}
    if not prefs:
        return refused(f"I don't know {person.get('name', 'their')} preferences yet.")

    if key and key in prefs:
        text = str(prefs[key])
        ref = f"person:{person['id']}:preferences:{key}"
        return response([
            item(ref, EntityType.person, text, "persons.preferences", person, 1.0)
        ], f"{person.get('name', 'Their')} {key} is {text}.", 1.0)

    if key in {"hobby", "activity"} and (prefs.get("hobby") or prefs.get("activity")):
        actual_key = "hobby" if prefs.get("hobby") else "activity"
        text = str(prefs[actual_key])
        return response([
            item(f"person:{person['id']}:preferences:{actual_key}", EntityType.person, text, "persons.preferences", person, 0.95)
        ], confidence=0.95)

    if key:
        return refused(f"I don't know {person.get('name', 'their')}'s favorite {key}.")

    items = [
        item(f"person:{person['id']}:preferences:{k}", EntityType.person, str(v), "persons.preferences", person, 0.95)
        for k, v in sorted(prefs.items())
    ]
    return response(items, confidence=0.95)


def preference_key_for_query(query: str) -> str | None:
    data = _load_aliases()
    q = query.lower()
    aliases = data.get("aliases") or {}
    for key, words in aliases.items():
        for word in words:
            if re.search(r"(?<!\w)" + re.escape(str(word).lower()) + r"(?!\w)", q):
                return key
    return None


async def _subject_person(query: str, meta: dict[str, Any]) -> dict | None:
    people = await _match_persons(query, meta.get("entities") or [])
    if people:
        return people[0]
    from ..db import fetch_persons
    for person in await fetch_persons():
        if str(person.get("relationship") or "").lower() == "self" or str(person.get("name") or "").lower() == "amma":
            return person
    return None
