"""
B7 — Single understanding pass per query.

Replaces the per-layer ad-hoc parsing (regex temporal, string-match capture,
score-boost graph) with one typed Intent that every router consumes.

Pipeline:
  text → regex fast-path (5 demo phrasings, <1ms)
       → Groq LLM fallback for paraphrases (~100-200ms)
       → Intent {kind, entities[], time_window, medication_hint, confidence}

Entity resolution happens against Moss as a separate step (entity strings
from the classifier are linked to refs via semantic match). That keeps the
classifier cheap and lets every router decide whether it needs resolved refs.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Literal, Optional

from .config import settings
from .time_window import TimeWindow, parse_time_window


IntentKind = Literal[
    "who_is",          # "who is Leo", "tell me about Sarah"
    "temporal_med",    # "did I take my pills", "have I had my heart pill"
    "temporal_event",  # "is Sarah coming today", "what's happening this week"
    "relational",      # "who is Leo to me", "what's Sarah's son's name"
    "remember",        # "remember this — Leo got into Stanford"
    "general",         # fallback — semantic only
]


@dataclass
class Intent:
    kind: IntentKind
    entities: list[str] = field(default_factory=list)   # raw mentions ("Leo", "Sarah")
    time_window: Optional[TimeWindow] = None
    medication_hint: Optional[str] = None               # "heart pill", "white pill", "BP"
    confidence: float = 1.0                              # 1.0 = regex hit, <1.0 = LLM
    raw_text: str = ""
    source: Literal["regex", "llm", "general"] = "general"

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "entities": self.entities,
            "time_window": (
                {"start": self.time_window.start.isoformat(),
                 "end": self.time_window.end.isoformat(),
                 "label": self.time_window.label}
                if self.time_window else None
            ),
            "medication_hint": self.medication_hint,
            "confidence": self.confidence,
            "source": self.source,
        }


# ---------------------------------------------------------------------------
# Regex fast-path — covers the 5 demo phrasings + common paraphrases.
# Sub-millisecond. ~80% of demo traffic should hit here.
# ---------------------------------------------------------------------------

# "who is X" / "tell me about X" / "what about X" / "X who"
_WHO_IS = re.compile(
    r"\b(?:who(?:'s| is)|tell me about|what about|do (?:i|you) (?:remember|know))\s+([A-Z][a-z]+|the [a-z]+)",
    re.IGNORECASE,
)
# Bare-name fallback: "Leo?" / "Sarah?" / "Leo who?"
_BARE_NAME = re.compile(r"^\s*([A-Z][a-z]+)\s*(?:who)?\s*\??\s*$")

# Medication: pills / meds / medicine / heart pill / blood pressure / BP / morning pill
_MED_TOOK = re.compile(
    r"\b(?:did|have|did i|have i)\b.*?\b(?:take|took|had|do|done)\b.*?"
    r"\b(?:pill|pills|meds|medicine|medication|tablet|dose|"
    r"heart|bp|blood pressure|morning|evening|white|pink)\b",
    re.IGNORECASE,
)
_MED_GENERAL = re.compile(
    r"\b(?:my )?(?:pills?|meds|medicine|medication|tablets?|doses?|"
    r"heart pill|blood pressure pill|bp pill|white pill|pink pill|"
    r"morning pill|evening pill)\b",
    re.IGNORECASE,
)
_MED_HINTS = [
    ("heart", "heart pill"),
    ("white", "heart pill"),
    ("metoprolol", "heart pill"),
    ("blood pressure", "blood pressure pill"),
    ("\\bbp\\b", "blood pressure pill"),
    ("pink", "blood pressure pill"),
    ("amlodipine", "blood pressure pill"),
    ("evening", "blood pressure pill"),
    ("morning", "heart pill"),
]

# Event: "is X coming", "when is Y", "what's happening", "any visits"
_EVENT_QUERY = re.compile(
    r"\b(?:is|are|when|what's|whats|any)\b.*?"
    r"\b(?:coming|visit|visiting|happening|going on|appointment|doctor|"
    r"plans|scheduled|today|tomorrow|tonight|this week)\b",
    re.IGNORECASE,
)

# Remember: "remember this" / "remember that" / "make a note" / "don't forget"
_REMEMBER = re.compile(
    r"\b(?:remember (?:this|that|please)|make a note|don't forget|note that|"
    r"please remember|important[:,]?)\b",
    re.IGNORECASE,
)

# Relational: "X's Y" or "who is X to Y" or "is X Y's Z"
_RELATIONAL = re.compile(
    r"\b(?:who is [A-Z][a-z]+ to (?:me|her|him|us)|"
    r"[A-Z][a-z]+\'s (?:son|daughter|grandson|granddaughter|mother|father|"
    r"husband|wife|sister|brother)|"
    r"how (?:are|is) [A-Z][a-z]+ related)\b",
    re.IGNORECASE,
)

_PROPER_NAME = re.compile(r"\b([A-Z][a-z]{2,})\b")


def _extract_entities(text: str) -> list[str]:
    """Pull proper-noun mentions. Cheap heuristic — Moss does the actual link."""
    seen: set[str] = set()
    out: list[str] = []
    for m in _PROPER_NAME.finditer(text):
        n = m.group(1)
        if n.lower() in {"who", "what", "when", "where", "why", "how", "did", "have", "the", "tell", "is", "are"}:
            continue
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _extract_medication_hint(text: str) -> Optional[str]:
    t = text.lower()
    for pattern, label in _MED_HINTS:
        if re.search(pattern, t):
            return label
    return None


def _regex_classify(text: str) -> Optional[Intent]:
    """Returns an Intent if a fast-path pattern matches confidently, else None."""
    tw = parse_time_window(text)
    entities = _extract_entities(text)
    med_hint = _extract_medication_hint(text)

    if _REMEMBER.search(text):
        return Intent(kind="remember", entities=entities, time_window=tw,
                      medication_hint=med_hint, confidence=1.0,
                      raw_text=text, source="regex")

    if _RELATIONAL.search(text):
        return Intent(kind="relational", entities=entities, time_window=tw,
                      medication_hint=med_hint, confidence=1.0,
                      raw_text=text, source="regex")

    if _MED_TOOK.search(text) or (_MED_GENERAL.search(text) and tw is not None):
        return Intent(kind="temporal_med", entities=entities, time_window=tw,
                      medication_hint=med_hint, confidence=1.0,
                      raw_text=text, source="regex")

    if _EVENT_QUERY.search(text):
        return Intent(kind="temporal_event", entities=entities, time_window=tw,
                      medication_hint=med_hint, confidence=1.0,
                      raw_text=text, source="regex")

    if _WHO_IS.search(text) or _BARE_NAME.match(text):
        return Intent(kind="who_is", entities=entities, time_window=tw,
                      medication_hint=med_hint, confidence=1.0,
                      raw_text=text, source="regex")

    return None


# ---------------------------------------------------------------------------
# LLM fallback — Groq llama-3.3-70b structured output.
# Fires only when regex misses. ~100-200ms.
# ---------------------------------------------------------------------------

_LLM_SYSTEM = """You are an intent classifier for a memory companion.

