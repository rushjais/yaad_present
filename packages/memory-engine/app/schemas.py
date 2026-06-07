"""
Pydantic data models — single source of truth for the Yaad contract.
Generated contract.openapi.yaml from this file; caregiver-web types.ts from that.
"""
from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PlaceKind(str, Enum):
    home = "home"
    familiar = "familiar"
    other = "other"


class EntityType(str, Enum):
    person = "person"
    place = "place"
    event = "event"
    medication = "medication"
    med_log = "med_log"
    story = "story"
    episode = "episode"


class AlertKind(str, Enum):
    wander = "wander"
    lost = "lost"


class AlertStatus(str, Enum):
    active = "active"
    resolved = "resolved"


class LocationAction(str, Enum):
    none = "none"
    reassure = "reassure"
    alert = "alert"


class MemoryWriteType(str, Enum):
    person = "person"
    place = "place"
    event = "event"
    medication = "medication"
    med_log = "med_log"
    story = "story"
    episode = "episode"


# ---------------------------------------------------------------------------
# Provenance (attached to every embeddable row)
# ---------------------------------------------------------------------------

class Provenance(BaseModel):
    source: str
    added_by: str
    added_ts: datetime


# ---------------------------------------------------------------------------
# Core entity models
# ---------------------------------------------------------------------------

class Person(BaseModel):
    id: UUID
    name: str
    relationship: str
    aliases: list[str] = Field(default_factory=list)
    notes: str = ""
    photo_ref: str | None = None
    is_reassurance_contact: bool = False
    alert_priority: int | None = None
    provenance: Provenance | None = None


class Place(BaseModel):
    id: UUID
    name: str
    kind: PlaceKind
    lat: float | None = None
    lng: float | None = None
    notes: str = ""
    provenance: Provenance | None = None


class Event(BaseModel):
    id: UUID
    title: str
    kind: str
    start_ts: datetime
    end_ts: datetime | None = None
    place_id: UUID | None = None
    participant_ids: list[UUID] = Field(default_factory=list)
    notes: str = ""
    provenance: Provenance | None = None


class Medication(BaseModel):
    id: UUID
    name: str
    schedule_rrule: str
    notes: str = ""
    provenance: Provenance | None = None


class MedLog(BaseModel):
    id: UUID
    medication_id: UUID
    taken_ts: datetime
    source: str
    provenance: Provenance | None = None


class Story(BaseModel):
    id: UUID
    title: str
    text: str
    people_ids: list[UUID] = Field(default_factory=list)
    occurred_ts: datetime | None = None
    provenance: Provenance | None = None


class Episode(BaseModel):
    id: UUID
    title: str
    occurred_ts: datetime
    kind: str
    entity_refs: list[str] = Field(default_factory=list)
    summary: str
    provenance: Provenance | None = None


class Edge(BaseModel):
    id: UUID
    from_ref: str
    to_ref: str
    type: str
    weight: float = 1.0


class Interaction(BaseModel):
    id: UUID
    ts: datetime
    lang: str
    query: str
    response: str
    retrieved_refs: list[str] = Field(default_factory=list)
    grounded: bool
    confidence: float


class SafeZone(BaseModel):
    id: UUID
    center_place_id: UUID
    radius_m: float
    contact_ids_ordered: list[UUID] = Field(default_factory=list)


class LocationPing(BaseModel):
    id: UUID
    ts: datetime
    lat: float
    lng: float
    inside_zone: bool


class Alert(BaseModel):
    id: UUID
    ts: datetime
    kind: AlertKind
    lat: float
    lng: float
    contacts_notified: list[UUID] = Field(default_factory=list)
    status: AlertStatus = AlertStatus.active


# ---------------------------------------------------------------------------
# API request/response shapes
# ---------------------------------------------------------------------------

class RetrievedItem(BaseModel):
    ref: str
    type: EntityType
    text: str
    score: float
    provenance: Provenance


# POST /memory/query  or  POST /memory/temporal
class MemoryQueryRequest(BaseModel):
    text: str
    lang: str = "en"


class MemoryQueryResponse(BaseModel):
    items: list[RetrievedItem]
    grounded: bool
    confidence: float
    answer_draft: str | None = None


# POST /memory/write
class MemoryWriteRequest(BaseModel):
    type: MemoryWriteType
    payload: dict[str, Any]


class MemoryWriteResponse(BaseModel):
    id: str


# POST /memory/capture
class MemoryCaptureRequest(BaseModel):
    transcript: str


class MemoryCaptureResponse(BaseModel):
    created_refs: list[str]


# GET /memory/timeline
class TimelineBlock(BaseModel):
    ts: datetime
    type: str
    title: str
    summary: str
    entity_refs: list[str] = Field(default_factory=list)


class TimelineResponse(BaseModel):
    blocks: list[TimelineBlock]


# GET /reminders/due
class ReminderItem(BaseModel):
    kind: str  # "medication" | "event"
    text: str
    ref: str


class RemindersResponse(BaseModel):
    due: list[ReminderItem]


# POST /location/ping
class LocationPingRequest(BaseModel):
    lat: float
    lng: float


class LocationPingResponse(BaseModel):
    inside_zone: bool
    nearest_place: str | None
    action: LocationAction
    reassurance_text: str | None = None
    contacts: list[str] | None = None


# POST /vision/recognize
class VisionRecognizeRequest(BaseModel):
    image_b64: str


class VisionRecognizeResponse(BaseModel):
    match: RetrievedItem | None
    answer_draft: str


# POST /ingest/document  (multipart upload — see main.py)
class IngestDocumentResponse(BaseModel):
    created_refs: list[str]
    summary: str
    raw_extraction: str = ""


# GET /health
class HealthResponse(BaseModel):
    moss_ok: bool
    db_ok: bool
    latency_ms: float
