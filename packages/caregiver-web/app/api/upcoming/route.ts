import { NextResponse } from "next/server";

export interface UpcomingEvent {
  id: string;
  title: string;
  kind: string;
  start_ts: string;
  notes: string | null;
}

export async function GET() {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) {
    return NextResponse.json({ events: [] });
  }

  const now = new Date().toISOString();
  const weekOut = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();

  const res = await fetch(
    `${url}/rest/v1/events?select=id,title,kind,start_ts,notes&start_ts=gte.${now}&start_ts=lte.${weekOut}&order=start_ts.asc`,
    { headers: { apikey: key, Authorization: `Bearer ${key}` } },
  );

  if (!res.ok) return NextResponse.json({ events: [] });
  const raw: UpcomingEvent[] = await res.json();

  // Deduplicate by title — keep earliest start_ts per title
  const seen = new Set<string>();
  const deduped = raw.filter((e) => {
    const key = e.title.trim().toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  return NextResponse.json({ events: deduped.slice(0, 5) });
}
