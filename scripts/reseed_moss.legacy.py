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
import inspect
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


# ---------------------------------------------------------------------------
# B7.2 — Category enrichment.
#
# Why: semantic search misses abstract category queries ("favorite music")
# when the underlying fact is specific ("Bollywood songs from the 1960s").
# The chunk has no category cue, so the embedding doesn't bridge.
#
# Fix: same pattern as B7.1's relationship-baking — rewrite the chunk text
# so categories surface as natural prose. Groq does the rewrite once at seed
# time (offline, no hot-path cost), then Moss embedding does the rest.
#
# Skip via YAAD_SKIP_ENRICHMENT=1 (faster reseed, but "favorite music"-style
# queries fall through to retrieval.py's runtime rewrite fallback).
# ---------------------------------------------------------------------------

_ENRICH_SYSTEM = """You rewrite a memory chunk so each fact is labeled with its category as a
short topic lead. This helps a semantic search engine match abstract category
queries ("favorite music", "what does she eat", "her hobbies") to the right
specific fact.

CRITICAL OUTPUT FORMAT — each preference becomes its own short sentence
starting with the CATEGORY WORD, then a colon or comma, then the fact:

  "Bollywood songs from the 1960s"  → "Music: Amma listens to Bollywood songs from the 1960s."
  "jasmine tea"                      → "Drinks: Amma loves jasmine tea."
  "evening walk at Lullwater Park"   → "Activities: Amma's evening walk at Lullwater Park."
  "Loves chess and cooking"          → "Hobbies: chess and cooking."
  "samosas"                          → "Food: samosas."
  "studies CS at Georgia Tech"       → "Studies: computer science at Georgia Tech."

Category words you may use (pick the most specific):
  Music · Songs · Food · Drinks · Hobbies · Activities · Walks · Reading · Books · Studies · Work · Family · Friends · Pets · Home · Routine

DO NOT use the bland "favorite X" pattern repeatedly — it makes all preference
chunks look semantically identical. Use the specific category word as the lead.

Other rules:
- Preserve every fact. Do not invent. Output prose only (no JSON, no tags).
- Identity facts (who someone is, their relationships) stay in normal prose:
  "Leo is Amma's grandson, 22, studies CS at Georgia Tech."
- 2-5 sentences total. Concise."""


async def _enrich_chunk(text: str) -> str:
    """Rewrite a chunk via Groq to surface category cues. Returns the original
    text on any failure (never blocks the seed).
    """
    if os.environ.get("YAAD_SKIP_ENRICHMENT") == "1":
        return text
    if not text or len(text) < 20:
        return text
    pkg = os.path.join(os.path.dirname(__file__), "..", "packages", "memory-engine")
    if pkg not in sys.path:
        sys.path.insert(0, pkg)
    try:
        from app.config import settings  # type: ignore
        from groq import AsyncGroq
    except Exception:
        return text
    if not settings.groq_api_key:
        return text
    try:
        client = AsyncGroq(api_key=settings.groq_api_key)
        # 8b is sufficient for this paraphrase task and runs on a separate
        # TPD quota from 70b (matters when the 70b daily limit is hit).
        resp = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": _ENRICH_SYSTEM},
                {"role": "user", "content": text},
            ],
            temperature=0,
            max_tokens=400,
        )
        out = (resp.choices[0].message.content or "").strip()
        # Defensive: never accept empty or 10x-shorter rewrites (would mean
        # Groq dropped facts).
        if len(out) < max(20, len(text) // 4):
            return text
        return out
    except Exception as e:
        print(f"  [enrich] skipped on error: {e!r}")
        return text


def _person_text(p: dict, relations: list[str]) -> str:
    aliases = p.get("aliases") or []
    parts: list[str] = [p["name"]]
    if p.get("relationship") and not relations:
        parts.append(p["relationship"])
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


# Enrichment cache: ref → enriched text. Written after a --wipe reseed,
# read on every subsequent reseed (including server startup) so we never
# pay the ~12s Groq cost on hot paths. Lives in the repo so teammates and
# CI share the same cache.
_ENRICH_CACHE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "fixtures", "enriched_chunks.json"
)


def _load_enrich_cache() -> dict[str, str]:
    try:
        with open(_ENRICH_CACHE_PATH) as f:
            return json.load(f) or {}
    except FileNotFoundError:
        return {}
    except Exception as e:
        print(f"  [enrich-cache] load failed: {e!r}")
        return {}


def _save_enrich_cache(cache: dict[str, str]) -> None:
    try:
        os.makedirs(os.path.dirname(_ENRICH_CACHE_PATH), exist_ok=True)
        with open(_ENRICH_CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2, sort_keys=True)
        print(f"  [enrich-cache] saved {len(cache)} entries → {os.path.basename(_ENRICH_CACHE_PATH)}")
    except Exception as e:
        print(f"  [enrich-cache] save failed: {e!r}")


