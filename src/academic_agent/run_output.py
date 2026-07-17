"""Per-run output management for generated commercialization reports."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict
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
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
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
