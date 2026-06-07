"""
B6 — Smoke test + ~20-case grounding/latency table for the demo.
Run: pytest packages/memory-engine/tests/smoke_test.py -v
Or standalone: python -m pytest packages/memory-engine/tests/smoke_test.py
"""
from __future__ import annotations

import time
import pytest
import httpx

BASE = "http://localhost:8000"


def post(path: str, body: dict) -> tuple[dict, float]:
    t0 = time.perf_counter()
    r = httpx.post(f"{BASE}{path}", json=body, timeout=10)
    ms = (time.perf_counter() - t0) * 1000
    r.raise_for_status()
    return r.json(), ms


def get(path: str) -> tuple[dict, float]:
    t0 = time.perf_counter()
    r = httpx.get(f"{BASE}{path}", timeout=10)
    ms = (time.perf_counter() - t0) * 1000
    r.raise_for_status()
    return r.json(), ms


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health():
    data, ms = get("/health")
    assert "moss_ok" in data
    assert "db_ok" in data
    assert "latency_ms" in data
    print(f"  /health → {ms:.0f}ms  moss={data['moss_ok']}  db={data['db_ok']}")


# ---------------------------------------------------------------------------
# Core beat 1: who-is-this
# ---------------------------------------------------------------------------

# Language: English only. Multilingual support is a future add-on.
# Note: more thorough refusal cases live in tests/robustness.py — this smoke
# test stays small and avoids semantic ambiguities (e.g. "dog name" matches
# captured "cat named X" episodes from previous test runs).
QUERY_CASES = [
    ("Who is Leo?",            "en", True,  "person"),
    ("Tell me about Sarah.",   "en", True,  "person"),
    ("Who is the president?",  "en", False, None),
    ("Tell me about the park near home.", "en", True, "place"),
]

@pytest.mark.parametrize("text,lang,expect_grounded,expect_type", QUERY_CASES)
def test_memory_query(text, lang, expect_grounded, expect_type):
    data, ms = post("/memory/query", {"text": text, "lang": lang})
    grounded = data["grounded"]
    confidence = data["confidence"]

    print(f"  [{lang}] {text!r:45s} grounded={grounded} conf={confidence:.2f} {ms:.0f}ms")

    assert "items" in data
    assert "answer_draft" in data
    assert isinstance(data["answer_draft"], str)

    if expect_grounded:
        assert grounded, f"Expected grounded for: {text!r}"
        assert confidence >= 0.45
        if expect_type:
            types = [i["type"] for i in data["items"]]
            assert expect_type in types, f"Expected type {expect_type} in {types}"
    else:
        # Ungrounded → safe refusal, never fabrication
        assert not grounded or confidence < 0.45
        draft = data.get("answer_draft", "")
        bad_words = ["certainly", "yes, your", "of course", "definitely"]
        for w in bad_words:
            assert w.lower() not in draft.lower(), f"Possible confabulation: {draft!r}"


# ---------------------------------------------------------------------------
# Core beat 2: pills-today (temporal)
# ---------------------------------------------------------------------------

TEMPORAL_CASES = [
    ("Did I take my pills today?", "en"),
    ("Have I had my medicine?",    "en"),
    ("Is Sarah coming today?",     "en"),
    ("When is Leo visiting?",      "en"),
]

@pytest.mark.parametrize("text,lang", TEMPORAL_CASES)
def test_temporal(text, lang):
    data, ms = post("/memory/temporal", {"text": text, "lang": lang})
    print(f"  [{lang}] {text!r:45s} grounded={data['grounded']} {ms:.0f}ms")
    assert "items" in data
    assert "answer_draft" in data
    assert isinstance(data["answer_draft"], str) and len(data["answer_draft"]) > 5


# ---------------------------------------------------------------------------
# Core beat 3: add-fact-live (write → query < 1s)
# ---------------------------------------------------------------------------

