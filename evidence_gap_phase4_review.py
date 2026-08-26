"""Lock, prepare, and summarize the Phase 4 domain-source value review.

The live output directory is write-once execution evidence, not a mutable
review workspace. This module first binds it to a separate study-owner lock,
then creates a Schema v2 packet with visible baseline context, and finally
validates returned human labels without opening a socket or invoking a model.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evidence_gap_phase4_live import (
    EXPECTED_IMPLEMENTATION_SHA256,
    Phase4CaseExecution,
    Phase4ExecutionArtifact,
    Phase4ManifestArtifact,
    _AGGREGATE_SOURCE_FILES,
    _CANDIDATE_COLUMNS,
    _REVIEW_COLUMNS,
    _candidate_rows,
    _provider_accounting_issue,
)
from evidence_gap_phase4_audit import EXPECTED_FIXTURE_SHA256


SOURCE_FILES = (*_AGGREGATE_SOURCE_FILES, "artifact-index.json")
REVIEW_FIELDS = _REVIEW_COLUMNS
DECLARATION_FIELDS = (
    "reviewer_id",
    "reviewed_all",
    "generative_ai_use",
    "external_sources_checked",
    "elapsed_minutes",
    "expertise",
    "completed_date",
    "limitations",
)
VALID_LABEL_PAIRS = {
    ("YES", "YES"),
    ("YES", "NO"),
    ("NO", "N/A"),
    ("UNVERIFIABLE", "UNVERIFIABLE"),
}
ELIGIBLE_AI_USE = {"NONE", "LANGUAGE_ONLY"}
ALL_AI_USE = ELIGIBLE_AI_USE | {"SOME_SUBSTANTIVE", "MOST_OR_ALL"}
ACCEPTED_CASES_MIN = 3
WRONG_SOURCE_RATE_MAX = 0.05
NOVEL_RELEVANT_CASES_MIN = 3
MEASUREMENT_LIMIT = (
    "This injected-intent study measures candidate relevance and baseline-relative "
    "novelty, not planner precision, source truth, report value, or production utility."
)
_PROVIDERS = ("openalex", "lens")
_CASE_IDS = tuple(f"D{index:02d}" for index in range(1, 9))


class Phase4ReviewError(ValueError):
    """Raised when execution, lock, packet, or label provenance is not sound."""


class Phase4SourceLock(BaseModel):
    """Study-owner attestation over one finalized write-once live directory."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["phase4_source_artifact_lock"] = (
        "phase4_source_artifact_lock"
    )
    production_connected: Literal[False] = False
    authorized_output: Literal[True] = True
    fixture_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    source_file_sha256: dict[str, str]
    study_owner_id: str = Field(min_length=2, max_length=200)
    authorized_at: datetime
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _validate_frozen_identity(self) -> "Phase4SourceLock":
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("source lock fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("source lock implementation identities do not match")
        if set(self.source_file_sha256) != set(SOURCE_FILES):
            raise ValueError("source lock must identify every Phase 4 source file")
        if any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in self.source_file_sha256.values()
        ):
            raise ValueError("source lock hashes must be lowercase SHA-256 values")
        if self.authorized_at.tzinfo is None:
            raise ValueError("source lock timestamp must be timezone-aware")
        return self


@dataclass(frozen=True)
class ReviewCandidate:
    """One accepted source identity copied into the human packet."""

    case_id: str
    provider: str
    accepted_source_id: str
    title: str
    url: str

    @property
    def row_id(self) -> str:
        return f"{self.case_id}/{self.accepted_source_id}"

    @property
    def identity_sha256(self) -> str:
        payload = {
            "accepted_source_id": self.accepted_source_id,
            "case_id": self.case_id,
            "provider": self.provider,
            "title": self.title,
            "url": self.url,
        }
        return _sha256_bytes(
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )


