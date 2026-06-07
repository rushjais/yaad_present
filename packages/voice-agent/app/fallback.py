import os

# Fixture responses for the 5 demo beats.
# Returned when memory-engine times out or is unreachable (§13 demo resilience).
# Shape mirrors CONTRACT.md QueryResponse: {items, grounded, confidence, answer_draft}.

# ── Demo script ───────────────────────────────────────────────────────────────
# When YAAD_DEMO_MODE=1, these fire INSTEAD of hitting the memory engine.
# _temporal=True → answer_draft is emitted verbatim (or translated if Hindi).
# _temporal=False → answer_draft is passed to the LLM to compose naturally.
# Order matters — first match wins.

_PROV = {"source": "demo", "added_by": "family", "added_ts": "2026-06-07T00:00:00Z"}

_DEMO_SCRIPT: list[tuple[list[str], dict]] = [
    # Pills — clean, no double-"your" bug
    (
        ["pill", "pills", "medicine", "medication", "tablet", "dawai", "dawa"],
        {
            "grounded": True, "confidence": 1.0,
            "items": [{"ref": "med_log:demo", "type": "med_log", "score": 1.0,
                       "text": "Heart pill taken at 8:00 AM today.", "provenance": _PROV}],
            "answer_draft": "Yes, you took your heart pill at 8 this morning. You're all set for today.",
            "_temporal": True,
        }
    ),
    # Leo news (add-fact-live beat)
    (
        ["news", "google", "internship", "hear about leo", "leo up to"],
        {
            "grounded": True, "confidence": 1.0,
            "items": [{"ref": "story:leo-google", "type": "story", "score": 1.0,
                       "text": "Leo got a summer internship at Google in New York. Coming home Sunday to celebrate.",
                       "provenance": _PROV}],
            "answer_draft": "Leo called this morning with some wonderful news — he got a summer internship at Google in New York. He's coming home to celebrate with you on Sunday.",
            "_temporal": True,
        }
    ),
    # Who is Leo (identity)
    (
        ["who is leo", "tell me about leo", "leo kaun"],
        {
            "grounded": True, "confidence": 1.0,
            "items": [{"ref": "person:leo", "type": "person", "score": 1.0,
                       "text": "Leo is your grandson, 22, studying computer science at Georgia Tech. Visits every Sunday. Always brings jasmine flowers.",
                       "provenance": _PROV}],
            "answer_draft": "Leo is your grandson. He is 22 years old and studying computer science at Georgia Tech. He visits you every Sunday, and he always brings you jasmine flowers.",
            "_temporal": True,
        }
    ),
    # Who is Sarah — works for both English and Hindi (answer_draft gets translated if Hindi)
    (
        ["who is sarah", "sarah kaun", "tell me about sarah"],
        {
            "grounded": True, "confidence": 1.0,
            "items": [{"ref": "person:sarah", "type": "person", "score": 1.0,
                       "text": "Sarah is your daughter, 55. Calls every Tuesday. Visits on weekends. Lives 15 minutes away.",
                       "provenance": _PROV}],
            "answer_draft": "Sarah is your daughter. She calls you every Tuesday and visits on weekends. She lives just 15 minutes away and loves you very much.",
            "_temporal": True,
        }
    ),
    # Priya
    (
        ["who is priya", "priya kaun"],
        {
            "grounded": True, "confidence": 1.0,
            "items": [{"ref": "person:priya", "type": "person", "score": 1.0,
                       "text": "Priya is your neighbour and old friend. You have known each other for 40 years. You used to walk together at Lullwater Park every evening.",
                       "provenance": _PROV}],
            "answer_draft": "Priya is your dear friend — you have known each other for forty years. You used to walk together every evening at Lullwater Park. She makes the best chai you have ever tasted.",
            "_temporal": True,
        }
    ),
]


def get_demo_response(query_text: str) -> dict | None:
    """Return a scripted demo response if YAAD_DEMO_MODE=1 and query matches a beat.
    Returns None in normal mode or when no beat matches (falls through to memory engine)."""
    if os.environ.get("YAAD_DEMO_MODE") != "1":
        return None
    q = query_text.lower()
    for keywords, response in _DEMO_SCRIPT:
        if any(kw in q for kw in keywords):
            return response
    return None

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
