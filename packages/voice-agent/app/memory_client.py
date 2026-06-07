"""HTTP client to the memory-engine service (CONTRACT.md endpoints)."""

import os
import httpx

MEMORY_ENGINE_URL = os.environ.get("MEMORY_ENGINE_URL", "http://localhost:8000")


class MemoryClient:
    def __init__(self):
        self._client = httpx.AsyncClient(base_url=MEMORY_ENGINE_URL, timeout=3.0)

    async def query(self, text: str, lang: str) -> dict:
        """POST /memory/query → QueryResponse."""
        r = await self._client.post("/memory/query", json={"text": text, "lang": lang})
        r.raise_for_status()
        return r.json()

    async def temporal(self, text: str, lang: str) -> dict:
        """POST /memory/temporal → QueryResponse (routed through temporal logic)."""
        r = await self._client.post("/memory/temporal", json={"text": text, "lang": lang})
        r.raise_for_status()
        return r.json()

    async def aclose(self):
        await self._client.aclose()
