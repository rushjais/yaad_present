import { NextResponse } from "next/server";
import { AccessToken } from "livekit-server-sdk";

export async function GET() {
  const apiKey = process.env.LIVEKIT_API_KEY;
  const apiSecret = process.env.LIVEKIT_API_SECRET;
  const wsUrl = process.env.LIVEKIT_URL;
  const room = process.env.LIVEKIT_ROOM ?? "yaad-demo";

  if (!apiKey || !apiSecret || !wsUrl) {
    return NextResponse.json({ error: "LiveKit not configured" }, { status: 500 });
  }

  const at = new AccessToken(apiKey, apiSecret, {
    identity: `user-${Date.now()}`,
    name: "User",
  });
  at.addGrant({ roomJoin: true, room, canPublish: true, canSubscribe: true });

  const token = await at.toJwt();
  return NextResponse.json({ token, url: wsUrl, room });
}