Given a short user utterance, return STRICT JSON with these fields:
{
  "kind": one of ["who_is","temporal_med","temporal_event","relational","remember","general"],
  "entities": list of proper-noun mentions (people/places only — no "you"/"me"/"her"),
  "medication_hint": optional string — "heart pill" | "blood pressure pill" | null,
  "time_phrase": optional string — copy the literal time phrase if present (e.g. "today"),
  "confidence": 0..1
}

Rules:
- "who is X" / "tell me about X" → kind=who_is
- "did/have I take(n) my pills/meds" → kind=temporal_med
- "is X coming" / "what's happening" / "any plans" → kind=temporal_event
- "X is Y's Z" / "how is X related" → kind=relational
- "remember this" / "don't forget" / "make a note" → kind=remember
- Anything else → kind=general
- NEVER invent entities. Only pull proper nouns that are actually in the text.

Return ONLY the JSON, no prose."""


async def _llm_classify(text: str) -> Optional[Intent]:
    """Groq llama-3.3-70b structured-output fallback. Returns None on any
    failure so the caller can degrade to 'general'.
    """
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
            max_tokens=300,
        )
        raw = resp.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception:
        return None

    kind = data.get("kind", "general")
    if kind not in ("who_is", "temporal_med", "temporal_event", "relational", "remember", "general"):
        kind = "general"

    entities = [e for e in (data.get("entities") or []) if isinstance(e, str)]
    med_hint = data.get("medication_hint") or None
    conf = float(data.get("confidence", 0.7))
    # Time-window: prefer the LLM's phrase if it gave one; else parse the full text.
    time_phrase = data.get("time_phrase") or text
    tw = parse_time_window(time_phrase) if time_phrase else None

    return Intent(kind=kind, entities=entities, time_window=tw,
                  medication_hint=med_hint, confidence=conf,
                  raw_text=text, source="llm")


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def understand(text: str, allow_llm: bool = True) -> Intent:
    """Classify `text` into a typed Intent. Always returns an Intent — never None.

    Pipeline: regex fast-path → LLM fallback → general (last resort).
    """
    text = text.strip()
    if not text:
        return Intent(kind="general", raw_text=text, source="general", confidence=0.0)

    fast = _regex_classify(text)
    if fast is not None:
        return fast

    if allow_llm:
        slow = await _llm_classify(text)
        if slow is not None:
            return slow

    return Intent(
        kind="general",
        entities=_extract_entities(text),
        time_window=parse_time_window(text),
        medication_hint=_extract_medication_hint(text),
        confidence=0.3,
        raw_text=text,
        source="general",
    )
