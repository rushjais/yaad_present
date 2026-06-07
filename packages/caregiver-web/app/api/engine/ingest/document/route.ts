import { NextRequest, NextResponse } from "next/server";

const ENGINE_URL = process.env.MEMORY_ENGINE_URL ?? "http://localhost:8000";

export const runtime = "nodejs";
export const maxDuration = 300;

// Disable Next.js body parsing — we forward raw multipart to the engine.
export const config = { api: { bodyParser: false } };

export async function POST(req: NextRequest) {
  try {
    const form = await req.formData();
    const file = form.get("file") as File | null;
    if (!file) {
      return NextResponse.json({ error: "No file provided" }, { status: 400 });
    }

    // Rebuild multipart to forward to the engine (which expects field name "file")
    const forward = new FormData();
    forward.append("file", file, file.name);

    const res = await fetch(`${ENGINE_URL}/ingest/document`, {
      method: "POST",
      body: forward,
      // No Content-Type header — fetch sets it automatically with boundary
    });

    const text = await res.text();
    let data: unknown;
    try {
      data = text ? JSON.parse(text) : {};
    } catch {
      data = { error: text || `Memory engine returned ${res.status}` };
    }
    return NextResponse.json(data, { status: res.status });
  } catch (err) {
    console.error("[ingest/document proxy]", err);
    return NextResponse.json(
      { error: "Upload failed — engine unreachable.", created_refs: [], summary: "", raw_extraction: "" },
      { status: 502 },
    );
  }
}
