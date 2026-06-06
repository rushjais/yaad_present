"""
Moss client abstraction.
[CONFIRM] at office hours: on-device/WASM vs cloud, exact SDK calls, cross-lingual embeddings.

Current impl: REST API against MOSS_BASE_URL.
If Moss provides a Python SDK, swap _request() for the SDK calls — interface stays the same.

On-device mode: set MOSS_BASE_URL=http://localhost:7532 (WASM sidecar port — [CONFIRM]).
Cloud mode: set MOSS_BASE_URL=https://api.getmoss.dev and MOSS_API_KEY.
"""
from __future__ import annotations

import time
from typing import Any

import httpx

from .config import settings


class MossClient:
    def __init__(self) -> None:
        self._base = settings.moss_base_url.rstrip("/")
        self._key = settings.moss_api_key
        self._index = settings.moss_index

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._key:
            h["Authorization"] = f"Bearer {self._key}"
        return h

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.request(
                method,
                f"{self._base}{path}",
                headers=self._headers(),
                **kwargs,
            )
            resp.raise_for_status()
            return resp.json()

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    async def upsert(self, ref: str, text: str, metadata: dict[str, Any]) -> None:
        """Index or update a single item. Instant — this is Moss's core value."""
        await self._request(
            "POST",
            f"/indexes/{self._index}/upsert",
            json={"id": ref, "text": text, "metadata": metadata},
        )

    async def upsert_batch(self, items: list[dict]) -> None:
        """Batch upsert for seeding. Each item: {id, text, metadata}."""
        await self._request(
            "POST",
            f"/indexes/{self._index}/upsert_batch",
            json={"items": items},
        )

    async def query(
        self,
        text: str,
        top_k: int = 10,
        lang: str = "en",
        filters: dict | None = None,
    ) -> list[dict]:
        """
        Semantic search. Returns list of {id, text, score, metadata}.
        Cross-lingual embeddings [CONFIRM] — Moss should handle Hindi queries
        matching English-stored items natively.
        """
        body: dict[str, Any] = {
            "query": text,
            "top_k": top_k,
            "lang": lang,
        }
        if filters:
            body["filters"] = filters
        result = await self._request(
            "POST",
            f"/indexes/{self._index}/query",
            json=body,
        )
        return result.get("results", [])

    async def delete(self, ref: str) -> None:
        await self._request("DELETE", f"/indexes/{self._index}/items/{ref}")

    async def ping(self) -> bool:
        try:
            t0 = time.perf_counter()
            await self._request("GET", "/health")
            ms = (time.perf_counter() - t0) * 1000
            return ms < 500
        except Exception:
            return False

    async def create_index_if_needed(self) -> None:
        """Create the index on first run. [CONFIRM] exact endpoint."""
        try:
            await self._request(
                "POST",
                "/indexes",
                json={"name": self._index, "multilingual": True},
            )
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 409:
                pass  # already exists
            else:
                raise


moss = MossClient()
