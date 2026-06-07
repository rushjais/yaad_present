"""
B7 — Capture: structured extraction → review queue.

What changed vs Gate-1:
- Trigger: prefers `Intent.kind=remember` from intent.py; falls back to regex
  so /memory/capture still works without intent.
- Groq structured-output extracts `{subject, predicate, object, time_anchor,
  summary, confidence}` instead of a flat string.
- Entity resolution: subject and object are looked up in Moss with a high
  bar (≥0.85). On match → linked to existing ref. On miss → proposed new.
- Output is written as an `episode` row with `kind='pending_review'` —
  NOT auto-committed to person/place/edges tables. The caregiver dashboard
  surfaces pending items for confirmation; confirming graduates them.
- Reason: avoids duplicate-Leo bugs and confabulated entities slipping in.
  Demo can still show "we just remembered this from the conversation" by
  pointing at the pending row.
- A second `episode` row with the raw summary is committed immediately as a
  `captured_fact` so the conversation snippet is retrievable now.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional

from .schemas import MemoryCaptureResponse


_TRIGGER = re.compile(
    r"\b(?:remember (?:this|that|please)?|don'?t forget|keep in mind|note that|"
    r"please remember|make a note)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Structured extraction (Groq)
# ---------------------------------------------------------------------------

@dataclass
class Extraction:
    summary: str
    subject_name: Optional[str]
    predicate: Optional[str]      # short verb phrase, e.g. "got_into", "lives_with"
    object_name: Optional[str]
    time_anchor: Optional[str]    # raw phrase, e.g. "yesterday"
    confidence: float


_LLM_SYSTEM = """You extract structured memories from a caregiver/family utterance about an elderly person.

Return STRICT JSON only:
{
  "summary": "<one-sentence rewrite of the fact in third person, no fluff>",
  "subject_name": "<proper noun if the fact is about someone, else null>",
  "predicate": "<short verb phrase, e.g. got_into | lives_with | birthday_is | likes | visited>",
  "object_name": "<proper noun if the fact connects to someone/somewhere, else null>",
  "time_anchor": "<raw time phrase from the text, e.g. 'yesterday', 'on Saturday', 'this morning', or null>",
  "confidence": <0..1 — how sure you are this is a real, well-formed fact>
}

