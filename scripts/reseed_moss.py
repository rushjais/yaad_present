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


# ---------------------------------------------------------------------------
# Chunk text builders — v2 design: every entity's chunk bakes its
# relationships into the text. Moss semantic match then naturally answers
# relational queries ("Leo's mom" matches Leo's chunk → LLM reads "Sarah's
# son" → answers Sarah). No edge-walking needed.
# ---------------------------------------------------------------------------

# Edge type → natural-language phrase about the FROM entity relative to TO.
# e.g. ("Leo", "grandson_of", "Amma") → "Amma's grandson"
_FORWARD_PHRASE = {
    "grandson_of":      "{to}'s grandson",
    "granddaughter_of": "{to}'s granddaughter",
    "daughter_of":      "{to}'s daughter",
    "son_of":           "{to}'s son",
    "mother_of":        "{to}'s mother",
    "father_of":        "{to}'s father",
    "sister_of":        "{to}'s sister",
    "brother_of":       "{to}'s brother",
    "lives_at":         "lives at {to}",
    "frequents":        "regularly visits {to}",
}
# Edge from another direction: ("Amma", "grandson_of", reversed) → "Leo's grandmother"
_REVERSE_PHRASE = {
    "grandson_of":      "{from}'s grandmother",
    "granddaughter_of": "{from}'s grandmother",
    "daughter_of":      "{from}'s mother",
    "son_of":           "{from}'s mother",
    "mother_of":        "{from}'s daughter",
    "father_of":        "{from}'s daughter",
    "sister_of":        "{from}'s sister",
    "brother_of":       "{from}'s sister",
    "lives_at":         "home of {from}",
    "frequents":        "where {from} walks",
}


def _build_relations_for(ref: str,
                          edges: list[dict],
                          name_by_ref: dict[str, str]) -> list[str]:
    """Return a list of NL phrases describing this entity's relationships,
    suitable for inlining into its Moss chunk.
    """
    phrases: list[str] = []
    for e in edges:
        from_ref = e["from_ref"]
        to_ref = e["to_ref"]
        et = e.get("type", "related")
        if from_ref == ref:
            other = name_by_ref.get(to_ref)
            if not other:
                continue
            tmpl = _FORWARD_PHRASE.get(et)
            if tmpl:
                phrases.append(tmpl.format(to=other, from_=name_by_ref.get(from_ref, "")))
        elif to_ref == ref:
            other = name_by_ref.get(from_ref)
            if not other:
                continue
            tmpl = _REVERSE_PHRASE.get(et)
            if tmpl:
                phrases.append(tmpl.format(from_=other, **{"from": other}, to=name_by_ref.get(to_ref, "")))
    # de-dupe, preserve order
    seen = set()
    out = []
    for p in phrases:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _person_text(p: dict, relations: list[str]) -> str:
    aliases = p.get("aliases") or []
    parts: list[str] = [p["name"]]
    if relations:
        parts.append(", ".join(relations))
    if p.get("notes"):
        parts.append(p["notes"])
    if aliases:
        parts.append(f"Also called {', '.join(aliases)}.")
    return ". ".join(s.strip().rstrip(".") for s in parts if s) + "."


def _place_text(pl: dict, relations: list[str]) -> str:
    parts = [pl["name"]]
    if relations:
        parts.append(", ".join(relations))
    if pl.get("notes"):
        parts.append(pl["notes"])
    return ". ".join(s.strip().rstrip(".") for s in parts if s) + "."


def _medication_text(m: dict) -> str:
    return f"{m['name']} — Amma's medication. {m.get('notes', '')}"


def _event_text(e: dict, name_by_ref: dict[str, str]) -> str:
    participants = [name_by_ref.get(f"person:{pid}") for pid in (e.get("participant_ids") or [])]
    participants = [p for p in participants if p]
    who = f" with {', '.join(participants)}" if participants else ""
    return f"{e['title']}{who}. {e.get('notes', '')}".strip()


