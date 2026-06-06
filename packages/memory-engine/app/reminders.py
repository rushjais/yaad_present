"""
B5 — Proactive reminders: /reminders/due
Polls medications (schedule_rrule) and upcoming events to find what's due now.
Voice agent scheduler calls this; same grounded TTS path.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .schemas import ReminderItem, RemindersResponse


async def get_due_reminders(ts_str: str | None = None) -> RemindersResponse:
    now = (
        datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        if ts_str
        else datetime.now(timezone.utc)
    )
    window_end = now + timedelta(minutes=30)

    due: list[ReminderItem] = []

    try:
        due += await _medication_reminders(now, window_end)
    except Exception:
        pass

    try:
        due += await _event_reminders(now, window_end)
    except Exception:
        pass

    return RemindersResponse(due=due)


async def _medication_reminders(
    now: datetime, window_end: datetime
) -> list[ReminderItem]:
    from .config import settings
    from supabase import create_client
    from dateutil.rrule import rrulestr

    client = create_client(settings.supabase_url, settings.supabase_service_key)
    res = client.table("medications").select("*").execute()
    meds = res.data or []

    items = []
    for med in meds:
        rrule_str = med.get("schedule_rrule", "")
        if not rrule_str:
            continue
        try:
            rule = rrulestr(rrule_str, dtstart=now.replace(hour=0, minute=0, second=0))
            occurrences = list(rule.between(now, window_end, inc=True))
        except Exception:
            continue

        if occurrences:
            items.append(ReminderItem(
                kind="medication",
                text=f"Time for your {med['name']}.",
                ref=f"medication:{med['id']}",
            ))

    return items


async def _event_reminders(
    now: datetime, window_end: datetime
) -> list[ReminderItem]:
    from .db import fetch_upcoming_events

    events = await fetch_upcoming_events(window_end.isoformat())
    items = []
    for e in events:
        try:
            ts = datetime.fromisoformat(e["start_ts"].replace("Z", "+00:00"))
        except Exception:
            continue
        if now <= ts <= window_end:
            items.append(ReminderItem(
                kind="event",
                text=f"{e['title']} is coming up soon.",
                ref=f"event:{e['id']}",
            ))

    return items
