import { NextResponse } from "next/server";

const SUPABASE_URL = process.env.SUPABASE_URL!;
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_KEY!;

function sbFetch(table: string, select: string, extra = "") {
  return fetch(`${SUPABASE_URL}/rest/v1/${table}?select=${select}${extra}`, {
    headers: {
      apikey: SUPABASE_KEY,
      Authorization: `Bearer ${SUPABASE_KEY}`,
      Prefer: "return=representation",
    },
    cache: "no-store",
  }).then((r) => r.json());
}

export type SafetyContact = {
  id: string;
  name: string;
  relationship: string;
  notes: string;
};

export type SafetyAlert = {
  id: string;
  ts: string;
  query: string;    // what Amma asked
  response: string; // the exact SMS message sent to caregiver
};

export type SafetyData = {
  contacts: SafetyContact[];
  alerts: SafetyAlert[];
  recipient_email: string;
};

export async function GET() {
  const [contacts, alerts] = await Promise.all([
    sbFetch("persons", "id,name,relationship,notes", "&is_reassurance_contact=eq.true"),
    // interactions where grounded=false and response is not null = caregiver alerts sent
    sbFetch("interactions", "id,ts,query,response", "&grounded=eq.false&response=not.is.null&order=ts.desc&limit=30"),
  ]);

  return NextResponse.json({
    contacts: Array.isArray(contacts) ? contacts : [],
    alerts: Array.isArray(alerts) ? alerts : [],
    recipient_email: process.env.YAAD_DEMO_RECIPIENT_EMAIL ?? "",
  } satisfies SafetyData);
}
