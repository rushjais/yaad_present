"""
B4 — Temporal intent routing.
"pills today" → today's med_log, not a semantic match on "pills".
"is X coming" → upcoming events.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from .grounding import assess_grounding, safe_refusal
from .schemas import EntityType, Provenance, RetrievedItem, TimelineResponse, TimelineBlock

# Simple keyword signals — good enough for demo; extend if needed
_TODAY_MEDS = re.compile(
    r"(pill|pills|medicine|medication|tablet|dose|med)\b.*?(today|this morning|took|take)",
    re.IGNORECASE,
)
_TOOK_MEDS = re.compile(
    r"(did i|have i).{0,20}(take|took|had).{0,20}(pill|medicine|medication|tablet|dose)",
    re.IGNORECASE,
)
_UPCOMING = re.compile(
    r"(is|are|when).{0,30}(coming|visiting|visit|arrive|appointment|doctor|sarah|leo)",
    re.IGNORECASE,
)


def _detect_intent(text: str) -> str:
    if _TODAY_MEDS.search(text) or _TOOK_MEDS.search(text):
        return "pills_today"
    if _UPCOMING.search(text):
        return "upcoming_event"
    return "general"


async def query_temporal(text: str, lang: str = "en") -> dict:
    intent = _detect_intent(text)

    if intent == "pills_today":
        return await _handle_pills_today(lang)
    if intent == "upcoming_event":
        return await _handle_upcoming(text, lang)

    # fallback to semantic retrieval
    from .retrieval import query_memory
    return await query_memory(text, lang)


async def _handle_pills_today(lang: str) -> dict:
    from .db import fetch_med_logs_today
    try:
        logs = await fetch_med_logs_today()
    except Exception:
        logs = []

    now = datetime.now(timezone.utc)
    prov = Provenance(source="med_log_table", added_by="system", added_ts=now)

    if logs:
        taken_ts = logs[0].get("taken_ts", "")
        try:
            t = datetime.fromisoformat(taken_ts.replace("Z", "+00:00"))
            time_str = t.strftime("%I:%M %p").lstrip("0")
        except Exception:
            time_str = "earlier today"

        item = RetrievedItem(
            ref=f"med_log:{logs[0]['id']}",
            type=EntityType.med_log,
            text=f"Pill taken at {time_str} today.",
            score=1.0,
            provenance=prov,
        )
        draft_en = f"Yes, you took your pill at {time_str} this morning."
        draft_hi = f"Haan, aapne aaj subah {time_str} baje dawai li thi."
        return {
            "items": [item.model_dump()],
            "grounded": True,
            "confidence": 1.0,
            "answer_draft": draft_hi if lang.startswith("hi") else draft_en,
        }
    else:
        item = RetrievedItem(
            ref="med_log:none_today",
            type=EntityType.med_log,
            text="No pill logged yet today.",
            score=0.95,
            provenance=prov,
        )
        draft_en = "Not yet today. Would you like me to remind you?"
        draft_hi = "Aaj abhi tak nahi li. Kya aapko yaad dilaaun?"
        return {
            "items": [item.model_dump()],
            "grounded": True,
            "confidence": 0.95,
            "answer_draft": draft_hi if lang.startswith("hi") else draft_en,
        }


async def _handle_upcoming(text: str, lang: str) -> dict:
    from .db import fetch_upcoming_events
    try:
        cutoff = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        events = await fetch_upcoming_events(cutoff)
    except Exception:
        events = []

    now = datetime.now(timezone.utc)
    prov = Provenance(source="events_table", added_by="system", added_ts=now)

    if not events:
        return {
            "items": [],
            "grounded": False,
            "confidence": 0.0,
            "answer_draft": safe_refusal(lang),
        }

    items = []
    for e in events[:3]:
        try:
            ts = datetime.fromisoformat(e["start_ts"].replace("Z", "+00:00"))
            time_str = ts.strftime("%A at %-I %p")
        except Exception:
            time_str = e.get("start_ts", "soon")

        items.append(RetrievedItem(
            ref=f"event:{e['id']}",
            type=EntityType.event,
            text=f"{e['title']} — {time_str}.",
            score=0.95,
            provenance=prov,
        ))

    drafts = [i.text for i in items]
    return {
        "items": [i.model_dump() for i in items],
        "grounded": True,
        "confidence": 0.95,
        "answer_draft": " ".join(drafts),
    }


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
        for e in events:
            blocks.append(TimelineBlock(
                ts=datetime.fromisoformat(e["start_ts"].replace("Z", "+00:00")),
                type="event",
                title=e.get("title", "Event"),
                summary=e.get("notes", ""),
                entity_refs=[f"event:{e['id']}"],
            ))
    except Exception:
        pass

    blocks.sort(key=lambda b: b.ts)
    return TimelineResponse(blocks=blocks)
