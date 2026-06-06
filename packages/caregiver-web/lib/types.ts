// Generated from packages/shared/contract.openapi.json
// Regenerate: npm run generate-types
// DO NOT hand-edit — run the generator after any schema change.

export type EntityType =
  | "person"
  | "place"
  | "event"
  | "medication"
  | "med_log"
  | "story"
  | "episode";

export type MemoryWriteType = EntityType;

export type LocationAction = "none" | "reassure" | "alert";

export interface Provenance {
  source: string;
  added_by: string;
  added_ts: string; // ISO 8601
}

export interface RetrievedItem {
  ref: string;
  type: EntityType;
  text: string;
  score: number;
  provenance: Provenance;
}

// --- Query ---

export interface MemoryQueryRequest {
  text: string;
  lang?: string; // default "en"
}

export interface MemoryQueryResponse {
  items: RetrievedItem[];
  grounded: boolean;
  confidence: number;
  answer_draft?: string | null;
}

// --- Write ---
// Discriminated union so callers get payload type-checking per entity type.

export interface PersonPayload {
  name: string;
  relationship: string;
  aliases?: string[];
  notes?: string;
  photo_ref?: string;
  is_reassurance_contact?: boolean;
  alert_priority?: number;
}

export interface PlacePayload {
  name: string;
  kind: "home" | "familiar" | "other";
  lat?: number;
  lng?: number;
  notes?: string;
}

export interface EventPayload {
  title: string;
  kind: string;
  start_ts: string; // ISO 8601
  end_ts?: string;
  place_id?: string;
  participant_ids?: string[];
  notes?: string;
}

export interface MedicationPayload {
  name: string;
  schedule_rrule: string;
  notes?: string;
}

export interface MedLogPayload {
  medication_id: string;
  taken_ts: string; // ISO 8601
  source: string;
}

export interface StoryPayload {
  title: string;
  text: string;
  people_ids?: string[];
  occurred_ts?: string;
}

export interface EpisodePayload {
  title: string;
  occurred_ts?: string;
  kind: string;
  entity_refs?: string[];
  summary: string;
}

export type MemoryWriteRequest =
  | { type: "person"; payload: PersonPayload }
  | { type: "place"; payload: PlacePayload }
  | { type: "event"; payload: EventPayload }
  | { type: "medication"; payload: MedicationPayload }
  | { type: "med_log"; payload: MedLogPayload }
  | { type: "story"; payload: StoryPayload }
  | { type: "episode"; payload: EpisodePayload };

export interface MemoryWriteResponse {
  id: string;
}

// --- Capture ---

export interface MemoryCaptureRequest {
  transcript: string;
}

export interface MemoryCaptureResponse {
  created_refs: string[];
}

// --- Timeline ---

export interface TimelineBlock {
  ts: string; // ISO 8601
  type: string;
  title: string;
  summary: string;
  entity_refs?: string[];
}

export interface TimelineResponse {
  blocks: TimelineBlock[];
}

// --- Reminders ---

export interface ReminderItem {
  kind: string;
  text: string;
  ref: string;
}

export interface RemindersResponse {
  due: ReminderItem[];
}

// --- Location ---

export interface LocationPingRequest {
  lat: number;
  lng: number;
}

export interface LocationPingResponse {
  inside_zone: boolean;
  nearest_place: string | null;
  action: LocationAction;
  reassurance_text?: string | null;
  contacts?: string[] | null;
}

// --- Vision ---

export interface VisionRecognizeRequest {
  image_b64: string;
}

export interface VisionRecognizeResponse {
  match: RetrievedItem | null;
  answer_draft: string;
}

// --- Health ---

export interface HealthResponse {
  moss_ok: boolean;
  db_ok: boolean;
  latency_ms: number;
}
