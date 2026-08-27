"""Lock and review the frozen OpenAlex claim-scope v3 execution.

The live runner intentionally stops at a mechanical candidate gate.  This
module binds the exact V01-V08 bytes to a separate owner attestation, exposes
the frozen baseline and candidate context in a Schema v2 packet, and validates
returned human labels without opening a socket or invoking a model.  It never
authorizes production Tool Calling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from evidence_gap_phase4_review import (
    DECLARATION_FIELDS,
    ELIGIBLE_AI_USE,
    VALID_LABEL_PAIRS,
    Phase4ReviewError as ClaimScopeReviewError,
    _file_sha256,
    _read_csv,
    _read_json_object,
    _validated_declaration,
    _write_csv_new,
    _write_text_new,
)
from openalex_claim_scope_live import (
    EXPECTED_IMPLEMENTATION_SHA256,
    ClaimScopeCaseExecution,
    ClaimScopeExecutionArtifact,
    ClaimScopeManifestArtifact,
    _AGGREGATE_SOURCE_FILES,
    _CANDIDATE_COLUMNS,
    _REVIEW_COLUMNS,
    _candidate_rows,
)
from openalex_claim_scope_unseen import EXPECTED_FIXTURE_SHA256


EXPECTED_EXECUTED_REVISION = "ad70d72120e86dad5d04f99cce319a61a623508e"
EXPECTED_SOURCE_FILE_SHA256 = {
    "manifest.json": (
        "a28e6d2d84d539b256917ee89d0bb58e043b34592bc2e97899a4bb44a8630ede"
    ),
    "execution.json": (
        "aea0ded720262bb013df9c244d673acd3398f7efb8738d61d5f89ba3774eb60a"
    ),
    "candidates.csv": (
        "391fafd74a1b1ed6b3eb5eb20abd88e32dfea5692d5f9ab251880d38d79b912b"
    ),
    "review.csv": (
        "117b6256d3122bd1308f073648abf7e07528c22805d479801ae2bb2206bc2bd6"
    ),
    "artifact-index.json": (
        "ac4387fecd94394b20fed5e861af717204053182ff0897e5d9e32ab2b4457c4d"
    ),
    "case-executions/V01.json": (
        "002e0714aaad07c2c340d3770223258f73647334c186125fa379e93de5783fbf"
    ),
    "case-executions/V02.json": (
        "c89241f3ecb5677f4f26633be624e12ef0a8690be994001e1f608e31c186f296"
    ),
    "case-executions/V03.json": (
        "8ffd57429135f14a07a71d16fe813c5a5788d66674d60f1a2042cf92e0fd318c"
    ),
    "case-executions/V04.json": (
        "211091ae9ce2fc00cd080c3fc758b884aa10201701c8a53981ba731ba306ecff"
    ),
    "case-executions/V05.json": (
        "aa487770203a4dc3eec14feabd8358c73e822682e63e2ecd8e7e8f76e9d633ea"
    ),
    "case-executions/V06.json": (
        "3f4ae61ecc4c1e91e91ee97704e522a83263c698277822c770ab820914f2adb7"
    ),
    "case-executions/V07.json": (
        "1c7ff909b5a82b9b57f63eeadf01297d5880be4ecf5d77e7db8088f2be5e1e68"
    ),
    "case-executions/V08.json": (
        "9239a761e2b1e872e50b79d8d134aba4d3ae02ce09276e1ad0d751950e45142d"
    ),
}
CASE_IDS = tuple(f"V{index:02d}" for index in range(1, 9))
SOURCE_FILES = (
    *_AGGREGATE_SOURCE_FILES,
    "artifact-index.json",
    *(f"case-executions/{case_id}.json" for case_id in CASE_IDS),
)
REVIEW_FIELDS = _REVIEW_COLUMNS
EXPECTED_ACCEPTED_PER_CASE = {
    "V01": 2,
    "V02": 1,
    "V03": 4,
    "V04": 0,
    "V05": 1,
    "V06": 2,
    "V07": 1,
    "V08": 2,
}
EXPECTED_REVIEW_ROW_COUNT = 13
ACCEPTED_CASES_MIN = 6
WRONG_SOURCE_RATE_MAX = 0.05
NOVEL_RELEVANT_CASES_MIN = 6
MEASUREMENT_LIMIT = (
    "This source-locked study measures candidate relevance and baseline-relative "
    "novelty for one frozen eight-case OpenAlex execution. It does not measure "
    "planner-trigger precision, provider-wide source truth, report improvement, "
    "production reliability, adoption, or commercial value."
)


class ClaimScopeSourceLock(BaseModel):
    """Study-owner attestation over the exact V01-V08 execution bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_claim_scope_v3_source_artifact_lock"] = (
        "openalex_claim_scope_v3_source_artifact_lock"
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
    def _validate_frozen_identity(self) -> "ClaimScopeSourceLock":
        if self.executed_revision != EXPECTED_EXECUTED_REVISION:
            raise ValueError("source lock executed revision does not match")
        if self.fixture_sha256 != EXPECTED_FIXTURE_SHA256:
            raise ValueError("source lock fixture identity does not match")
        if self.implementation_sha256 != EXPECTED_IMPLEMENTATION_SHA256:
            raise ValueError("source lock implementation identities do not match")
        if self.source_file_sha256 != EXPECTED_SOURCE_FILE_SHA256:
            raise ValueError("source lock does not identify the frozen v3 run")
        if self.authorized_at.tzinfo is None:
            raise ValueError("source lock timestamp must be timezone-aware")
        return self


