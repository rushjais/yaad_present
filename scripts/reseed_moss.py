"""
Episodic-only Supabase -> Moss reseed.

Moss is now used only for fuzzy story / captured-fact retrieval. Persons,
places, medications, events, preferences, and relations are retrieved from
Supabase plus the in-process edge cache. No LLM touches stored/indexed text.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import sys
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def prov(source: str = "reseed") -> dict:
    return {"source": source, "added_by": "reseed_moss", "added_ts": now_iso()}


def _dedupe_by_name(rows: list[dict], key: str = "title") -> list[dict]:
    by_name: dict[str, dict] = {}
    for row in rows:
        name = row.get(key) or row.get("id")
        if not name:
            continue
        existing = by_name.get(name)
        if existing is None:
            by_name[name] = row
            continue
        existing_ts = (existing.get("provenance") or {}).get("added_ts", "")
        new_ts = (row.get("provenance") or {}).get("added_ts", "")
        if new_ts > existing_ts:
            by_name[name] = row
    return list(by_name.values())


def _package_path() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "packages", "memory-engine"))


async def build_moss_items() -> list[dict]:
    pkg = _package_path()
    if pkg not in sys.path:
        sys.path.insert(0, pkg)

    from app.chunks import render  # type: ignore
    from app.config import settings  # type: ignore
    from supabase import create_client

    db = create_client(settings.supabase_url, settings.supabase_service_key)
    items: list[dict] = []
    print(f"Reseed -> Moss index '{settings.moss_index}'")

    stories = _dedupe_by_name(db.table("stories").select("*").execute().data or [], key="title")
    for story in stories:
        items.append({
            "id": f"story:{story['id']}",
            "text": render("story", story),
            "metadata": {
                "type": "story",
                "title": story.get("title", ""),
                "provenance": story.get("provenance") or prov("stories"),
            },
        })
    print(f"  stories: {len(stories)}")

    episodes = db.table("episodes").select("*").eq("kind", "captured_fact").execute().data or []
    episodes = _dedupe_by_name(episodes, key="title")
    for episode in episodes:
        items.append({
            "id": f"episode:{episode['id']}",
            "text": render("episode", episode),
            "metadata": {
                "type": "episode",
                "kind": "captured_fact",
                "title": episode.get("title", ""),
                "provenance": episode.get("provenance") or prov("episodes"),
            },
        })
    print(f"  captured_fact episodes: {len(episodes)}")
    return items


async def reseed_moss(verify: bool = True, verbose: bool = True,
                      wipe_first: bool = False, enrich: bool | None = None) -> int:
    pkg = _package_path()
    if pkg not in sys.path:
        sys.path.insert(0, pkg)

    from app.config import settings  # type: ignore
    from app.moss_client import moss  # type: ignore

    if wipe_first:
        if verbose:
            print(f"Wiping Moss index '{settings.moss_index}'...")
        try:
            from moss import MossClient
            client = MossClient(settings.moss_project_id, settings.moss_project_key)
            deleted = client.delete_index(settings.moss_index)
            if inspect.isawaitable(deleted):
                await deleted
        except Exception as exc:
            if verbose:
                print(f"  wipe failed (continuing): {exc!r}")
        moss._session = None
        moss._client = None
        moss._known_doc_ids.clear()

    items = await build_moss_items()
    if verbose:
        print(f"\nUpserting {len(items)} episodic items to Moss...")
    if items:
        await moss.upsert_batch(items)
        await moss._push()
    if verbose:
        print("Push complete.")

    if not verify:
        return 0

    checks = [
        ("Tell me the chess story", "story", 0.5),
        ("Tell me a story about the garden", "story", 0.5),
    ]
    failed = False
    for query, expect_type, min_score in checks:
        hits = await moss.query(query, top_k=8)
        match = next(
            (
                hit for hit in hits
                if hit.get("metadata", {}).get("type") == expect_type
                and float(hit.get("score", 0.0)) >= min_score
            ),
            None,
        )
        if verbose:
            if match:
                print(f"  ok '{query}' -> {match['score']:.3f} {match['text'][:60]}")
            else:
                print(f"  fail '{query}' -> 0 acceptable results")
        failed = failed or match is None

    return 1 if failed else 0


if __name__ == "__main__":
    wipe = "--wipe" in sys.argv
    sys.exit(asyncio.run(reseed_moss(wipe_first=wipe)))
