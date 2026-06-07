from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import settings
from .schemas import TimelineBlock, TimelineResponse


async def query_temporal(text: str, lang: str = "en") -> dict:
    from .router import dispatch

    return await dispatch(text, lang)


async def get_timeline(date_str: str | None = None) -> TimelineResponse:
    from .db import fetch_events_in_window, fetch_med_logs_in_window

    start_utc, end_utc = _timeline_window(date_str)

    blocks: list[TimelineBlock] = []
    try:
        logs = await fetch_med_logs_in_window(start_utc.isoformat(), end_utc.isoformat())
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
        events = await fetch_events_in_window(start_utc.isoformat(), end_utc.isoformat())
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


def _timeline_window(date_str: str | None) -> tuple[datetime, datetime]:
    tz = ZoneInfo(settings.patient_tz)
    if date_str:
        day = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        day = datetime.now(tz).date()

    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = datetime.combine(day, time.max, tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)
