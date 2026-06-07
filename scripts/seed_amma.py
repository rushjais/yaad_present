"""
Seed Amma's fictional but believable life into Supabase + Moss.
Run: python scripts/seed_amma.py

Persona: Amma, 84. Grandson Leo (22). Daughter Sarah (55).
Medications: white heart pill (8am), blood pressure pill (8pm).
Routine: morning chai, evening walk at Lullwater Park.
Home: 142 Elmwood Ave.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def days_ago(n: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=n)).isoformat()


def days_ahead(n: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=n)).isoformat()


def prov(source: str = "seed") -> dict:
    return {"source": source, "added_by": "seed_script", "added_ts": now()}


async def main():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "memory-engine"))
    from app.config import settings
    from app.moss_client import moss
    from supabase import create_client

    db = create_client(settings.supabase_url, settings.supabase_service_key)
    await moss.create_index_if_needed()

    moss_items = []

    # -----------------------------------------------------------------------
    # Persons
    # -----------------------------------------------------------------------
    leo_id = str(uuid.uuid4())
    sarah_id = str(uuid.uuid4())
    amma_id = str(uuid.uuid4())

    persons = [
        {
            "id": leo_id,
            "name": "Leo",
            "relationship": "grandson",
            "aliases": ["Leo beta", "beta"],
            "notes": "22 years old, studying computer science at Georgia Tech. Visits every Sunday. Loves chess and cooking. Very patient with Amma.",
            "preferences": {
                "hobby": "chess",
                "food": "cooking",
                "study": "computer science at Georgia Tech",
            },
            "is_reassurance_contact": False,
            "alert_priority": 2,
            "provenance": prov(),
        },
        {
            "id": sarah_id,
            "name": "Sarah",
            "relationship": "daughter",
            "aliases": ["Sarah beti", "beti"],
            "notes": "55 years old. Lives at 89 Maple Lane, 15 minutes away. Visits Tuesday and Friday afternoons for tea. Primary caregiver.",
            "preferences": {
                "visit_day": "Tuesday and Friday afternoons",
                "food": "samosas",
            },
            "is_reassurance_contact": True,
            "alert_priority": 1,
            "provenance": prov(),
        },
        {
            "id": amma_id,
            "name": "Amma",
            "relationship": "self",
            "aliases": ["herself"],
            "notes": "84 years old. Loves jasmine tea, Bollywood songs from the 1960s, and her evening walk.",
            "preferences": {
                "music": "Bollywood songs from the 1960s",
                "drink": "jasmine tea",
                "activity": "evening walk at Lullwater Park",
                "food": "samosas",
            },
            "is_reassurance_contact": False,
            "provenance": prov(),
        },
    ]

    for p in persons:
        db.table("persons").upsert(p).execute()

    print(f"  persons: {len(persons)} seeded")

    # -----------------------------------------------------------------------
    # Places
    # -----------------------------------------------------------------------
    home_id = str(uuid.uuid4())
    park_id = str(uuid.uuid4())

    places = [
        {
            "id": home_id,
            "name": "Home",
            "kind": "home",
            "lat": 33.7490,
            "lng": -84.3880,
            "notes": "142 Elmwood Ave. Two-bedroom house with a jasmine garden. Lived here for 40 years.",
            "provenance": prov(),
        },
        {
            "id": park_id,
            "name": "Lullwater Park",
            "kind": "familiar",
            "lat": 33.7940,
            "lng": -84.3390,
            "notes": "Amma's favorite evening walk spot. Has a pond with ducks. About 10 minutes from home.",
            "provenance": prov(),
        },
    ]

    for place in places:
        db.table("places").upsert(place).execute()

    print(f"  places: {len(places)} seeded")

    # -----------------------------------------------------------------------
    # Medications
    # -----------------------------------------------------------------------
    heart_pill_id = str(uuid.uuid4())
    bp_pill_id = str(uuid.uuid4())

    medications = [
        {
            "id": heart_pill_id,
            "name": "white heart pill (Metoprolol)",
            "schedule_rrule": "FREQ=DAILY;BYHOUR=8;BYMINUTE=0;BYSECOND=0",
            "notes": "Small white tablet. Take with morning chai. For heart rhythm.",
            "provenance": prov(),
        },
        {
            "id": bp_pill_id,
            "name": "blood pressure pill (Amlodipine)",
            "schedule_rrule": "FREQ=DAILY;BYHOUR=20;BYMINUTE=0;BYSECOND=0",
            "notes": "Pink oval tablet. Take with dinner. For blood pressure.",
            "provenance": prov(),
        },
    ]

    for med in medications:
        db.table("medications").upsert(med).execute()

    print(f"  medications: {len(medications)} seeded")

    # Seed a med log for today (morning pill taken)
    today_log_id = str(uuid.uuid4())
    today_8am = datetime.now(timezone.utc).replace(hour=8, minute=0, second=0, microsecond=0)
    db.table("med_logs").upsert({
        "id": today_log_id,
        "medication_id": heart_pill_id,
        "taken_ts": today_8am.isoformat(),
        "source": "caregiver_confirmed",
        "provenance": prov(),
    }).execute()
    print("  med_log: today's heart pill seeded")

    # -----------------------------------------------------------------------
    # Events
    # -----------------------------------------------------------------------
    events = [
        {
            "id": str(uuid.uuid4()),
            "title": "Sarah's visit for tea",
            "kind": "family_visit",
            "start_ts": days_ahead(1) if datetime.now(timezone.utc).hour < 13 else days_ahead(2),
            "place_id": home_id,
            "participant_ids": [sarah_id],
            "notes": "Sarah comes every Tuesday and Friday. Brings samosas sometimes.",
            "provenance": prov(),
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Leo's Sunday visit",
            "kind": "family_visit",
            "start_ts": days_ahead(3),
            "place_id": home_id,
            "participant_ids": [leo_id],
            "notes": "Leo visits every Sunday. Usually brings flowers. Plays chess with Amma.",
            "provenance": prov(),
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Doctor checkup (Dr. Patel)",
            "kind": "medical",
            "start_ts": days_ahead(5),
            "place_id": None,
            "participant_ids": [sarah_id],
            "notes": "Routine checkup. Sarah will drive.",
            "provenance": prov(),
        },
    ]

    for e in events:
        db.table("events").upsert(e).execute()

    print(f"  events: {len(events)} seeded")

    # -----------------------------------------------------------------------
    # Stories & Episodes
    # -----------------------------------------------------------------------
    stories = [
        {
            "id": str(uuid.uuid4()),
            "title": "Leo's first chess win",
            "text": "Leo beat Amma at chess for the first time when he was 12. She was so proud she told all the neighbors. He still reminds her every visit.",
            "people_ids": [leo_id],
            "occurred_ts": days_ago(3650),
            "category": "family",
            "provenance": prov(),
        },
        {
            "id": str(uuid.uuid4()),
            "title": "The jasmine garden",
            "text": "Amma planted jasmine in the backyard the year she moved to Elmwood Ave, forty years ago. She waters it every morning before chai.",
            "people_ids": [amma_id],
            "occurred_ts": days_ago(14600),
            "category": "place",
            "provenance": prov(),
        },
        {
            "id": str(uuid.uuid4()),
            "title": "Sarah's cooking lessons",
            "text": "Sarah learned all her recipes from Amma. The biryani recipe has been in the family for three generations.",
            "people_ids": [sarah_id, amma_id],
            "occurred_ts": days_ago(10950),
            "category": "family",
            "provenance": prov(),
        },
    ]

    for s in stories:
        db.table("stories").upsert(s).execute()
        from app.chunks import render
        text = render("story", s)
        moss_items.append({
            "id": f"story:{s['id']}",
            "text": text,
            "metadata": {"type": "story", "title": s["title"], "provenance": prov()},
        })

    print(f"  stories: {len(stories)} seeded")

    # -----------------------------------------------------------------------
    # Edges (relationships)
    # -----------------------------------------------------------------------
    edges = [
        {"id": str(uuid.uuid4()), "from_ref": f"person:{leo_id}",   "to_ref": f"person:{amma_id}",  "type": "grandson_of",  "weight": 2.0},
        {"id": str(uuid.uuid4()), "from_ref": f"person:{sarah_id}", "to_ref": f"person:{amma_id}",  "type": "daughter_of",  "weight": 2.0},
        {"id": str(uuid.uuid4()), "from_ref": f"person:{leo_id}",   "to_ref": f"person:{sarah_id}", "type": "son_of",       "weight": 1.5},
        {"id": str(uuid.uuid4()), "from_ref": f"person:{amma_id}",  "to_ref": f"place:{home_id}",   "type": "lives_at",     "weight": 2.0},
        {"id": str(uuid.uuid4()), "from_ref": f"person:{amma_id}",  "to_ref": f"place:{park_id}",   "type": "frequents",    "weight": 1.5},
    ]

    for e in edges:
        db.table("edges").upsert(e).execute()

    print(f"  edges: {len(edges)} seeded")

    # -----------------------------------------------------------------------
    # Safe zone
    # -----------------------------------------------------------------------
    db.table("safe_zones").upsert({
        "id": str(uuid.uuid4()),
        "center_place_id": home_id,
        "radius_m": 500,
        "contact_ids_ordered": [sarah_id, leo_id],
    }).execute()
    print("  safe_zone: seeded (500m around home)")

    # -----------------------------------------------------------------------
    # Batch upsert to Moss
    # -----------------------------------------------------------------------
    print(f"\n  Upserting {len(moss_items)} items to Moss index '{settings.moss_index}'...")
    await moss.upsert_batch(moss_items)
    await moss._push()  # explicit push so process doesn't end before cloud sync
    print("  Moss index populated and pushed to cloud.")

    # verify episodic retrieval works
    hits = await moss.query("Tell me the chess story", top_k=3)
    print(f"  Verify: 'Tell me the chess story' -> {len(hits)} results")
    for h in hits:
        print(f"    [{h['score']:.3f}] {h['text'][:70]}")

    print("\nSeed complete. Amma's life is ready.")


if __name__ == "__main__":
    asyncio.run(main())
