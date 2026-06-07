"""
Deduplicate repeated seed rows in Supabase.

Backup-first cleanup for repeated `scripts/seed_amma.py` runs. The script:
1. Fetches all Yaad tables and writes a local JSON backup.
2. Chooses one canonical row per duplicate seed name/title.
3. Rewrites all known reference fields to canonical IDs.
4. Deletes duplicate rows.

Run from repo root:
  packages/memory-engine/.venv/bin/python scripts/dedupe_supabase_seed.py
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "memory-engine"))

from app.config import settings  # type: ignore
from supabase import create_client


TABLES = [
    "persons",
    "places",
    "medications",
    "med_logs",
    "events",
    "stories",
    "episodes",
    "edges",
    "interactions",
    "safe_zones",
    "location_pings",
    "alerts",
]

DEDUP_KEYS = {
    "persons": "name",
    "places": "name",
    "medications": "name",
    "events": "title",
    "stories": "title",
}


def main() -> None:
    db = create_client(settings.supabase_url, settings.supabase_service_key)
    data = {table: _fetch_all(db, table) for table in TABLES}
    backup_path = _write_backup(data)
    print(f"backup: {backup_path}")

    canonical: dict[str, str] = {}
    duplicate_ids: dict[str, list[str]] = defaultdict(list)

    for table, key in DEDUP_KEYS.items():
        for value, rows in _groups(data[table], key).items():
            if len(rows) <= 1:
                continue
            keep = _choose_canonical(table, rows)
            for row in rows:
                if row["id"] == keep["id"]:
                    continue
                canonical[row["id"]] = keep["id"]
                duplicate_ids[table].append(row["id"])
            print(f"{table}: {value!r} keep={keep['id']} delete={len(rows) - 1}")

    ref_map = _build_ref_map(data, canonical)

    updates = 0
    updates += _rewrite_events(db, data["events"], canonical)
    updates += _rewrite_stories(db, data["stories"], canonical)
    updates += _rewrite_med_logs(db, data["med_logs"], canonical)
    updates += _rewrite_edges(db, data["edges"], ref_map)
    updates += _rewrite_episodes(db, data["episodes"], ref_map)
    updates += _rewrite_interactions(db, data["interactions"], ref_map)
    updates += _rewrite_safe_zones(db, data["safe_zones"], canonical)
    updates += _rewrite_alerts(db, data["alerts"], canonical)
    print(f"reference updates: {updates}")

    # Delete children whose rows are duplicated by natural key after references
    # have been rewritten. Real FKs now point at canonical parents.
    for table in ["events", "stories", "med_logs", "edges", "safe_zones", "medications", "places", "persons"]:
        ids = duplicate_ids.get(table, [])
        if ids:
            _delete_ids(db, table, ids)
            print(f"deleted {len(ids)} from {table}")

    # Edge/safe-zone duplicates often become exact duplicates only after parent
    # refs are canonicalized, so clean them in a second pass.
    data2 = {table: _fetch_all(db, table) for table in TABLES}
    edge_dupes = _duplicate_edge_ids(data2["edges"])
    if edge_dupes:
        _delete_ids(db, "edges", edge_dupes)
        print(f"deleted {len(edge_dupes)} duplicate edges")
    zone_dupes = _duplicate_safe_zone_ids(data2["safe_zones"])
    if zone_dupes:
        _delete_ids(db, "safe_zones", zone_dupes)
        print(f"deleted {len(zone_dupes)} duplicate safe_zones")
    med_log_dupes = _duplicate_med_log_ids(data2["med_logs"])
    if med_log_dupes:
        _delete_ids(db, "med_logs", med_log_dupes)
        print(f"deleted {len(med_log_dupes)} duplicate med_logs")


def _fetch_all(db: Any, table: str) -> list[dict]:
    return db.table(table).select("*").execute().data or []


def _write_backup(data: dict[str, list[dict]]) -> str:
    os.makedirs("backups", exist_ok=True)
    path = os.path.join(
        "backups",
        f"supabase_dedupe_backup_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json",
    )
    with open(path, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    return path


def _groups(rows: list[dict], key: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        value = row.get(key)
        if value:
            out[str(value)].append(row)
    return out


def _choose_canonical(table: str, rows: list[dict]) -> dict:
    def score(row: dict) -> tuple:
        prov = row.get("provenance") or {}
        if not isinstance(prov, dict):
            prov = {}
        ts = str(prov.get("added_ts") or "")
        if table == "persons":
            prefs = row.get("preferences") or {}
            return (bool(prefs), bool(row.get("is_reassurance_contact")), row.get("alert_priority") or 0, ts)
        return (ts,)

    return sorted(rows, key=score, reverse=True)[0]


def _build_ref_map(data: dict[str, list[dict]], canonical: dict[str, str]) -> dict[str, str]:
    type_by_table = {
        "persons": "person",
        "places": "place",
        "medications": "medication",
        "events": "event",
        "stories": "story",
    }
    ref_map = {}
    for table, prefix in type_by_table.items():
        ids = {row["id"] for row in data[table]}
        for old_id, new_id in canonical.items():
            if old_id in ids:
                ref_map[f"{prefix}:{old_id}"] = f"{prefix}:{new_id}"
    return ref_map


def _rewrite_events(db: Any, rows: list[dict], canonical: dict[str, str]) -> int:
    count = 0
    for row in rows:
        patch = {}
        place_id = row.get("place_id")
        if place_id in canonical:
            patch["place_id"] = canonical[place_id]
        participants = _map_uuid_list(row.get("participant_ids"), canonical)
        if participants != (row.get("participant_ids") or []):
            patch["participant_ids"] = participants
        if patch:
            db.table("events").update(patch).eq("id", row["id"]).execute()
            count += 1
    return count


def _rewrite_stories(db: Any, rows: list[dict], canonical: dict[str, str]) -> int:
    count = 0
    for row in rows:
        people = _map_uuid_list(row.get("people_ids"), canonical)
        if people != (row.get("people_ids") or []):
            db.table("stories").update({"people_ids": people}).eq("id", row["id"]).execute()
            count += 1
    return count


def _rewrite_med_logs(db: Any, rows: list[dict], canonical: dict[str, str]) -> int:
    count = 0
    for row in rows:
        medication_id = row.get("medication_id")
        if medication_id in canonical:
            db.table("med_logs").update({"medication_id": canonical[medication_id]}).eq("id", row["id"]).execute()
            count += 1
    return count


def _rewrite_edges(db: Any, rows: list[dict], ref_map: dict[str, str]) -> int:
    count = 0
    for row in rows:
        patch = {}
        if row.get("from_ref") in ref_map:
            patch["from_ref"] = ref_map[row["from_ref"]]
        if row.get("to_ref") in ref_map:
            patch["to_ref"] = ref_map[row["to_ref"]]
        if patch:
            db.table("edges").update(patch).eq("id", row["id"]).execute()
            count += 1
    return count


def _rewrite_episodes(db: Any, rows: list[dict], ref_map: dict[str, str]) -> int:
    count = 0
    for row in rows:
        refs = _map_ref_list(row.get("entity_refs"), ref_map)
        if refs != (row.get("entity_refs") or []):
            db.table("episodes").update({"entity_refs": refs}).eq("id", row["id"]).execute()
            count += 1
    return count


def _rewrite_interactions(db: Any, rows: list[dict], ref_map: dict[str, str]) -> int:
    count = 0
    for row in rows:
        refs = _map_ref_list(row.get("retrieved_refs"), ref_map)
        if refs != (row.get("retrieved_refs") or []):
            db.table("interactions").update({"retrieved_refs": refs}).eq("id", row["id"]).execute()
            count += 1
    return count


def _rewrite_safe_zones(db: Any, rows: list[dict], canonical: dict[str, str]) -> int:
    count = 0
    for row in rows:
        patch = {}
        center = row.get("center_place_id")
        if center in canonical:
            patch["center_place_id"] = canonical[center]
        contacts = _map_uuid_list(row.get("contact_ids_ordered"), canonical)
        if contacts != (row.get("contact_ids_ordered") or []):
            patch["contact_ids_ordered"] = contacts
        if patch:
            db.table("safe_zones").update(patch).eq("id", row["id"]).execute()
            count += 1
    return count


def _rewrite_alerts(db: Any, rows: list[dict], canonical: dict[str, str]) -> int:
    count = 0
    for row in rows:
        contacts = _map_uuid_list(row.get("contacts_notified"), canonical)
        if contacts != (row.get("contacts_notified") or []):
            db.table("alerts").update({"contacts_notified": contacts}).eq("id", row["id"]).execute()
            count += 1
    return count


def _map_uuid_list(values: Any, canonical: dict[str, str]) -> list[str]:
    if not isinstance(values, list):
        return []
    return _dedupe([canonical.get(str(value), str(value)) for value in values])


def _map_ref_list(values: Any, ref_map: dict[str, str]) -> list[str]:
    if not isinstance(values, list):
        return []
    return _dedupe([ref_map.get(str(value), str(value)) for value in values])


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    out = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _delete_ids(db: Any, table: str, ids: list[str]) -> None:
    for row_id in ids:
        db.table(table).delete().eq("id", row_id).execute()


def _duplicate_edge_ids(rows: list[dict]) -> list[str]:
    seen = {}
    delete = []
    for row in sorted(rows, key=lambda r: r["id"]):
        key = (row.get("from_ref"), row.get("to_ref"), row.get("type"))
        if key in seen:
            delete.append(row["id"])
        else:
            seen[key] = row["id"]
    return delete


def _duplicate_safe_zone_ids(rows: list[dict]) -> list[str]:
    seen = {}
    delete = []
    for row in sorted(rows, key=lambda r: r["id"]):
        key = (row.get("center_place_id"), row.get("radius_m"), tuple(row.get("contact_ids_ordered") or []))
        if key in seen:
            delete.append(row["id"])
        else:
            seen[key] = row["id"]
    return delete


def _duplicate_med_log_ids(rows: list[dict]) -> list[str]:
    seen = {}
    delete = []
    for row in sorted(rows, key=lambda r: r["id"]):
        taken = str(row.get("taken_ts") or "")[:10]
        key = (row.get("medication_id"), taken, row.get("source"))
        if key in seen:
            delete.append(row["id"])
        else:
            seen[key] = row["id"]
    return delete


if __name__ == "__main__":
    main()
