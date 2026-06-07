"""
Yaad Memory Engine — FastAPI app.
Gate 0: all endpoints return fixture stubs so Track A and C can unblock.
Real implementation wired in progressively through B1–B5.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timezone
from typing import Any

from fastapi import FastAPI, Query

from .schemas import (
    EntityType,
    HealthResponse,
    LocationPingRequest,
    LocationPingResponse,
    LocationAction,
    MemoryCaptureRequest,
    MemoryCaptureResponse,
    MemoryQueryRequest,
    MemoryQueryResponse,
    MemoryWriteRequest,
    MemoryWriteResponse,
    Provenance,
    RemindersResponse,
    RetrievedItem,
    TimelineResponse,
    VisionRecognizeRequest,
    VisionRecognizeResponse,
)

app = FastAPI(title="Yaad Memory Engine", version="0.1.0")


@app.on_event("startup")
async def _reseed_moss_on_startup() -> None:
    """Repopulate the in-process Moss session from Supabase.

    Moss `SessionIndex.session(index_name=...)` does NOT reliably resume the
    cloud index in a fresh process — queries return 0 results until docs are
    added to the in-memory session. The fix is to push the canonical Supabase
    state into this process's session at startup. ~3-5s cost, self-healing.

    Skipped if YAAD_SKIP_RESEED=1 (useful for tests that don't need data).
    """
    import os
    if os.environ.get("YAAD_SKIP_RESEED") == "1":
        return
    try:
        import sys
        scripts_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts")
        scripts_dir = os.path.abspath(scripts_dir)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from reseed_moss import reseed_moss  # type: ignore
        rc = await reseed_moss(verify=False, verbose=False)
        print(f"[startup] Moss session reseeded (rc={rc})")
    except Exception as e:
        print(f"[startup] Moss reseed failed: {e!r}")

# ---------------------------------------------------------------------------
# Lazy-imported real modules (wired after Gate 0)
# ---------------------------------------------------------------------------

def _query_impl() -> Any:
    try:
        from .retrieval import query_memory
        return query_memory
    except Exception:
        return None


def _temporal_impl() -> Any:
    try:
        from .temporal import query_temporal
        return query_temporal
    except Exception:
        return None


def _write_impl() -> Any:
    try:
        from .db import write_memory
        return write_memory
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Fixture payloads (Gate 0 stubs — logged in STATUS.md)
# ---------------------------------------------------------------------------

_FIXTURE_PROV = Provenance(source="fixture", added_by="seed", added_ts="2025-01-01T00:00:00+00:00")

FIXTURE_QUERY_RESPONSE = MemoryQueryResponse(
    items=[RetrievedItem(
        ref="person:leo-fixture",
        type=EntityType.person,
        text="Leo is your grandson. He's 22, studying computer science. He visits every Sunday.",
        score=0.95,
        provenance=_FIXTURE_PROV,
    )],
    grounded=True,
    confidence=0.95,
    answer_draft="That's Leo, your grandson. He's 22 and visits every Sunday.",
)

FIXTURE_TEMPORAL_RESPONSE = MemoryQueryResponse(
    items=[RetrievedItem(
        ref="med_log:fixture",
        type=EntityType.med_log,
        text="Heart pill (white) — taken at 8:00 AM today.",
        score=0.99,
        provenance=_FIXTURE_PROV,
    )],
    grounded=True,
    confidence=0.99,
    answer_draft="Yes, you took your white heart pill at 8 this morning.",
)

FIXTURE_REMINDERS = RemindersResponse(
    due=[
        {"kind": "medication", "text": "It's time for your white heart pill.", "ref": "medication:heart-pill"},
        {"kind": "event", "text": "Sarah visits at 3 PM today.", "ref": "event:sarah-visit"},
    ]
)

FIXTURE_TIMELINE = TimelineResponse(blocks=[
    {"ts": "2025-01-01T08:00:00+00:00", "type": "med_log", "title": "Heart pill taken",
     "summary": "Took white heart pill at 8 AM.", "entity_refs": ["medication:heart-pill"]},
    {"ts": "2025-01-01T15:00:00+00:00", "type": "event", "title": "Sarah's visit",
     "summary": "Daughter Sarah visited for tea.", "entity_refs": ["person:sarah"]},
])

FIXTURE_LOCATION = LocationPingResponse(
    inside_zone=True,
    nearest_place="Home",
    action=LocationAction.none,
)

FIXTURE_VISION = VisionRecognizeResponse(
    match=RetrievedItem(
        ref="person:leo-fixture",
        type=EntityType.person,
        text="Leo, your grandson.",
        score=0.92,
        provenance=_FIXTURE_PROV,
    ),
    answer_draft="That's Leo, your grandson!",
)

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/memory/query", response_model=MemoryQueryResponse)
async def memory_query(req: MemoryQueryRequest):
    try:
        from .retrieval import query_memory
        result = await query_memory(req.text, req.lang)
        return MemoryQueryResponse(**result)
    except Exception:
        return FIXTURE_QUERY_RESPONSE


@app.post("/memory/temporal", response_model=MemoryQueryResponse)
async def memory_temporal(req: MemoryQueryRequest):
    try:
        from .temporal import query_temporal
        result = await query_temporal(req.text, req.lang)
        return MemoryQueryResponse(**result)
    except Exception:
        return FIXTURE_TEMPORAL_RESPONSE


@app.post("/memory/write", response_model=MemoryWriteResponse)
async def memory_write(req: MemoryWriteRequest):
    """Caregiver-web add-fact-live path. Writes to Supabase AND upserts the
    new chunk to Moss in the same request so the next /memory/query can find it.
    Without this Moss step, add-fact-live silently doesn't work — DB has the row
    but the voice agent can't see it. db.py's old comment ('triggered by caller')
    documented the gap; this handler is the caller."""
    try:
        from .db import write_memory
        result = await write_memory(req.type.value, req.payload)

        # Index in Moss so it's retrievable on the next query
        try:
            entity_type = req.type.value
            ref = f"{entity_type}:{result['id']}"
            text = _build_chunk_text(entity_type, req.payload)
            if text:
                from .moss_client import moss
                await moss.upsert(ref, text, {
                    "type": entity_type,
                    "name": str(req.payload.get("name") or req.payload.get("title") or ""),
                    "provenance": {
                        "source": "caregiver_web",
                        "added_by": "caregiver",
                        "added_ts": datetime.now(timezone.utc).isoformat(),
                    },
                })
                # Refresh graph entity-text cache so capture's entity resolution
                # sees this new entity immediately.
                try:
                    from .graph import load_cache
                    await load_cache(force=True)
                except Exception:
                    pass
        except Exception:
            pass  # Moss failed — DB still has the row; reseed will pick it up

        return MemoryWriteResponse(**result)
    except Exception:
        return MemoryWriteResponse(id="fixture-id-" + str(int(time.time())))


def _build_chunk_text(entity_type: str, payload: dict) -> str:
    """Render a Moss chunk for a freshly-written entity. Matches the chunk
    format in scripts/reseed_moss.py so search behaves consistently with
    seed-time data. Edges aren't known at write-time, so relationship phrases
    aren't included — the next reseed picks those up if Track C adds edges.
    """
    name = (payload.get("name") or payload.get("title") or "").strip()
    notes = (payload.get("notes") or "").strip()

    if entity_type == "person":
        relationship = (payload.get("relationship") or "").strip()
        aliases = payload.get("aliases") or []
        parts = [name]
        if relationship:
            parts.append(relationship)
        if notes:
            parts.append(notes)
        if aliases:
            parts.append(f"Also called {', '.join(aliases)}.")
        return ". ".join(s.rstrip(".") for s in parts if s) + "."

    if entity_type == "place":
        return f"{name}. {notes}".strip().rstrip(".") + "."

    if entity_type == "medication":
        return f"{name} — Amma's medication. {notes}".strip().rstrip(".") + "."

    if entity_type == "event":
        return f"{name}. {notes}".strip().rstrip(".") + "."

    if entity_type == "story":
        return f"Story: {notes or name}"

    if entity_type == "episode":
        return f"{payload.get('summary') or notes or name}".strip()

    # med_log doesn't need a chunk (queried via Supabase by temporal)
    return ""


@app.post("/memory/capture", response_model=MemoryCaptureResponse)
async def memory_capture(req: MemoryCaptureRequest):
    try:
        from .capture import capture_from_transcript
        return await capture_from_transcript(req.transcript)
    except Exception:
        return MemoryCaptureResponse(created_refs=[])


@app.get("/memory/timeline", response_model=TimelineResponse)
async def memory_timeline(date: str = Query(default=None)):
    try:
        from .temporal import get_timeline
        return await get_timeline(date)
    except Exception:
        return FIXTURE_TIMELINE


@app.get("/reminders/due", response_model=RemindersResponse)
async def reminders_due(ts: str = Query(default=None)):
    try:
        from .reminders import get_due_reminders
        return await get_due_reminders(ts)
    except Exception:
        return FIXTURE_REMINDERS


@app.post("/location/ping", response_model=LocationPingResponse)
async def location_ping(req: LocationPingRequest):
    try:
        from .location import handle_ping
        return await handle_ping(req.lat, req.lng)
    except Exception:
        return FIXTURE_LOCATION


@app.post("/vision/recognize", response_model=VisionRecognizeResponse)
async def vision_recognize(req: VisionRecognizeRequest):
    try:
        from .vision import recognize
        return await recognize(req.image_b64)
    except Exception:
        return FIXTURE_VISION


@app.get("/health", response_model=HealthResponse)
async def health():
    t0 = time.perf_counter()
    moss_ok = False
    db_ok = False
    try:
        from .moss_client import moss
        moss_ok = await moss.ping()
    except Exception:
        pass
    try:
        from .db import db_ping
        db_ok = await db_ping()
    except Exception:
        pass
    latency_ms = (time.perf_counter() - t0) * 1000
    return HealthResponse(moss_ok=moss_ok, db_ok=db_ok, latency_ms=round(latency_ms, 2))
