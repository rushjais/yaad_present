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
type RawEvent  = { participant_ids: string[] | null };

export async function GET() {
  const [persons, places, edges, events] = await Promise.all([
    sbFetch("persons", "id,name,relationship") as Promise<RawPerson[]>,
    sbFetch("places",  "id,name,kind")         as Promise<RawPlace[]>,
    sbFetch("edges",   "from_ref,to_ref,type,weight") as Promise<RawEdge[]>,
    sbFetch("events",  "participant_ids") as Promise<RawEvent[]>,
  ]);

  // Deduplicate by name — keep first occurrence, build a remap for duplicates
  // so edges pointing to deduped-away UUIDs still resolve.
  const seenPersons = new Map<string, string>(); // name → canonical ref
  const seenPlaces  = new Map<string, string>();
  const refRemap    = new Map<string, string>(); // duplicate ref → canonical ref

  const nodes: { id: string; label: string; type: string; sub: string }[] = [];

  const testPattern = /^(TestPerson|Bibhuti)_[0-9a-fA-F]+$/;
  for (const p of persons) {
    if (testPattern.test(p.name)) continue;
    const ref = `person:${p.id}`;
    if (!seenPersons.has(p.name)) {
      seenPersons.set(p.name, ref);
      nodes.push({ id: ref, label: p.name, type: "person", sub: p.relationship });
    } else {
      // Map this duplicate ref → canonical so edges still work
      refRemap.set(ref, seenPersons.get(p.name)!);
    }
  }
  for (const p of places) {
    const ref = `place:${p.id}`;
    if (!seenPlaces.has(p.name)) {
      seenPlaces.set(p.name, ref);
      nodes.push({ id: ref, label: p.name, type: "place", sub: p.kind });
    } else {
      refRemap.set(ref, seenPlaces.get(p.name)!);
    }
  }

  const validIds = new Set(nodes.map((n) => n.id));
  const resolve  = (ref: string) => refRemap.get(ref) ?? ref;

  // Seeded edges — remap any duplicate refs before filtering
  const seededEdgeSeen = new Set<string>();
  const links: { source: string; target: string; type: string; weight: number }[] = [];

  for (const e of edges) {
    const src = resolve(e.from_ref);
    const tgt = resolve(e.to_ref);
    if (!validIds.has(src) || !validIds.has(tgt)) continue;
    const key = `${src}→${tgt}:${e.type}`;
    if (seededEdgeSeen.has(key)) continue;
    seededEdgeSeen.add(key);
    links.push({ source: src, target: tgt, type: e.type, weight: e.weight });
  }

  // Derive edges from event participant_ids — link each participant to Amma.
  // Find Amma dynamically so the ref always matches a real node.
  const ammaNode = nodes.find((n) => n.type === "person" && (n.sub === "self" || n.label === "Amma"));
  const ammaRef  = ammaNode?.id ?? "";
  const eventEdgeSeen = new Set<string>();
  if (ammaRef) {
    for (const ev of events) {
      for (const pid of ev.participant_ids ?? []) {
        const ref = resolve(`person:${pid}`);
        if (!validIds.has(ref) || ref === ammaRef) continue;
        const key = `${ref}→${ammaRef}`;
        if (eventEdgeSeen.has(key)) continue;
        eventEdgeSeen.add(key);
        links.push({ source: ref, target: ammaRef, type: "visits", weight: 1 });
      }
    }
  }

  return NextResponse.json({ nodes, links });
}