@dataclass(frozen=True)
class SourceSnapshot:
    """Validated source state reused at lock, packet, and result boundaries."""

    file_hashes: dict[str, str]
    execution: Phase4ExecutionArtifact
    candidates: tuple[ReviewCandidate, ...]
    baseline_contexts: tuple[dict[str, Any], ...]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise Phase4ReviewError(f"could not read artifact {path}: {exc}") from exc


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase4ReviewError(f"could not parse JSON from {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise Phase4ReviewError(f"{path} must contain one JSON object")
    return payload


def _read_csv(path: Path, expected_fields: tuple[str, ...]) -> list[dict[str, str]]:
    try:
        # Spreadsheet software may add a UTF-8 BOM. Accepting it changes no
        # identity because the source lock still covers the original bytes.
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != expected_fields:
                raise Phase4ReviewError(
                    f"{path} columns must be exactly: {', '.join(expected_fields)}"
                )
            return list(reader)
    except (OSError, csv.Error) as exc:
        raise Phase4ReviewError(f"could not read CSV from {path}: {exc}") from exc


def _write_text_new(path: Path, value: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(value)
    except OSError as exc:
        raise Phase4ReviewError(f"could not create {path}: {exc}") from exc


def _write_csv_new(
    path: Path,
    fields: tuple[str, ...],
    rows: list[dict[str, str]],
) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
    except OSError as exc:
        raise Phase4ReviewError(f"could not create {path}: {exc}") from exc


def _baseline_contexts(
    manifest: Phase4ManifestArtifact,
) -> tuple[dict[str, Any], ...]:
    contexts: list[dict[str, Any]] = []
    for case in manifest.cases:
        gap_subject = "academic" if case.spec.provider == "openalex" else "patent"
        failure_reason = case.source_collection.failed_domains.get(gap_subject)
        if not failure_reason:
            raise Phase4ReviewError(
                f"{case.spec.case_id}: baseline failed-domain state is missing"
            )
        baseline_sources: list[dict[str, str]] = []
        for domain in ("academic", "patent", "market"):
            for source in getattr(case.source_collection, f"{domain}_sources"):
                projected = {
                    "domain": domain,
                    "source_id": source.source_id,
                    "title": source.title,
                    "url": str(source.url),
                    "evidence_summary": source.evidence_summary,
                }
                if not all(projected.values()):
                    raise Phase4ReviewError(
                        f"{case.spec.case_id}: baseline source projection is incomplete"
                    )
                baseline_sources.append(projected)
        contexts.append(
            {
                "case_id": case.spec.case_id,
                "provider": case.spec.provider,
                "tool": case.spec.tool,
                "topic": case.spec.topic,
                "query": case.spec.query,
                "collection_sha256": case.collection_sha256,
                "gap_subject": gap_subject,
                "gap_state": (
                    f"{gap_subject} retrieval failed: {failure_reason.strip()}"
                ),
                "baseline_sources": baseline_sources,
            }
        )
    return tuple(contexts)


def _validate_complete_execution(
    manifest: Phase4ManifestArtifact,
    execution: Phase4ExecutionArtifact,
) -> None:
    if execution.overall_state != "completed":
        raise Phase4ReviewError("only a completed eight-case run may be source-locked")
    if (
        execution.request_count != 8
        or execution.attempted_case_count != 8
        or execution.successful_case_count != 8
    ):
        raise Phase4ReviewError("source execution must contain eight successful requests")
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
        raise Phase4ReviewError("execution cases do not join the frozen manifest")
    summaries = {item.provider: item for item in execution.provider_summaries}
    for case in execution.cases:
        issue = _provider_accounting_issue(case)
        if issue is not None:
            raise Phase4ReviewError(
                f"{case.case_id}: completed provider accounting is invalid: {issue}"
            )
    for provider in _PROVIDERS:
        summary = summaries.get(provider)
        if summary is None or (
            summary.stopped_reason != "completed"
            or summary.request_count != 4
            or summary.attempted_case_count != 4
            or summary.successful_case_count != 4
        ):
            raise Phase4ReviewError(
                f"{provider} did not complete its four-case provider boundary"
            )
    if summaries["openalex"].cost_state != "known":
        raise Phase4ReviewError("OpenAlex reported cost is not inspectable")
    if summaries["lens"].cost_state != "uninspectable":
        raise Phase4ReviewError("Lens cost must remain explicitly uninspectable")


def _validate_case_journals(
    source_dir: Path,
    execution: Phase4ExecutionArtifact,
) -> None:
    journal_dir = source_dir / "case-executions"
    if not journal_dir.is_dir():
        raise Phase4ReviewError("case-executions journal directory is missing")
    observed_names = {path.name for path in journal_dir.glob("*.json")}
    expected_names = {f"{case_id}.json" for case_id in _CASE_IDS}
    if observed_names != expected_names:
        raise Phase4ReviewError(
            "case journals do not cover the frozen case set exactly"
        )
    execution_by_id = {case.case_id: case for case in execution.cases}
    for case_id in _CASE_IDS:
        journal = Phase4CaseExecution.model_validate(
            _read_json_object(journal_dir / f"{case_id}.json")
        )
        if journal != execution_by_id[case_id]:
            raise Phase4ReviewError(
                f"{case_id}: case journal does not match aggregate execution"
            )


def _candidate_from_row(row: Mapping[str, str]) -> ReviewCandidate:
    candidate = ReviewCandidate(
        case_id=row.get("case_id", "").strip(),
        provider=row.get("provider", "").strip(),
        accepted_source_id=row.get("accepted_source_id", "").strip(),
        title=row.get("title", "").strip(),
        url=row.get("url", "").strip(),
    )
    if not all(
        (
            candidate.case_id,
            candidate.provider,
            candidate.accepted_source_id,
            candidate.title,
            candidate.url,
        )
    ):
        raise Phase4ReviewError("accepted review identities must not be blank")
    expected_provider = "openalex" if candidate.case_id in _CASE_IDS[:4] else "lens"
    if candidate.case_id not in _CASE_IDS or candidate.provider != expected_provider:
        raise Phase4ReviewError(
            f"unexpected case/provider identity: {candidate.case_id}/{candidate.provider}"
        )
    return candidate


def _validate_artifact_index(
    source_dir: Path,
    file_hashes: Mapping[str, str],
) -> None:
    index = _read_json_object(source_dir / "artifact-index.json")
    expected = {
        "schema_version": 1,
        "mode": "phase4_live_artifact_index",
        "production_connected": False,
        "source_file_sha256": {
            name: file_hashes[name] for name in _AGGREGATE_SOURCE_FILES
        },
    }
    if index != expected:
        raise Phase4ReviewError("artifact index does not match aggregate source bytes")


def validate_finalized_source(
    source_dir: Path,
    *,
    expected_hashes: Mapping[str, str] | None = None,
) -> SourceSnapshot:
    """Validate every execution and file seam without mutating source evidence."""

    if not source_dir.is_dir():
        raise Phase4ReviewError(f"source directory does not exist: {source_dir}")
    file_hashes = {name: _file_sha256(source_dir / name) for name in SOURCE_FILES}
    if expected_hashes is not None:
        expected = dict(expected_hashes)
        if set(expected) != set(SOURCE_FILES):
            raise Phase4ReviewError("expected hashes must identify every source file")
        if file_hashes != expected:
            drift = {
                name: {"expected": expected[name], "observed": file_hashes[name]}
                for name in SOURCE_FILES
                if file_hashes[name] != expected[name]
            }
            raise Phase4ReviewError(f"source artifact identity drifted: {drift}")
    _validate_artifact_index(source_dir, file_hashes)

    manifest = Phase4ManifestArtifact.model_validate(
        _read_json_object(source_dir / "manifest.json")
    )
    execution = Phase4ExecutionArtifact.model_validate(
        _read_json_object(source_dir / "execution.json")
    )
    _validate_complete_execution(manifest, execution)
    _validate_case_journals(source_dir, execution)

    candidate_rows = _read_csv(source_dir / "candidates.csv", _CANDIDATE_COLUMNS)
    review_rows = _read_csv(source_dir / "review.csv", REVIEW_FIELDS)
    expected_candidates, expected_reviews = _candidate_rows(execution.cases)
    if candidate_rows != expected_candidates:
        raise Phase4ReviewError(
            "candidate CSV does not contain every executor disposition exactly once"
        )
    if review_rows != expected_reviews:
        raise Phase4ReviewError(
            "blank review CSV does not match quarantine-accepted candidates"
        )

    candidates: list[ReviewCandidate] = []
    seen: set[tuple[str, str]] = set()
    for row in review_rows:
        if any(row[field].strip() for field in ("relevant", "novel", "review_note")):
            raise Phase4ReviewError("source review.csv is no longer blank")
        candidate = _candidate_from_row(row)
        key = (candidate.case_id, candidate.accepted_source_id)
        if key in seen:
            raise Phase4ReviewError(
                f"source review rows contain duplicate identity {candidate.row_id}"
            )
        seen.add(key)
        candidates.append(candidate)
    return SourceSnapshot(
        file_hashes=file_hashes,
        execution=execution,
        candidates=tuple(candidates),
        baseline_contexts=_baseline_contexts(manifest),
    )


def create_source_lock(
    source_dir: Path,
    output_path: Path,
    *,
    study_owner_id: str,
    confirm_authorized_output: bool,
    note: str | None = None,
    authorized_at: datetime | None = None,
) -> Phase4SourceLock:
    """Freeze inspected source bytes separately from the live output directory."""

    if not confirm_authorized_output:
        raise Phase4ReviewError(
            "source locking requires explicit authorized-output confirmation"
        )
    if output_path.exists():
        raise Phase4ReviewError(f"refusing to overwrite source lock: {output_path}")
    snapshot = validate_finalized_source(source_dir)
    lock = Phase4SourceLock(
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
        raise Phase4ReviewError(
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


def _load_source_lock(path: Path) -> Phase4SourceLock:
    try:
        return Phase4SourceLock.model_validate(_read_json_object(path))
    except ValueError as exc:
        if isinstance(exc, Phase4ReviewError):
            raise
        raise Phase4ReviewError(f"source lock is invalid: {exc}") from exc


def _packet_readme(snapshot: SourceSnapshot) -> str:
    case_rows = "\n".join(
        (
            f"| {item['case_id']} | {item['provider']} | {item['topic']} | "
            f"{item['gap_subject']} | {item['query']} |"
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
    return f"""# Phase 4 domain-source human review packet

This packet contains quarantine-accepted candidates from one completed,
production-disconnected OpenAlex/Lens value study. Packet preparation and
summary make zero API or LLM calls.

Do not edit `packet_manifest.json`. Complete only `labels.csv` and
`reviewer_declaration.csv`. Rows may be reordered, but identity fields must not
change.

## Case targets

| Case | Provider | Topic | Declared gap | Frozen query |
|---|---|---|---|---|
{case_rows}

## Frozen baseline visible to the reviewer

| Case | Gap state | Baseline sources |
|---|---|---:|
{baseline_rows}

Full baseline source identities and evidence summaries are stored under
`baseline_contexts` in `packet_manifest.json`. Read them before assigning
`novel`. Novelty is relative only to that synthetic baseline, not to the wider
literature or patent landscape.

Attempt every candidate URL and inspect the paper abstract or patent record.
Judge direct relevance to the declared gap, not broad topic overlap.

## Labels

- `YES/YES`: directly relevant and materially absent from the frozen baseline.
- `YES/NO`: directly relevant but already represented in the baseline.
- `NO/N/A`: adjacent, generic, or otherwise not directly relevant.
- `UNVERIFIABLE/UNVERIFIABLE`: attempted but insufficient source content was
  inspectable.

Every row requires a source-grounded `review_note`. Complete
`reviewer_declaration.csv` after all rows. `NONE` or `LANGUAGE_ONLY`
generative-AI use is eligible; substantive generated judgments are retained but
excluded from the human-value headline. An unreachable source is
`UNVERIFIABLE`, never silently negative or positive.

Each provider must have accepted candidates in at least three of four cases, a
wrong-source rate no greater than 5%, and novel relevant candidates in at least
three cases. Both providers must pass. Even a pass does not authorize
production Tool Calling.
"""


def _packet_manifest(
    snapshot: SourceSnapshot,
    source_lock_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "mode": "phase4_domain_value_review_packet",
        "prepared_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "production_connected": False,
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
        "provider_thresholds": {
            provider: {
                "accepted_cases_min": ACCEPTED_CASES_MIN,
                "wrong_source_rate_max": WRONG_SOURCE_RATE_MAX,
                "novel_relevant_cases_min": NOVEL_RELEVANT_CASES_MIN,
                "case_count": 4,
            }
            for provider in _PROVIDERS
        },
        "measurement_limit": MEASUREMENT_LIMIT,
    }


def prepare_packet(
    source_dir: Path,
    source_lock_path: Path,
    packet_dir: Path,
) -> dict[str, Any]:
    """Create a separate Schema v2 packet from source-locked execution bytes."""

    if packet_dir.exists():
        raise Phase4ReviewError(f"refusing to overwrite packet: {packet_dir}")
    source_lock = _load_source_lock(source_lock_path)
    snapshot = validate_finalized_source(
        source_dir,
        expected_hashes=source_lock.source_file_sha256,
    )
    try:
        packet_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise Phase4ReviewError(f"could not create packet {packet_dir}: {exc}") from exc
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
    snapshot: SourceSnapshot,
    source_lock_path: Path,
) -> dict[tuple[str, str], ReviewCandidate]:
    if manifest.get("schema_version") != 2 or manifest.get("mode") != (
        "phase4_domain_value_review_packet"
    ):
        raise Phase4ReviewError("packet manifest has the wrong schema or mode")
    if manifest.get("production_connected") is not False:
        raise Phase4ReviewError("packet manifest must remain production-disconnected")
    if manifest.get("source_lock_sha256") != _file_sha256(source_lock_path):
        raise Phase4ReviewError("packet source-lock identity drifted")
    if manifest.get("source_file_sha256") != snapshot.file_hashes:
        raise Phase4ReviewError("packet source-file identities drifted")
    if manifest.get("baseline_contexts") != list(snapshot.baseline_contexts):
        raise Phase4ReviewError("packet baseline context drifted")
    expected_thresholds = {
        provider: {
            "accepted_cases_min": ACCEPTED_CASES_MIN,
            "wrong_source_rate_max": WRONG_SOURCE_RATE_MAX,
            "novel_relevant_cases_min": NOVEL_RELEVANT_CASES_MIN,
            "case_count": 4,
        }
        for provider in _PROVIDERS
    }
    if manifest.get("provider_thresholds") != expected_thresholds:
        raise Phase4ReviewError("packet provider thresholds drifted")
    if manifest.get("valid_label_pairs") != [
        list(pair) for pair in sorted(VALID_LABEL_PAIRS)
    ]:
        raise Phase4ReviewError("packet label contract drifted")

    if manifest.get("measurement_limit") != MEASUREMENT_LIMIT:
        raise Phase4ReviewError("packet measurement limit drifted")
    rows = manifest.get("rows")
    if not isinstance(rows, list) or manifest.get("row_count") != len(rows):
        raise Phase4ReviewError("packet row count is not inspectable")
    candidates: dict[tuple[str, str], ReviewCandidate] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise Phase4ReviewError("packet rows must be objects")
        candidate = _candidate_from_row(row)
        if row.get("identity_sha256") != candidate.identity_sha256:
            raise Phase4ReviewError(
                f"packet identity hash drifted for {candidate.row_id}"
            )
        key = (candidate.case_id, candidate.accepted_source_id)
        if key in candidates:
            raise Phase4ReviewError(
                f"packet contains duplicate identity {candidate.row_id}"
            )
        candidates[key] = candidate
    expected = {
        (candidate.case_id, candidate.accepted_source_id): candidate
        for candidate in snapshot.candidates
    }
    if candidates != expected:
        raise Phase4ReviewError("packet candidates do not match source-locked rows")
    return candidates


def _validated_label(
    row: dict[str, str],
    expected: ReviewCandidate,
) -> dict[str, str] | None:
    observed = _candidate_from_row(row)
    if observed != expected:
        raise Phase4ReviewError(f"label identity drifted for {expected.row_id}")
    values = [row[field].strip() for field in ("relevant", "novel", "review_note")]
    if not any(values):
        return None
    if not all(values):
        raise Phase4ReviewError(f"{expected.row_id} is partially completed")
    relevant, novel, note = values
    relevant = relevant.upper()
    novel = novel.upper()
    if (relevant, novel) not in VALID_LABEL_PAIRS:
        raise Phase4ReviewError(
            f"{expected.row_id} has invalid relevant/novel pair: {relevant}/{novel}"
        )
    if len("".join(note.split())) < 12:
        raise Phase4ReviewError(
            f"{expected.row_id} review_note is too short to ground the judgment"
        )
    return {
        "case_id": expected.case_id,
        "provider": expected.provider,
        "accepted_source_id": expected.accepted_source_id,
        "row_id": expected.row_id,
        "relevant": relevant,
        "novel": novel,
        "review_note": note,
    }


def _validated_declaration(row: dict[str, str]) -> dict[str, Any] | None:
    required = (
        "reviewer_id",
        "reviewed_all",
        "generative_ai_use",
        "external_sources_checked",
        "elapsed_minutes",
        "completed_date",
    )
    if not any(value.strip() for value in row.values()):
        return None
    missing = [field for field in required if not row[field].strip()]
    if missing:
        raise Phase4ReviewError(
            f"reviewer declaration is partially completed; missing={missing}"
        )
    reviewed_all = row["reviewed_all"].strip().upper()
    if reviewed_all not in {"YES", "NO"}:
        raise Phase4ReviewError("reviewed_all must be YES or NO")
    ai_use = row["generative_ai_use"].strip().upper()
    if ai_use not in ALL_AI_USE:
        raise Phase4ReviewError(f"invalid generative_ai_use: {ai_use}")
    external = row["external_sources_checked"].strip().upper()
    if external not in {"ALL_ATTEMPTED", "SOME", "NONE"}:
        raise Phase4ReviewError(
            "external_sources_checked must be ALL_ATTEMPTED, SOME, or NONE"
        )
    try:
        elapsed = int(row["elapsed_minutes"].strip())
    except ValueError as exc:
        raise Phase4ReviewError("elapsed_minutes must be an integer") from exc
    if elapsed <= 0:
        raise Phase4ReviewError("elapsed_minutes must be positive")
    try:
        completed = date.fromisoformat(row["completed_date"].strip())
    except ValueError as exc:
        raise Phase4ReviewError("completed_date must use YYYY-MM-DD") from exc
    return {
        "reviewer_id": row["reviewer_id"].strip(),
        "reviewed_all": reviewed_all,
        "generative_ai_use": ai_use,
        "external_sources_checked": external,
        "elapsed_minutes": elapsed,
        "expertise": row["expertise"].strip() or None,
        "completed_date": completed.isoformat(),
        "limitations": row["limitations"].strip() or None,
    }


def _provider_metrics(
    provider: str,
    snapshot: SourceSnapshot,
    completed: list[dict[str, str]],
) -> tuple[dict[str, Any], dict[str, str], str]:
    provider_candidates = [
        candidate
        for candidate in snapshot.candidates
        if candidate.provider == provider
    ]
    provider_rows = [row for row in completed if row["provider"] == provider]
    accepted_case_ids = sorted({item.case_id for item in provider_candidates})
    wrong_source_count = sum(row["relevant"] == "NO" for row in provider_rows)
    denominator = len(provider_rows)
    wrong_source_rate = wrong_source_count / denominator if denominator else None
    novel_case_ids = sorted(
        {
            row["case_id"]
            for row in provider_rows
            if row["relevant"] == "YES" and row["novel"] == "YES"
        }
    )
    accepted_pass = len(accepted_case_ids) >= ACCEPTED_CASES_MIN
    wrong_source_pass = (
        wrong_source_rate is not None
        and wrong_source_rate <= WRONG_SOURCE_RATE_MAX
    )
    novel_pass = len(novel_case_ids) >= NOVEL_RELEVANT_CASES_MIN
    metrics = {
        "accepted_candidate_count": len(provider_candidates),
        "accepted_case_ids": accepted_case_ids,
        "accepted_case_count": len(accepted_case_ids),
        "wrong_source_count": wrong_source_count,
        "wrong_source_rate": wrong_source_rate,
        "novel_relevant_case_ids": novel_case_ids,
        "novel_relevant_case_count": len(novel_case_ids),
    }
    thresholds = {
        "accepted_cases": "pass" if accepted_pass else "fail",
        "wrong_source_rate": "pass" if wrong_source_pass else "fail",
        "novel_relevant_cases": "pass" if novel_pass else "fail",
    }
    decision = "pass" if all(value == "pass" for value in thresholds.values()) else "fail"
    return metrics, thresholds, decision


def summarize_packet(
    source_dir: Path,
    source_lock_path: Path,
    packet_dir: Path,
) -> dict[str, Any]:
    """Validate source, packet, declarations, and provider gates at one seam."""

    if not packet_dir.is_dir():
        raise Phase4ReviewError(f"packet directory does not exist: {packet_dir}")
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
        raise Phase4ReviewError("labels contain duplicate case/source identities")
    if set(observed_keys) != set(expected_candidates):
        missing = sorted(set(expected_candidates) - set(observed_keys))
        extra = sorted(set(observed_keys) - set(expected_candidates))
        raise Phase4ReviewError(
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
        raise Phase4ReviewError("reviewer_declaration.csv must contain exactly one row")
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

    provider_results: dict[str, Any] = {}
    decision = "not_evaluated"
    if protocol_status == "complete":
        for provider in _PROVIDERS:
            metrics, thresholds, provider_decision = _provider_metrics(
                provider,
                snapshot,
                ordered_completed,
            )
            provider_results[provider] = {
                "metrics": metrics,
                "threshold_results": thresholds,
                "decision": provider_decision,
            }
        decision = (
            "pass"
            if all(
                result["decision"] == "pass"
                for result in provider_results.values()
            )
            else "fail"
        )
    else:
        provider_results = {
            provider: {
                "metrics": None,
                "threshold_results": {
                    "accepted_cases": "not_evaluated",
                    "wrong_source_rate": "not_evaluated",
                    "novel_relevant_cases": "not_evaluated",
                },
                "decision": "not_evaluated",
            }
            for provider in _PROVIDERS
        }

    return {
        "schema_version": 1,
        "mode": "phase4_domain_value_review_result",
        "production_connected": False,
        "source_lock_sha256": _file_sha256(source_lock_path),
        "source_file_sha256": snapshot.file_hashes,
        "packet_manifest_sha256": _file_sha256(
            packet_dir / "packet_manifest.json"
        ),
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
        "provider_results": provider_results,
        "provider_thresholds": manifest["provider_thresholds"],
        "planner_trigger_study_eligible": decision == "pass",
        "production_connection_authorized": False,
        "remaining_production_blockers": (
            ["planner_trigger_precision", "disabled_path_regression", "report_value"]
            if decision == "pass"
            else [
                "domain_source_value",
                "planner_trigger_precision",
                "disabled_path_regression",
                "report_value",
            ]
        ),
        "measurement_limit": MEASUREMENT_LIMIT,
    }


def write_summary(path: Path, result: dict[str, Any]) -> None:
    """Persist one interpretation without replacing prior human evidence."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise Phase4ReviewError(
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

    lock = commands.add_parser("lock", help="bind one inspected live directory")
    lock.add_argument("source", type=Path)
    lock.add_argument("output", type=Path)
    lock.add_argument("--study-owner-id", required=True)
    lock.add_argument("--confirm-authorized-output", action="store_true")
    lock.add_argument("--note")

    prepare = commands.add_parser("prepare", help="create a blank Schema v2 packet")
    prepare.add_argument("source", type=Path)
    prepare.add_argument("source_lock", type=Path)
    prepare.add_argument("packet", type=Path)

    summarize = commands.add_parser("summarize", help="validate labels and write one result")
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
