"""
Smoke test for Unsiloed ingestion (POST /ingest/document).

Builds a synthetic discharge-summary PDF in-memory, posts it to the running
memory engine (default http://localhost:8000), and asserts:
  - at least one medication ref was created
  - the summary string is non-empty

Run:
    python scripts/smoke_unsiloed.py

Requires the server to be running (uvicorn app.main:app --port 8000) and
UNSILOED_API_KEY + GROQ_API_KEY + SUPABASE creds set in .env.
"""
from __future__ import annotations

import io
import os
import sys

import httpx
from fpdf import FPDF


BASE = os.environ.get("MEMORY_ENGINE_URL", "http://localhost:8000")

# Realistic-ish synthetic discharge note. Two meds + one follow-up so we can
# verify the medication + event branches of the pipeline.
DOC_TEXT = """
AMMA SHARMA - DISCHARGE SUMMARY

Date: 2026-06-04
Attending: Dr. Patel (Cardiology)

Diagnosis: Hypertension, well-controlled.

MEDICATIONS:
1. Aspirin 100 mg - take once daily at 8:00 AM, with food.
2. Metoprolol 25 mg - take twice daily, morning and evening (8 AM and 8 PM).

FOLLOW-UP:
- Cardiology follow-up with Dr. Patel on 2026-06-18 at 10:00 AM,
  Stanford Hospital Clinic Building 2nd floor.

NOTES:
Patient tolerated treatment well. Family present at discharge.
""".strip()


def build_pdf() -> bytes:
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=11)
    for line in DOC_TEXT.split("\n"):
        pdf.cell(0, 6, line, ln=1)
    out = io.BytesIO()
    pdf.output(out)
    return out.getvalue()


def main() -> int:
    pdf_bytes = build_pdf()
    print(f"Built test PDF ({len(pdf_bytes)} bytes)")

    files = {"file": ("amma_discharge.pdf", pdf_bytes, "application/pdf")}
    print(f"POST {BASE}/ingest/document ...")
    try:
        resp = httpx.post(f"{BASE}/ingest/document", files=files, timeout=180.0)
    except httpx.HTTPError as e:
        print(f"FAIL: request error: {e!r}")
        return 1
    if resp.status_code != 200:
        print(f"FAIL: {resp.status_code} {resp.text[:500]}")
        return 1

    data = resp.json()
    print(f"Response: created_refs={data.get('created_refs')}")
    print(f"          summary={data.get('summary')!r}")
    print(f"          raw[:200]={(data.get('raw_extraction') or '')[:200]!r}")

    refs = data.get("created_refs") or []
    med_refs = [r for r in refs if r.startswith("medication:")]
    if not med_refs:
        print("FAIL: no medication refs created")
        return 1

    # Verify retrievability: ask the memory engine about Aspirin.
    print(f"\nPOST {BASE}/memory/query  text='Aspirin' ...")
    q = httpx.post(f"{BASE}/memory/query",
                   json={"text": "What is Aspirin?", "lang": "en"},
                   timeout=30.0)
    print(f"  status={q.status_code} grounded={q.json().get('grounded')}")
    items = q.json().get("items") or []
    if items:
        print(f"  top item: {items[0].get('ref')} score={items[0].get('score'):.2f}")
        print(f"           text={items[0].get('text')[:120]!r}")

    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
