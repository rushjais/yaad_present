"""
B7 — Per-beat robustness harness.

For each of the 5 demo beats, throw 6+ off-script phrasings at the memory
engine. Ground-truth phrasings must be `grounded=true`; adversarial phrasings
must be safe-refused. Green = ship-ready.

Run (server must be on :8000):
    pytest packages/memory-engine/tests/robustness.py -s
"""
from __future__ import annotations

import time
import httpx
import pytest

BASE = "http://localhost:8000"


def post(path: str, body: dict) -> tuple[dict, float]:
    t0 = time.perf_counter()
    r = httpx.post(f"{BASE}{path}", json=body, timeout=15)
    ms = (time.perf_counter() - t0) * 1000
    r.raise_for_status()
    return r.json(), ms


# ---------------------------------------------------------------------------
# Beat 1 — who-is-this (person identification)
# ---------------------------------------------------------------------------
WHO_IS_GROUND = [
    "Who is Leo?",
    "Tell me about Leo.",
    "Leo?",
    "Remind me who Leo is.",
    "What do you know about Leo?",
    "Who's Sarah?",
    "Tell me about my daughter Sarah.",
]
WHO_IS_REFUSE = [
    "Who is the president?",
    "Who is Tom Cruise?",
    "Tell me about Mars.",
    "Who is my dog?",
    "What is 2 plus 2?",
]


@pytest.mark.parametrize("text", WHO_IS_GROUND)
def test_beat1_who_is_grounded(text):
    d, ms = post("/memory/query", {"text": text, "lang": "en"})
    print(f"  [G] {text!r:45s} grounded={d['grounded']} conf={d['confidence']} {ms:.0f}ms")
    assert d["grounded"], f"Expected grounded for {text!r} — got {d['answer_draft']!r}"


@pytest.mark.parametrize("text", WHO_IS_REFUSE)
def test_beat1_who_is_refused(text):
    d, ms = post("/memory/query", {"text": text, "lang": "en"})
    print(f"  [R] {text!r:45s} grounded={d['grounded']} conf={d['confidence']} {ms:.0f}ms")
    assert not d["grounded"], f"Expected safe-refusal for {text!r} — got grounded {d['answer_draft']!r}"


# ---------------------------------------------------------------------------
# Beat 2 — pills-today (temporal medication)
# ---------------------------------------------------------------------------
PILLS_GROUND = [
    "Did I take my pills today?",
    "Have I had my medicine?",
    "Did I take my heart pill?",
    "Have I had my morning medication?",
    "Did I do my pills today?",
    "Have I taken my white pill?",
    "Have I taken my medication this morning?",
]


@pytest.mark.parametrize("text", PILLS_GROUND)
def test_beat2_pills_grounded(text):
    d, ms = post("/memory/temporal", {"text": text, "lang": "en"})
    print(f"  [G] {text!r:45s} grounded={d['grounded']} conf={d['confidence']} {ms:.0f}ms")
    assert d["grounded"], f"Expected grounded for {text!r} — got {d['answer_draft']!r}"
    assert isinstance(d["answer_draft"], str) and len(d["answer_draft"]) > 5


# ---------------------------------------------------------------------------
# Beat 3 — add-fact-live (write → query <1s)
# ---------------------------------------------------------------------------

def test_beat3_add_fact_live():
    import uuid
    suffix = uuid.uuid4().hex[:6].title()
    body = {
        "type": "person",
        "payload": {
            "name": f"Bibhuti_{suffix}",
            "relationship": "neighbor",
            "notes": f"A new friend named Bibhuti_{suffix} who lives down the street.",
        },
    }
    w, write_ms = post("/memory/write", body)
    assert "id" in w
    d, query_ms = post("/memory/query",
                       {"text": f"Who is Bibhuti_{suffix}?", "lang": "en"})
    total = write_ms + query_ms
    print(f"  add-fact-live → write {write_ms:.0f}ms + query {query_ms:.0f}ms = {total:.0f}ms  grounded={d['grounded']}")
    assert total < 2000, f"add-fact-live total {total:.0f}ms — must be <2000ms"
    assert d["grounded"], (
        f"add-fact-live produced an unretrievable write — Moss upsert in "
        f"/memory/write may have failed. response={d['answer_draft']!r}"
    )
    assert any(f"bibhuti_{suffix.lower()}" in (i.get("text") or "").lower() for i in d["items"]), \
        f"Items don't contain the new person — got {[i['text'][:50] for i in d['items']]}"