@dataclass(frozen=True)
class ClaimScopeReviewCandidate:
    """One accepted v3 source identity copied into the human packet."""

    case_id: str
    provider: str
    provider_result_index: int
    candidate_sha256: str
    title: str
    url: str

    @property
    def row_id(self) -> str:
        return (
            f"{self.case_id}/{self.provider_result_index}/"
            f"{self.candidate_sha256[:12]}"
        )

    @property
    def identity_sha256(self) -> str:
        payload = {
            "candidate_sha256": self.candidate_sha256,
            "case_id": self.case_id,
            "provider": self.provider,
            "provider_result_index": self.provider_result_index,
            "title": self.title,
            "url": self.url,
        }
        rendered = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(rendered).hexdigest()


@dataclass(frozen=True)
class ClaimScopeSourceSnapshot:
    """Validated source reused unchanged at lock, packet, and result seams."""

    file_hashes: dict[str, str]
    manifest: ClaimScopeManifestArtifact
    execution: ClaimScopeExecutionArtifact
    candidates: tuple[ClaimScopeReviewCandidate, ...]
    baseline_contexts: tuple[dict[str, Any], ...]
    candidate_contexts: tuple[dict[str, Any], ...]


def _candidate_from_row(row: Mapping[str, str]) -> ClaimScopeReviewCandidate:
    try:
        provider_result_index = int(row.get("provider_result_index", "").strip())
    except ValueError as exc:
        raise ClaimScopeReviewError(
            "provider_result_index must be an integer"
        ) from exc
    candidate = ClaimScopeReviewCandidate(
        case_id=row.get("case_id", "").strip(),
        provider=row.get("provider", "").strip(),
        provider_result_index=provider_result_index,
        candidate_sha256=row.get("candidate_sha256", "").strip(),
        title=row.get("title", "").strip(),
        url=row.get("url", "").strip(),
    )
    if candidate.case_id not in CASE_IDS or candidate.provider != "openalex":
        raise ClaimScopeReviewError(
            f"unexpected case/provider identity: {candidate.case_id}/{candidate.provider}"
        )
    if not 0 <= candidate.provider_result_index <= 7:
        raise ClaimScopeReviewError(
            f"{candidate.case_id}: provider_result_index is outside the frozen page"
        )
    if (
        len(candidate.candidate_sha256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in candidate.candidate_sha256
        )
    ):
        raise ClaimScopeReviewError(
            f"{candidate.case_id}: candidate SHA-256 is invalid"
        )
    if not candidate.title or not candidate.url.startswith("https://openalex.org/W"):
        raise ClaimScopeReviewError(
            f"{candidate.case_id}: accepted source identity is incomplete"
        )
    return candidate


