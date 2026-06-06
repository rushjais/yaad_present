"""
B5 — Vision beat (OPTIONAL — build last, single-shot only).
Snapshot → match pre-registered face → person ref → answer_draft.
[CONFIRM] on-device embedding or hosted VLM.
Fixture fallback always present.
"""
from __future__ import annotations

import base64

from .schemas import EntityType, Provenance, RetrievedItem, VisionRecognizeResponse

FIXTURE_RESPONSE = VisionRecognizeResponse(
    match=RetrievedItem(
        ref="person:leo-fixture",
        type=EntityType.person,
        text="Leo, your grandson.",
        score=0.92,
        provenance=Provenance(
            source="fixture",
            added_by="seed",
            added_ts="2025-01-01T00:00:00+00:00",
        ),
    ),
    answer_draft="That's Leo, your grandson!",
)


async def recognize(image_b64: str) -> VisionRecognizeResponse:
    try:
        return await _recognize_impl(image_b64)
    except Exception:
        return FIXTURE_RESPONSE


async def _recognize_impl(image_b64: str) -> VisionRecognizeResponse:
    # [CONFIRM] on-device embedding vs hosted VLM
    # Current plan: OpenAI vision to describe → match description against Moss persons index
    from .config import settings
    from .moss_client import moss
    import openai

    client = openai.AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": "Describe the person in this photo in one sentence. Name, approximate age, notable features."},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
            ],
        }],
        max_tokens=100,
    )
    description = response.choices[0].message.content or ""

    # Match description against Moss persons
    results = await moss.query(description, top_k=3, filters={"type": "person"})
    if not results or results[0].get("score", 0) < 0.6:
        return VisionRecognizeResponse(match=None, answer_draft="I'm not sure who that is. Let me check with the family.")

    top = results[0]
    meta = top.get("metadata", {})
    prov_raw = meta.get("provenance", {})
    match = RetrievedItem(
        ref=top["id"],
        type=EntityType.person,
        text=top.get("text", ""),
        score=top.get("score", 0.0),
        provenance=Provenance(
            source=prov_raw.get("source", "moss"),
            added_by=prov_raw.get("added_by", "caregiver"),
            added_ts=prov_raw.get("added_ts", "2025-01-01T00:00:00+00:00"),
        ),
    )
    return VisionRecognizeResponse(
        match=match,
        answer_draft=f"That's {top.get('text', 'someone you know')}!",
    )
