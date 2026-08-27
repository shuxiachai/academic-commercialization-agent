"""Label-blind development audit for the OpenAlex precision-v2 gate.

The candidate decisions are computed from frozen case journals before this
module opens the human-label file.  Labels are joined only to score the
already-materialized decisions.  The production worker never imports this
module, and a passing development result authorizes neither a live request nor
a report-workflow connection.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from academic_agent.openalex_precision import (
    AcademicPrecisionDecision,
    AcademicPrecisionProfile,
    evaluate_academic_candidate,
)
from academic_agent.tools.evidence_search import ToolEvidenceCandidate


_ROOT = Path(__file__).resolve().parent
DEFAULT_FIXTURE_PATH = (
    _ROOT / "tests/fixtures/openalex_precision_v2_challenge.json"
)
EXPECTED_FIXTURE_SHA256 = (
    "355782bbe40278f44cb76f650d57fbb13be6b9097bfecb6e101815a24c47ea8b"
)
_EXPECTED_LABEL_COLUMNS = (
    "case_id",
    "provider",
    "accepted_source_id",
    "title",
    "url",
    "relevant",
    "novel",
    "review_note",
)
_DECISION_COLUMNS = (
    "case_id",
    "accepted_source_id",
    "title",
    "url",
    "candidate_sha256",
    "profile_sha256",
    "action",
    "matched_required_groups",
    "missing_required_groups",
    "matched_supporting_groups",
    "title_required_groups",
    "abstention_reasons",
    "relevant",
    "novel",
)


class OpenAlexPrecisionAuditError(ValueError):
    """Raised when frozen lineage or review completeness fails closed."""


class DevelopmentSourceSpec(BaseModel):
    """Hashes that bind the audit to the completed development observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    labels_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_rows_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    row_count: int = Field(ge=1, le=40)
    case_execution_sha256: dict[str, str] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def _validate_case_hashes(self) -> "DevelopmentSourceSpec":
        if any(
            len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
            for value in self.case_execution_sha256.values()
        ):
            raise ValueError("every case execution must carry a lowercase SHA-256")
        return self


class DevelopmentProfileSpec(BaseModel):
    """One case identifier paired with the trusted profile under test."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(pattern=r"^[A-Z][0-9]{2}$")
    required_groups: tuple[dict[str, Any], ...]
    supporting_groups: tuple[dict[str, Any], ...]
    minimum_supporting_groups: int
    minimum_title_required_groups: int

    def profile(self) -> AcademicPrecisionProfile:
        return AcademicPrecisionProfile.model_validate(
            self.model_dump(exclude={"case_id"})
        )


class DevelopmentManifest(BaseModel):
    """Only the fixture fields needed for the development audit."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    schema_version: Literal[1] = 1
    mode: Literal["openalex_precision_v2_unseen_challenge"]
    production_connected: Literal[False] = False
    development_source: DevelopmentSourceSpec
    development_profiles: tuple[DevelopmentProfileSpec, ...] = Field(
        min_length=1,
        max_length=8,
    )

    @model_validator(mode="after")
    def _validate_case_identity(self) -> "DevelopmentManifest":
        profile_ids = tuple(item.case_id for item in self.development_profiles)
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("development profile case IDs must be unique")
        if profile_ids != tuple(self.development_source.case_execution_sha256):
            raise ValueError(
                "development profiles and case-journal hashes must share order"
            )
        return self


@dataclass(frozen=True)
class FrozenCandidate:
    """A quarantine-accepted source reconstructed from one case journal."""

    case_id: str
    accepted_source_id: str
    candidate: ToolEvidenceCandidate


@dataclass(frozen=True)
class BlindDecision:
    """A decision created before the label file is available to the scorer."""

    source: FrozenCandidate
    decision: AcademicPrecisionDecision


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _require_hash(path: Path, expected: str, label: str) -> None:
    observed = _sha256_file(path)
    if observed != expected:
        raise OpenAlexPrecisionAuditError(
            f"{label} byte identity drifted: expected {expected}, got {observed}"
        )


