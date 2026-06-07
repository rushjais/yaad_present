import { NextRequest, NextResponse } from "next/server";

const VISION_URL = process.env.VISION_SERVER_URL ?? "http://localhost:8765";

export async function POST(req: NextRequest) {
  const body = await req.json();
  try {
    const r = await fetch(`${VISION_URL}/match`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    return NextResponse.json(data, { status: r.status });
  } catch {
    return NextResponse.json({ error: "Vision server unreachable. Is it running at " + VISION_URL + "?" }, { status: 503 });
  }
}
