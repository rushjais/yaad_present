from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, "packages/memory-engine")


def test_timeline_filters_by_requested_date(monkeypatch):
    from app import db
    from app.temporal import get_timeline

    captured = {}

    async def fake_med_logs(start_ts: str, end_ts: str, medication_id=None):
        captured["med_start"] = start_ts
        captured["med_end"] = end_ts
        return []

    async def fake_events(start_ts: str, end_ts: str, participant_id=None):
        captured["event_start"] = start_ts
        captured["event_end"] = end_ts
        return [{
            "id": "eb6da769-2849-4bb2-8338-1eca2b63d2c3",
            "title": "Sam is coming to visit her and get a drink on Wednesday",
            "start_ts": "2026-06-10T14:00:00+00:00",
            "notes": "",
        }]

    monkeypatch.setattr(db, "fetch_med_logs_in_window", fake_med_logs)
    monkeypatch.setattr(db, "fetch_events_in_window", fake_events)

    result = asyncio.run(get_timeline("2026-06-10"))

    assert captured["event_start"].startswith("2026-06-10T04:00:00")
    assert captured["event_end"].startswith("2026-06-11T03:59:59")
    assert captured["med_start"] == captured["event_start"]
    assert captured["med_end"] == captured["event_end"]
    assert [block.title for block in result.blocks] == [
        "Sam is coming to visit her and get a drink on Wednesday"
    ]