def _validate_artifact_index(
    source_dir: Path,
    file_hashes: Mapping[str, str],
) -> None:
    index = _read_json_object(source_dir / "artifact-index.json")
    expected = {
        "schema_version": 1,
        "mode": "openalex_claim_scope_v3_artifact_index",
        "production_connected": False,
        "report_workflow_connected": False,
        "source_file_sha256": {
            name: file_hashes[name] for name in _AGGREGATE_SOURCE_FILES
        },
    }
    if index != expected:
        raise ClaimScopeReviewError(
            "artifact index does not match aggregate claim-scope bytes"
        )


def _validate_complete_execution(
    manifest: ClaimScopeManifestArtifact,
    execution: ClaimScopeExecutionArtifact,
) -> None:
    if execution.overall_state != "completed":
        raise ClaimScopeReviewError(
            "only the completed eight-case v3 run may be source-locked"
        )
    if (
        execution.request_count != 8
        or execution.attempted_case_count != 8
        or execution.successful_case_count != 8
    ):
        raise ClaimScopeReviewError(
            "claim-scope source execution must contain eight successful requests"
        )
    if (
        execution.provider_summary.stopped_reason != "completed"
        or execution.provider_summary.cost_state != "known"
    ):
        raise ClaimScopeReviewError(
            "claim-scope provider completion or cost is not inspectable"
        )
    if execution.review_packet_eligibility != "eligible_for_source_lock":
        raise ClaimScopeReviewError(
            "the frozen mechanical gate did not authorize source locking"
        )
    if execution.claim_scope_accepted_case_count < ACCEPTED_CASES_MIN:
        raise ClaimScopeReviewError(
            "accepted-case count is below the frozen mechanical gate"
        )
    if (
        manifest.fixture_sha256 != execution.fixture_sha256
        or manifest.implementation_sha256 != execution.implementation_sha256
        or manifest.soft_stop_usd != execution.soft_stop_usd
        or manifest.source_value_gates != execution.source_value_gates
    ):
        raise ClaimScopeReviewError(
            "execution identity does not join the persisted manifest"
        )

    expected_cases = {
        case.spec.case_id: (
            case.collection_sha256,
            case.plan_sha256,
            case.profile_sha256,
            case.validated_plan.calls[0].idempotency_key,
        )
        for case in manifest.cases
    }
    observed_cases = {
        case.case_id: (
            case.collection_sha256,
            case.plan_sha256,
            case.profile_sha256,
            case.idempotency_key,
        )
        for case in execution.cases
    }
    if observed_cases != expected_cases:
        raise ClaimScopeReviewError(
            "case executions do not join the frozen manifest"
        )

    costs: list[float] = []
    for case in execution.cases:
        if case.state != "completed" or case.response is None:
            raise ClaimScopeReviewError(
                f"{case.case_id}: case is not a completed provider observation"
            )
        usage = case.response.provider_usage
        if (
            case.response.outbound_request_count != 1
            or usage.cost_basis != "reported_usd"
            or usage.reported_cost_usd is None
            or case.search_cost_usd is None
            or usage.reported_cost_usd != case.search_cost_usd
        ):
            raise ClaimScopeReviewError(
                f"{case.case_id}: request or provider accounting is invalid"
            )
        observed_rows = len(case.response.candidates) + len(
            case.response.provider_rejections
        )
        if usage.result_count != observed_rows:
            raise ClaimScopeReviewError(
                f"{case.case_id}: provider row accounting is incomplete"
            )
        costs.append(case.search_cost_usd)
    reported = execution.provider_summary.reported_cost_usd
    if reported is None or abs(reported - sum(costs)) > 1e-12:
        raise ClaimScopeReviewError(
            "provider summary cost does not equal the eight case journals"
        )

    accepted_per_case = {
        case.case_id: sum(
            item.decision.action == "ACCEPT" for item in case.evaluations
        )
        for case in execution.cases
    }
    if accepted_per_case != EXPECTED_ACCEPTED_PER_CASE:
        raise ClaimScopeReviewError(
            "accepted candidate distribution does not match the frozen execution"
        )
    if sum(accepted_per_case.values()) != EXPECTED_REVIEW_ROW_COUNT:
        raise ClaimScopeReviewError(
            "accepted candidate denominator does not match the frozen review"
        )


