from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .schemas import TimelineBlock, TimelineResponse


async def query_temporal(text: str, lang: str = "en") -> dict:
    from .router import dispatch

    return await dispatch(text, lang)


async def get_timeline(date_str: str | None = None) -> TimelineResponse:
    from .db import fetch_med_logs_today, fetch_upcoming_events

    blocks: list[TimelineBlock] = []
    try:
        logs = await fetch_med_logs_today()
        for log in logs:
            blocks.append(TimelineBlock(
                ts=datetime.fromisoformat(log["taken_ts"].replace("Z", "+00:00")),
                type="med_log",
                title="Medication taken",
                summary=f"Pill taken. Source: {log.get('source', 'unknown')}",
                entity_refs=[f"med_log:{log['id']}"],
            ))
    except Exception:
        pass

    try:
        cutoff = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
        events = await fetch_upcoming_events(cutoff)
        for event in events:
            blocks.append(TimelineBlock(
                ts=datetime.fromisoformat(event["start_ts"].replace("Z", "+00:00")),
                type="event",
                title=event.get("title", "Event"),
                summary=event.get("notes", ""),
                entity_refs=[f"event:{event['id']}"],
            ))
    except Exception:
        pass

    blocks.sort(key=lambda b: b.ts)
    return TimelineResponse(blocks=blocks)