def load_manifest(
    fixture_path: Path = DEFAULT_FIXTURE_PATH,
    *,
    expected_fixture_sha256: str = EXPECTED_FIXTURE_SHA256,
) -> tuple[str, DevelopmentManifest]:
    """Check raw bytes before parsing any experimental configuration."""

    raw = fixture_path.read_bytes()
    fixture_sha256 = _sha256_bytes(raw)
    if fixture_sha256 != expected_fixture_sha256:
        raise OpenAlexPrecisionAuditError(
            "precision-v2 fixture byte identity drifted: "
            f"expected {expected_fixture_sha256}, got {fixture_sha256}"
        )
    return fixture_sha256, DevelopmentManifest.model_validate_json(raw)


def _candidate_from_source(
    source: dict[str, Any],
    provider_indices: dict[str, int],
) -> ToolEvidenceCandidate:
    url = str(source.get("url", ""))
    if url not in provider_indices:
        raise OpenAlexPrecisionAuditError(
            f"accepted source {url!r} is absent from provider candidate records"
        )
    return ToolEvidenceCandidate.model_validate(
        {
            "title": source.get("title"),
            "url": url,
            "doi": source.get("doi"),
            "publisher": source.get("publisher"),
            "published_date": source.get("published_date"),
            "evidence_summary": source.get("evidence_summary"),
            "summary_source": source.get("summary_source"),
            "citation_count": source.get("citation_count"),
            "provider_result_index": provider_indices[url],
        }
    )


def _read_accepted_csv_rows(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = tuple(csv.DictReader(handle))
    accepted: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        if row.get("local_disposition") != "quarantined_accepted":
            continue
        key = (row.get("case_id", ""), row.get("accepted_source_id", ""))
        if not all(key) or key in accepted:
            raise OpenAlexPrecisionAuditError(
                "candidate CSV has a missing or duplicate accepted-source identity"
            )
        accepted[key] = row
    return accepted


def load_frozen_candidates(
    manifest: DevelopmentManifest,
    source_root: Path,
) -> tuple[FrozenCandidate, ...]:
    """Reconstruct every accepted row while preserving provider lineage."""

    candidate_csv = source_root / "candidates.csv"
    _require_hash(
        candidate_csv,
        manifest.development_source.candidate_rows_sha256,
        "development candidate CSV",
    )
    csv_rows = _read_accepted_csv_rows(candidate_csv)
    candidates: list[FrozenCandidate] = []
    observed_keys: set[tuple[str, str]] = set()

    for case_id, expected_hash in (
        manifest.development_source.case_execution_sha256.items()
    ):
        journal_path = source_root / "case-executions" / f"{case_id}.json"
        _require_hash(journal_path, expected_hash, f"{case_id} case journal")
        journal = json.loads(journal_path.read_text(encoding="utf-8"))
        if journal.get("case_id") != case_id:
            raise OpenAlexPrecisionAuditError(
                f"{case_id} case journal carries a different case identity"
            )
        audit = journal.get("audit")
        if not isinstance(audit, dict):
            raise OpenAlexPrecisionAuditError(f"{case_id} audit is missing")
        call_audits = audit.get("call_audits")
        if not isinstance(call_audits, list) or len(call_audits) != 1:
            raise OpenAlexPrecisionAuditError(
                f"{case_id} must retain exactly one provider-call audit"
            )
        records = call_audits[0].get("candidate_records")
        if not isinstance(records, list):
            raise OpenAlexPrecisionAuditError(
                f"{case_id} provider candidate records are missing"
            )
        provider_indices: dict[str, int] = {}
        for record in records:
            if not isinstance(record, dict):
                raise OpenAlexPrecisionAuditError(
                    f"{case_id} provider candidate record is not an object"
                )
            url = str(record.get("url", ""))
            index = record.get("provider_result_index")
            if not url or not isinstance(index, int) or url in provider_indices:
                raise OpenAlexPrecisionAuditError(
                    f"{case_id} provider candidate lineage is ambiguous"
                )
            provider_indices[url] = index

        accepted_sources = audit.get("accepted_sources")
        if not isinstance(accepted_sources, list):
            raise OpenAlexPrecisionAuditError(
                f"{case_id} accepted-source list is missing"
            )
        for source in accepted_sources:
            if not isinstance(source, dict):
                raise OpenAlexPrecisionAuditError(
                    f"{case_id} accepted source is not an object"
                )
            source_id = str(source.get("source_id", ""))
            key = (case_id, source_id)
            if not source_id or key in observed_keys:
                raise OpenAlexPrecisionAuditError(
                    f"{case_id} accepted-source identity is missing or duplicated"
                )
            csv_row = csv_rows.get(key)
            if csv_row is None:
                raise OpenAlexPrecisionAuditError(
                    f"{case_id}/{source_id} is absent from the accepted CSV rows"
                )
            if (
                csv_row.get("title") != source.get("title")
                or csv_row.get("url") != source.get("url")
            ):
                raise OpenAlexPrecisionAuditError(
                    f"{case_id}/{source_id} identity differs across artifact seams"
                )
            observed_keys.add(key)
            candidates.append(
                FrozenCandidate(
                    case_id=case_id,
                    accepted_source_id=source_id,
                    candidate=_candidate_from_source(source, provider_indices),
                )
            )

    expected_count = manifest.development_source.row_count
    if len(candidates) != expected_count or set(csv_rows) != observed_keys:
        raise OpenAlexPrecisionAuditError(
            "accepted-row denominator differs between fixture, journals and CSV"
        )
    return tuple(candidates)


def make_blind_decisions(
    manifest: DevelopmentManifest,
    candidates: tuple[FrozenCandidate, ...],
) -> tuple[BlindDecision, ...]:
    """Materialize every decision without accepting a label argument."""

    profiles = {
        item.case_id: item.profile() for item in manifest.development_profiles
    }
    decisions: list[BlindDecision] = []
    for source in candidates:
        profile = profiles.get(source.case_id)
        if profile is None:
            raise OpenAlexPrecisionAuditError(
                f"{source.case_id} has no trusted precision profile"
            )
        decisions.append(
            BlindDecision(
                source=source,
                decision=evaluate_academic_candidate(source.candidate, profile),
            )
        )
    return tuple(decisions)


def _read_labels(
    path: Path,
    expected_sha256: str,
    expected_count: int,
) -> dict[tuple[str, str], dict[str, str]]:
    # This function is intentionally called only after make_blind_decisions.
    # Keeping the file operation here makes label leakage testable rather than
    # relying on the caller to remember a procedural convention.
    _require_hash(path, expected_sha256, "development label file")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != _EXPECTED_LABEL_COLUMNS:
            raise OpenAlexPrecisionAuditError("development label columns drifted")
        rows = tuple(reader)
    if len(rows) != expected_count:
        raise OpenAlexPrecisionAuditError("development label denominator drifted")

    labels: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["case_id"], row["accepted_source_id"])
        if key in labels:
            raise OpenAlexPrecisionAuditError(
                "development labels contain a duplicate source identity"
            )
        if row["provider"] != "openalex" or row["relevant"] not in {"YES", "NO"}:
            raise OpenAlexPrecisionAuditError(
                f"{key[0]}/{key[1]} has an invalid provider or relevance label"
            )
        labels[key] = row
    return labels