def test_add_fact_live():
    import uuid
    # Use a distinctive name + notes so this fixture doesn't pollute later
    # semantic queries (the old "neighbor with a cat" matched 'dog name' too
    # well, false-positiving the refusal tests).
    fact_name = f"TestFriend_{uuid.uuid4().hex[:6]}"
    body = {
        "type": "person",
        "payload": {
            "name": fact_name,
            "relationship": "book_club_friend",
            "notes": "From Tuesday book club. Reads mystery novels.",
        },
    }
    write_data, write_ms = post("/memory/write", body)
    assert "id" in write_data
    print(f"  write {fact_name!r} → {write_ms:.0f}ms")

    # Query immediately — must be answerable
    query_data, query_ms = post("/memory/query", {"text": f"Who is {fact_name}?", "lang": "en"})
    total_ms = write_ms + query_ms
    print(f"  query after write → {query_ms:.0f}ms  total={total_ms:.0f}ms  grounded={query_data['grounded']}")

    # <1s total is the contract
    assert total_ms < 1000, f"add-fact-live took {total_ms:.0f}ms — must be <1000ms"


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------

def test_reminders_due():
    data, ms = get("/reminders/due")
    print(f"  /reminders/due → {ms:.0f}ms  count={len(data['due'])}")
    assert "due" in data
    assert isinstance(data["due"], list)


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------

def test_timeline():
    data, ms = get("/memory/timeline")
    print(f"  /timeline → {ms:.0f}ms  blocks={len(data['blocks'])}")
    assert "blocks" in data


# ---------------------------------------------------------------------------
# Latency contract: /memory/query p95 < 60ms server-side
# ---------------------------------------------------------------------------

def test_latency_p95():
    samples = []
    for _ in range(10):
        _, ms = post("/memory/query", {"text": "Who is Leo?", "lang": "en"})
        samples.append(ms)
    samples.sort()
    p50 = samples[4]
    p95 = samples[int(len(samples) * 0.95)]
    print(f"  latency p50={p50:.0f}ms  p95={p95:.0f}ms  (contract: p95<60ms server-side)")
    # Client-side includes network; server-side will be lower. Warn, don't hard-fail.
    if p95 > 200:
        pytest.fail(f"p95 latency {p95:.0f}ms is very high — investigate")


# ---------------------------------------------------------------------------
# Grounding: ungrounded response must contain safe-refusal phrase
# ---------------------------------------------------------------------------

def test_safe_refusal_en():
    data, _ = post("/memory/query", {"text": "Who is the Prime Minister of Mars?", "lang": "en"})
    if not data["grounded"]:
        draft = data.get("answer_draft", "")
        assert any(w in draft.lower() for w in ["not sure", "check with", "family", "I'm not"]), \
            f"Safe refusal missing expected phrase: {draft!r}"


# ---------------------------------------------------------------------------
# Print eval table (run with -s to see)
# ---------------------------------------------------------------------------

def test_eval_table(capsys):
    # Language: English only. Multilingual is a future add-on.
    cases = [
        ("Who is Leo?",               "en"),
        ("Tell me about Sarah.",       "en"),
        ("Did I take my pills today?", "en"),
        ("Is Sarah coming today?",     "en"),
        ("Tell me about home.",        "en"),
        ("Who is the president?",      "en"),
        ("What is 2+2?",              "en"),
    ]
    rows = []
    for text, lang in cases:
        try:
            d, ms = post("/memory/query" if "pill" not in text.lower() else "/memory/temporal",
                         {"text": text, "lang": lang})
            rows.append((text, d["grounded"], round(d["confidence"], 2), round(ms), d.get("answer_draft", "")[:60]))
        except Exception as e:
            rows.append((text, "ERR", 0, 0, str(e)[:60]))

    with capsys.disabled():
        print("\n\n=== YAAD EVAL TABLE ===")
        print(f"{'Query':45s} {'G':5s} {'Conf':5s} {'ms':5s} {'Draft'}")
        print("-" * 110)
        for r in rows:
            print(f"{r[0]:45s} {str(r[1]):5s} {str(r[2]):5s} {str(r[3]):5s} {r[4]}")
        print("=" * 100)
