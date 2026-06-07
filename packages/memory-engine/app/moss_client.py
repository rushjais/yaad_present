"""
Moss on-device SDK client.
SDK: pip install moss  (https://docs.moss.dev/docs/reference/python/api)
Auth: MossClient(MOSS_PROJECT_ID, MOSS_PROJECT_KEY) from the Moss portal.

Architecture: SessionIndex wraps the persistent cloud index "yaad_amma".
- session() auto-loads the cloud index on first call (Amma's seeded life)
- add_docs: instant in-memory upsert, async push to cloud -> powers add-fact-live
- query: in-memory, ~1-10ms (Moss sub-10ms guarantee)

Pattern: https://docs.moss.dev/docs/build/live-call-context
"""
from __future__ import annotations

import asyncio
from typing import Any

from .config import settings


class _MossWrapper:
    """Thin wrapper around Moss SessionIndex."""

    def __init__(self) -> None:
        self._client = None
        self._session = None
        self._lock = asyncio.Lock()
        self._known_doc_ids: set[str] = set()

    def id(self) -> int:
        return id(self)

    def doc_count(self) -> int:
        return len(self._known_doc_ids)

    async def _ensure(self) -> Any:
        if self._session is not None:
            return self._session
        async with self._lock:
            if self._session is not None:
                return self._session
            from moss import MossClient
            self._client = MossClient(
                settings.moss_project_id,
                settings.moss_project_key,
            )
            # Resumes existing cloud index if it exists, else starts empty
            self._session = await self._client.session(
                index_name=settings.moss_index,
            )
        return self._session

    @staticmethod
    def _clean_meta(metadata: dict[str, Any]) -> dict[str, str]:
        """Flatten metadata to str->str since Moss (PyO3) only accepts string values."""
        import json
        return {k: v if isinstance(v, str) else json.dumps(v) for k, v in metadata.items()}

    async def upsert(self, ref: str, text: str, metadata: dict[str, Any]) -> None:
        """Instant in-memory upsert — no network call. Powers add-fact-live."""
        from moss import DocumentInfo, MutationOptions
        session = await self._ensure()
        await session.add_docs(
            [DocumentInfo(id=ref, text=text, metadata=self._clean_meta(metadata))],
            MutationOptions(upsert=True),
        )
        self._known_doc_ids.add(ref)
        asyncio.create_task(self._push())

    async def upsert_batch(self, items: list[dict]) -> None:
        """Batch upsert for seeding. Each item: {id, text, metadata}."""
        from moss import DocumentInfo, MutationOptions
        session = await self._ensure()
        docs = [
            DocumentInfo(
                id=it["id"],
                text=it["text"],
                metadata=self._clean_meta(it.get("metadata", {})),
            )
            for it in items
        ]
        await session.add_docs(docs, MutationOptions(upsert=True))
        self._known_doc_ids.update(str(it["id"]) for it in items)
        asyncio.create_task(self._push())

    async def query(
        self,
        text: str,
        top_k: int = 10,
        lang: str = "en",
        filters: dict | None = None,
    ) -> list[dict]:
        """
        In-memory semantic search. ~1-10ms.
        lang param reserved for future multilingual add-on — currently ignored.
        Returns list of {id, text, score, metadata}.
        """
        from moss import QueryOptions
        session = await self._ensure()
        opts = QueryOptions(top_k=top_k)
        if filters:
            opts.filter = filters
        result = await session.query(text, opts)
        import json
        out = []
        for doc in result.docs:
            meta = doc.metadata or "{}"
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            # _clean_meta json-serialized nested dicts (Moss only accepts str→str).
            # Re-parse so callers see the original structure (e.g. provenance dict).
            if isinstance(meta, dict):
                for k, v in list(meta.items()):
                    if isinstance(v, str) and v.startswith(("{", "[")):
                        try:
                            meta[k] = json.loads(v)
                        except Exception:
                            pass
            out.append({"id": doc.id, "text": doc.text or "", "score": doc.score, "metadata": meta})
        return out

    async def _push(self) -> None:
        try:
            session = await self._ensure()
            await session.push_index()
        except Exception:
            pass

    async def ping(self) -> bool:
        try:
            from moss import QueryOptions
            session = await self._ensure()
            await session.query("ping", QueryOptions(top_k=1))
            return True
        except Exception:
            return False

    async def create_index_if_needed(self) -> None:
        """session() handles index creation automatically."""
        await self._ensure()


moss = _MossWrapper()