def _json_tuple(values: tuple[str, ...]) -> str:
    return json.dumps(values, ensure_ascii=True, separators=(",", ":"))


def score_decisions(
    decisions: tuple[BlindDecision, ...],
    labels: dict[tuple[str, str], dict[str, str]],
) -> tuple[dict[str, Any], tuple[dict[str, str], ...]]:
    """Join labels by frozen identity and calculate the development gate."""

    decision_keys = {
        (item.source.case_id, item.source.accepted_source_id) for item in decisions
    }
    if set(labels) != decision_keys:
        raise OpenAlexPrecisionAuditError(
            "label identities do not exactly match blind decision identities"
        )

    output_rows: list[dict[str, str]] = []
    relevant_total = 0
    irrelevant_total = 0
    relevant_accepted = 0
    irrelevant_accepted = 0
    relevant_case_ids: set[str] = set()
    retained_case_ids: set[str] = set()

    for item in decisions:
        source = item.source
        decision = item.decision
        key = (source.case_id, source.accepted_source_id)
        label = labels[key]
        if (
            label["title"] != source.candidate.title
            or label["url"] != source.candidate.url
        ):
            raise OpenAlexPrecisionAuditError(
                f"{source.case_id}/{source.accepted_source_id} label identity drifted"
            )
        relevant = label["relevant"] == "YES"
        if relevant:
            relevant_total += 1
            relevant_case_ids.add(source.case_id)
            if decision.action == "ACCEPT":
                relevant_accepted += 1
                retained_case_ids.add(source.case_id)
        else:
            irrelevant_total += 1
            if decision.action == "ACCEPT":
                irrelevant_accepted += 1

        output_rows.append(
            {
                "case_id": source.case_id,
                "accepted_source_id": source.accepted_source_id,
                "title": source.candidate.title,
                "url": source.candidate.url,
                "candidate_sha256": decision.candidate_sha256,
                "profile_sha256": decision.profile_sha256,
                "action": decision.action,
                "matched_required_groups": _json_tuple(
                    decision.matched_required_groups
                ),
                "missing_required_groups": _json_tuple(
                    decision.missing_required_groups
                ),
                "matched_supporting_groups": _json_tuple(
                    decision.matched_supporting_groups
                ),
                "title_required_groups": _json_tuple(
                    decision.title_required_groups
                ),
                "abstention_reasons": _json_tuple(decision.abstention_reasons),
                "relevant": label["relevant"],
                "novel": label["novel"],
            }
        )

    all_relevant_accepted = relevant_total > 0 and (
        relevant_accepted == relevant_total
    )
    all_irrelevant_abstained = irrelevant_total > 0 and irrelevant_accepted == 0
    every_case_retains_relevant = retained_case_ids == relevant_case_ids
    qualified = (
        all_relevant_accepted
        and all_irrelevant_abstained
        and every_case_retains_relevant
    )
    metrics: dict[str, Any] = {
        "status": (
            "qualified_for_unseen_harness"
            if qualified
            else "development_gate_failed"
        ),
        "qualified": qualified,
        "row_count": len(decisions),
        "relevant_total": relevant_total,
        "relevant_accepted": relevant_accepted,
        "irrelevant_total": irrelevant_total,
        "irrelevant_accepted": irrelevant_accepted,
        "irrelevant_abstained": irrelevant_total - irrelevant_accepted,
        "relevant_case_count": len(relevant_case_ids),
        "retained_relevant_case_count": len(retained_case_ids),
        "all_relevant_accepted": all_relevant_accepted,
        "all_irrelevant_abstained": all_irrelevant_abstained,
        "every_case_retains_relevant": every_case_retains_relevant,
    }
    return metrics, tuple(output_rows)


