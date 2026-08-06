"""Per-run output management for generated commercialization reports."""

import json
from collections.abc import Sequence
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Literal, TypedDict
from uuid import uuid4


class _StepEntryRequired(TypedDict):
    """Required fields that every steps.jsonl entry must carry."""
    agent_idx: int
    type: Literal["action", "result", "finish"]


class StepEntry(_StepEntryRequired, total=False):
    """Schema for a single line in steps.jsonl written by pipeline_worker."""
    thought: str
    tool: str
    tool_input: str
    result: str


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "outputs"


def create_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid4().hex[:10]}"


def save_report(
    report: str,
    run_id: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> tuple[str, Path]:
    if not run_id:
        raise ValueError(f"run_id must be a non-empty string, got {run_id!r}")
    run_directory = output_root / run_id
    run_directory.mkdir(parents=True, exist_ok=True)
    report_path = run_directory / "commercialization_report.md"
    report_path.write_text(report, encoding="utf-8")
    return run_id, report_path


def save_error(
    error_details: str,
    run_id: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    if not run_id:
        raise ValueError(f"run_id must be a non-empty string, got {run_id!r}")
    run_directory = output_root / run_id
    run_directory.mkdir(parents=True, exist_ok=True)
    error_path = run_directory / "error.log"
    error_path.write_text(error_details, encoding="utf-8")
    return error_path


#: Task index -> filename for the three evidence-gathering agents. Their JSON
#: output is what Tasks 4 and 6 actually read — neither the report writer nor
#: the scorer sees the raw source registry — so without these files the middle
#: of the pipeline leaves no trace and a questionable score cannot be traced
#: back to the agent that produced the reasoning behind it.
EVIDENCE_ARTIFACTS: tuple[tuple[int, str], ...] = (
    (0, "academic_evidence.json"),
    (1, "patent_evidence.json"),
    (2, "market_evidence.json"),
)


def save_evidence_reports(
    tasks_output: Sequence[Any],
    run_id: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> list[Path]:
    """Persist the evidence JSON from Tasks 1-3.

    Best-effort by design: these files are for inspection, so a failure to
    write one must never take down a run that has already produced a report.
    Returns the paths actually written.
    """
    if not run_id:
        raise ValueError(f"run_id must be a non-empty string, got {run_id!r}")
    run_directory = output_root / run_id
    run_directory.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for index, filename in EVIDENCE_ARTIFACTS:
        if index >= len(tasks_output):
            continue
        raw = getattr(tasks_output[index], "raw", None)
        if not raw:
            continue
        path = run_directory / filename
        try:
            # Reformat when it parses, so the file is readable; keep the raw
            # text when it does not, because unparseable output is exactly
            # what someone debugging this stage needs to see.
            text = json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
        except (json.JSONDecodeError, TypeError):
            text = raw if isinstance(raw, str) else str(raw)
        try:
            path.write_text(text, encoding="utf-8")
        except OSError:
            continue
        written.append(path)
    return written


def save_source_collection(
    collection_json: str,
    run_id: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    if not run_id:
        raise ValueError(f"run_id must be a non-empty string, got {run_id!r}")
    run_directory = output_root / run_id
    run_directory.mkdir(parents=True, exist_ok=True)
    source_path = run_directory / "validated_sources.json"
    source_path.write_text(collection_json, encoding="utf-8")
    return source_path


def save_scores(
    scores_json: str,
    run_id: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    if not run_id:
        raise ValueError(f"run_id must be a non-empty string, got {run_id!r}")
    run_directory = output_root / run_id
    run_directory.mkdir(parents=True, exist_ok=True)
    scores_path = run_directory / "commercialization_scores.json"
    scores_path.write_text(scores_json, encoding="utf-8")
    return scores_path


def save_reviewer_notes(
    notes: str,
    run_id: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    if not run_id:
        raise ValueError(f"run_id must be a non-empty string, got {run_id!r}")
    run_directory = output_root / run_id
    run_directory.mkdir(parents=True, exist_ok=True)
    notes_path = run_directory / "reviewer_notes.md"
    notes_path.write_text(notes, encoding="utf-8")
    return notes_path
