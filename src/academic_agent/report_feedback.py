"""One-click feedback on a delivered report, kept with the run.

Whether a report changes a decision is the project's open question: two user
studies closed without establishing it, and nothing since has asked a reader.
This records a reader's answer beside the run it is about: a closed
vocabulary, no free text, one record per responder, replaced by a later
answer. It is a signal for the operator's ops report, not a rating shown to
other readers.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path

FILE_NAME = "feedback.json"
SCHEMA_VERSION = 1
CHANGED_VIEW = ("yes", "no", "unsure")
PARTS = ("scorecard", "report", "sources", "checks")
# An ownerless run (a visitor's own key) has one responder: whoever holds its URL.
HOLDER = "holder"


class FeedbackUnreadable(OSError):
    """The file exists and cannot be read, or is not a feedback record."""


def responder_key(owner: str | None) -> str:
    return owner or HOLDER


def _valid(record: object) -> bool:
    return (
        isinstance(record, dict)
        and record.get("changed_view") in CHANGED_VIEW
        and (record.get("part") is None or record.get("part") in PARTS)
        and isinstance(record.get("recorded_at"), str)
    )


def _load(run_dir: Path) -> dict:
    path = run_dir / FILE_NAME
    if not path.exists():
        return {"schema_version": SCHEMA_VERSION, "responses": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise FeedbackUnreadable(f"{FILE_NAME} could not be read") from exc
    if not isinstance(data, dict) or not isinstance(data.get("responses"), dict):
        raise FeedbackUnreadable(f"{FILE_NAME} is not a feedback record")
    return data


def read(run_dir: Path, responder: str) -> dict | None:
    """The responder's own record, or None. Raises FeedbackUnreadable."""
    record = _load(run_dir)["responses"].get(responder)
    if record is None:
        return None
    if not _valid(record):
        raise FeedbackUnreadable(f"{FILE_NAME} holds a malformed response")
    return dict(record)


def record(run_dir: Path, responder: str, changed_view: str, part: str | None) -> dict:
    """Store the responder's answer, replacing their earlier one.

    A damaged file raises rather than being overwritten: it may hold other
    responders' answers. Raises FeedbackUnreadable or OSError.
    """
    if changed_view not in CHANGED_VIEW or (part is not None and part not in PARTS):
        raise ValueError("answer outside the fixed vocabulary")
    data = _load(run_dir)
    answer = {
        "changed_view": changed_view,
        "part": part,
        "recorded_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    data["schema_version"] = SCHEMA_VERSION
    data["responses"][responder] = answer
    path = run_dir / FILE_NAME
    temporary = path.with_name(FILE_NAME + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, sort_keys=True, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    return dict(answer)


def responses(run_dir: Path) -> list[dict] | None:
    """Every well-formed response, for the ops report; None for a damaged file."""
    try:
        data = _load(run_dir)
    except FeedbackUnreadable:
        return None
    return [dict(item) for item in data["responses"].values() if _valid(item)]
