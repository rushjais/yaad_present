"""
B7.1 — Retrieval v2: Moss chunks + single τ + intent routing.

What changed vs v1:
- Dropped graph expansion (no more neighbors shoveled into items[]).
- Dropped composite scoring (α·sem + β·rec + γ·sal + δ·gp). Pure Moss
  semantic. Recency lives in the captured-fact upsert timestamp;
  relationships live in the chunk text (set at seed time).
- Single τ relevance gate. Below τ → grounded=false, safe refusal.
  No more layered _OFF_TOPIC_HINTS / _IMPLICIT_ENTITY_WORDS /
  _entity_name_in_top guards.
- `answer_draft` is NOT pre-composed for semantic queries — voice agent's
  LLM composes from items[]. Temporal still pre-composes because grounded
  negatives need exact phrasing.
- Optional one-hop query expansion: if Moss's top chunk mentions an entity
  the question references that ISN'T already in our top-k, fire one more
  Moss query for it. Graph-like behavior without a graph engine.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from .config import settings
from .schemas import EntityType, Provenance, RetrievedItem


# Single hard relevance gate. Moss returns ~0.70-1.00 for any query;
# legitimate matches cluster ≥0.82. Tune via CONFIDENCE_THRESHOLD env if needed.
TAU = 0.82
# Hard floor for the SECOND-hop expansion query — looser since we're
# now scoping to a known entity name.
TAU_EXPANSION = 0.78


def _provenance_from_meta(meta: dict) -> Provenance:
    prov_raw = meta.get("provenance", {}) or {}
    if isinstance(prov_raw, str):
        prov_raw = {}
    return Provenance(
        source=prov_raw.get("source", "unknown"),
        added_by=prov_raw.get("added_by", "unknown"),
        added_ts=datetime.fromisoformat(
            (prov_raw.get("added_ts") or "2025-01-01T00:00:00+00:00").replace("Z", "+00:00")
        ),
    )


def _entity_type_from_meta(meta: dict) -> EntityType:
    t = meta.get("type", "episode")
    try:
        return EntityType(t)
    except Exception:
        return EntityType.episode


def _moss_hits_to_items(hits: list[dict]) -> list[RetrievedItem]:
    out: list[RetrievedItem] = []
    for h in hits:
        meta = h.get("metadata", {}) or {}
        out.append(RetrievedItem(
            ref=h["id"],
            type=_entity_type_from_meta(meta),
            text=h.get("text", ""),
            score=float(h.get("score", 0.0)),
            provenance=_provenance_from_meta(meta),
        ))
    return out


def _refused(message: str) -> dict:
    return {
        "items": [], "grounded": False, "confidence": 0.0,
        "answer_draft": message,
    }


# ---------------------------------------------------------------------------
# Main entry
# ---------------------------------------------------------------------------

async def query_memory(text: str, lang: str = "en") -> dict:
    """v2 retrieval:
       1. understand → Intent
       2. Route temporal/remember to dedicated handlers
       3. Else: Moss query → τ filter → optional 1-hop expansion
       4. Return items + (for semantic) NO answer_draft — LLM composes
    """
    from .grounding import safe_refusal
    from .intent import understand
    from .moss_client import moss

    intent = await understand(text)

    if intent.kind in ("temporal_med", "temporal_event"):
        from .temporal import execute
        return await execute(intent, lang)

    if intent.kind == "remember":
        try:
            from .capture import capture_from_intent
            return await capture_from_intent(intent, lang)
        except ImportError:
            pass  # fall through to semantic

    # Pure semantic. Moss does the work.
    raw = await moss.query(text, top_k=8, lang=lang)
    survivors = [h for h in raw if float(h.get("score", 0.0)) >= TAU]

    # B7.2 — Query-rewrite fallback. If nothing cleared τ, this MIGHT be an
    # abstract category query ("favorite music") where the underlying fact
    # lives in prose that doesn't share embedding surface. Try ONE rewrite
    # pass via Groq, entity-anchored if intent has named entities, then
    # safe-refuse if still empty. Single retry, no cascading.
    #
    # Adversarial queries that semantically resemble enriched chunks
    # ("favorite color", "what sport") are NOT filtered here — they pass
    # through to the voice agent, whose grounding system prompt ("state ONLY
    # facts in the provided MEMORY context") is the real anti-confab gate.
    # We tried a deterministic stopword/content-word filter — too brittle.
    if not survivors:
        rescued = await _rewrite_and_retry(text, intent, lang)
        if rescued:
            survivors = rescued
        else:
            return _refused(safe_refusal(lang))

    # Optional one-hop query expansion: if the user mentioned multiple
    # entities and one isn't represented, fire a 2nd Moss query for it.
    if intent.entities and len(intent.entities) >= 2:
        survivors = await _expand_for_missing_entities(intent.entities, survivors, lang)

    items = _moss_hits_to_items(survivors[:6])

    # Semantic answer: do NOT pre-compose. Voice agent's LLM composes the
    # spoken answer using items[]. We hand back a minimal draft string for
    # callers that don't run an LLM (smoke tests, dashboard).
    minimal_draft = items[0].text  # first chunk; LLM downstream will rewrite

    return {
        "items": [i.model_dump() for i in items],
        "grounded": True,
        "confidence": round(items[0].score, 3),
        "answer_draft": minimal_draft,
    }


# ---------------------------------------------------------------------------
# One-hop query expansion
# ---------------------------------------------------------------------------

async def _expand_for_missing_entities(entities: list[str],
                                        existing: list[dict],
                                        lang: str) -> list[dict]:
    """If the question mentions multiple entities (e.g. 'Did Leo get into
    Stanford?'), make sure all of them are represented in the results by
    firing a focused Moss query for any that aren't.
    """
    from .moss_client import moss

    have_text = " ".join((h.get("text") or "").lower() for h in existing)
    out = list(existing)
    seen_ids = {h["id"] for h in existing}

    for ent in entities[1:]:  # skip the first — it's almost always covered
        if ent.lower() in have_text:
            continue
        extra = await moss.query(ent, top_k=3, lang=lang)
        for e in extra:
            if e["id"] in seen_ids:
                continue
            if float(e.get("score", 0.0)) >= TAU_EXPANSION:
                out.append(e)
                seen_ids.add(e["id"])

    out.sort(key=lambda h: float(h.get("score", 0.0)), reverse=True)
    return out


# ---------------------------------------------------------------------------
# B7.2 — Query-rewrite fallback
# ---------------------------------------------------------------------------

_REWRITE_SYSTEM = """You help a memory system retrieve facts about Amma (an elderly grandmother)
and her family. The user's query failed because it asks about a category
("favorite music", "her hobbies") while the facts are stored as specifics
("Bollywood songs from the 1960s", "plays chess"). Your job: generate 3
alternative phrasings that bridge that gap — OR refuse if the query is
unrelated to her life.

Return STRICT JSON: {"queries": ["...", "...", "..."]}
If the query is clearly general knowledge or about something outside her
life, return {"queries": []} — DO NOT make up an Amma-shaped version of it.

REFUSE (return []) when the query is about:
- General knowledge (politics, math, geography, celebrities, news)
- Things Amma has no relationship to (random sports teams, brands, weather)
- A person, pet, or thing not named in the original query
  Example: "Who is my dog?" → []  (no dog mentioned in her life, and you
  must not invent one)

REWRITE when the query is plausibly about her life or someone in it:
- Each variant should approach the question from a different angle
  (literal synonym, descriptive paraphrase, related concept).
- Variants MUST NOT introduce entities that aren't in the original query.
  Don't add "Amma" or any person's name unless the user already said it.
  Example: "favorite music" → ["music she loves", "songs she enjoys",
                               "what she listens to"]
  NOT:    "favorite music" → ["Amma's favorite music", ...]
- If the original named a person (e.g. "Leo"), every variant MUST include
  that name. Example: "what does Leo like?" →
    ["things Leo enjoys", "Leo's hobbies", "Leo's interests"]
- Keep each variant short — 2-6 words is ideal."""


async def _rewrite_and_retry(text: str, intent, lang: str) -> list[dict]:
    """One-shot rescue path: ask Groq for 3 alternative phrasings, fire them
    in parallel against Moss, union anything above τ_EXPANSION. Returns the
    deduped above-threshold hits, or [] if still empty.

    Entity-anchored: if intent.entities is set, the rewrite prompt is told
    every variant MUST include at least one entity name. Prevents the
    fallback from drifting onto the wrong person.
    """
    from .config import settings
    from .moss_client import moss

    if not settings.groq_api_key:
        return []

    user_prompt = f"Original query: {text!r}"
    if intent.entities:
        user_prompt += f"\nEntities mentioned (must appear in every rephrasing): {intent.entities}"

    variants: list[str] = []
    try:
        import json
        from groq import AsyncGroq
        client = AsyncGroq(api_key=settings.groq_api_key)
        # Use 8b: rewrite is a simple paraphrase task, doesn't need 70b's
        # reasoning, and the 8b daily quota is separate so we stay live even
        # when the 70b TPD is exhausted (real failure mode on 2026-06-06).
        resp = await client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": _REWRITE_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=200,
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        variants = [v.strip() for v in (data.get("queries") or []) if isinstance(v, str) and v.strip()]
        variants = variants[:3]
    except Exception as e:
        print(f"[rewrite] Groq failed: {e!r}")
        return []

    if not variants:
        return []

    import asyncio
    raw_batches = await asyncio.gather(
        *[moss.query(v, top_k=4, lang=lang) for v in variants],
        return_exceptions=True,
    )

    # Use the SAME τ as first-pass. A laxer threshold here was the original
    # false-positive vector (adversarial queries getting rescued at 0.78).
    merged: dict[str, dict] = {}
    for batch in raw_batches:
        if isinstance(batch, Exception):
            continue
        for h in batch:
            if float(h.get("score", 0.0)) < TAU:
                continue
            existing = merged.get(h["id"])
            if existing is None or float(h["score"]) > float(existing["score"]):
                merged[h["id"]] = h

    survivors = sorted(merged.values(), key=lambda h: float(h["score"]), reverse=True)
    if survivors:
        print(f"[rewrite] rescued {len(survivors)} hits via {variants!r}")
    return survivors
