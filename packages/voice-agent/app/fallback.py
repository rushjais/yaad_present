# Fixture responses for the 5 demo beats.
# Returned when memory-engine times out or is unreachable (§13 demo resilience).
# Shape mirrors CONTRACT.md QueryResponse: {items, grounded, confidence, answer_draft}.

_FIXTURES: dict[str, dict] = {
    "leo": {
        "items": [
            {
                "ref": "person:leo",
                "type": "person",
                "text": "Leo is your grandson, 23 years old. He studies at Stanford and visits every Sunday.",
                "score": 0.95,
                "provenance": {"source": "fixture", "added_by": "family", "added_ts": "2026-06-01T00:00:00Z"},
            }
        ],
        "grounded": True,
        "confidence": 0.95,
        "answer_draft": "That's Leo, your dear grandson! He's 23 and studying at Stanford. He visits every Sunday and loves your chai.",
    },
    "pills": {
        "items": [
            {
                "ref": "med_log:today-morning",
                "type": "med_log",
                "text": "You took your white heart pill (Metoprolol) at 8:00 AM this morning.",
                "score": 0.98,
                "provenance": {"source": "fixture", "added_by": "system", "added_ts": "2026-06-06T08:00:00Z"},
            }
        ],
        "grounded": True,
        "confidence": 0.98,
        "answer_draft": "Yes, you took your white heart pill this morning at 8 o'clock. You're all set for today.",
    },
    "sarah": {
        "items": [
            {
                "ref": "person:sarah",
                "type": "person",
                "text": "Sarah is your daughter. She calls every morning and visits on weekends.",
                "score": 0.93,
                "provenance": {"source": "fixture", "added_by": "family", "added_ts": "2026-06-01T00:00:00Z"},
            }
        ],
        "grounded": True,
        "confidence": 0.93,
        "answer_draft": "Sarah is your daughter. She calls you every morning and loves to visit on weekends.",
    },
    "hindi_leo": {
        "items": [
            {
                "ref": "person:leo",
                "type": "person",
                "text": "Leo aapka pota hai, 23 saal ka. Woh Stanford mein padhta hai aur har Ravivaar milne aata hai.",
                "score": 0.95,
                "provenance": {"source": "fixture", "added_by": "family", "added_ts": "2026-06-01T00:00:00Z"},
            }
        ],
        "grounded": True,
        "confidence": 0.95,
        "answer_draft": "Yeh Leo hai, aapka pyaara pota! Woh 23 saal ka hai aur Stanford mein padhta hai.",
    },
    "default": {
        "items": [],
        "grounded": False,
        "confidence": 0.0,
        "answer_draft": "I'm not sure about that. Let me check with the family and get back to you.",
    },
}

# keywords → fixture key
_ROUTING: list[tuple[list[str], str]] = [
    (["leo"], "leo"),
    (["pill", "pills", "medicine", "tablet", "medication", "dawai", "dawa"], "pills"),
    (["sarah"], "sarah"),
]


def get_fixture(query_text: str) -> dict:
    """Return the best-matching fixture for a query. Always returns a valid QueryResponse shape."""
    text = query_text.lower()
    # Check for Devanagari script (Hindi)
    is_hindi = any(0x0900 <= ord(c) <= 0x097F for c in query_text)
    for keywords, key in _ROUTING:
        if any(kw in text for kw in keywords):
            if is_hindi and key == "leo":
                return _FIXTURES["hindi_leo"]
            return _FIXTURES[key]
    return _FIXTURES["default"]