def _validate_case_journals(
    source_dir: Path,
    execution: ClaimScopeExecutionArtifact,
) -> None:
    journal_dir = source_dir / "case-executions"
    if not journal_dir.is_dir():
        raise ClaimScopeReviewError("case-executions journal directory is missing")
    observed_names = {path.name for path in journal_dir.glob("*.json")}
    expected_names = {f"{case_id}.json" for case_id in CASE_IDS}
    if observed_names != expected_names:
        raise ClaimScopeReviewError(
            "case journals do not cover V01-V08 exactly"
        )
    execution_by_id = {case.case_id: case for case in execution.cases}
    for case_id in CASE_IDS:
        journal = ClaimScopeCaseExecution.model_validate(
            _read_json_object(journal_dir / f"{case_id}.json")
        )
        if journal != execution_by_id[case_id]:
            raise ClaimScopeReviewError(
                f"{case_id}: case journal does not match aggregate execution"
            )


def _baseline_contexts(
    manifest: ClaimScopeManifestArtifact,
) -> tuple[dict[str, Any], ...]:
    contexts: list[dict[str, Any]] = []
    for case in manifest.cases:
        failure_reason = case.source_collection.failed_domains.get("academic")
        if not failure_reason:
            raise ClaimScopeReviewError(
                f"{case.spec.case_id}: baseline academic gap state is missing"
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
                    raise ClaimScopeReviewError(
                        f"{case.spec.case_id}: baseline source projection is incomplete"
                    )
                baseline_sources.append(projected)
        contexts.append(
            {
                "case_id": case.spec.case_id,
                "provider": "openalex",
                "tool": "academic_search",
                "topic": case.spec.topic,
                "query": case.spec.query,
                "collection_sha256": case.collection_sha256,
                "profile_sha256": case.profile_sha256,
                "gap_subject": "academic",
                "gap_state": (
                    f"academic retrieval failed: {failure_reason.strip()}"
                ),
                "claim_scope_profile": case.spec.profile.model_dump(mode="json"),
                "baseline_sources": baseline_sources,
            }
        )
    return tuple(contexts)


def _candidate_contexts(
    execution: ClaimScopeExecutionArtifact,
) -> tuple[dict[str, Any], ...]:
    contexts: list[dict[str, Any]] = []
    for case in execution.cases:
        for item in case.evaluations:
            if item.decision.action != "ACCEPT":
                continue
            evidence = item.candidate.evidence
            contexts.append(
                {
                    "case_id": case.case_id,
                    "provider": "openalex",
                    "provider_result_index": item.provider_result_index,
                    "candidate_sha256": item.decision.candidate_sha256,
                    "title": evidence.title,
                    "url": str(evidence.url),
                    "publisher": evidence.publisher,
                    "published_date": (
                        evidence.published_date.isoformat()
                        if evidence.published_date is not None
                        else None
                    ),
                    "doi": evidence.doi,
                    "evidence_summary": evidence.evidence_summary,
                    "summary_source": evidence.summary_source,
                    "aboutness": [
                        signal.model_dump(mode="json")
                        for signal in item.candidate.aboutness
                    ],
                    "claim_scope_decision": item.decision.model_dump(mode="json"),
                }
            )
    return tuple(contexts)


def validate_finalized_source(
    source_dir: Path,
    *,
    expected_hashes: Mapping[str, str] | None = None,
) -> ClaimScopeSourceSnapshot:
    """Validate every execution and file seam without mutating source evidence."""

    if not source_dir.is_dir():
        raise ClaimScopeReviewError(f"source directory does not exist: {source_dir}")
    file_hashes = {name: _file_sha256(source_dir / name) for name in SOURCE_FILES}
    if expected_hashes is not None:
        expected = dict(expected_hashes)
        if set(expected) != set(SOURCE_FILES):
            raise ClaimScopeReviewError(
                "expected hashes must identify every v3 source file"
            )
        if file_hashes != expected:
            drift = {
                name: {"expected": expected[name], "observed": file_hashes[name]}
                for name in SOURCE_FILES
                if file_hashes[name] != expected[name]
            }
            raise ClaimScopeReviewError(
                f"source artifact identity drifted after locking: {drift}"
            )
    _validate_artifact_index(source_dir, file_hashes)

    manifest = ClaimScopeManifestArtifact.model_validate(
        _read_json_object(source_dir / "manifest.json")
    )
    execution = ClaimScopeExecutionArtifact.model_validate(
        _read_json_object(source_dir / "execution.json")
    )
    _validate_complete_execution(manifest, execution)
    _validate_case_journals(source_dir, execution)

    candidate_rows = _read_csv(source_dir / "candidates.csv", _CANDIDATE_COLUMNS)
    review_rows = _read_csv(source_dir / "review.csv", REVIEW_FIELDS)
    expected_candidates, expected_reviews = _candidate_rows(execution.cases)
    if candidate_rows != expected_candidates:
        raise ClaimScopeReviewError(
            "candidate CSV does not contain every v3 disposition exactly once"
        )
    if review_rows != expected_reviews:
        raise ClaimScopeReviewError(
            "blank review CSV does not match every v3 ACCEPT exactly"
        )

    candidates: list[ClaimScopeReviewCandidate] = []
    seen: set[tuple[str, int, str]] = set()
    for row in review_rows:
        if any(row[field].strip() for field in ("relevant", "novel", "review_note")):
            raise ClaimScopeReviewError("source review.csv is no longer blank")
        candidate = _candidate_from_row(row)
        key = (
            candidate.case_id,
            candidate.provider_result_index,
            candidate.candidate_sha256,
        )
        if key in seen:
            raise ClaimScopeReviewError(
                f"source review rows duplicate {candidate.row_id}"
            )
        seen.add(key)
        candidates.append(candidate)
    if len(candidates) != EXPECTED_REVIEW_ROW_COUNT:
        raise ClaimScopeReviewError(
            "source review denominator does not match the frozen execution"
        )

    contexts = _candidate_contexts(execution)
    context_keys = {
        (
            item["case_id"],
            item["provider_result_index"],
            item["candidate_sha256"],
        )
        for item in contexts
    }
    candidate_keys = {
        (item.case_id, item.provider_result_index, item.candidate_sha256)
        for item in candidates
    }
    if context_keys != candidate_keys:
        raise ClaimScopeReviewError(
            "review identities do not join accepted execution contexts"
        )
    return ClaimScopeSourceSnapshot(
        file_hashes=file_hashes,
        manifest=manifest,
        execution=execution,
        candidates=tuple(candidates),
        baseline_contexts=_baseline_contexts(manifest),
        candidate_contexts=contexts,
    )


def create_source_lock(
    source_dir: Path,
    output_path: Path,
    *,
    study_owner_id: str,
    confirm_authorized_output: bool,
    note: str | None = None,
    authorized_at: datetime | None = None,
) -> ClaimScopeSourceLock:
    """Freeze inspected source bytes separately from the live output directory."""

    if not confirm_authorized_output:
        raise ClaimScopeReviewError(
            "source locking requires explicit authorized-output confirmation"
        )
    if output_path.exists():
        raise ClaimScopeReviewError(
            f"refusing to overwrite source lock: {output_path}"
        )
    snapshot = validate_finalized_source(source_dir)
    lock = ClaimScopeSourceLock(
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
        raise ClaimScopeReviewError(
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


def _load_source_lock(path: Path) -> ClaimScopeSourceLock:
    try:
        return ClaimScopeSourceLock.model_validate(_read_json_object(path))
    except ValueError as exc:
        if isinstance(exc, ClaimScopeReviewError):
            raise
        raise ClaimScopeReviewError(f"source lock is invalid: {exc}") from exc


def _packet_rows(snapshot: ClaimScopeSourceSnapshot) -> list[dict[str, Any]]:
    context_by_key = {
        (
            item["case_id"],
            item["provider_result_index"],
            item["candidate_sha256"],
        ): item
        for item in snapshot.candidate_contexts
    }
    rows: list[dict[str, Any]] = []
    for candidate in snapshot.candidates:
        key = (
            candidate.case_id,
            candidate.provider_result_index,
            candidate.candidate_sha256,
        )
        context = context_by_key[key]
        rows.append(
            {
                "case_id": candidate.case_id,
                "provider": candidate.provider,
                "provider_result_index": candidate.provider_result_index,
                "candidate_sha256": candidate.candidate_sha256,
                "title": candidate.title,
                "url": candidate.url,
                "identity_sha256": candidate.identity_sha256,
                "source_context": {
                    name: value
                    for name, value in context.items()
                    if name
                    not in {
                        "case_id",
                        "provider",
                        "provider_result_index",
                        "candidate_sha256",
                        "title",
                        "url",
                    }
                },
            }
        )
    return rows


def _provider_thresholds() -> dict[str, dict[str, int | float]]:
    return {
        "openalex": {
            "accepted_cases_min": ACCEPTED_CASES_MIN,
            "wrong_source_rate_max": WRONG_SOURCE_RATE_MAX,
            "novel_relevant_cases_min": NOVEL_RELEVANT_CASES_MIN,
            "case_count": 8,
        }
    }


def _packet_readme(snapshot: ClaimScopeSourceSnapshot) -> str:
    case_rows = "\n".join(
        (
            f"| {item['case_id']} | {item['topic']} | {item['query']} | "
            f"{len(item['baseline_sources'])} |"
        )
        for item in snapshot.baseline_contexts
    )
    return f"""# OpenAlex claim-scope v3 human source-value review

This packet contains the {len(snapshot.candidates)} candidates accepted by one
exact, completed, production-disconnected V01-V08 execution. Preparing or
summarizing it makes zero API or LLM calls.

Do not edit `packet_manifest.json`. Complete only `labels.csv` and
`reviewer_declaration.csv`. Rows may be reordered, but every identity field
must remain unchanged. Do not send the separate source-lock file to the
reviewer.

## Case targets and frozen baselines

| Case | Topic | Declared academic-gap query | Baseline sources |
|---|---|---|---:|
{case_rows}

Read each case's full `baseline_contexts` and `claim_scope_profile` in
`packet_manifest.json` before assigning novelty. Each candidate row also
contains the OpenAlex abstract, metadata, provider aboutness, and the exact
claim-scope decision provenance. These are frozen context, not proof that the
source is correct.

Attempt every candidate URL and inspect the OpenAlex work page plus accessible
abstract or linked source content. Judge direct relevance to the declared gap,
not broad topic overlap. Novelty means materially absent from the visible
frozen baseline, not absent from the wider literature.

## Labels

- `YES/YES`: directly relevant and materially absent from the frozen baseline.
- `YES/NO`: directly relevant but already represented in the baseline.
- `NO/N/A`: adjacent, generic, or otherwise not directly relevant.
- `UNVERIFIABLE/UNVERIFIABLE`: attempted, but insufficient source content was
  inspectable.

Every row requires a source-grounded `review_note`. Complete
`reviewer_declaration.csv` after all rows. `NONE` or `LANGUAGE_ONLY`
generative-AI use is eligible; substantive generated judgments are retained but
excluded from the human-value result. An unreachable source is
`UNVERIFIABLE`, never silently converted to a positive or negative judgment.

The frozen gates require accepted candidates in at least six of eight cases, a
directly irrelevant rate no greater than 5%, novel relevant candidates in at
least six cases, every source attempted, and no substantive generative-AI
judgment. Even a pass does not authorize production Tool Calling.
"""


def _packet_manifest(
    snapshot: ClaimScopeSourceSnapshot,
    source_lock_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "mode": "openalex_claim_scope_v3_value_review_packet",
        "prepared_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "production_connected": False,
        "report_workflow_connected": False,
        "executed_revision": EXPECTED_EXECUTED_REVISION,
        "source_lock_sha256": _file_sha256(source_lock_path),
        "source_file_sha256": snapshot.file_hashes,
        "row_count": len(snapshot.candidates),
        "mechanical_result": {
            "accepted_candidate_count": (
                snapshot.execution.claim_scope_accepted_candidate_count
            ),
            "accepted_case_count": snapshot.execution.claim_scope_accepted_case_count,
            "review_packet_eligibility": (
                snapshot.execution.review_packet_eligibility
            ),
        },
        "baseline_contexts": list(snapshot.baseline_contexts),
        "rows": _packet_rows(snapshot),
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
        raise ClaimScopeReviewError(f"refusing to overwrite packet: {packet_dir}")
    source_lock = _load_source_lock(source_lock_path)
    snapshot = validate_finalized_source(
        source_dir,
        expected_hashes=source_lock.source_file_sha256,
    )
    try:
        packet_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise ClaimScopeReviewError(
            f"could not create packet {packet_dir}: {exc}"
        ) from exc
    manifest = _packet_manifest(snapshot, source_lock_path)
    label_rows = [
        {
            "case_id": candidate.case_id,
            "provider": candidate.provider,
            "provider_result_index": str(candidate.provider_result_index),
            "candidate_sha256": candidate.candidate_sha256,
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
    snapshot: ClaimScopeSourceSnapshot,
    source_lock_path: Path,
) -> dict[tuple[str, int, str], ClaimScopeReviewCandidate]:
    if manifest.get("schema_version") != 2 or manifest.get("mode") != (
        "openalex_claim_scope_v3_value_review_packet"
    ):
        raise ClaimScopeReviewError("packet manifest has the wrong schema or mode")
    if (
        manifest.get("production_connected") is not False
        or manifest.get("report_workflow_connected") is not False
    ):
        raise ClaimScopeReviewError(
            "packet manifest must remain production-disconnected"
        )
    if manifest.get("executed_revision") != EXPECTED_EXECUTED_REVISION:
        raise ClaimScopeReviewError("packet executed revision drifted")
    if manifest.get("source_lock_sha256") != _file_sha256(source_lock_path):
        raise ClaimScopeReviewError("packet source-lock identity drifted")
    if manifest.get("source_file_sha256") != snapshot.file_hashes:
        raise ClaimScopeReviewError("packet source-file identities drifted")
    if manifest.get("baseline_contexts") != list(snapshot.baseline_contexts):
        raise ClaimScopeReviewError("packet baseline context drifted")
    if manifest.get("provider_thresholds") != _provider_thresholds():
        raise ClaimScopeReviewError("packet provider thresholds drifted")
    if manifest.get("valid_label_pairs") != [
        list(pair) for pair in sorted(VALID_LABEL_PAIRS)
    ]:
        raise ClaimScopeReviewError("packet label contract drifted")
    if manifest.get("measurement_limit") != MEASUREMENT_LIMIT:
        raise ClaimScopeReviewError("packet measurement limit drifted")
    expected_mechanical = {
        "accepted_candidate_count": (
            snapshot.execution.claim_scope_accepted_candidate_count
        ),
        "accepted_case_count": snapshot.execution.claim_scope_accepted_case_count,
        "review_packet_eligibility": snapshot.execution.review_packet_eligibility,
    }
    if manifest.get("mechanical_result") != expected_mechanical:
        raise ClaimScopeReviewError("packet mechanical result drifted")
    try:
        prepared_at = datetime.fromisoformat(str(manifest["prepared_at"]))
    except (KeyError, ValueError) as exc:
        raise ClaimScopeReviewError(
            "packet prepared_at is not an ISO timestamp"
        ) from exc
    if prepared_at.tzinfo is None:
        raise ClaimScopeReviewError(
            "packet prepared_at must be timezone-aware"
        )

    expected_rows = _packet_rows(snapshot)
    if (
        manifest.get("row_count") != len(expected_rows)
        or manifest.get("rows") != expected_rows
    ):
        raise ClaimScopeReviewError(
            "packet rows do not match source-locked candidates and context"
        )
    return {
        (
            candidate.case_id,
            candidate.provider_result_index,
            candidate.candidate_sha256,
        ): candidate
        for candidate in snapshot.candidates
    }


def _validated_label(
    row: dict[str, str],
    expected: ClaimScopeReviewCandidate,
) -> dict[str, str] | None:
    observed = _candidate_from_row(row)
    if observed != expected:
        raise ClaimScopeReviewError(
            f"label identity drifted for {expected.row_id}"
        )
    values = [row[field].strip() for field in ("relevant", "novel", "review_note")]
    if not any(values):
        return None
    if not all(values):
        raise ClaimScopeReviewError(f"{expected.row_id} is partially completed")
    relevant, novel, note = values
    relevant = relevant.upper()
    novel = novel.upper()
    if (relevant, novel) not in VALID_LABEL_PAIRS:
        raise ClaimScopeReviewError(
            f"{expected.row_id} has invalid relevant/novel pair: "
            f"{relevant}/{novel}"
        )
    if len("".join(note.split())) < 12:
        raise ClaimScopeReviewError(
            f"{expected.row_id} review_note is too short to ground the judgment"
        )
    return {
        "case_id": expected.case_id,
        "provider": expected.provider,
        "provider_result_index": str(expected.provider_result_index),
        "candidate_sha256": expected.candidate_sha256,
        "row_id": expected.row_id,
        "relevant": relevant,
        "novel": novel,
        "review_note": note,
    }


def _openalex_metrics(
    snapshot: ClaimScopeSourceSnapshot,
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
            "pass"
            if len(novel_case_ids) >= NOVEL_RELEVANT_CASES_MIN
            else "fail"
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
    decision = (
        "pass" if all(value == "pass" for value in thresholds.values()) else "fail"
    )
    return metrics, thresholds, decision


def summarize_packet(
    source_dir: Path,
    source_lock_path: Path,
    packet_dir: Path,
) -> dict[str, Any]:
    """Validate source, packet, declaration, and all frozen value gates."""

    if not packet_dir.is_dir():
        raise ClaimScopeReviewError(
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
    observed_keys: list[tuple[str, int, str]] = []
    for row in label_rows:
        candidate = _candidate_from_row(row)
        observed_keys.append(
            (
                candidate.case_id,
                candidate.provider_result_index,
                candidate.candidate_sha256,
            )
        )
    if len(observed_keys) != len(set(observed_keys)):
        raise ClaimScopeReviewError("labels contain duplicate candidate identities")
    if set(observed_keys) != set(expected_candidates):
        missing = sorted(set(expected_candidates) - set(observed_keys))
        extra = sorted(set(observed_keys) - set(expected_candidates))
        raise ClaimScopeReviewError(
            f"label identities do not match packet; missing={missing}, extra={extra}"
        )

    completed: dict[tuple[str, int, str], dict[str, str]] = {}
    incomplete_row_ids: list[str] = []
    for row in label_rows:
        candidate = _candidate_from_row(row)
        key = (
            candidate.case_id,
            candidate.provider_result_index,
            candidate.candidate_sha256,
        )
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
        raise ClaimScopeReviewError(
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
        "mode": "openalex_claim_scope_v3_value_review_result",
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
                    sorted(
                        Counter(
                            row["relevant"] for row in ordered_completed
                        ).items()
                    )
                ),
                "novel": dict(
                    sorted(
                        Counter(row["novel"] for row in ordered_completed).items()
                    )
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
                "claim_scope_v3_source_value",
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
        raise ClaimScopeReviewError(
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

    lock = commands.add_parser("lock", help="bind the exact v3 live output")
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
        result = summarize_packet(args.source, args.source_lock, args.packet)
        write_summary(args.output, result)
    print(_stdout_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
