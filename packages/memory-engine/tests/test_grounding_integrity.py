from __future__ import annotations

import json
import os

import httpx
import pytest

BASE = os.environ.get("YAAD_TEST_BASE", "http://localhost:8000")
CORPUS = os.path.join(os.path.dirname(__file__), "general_queries.json")
RECOGNIZED = {
    "persons",
    "persons.preferences",
    "places",
    "medications",
    "med_logs",
    "events",
    "stories",
    "episodes",
    "events_table",
    "med_log_table",
}


def post(path: str, body: dict) -> dict:
    resp = httpx.post(f"{BASE}{path}", json=body, timeout=15)
    resp.raise_for_status()
    return resp.json()


@pytest.mark.parametrize("case", [c for c in json.load(open(CORPUS)) if c["grounded"]])
def test_every_item_has_recognized_provenance(case):
    q = case["query"]
    path = "/memory/temporal" if any(word in q.lower() for word in ("pill", "medication")) else "/memory/query"
    resp = post(path, {"text": q, "lang": "en"})
    assert resp["grounded"]
    assert resp["items"]
    for item in resp["items"]:
        assert item["provenance"]["source"] in RECOGNIZED
