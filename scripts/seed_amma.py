"""
seed_amma.py — minimal, realistic "Amma" persona for Track B to test against.

Gate 0: there is no DB/Moss yet, so this builds the entities as schema-validated
Pydantic models (proving they match the frozen contract) and writes them to
packages/memory-engine/fixtures/seed_amma.json. Raghav (Track C, C2) will expand
this into the rich persona and wire it to the real /memory/write once B1 lands.

Run:  python scripts/seed_amma.py
"""

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT / "packages" / "memory-engine"))

from app.schemas import (  # noqa: E402
    Edge,
    Episode,
    Event,
    MedLog,
    Medication,
    Person,
    Place,
    Provenance,
    SafeZone,
    Story,
)

_OUT = _ROOT / "packages" / "memory-engine" / "fixtures" / "seed_amma.json"

# All seed facts share this provenance: added by the system at setup time.
PROV = Provenance(source="seed", added_by="system", added_ts="2026-06-01T09:00:00Z")


def build() -> dict:
    people = [
        Person(
            id="person_leo",
            name="Leo",
            relationship="grandson",
            aliases=["Leo beta", "the boy"],
            notes="Sarah's son, 19. Just started at Stanford. Loves Amma's mango lassi.",
            is_reassurance_contact=True,
            alert_priority=2,
            provenance=PROV,
        ),
        Person(
            id="person_sarah",
            name="Sarah",
            relationship="daughter",
            aliases=["Sara", "beti"],
            notes="Amma's daughter, Leo's mother. Visits on weekends. Primary caregiver.",
            is_reassurance_contact=True,
            alert_priority=1,
            provenance=PROV,
        ),
    ]

    places = [
        Place(
            id="place_home",
            name="Amma's house",
            kind="home",
            lat=12.9716,
            lng=77.5946,
            notes="The yellow house in Bengaluru with the jasmine by the door.",
            provenance=PROV,
        ),
        Place(
            id="place_cubbon_park",
            name="Cubbon Park",
            kind="familiar",
            lat=12.9763,
            lng=77.5929,
            notes="Where Amma takes her morning walk, by the bamboo grove.",
            provenance=PROV,
        ),
    ]

    medications = [
        Medication(
            id="med_donepezil",
            name="Donepezil",
            schedule_rrule="FREQ=DAILY;BYHOUR=8;BYMINUTE=0",
            notes="The white heart-shaped pill. Morning, with breakfast.",
            provenance=PROV,
        ),
        Medication(
            id="med_memantine",
            name="Memantine",
            schedule_rrule="FREQ=DAILY;BYHOUR=20;BYMINUTE=0",
            notes="The small oval pill. Evening, after dinner.",
            provenance=PROV,
        ),
    ]

    med_logs = [
        MedLog(
            id="medlog_morning_dose",
            medication_id="med_donepezil",
            taken_ts="2026-06-05T08:02:00Z",
            source="voice",
        ),
    ]

    events = [
        Event(
            id="evt_sarah_visit",
            title="Sarah visits",
            kind="visit",
            start_ts="2026-06-05T15:00:00Z",
            place_id="place_home",
            participant_ids=["person_sarah"],
            notes="Sarah comes over Saturday afternoons for tea.",
            provenance=PROV,
        ),
    ]

    stories = [
        Story(
            id="story_mango_tree",
            title="The mango tree",
            text=(
                "Amma planted a mango tree the year Sarah was born. Every summer the "
                "whole family would gather under it to eat the first ripe mangoes."
            ),
            people_ids=["person_sarah"],
            occurred_ts="1975-06-01T00:00:00Z",
            provenance=PROV,
        ),
    ]

    episodes = [
        Episode(
            id="episode_leo_stanford",
            title="Leo got into Stanford",
            occurred_ts="2025-09-12T18:00:00Z",
            kind="milestone",
            entity_refs=["person_leo", "place_home"],
            summary="Last September Leo got into Stanford. The family celebrated at Amma's with gulab jamun.",
            provenance=PROV,
        ),
        Episode(
            id="episode_morning_walk",
            title="Morning walk in Cubbon Park",
            occurred_ts="2026-06-05T09:30:00Z",
            kind="routine",
            entity_refs=["place_cubbon_park"],
            summary="Amma's daily walk by the bamboo grove. She likes to feed the pigeons.",
            provenance=PROV,
        ),
        Episode(
            id="episode_sarah_wedding",
            title="Sarah's wedding",
            occurred_ts="2005-12-04T11:00:00Z",
            kind="memory",
            entity_refs=["person_sarah"],
            summary="Sarah's wedding in the garden. Amma wore the red Kanjeevaram saree.",
            provenance=PROV,
        ),
    ]

    edges = [
        Edge(id="edge_leo_sarah", from_ref="person_leo", to_ref="person_sarah", type="son_of", weight=1.0),
        Edge(id="edge_leo_stanford", from_ref="person_leo", to_ref="episode_leo_stanford", type="subject_of", weight=0.9),
        Edge(id="edge_sarah_home", from_ref="person_sarah", to_ref="place_home", type="visits", weight=0.8),
        Edge(id="edge_walk_park", from_ref="episode_morning_walk", to_ref="place_cubbon_park", type="at", weight=1.0),
    ]

    safe_zones = [
        SafeZone(
            id="zone_home",
            center_place_id="place_home",
            radius_m=500.0,
            contact_ids_ordered=["person_sarah", "person_leo"],
        ),
    ]

    def dump(rows):
        return [r.model_dump(mode="json") for r in rows]

    return {
        "person": dump(people),
        "place": dump(places),
        "medication": dump(medications),
        "med_log": dump(med_logs),
        "event": dump(events),
        "story": dump(stories),
        "episode": dump(episodes),
        "edge": dump(edges),
        "safe_zone": dump(safe_zones),
    }


def main() -> None:
    data = build()
    with open(_OUT, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    counts = ", ".join(f"{len(v)} {k}" for k, v in data.items())
    print(f"seeded Amma -> {_OUT}")
    print(f"  {counts}")


if __name__ == "__main__":
    main()
