"""Show how the planner reads a topic before a run is started on that reading.

The planner turns the typed topic into the phrase every backend searches.
When it read a topic wrongly (it renamed "hyperloop", and drifted on
vertical farming), the run spent all its paid stages on off-topic sources
and used one of the code's three daily runs doing so. A preview costs one
small model call, so it does not take a daily run; it has a cap of its own
per code and UTC day instead. The count is kept in memory, so a restart
resets it: the cap bounds spend per process, not exactly per day.
"""

from __future__ import annotations

import os
import threading
from datetime import UTC, date, datetime

from academic_agent.language import plan_topic_search


def _daily_limit() -> int:
    try:
        return max(0, int(os.getenv("PLAN_PREVIEW_DAILY_LIMIT", "20")))
    except ValueError:
        return 20


# 0 turns previews off; the browser then starts runs as it did before.
DAILY_LIMIT = _daily_limit()

_lock = threading.Lock()
_counts: dict[tuple[date, str | None], int] = {}


class PreviewLimitReached(Exception):
    pass


def enabled() -> bool:
    return DAILY_LIMIT > 0


def admit(owner: str | None) -> None:
    """Count one preview for `owner` today, or raise when the cap is reached."""
    today = datetime.now(UTC).date()
    with _lock:
        for key in [key for key in _counts if key[0] != today]:
            del _counts[key]
        used = _counts.get((today, owner), 0)
        if used >= DAILY_LIMIT:
            raise PreviewLimitReached(f"{DAILY_LIMIT} topic previews already used today")
        _counts[(today, owner)] = used + 1


def preview(topic: str) -> dict:
    plan = plan_topic_search(topic, n=2)
    return {
        "resolved": plan.resolved,
        "search_topic": plan.search_topic,
        "aliases": list(plan.aliases),
        "components": list(plan.components),
    }
