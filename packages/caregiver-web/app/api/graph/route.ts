import { NextResponse } from "next/server";

const SUPABASE_URL = process.env.SUPABASE_URL!;
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_KEY!;

function sbFetch(table: string, select: string) {
  return fetch(`${SUPABASE_URL}/rest/v1/${table}?select=${select}`, {
    headers: {
      apikey: SUPABASE_KEY,
      Authorization: `Bearer ${SUPABASE_KEY}`,
    },
    cache: "no-store",
  }).then((r) => r.json());
}

type RawPerson = { id: string; name: string; relationship: string };
type RawPlace  = { id: string; name: string; kind: string };
type RawEdge   = { from_ref: string; to_ref: string; type: string; weight: number };

export async function GET() {
  const [persons, places, edges] = await Promise.all([
    sbFetch("persons", "id,name,relationship") as Promise<RawPerson[]>,
    sbFetch("places",  "id,name,kind")         as Promise<RawPlace[]>,
    sbFetch("edges",   "from_ref,to_ref,type,weight") as Promise<RawEdge[]>,
  ]);

  // Deduplicate by (label, type) — keep first occurrence of each unique name
  const seenPersons = new Map<string, string>(); // name → canonical ref
  const seenPlaces  = new Map<string, string>();

  const nodes: { id: string; label: string; type: string; sub: string }[] = [];

  const testPattern = /^(TestPerson|Bibhuti)_[0-9a-fA-F]+$/;
  for (const p of persons) {
    if (testPattern.test(p.name)) continue;
    const ref = `person:${p.id}`;
    if (!seenPersons.has(p.name)) {
      seenPersons.set(p.name, ref);
      nodes.push({ id: ref, label: p.name, type: "person", sub: p.relationship });
    }
  }
  for (const p of places) {
    const ref = `place:${p.id}`;
    if (!seenPlaces.has(p.name)) {
      seenPlaces.set(p.name, ref);
      nodes.push({ id: ref, label: p.name, type: "place", sub: p.kind });
    }
  }

  const validIds = new Set(nodes.map((n) => n.id));
  const links = edges
    .filter((e) => validIds.has(e.from_ref) && validIds.has(e.to_ref))
    .map((e) => ({ source: e.from_ref, target: e.to_ref, type: e.type, weight: e.weight }));

  return NextResponse.json({ nodes, links });
}
