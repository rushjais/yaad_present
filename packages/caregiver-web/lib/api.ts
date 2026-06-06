import type {
  HealthResponse,
  LocationPingRequest,
  LocationPingResponse,
  MemoryCaptureRequest,
  MemoryCaptureResponse,
  MemoryQueryResponse,
  MemoryWriteRequest,
  MemoryWriteResponse,
  RemindersResponse,
  TimelineResponse,
} from "./types";

// All calls go through Next.js rewrites → memory-engine.
// The rewrite strips /api/engine and forwards to http://localhost:8000.
const BASE = "/api/engine";

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${path} ${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

async function get<T>(path: string, params?: Record<string, string>): Promise<T> {
  const url = new URL(`${BASE}${path}`, "http://localhost");
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));
  const res = await fetch(url.pathname + url.search);
  if (!res.ok) throw new Error(`${path} ${res.status}: ${await res.text()}`);
  return res.json() as Promise<T>;
}

export function queryMemory(text: string): Promise<MemoryQueryResponse> {
  return post("/memory/query", { text, lang: "en" });
}

export function queryTemporal(text: string): Promise<MemoryQueryResponse> {
  return post("/memory/temporal", { text, lang: "en" });
}

export function writeMemory(req: MemoryWriteRequest): Promise<MemoryWriteResponse> {
  return post("/memory/write", req);
}

export function captureMemory(transcript: string): Promise<MemoryCaptureResponse> {
  return post<MemoryCaptureResponse>("/memory/capture", {
    transcript,
  } satisfies MemoryCaptureRequest);
}

export function getTimeline(date?: string): Promise<TimelineResponse> {
  return get("/memory/timeline", date ? { date } : undefined);
}

export function getReminders(ts?: string): Promise<RemindersResponse> {
  return get("/reminders/due", ts ? { ts } : undefined);
}

export function pingLocation(req: LocationPingRequest): Promise<LocationPingResponse> {
  return post("/location/ping", req);
}

export function getHealth(): Promise<HealthResponse> {
  return get("/health");
}
