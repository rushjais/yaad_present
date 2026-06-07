from __future__ import annotations

import json
import os
import time

import httpx
import pytest

BASE = os.environ.get("YAAD_TEST_BASE", "http://localhost:8000")
CORPUS = os.path.join(os.path.dirname(__file__), "general_queries.json")


def post(path: str, body: dict) -> tuple[dict, float]:
    t0 = time.perf_counter()
    resp = httpx.post(f"{BASE}{path}", json=body, timeout=15)
    ms = (time.perf_counter() - t0) * 1000
    resp.raise_for_status()
    return resp.json(), ms


def _combined_text(resp: dict) -> str:
    return " ".join([resp.get("answer_draft") or "", *(item.get("text") or "" for item in resp.get("items") or [])])


@pytest.mark.parametrize("case", json.load(open(CORPUS)))
def test_general_query_corpus(case):
    q = case["query"]
    path = "/memory/temporal" if any(word in q.lower() for word in ("pill", "medication")) else "/memory/query"
    resp, ms = post(path, {"text": q, "lang": "en"})
    print(f"{q!r} -> grounded={resp['grounded']} conf={resp['confidence']} {ms:.0f}ms")
    assert resp["grounded"] is case["grounded"]
    text = _combined_text(resp).lower()
    for needle in case.get("must_contain", []):
        assert needle.lower() in text
    for forbidden in case.get("must_not_contain", []):
        assert forbidden.lower() not in text
