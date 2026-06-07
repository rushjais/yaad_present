from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ..schemas import EntityType
from ..time_window import TimeWindow, parse_time_window
from .common import item, response
from .identity import _match_persons


async def execute(query: str, meta: dict[str, Any] | None = None) -> dict:
    from ..db import fetch_events_in_window

    meta = meta or {}
    window = meta.get("time_window") or parse_time_window(query) or _default_window()
    people = await _match_persons(query, meta.get("entities") or [])
    participant_id = people[0]["id"] if people else None

    events = await fetch_events_in_window(
        window.start.astimezone(timezone.utc).isoformat(),
        window.end.astimezone(timezone.utc).isoformat(),
        participant_id,
    )
    if not events:
        subj = f" with {people[0]['name']}" if people else ""
        synthetic = {"id": f"none:{window.label}", "provenance": {}}
        return response([
            item(
                f"event:none:{window.label}:{participant_id or 'any'}",
                EntityType.event,
                f"No events{subj} {window.label}.",
                "events",
                synthetic,
                0.9,
            )
        ], f"Nothing on the calendar{subj} {window.label}.", 0.9)

    items = [
        item(f"event:{e['id']}", EntityType.event, _event_text(e), "events", e, 0.95)
        for e in events[:5]
    ]
    return response(items, confidence=0.95)


def _default_window() -> TimeWindow:
    now = datetime.now(timezone.utc)
    return TimeWindow(now, now + timedelta(days=7), "this week")


def _event_text(row: dict) -> str:
    when = _fmt_event_time(row.get("start_ts", ""))
    notes = row.get("notes") or ""
    return f"{row.get('title', 'Event')} - {when}. {notes}".strip()


def _fmt_event_time(iso: str) -> str:
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return t.strftime("%A at %-I %p")
    except Exception:
        return "soon"
