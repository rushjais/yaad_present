from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ..schemas import EntityType
from ..time_window import parse_time_window
from .common import item, response


async def execute(query: str, meta: dict[str, Any] | None = None) -> dict:
    from ..db import fetch_med_logs_in_window

    meta = meta or {}
    window = meta.get("time_window") or parse_time_window(query) or parse_time_window("today")
    med = await resolve_medication(query)
    medication_id = med["id"] if med else None

    logs = await fetch_med_logs_in_window(
        window.start.astimezone(timezone.utc).isoformat(),
        window.end.astimezone(timezone.utc).isoformat(),
        medication_id,
    )
    med_label = med["name"] if med else "your medication"

    if logs:
        latest = logs[0]
        time_str = _fmt_time(latest.get("taken_ts", ""))
        return response([
            item(
                f"med_log:{latest['id']}",
                EntityType.med_log,
                f"{med_label} taken at {time_str} ({window.label}).",
                "med_logs",
                latest,
                1.0,
            )
        ], f"Yes, you took your {med_label} at {time_str}.", 1.0)

    synthetic = {
        "id": f"none:{window.label}:{medication_id or 'any'}",
        "taken_ts": datetime.now(timezone.utc).isoformat(),
        "source": "absence",
    }
    return response([
        item(
            f"med_log:none:{window.label}:{medication_id or 'any'}",
            EntityType.med_log,
            f"No {med_label} logged {window.label}.",
            "med_logs",
            synthetic,
            0.95,
        )
    ], f"I don't see your {med_label} logged {window.label}.", 0.95)


async def resolve_medication(query: str) -> dict | None:
    from ..db import fetch_medications

    meds = await fetch_medications()
    if not meds:
        return None
    q_tokens = _tokens(query)
    best: tuple[float, dict] | None = None
    for med in meds:
        text = " ".join(str(med.get(k) or "") for k in ("name", "notes"))
        m_tokens = _tokens(text)
        overlap = len(q_tokens & m_tokens)
        if not q_tokens:
            score = 0.0
        else:
            score = overlap / max(1, len(q_tokens))
        if any(tok in text.lower() for tok in q_tokens if len(tok) >= 4):
            score += 0.25
        if best is None or score > best[0]:
            best = (score, med)
    if best and best[0] > 0.0:
        return best[1]
    return None


def _tokens(text: str) -> set[str]:
    stop = {"did", "have", "take", "taken", "took", "my", "your", "the", "a", "i", "pill", "pills", "med", "meds", "medicine", "medication", "today", "this", "morning"}
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in stop and len(t) >= 2}


def _fmt_time(iso: str) -> str:
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return t.strftime("%-I:%M %p").lstrip("0").lower().replace(" ", "")
    except Exception:
        return "earlier"
