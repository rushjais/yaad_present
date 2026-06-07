from __future__ import annotations

import os
import time

import httpx

BASE = os.environ.get("YAAD_TEST_BASE", "http://localhost:8000")


def _samples(query: str, n: int = 20) -> list[float]:
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        resp = httpx.post(f"{BASE}/memory/query", json={"text": query, "lang": "en"}, timeout=15)
        out.append((time.perf_counter() - t0) * 1000)
        resp.raise_for_status()
    return sorted(out)


def _p95(samples: list[float]) -> float:
    return samples[int(len(samples) * 0.95) - 1]


def test_structural_queries_are_fast_client_side():
    # Client-side guard is looser than the server-side target because HTTP
    # overhead and local machine load are included.
    for query in ["Who is Leo?", "Who is my grandson?", "What's my favorite music?"]:
        assert _p95(_samples(query, 10)) < 200