Rules:
- NEVER invent. Only fill fields you can ground in the text.
- subject_name and object_name must be proper nouns that appear in the text. If unsure → null.
- Confidence <0.5 if the utterance is vague or you had to guess.
- Strip filler ("remember this — ", "please don't forget that")."""


async def _llm_extract(text: str) -> Optional[Extraction]:
    from .config import settings
    if not settings.groq_api_key:
        return None
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=settings.groq_api_key)
        resp = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": _LLM_SYSTEM},
                {"role": "user", "content": text},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=400,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception:
        return None

    return Extraction(
        summary=str(data.get("summary") or "").strip() or text,
        subject_name=(data.get("subject_name") or None),
        predicate=(data.get("predicate") or None),
        object_name=(data.get("object_name") or None),
        time_anchor=(data.get("time_anchor") or None),
        confidence=float(data.get("confidence", 0.5)),
    )


# ---------------------------------------------------------------------------
# Entity resolution against Moss
# ---------------------------------------------------------------------------

RESOLUTION_THRESHOLD = 0.85   # raw Moss semantic floor for "match existing"


async def _resolve_existing(name: Optional[str]) -> Optional[dict]:
    """Returns the matched Moss doc dict if a name resolves to an existing
    entity with high confidence, else None.
    """
    if not name:
        return None
    from .moss_client import moss
    hits = await moss.query(name, top_k=3)
    if not hits:
        return None
    top = hits[0]
    if float(top.get("score", 0.0)) >= RESOLUTION_THRESHOLD and name.lower() in (top.get("text", "").lower()):
        return top
    return None


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------

async def capture_from_transcript(transcript: str) -> MemoryCaptureResponse:
    """`/memory/capture` entry. Detects trigger, extracts, queues for review."""
    if not _TRIGGER.search(transcript):
        return MemoryCaptureResponse(created_refs=[])
    return await _capture(transcript)


async def capture_from_intent(intent, lang: str = "en") -> dict:
    """Called from retrieval.py when Intent.kind=remember.
    Returns a MemoryQueryResponse-shaped dict so the voice agent can speak
    a grounded confirmation: "Got it — I'll remember Leo got into Stanford."
    """
    text = intent.raw_text
    result = await _capture(text)
    return {
        "items": [{"ref": ref,
                   "type": "episode",
                   "text": text,
                   "score": 1.0,
                   "provenance": {"source": "capture",
                                  "added_by": "voice_agent",
                                  "added_ts": datetime.now(timezone.utc).isoformat()}}
                  for ref in result.created_refs],
        "grounded": True,
        "confidence": 1.0,
        "answer_draft": f"Got it — I'll remember that.",
    }


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

async def _capture(transcript: str) -> MemoryCaptureResponse:
    fact_text = _TRIGGER.sub("", transcript).strip(" ,.:!?—–-")
    if len(fact_text) < 5:
        return MemoryCaptureResponse(created_refs=[])

    # Structured extraction (best-effort; falls back to flat episode if LLM fails)
    extraction = await _llm_extract(fact_text)

    # Resolve entities against Moss
    subject_hit = await _resolve_existing(extraction.subject_name) if extraction else None
    object_hit = await _resolve_existing(extraction.object_name) if extraction else None

    now = datetime.now(timezone.utc)
    created: list[str] = []

    # 1) Always commit a `captured_fact` episode so the snippet is retrievable now.
    captured_ref = await _store_episode(
        kind="captured_fact",
        title=fact_text[:80],
        summary=fact_text,
        ts=now,
        entity_refs=[h["id"] for h in (subject_hit, object_hit) if h],
    )
    created.append(captured_ref)

    # 2) If we got a structured extraction, queue a pending_review episode so
    #    the caregiver can confirm. THIS is the future entity/edge write.
    if extraction:
        proposal = {
            "summary":      extraction.summary,
            "subject_name": extraction.subject_name,
            "predicate":    extraction.predicate,
            "object_name":  extraction.object_name,
            "time_anchor":  extraction.time_anchor,
            "subject_ref":  subject_hit["id"] if subject_hit else None,
            "object_ref":   object_hit["id"] if object_hit else None,
            "confidence":   extraction.confidence,
        }
        pending_ref = await _store_episode(
            kind="pending_review",
            title=f"Pending: {extraction.summary[:60]}",
            summary=json.dumps(proposal),
            ts=now,
            entity_refs=[h["id"] for h in (subject_hit, object_hit) if h],
        )
        created.append(pending_ref)

    return MemoryCaptureResponse(created_refs=created)


async def _store_episode(*, kind: str, title: str, summary: str, ts: datetime,
                          entity_refs: list[str]) -> str:
    """Write an episode row to Supabase and upsert to Moss for retrieval.
    Returns the episode ref ('episode:<uuid>').
    """
    episode_id = str(uuid.uuid4())
    ref = f"episode:{episode_id}"
    provenance = {
        "source": "voice_capture",
        "added_by": "voice_agent",
        "added_ts": ts.isoformat(),
    }

    # Supabase
    try:
        from .db import _client
        _client().table("episodes").insert({
            "id": episode_id,
            "title": title,
            "occurred_ts": ts.isoformat(),
            "kind": kind,
            "entity_refs": entity_refs,
            "summary": summary,
            "provenance": provenance,
        }).execute()
    except Exception:
        pass

    # Moss — only retrieve `captured_fact`, not `pending_review` (avoid surfacing
    # unconfirmed proposals during conversation).
    if kind == "captured_fact":
        try:
            from .moss_client import moss
            await moss.upsert(ref, summary, {
                "type": "episode",
                "kind": kind,
                "provenance": provenance,
            })
        except Exception:
            pass

    return ref
