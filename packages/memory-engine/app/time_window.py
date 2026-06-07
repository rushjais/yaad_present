"""
B7 — Relative time window parser.

Parses "today" / "yesterday" / "this morning" / "tonight" / "last week" /
"before lunch" / etc. into a concrete (start_ts, end_ts) pair in the
patient's local timezone. Used by temporal routing.

Hardcoded tz = America/New_York (Atlanta — where Amma lives, per the
seed). Becomes a setting if Yaad ever ships beyond demo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Optional

try:
    from zoneinfo import ZoneInfo
    from .config import settings
    _LOCAL_TZ = ZoneInfo(settings.patient_tz)
except Exception:
    _LOCAL_TZ = None


@dataclass
class TimeWindow:
    start: datetime
    end: datetime
    label: str  # for debugging / explanations ("today", "yesterday", "this week")

    def contains(self, ts: datetime) -> bool:
        return self.start <= ts <= self.end


def _now_local() -> datetime:
    return datetime.now(_LOCAL_TZ) if _LOCAL_TZ else datetime.now()


def _at(d: datetime, h: int, m: int = 0) -> datetime:
    return d.replace(hour=h, minute=m, second=0, microsecond=0)


def _day_bounds(d: datetime) -> tuple[datetime, datetime]:
    return _at(d, 0, 0), _at(d, 23, 59).replace(second=59, microsecond=999999)


# Order matters: longest / most specific patterns first.
_PATTERNS: list[tuple[str, str]] = [
    (r"\bthis morning\b",       "this morning"),
    (r"\bthis afternoon\b",     "this afternoon"),
    (r"\bthis evening\b|\btonight\b", "this evening"),
    (r"\blast night\b",         "last night"),
    (r"\byesterday morning\b",  "yesterday morning"),
    (r"\byesterday\b",          "yesterday"),
    (r"\btomorrow morning\b",   "tomorrow morning"),
    (r"\btomorrow\b",           "tomorrow"),
    (r"\bbefore lunch\b",       "before lunch"),
    (r"\bafter lunch\b",        "after lunch"),
    (r"\blast week\b",          "last week"),
    (r"\bthis week\b",          "this week"),
    (r"\bnext week\b",          "next week"),
    (r"\btoday\b|\bnow\b|\bright now\b", "today"),
    (r"\b(?:in the )?next (\d+) (hour|hours|day|days)\b", "next_n"),
    (r"\b(?:in the )?last (\d+) (hour|hours|day|days)\b", "last_n"),
]


def parse_time_window(text: str) -> Optional[TimeWindow]:
    """Return a TimeWindow if the text contains a recognizable relative-time
    phrase, else None. Caller decides what to do with None (often: treat
    as "no window — return the most recent N").
    """
    t = text.lower()
    now = _now_local()
    today_start, today_end = _day_bounds(now)

    for pattern, label in _PATTERNS:
        m = re.search(pattern, t)
        if not m:
            continue
        if label == "today":
            return TimeWindow(today_start, today_end, "today")
        if label == "this morning":
            return TimeWindow(_at(now, 5), _at(now, 12), "this morning")
        if label == "this afternoon":
            return TimeWindow(_at(now, 12), _at(now, 17), "this afternoon")
        if label == "this evening":
            return TimeWindow(_at(now, 17), _at(now, 23, 59), "this evening")
        if label == "last night":
            y = now - timedelta(days=1)
            return TimeWindow(_at(y, 20), _at(now, 5), "last night")
        if label == "yesterday":
            y = now - timedelta(days=1)
            ys, ye = _day_bounds(y)
            return TimeWindow(ys, ye, "yesterday")
        if label == "yesterday morning":
            y = now - timedelta(days=1)
            return TimeWindow(_at(y, 5), _at(y, 12), "yesterday morning")
        if label == "tomorrow":
            tm = now + timedelta(days=1)
            ts, te = _day_bounds(tm)
            return TimeWindow(ts, te, "tomorrow")
        if label == "tomorrow morning":
            tm = now + timedelta(days=1)
            return TimeWindow(_at(tm, 5), _at(tm, 12), "tomorrow morning")
        if label == "before lunch":
            return TimeWindow(today_start, _at(now, 12), "before lunch")
        if label == "after lunch":
            return TimeWindow(_at(now, 13), today_end, "after lunch")
        if label == "this week":
            week_start = today_start - timedelta(days=now.weekday())
            week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
            return TimeWindow(week_start, week_end, "this week")
        if label == "last week":
            week_start = today_start - timedelta(days=now.weekday() + 7)
            week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
            return TimeWindow(week_start, week_end, "last week")
        if label == "next week":
            week_start = today_start + timedelta(days=7 - now.weekday())
            week_end = week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
            return TimeWindow(week_start, week_end, "next week")
        if label == "next_n":
            n = int(m.group(1))
            unit = m.group(2)
            delta = timedelta(hours=n) if "hour" in unit else timedelta(days=n)
            return TimeWindow(now, now + delta, f"next {n} {unit}")
        if label == "last_n":
            n = int(m.group(1))
            unit = m.group(2)
            delta = timedelta(hours=n) if "hour" in unit else timedelta(days=n)
            return TimeWindow(now - delta, now, f"last {n} {unit}")

    return None
