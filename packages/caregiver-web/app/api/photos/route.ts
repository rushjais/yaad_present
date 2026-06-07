import { NextRequest, NextResponse } from "next/server";
import path from "path";
import fs from "fs";

const REFS_DIR = path.join(process.cwd(), "..", "voice-agent", "references");
const SUPABASE_URL = process.env.SUPABASE_URL!;
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_KEY!;

const ALLOWED_EXTS = new Set([".jpg", ".jpeg", ".png", ".webp", ".bmp"]);

// GET — list existing reference photos + persons for dropdown
export async function GET() {
  // Fetch persons from Supabase
  const res = await fetch(
    `${SUPABASE_URL}/rest/v1/persons?select=id,name,relationship&order=name.asc`,
    {
      headers: { apikey: SUPABASE_KEY, Authorization: `Bearer ${SUPABASE_KEY}` },
      cache: "no-store",
    }
  );
  const persons: { id: string; name: string; relationship: string }[] = await res.json();

  // List existing reference photos (exclude README.txt)
  let photos: { filename: string; stem: string }[] = [];
  try {
    photos = fs
      .readdirSync(REFS_DIR)
      .filter((f) => ALLOWED_EXTS.has(path.extname(f).toLowerCase()))
      .map((f) => ({ filename: f, stem: path.basename(f, path.extname(f)) }));
  } catch {
    // directory may not exist yet
  }

  return NextResponse.json({ persons, photos });
}

// POST — upload a photo and assign it to a person
export async function POST(req: NextRequest) {
  const form = await req.formData();
  const file = form.get("file") as File | null;
  const personName = (form.get("person_name") as string | null)?.trim();

  if (!file) return NextResponse.json({ error: "No file" }, { status: 400 });
  if (!personName) return NextResponse.json({ error: "No person selected" }, { status: 400 });

  const ext = path.extname(file.name).toLowerCase();
  if (!ALLOWED_EXTS.has(ext)) {
    return NextResponse.json({ error: "Unsupported file type" }, { status: 400 });
  }

  // Sanitise name → filename stem (matches voice-agent convention)
  const stem = personName.toLowerCase().replace(/\s+/g, "_").replace(/[^a-z0-9_]/g, "");
  const filename = `${stem}${ext}`;
  const dest = path.join(REFS_DIR, filename);

  const buf = Buffer.from(await file.arrayBuffer());
  fs.mkdirSync(REFS_DIR, { recursive: true });
  fs.writeFileSync(dest, buf);

  return NextResponse.json({ ok: true, filename });
}
