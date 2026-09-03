"""Per-run output management for generated commercialization reports."""

import json
import math
import re
import secrets
import warnings
from collections.abc import Sequence
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Literal, TypedDict

from academic_agent.report_applicability import add_applicability_block


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


#: Bytes of randomness in a run id's suffix. The id is not only a name: the
#: API treats a run URL as a capability, so anyone holding one can read the
#: report and anyone who guesses one can too. It used to be uuid4().hex[:10] —
#: 40 bits, against a timestamp prefix that tells an attacker which minute to
#: search. Rate limiting makes 40 bits impractical to brute force in practice,
#: which is a weaker thing to be relying on than the id itself when the run may
#: hold an unpublished paper. 128 bits costs nothing.
#:
#: Old ids stay readable: nothing parses the suffix, and _RUN_ID_PATTERN in
#: api/runs.py matches [0-9a-f]+ at any length.
_RUN_ID_ENTROPY_BYTES = 16


def create_run_id() -> str:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{secrets.token_hex(_RUN_ID_ENTROPY_BYTES)}"


def save_report(
    report: str,
    run_id: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    decision_gate: dict[str, Any] | None = None,
    output_language: str = "English",
) -> tuple[str, Path]:
    if not run_id:
        raise ValueError(f"run_id must be a non-empty string, got {run_id!r}")
    run_directory = output_root / run_id
    run_directory.mkdir(parents=True, exist_ok=True)
    report_path = run_directory / "commercialization_report.md"
    delivered_report = add_applicability_block(
        report, decision_gate=decision_gate, output_language=output_language
    )
    report_path.write_text(delivered_report, encoding="utf-8")
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


