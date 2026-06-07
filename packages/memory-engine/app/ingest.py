"""
Medical-document → structured-memory pipeline.

Flow:
  1. Upload PDF to Unsiloed.
  2. Ask one consolidated question that extracts medications + appointments +
     people + a one-line summary.
  3. Groq normalizes Unsiloed's natural-language answer into typed records
     matching the Yaad schema.
  4. Each record is written through the same path /memory/write uses
     (Supabase row + Moss upsert), so it's queryable on the next turn.

Only `medication` and `event` records are auto-committed — those are the demo-
useful structured facts in a medical doc (discharge summary, med list, follow-up
appointments). Free-text findings land as a single `story` row so they're
retrievable but not mistaken for structured state.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from .config import settings


# One prompt, structured JSON — cheaper + less drift than four separate chats.
_UNSILOED_PROMPT = """List every medication and every appointment mentioned in this document.

For each medication: name, dose, frequency (e.g. 'once daily', 'twice a day'), time of day if stated.
For each appointment / follow-up / visit: title, date or relative date, location if stated.
Also include: a one-sentence plain-English summary of the document, and a list of any people named (doctors, family).

Reply in this exact JSON shape, no prose:
{
  "summary": "...",
  "medications": [{"name": "...", "dose": "...", "frequency": "...", "time_of_day": "..."}],
  "appointments": [{"title": "...", "when": "...", "location": "..."}],
  "people": [{"name": "...", "role": "..."}]
}
If a field is unknown, use an empty string. If a list is empty, return []."""


_GROQ_NORMALIZE_SYSTEM = """You normalize a medical-document extraction into Yaad memory records.

Input: a JSON extraction from a parser (may have noise, missing fields, or be wrapped in prose).
Output: STRICT JSON matching this shape — no prose, no markdown fences:

{
  "summary": "<one sentence>",
  "medications": [
    {"name": "<drug name only, e.g. 'Aspirin'>",
     "schedule_rrule": "<RFC5545 RRULE, e.g. 'FREQ=DAILY;BYHOUR=8;BYMINUTE=0' or empty if unknown>",
     "notes": "<dose + any context, e.g. '100mg, with food'>"}
  ],
  "events": [
    {"title": "<short event title>",
     "kind": "appointment",
     "start_ts": "<ISO 8601 if a date is known, else empty>",
     "notes": "<location + context>"}
  ],
  "persons": [
    {"name": "<full name>", "relationship": "<e.g. doctor, cardiologist, daughter>", "notes": ""}
  ]
}

Rules:
- Drop entries with no name/title. Never invent.
- For schedule_rrule: 'once daily at 8am' → 'FREQ=DAILY;BYHOUR=8;BYMINUTE=0'.
  'twice daily' → 'FREQ=DAILY;INTERVAL=1;COUNT=2' is wrong — use 'FREQ=DAILY;BYHOUR=8,20'.
  Unknown → empty string. Better empty than wrong.
- For start_ts: only emit if an absolute date is in the input. Relative dates ('next week') → empty.
- persons.relationship: use 'doctor' / 'cardiologist' / 'nurse' for clinical roles; never guess family ties."""


async def _groq_normalize(raw_extraction: str) -> dict[str, Any]:
    """Normalize Unsiloed extraction → schema-shaped records using OpenAI."""
    if not settings.openai_api_key:
        return {"summary": "", "medications": [], "events": [], "persons": []}
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": _GROQ_NORMALIZE_SYSTEM},
                {"role": "user", "content": raw_extraction},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=1500,
        )
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception as e:
        print(f"[ingest] normalize failed: {e!r}")
        return {"summary": "", "medications": [], "events": [], "persons": []}


async def _write_and_index(entity_type: str, payload: dict, source: str) -> str | None:
    """Write to Supabase + Moss. Returns 'type:uuid' or None on failure.
    Skips silently if the payload has no name/title — Groq sometimes emits
    blanks for partial extractions and we'd rather drop than write junk.
    """
    name = (payload.get("name") or payload.get("title") or "").strip()
    if not name:
        return None

    payload = {**payload, "source": source, "added_by": "unsiloed_ingest"}
    try:
        from .db import write_memory
        result = await write_memory(entity_type, payload)
    except Exception as e:
        print(f"[ingest] Supabase write failed for {entity_type}: {e!r}")
        return None

    ref = f"{entity_type}:{result['id']}"
    text = ""
    if entity_type == "story":
        from .chunks import render
        text = render(entity_type, payload)
    if text:
        try:
            from .moss_client import moss
            await moss.upsert(ref, text, {
                "type": entity_type,
                "name": name,
                "provenance": {
                    "source": source,
                    "added_by": "unsiloed_ingest",
                    "added_ts": datetime.now(timezone.utc).isoformat(),
                },
            })
        except Exception as e:
            print(f"[ingest] Moss upsert failed for {ref}: {e!r}")
    return ref


async def ingest_document(file_bytes: bytes, filename: str,
                          content_type: str = "application/pdf") -> dict[str, Any]:
    """Top-level pipeline. Returns:
        {
          "created_refs": ["medication:uuid", ...],
          "summary": "<one-sentence doc summary>",
          "raw_extraction": "<Unsiloed's raw answer, kept for audit>"
        }
    Caller wraps in try/except (main.py pattern) to keep the demo path safe.
    """
    from . import unsiloed

    doc_id = await unsiloed.upload(file_bytes, filename, content_type)
    raw = await unsiloed.chat(doc_id, _UNSILOED_PROMPT)
    normalized = await _groq_normalize(raw)

    created: list[str] = []
    source = f"unsiloed:{filename}"

    for med in normalized.get("medications") or []:
        ref = await _write_and_index("medication", {
            "name": med.get("name", ""),
            "schedule_rrule": med.get("schedule_rrule", "") or "FREQ=DAILY",
            "notes": med.get("notes", ""),
        }, source)
        if ref:
            created.append(ref)

    for evt in normalized.get("events") or []:
        start_ts = evt.get("start_ts") or ""
        if not start_ts:
            # Events without dates aren't useful to /reminders/due. Skip rather
            # than fabricate a timestamp.
            continue
        ref = await _write_and_index("event", {
            "title": evt.get("title", ""),
            "kind": evt.get("kind", "appointment"),
            "start_ts": start_ts,
            "notes": evt.get("notes", ""),
        }, source)
        if ref:
            created.append(ref)

    for person in normalized.get("persons") or []:
        ref = await _write_and_index("person", {
            "name": person.get("name", ""),
            "relationship": person.get("relationship", ""),
            "notes": person.get("notes", ""),
        }, source)
        if ref:
            created.append(ref)

    # Anchor the document itself as a single story so the full extraction is
    # retrievable as one chunk ("what did the discharge summary say?"). Story
    # schema has `text` not `notes`; combine summary + raw extraction there.
    summary = (normalized.get("summary") or "").strip()
    if summary:
        story_text = summary
        if raw and raw.strip() and raw.strip() != summary:
            story_text = f"{summary}\n\n{raw[:2000]}"
        story_ref = await _write_and_index("story", {
            "title": filename,
            "text": story_text,
        }, source)
        if story_ref:
            created.append(story_ref)

    return {
        "created_refs": created,
        "summary": summary,
        "raw_extraction": raw,
    }
