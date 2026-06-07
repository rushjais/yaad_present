from __future__ import annotations

from typing import Any


def render(entity_type: str, row: dict, edges: Any | None = None) -> str:
    """Canonical row text. No LLM, no cross-person fact synthesis."""
    if entity_type == "person":
        return _person(row)
    if entity_type == "place":
        return _place(row)
    if entity_type == "medication":
        return _medication(row)
    if entity_type == "event":
        return _event(row)
    if entity_type == "story":
        return _story(row)
    if entity_type == "episode":
        return _episode(row)
    if entity_type == "med_log":
        return _med_log(row)
    return ""


def _join(parts: list[str]) -> str:
    clean = [p.strip().rstrip(".") for p in parts if p and p.strip()]
    if not clean:
        return ""
    return ". ".join(clean) + "."


def _person(row: dict) -> str:
    aliases = row.get("aliases") or []
    parts = [str(row.get("name") or "")]
    relationship = row.get("relationship")
    if relationship:
        parts.append(str(relationship))
    if row.get("notes"):
        parts.append(str(row["notes"]))
    if aliases:
        parts.append(f"Also called {', '.join(str(a) for a in aliases)}")
    prefs = row.get("preferences") or {}
    if prefs:
        parts.append("Preferences: " + "; ".join(f"{k}: {v}" for k, v in sorted(prefs.items())))
    return _join(parts)


def _place(row: dict) -> str:
    return _join([str(row.get("name") or ""), str(row.get("kind") or ""), str(row.get("notes") or "")])


def _medication(row: dict) -> str:
    return _join([str(row.get("name") or ""), "Amma's medication", str(row.get("notes") or "")])


def _event(row: dict) -> str:
    return _join([str(row.get("title") or ""), str(row.get("kind") or ""), str(row.get("notes") or "")])


def _story(row: dict) -> str:
    title = str(row.get("title") or "")
    text = str(row.get("text") or "")
    return f"Story: {title}. {text}".strip()


def _episode(row: dict) -> str:
    title = str(row.get("title") or "")
    summary = str(row.get("summary") or "")
    return _join([title, summary])


def _med_log(row: dict) -> str:
    return _join([f"Medication log {row.get('id', '')}", str(row.get("taken_ts") or ""), str(row.get("source") or "")])
