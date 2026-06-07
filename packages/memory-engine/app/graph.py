from __future__ import annotations


async def load_cache(*, force: bool = False) -> None:
    from .edges_cache import edges_cache

    await edges_cache.load(force=force)