def _write_once(
    output_dir: Path,
    result: dict[str, Any],
    rows: tuple[dict[str, str], ...],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=False)
    result_path = output_dir / "result.json"
    decisions_path = output_dir / "decisions.csv"
    with result_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, ensure_ascii=True, indent=2, sort_keys=True)
        handle.write("\n")
    with decisions_path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_DECISION_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def run_development_audit(
    *,
    fixture_path: Path,
    source_root: Path,
    labels_path: Path,
    output_dir: Path,
    expected_fixture_sha256: str = EXPECTED_FIXTURE_SHA256,
) -> dict[str, Any]:
    """Run the frozen development gate without network or model calls."""

    fixture_sha256, manifest = load_manifest(
        fixture_path,
        expected_fixture_sha256=expected_fixture_sha256,
    )
    candidates = load_frozen_candidates(manifest, source_root)
    blind_decisions = make_blind_decisions(manifest, candidates)
    labels = _read_labels(
        labels_path,
        manifest.development_source.labels_sha256,
        manifest.development_source.row_count,
    )
    metrics, rows = score_decisions(blind_decisions, labels)
    result: dict[str, Any] = {
        "schema_version": 1,
        "mode": "openalex_precision_v2_development_audit",
        "fixture_sha256": fixture_sha256,
        "candidate_rows_sha256": (
            manifest.development_source.candidate_rows_sha256
        ),
        "labels_sha256": manifest.development_source.labels_sha256,
        "case_execution_sha256": (
            manifest.development_source.case_execution_sha256
        ),
        "decision_count": len(rows),
        "metrics": metrics,
        "network_calls_performed": False,
        "model_calls_performed": False,
        "production_connected": False,
        "report_workflow_connected": False,
        "unseen_live_execution_authorized": False,
    }
    _write_once(output_dir, result, rows)
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE_PATH)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    result = run_development_audit(
        fixture_path=args.fixture,
        source_root=args.source_root,
        labels_path=args.labels,
        output_dir=args.output,
    )
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
