from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Literal

from .time_window import TimeWindow, parse_time_window

Archetype = Literal[
    "identity",
    "relational",
    "temporal_med",
    "temporal_event",
    "preference",
    "episodic",
    "remember",
]


@dataclass
class Route:
    archetype: Archetype
    entities: list[str] = field(default_factory=list)
    relationship_word: str | None = None
    preference_key: str | None = None
    time_window: TimeWindow | None = None
    source: str = "regex"

    def meta(self) -> dict:
        return {
            "entities": self.entities,
            "relationship_word": self.relationship_word,
            "preference_key": self.preference_key,
            "time_window": self.time_window,
            "source": self.source,
        }


def _data(name: str) -> dict:
    path = os.path.join(os.path.dirname(__file__), "data", name)
    with open(path) as f:
        return json.load(f)


async def classify(query: str) -> Route:
    text = query.strip()
    q = text.lower()
    tw = parse_time_window(text)
    entities = await _known_entities(text)
    aliases = _data("router_aliases.json")

    if _force_refusal(q):
        return Route("episodic", entities=entities, time_window=tw, source="force_refuse")

    if _has_any(q, aliases["remember_phrases"]):
        return Route("remember", entities=entities, time_window=tw)

    if _looks_medical(q, aliases):
        return Route("temporal_med", entities=entities, time_window=tw)

    if _looks_event(q, aliases, tw, entities):
        return Route("temporal_event", entities=entities, time_window=tw)

    relationship_word = await _relationship_word(q)
    if "to me" in q and entities:
        return Route("relational", entities=entities, relationship_word=relationship_word, time_window=tw)

    if "family" in q:
        return Route("relational", entities=entities, relationship_word=relationship_word, time_window=tw)

    if relationship_word and _looks_relational(q):
        return Route("relational", entities=entities, relationship_word=relationship_word, time_window=tw)

    pref_key = _preference_key(q)
    looks_pref = _looks_preference(q)
    if (pref_key and (looks_pref or _is_standalone_preference_alias(q, pref_key))) or (looks_pref and pref_key):
        return Route("preference", entities=entities, preference_key=pref_key, time_window=tw)

    if "story" in q or "remember when" in q:
        return Route("episodic", entities=entities, time_window=tw)

    if entities or _looks_identity(q, aliases):
        return Route("identity", entities=entities, time_window=tw)

    slow = await _llm_classify_or_episodic(text, entities, tw)
    return slow


async def dispatch(query: str, lang: str = "en") -> dict:
    route = await classify(query)
    if route.archetype == "identity":
        from .archetypes.identity import execute
        result = await execute(query, route.meta())
        if not result.get("grounded") and route.entities:
            from .archetypes.episodic import execute as episodic_execute
            return await episodic_execute(query, route.meta())
        return result
    elif route.archetype == "relational":
        from .archetypes.relational import execute
    elif route.archetype == "temporal_med":
        from .archetypes.temporal_med import execute
    elif route.archetype == "temporal_event":
        from .archetypes.temporal_event import execute
    elif route.archetype == "preference":
        from .archetypes.preference import execute
    elif route.archetype == "remember":
        from .capture import capture_from_transcript
        result = await capture_from_transcript(query)
        return {
            "items": [
                {
                    "ref": ref,
                    "type": "episode",
                    "text": query,
                    "score": 1.0,
                    "provenance": {
                        "source": "capture",
                        "added_by": "voice_agent",
                        "added_ts": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
                    },
                }
                for ref in result.created_refs
            ],
            "grounded": bool(result.created_refs),
            "confidence": 1.0 if result.created_refs else 0.0,
            "answer_draft": "Got it - I'll remember that." if result.created_refs else None,
        }
    else:
        from .archetypes.episodic import execute
    return await execute(query, route.meta())


async def _known_entities(query: str) -> list[str]:
    from .db import fetch_persons, fetch_places

    q_norm = _norm(query)
    out: list[str] = []
    seen: set[str] = set()
    for row in [*(await fetch_persons()), *(await fetch_places())]:
        names = [row.get("name"), *(row.get("aliases") or [])]
        for name in names:
            value = str(name or "")
            if value and _contains(q_norm, _norm(value)) and value.lower() not in seen:
                out.append(value)
                seen.add(value.lower())
                break
    for match in re.finditer(r"\b[A-Z][A-Za-z_]*(?:\s+[A-Z][A-Za-z_]*){0,2}\b", query):
        value = match.group(0)
        if value.lower() not in {"who", "what", "when", "where", "why", "how", "tell"} and value.lower() not in seen:
            out.append(value)
            seen.add(value.lower())
    return out


async def _relationship_word(q: str) -> str | None:
    from .edges_cache import edges_cache

    for word in await edges_cache.relation_words():
        if _contains(q, word.lower()):
            return word
    return None


def _preference_key(q: str) -> str | None:
    from .archetypes.preference import preference_key_for_query

    return preference_key_for_query(q)


def _looks_medical(q: str, aliases: dict) -> bool:
    return _has_any(q, aliases["medication_words"]) and (
        _has_any(q, aliases["medication_query_words"]) or "?" in q
    )


def _looks_event(q: str, aliases: dict, tw: TimeWindow | None, entities: list[str]) -> bool:
    return _has_any(q, aliases["event_words"]) and (tw is not None or bool(entities) or "calendar" in q or "schedule" in q)


def _looks_relational(q: str) -> bool:
    return bool(re.search(r"\b(my|her|his|amma'?s|to me|family)\b", q))


def _looks_preference(q: str) -> bool:
    return bool(re.search(r"\b(favorite|favourite|like|likes|enjoy|enjoys|eat|drink|listen|watch|read|study)\b", q))


def _is_standalone_preference_alias(q: str, key: str) -> bool:
    compact = q.strip(" ?.!")
    return key in {"music", "food", "drink", "hobby", "study"} and len(compact.split()) <= 3


def _force_refusal(q: str) -> bool:
    return bool(re.search(r"\b(meaning of life|weather|president of the united states|2\s*\+\s*2)\b", q))


def _looks_identity(q: str, aliases: dict) -> bool:
    return _has_any(q, aliases["identity_words"]) or bool(re.search(r"\b(address|allergic|allergy)\b", q))


def _has_any(q: str, words: list[str]) -> bool:
    return any(_contains(q, str(word).lower()) for word in words)


def _contains(haystack: str, needle: str) -> bool:
    if not needle:
        return False
    return re.search(r"(?<!\w)" + re.escape(needle) + r"(?!\w)", haystack) is not None


def _norm(value: str) -> str:
    return " ".join(value.replace("_", " ").lower().split())


async def _llm_classify_or_episodic(text: str, entities: list[str], tw: TimeWindow | None) -> Route:
    from .config import settings

    if not settings.groq_api_key:
        return Route("episodic", entities=entities, time_window=tw, source="fallback")

    system = """Classify a query for a dementia memory engine.
Return strict JSON: {"archetype": one of ["identity","relational","temporal_med","temporal_event","preference","episodic","remember"]}.
Only classify. Never answer the query and never produce facts."""
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=settings.groq_api_key)
        resp = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=80,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        archetype = data.get("archetype")
        if archetype in {"identity", "relational", "temporal_med", "temporal_event", "preference", "episodic", "remember"}:
            return Route(archetype, entities=entities, time_window=tw, source="llm")
    except Exception:
        pass
    return Route("episodic", entities=entities, time_window=tw, source="fallback")
