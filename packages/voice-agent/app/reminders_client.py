"""Polls /reminders/due and puts due reminder text onto an asyncio.Queue (A5)."""

import asyncio
import logging
import os
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)
MEMORY_ENGINE_URL = os.environ.get("MEMORY_ENGINE_URL", "http://localhost:8000")


async def poll_reminders(queue: asyncio.Queue, interval_secs: int = 60) -> None:
    """Background task: check for due reminders every interval_secs.

    Caller should call asyncio.create_task(poll_reminders(queue)) and then
    drain queue items via queue.get() to inject proactive speech into the agent.
    """
    async with httpx.AsyncClient(base_url=MEMORY_ENGINE_URL, timeout=5.0) as client:
        while True:
            try:
                ts = datetime.now(timezone.utc).isoformat()
                r = await client.get(f"/reminders/due?ts={ts}")
                r.raise_for_status()
                for reminder in r.json().get("due", []):
                    await queue.put(reminder["text"])
            except Exception as e:
                logger.warning("Reminder poll error: %s", e)
            await asyncio.sleep(interval_secs)