def _story_text(s: dict, name_by_ref: dict[str, str]) -> str:
    people = [name_by_ref.get(f"person:{pid}") for pid in (s.get("people_ids") or [])]
    people = [p for p in people if p]
    about = f" (about {', '.join(people)})" if people else ""
    return f"Story{about}: {s.get('text', '')}"


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
    places = _dedupe_by_name(db.table("places").select("*").execute().data or [])
    medications = _dedupe_by_name(db.table("medications").select("*").execute().data or [])
    edges = db.table("edges").select("*").execute().data or []

    # Build ref → name map for relationship rendering
    name_by_ref: dict[str, str] = {}
    for p in persons:
        name_by_ref[f"person:{p['id']}"] = p["name"]
    for pl in places:
        name_by_ref[f"place:{pl['id']}"] = pl["name"]
    for m in medications:
        name_by_ref[f"medication:{m['id']}"] = m["name"]

    for p in persons:
        ref = f"person:{p['id']}"
        relations = _build_relations_for(ref, edges, name_by_ref)
        moss_items.append({
            "id": ref,
            "text": _person_text(p, relations),
            "metadata": {
                "type": "person",
                "name": p["name"],
                "relationship": p.get("relationship", ""),
                "provenance": prov(),
            },
        })
    print(f"  persons: {len(persons)}")

    for pl in places:
        ref = f"place:{pl['id']}"
        relations = _build_relations_for(ref, edges, name_by_ref)
        moss_items.append({
            "id": ref,
            "text": _place_text(pl, relations),
            "metadata": {
                "type": "place",
                "name": pl["name"],
                "kind": pl.get("kind", ""),
                "provenance": prov(),
            },
        })
    print(f"  places: {len(places)}")

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

    # Family-overview chunk — a single chunk that mentions everyone in the
    # immediate circle. Lets "tell me about my family" (which has no proper
    # noun for the τ gate to hook into) hit a clear target instead of getting
    # filtered. Cheap, scoped, demo-saving.
    family_members = []
    for p in persons:
        rel = p.get("relationship", "")
        notes = (p.get("notes") or "").split(".")[0]
        if rel and rel != "self":
            family_members.append(f"{p['name']} ({rel}, {notes.strip().lower()})")
        elif rel == "self":
            family_members.append(f"{p['name']} (the patient, {notes.strip().lower()})")
    if family_members:
        moss_items.append({
            "id": "summary:family",
            "text": "Amma's family includes: " + "; ".join(family_members) + ".",
            "metadata": {
                "type": "story",
                "title": "Family overview",
                "provenance": prov(source="seed_overview"),
            },
        })

    events = _dedupe_by_name(
        db.table("events").select("*").execute().data or [],
        key="title",
    )
    for e in events:
        moss_items.append({
            "id": f"event:{e['id']}",
            "text": _event_text(e, name_by_ref),
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
            "text": _story_text(s, name_by_ref),
            "metadata": {
                "type": "story",
                "title": s["title"],
                "provenance": prov(),
            },
        })
    print(f"  stories: {len(stories)}")
    return moss_items


async def reseed_moss(verify: bool = True, verbose: bool = True,
                       wipe_first: bool = False) -> int:
    """Reseed the in-process Moss session from Supabase.

    If `wipe_first=True`, delete the cloud index entirely first so stale test
    garbage (e.g. dynamic TestPerson/Bibhuti chunks from earlier runs) is
    purged. Run with `--wipe` from the CLI before a demo or after dirty test
    runs. Default is additive (no wipe) so server startup stays cheap.

    Returns 0 on success, 1 on verification failure.
    """
    pkg = os.path.join(os.path.dirname(__file__), "..", "packages", "memory-engine")
    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    from app.config import settings  # type: ignore
    from app.moss_client import moss  # type: ignore

    if wipe_first:
        if verbose:
            print(f"Wiping Moss index '{settings.moss_index}'…")
        try:
            from moss import MossClient
            client = MossClient(settings.moss_project_id, settings.moss_project_key)
            client.delete_index(settings.moss_index)
        except Exception as e:
            if verbose:
                print(f"  wipe failed (continuing): {e!r}")
        # Force the wrapper to re-open a fresh session next call
        moss._session = None
        moss._client = None

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
    wipe = "--wipe" in sys.argv
    sys.exit(asyncio.run(reseed_moss(wipe_first=wipe)))
