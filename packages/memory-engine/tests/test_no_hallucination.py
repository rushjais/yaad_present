from __future__ import annotations

import os
import uuid

import httpx

BASE = os.environ.get("YAAD_TEST_BASE", "http://localhost:8000")


def post(path: str, body: dict) -> dict:
    resp = httpx.post(f"{BASE}{path}", json=body, timeout=15)
    resp.raise_for_status()
    return resp.json()


def test_sparse_person_does_not_inherit_other_biography():
    suffix = uuid.uuid4().hex[:8]
    name = f"Sparse_Test_Person_{suffix}"
    post("/memory/write", {
        "type": "person",
        "payload": {"name": name, "relationship": "neighbor", "notes": "Friendly."},
    })

    resp = post("/memory/query", {"text": f"Who is {name}?", "lang": "en"})
    assert resp["grounded"]
    text = " ".join(item.get("text") or "" for item in resp["items"])

    forbidden = [
        "Leo", "Sarah", "Amma", "Bhavya", "grandson", "daughter", "Georgia Tech",
        "Bollywood", "chess", "jasmine", "computer science",
    ]
    for word in forbidden:
        assert word not in text, f"Hallucination: sparse person text contains {word!r}"
