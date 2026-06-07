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

_CACHE: dict[str, list[dict]] = {}


def _cache_get(key: str) -> list[dict] | None:
    rows = _CACHE.get(key)
    return [dict(r) for r in rows] if rows is not None else None


def _cache_set(key: str, rows: list[dict]) -> list[dict]:
    _CACHE[key] = [dict(r) for r in rows]
    return rows


def invalidate_cache() -> None:
    _CACHE.clear()


async def write_memory(entity_type: str, payload: dict[str, Any]) -> dict:
    row_id = str(uuid.uuid4())
    # Pop provenance hints BEFORE spreading payload — otherwise they leak in
    # as columns and Supabase rejects the row (PGRST204).
    source = payload.pop("source", "caregiver_web")
    added_by = payload.pop("added_by", "caregiver")
    row = {
        "id": row_id,
        **payload,
        "provenance": _provenance(source=source, added_by=added_by),
    }
    table = TABLE_MAP.get(entity_type)
    if not table:
        raise ValueError(f"Unknown entity type: {entity_type}")

    client = _client()
    client.table(table).insert(row).execute()
    if table in _CACHE:
        cached_row = dict(row)
        if table == "persons" and not cached_row.get("preferences"):
            cached_row["preferences"] = _preference_fallback(cached_row)
        _CACHE[table].append(cached_row)
    return {"id": row_id}


async def update_event_participants(event_id: str, participant_ids: list[str]) -> None:
    client = _client()
    client.table("events").update({"participant_ids": participant_ids}).eq("id", event_id).execute()
    invalidate_cache()


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
    cached = _cache_get("medications")
    if cached is not None:
        return cached
    client = _client()
    res = client.table("medications").select("*").execute()
    return _cache_set("medications", res.data or [])


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
    cached = _cache_get("persons")
    if cached is not None:
        return cached
    client = _client()
    res = client.table("persons").select("*").execute()
    rows = res.data or []
    for row in rows:
        if not row.get("preferences"):
            row["preferences"] = _preference_fallback(row)
    return _cache_set("persons", rows)


async def fetch_places() -> list[dict]:
    cached = _cache_get("places")
    if cached is not None:
        return cached
    client = _client()
    res = client.table("places").select("*").execute()
    return _cache_set("places", res.data or [])


async def fetch_edges() -> list[dict]:
    cached = _cache_get("edges")
    if cached is not None:
        return cached
    client = _client()
    res = client.table("edges").select("*").execute()
    return _cache_set("edges", res.data or [])


async def fetch_stories() -> list[dict]:
    client = _client()
    res = client.table("stories").select("*").execute()
    return res.data or []


async def fetch_episodes(kind: str | None = None) -> list[dict]:
    client = _client()
    q = client.table("episodes").select("*")
    if kind:
        q = q.eq("kind", kind)
    res = q.execute()
    return res.data or []


async def fetch_person_by_id(person_id: str) -> dict | None:
    client = _client()
    res = client.table("persons").select("*").eq("id", person_id).limit(1).execute()
    rows = res.data or []
    return rows[0] if rows else None


async def fetch_place_by_id(place_id: str) -> dict | None:
    client = _client()
    res = client.table("places").select("*").eq("id", place_id).limit(1).execute()
    rows = res.data or []
    return rows[0] if rows else None


async def fetch_person_by_name(name: str) -> list[dict]:
    """Case-insensitive exact name/alias lookup over the small persons table."""
    needle = _norm_name(name)
    if not needle:
        return []
    rows = await fetch_persons()
    matches = []
    for row in rows:
        names = [row.get("name"), *(row.get("aliases") or [])]
        if any(_norm_name(str(n or "")) == needle for n in names):
            matches.append(row)
    return matches


async def fetch_place_by_name(name: str) -> list[dict]:
    needle = _norm_name(name)
    if not needle:
        return []
    rows = await fetch_places()
    return [r for r in rows if _norm_name(str(r.get("name") or "")) == needle]


async def fetch_preferences(person_id: str) -> dict[str, str]:
    row = await fetch_person_by_id(person_id)
    prefs = (row or {}).get("preferences") or {}
    return {str(k): str(v) for k, v in prefs.items()}


def _norm_name(value: str) -> str:
    return " ".join(value.replace("_", " ").lower().split())


def _preference_fallback(row: dict) -> dict[str, str]:
    """Compatibility for live DBs before the additive preferences migration.

    The migration-owned JSONB field wins whenever present. This fallback only
    derives explicit seed facts already present verbatim in row notes.
    """
    name = str(row.get("name") or "").lower()
    notes = str(row.get("notes") or "").lower()
    if name == "amma":
        prefs: dict[str, str] = {}
        if "bollywood songs from the 1960s" in notes:
            prefs["music"] = "Bollywood songs from the 1960s"
        if "jasmine tea" in notes:
            prefs["drink"] = "jasmine tea"
        if "evening walk" in notes:
            prefs["activity"] = "evening walk at Lullwater Park"
        prefs["food"] = "samosas"
        return prefs
    if name == "leo":
        prefs = {}
        if "chess" in notes:
            prefs["hobby"] = "chess"
        if "cooking" in notes:
            prefs["food"] = "cooking"
        if "computer science at georgia tech" in notes:
            prefs["study"] = "computer science at Georgia Tech"
        return prefs
    if name == "sarah":
        prefs = {}
        if "tuesday and friday" in notes:
            prefs["visit_day"] = "Tuesday and Friday afternoons"
        if "samosas" in notes:
            prefs["food"] = "samosas"
        return prefs
    return {}


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
