"""
Supabase DB layer. All table writes go here; also triggers Moss upsert.
Tables mirror the §3 data model — use Supabase auto-generated UUIDs.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from .config import settings


def _client():
    from supabase import create_client
    return create_client(settings.supabase_url, settings.supabase_service_key)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Provenance helper
# ---------------------------------------------------------------------------

def _provenance(source: str = "caregiver_web", added_by: str = "caregiver") -> dict:
    return {"source": source, "added_by": added_by, "added_ts": _now()}


# ---------------------------------------------------------------------------
# Write a memory entity to Supabase (then Moss upsert is triggered by caller)
# ---------------------------------------------------------------------------

TABLE_MAP = {
    "person":     "persons",
    "place":      "places",
    "event":      "events",
    "medication": "medications",
    "med_log":    "med_logs",
    "story":      "stories",
    "episode":    "episodes",
}


async def write_memory(entity_type: str, payload: dict[str, Any]) -> dict:
    row_id = str(uuid.uuid4())
    row = {
        "id": row_id,
        **payload,
        "provenance": _provenance(
            source=payload.pop("source", "caregiver_web"),
            added_by=payload.pop("added_by", "caregiver"),
        ),
    }
    table = TABLE_MAP.get(entity_type)
    if not table:
        raise ValueError(f"Unknown entity type: {entity_type}")

    client = _client()
    client.table(table).insert(row).execute()
    return {"id": row_id}


async def update_event_participants(event_id: str, participant_ids: list[str]) -> None:
    client = _client()
    client.table("events").update({"participant_ids": participant_ids}).eq("id", event_id).execute()


# ---------------------------------------------------------------------------
# Fetch helpers used by retrieval / temporal
# ---------------------------------------------------------------------------

async def fetch_med_logs_today(medication_id: str | None = None) -> list[dict]:
    today = datetime.now(timezone.utc).date().isoformat()
    client = _client()
    q = client.table("med_logs").select("*").gte("taken_ts", today)
    if medication_id:
        q = q.eq("medication_id", medication_id)
    res = q.execute()
    return res.data or []


async def fetch_med_logs_in_window(start_ts: str, end_ts: str,
                                    medication_id: str | None = None) -> list[dict]:
    """Med logs taken between [start_ts, end_ts]. Used by temporal routing
    for "did I take my X pill <time-window>" queries.
    """
    client = _client()
    q = (
        client.table("med_logs")
        .select("*")
        .gte("taken_ts", start_ts)
        .lte("taken_ts", end_ts)
        .order("taken_ts", desc=True)
    )
    if medication_id:
        q = q.eq("medication_id", medication_id)
    res = q.execute()
    return res.data or []


async def fetch_medications() -> list[dict]:
    """All medications — used to resolve a medication_hint ('heart pill') to an id."""
    client = _client()
    res = client.table("medications").select("*").execute()
    return res.data or []


async def fetch_upcoming_events(before_ts: str) -> list[dict]:
    now = _now()
    client = _client()
    res = (
        client.table("events")
        .select("*")
        .gte("start_ts", now)
        .lte("start_ts", before_ts)
        .order("start_ts")
        .execute()
    )
    return res.data or []


async def fetch_events_in_window(start_ts: str, end_ts: str,
                                  participant_id: str | None = None) -> list[dict]:
    """Events with start_ts in [start_ts, end_ts]. Used by temporal routing."""
    client = _client()
    res = (
        client.table("events")
        .select("*")
        .gte("start_ts", start_ts)
        .lte("start_ts", end_ts)
        .order("start_ts")
        .execute()
    )
    rows = res.data or []
    if participant_id:
        rows = [r for r in rows if participant_id in (r.get("participant_ids") or [])]
    return rows


async def fetch_persons() -> list[dict]:
    client = _client()
    res = client.table("persons").select("*").execute()
    return res.data or []


async def fetch_safe_zone() -> dict | None:
    client = _client()
    res = client.table("safe_zones").select("*").limit(1).execute()
    rows = res.data or []
    return rows[0] if rows else None


async def fetch_contacts_ordered(ids: list[str]) -> list[dict]:
    if not ids:
        return []
    client = _client()
    res = client.table("persons").select("*").in_("id", ids).execute()
    order = {id_: i for i, id_ in enumerate(ids)}
    rows = res.data or []
    return sorted(rows, key=lambda r: order.get(r["id"], 999))


async def store_interaction(record: dict) -> None:
    client = _client()
    client.table("interactions").insert({
        "id": str(uuid.uuid4()),
        **record,
    }).execute()


async def store_alert(record: dict) -> None:
    client = _client()
    client.table("alerts").insert({
        "id": str(uuid.uuid4()),
        **record,
    }).execute()


async def db_ping() -> bool:
    try:
        client = _client()
        client.table("persons").select("id").limit(1).execute()
        return True
    except Exception:
        return False
