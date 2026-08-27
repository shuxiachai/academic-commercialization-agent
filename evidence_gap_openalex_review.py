"""Lock and review the one anonymous OpenAlex live-value execution.

The anonymous run is a separate experiment from the credentialed eight-case
Phase 4 study.  This module therefore binds the exact executed bytes instead
of widening the older protocol after observation.  Packet preparation and
summary are zero-network operations and never authorize production Tool
Calling.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evidence_gap_openalex_live import (
    EXPECTED_IMPLEMENTATION_SHA256,
    AnonymousOpenAlexExecutionArtifact,
    AnonymousOpenAlexManifestArtifact,
    _AGGREGATE_SOURCE_FILES,
)
from evidence_gap_phase4_audit import EXPECTED_FIXTURE_SHA256
from evidence_gap_phase4_live import (
    Phase4CaseExecution,
    _CANDIDATE_COLUMNS,
    _REVIEW_COLUMNS,
    _candidate_rows,
    _provider_accounting_issue,
)

# Label semantics are intentionally shared with the credentialed Phase 4
# review.  Reusing these narrow, already-tested primitives prevents the same
# YES/NO declaration from acquiring a different meaning merely because this
# study used anonymous OpenAlex access.  Source validation, identities,
# thresholds, packet modes and results remain experiment-specific below.
from evidence_gap_phase4_review import (
    DECLARATION_FIELDS,
    ELIGIBLE_AI_USE,
    REVIEW_FIELDS,
    VALID_LABEL_PAIRS,
    Phase4ReviewError as AnonymousOpenAlexReviewError,
    ReviewCandidate,
    _baseline_contexts,
    _candidate_from_row,
    _file_sha256,

    _read_csv,
    _read_json_object,
    _validated_declaration,
    _validated_label,
    _write_csv_new,
    _write_text_new,
)


EXPECTED_EXECUTED_REVISION = "7bfe4eadbf2ead7549125e59d0156c9fa3c1bf94"
EXPECTED_SOURCE_FILE_SHA256 = {
    "manifest.json": (
        "a53e05dc31b41a047307f393670f2983cf3ca3d6dab8c92f7bc58f8e9ecd7de0"
    ),
    "execution.json": (
        "44298f78a0006eeb61f544620ce693dc1510cad015f43b0b1e94d6c6b1c7ffec"
    ),
    "candidates.csv": (
        "91d148f97320582fe29987ff2ef139f7e3cb3d53ab2473ef1ac4ad3119805006"
    ),
    "review.csv": (
        "c3fc1f61c9cd07257bff9ea95e77a9a07f674ec2a92b75ab21713a675579e191"
    ),
    "artifact-index.json": (
        "e5ed0d0bc7bb044e3c2790b4f05e8f41c06195f6543e8285f8f57dd086014881"
    ),
    "case-executions/D01.json": (
        "afeaca1f650a165f94889c24e09d1b1ed42fb9fb949bb1bbff6417ed3c596a2e"
    ),
    "case-executions/D02.json": (
        "5a665b7349453a4ed03c19543307276108e5e7fa32191a5fc193faf64138cd6a"
    ),
    "case-executions/D03.json": (
        "8fa921e959e5b2904360e1577b501a1b5ab082c35f37b6b6367e9e2a2a8d50d6"
    ),
    "case-executions/D04.json": (
        "b2e1ae2909786d3a72aa2bdc91bb02f513b7566ca5820dd26b96add719940ade"
    ),
}
SOURCE_FILES = tuple(EXPECTED_SOURCE_FILE_SHA256)
CASE_IDS = ("D01", "D02", "D03", "D04")
EXPECTED_ACCEPTED_PER_CASE = {"D01": 1, "D02": 2, "D03": 3, "D04": 3}
EXPECTED_REVIEW_ROW_COUNT = 9
ACCEPTED_CASES_MIN = 3
WRONG_SOURCE_RATE_MAX = 0.05
NOVEL_RELEVANT_CASES_MIN = 3
MEASUREMENT_LIMIT = (
    "This anonymous OpenAlex study measures candidate relevance and "
    "baseline-relative novelty for one frozen four-case execution, not planner "
    "precision, provider-wide source truth, report value, or production utility."
)


class AnonymousOpenAlexSourceLock(BaseModel):
    """Study-owner attestation over the exact anonymous execution bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["anonymous_openalex_source_artifact_lock"] = (
        "anonymous_openalex_source_artifact_lock"
    )
    production_connected: Literal[False] = False
    report_workflow_connected: Literal[False] = False
    api_key_used: Literal[False] = False
    authorized_output: Literal[True] = True
    executed_revision: str = Field(pattern=r"^[0-9a-f]{40}$")
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    source_file_sha256: dict[str, str]
    study_owner_id: str = Field(min_length=2, max_length=200)
    authorized_at: datetime
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _validate_frozen_identity(self) -> "AnonymousOpenAlexSourceLock":
        if self.executed_revision != EXPECTED_EXECUTED_REVISION:
            raise ValueError("source lock executed revision does not match")
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("source lock fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("source lock implementation identities do not match")
        if self.source_file_sha256 != EXPECTED_SOURCE_FILE_SHA256:
            raise ValueError("source lock does not identify the frozen anonymous run")
        if self.authorized_at.tzinfo is None:
            raise ValueError("source lock timestamp must be timezone-aware")
        return self


@dataclass(frozen=True)
class AnonymousSourceSnapshot:
    """Validated source reused unchanged at lock, packet and result seams."""

    file_hashes: dict[str, str]
    execution: AnonymousOpenAlexExecutionArtifact
    candidates: tuple[ReviewCandidate, ...]
    baseline_contexts: tuple[dict[str, Any], ...]


def _validate_artifact_index(
    source_dir: Path,
    file_hashes: Mapping[str, str],
) -> None:
    index = _read_json_object(source_dir / "artifact-index.json")
    expected = {
        "schema_version": 1,
        "mode": "anonymous_openalex_artifact_index",
        "production_connected": False,
        "source_file_sha256": {
            name: file_hashes[name] for name in _AGGREGATE_SOURCE_FILES
        },
    }
    if index != expected:
        raise AnonymousOpenAlexReviewError(
            "artifact index does not match aggregate anonymous-run bytes"
        )


def _validate_complete_execution(
    manifest: AnonymousOpenAlexManifestArtifact,
    execution: AnonymousOpenAlexExecutionArtifact,
) -> None:
    if execution.overall_state != "completed":
        raise AnonymousOpenAlexReviewError(
            "only the completed four-case anonymous run may be source-locked"
        )
    if (
        execution.request_count != 4
        or execution.attempted_case_count != 4
        or execution.successful_case_count != 4
    ):
        raise AnonymousOpenAlexReviewError(
            "anonymous source execution must contain four successful requests"
        )
    if execution.provider_summary.stopped_reason != "completed":
        raise AnonymousOpenAlexReviewError(
            "anonymous provider boundary did not report completion"
        )
    if execution.provider_summary.cost_state != "known":
        raise AnonymousOpenAlexReviewError(
            "anonymous OpenAlex accounting is not inspectable"
        )
    if (
        manifest.fixture_sha256 != execution.fixture_sha256
        or manifest.implementation_sha256 != execution.implementation_sha256
        or manifest.soft_stop_usd != execution.soft_stop_usd
    ):
        raise AnonymousOpenAlexReviewError(
            "execution identity does not join the persisted manifest"
        )

    expected_cases = {
        case.spec.case_id: (
            case.spec.provider,
            case.collection_sha256,
            case.plan_sha256,
        )
        for case in manifest.cases
    }
    observed_cases = {
        case.case_id: (case.provider, case.collection_sha256, case.plan_sha256)
        for case in execution.cases
    }
    if observed_cases != expected_cases:
        raise AnonymousOpenAlexReviewError(
            "execution cases do not join the frozen manifest"
        )

    costs: list[float] = []
    for case in execution.cases:
        issue = _provider_accounting_issue(case)
        if issue is not None:
            raise AnonymousOpenAlexReviewError(
                f"{case.case_id}: completed provider accounting is invalid: {issue}"
            )
        cost = case.audit.incremental_search_cost_usd
        if cost is None:
            raise AnonymousOpenAlexReviewError(
                f"{case.case_id}: provider cost is not inspectable"
            )
        costs.append(cost)
    observed_cost = sum(costs)
    reported_cost = execution.provider_summary.reported_cost_usd
    if reported_cost is None or abs(reported_cost - observed_cost) > 1e-12:
        raise AnonymousOpenAlexReviewError(
            "provider summary cost does not equal the four case journals"
        )


def _validate_case_journals(
    source_dir: Path,
    execution: AnonymousOpenAlexExecutionArtifact,
) -> None:
    journal_dir = source_dir / "case-executions"
    if not journal_dir.is_dir():
        raise AnonymousOpenAlexReviewError("case-executions directory is missing")
    observed_names = {path.name for path in journal_dir.glob("*.json")}
    expected_names = {f"{case_id}.json" for case_id in CASE_IDS}
    if observed_names != expected_names:
        raise AnonymousOpenAlexReviewError(
            "case journals do not cover D01 through D04 exactly"
        )
    execution_by_id = {case.case_id: case for case in execution.cases}
    for case_id in CASE_IDS:
        journal = Phase4CaseExecution.model_validate(
            _read_json_object(journal_dir / f"{case_id}.json")
        )
        if journal != execution_by_id[case_id]:
            raise AnonymousOpenAlexReviewError(
                f"{case_id}: case journal does not match aggregate execution"
            )


def validate_finalized_source(
    source_dir: Path,
    *,
    expected_hashes: Mapping[str, str] | None = None,
) -> AnonymousSourceSnapshot:
    """Validate exact live bytes and semantic joins without mutating evidence."""

    if not source_dir.is_dir():
        raise AnonymousOpenAlexReviewError(
            f"source directory does not exist: {source_dir}"
        )
    file_hashes = {name: _file_sha256(source_dir / name) for name in SOURCE_FILES}
    if file_hashes != EXPECTED_SOURCE_FILE_SHA256:
        drift = {
            name: {
                "expected": EXPECTED_SOURCE_FILE_SHA256[name],
                "observed": file_hashes[name],
            }
            for name in SOURCE_FILES
            if file_hashes[name] != EXPECTED_SOURCE_FILE_SHA256[name]
        }
        raise AnonymousOpenAlexReviewError(
            f"source is not the frozen anonymous execution: {drift}"
        )
    if expected_hashes is not None and file_hashes != dict(expected_hashes):
        raise AnonymousOpenAlexReviewError(
            "source artifact identity drifted after source locking"
        )
    _validate_artifact_index(source_dir, file_hashes)

    manifest = AnonymousOpenAlexManifestArtifact.model_validate(
        _read_json_object(source_dir / "manifest.json")
    )
    execution = AnonymousOpenAlexExecutionArtifact.model_validate(
        _read_json_object(source_dir / "execution.json")
    )
    _validate_complete_execution(manifest, execution)
    _validate_case_journals(source_dir, execution)

    candidate_rows = _read_csv(source_dir / "candidates.csv", _CANDIDATE_COLUMNS)
    review_rows = _read_csv(source_dir / "review.csv", _REVIEW_COLUMNS)
    expected_candidates, expected_reviews = _candidate_rows(execution.cases)
    if candidate_rows != expected_candidates:
        raise AnonymousOpenAlexReviewError(
            "candidate CSV does not preserve every executor disposition"
        )
    if review_rows != expected_reviews:
        raise AnonymousOpenAlexReviewError(
            "blank review CSV does not match quarantine-accepted candidates"
        )

    candidates: list[ReviewCandidate] = []
    seen: set[tuple[str, str]] = set()
    per_case = Counter[str]()
    for row in review_rows:
        if any(row[field].strip() for field in ("relevant", "novel", "review_note")):
            raise AnonymousOpenAlexReviewError("source review.csv is no longer blank")
        candidate = _candidate_from_row(row)
        if candidate.case_id not in CASE_IDS or candidate.provider != "openalex":
            raise AnonymousOpenAlexReviewError(
                f"unexpected anonymous-review identity: {candidate.row_id}"
            )
        key = (candidate.case_id, candidate.accepted_source_id)
        if key in seen:
            raise AnonymousOpenAlexReviewError(
                f"source review rows duplicate {candidate.row_id}"
            )
        seen.add(key)
        per_case[candidate.case_id] += 1
        candidates.append(candidate)
    if len(candidates) != EXPECTED_REVIEW_ROW_COUNT or dict(per_case) != (
        EXPECTED_ACCEPTED_PER_CASE
    ):
        raise AnonymousOpenAlexReviewError(
            "accepted-candidate denominator drifted from the frozen 1/2/3/3 rows"
        )

    # Phase 4 manifest cases carry the same frozen collection schema.  Reusing
    # this projection is deliberate: novelty must be judged against byte-identical
    # baseline source identities and summaries, not a shortened retrospective.
    baseline_contexts = _baseline_contexts(manifest)  # type: ignore[arg-type]
    if [item["case_id"] for item in baseline_contexts] != list(CASE_IDS):
        raise AnonymousOpenAlexReviewError("baseline case order drifted")
    return AnonymousSourceSnapshot(
        file_hashes=file_hashes,
        execution=execution,
        candidates=tuple(candidates),
        baseline_contexts=baseline_contexts,
    )


def create_source_lock(
    source_dir: Path,
    output_path: Path,
    *,
    study_owner_id: str,
    confirm_authorized_output: bool,
    note: str | None = None,
    authorized_at: datetime | None = None,
) -> AnonymousOpenAlexSourceLock:
    """Freeze the inspected anonymous run separately from reviewer files."""

    if not confirm_authorized_output:
        raise AnonymousOpenAlexReviewError(
            "source locking requires explicit authorized-output confirmation"
        )
    if output_path.exists():
        raise AnonymousOpenAlexReviewError(
            f"refusing to overwrite source lock: {output_path}"
        )
    snapshot = validate_finalized_source(source_dir)
    lock = AnonymousOpenAlexSourceLock(
        executed_revision=EXPECTED_EXECUTED_REVISION,
        fixture_sha256=EXPECTED_FIXTURE_SHA256,
        implementation_sha256=EXPECTED_IMPLEMENTATION_SHA256,
        source_file_sha256=snapshot.file_hashes,
        study_owner_id=study_owner_id.strip(),
        authorized_at=authorized_at or datetime.now(UTC),
        note=note.strip() if note and note.strip() else None,
    )
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AnonymousOpenAlexReviewError(
            f"could not create source-lock parent {output_path.parent}: {exc}"
        ) from exc
    _write_text_new(
        output_path,
        json.dumps(
            lock.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
    )
    return lock


def _load_source_lock(path: Path) -> AnonymousOpenAlexSourceLock:
    try:
        return AnonymousOpenAlexSourceLock.model_validate(_read_json_object(path))
    except ValueError as exc:
        if isinstance(exc, AnonymousOpenAlexReviewError):
            raise
        raise AnonymousOpenAlexReviewError(f"source lock is invalid: {exc}") from exc


def _packet_readme(snapshot: AnonymousSourceSnapshot) -> str:
    case_rows = "\n".join(
        (
            f"| {item['case_id']} | {item['topic']} | {item['gap_subject']} | "
            f"{item['query']} |"
        )
        for item in snapshot.baseline_contexts
    )
    baseline_rows = "\n".join(
        (
            f"| {item['case_id']} | {item['gap_state']} | "
            f"{len(item['baseline_sources'])} |"
        )
        for item in snapshot.baseline_contexts
    )
    return f"""# Anonymous OpenAlex human value-review packet

This packet contains the nine quarantine-accepted candidates from one exact,
completed, production-disconnected anonymous OpenAlex run. Preparing or
summarizing it makes zero API or LLM calls.

Do not edit `packet_manifest.json`. Complete only `labels.csv` and
`reviewer_declaration.csv`. Rows may be reordered, but identity fields must not
change. Do not send the separate source-lock file to the reviewer.

## Case targets

| Case | Topic | Declared academic gap | Frozen query |
|---|---|---|---|
{case_rows}

## Frozen baseline visible to the reviewer

| Case | Gap state | Baseline sources |
|---|---|---:|
{baseline_rows}

Full baseline source identities and evidence summaries are in
`baseline_contexts` inside `packet_manifest.json`. Read the matching case before
assigning `novel`. Novelty means materially absent from this frozen baseline,
not absent from the wider literature.

Attempt every candidate URL and inspect the OpenAlex work page plus available
abstract or linked source content. Judge direct relevance to the declared gap,
not broad topic overlap.

## Labels

- `YES/YES`: directly relevant and materially absent from the frozen baseline.
- `YES/NO`: directly relevant but already represented in the baseline.
- `NO/N/A`: adjacent, generic, or otherwise not directly relevant.
- `UNVERIFIABLE/UNVERIFIABLE`: attempted, but insufficient source content was
  inspectable.

Every row requires a source-grounded `review_note`. Complete
`reviewer_declaration.csv` after all nine rows. `NONE` or `LANGUAGE_ONLY`
generative-AI use is eligible; substantive generated judgments are retained but
excluded from the human-value result. An unreachable source is
`UNVERIFIABLE`, never silently negative or positive.

The frozen gates require accepted candidates in at least three of four cases,
a directly irrelevant rate no greater than 5%, and novel relevant candidates
in at least three cases. Even a pass authorizes only a separately
pre-registered planner-trigger study, never production Tool Calling.
"""


def _provider_thresholds() -> dict[str, dict[str, int | float]]:
    return {
        "openalex": {
            "accepted_cases_min": ACCEPTED_CASES_MIN,
            "wrong_source_rate_max": WRONG_SOURCE_RATE_MAX,
            "novel_relevant_cases_min": NOVEL_RELEVANT_CASES_MIN,
            "case_count": 4,
        }
    }


def _packet_manifest(
    snapshot: AnonymousSourceSnapshot,
    source_lock_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "mode": "anonymous_openalex_value_review_packet",
        "prepared_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "production_connected": False,
        "report_workflow_connected": False,
        "executed_revision": EXPECTED_EXECUTED_REVISION,
        "source_lock_sha256": _file_sha256(source_lock_path),
        "source_file_sha256": snapshot.file_hashes,
        "row_count": len(snapshot.candidates),
        "baseline_contexts": list(snapshot.baseline_contexts),
        "rows": [
            {
                "case_id": candidate.case_id,
                "provider": candidate.provider,
                "accepted_source_id": candidate.accepted_source_id,
                "title": candidate.title,
                "url": candidate.url,
                "identity_sha256": candidate.identity_sha256,
            }
            for candidate in snapshot.candidates
        ],
        "valid_label_pairs": [list(pair) for pair in sorted(VALID_LABEL_PAIRS)],
        "provider_thresholds": _provider_thresholds(),
        "measurement_limit": MEASUREMENT_LIMIT,
    }


def prepare_packet(
    source_dir: Path,
    source_lock_path: Path,
    packet_dir: Path,
) -> dict[str, Any]:
    """Create a separate Schema v2 packet from source-locked exact bytes."""

    if packet_dir.exists():
        raise AnonymousOpenAlexReviewError(
            f"refusing to overwrite packet: {packet_dir}"
        )
    source_lock = _load_source_lock(source_lock_path)
    snapshot = validate_finalized_source(
        source_dir,
        expected_hashes=source_lock.source_file_sha256,
    )
    try:
        packet_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise AnonymousOpenAlexReviewError(
            f"could not create packet {packet_dir}: {exc}"
        ) from exc
    manifest = _packet_manifest(snapshot, source_lock_path)
    label_rows = [
        {
            "case_id": candidate.case_id,
            "provider": candidate.provider,
            "accepted_source_id": candidate.accepted_source_id,
            "title": candidate.title,
            "url": candidate.url,
            "relevant": "",
            "novel": "",
            "review_note": "",
        }
        for candidate in snapshot.candidates
    ]
    _write_csv_new(packet_dir / "labels.csv", REVIEW_FIELDS, label_rows)
    _write_csv_new(
        packet_dir / "reviewer_declaration.csv",
        DECLARATION_FIELDS,
        [{}],
    )
    _write_text_new(packet_dir / "README.md", _packet_readme(snapshot))
    _write_text_new(
        packet_dir / "packet_manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return manifest


def _manifest_candidates(
    manifest: dict[str, Any],
    snapshot: AnonymousSourceSnapshot,
    source_lock_path: Path,
) -> dict[tuple[str, str], ReviewCandidate]:
    if manifest.get("schema_version") != 2 or manifest.get("mode") != (
        "anonymous_openalex_value_review_packet"
    ):
        raise AnonymousOpenAlexReviewError(
            "packet manifest has the wrong schema or mode"
        )
    if (
        manifest.get("production_connected") is not False
        or manifest.get("report_workflow_connected") is not False
    ):
        raise AnonymousOpenAlexReviewError(
            "packet manifest must remain production-disconnected"
        )
    if manifest.get("executed_revision") != EXPECTED_EXECUTED_REVISION:
        raise AnonymousOpenAlexReviewError("packet executed revision drifted")
    if manifest.get("source_lock_sha256") != _file_sha256(source_lock_path):
        raise AnonymousOpenAlexReviewError("packet source-lock identity drifted")
    if manifest.get("source_file_sha256") != snapshot.file_hashes:
        raise AnonymousOpenAlexReviewError("packet source-file identities drifted")
    if manifest.get("baseline_contexts") != list(snapshot.baseline_contexts):
        raise AnonymousOpenAlexReviewError("packet baseline context drifted")
    if manifest.get("provider_thresholds") != _provider_thresholds():
        raise AnonymousOpenAlexReviewError("packet provider thresholds drifted")
    if manifest.get("valid_label_pairs") != [
        list(pair) for pair in sorted(VALID_LABEL_PAIRS)
    ]:
        raise AnonymousOpenAlexReviewError("packet label contract drifted")
    if manifest.get("measurement_limit") != MEASUREMENT_LIMIT:
        raise AnonymousOpenAlexReviewError("packet measurement limit drifted")
    try:
        prepared_at = datetime.fromisoformat(str(manifest["prepared_at"]))
    except (KeyError, ValueError) as exc:
        raise AnonymousOpenAlexReviewError(
            "packet prepared_at is not an ISO timestamp"
        ) from exc
    if prepared_at.tzinfo is None:
        raise AnonymousOpenAlexReviewError(
            "packet prepared_at must be timezone-aware"
        )

    rows = manifest.get("rows")
    if (
        not isinstance(rows, list)
        or manifest.get("row_count") != len(rows)
        or len(rows) != EXPECTED_REVIEW_ROW_COUNT
    ):
        raise AnonymousOpenAlexReviewError("packet row count is not inspectable")
    candidates: dict[tuple[str, str], ReviewCandidate] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise AnonymousOpenAlexReviewError("packet rows must be objects")
        candidate = _candidate_from_row(row)
        if row.get("identity_sha256") != candidate.identity_sha256:
            raise AnonymousOpenAlexReviewError(
                f"packet identity hash drifted for {candidate.row_id}"
            )
        key = (candidate.case_id, candidate.accepted_source_id)
        if key in candidates:
            raise AnonymousOpenAlexReviewError(
                f"packet duplicates identity {candidate.row_id}"
            )
        candidates[key] = candidate
    expected = {
        (candidate.case_id, candidate.accepted_source_id): candidate
        for candidate in snapshot.candidates
    }
    if candidates != expected:
        raise AnonymousOpenAlexReviewError(
            "packet candidates do not match source-locked rows"
        )
    return candidates


def _openalex_metrics(
    snapshot: AnonymousSourceSnapshot,
    completed: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, str], str]:
    accepted_case_ids = sorted({item.case_id for item in snapshot.candidates})
    wrong_source_count = sum(row["relevant"] == "NO" for row in completed)
    denominator = len(completed)
    wrong_source_rate = wrong_source_count / denominator if denominator else None
    novel_case_ids = sorted(
        {
            row["case_id"]
            for row in completed
            if row["relevant"] == "YES" and row["novel"] == "YES"
        }
    )
    thresholds = {
        "accepted_cases": (
            "pass" if len(accepted_case_ids) >= ACCEPTED_CASES_MIN else "fail"
        ),
        "wrong_source_rate": (
            "pass"
            if wrong_source_rate is not None
            and wrong_source_rate <= WRONG_SOURCE_RATE_MAX
            else "fail"
        ),
        "novel_relevant_cases": (
            "pass" if len(novel_case_ids) >= NOVEL_RELEVANT_CASES_MIN else "fail"
        ),
    }
    metrics = {
        "accepted_candidate_count": len(snapshot.candidates),
        "accepted_case_ids": accepted_case_ids,
        "accepted_case_count": len(accepted_case_ids),
        "wrong_source_count": wrong_source_count,
        "wrong_source_rate": wrong_source_rate,
        "novel_relevant_case_ids": novel_case_ids,
        "novel_relevant_case_count": len(novel_case_ids),
    }
    decision = "pass" if all(value == "pass" for value in thresholds.values()) else "fail"
    return metrics, thresholds, decision


def summarize_packet(
    source_dir: Path,
    source_lock_path: Path,
    packet_dir: Path,
) -> dict[str, Any]:
    """Validate source, packet, declaration and both remaining value gates."""

    if not packet_dir.is_dir():
        raise AnonymousOpenAlexReviewError(
            f"packet directory does not exist: {packet_dir}"
        )
    source_lock = _load_source_lock(source_lock_path)
    snapshot = validate_finalized_source(
        source_dir,
        expected_hashes=source_lock.source_file_sha256,
    )
    manifest = _read_json_object(packet_dir / "packet_manifest.json")
    expected_candidates = _manifest_candidates(
        manifest,
        snapshot,
        source_lock_path,
    )

    label_rows = _read_csv(packet_dir / "labels.csv", REVIEW_FIELDS)
    observed_keys = [
        (row["case_id"].strip(), row["accepted_source_id"].strip())
        for row in label_rows
    ]
    if len(observed_keys) != len(set(observed_keys)):
        raise AnonymousOpenAlexReviewError(
            "labels contain duplicate case/source identities"
        )
    if set(observed_keys) != set(expected_candidates):
        missing = sorted(set(expected_candidates) - set(observed_keys))
        extra = sorted(set(observed_keys) - set(expected_candidates))
        raise AnonymousOpenAlexReviewError(
            f"label identities do not match packet; missing={missing}, extra={extra}"
        )

    completed: dict[tuple[str, str], dict[str, str]] = {}
    incomplete_row_ids: list[str] = []
    for row in label_rows:
        key = (row["case_id"].strip(), row["accepted_source_id"].strip())
        validated = _validated_label(row, expected_candidates[key])
        if validated is None:
            incomplete_row_ids.append(expected_candidates[key].row_id)
        else:
            completed[key] = validated

    declaration_rows = _read_csv(
        packet_dir / "reviewer_declaration.csv",
        DECLARATION_FIELDS,
    )
    if len(declaration_rows) != 1:
        raise AnonymousOpenAlexReviewError(
            "reviewer_declaration.csv must contain exactly one row"
        )
    declaration = _validated_declaration(declaration_rows[0])
    ordered_completed = [completed[key] for key in sorted(completed)]
    uninspectable_row_ids = [
        row["row_id"]
        for row in ordered_completed
        if row["relevant"] == "UNVERIFIABLE"
    ]
    method_issues: list[str] = []
    if declaration is not None:
        if declaration["reviewed_all"] != "YES":
            method_issues.append("reviewer_did_not_confirm_all_rows")
        if declaration["external_sources_checked"] != "ALL_ATTEMPTED":
            method_issues.append("not_all_external_sources_were_attempted")

    if incomplete_row_ids or declaration is None:
        protocol_status = "incomplete"
    elif declaration["generative_ai_use"] not in ELIGIBLE_AI_USE:
        protocol_status = "excluded_substantive_ai"
    elif uninspectable_row_ids or method_issues:
        protocol_status = "not_inspectable"
    else:
        protocol_status = "complete"

    metrics: dict[str, Any] | None = None
    threshold_results = {
        "accepted_cases": "not_evaluated",
        "wrong_source_rate": "not_evaluated",
        "novel_relevant_cases": "not_evaluated",
    }
    decision = "not_evaluated"
    if protocol_status == "complete":
        metrics, threshold_results, decision = _openalex_metrics(
            snapshot,
            ordered_completed,
        )

    return {
        "schema_version": 1,
        "mode": "anonymous_openalex_value_review_result",
        "production_connected": False,
        "report_workflow_connected": False,
        "source_lock_sha256": _file_sha256(source_lock_path),
        "source_file_sha256": snapshot.file_hashes,
        "packet_manifest_sha256": _file_sha256(
            packet_dir / "packet_manifest.json"
        ),
        "executed_revision": EXPECTED_EXECUTED_REVISION,
        "protocol_status": protocol_status,
        "baseline_context_exposed_to_reviewer": True,
        "decision": decision,
        "row_count": len(expected_candidates),
        "completed_row_count": len(completed),
        "incomplete_row_ids": sorted(incomplete_row_ids),
        "uninspectable_row_ids": sorted(uninspectable_row_ids),
        "method_issues": method_issues,
        "reviewer_declaration": declaration,
        "observed_label_counts": (
            {
                "relevant": dict(
                    sorted(Counter(row["relevant"] for row in ordered_completed).items())
                ),
                "novel": dict(
                    sorted(Counter(row["novel"] for row in ordered_completed).items())
                ),
            }
            if not incomplete_row_ids
            else None
        ),
        "provider_results": {
            "openalex": {
                "metrics": metrics,
                "threshold_results": threshold_results,
                "decision": decision,
            }
        },
        "provider_thresholds": manifest["provider_thresholds"],
        "planner_trigger_study_eligible": decision == "pass",
        "production_connection_authorized": False,
        "remaining_production_blockers": (
            ["planner_trigger_precision", "disabled_path_regression", "report_value"]
            if decision == "pass"
            else [
                "anonymous_openalex_source_value",
                "planner_trigger_precision",
                "disabled_path_regression",
                "report_value",
            ]
        ),
        "measurement_limit": MEASUREMENT_LIMIT,
    }


def write_summary(path: Path, result: dict[str, Any]) -> None:
    """Persist one interpretation without replacing returned human evidence."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise AnonymousOpenAlexReviewError(
            f"could not create summary parent {path.parent}: {exc}"
        ) from exc
    _write_text_new(
        path,
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _stdout_json(value: object) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    lock = commands.add_parser("lock", help="bind the exact anonymous live output")
    lock.add_argument("source", type=Path)
    lock.add_argument("output", type=Path)
    lock.add_argument("--study-owner-id", required=True)
    lock.add_argument("--confirm-authorized-output", action="store_true")
    lock.add_argument("--note")

    prepare = commands.add_parser("prepare", help="create a blank Schema v2 packet")
    prepare.add_argument("source", type=Path)
    prepare.add_argument("source_lock", type=Path)
    prepare.add_argument("packet", type=Path)

    summarize = commands.add_parser(
        "summarize",
        help="validate returned labels and write one result",
    )
    summarize.add_argument("source", type=Path)
    summarize.add_argument("source_lock", type=Path)
    summarize.add_argument("packet", type=Path)
    summarize.add_argument("output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "lock":
        result = create_source_lock(
            args.source,
            args.output,
            study_owner_id=args.study_owner_id,
            confirm_authorized_output=args.confirm_authorized_output,
            note=args.note,
        )
    elif args.command == "prepare":
        result = prepare_packet(args.source, args.source_lock, args.packet)
    else:
        result = summarize_packet(
            args.source,
            args.source_lock,
            args.packet,
        )
        write_summary(args.output, result)
    print(_stdout_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
