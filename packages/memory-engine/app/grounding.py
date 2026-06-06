"""
B3 — Grounding / anti-confabulation gate.
Below confidence threshold τ → grounded=False, answer_draft = safe refusal.
Every item carries provenance. The LLM is never allowed to invent facts.
"""
from __future__ import annotations

from .config import settings
from .schemas import MemoryQueryResponse, RetrievedItem

SAFE_REFUSAL_EN = (
    "I'm not sure about that right now. Let me check with the family — "
    "they'll know for certain."
)

SAFE_REFUSAL_HI = (
    "Mujhe abhi yeh yaad nahi aa raha. Parivaar se poochh lete hain — "
    "woh zaroor jaante honge."
)


def safe_refusal(lang: str = "en") -> str:
    if lang.startswith("hi"):
        return SAFE_REFUSAL_HI
    return SAFE_REFUSAL_EN


def assess_grounding(
    items: list[RetrievedItem],
    query: str,
    lang: str = "en",
) -> dict:
    """
    Given ranked retrieved items, decide grounded/confidence and build the response.
    If top item score < τ: grounded=False, answer_draft = safe refusal.
    """
    if not items:
        return {
            "items": [],
            "grounded": False,
            "confidence": 0.0,
            "answer_draft": safe_refusal(lang),
        }

    top_score = items[0].score
    grounded = top_score >= settings.confidence_threshold

    answer_draft: str | None
    if grounded:
        answer_draft = _draft_from_items(items, lang)
    else:
        answer_draft = safe_refusal(lang)

    return {
        "items": [i.model_dump() for i in items],
        "grounded": grounded,
        "confidence": round(top_score, 3),
        "answer_draft": answer_draft,
    }


def _draft_from_items(items: list[RetrievedItem], lang: str) -> str:
    """
    Build a minimal grounded answer draft from top items.
    The voice-agent LLM will rewrite this into natural speech;
    this draft is the factual skeleton and the source of truth.
    """
    lines = [i.text for i in items[:3] if i.text]
    return " ".join(lines)