def save_retrieval_diagnostics(
    diagnostics: dict[str, Any],
    run_id: str,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> Path:
    """Persist why source collection failed before a registry could exist."""
    if not run_id:
        raise ValueError(f"run_id must be a non-empty string, got {run_id!r}")
    run_directory = output_root / run_id
    run_directory.mkdir(parents=True, exist_ok=True)
    path = run_directory / "retrieval_diagnostics.json"
    path.write_text(
        json.dumps(diagnostics, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return path


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
) -> dict:
    """Screen the evidence tasks' claims against the sources they cite.

    Writes claim_grounding.json beside the evidence files and returns a
    summary for status.json. The summary always names whether the screen
    completed, was inapplicable, was only partial, or failed; absence is
    reserved for runs created before this contract existed.

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
        totals = {"checked": 0, "ungrounded": 0, "unverifiable": 0,
                  "duplicates_collapsed": 0}
        # Also per domain, because the aggregate is actively misleading. Across
        # the 30-run baseline the overall figure was 14% checkable, which reads
        # as "this check barely works" — while the academic domain was 92% and
        # the market domain 0%. Market claims are quantitative-heavy and cite
        # market reports, which have no abstract anywhere; that zero is a fact
        # about the evidence, not a shortfall in the screen. One number cannot
        # say both things.
        per_domain: dict[str, dict[str, int]] = {}
        screened_domains: list[str] = []
        unavailable_domains: list[str] = []

        for index, filename in EVIDENCE_ARTIFACTS:
            domain = filename.split("_")[0]
            if index >= len(tasks_output):
                unavailable_domains.append(domain)
                continue
            raw = getattr(tasks_output[index], "raw", None)
            if not raw:
                unavailable_domains.append(domain)
                continue
            try:
                report = EvidenceReport.model_validate_json(raw)
            except Exception:  # noqa: BLE001 - unparseable output is the
                # guardrail's business, but the audit still records that this
                # domain could not be checked instead of disappearing as a pass.
                unavailable_domains.append(domain)
                continue
            result = check_report(report)
            if result.error:
                unavailable_domains.append(domain)
                continue
            screened_domains.append(domain)
            totals["checked"] += result.checked_count
            totals["ungrounded"] += result.ungrounded_count
            totals["unverifiable"] += result.unverifiable_count
            totals["duplicates_collapsed"] += result.duplicates_collapsed
            per_domain[domain] = {
                "checked": result.checked_count,
                "ungrounded": result.ungrounded_count,
                "unverifiable": result.unverifiable_count,
                "duplicates_collapsed": result.duplicates_collapsed,
            }
            for check in result.checks:
                if check.status != "grounded":
                    combined.append({"domain": domain, **check.as_dict()})

        if unavailable_domains:
            status = "partial" if screened_domains else "unavailable"
        elif not any(totals.values()):
            # Valid evidence reports with no distinctive quantitative claim are
            # not a failed audit and not a clean citation result.
            status = "not_applicable"
        else:
            status = "completed"

        payload = {
            "status": status,
            **totals,
            "by_domain": per_domain,
            "screened_domains": screened_domains,
            "unavailable_domains": unavailable_domains,
            "findings": combined,
        }
        run_directory.mkdir(parents=True, exist_ok=True)
        (run_directory / "claim_grounding.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {key: value for key, value in payload.items() if key != "findings"}
    except Exception as exc:  # noqa: BLE001 - see the docstring
        warnings.warn(f"claim grounding screen failed: {type(exc).__name__}: {exc}")
        # The caller can still persist this stable state in status.json even
        # when the detailed artifact itself could not be written. Never return
        # None here: old runs, no applicable claims, and an audit failure are
        # three different facts.
        return {
            "status": "failed",
            "checked": 0,
            "ungrounded": 0,
            "unverifiable": 0,
            "duplicates_collapsed": 0,
            "by_domain": {},
            "screened_domains": [],
            "unavailable_domains": [],
        }


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


_SCORE_RATIONALE_FIELDS = (
    ("trl_score", "trl_rationale"),
    ("mrl_score", "mrl_rationale"),
    ("patent_strength", "patent_rationale"),
    ("market_accessibility", "market_rationale"),
    ("evidence_confidence", "evidence_rationale"),
)
_SCORE_NOUNS = "score|rating|confidence|accessibility|strength|readiness"
_RATING_ADJECTIVES = "low|weak|limited|moderate|medium|strong|high"


def _delivered_and_raw_score_text(value: Any) -> tuple[str, str] | None:
    """Return the client-scale value and its exact internal x10 integer."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    delivered = float(value)
    raw = delivered * 10
    if not math.isfinite(delivered) or not raw.is_integer() or not 0 <= raw <= 100:
        return None
    return f"{delivered:g}", str(int(raw))


def _normalize_qwen_score_phrase(rationale: str, delivered_score: Any) -> str:
    pair = _delivered_and_raw_score_text(delivered_score)
    if pair is None:
        return rationale
    delivered, raw = pair
    escaped_raw = re.escape(raw)
    rated_pattern = re.compile(
        rf"(?P<prefix>\b(?:{_SCORE_NOUNS})\s+"
        rf"(?:(?:is|was|remains)\s+)?rated\s+(?:at|as)\s*)"
        rf"{escaped_raw}(?![\d.%])"
        rf"(?=\s*(?:[,.;:)]|$|\b(?:because|based|reflecting|given|with)\b))",
        re.IGNORECASE,
    )
    parenthetical_pattern = re.compile(
        rf"(?P<prefix>\b(?:{_SCORE_NOUNS})\s+"
        rf"(?:is|was|remains)\s+(?:very\s+)?(?:{_RATING_ADJECTIVES})\s+\(\s*)"
        rf"{escaped_raw}(?P<suffix>\s*\))(?!\d)",
        re.IGNORECASE,
    )
    normalized = rated_pattern.sub(
        lambda match: f"{match.group('prefix')}{delivered}", rationale
    )
    return parenthetical_pattern.sub(
        lambda match: f"{match.group('prefix')}{delivered}{match.group('suffix')}",
        normalized,
    )


def _normalize_delivered_score_rationales(scores_json: str) -> str:
    """Repair only bounded raw-scale phrases at the persisted client seam.

    The scoring guardrail already handles generic explicit score forms. The
    first paid Qwen canary used two new phrases that passed that guardrail
    while the numeric fields were correct. This second defense belongs here:
    every fresh or restored scorer output reaches this file before API and
    browser readers do.

    Moving the rule into evidence.py would change byte-locked dependencies of
    consumed OpenAlex experiments. Updating those historical hashes would
    falsely rewrite their method identity, so the persistence seam is both
    the narrowest production fix and the one that preserves experiment lineage.
    """

    try:
        payload = json.loads(scores_json)
    except json.JSONDecodeError:
        # Persisting the original diagnostic payload preserves save_scores'
        # pre-existing behavior; validation belongs to the scorer guardrail.
        return scores_json
    if not isinstance(payload, dict):
        return scores_json

    changed = False
    for score_field, rationale_field in _SCORE_RATIONALE_FIELDS:
        rationale = payload.get(rationale_field)
        if not isinstance(rationale, str):
            continue
        normalized = _normalize_qwen_score_phrase(
            rationale, payload.get(score_field)
        )
        if normalized != rationale:
            payload[rationale_field] = normalized
            changed = True

    if not changed:
        return scores_json
    return json.dumps(payload, ensure_ascii=False)


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
    scores_path.write_text(
        _normalize_delivered_score_rationales(scores_json), encoding="utf-8"
    )
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
