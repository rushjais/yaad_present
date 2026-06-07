import { NextResponse } from "next/server";
import OpenAI from "openai";

export interface PriorityItem {
  title: string;
  kind: string;
  start_ts: string;
  reason: string;
}

async function fetchAllItems(): Promise<{ title: string; kind: string; start_ts: string }[]> {
  const url = process.env.SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_KEY;
  if (!url || !key) return [];

  const now = new Date().toISOString();
  const weekOut = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000).toISOString();

  const [eventsRes, medsRes] = await Promise.all([
    fetch(
      `${url}/rest/v1/events?select=title,kind,start_ts&start_ts=gte.${now}&start_ts=lte.${weekOut}&order=start_ts.asc`,
      { headers: { apikey: key, Authorization: `Bearer ${key}` } },
    ),
    fetch(
      `${url}/rest/v1/medications?select=name,schedule_rrule`,
      { headers: { apikey: key, Authorization: `Bearer ${key}` } },
    ),
  ]);

  const events = eventsRes.ok ? await eventsRes.json() : [];
  const meds = medsRes.ok ? await medsRes.json() : [];

  const seen = new Set<string>();
  const deduped = (events as { title: string; kind: string; start_ts: string }[]).filter((e) => {
    const k = e.title.trim().toLowerCase();
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });

  const medItems = (meds as { name: string; schedule_rrule: string }[]).map((m) => ({
    title: m.name,
    kind: "medication",
    start_ts: now,
  }));

  return [...deduped, ...medItems];
}

export async function GET() {
  const apiKey = process.env.OPENAI_API_KEY?.trim();
  if (!apiKey) return NextResponse.json({ items: [] });

  const candidates = await fetchAllItems();
  if (candidates.length === 0) return NextResponse.json({ items: [] });

  const client = new OpenAI({ apiKey });

  const list = candidates
    .map((c, i) => `${i + 1}. [${c.kind}] ${c.title}`)
    .join("\n");

  const completion = await client.chat.completions.create({
    model: "gpt-4o-mini",
    response_format: { type: "json_object" },
    messages: [
      {
        role: "system",
        content:
          "You are a caregiver assistant for someone with early dementia. Rank the provided items by how urgently a caregiver should attend to them — health and safety first (medications, medical appointments), then family connection (close family visits), then social events. Return JSON: { \"top4\": [ { \"index\": <1-based>, \"reason\": \"<one short sentence why this matters\" } ] }",
      },
      {
        role: "user",
        content: `Here are today's items for Amma:\n${list}\n\nReturn the 4 most important by caregiver priority.`,
      },
    ],
  });

  let top4: { index: number; reason: string }[] = [];
  try {
    const parsed = JSON.parse(completion.choices[0].message.content ?? "{}");
    top4 = parsed.top4 ?? [];
  } catch {
    return NextResponse.json({ items: [] });
  }

  const items: PriorityItem[] = top4
    .map(({ index, reason }) => {
      const c = candidates[index - 1];
      if (!c) return null;
      return { title: c.title, kind: c.kind, start_ts: c.start_ts, reason };
    })
    .filter((x): x is PriorityItem => x !== null);

  return NextResponse.json({ items });
}
