"""Which retrieval lanes keep coming back empty or refused, across recent runs.

One run's audit says why its academic sources were thin. It cannot say that
Semantic Scholar has refused every request this week, or that OpenAlex's
daily budget ran out at noon; those only show up when the audits of several
runs are read together. This module reads them and returns counts per lane,
with no topics, queries or run ids, so the summary can be shown to any code
holder without revealing what anyone searched for.

Coverage is uneven by design of the pipeline: the S2, PubMed and arXiv rows
exist only when OpenAlex left slots open or the lane recorded a failure, so
their counts describe the runs that needed them, not every run.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

DEFAULT_WINDOW = 20
# A lane needs this many observed runs before it is flagged at all.
MIN_OBSERVED_RUNS = 3
# Flag a lane that failed in at least half of its observed runs ...
FAILING_SHARE = 0.5
# ... or that returned nothing in at least this share without failing.
MOSTLY_EMPTY_SHARE = 0.8

# Saved by a run that collected sources, and by one that stopped short of the
# academic minimum (no registry exists then), in that order of preference.
_AUDIT_FILES = ("validated_sources.json", "retrieval_diagnostics.json")

# "[OA-Cluster:T123] topic" -> "OA-Cluster"
_BRACKET_LABEL = re.compile(r"^\[([^\]:]+)")
_RENAMED_LABELS = {
    "OpenAlex-Recent 2023+": "OA-Recent",
    "OpenAlex-Cited": "OA-Cited",
    "SemanticScholar": "S2",
    "Serper-Fallback": "academic web search",
}
# Audit rows that record a step after retrieval (filtering, page dating), not a
# search for sources.
_NOT_RETRIEVAL = frozenset({
    "Relevance-Filter",
    "Relevance-Recovery-Filter",
    "Relaxed-Title-Gate",
    "Deferred-Promotion",
    "Page-Dates",
})
# Notes written when a client gives up, e.g. "Semantic Scholar refused the
# request (HTTP 429 ...)", "OpenAlex request failed (HTTP 500)", "Tavily search
# failed for ...", "Lens.org unavailable (HTTP 401 ...)". The prefix may not
# contain a colon or a quote, so a rejected paper title that happens to hold
# these words ("title not relevant to topic: '...'") never matches.
_FAILURE_NOTE = re.compile(
    r"^(?:[^:'\"]{0,40} )?(?:refused the request|request failed|search failed for|unavailable \()"
)


def _lane(row: dict[str, Any]) -> str | None:
    query = str(row.get("query") or "")
    match = _BRACKET_LABEL.match(query)
    if match is None:
        return f"{row.get('domain') or 'unknown'} web search"
    label = match.group(1).strip()
    if label in _NOT_RETRIEVAL:
        return None
    return _RENAMED_LABELS.get(label, label)


def _failed(row: dict[str, Any]) -> bool:
    return any(
        isinstance(reason, str) and _FAILURE_NOTE.match(reason)
        for reason in row.get("rejected_reasons") or []
    )


def run_lanes(record: dict[str, Any]) -> dict[str, dict[str, bool]]:
    """Lane -> {"empty", "failed"} for one run's saved audit.

    A lane is empty when none of its rows returned a result, and failed when
    any of them recorded a refusal or failure.
    """
    lanes: dict[str, dict[str, bool]] = {}
    for row in record.get("audit") or []:
        if not isinstance(row, dict) or (lane := _lane(row)) is None:
            continue
        state = lanes.setdefault(lane, {"empty": True, "failed": False})
        state["empty"] = state["empty"] and not row.get("result_count")
        state["failed"] = state["failed"] or _failed(row)
    # A web-search domain that failed outright may have left no rows at all.
    for domain in record.get("failed_domains") or {}:
        lanes.setdefault(f"{domain} web search", {"empty": True, "failed": False})["failed"] = True
    return lanes


def _saved_audit(run_dir: Path) -> dict[str, Any] | None:
    for name in _AUDIT_FILES:
        try:
            record = json.loads((run_dir / name).read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            return None
        if isinstance(record, dict) and isinstance(record.get("audit"), list):
            return record
    return None


def summarize(run_dirs: Iterable[Path], *, window: int = DEFAULT_WINDOW) -> dict[str, Any]:
    """Per-lane counts over the newest `window` runs that saved an audit.

    `run_dirs` must be newest first. Runs still collecting sources, and runs
    that failed before retrieval, saved no audit and are skipped.
    """
    counts: dict[str, dict[str, int]] = {}
    examined = 0
    for run_dir in run_dirs:
        if examined >= window:
            break
        record = _saved_audit(run_dir)
        if record is None:
            continue
        examined += 1
        for lane, state in run_lanes(record).items():
            lane_counts = counts.setdefault(lane, {"observed_runs": 0, "empty_runs": 0, "failed_runs": 0})
            lane_counts["observed_runs"] += 1
            lane_counts["empty_runs"] += state["empty"]
            lane_counts["failed_runs"] += state["failed"]

    failing: list[str] = []
    mostly_empty: list[str] = []
    for lane, c in sorted(counts.items()):
        if c["observed_runs"] < MIN_OBSERVED_RUNS:
            continue
        if c["failed_runs"] >= FAILING_SHARE * c["observed_runs"]:
            failing.append(lane)
        elif c["empty_runs"] >= MOSTLY_EMPTY_SHARE * c["observed_runs"]:
            mostly_empty.append(lane)
    return {
        "window": window,
        "runs_examined": examined,
        "lanes": [{"lane": lane, **c} for lane, c in sorted(counts.items())],
        "failing": failing,
        "mostly_empty": mostly_empty,
    }