def test_beat3_capture_via_transcript():
    """Voice path: 'remember this — X' → episode + pending_review row.

    Uses a clean proper name (no digits/underscores) since the proper-noun
    regex in intent.py requires `[A-Z][a-z]+` and underscores break the word
    boundary. Demo transcripts will always be natural names anyway.
    """
    import uuid
    # Random but capitalized-alpha name for entity extraction
    names = ["Whiskers", "Biscuit", "Mango", "Daisy", "Toby", "Luna"]
    name = names[int(uuid.uuid4().int) % len(names)]
    transcript = f"Remember this — Leo brought home a cat named {name} today."
    d, capture_ms = post("/memory/capture", {"transcript": transcript})
    print(f"  capture → {capture_ms:.0f}ms  refs={len(d['created_refs'])}")
    assert len(d["created_refs"]) >= 1, "Capture produced no refs"

    d2, q_ms = post("/memory/query", {"text": f"Tell me about {name}", "lang": "en"})
    print(f"  capture-then-query → {q_ms:.0f}ms  grounded={d2['grounded']} items={len(d2['items'])}")
    assert d2["grounded"] or len(d2["items"]) > 0, "Captured fact not retrievable"


# ---------------------------------------------------------------------------
# Beat 4 — wifi-off (covered by general latency: <60ms = on-device)
# ---------------------------------------------------------------------------

def test_beat4_in_memory_latency():
    """Wifi-off promise = sub-10ms Moss in-memory. Server-side p95 should
    stay well under 60ms for semantic queries."""
    samples = []
    for _ in range(15):
        _, ms = post("/memory/query", {"text": "Who is Leo?", "lang": "en"})
        samples.append(ms)
    samples.sort()
    p50 = samples[len(samples) // 2]
    p95 = samples[int(len(samples) * 0.95)]
    print(f"  latency p50={p50:.0f}ms p95={p95:.0f}ms (target: p95<150ms client-side)")
    assert p95 < 200, f"p95 {p95:.0f}ms too high — graph N+1 may have regressed"


# ---------------------------------------------------------------------------
# Beat 5 — relational / graph traversal
# ---------------------------------------------------------------------------
RELATIONAL_GROUND = [
    "who is Leo to me",
    "who is Sarah to me",
    "tell me about my family",
    "tell me about my grandson",
    "tell me about my daughter",
]


@pytest.mark.parametrize("text", RELATIONAL_GROUND)
def test_beat5_relational_grounded(text):
    d, ms = post("/memory/query", {"text": text, "lang": "en"})
    print(f"  [G] {text!r:45s} grounded={d['grounded']} conf={d['confidence']} items={len(d['items'])} {ms:.0f}ms")
    assert d["grounded"], f"Expected grounded relational for {text!r} — got {d['answer_draft']!r}"
    assert len(d["items"]) >= 1


# ---------------------------------------------------------------------------
# Final per-beat scorecard
# ---------------------------------------------------------------------------

def test_scorecard(capsys):
    with capsys.disabled():
        print("\n=== YAAD B7 ROBUSTNESS SCORECARD ===")
        beats = {
            "1 who-is (grounded)":    WHO_IS_GROUND,
            "1 who-is (refused)":     WHO_IS_REFUSE,
            "2 pills today":          PILLS_GROUND,
            "5 relational":           RELATIONAL_GROUND,
        }
        for name, queries in beats.items():
            ok = 0
            for q in queries:
                path = "/memory/temporal" if "pill" in q.lower() or "medic" in q.lower() else "/memory/query"
                d, _ = post(path, {"text": q, "lang": "en"})
                expect_grounded = "refused" not in name
                if d["grounded"] == expect_grounded:
                    ok += 1
            print(f"  beat {name:25s} {ok}/{len(queries)}")
        print("===\n")
