"""
Yaad Memory Engine — FastAPI app.
Gate 0: all endpoints return fixture stubs so Track A and C can unblock.
Real implementation wired in progressively through B1–B5.
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime, timezone
from typing import Any

# Load .env into process env so modules using raw os.getenv (e.g.
# location.py reading TWILIO_*, YAAD_DEMO_RECIPIENT) see the values.
# pydantic-settings reads .env on its own, but raw os.getenv doesn't.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from fastapi import FastAPI, File, Query, UploadFile

from .schemas import (
    EntityType,
    HealthResponse,
    IngestDocumentResponse,
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

        # Warm graph entity-text cache (used by capture + /memory/write). Saves
        # ~300ms cold-cache latency on the first add-fact-live request, which
        # used to push the smoke test just over the <1s contract.
        try:
            from .graph import load_cache
            await load_cache()
            print("[startup] graph entity cache warmed")
        except Exception as e:
            print(f"[startup] graph cache warm failed (non-fatal): {e!r}")
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

        if req.type.value == "event":
            try:
                participant_ids = await _resolve_event_participants(req.payload)
                if participant_ids:
                    from .db import update_event_participants
                    await update_event_participants(result["id"], participant_ids)
                    req.payload["participant_ids"] = participant_ids
            except Exception:
                pass

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


PERSON_RESOLUTION_THRESHOLD = 0.85


async def _resolve_event_participants(payload: dict) -> list[str]:
    """Resolve people mentioned in event title/notes into participant ids.

    Candidate extraction is intentionally conservative: capitalized name-like
    spans cover normal entries ("Sarah visit"), while known person names and
    aliases are matched case-insensitively so lowercase entries ("sarah visit")
    still backfill. Moss remains the authority for accepting a candidate.
    """
    text = " ".join(str(payload.get(k) or "") for k in ("title", "notes")).strip()
    existing = [str(p) for p in (payload.get("participant_ids") or []) if p]
    if not text:
        return existing

    candidates = await _event_person_candidates(text)
    if not candidates:
        return existing

    from .moss_client import moss

    resolved = list(existing)
    seen = set(existing)
    for candidate in candidates:
        hits = await moss.query(candidate, top_k=8)
        person_hit = _first_person_hit(candidate, hits)
        if not person_hit:
            continue

        person_id = person_hit["id"].split(":", 1)[-1]
        if person_id not in seen:
            resolved.append(person_id)
            seen.add(person_id)

    return resolved


async def _event_person_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add(value: str) -> None:
        value = " ".join(value.split()).strip(" ,.:;!?()[]{}'\"")
        key = value.lower()
        if len(value) < 2 or key in seen:
            return
        seen.add(key)
        candidates.append(value)

    # Normal title-cased entries: "Sarah visits", "Leo lunch".
    for match in re.finditer(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", text):
        span = match.group(0)
        add(span)
        for part in span.split():
            add(part)

    # Lowercase protection: match known person names and aliases regardless of
    # how the caregiver typed them, then let Moss verify the final identity.
    try:
        from .db import fetch_persons
        for person in await fetch_persons():
            add_if_present = [person.get("name"), *(person.get("aliases") or [])]
            for name in add_if_present:
                if name and _contains_name(text, str(name)):
                    add(str(name))
    except Exception:
        pass

    return candidates[:12]


def _first_person_hit(candidate: str, hits: list[dict]) -> dict | None:
    for hit in hits:
        meta = hit.get("metadata", {}) or {}
        if meta.get("type") != "person":
            continue
        if float(hit.get("score", 0.0)) < PERSON_RESOLUTION_THRESHOLD:
            continue
        if not _hit_confirms_person_name(candidate, hit):
            continue
        return hit
    return None


def _contains_name(text: str, name: str) -> bool:
    pattern = r"(?<!\w)" + re.escape(name) + r"(?!\w)"
    return re.search(pattern, text, re.IGNORECASE) is not None


def _hit_confirms_person_name(candidate: str, hit: dict) -> bool:
    meta = hit.get("metadata", {}) or {}
    hit_name = str(meta.get("name") or "")
    hit_text = str(hit.get("text") or "")
    return (
        _contains_name(hit_text, candidate)
        or bool(hit_name and hit_name.lower() == candidate.lower())
        or bool(hit_name and _contains_name(candidate, hit_name))
    )


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


@app.post("/ingest/document", response_model=IngestDocumentResponse)
async def ingest_document(file: UploadFile = File(...)):
    """Upload a medical PDF → Unsiloed parses → Groq normalizes → records are
    written to Supabase + Moss and immediately queryable. Sponsor beat
    (§18: 'Unsiloed = ingest a medical doc into structured memory').
    """
    try:
        from .ingest import ingest_document as _ingest
        file_bytes = await file.read()
        result = await _ingest(
            file_bytes,
            file.filename or "document.pdf",
            file.content_type or "application/pdf",
        )
        return IngestDocumentResponse(**result)
    except Exception as e:
        print(f"[ingest] failed: {e!r}")
        return IngestDocumentResponse(created_refs=[], summary="", raw_extraction="")


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
