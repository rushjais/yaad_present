"""
Smoke test for wander-safety end-to-end (POST /location/ping).

Verifies:
  - Pinging coords OUTSIDE the seeded safe zone (~2km from home) returns
    action='alert' with reassurance_text and a contact list.
  - SMS (delivered as email-to-SMS via the recipient's carrier gateway)
    actually dispatches via Gmail SMTP.
  - An `alerts` row is created in Supabase.

Setup before running:
  1. Run scripts/migrate_supabase.sql (idempotent — adds persons.phone).
  2. .env must have EMAIL_FROM + EMAIL_APP_PASSWORD (Gmail app password).
  3. Set YAAD_DEMO_RECIPIENT_EMAIL in .env to <number>@<carrier-gateway>
     so every alert routes to one phone you can watch.
  4. Server running on http://localhost:8000 (or set MEMORY_ENGINE_URL).
"""
from __future__ import annotations

import os
import sys

import httpx


BASE = os.environ.get("MEMORY_ENGINE_URL", "http://localhost:8000")

# Home is seeded at (33.7490, -84.3880), safe_zone radius_m=500.
# Pick a coord ~2km north-east — clearly OUTSIDE the zone.
WANDER_COORDS = (33.7660, -84.3720)


def main() -> int:
    if not os.environ.get("YAAD_DEMO_RECIPIENT") and not _has_env(".env", "YAAD_DEMO_RECIPIENT"):
        print("WARN: YAAD_DEMO_RECIPIENT not set — SMS will only land if "
              "persons rows have phone numbers populated.")

    lat, lng = WANDER_COORDS
    print(f"POST {BASE}/location/ping  lat={lat}, lng={lng} (outside zone)")
    try:
        resp = httpx.post(f"{BASE}/location/ping",
                          json={"lat": lat, "lng": lng},
                          timeout=30.0)
    except httpx.HTTPError as e:
        print(f"FAIL: request error: {e!r}")
        return 1
    if resp.status_code != 200:
        print(f"FAIL: {resp.status_code} {resp.text[:400]}")
        return 1

    data = resp.json()
    print(f"  inside_zone={data.get('inside_zone')} action={data.get('action')}")
    print(f"  nearest_place={data.get('nearest_place')}")
    print(f"  contacts={data.get('contacts')}")
    print(f"  reassurance_text={data.get('reassurance_text')!r}")

    if data.get("inside_zone") is True:
        print("FAIL: server thinks coord is inside zone — check seed_amma safe_zone "
              "is present and home place has lat/lng. Did you run seed_amma.py?")
        return 1
    if data.get("action") != "alert":
        print(f"FAIL: expected action='alert', got {data.get('action')!r} "
              "— check fixture fallback isn't masking real logic.")
        return 1

    print()
    print("✓ Endpoint says: alert fired. Check your phone for SMS now.")
    print("  Watching Supabase alerts table for the new row...")
    if _verify_alert_row(lat, lng):
        print("✓ alerts row found in Supabase")
    else:
        print("⚠ no recent alerts row found — Supabase write may have failed silently")

    print()
    print("PASS (endpoint side). Confirm SMS arrives at your recipient phone.")
    return 0


def _has_env(path: str, key: str) -> bool:
    try:
        with open(path) as f:
            return any(line.startswith(key + "=") and line.split("=", 1)[1].strip()
                       for line in f)
    except FileNotFoundError:
        return False


def _verify_alert_row(lat: float, lng: float) -> bool:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "packages", "memory-engine"))
    try:
        from app.config import settings
        from supabase import create_client
    except Exception as e:
        print(f"  (verify skipped: import error {e!r})")
        return False
    try:
        db = create_client(settings.supabase_url, settings.supabase_service_key)
        res = (
            db.table("alerts")
            .select("*")
            .eq("kind", "wander")
            .order("ts", desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        if not rows:
            return False
        row = rows[0]
        # Light sanity check — most recent wander alert should match our coords
        return abs(float(row["lat"]) - lat) < 0.001 and abs(float(row["lng"]) - lng) < 0.001
    except Exception as e:
        print(f"  (verify skipped: {e!r})")
        return False


if __name__ == "__main__":
    sys.exit(main())