async def build_moss_items(*, enrich: bool = False) -> list[dict]:
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

    enrich_tasks = []  # collected for batched await; index aligned to moss_items

    for p in persons:
        ref = f"person:{p['id']}"
        relations = _build_relations_for(ref, edges, name_by_ref)
        base_text = _person_text(p, relations)
        moss_items.append({
            "id": ref,
            "text": base_text,
            "metadata": {
                "type": "person",
                "name": p["name"],
                "relationship": p.get("relationship", ""),
                "provenance": prov(),
            },
        })
        enrich_tasks.append((len(moss_items) - 1, base_text))
    print(f"  persons: {len(persons)}")

    for pl in places:
        ref = f"place:{pl['id']}"
        relations = _build_relations_for(ref, edges, name_by_ref)
        base_text = _place_text(pl, relations)
        moss_items.append({
            "id": ref,
            "text": base_text,
            "metadata": {
                "type": "place",
                "name": pl["name"],
                "kind": pl.get("kind", ""),
                "provenance": prov(),
            },
        })
        enrich_tasks.append((len(moss_items) - 1, base_text))
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
        base_text = _story_text(s, name_by_ref)
        moss_items.append({
            "id": f"story:{s['id']}",
            "text": base_text,
            "metadata": {
                "type": "story",
                "title": s["title"],
                "provenance": prov(),
            },
        })
        enrich_tasks.append((len(moss_items) - 1, base_text))
    print(f"  stories: {len(stories)}")

    # ---- B7.2: category enrichment over persons/places/stories -------------
    # Surface "favorite music" / "what she likes to eat" / "hobbies" cues in
    # chunk text so semantic search bridges abstract → specific. One Groq
    # call per chunk, fired in parallel. Skipped via YAAD_SKIP_ENRICHMENT=1.
    # B7.2 — category enrichment. Two modes:
    #   - enrich=True (CLI --wipe path): Groq rewrites chunks, result is
    #     cached to fixtures/enriched_chunks.json. ~12s.
    #   - enrich=False (server startup): just applies the cache. ~0s.
    # When the cache is missing and enrich=False, we ship the base text —
    # category queries fall through to retrieval._rewrite_and_retry().
    cache = _load_enrich_cache()
    applied = 0
    for idx, _ in enrich_tasks:
        ref = moss_items[idx]["id"]
        if ref in cache:
            moss_items[idx]["text"] = cache[ref]
            applied += 1
    if applied:
        print(f"  enrich-cache: applied {applied}/{len(enrich_tasks)} cached entries")

    if enrich and os.environ.get("YAAD_SKIP_ENRICHMENT") != "1":
        print(f"  enriching {len(enrich_tasks)} chunks with category cues…")
        # Serial with a small pause: Groq's 8b TPM is 6000 — bursting all 25
        # chunks in parallel triggers 429s halfway through. Serial is ~12s
        # total, deterministic, no retry logic needed.
        changed = 0
        new_cache = dict(cache)
        for idx, original in enrich_tasks:
            ref = moss_items[idx]["id"]
            # Re-enrich from BASE text (not the already-cached version) so
            # changes to the seed roll through.
            result = await _enrich_chunk(original)
            if result and result != original:
                moss_items[idx]["text"] = result
                new_cache[ref] = result
                changed += 1
            await asyncio.sleep(0.4)
        print(f"  enriched: {changed}/{len(enrich_tasks)} chunks rewritten")
        if new_cache != cache:
            _save_enrich_cache(new_cache)
    return moss_items


async def reseed_moss(verify: bool = True, verbose: bool = True,
                       wipe_first: bool = False, enrich: bool | None = None) -> int:
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
            deleted = client.delete_index(settings.moss_index)
            if inspect.isawaitable(deleted):
                await deleted
        except Exception as e:
            if verbose:
                print(f"  wipe failed (continuing): {e!r}")
        # Force the wrapper to re-open a fresh session next call
        moss._session = None
        moss._client = None

    # Default: enrich on --wipe, skip otherwise (use cache). Caller can override.
    if enrich is None:
        enrich = wipe_first
    items = await build_moss_items(enrich=enrich)
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
        hits = await moss.query(query, top_k=8)
        if not hits:
            if verbose:
                print(f"  ❌ '{query}' → 0 results")
            fail = True
            continue
        match = next(
            (
                h for h in hits
                if h["score"] >= min_score and h["metadata"].get("type") == expect_type
            ),
            None,
        )
        top = match or hits[0]
        ok = match is not None
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
