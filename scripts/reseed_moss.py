"""
reseed_moss.py — idempotent Supabase → Moss reseed.

Why this exists:
  Moss `SessionIndex.session(index_name=...)` does not reliably resume
  the cloud index in a fresh process. Empirically: after a server
  restart, `query("Leo")` returns 0 results even though seed_amma.py
  pushed successfully. This script repopulates the Moss session from
  the canonical source of truth (Supabase) and verifies query works
  before exiting non-zero on failure.

  Run before any demo, after any server restart, after any teammate
  pulls fresh.

  No Supabase mutation. Safe to re-run.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def prov(source: str = "reseed") -> dict:
    return {"source": source, "added_by": "reseed_moss", "added_ts": now_iso()}


def _dedupe_by_name(rows: list[dict], key: str = "name") -> list[dict]:
    """Supabase has duplicates from re-runs of seed_amma. Keep the most
    recent row per name (provenance.added_ts breaks ties).
    """
    by_name: dict[str, dict] = {}
    for r in rows:
        k = r.get(key) or r.get("title")
        if not k:
            continue
        existing = by_name.get(k)
        if existing is None:
            by_name[k] = r
            continue
        existing_ts = (existing.get("provenance") or {}).get("added_ts", "")
        new_ts = (r.get("provenance") or {}).get("added_ts", "")
        if new_ts > existing_ts:
            by_name[k] = r
    return list(by_name.values())


def _person_text(p: dict) -> str:
    aliases = p.get("aliases") or []
    alias_str = f" (also called {', '.join(aliases)})" if aliases else ""
    return f"{p['name']} — {p.get('relationship', 'unknown')}{alias_str}. {p.get('notes', '')}"


def _place_text(pl: dict) -> str:
    return f"{pl['name']} ({pl.get('kind', 'place')}): {pl.get('notes', '')}"


def _medication_text(m: dict) -> str:
    return f"Medication: {m['name']}. {m.get('notes', '')}"


def _event_text(e: dict) -> str:
    return f"Event: {e['title']}. {e.get('notes', '')}"


def _story_text(s: dict) -> str:
    return f"Story — {s['title']}: {s.get('text', '')}"


async def build_moss_items() -> list[dict]:
    """Read Supabase, dedupe, and return canonical Moss items.
    Importable from the server's startup hook.
    """
    # Make app/* importable when called either as a script or from the server.
    pkg = os.path.join(os.path.dirname(__file__), "..", "packages", "memory-engine")
    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    from app.config import settings  # type: ignore
    from supabase import create_client

    db = create_client(settings.supabase_url, settings.supabase_service_key)
    moss_items: list[dict] = []

    print(f"Reseed → Moss index '{settings.moss_index}'")
    persons = _dedupe_by_name(db.table("persons").select("*").execute().data or [])
    for p in persons:
        moss_items.append({
            "id": f"person:{p['id']}",
            "text": _person_text(p),
            "metadata": {
                "type": "person",
                "name": p["name"],
                "relationship": p.get("relationship", ""),
                "provenance": prov(),
            },
        })
    print(f"  persons: {len(persons)}")

    places = _dedupe_by_name(db.table("places").select("*").execute().data or [])
    for pl in places:
        moss_items.append({
            "id": f"place:{pl['id']}",
            "text": _place_text(pl),
            "metadata": {
                "type": "place",
                "name": pl["name"],
                "kind": pl.get("kind", ""),
                "provenance": prov(),
            },
        })
    print(f"  places: {len(places)}")

    medications = _dedupe_by_name(db.table("medications").select("*").execute().data or [])
    for m in medications:
        moss_items.append({
            "id": f"medication:{m['id']}",
            "text": _medication_text(m),
            "metadata": {
                "type": "medication",
                "name": m["name"],
                "provenance": prov(),
            },
        })
    print(f"  medications: {len(medications)}")

    events = _dedupe_by_name(
        db.table("events").select("*").execute().data or [],
        key="title",
    )
    for e in events:
        moss_items.append({
            "id": f"event:{e['id']}",
            "text": _event_text(e),
            "metadata": {
                "type": "event",
                "title": e["title"],
                "start_ts": e.get("start_ts", ""),
                "provenance": prov(),
            },
        })
    print(f"  events: {len(events)}")

    stories = _dedupe_by_name(
        db.table("stories").select("*").execute().data or [],
        key="title",
    )
    for s in stories:
        moss_items.append({
            "id": f"story:{s['id']}",
            "text": _story_text(s),
            "metadata": {
                "type": "story",
                "title": s["title"],
                "provenance": prov(),
            },
        })
    print(f"  stories: {len(stories)}")
    return moss_items


async def reseed_moss(verify: bool = True, verbose: bool = True) -> int:
    """Reseed the in-process Moss session from Supabase.
    Returns 0 on success, 1 on verification failure.
    """
    pkg = os.path.join(os.path.dirname(__file__), "..", "packages", "memory-engine")
    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    from app.moss_client import moss  # type: ignore

    items = await build_moss_items()
    if verbose:
        print(f"\nUpserting {len(items)} items to Moss…")
    await moss.upsert_batch(items)
    await moss._push()
    if verbose:
        print("Push complete.")

    if not verify:
        return 0

    if verbose:
        print("\nVerify:")
    checks = [
        ("Who is Leo?", "person", 0.5),
        ("Tell me about Sarah.", "person", 0.5),
        ("Lullwater Park", "place", 0.5),
        ("heart pill", "medication", 0.4),
    ]
    fail = False
    for query, expect_type, min_score in checks:
        hits = await moss.query(query, top_k=3)
        if not hits:
            if verbose:
                print(f"  ❌ '{query}' → 0 results")
            fail = True
            continue
        top = hits[0]
        ok = top["score"] >= min_score and top["metadata"].get("type") == expect_type
        if verbose:
            mark = "✅" if ok else "❌"
            print(f"  {mark} '{query}' → {top['score']:.3f} {top['metadata'].get('type')} :: {top['text'][:60]}")
        if not ok:
            fail = True
    if fail:
        if verbose:
            print("\nReseed verification FAILED.")
        return 1
    if verbose:
        print("\nReseed verified. Moss is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(reseed_moss()))
