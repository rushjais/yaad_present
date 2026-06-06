# Yaad

A warm, bilingual (Hindi/English) voice companion for early dementia, backed by an **episodic, temporal, self-updating memory graph built on Moss**.

Built at the Conversational AI Hackathon — Moss (YC F25) @ Y Combinator.

## What this is
Yaad is not a chatbot with a microphone. It's a memory layer that gives a person their own life back — grounded, temporal, and updated live. The novel surface area is the **memory**, not the conversation.

## The docs — read in this order
1. **CONTRACT.md** — the frozen API + data schema (source of truth; frozen at Gate 0).
2. **FEATURES.md** — every feature + the unique mechanics (what we're building and why it's different).
3. **CLAUDE.md** — full architecture per track (how to build it).
4. **PLAN.md** — the 24h execution schedule and gates (when).
5. **STATUS.md** — live build log (kept current in the same commit as every change).

## Team / tracks
Track A Voice — **Rushil** · Track B Memory — **Keshav** · Track C Caregiver Web — **Raghav**

## Packages (created at Gate 0)
`packages/memory-engine` (Python/FastAPI) · `packages/voice-agent` (Python/Pipecat+LiveKit) · `packages/caregiver-web` (Next.js/TS)

## Living docs rule
A change isn't done until its `CLAUDE.md` / `CONTRACT.md` / `STATUS.md` is updated in the **same commit**. Re-read before you code, update after.
