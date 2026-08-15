"""Per-run output management for generated commercialization reports."""

import json
import warnings
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
class EvidenceArtifactsIncomplete(OSError):
    """Some evidence artifacts could not be written; the rest were.

    Subclasses OSError because that is what it wraps, and because a caller
    that already tolerates OSError around this call keeps working.
    """


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
    Every artifact that can be written is written. Returns those paths.

    Raises EvidenceArtifactsIncomplete afterwards if any write failed, so the
    caller can record that the audit trail is missing without losing the
    report. Silently returning a short list instead made partial loss
    undetectable: the caller saw no exception, marked the evidence saved, and
    a run whose sources-to-findings record was half gone looked identical to
    one that was complete.

    A task that produced no output is skipped, not failed — there was nothing
    to write.
    """
    if not run_id:
        raise ValueError(f"run_id must be a non-empty string, got {run_id!r}")
    run_directory = output_root / run_id
    run_directory.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    failures: list[str] = []
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
        except OSError as exc:
            # Keep going: the remaining artifacts are still worth having.
            failures.append(f"{filename}: {exc}")
            continue
        written.append(path)

    if failures:
        raise EvidenceArtifactsIncomplete(
            f"{len(failures)} of {len(failures) + len(written)} evidence "
            f"artifacts could not be written — " + "; ".join(failures)
        )
    return written


def save_claim_grounding(
    tasks_output: Sequence[Any],
    run_id: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict | None:
    """Screen the evidence tasks' claims against the sources they cite.

    Writes claim_grounding.json beside the evidence files and returns a
    summary for status.json, or None when there was nothing to screen.

    Deliberately not a guardrail. The existing guardrails block and retry, and
    this check is a heuristic: a false positive would fail a sound run and
    charge for a second attempt, while the errors it catches are ones a reader
    can act on after the fact. It reports; it does not reject.

    Never raises, for the same reason the evidence writer is best-effort — an
    audit that takes down the assessment it was auditing is worse than no
    audit.
    """
    from academic_agent.claim_grounding import check_report
    from academic_agent.evidence import EvidenceReport

    try:
        run_directory = output_root / run_id
        combined: list[Any] = []
        totals = {"checked": 0, "ungrounded": 0, "unverifiable": 0}
        # Also per domain, because the aggregate is actively misleading. Across
        # the 30-run baseline the overall figure was 14% checkable, which reads
        # as "this check barely works" — while the academic domain was 92% and
        # the market domain 0%. Market claims are quantitative-heavy and cite
        # market reports, which have no abstract anywhere; that zero is a fact
        # about the evidence, not a shortfall in the screen. One number cannot
        # say both things.
        per_domain: dict[str, dict[str, int]] = {}

        for index, filename in EVIDENCE_ARTIFACTS:
            if index >= len(tasks_output):
                continue
            raw = getattr(tasks_output[index], "raw", None)
            if not raw:
                continue
            try:
                report = EvidenceReport.model_validate_json(raw)
            except Exception:  # noqa: BLE001 - unparseable output is the
                # guardrail's business, not this screen's; skipping keeps the
                # two failures from being reported as one.
                continue
            result = check_report(report)
            domain = filename.split("_")[0]
            totals["checked"] += result.checked_count
            totals["ungrounded"] += result.ungrounded_count
            totals["unverifiable"] += result.unverifiable_count
            per_domain[domain] = {
                "checked": result.checked_count,
                "ungrounded": result.ungrounded_count,
                "unverifiable": result.unverifiable_count,
            }
            for check in result.checks:
                if check.status != "grounded":
                    combined.append({"domain": domain, **check.as_dict()})

        if not any(totals.values()):
            return None

        payload = {**totals, "by_domain": per_domain, "findings": combined}
        run_directory.mkdir(parents=True, exist_ok=True)
        (run_directory / "claim_grounding.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {**totals, "by_domain": per_domain}
    except Exception as exc:  # noqa: BLE001 - see the docstring
        warnings.warn(f"claim grounding screen failed: {type(exc).__name__}: {exc}")
        return None


def save_consistency(
    report_markdown: str,
    scores_raw: str | None,
    run_id: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> dict | None:
    """Check the finished report against its scorecard; return a summary.

    Runs after both exist, which is the only moment either can be compared
    with the other: the reviewer never sees the scorecard and the scorer never
    sees the reviewed report.

    Reports rather than blocks, for the same reason the citation screen does.
    A phrase table is a heuristic, and rejecting a finished six-agent run on
    one would throw away a paid assessment over a wording choice. What it
    earns instead is a place in the artifacts and a count on the status, where
    a reader meets it before acting on the recommendation.
    """
    from academic_agent.consistency import check

    try:
        if not report_markdown or not scores_raw:
            return None
        try:
            scores = json.loads(scores_raw)
        except (json.JSONDecodeError, TypeError):
            return None
        result = check(report_markdown, scores)
        if not result.checked:
            return None
        payload = result.as_dict()
        run_directory = output_root / run_id
        run_directory.mkdir(parents=True, exist_ok=True)
        (run_directory / "consistency.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"blockers": payload["blockers"], "warnings": payload["warnings"]}
    except Exception as exc:  # noqa: BLE001 - an audit must not fail a run
        warnings.warn(f"consistency check failed: {type(exc).__name__}: {exc}")
        return None


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
