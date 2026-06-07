"""
B7 — Temporal intent routing on top of `intent.understand`.

What changed vs Gate-1:
- No regex routing inside this file — defer to `intent.understand` which
  emits a typed `Intent`. This file is now just *executors* per intent kind.
- Per-medication routing: "heart pill" → filter med_logs by that med's id.
  Previously every "did I take my X" query returned the first row regardless.
- Grounded negatives: "you haven't taken your heart pill yet today" is
  grounded on the *absence* of a row, not a hallucination.
- Time-window aware: "did I take my heart pill yesterday" filters logs to
  yesterday's window; "is Sarah coming this week" filters events.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from .grounding import assess_grounding, safe_refusal
from .intent import Intent, understand
from .schemas import EntityType, Provenance, RetrievedItem, TimelineResponse, TimelineBlock
from .time_window import TimeWindow, parse_time_window


# ---------------------------------------------------------------------------
# Medication hint → row resolution
# ---------------------------------------------------------------------------

# Substring matchers — case-insensitive substring of medications.name.
_MED_HINT_TO_NEEDLE = {
    "heart pill":          ["heart", "metoprolol"],
    "blood pressure pill": ["blood pressure", "amlodipine", "bp"],
}


async def _resolve_medication(hint: Optional[str]) -> Optional[dict]:
    """Return the medications row best matching the hint, or None."""
    if not hint:
        return None
    from .db import fetch_medications
    meds = await fetch_medications()
    needles = _MED_HINT_TO_NEEDLE.get(hint, [hint])
    for needle in needles:
        n = needle.lower()
        for m in meds:
            if n in (m.get("name") or "").lower():
                return m
    return None


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

async def query_temporal(text: str, lang: str = "en") -> dict:
    """Used by `/memory/temporal`. Understand → route to executor."""
    intent = await understand(text)
    return await execute(intent, lang)


async def execute(intent: Intent, lang: str = "en") -> dict:
    """Dispatch a pre-classified Intent to its executor.

    Public so retrieval.py can call execute() directly when /memory/query
    receives a clearly-temporal phrasing.
    """
    if intent.kind == "temporal_med":
        return await _handle_temporal_med(intent, lang)
    if intent.kind == "temporal_event":
        return await _handle_temporal_event(intent, lang)
    # Fall back to semantic retrieval for everything else
    from .retrieval import query_memory
    return await query_memory(intent.raw_text, lang)


# ---------------------------------------------------------------------------
# Medication taken in a window (default: today)
# ---------------------------------------------------------------------------

async def _handle_temporal_med(intent: Intent, lang: str) -> dict:
    from .db import fetch_med_logs_in_window

    window = intent.time_window or _default_window_today()
    med = await _resolve_medication(intent.medication_hint)

    start_iso = window.start.astimezone(timezone.utc).isoformat()
    end_iso = window.end.astimezone(timezone.utc).isoformat()
    medication_id = med["id"] if med else None

    try:
        logs = await fetch_med_logs_in_window(start_iso, end_iso, medication_id)
    except Exception:
        logs = []

    now = datetime.now(timezone.utc)
    prov = Provenance(source="med_log_table", added_by="system", added_ts=now)
    med_label = (med["name"] if med else "your medication")

    if logs:
        latest = logs[0]
        time_str = _fmt_time(latest.get("taken_ts", ""))
        item = RetrievedItem(
            ref=f"med_log:{latest['id']}",
            type=EntityType.med_log,
            text=f"{med_label} taken at {time_str} ({window.label}).",
            score=1.0,
            provenance=prov,
        )
        return _grounded_one(item, f"Yes, you took your {med_label} at {time_str}.")

    # Grounded negative — absence of a row is itself a confident fact.
    item = RetrievedItem(
        ref=f"med_log:none:{window.label}:{medication_id or 'any'}",
        type=EntityType.med_log,
        text=f"No {med_label} logged {window.label}.",
        score=0.95,
        provenance=prov,
    )
    if intent.medication_hint:
        draft = f"Not yet — I don't see your {med_label} {window.label}. Would you like me to remind you?"
    else:
        draft = f"I don't see any medication taken {window.label} yet. Want a reminder?"
    return _grounded_one(item, draft)


# ---------------------------------------------------------------------------
# Events in a window (default: next 7 days)
# ---------------------------------------------------------------------------

async def _handle_temporal_event(intent: Intent, lang: str) -> dict:
    from .db import fetch_events_in_window
    from .moss_client import moss

    if intent.time_window:
        window = intent.time_window
    else:
        now = datetime.now(timezone.utc)
        window = TimeWindow(now, now + timedelta(days=7), "this week")

    # Resolve any entity mention to a person id (Moss search)
    participant_id: Optional[str] = None
    if intent.entities:
        hits = await moss.query(intent.entities[0], top_k=3)
        for h in hits:
            if h["metadata"].get("type") == "person":
                participant_id = h["id"].split(":", 1)[-1]
                break

    start_iso = window.start.astimezone(timezone.utc).isoformat()
    end_iso = window.end.astimezone(timezone.utc).isoformat()
    try:
        events = await fetch_events_in_window(start_iso, end_iso, participant_id)
    except Exception:
        events = []

    now = datetime.now(timezone.utc)
    prov = Provenance(source="events_table", added_by="system", added_ts=now)

    if not events:
        subj = f" with {intent.entities[0]}" if intent.entities else ""
        item = RetrievedItem(
            ref=f"event:none:{window.label}",
            type=EntityType.event,
            text=f"No events{subj} {window.label}.",
            score=0.9,
            provenance=prov,
        )
        return _grounded_one(item, f"Nothing on the calendar{subj} {window.label}.")

    items: list[RetrievedItem] = []
    for e in events[:3]:
        time_str = _fmt_event_time(e.get("start_ts", ""))
        items.append(RetrievedItem(
            ref=f"event:{e['id']}",
            type=EntityType.event,
            text=f"{e['title']} — {time_str}.",
            score=0.95,
            provenance=prov,
        ))

    return {
        "items": [i.model_dump() for i in items],
        "grounded": True,
        "confidence": 0.95,
        "answer_draft": " ".join(i.text for i in items),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _default_window_today() -> TimeWindow:
    tw = parse_time_window("today")
    assert tw is not None
    return tw


def _grounded_one(item: RetrievedItem, answer: str) -> dict:
    return {
        "items": [item.model_dump()],
        "grounded": True,
        "confidence": float(item.score),
        "answer_draft": answer,
    }


def _fmt_time(iso: str) -> str:
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return t.strftime("%-I:%M %p").lstrip("0").lower().replace(" ", "")
    except Exception:
        return "earlier"


def _fmt_event_time(iso: str) -> str:
    try:
        t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return t.strftime("%A at %-I %p")
    except Exception:
        return "soon"


# ---------------------------------------------------------------------------
# Timeline — unchanged
# ---------------------------------------------------------------------------

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
