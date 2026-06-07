import { NextRequest, NextResponse } from "next/server";

const VISION_URL = process.env.VISION_SERVER_URL ?? "http://localhost:8765";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const r = await fetch(`${VISION_URL}/match`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const text = await r.text();
    try {
      return NextResponse.json(JSON.parse(text), { status: r.status });
    } catch {
      return NextResponse.json({ error: `Vision server error: ${text.slice(0, 200)}` }, { status: 502 });
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : "Unknown error";
    if (msg.includes("ECONNREFUSED") || msg.includes("fetch failed")) {
      return NextResponse.json(
        { error: "Vision server unreachable. Run: YAAD_DEMO_MODE=1 ~/anaconda3/bin/python3 -m app.vision_server" },
        { status: 503 }
      );
    }
    return NextResponse.json({ error: msg }, { status: 500 });
  }
}
