"""Evaluate a zero-network official-source title recovery candidate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

from academic_agent.source_title_recovery import recover_official_source_title
from regulator_title_audit import authority_scope_for_url


ExpectedAction = Literal["preserve", "recover", "reject", "out_of_scope"]
LabelProvenance = Literal[
    "official_api_clean_control",
    "official_api_observed_encoding_anomaly",
    "observed_production_failure",
    "synthetic_positive_control",
    "synthetic_scope_control",
]

CASE_FIELDS = (
    "case_id",
    "source",
    "record_id",
    "url",
    "input_title",
    "label_provenance",
    "expected_action",
    "baseline_action",
    "candidate_action",
    "expected_title",
    "baseline_title",
    "candidate_title",
    "reason_codes",
    "baseline_matches_expectation",
    "candidate_matches_expectation",
    "idempotent_output",
)


class RecoveryCandidateError(ValueError):
    """Raised when the candidate evaluation would be partial or mutable."""


class FrozenCollection(BaseModel):
    """Provenance for one official API response used during case selection."""

    source: str = Field(min_length=3)
    request_url: HttpUrl
    raw_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    selection: str = Field(min_length=20)
    selected_count: int = Field(gt=0)


class RecoveryCase(BaseModel):
    """One immutable input and expected action at the recovery seam."""

    case_id: str = Field(min_length=5)
    source: str = Field(min_length=3)
    record_id: str
    url: HttpUrl
    input_title: str
    expected_action: ExpectedAction
    expected_title: str | None
    label_provenance: LabelProvenance

    @model_validator(mode="after")
    def expected_title_matches_action(self) -> "RecoveryCase":
        if self.expected_action in {"preserve", "recover"}:
            if self.expected_title is None:
                raise ValueError("accepted actions require expected_title")
        elif self.expected_title is not None:
            raise ValueError("rejected or out-of-scope cases cannot expect a title")
        return self


class RecoveryChallenge(BaseModel):
    """Frozen development controls, not a real-world prevalence sample."""

    schema_version: Literal[1]
    protocol: Literal["regulator-title-recovery-candidate-v1"]
    collected_at: str = Field(min_length=10)
    measurement_design: str = Field(min_length=20)
    collections: list[FrozenCollection] = Field(min_length=2)
    cases: list[RecoveryCase] = Field(min_length=1)


def _read_challenge(path: Path) -> tuple[RecoveryChallenge, str]:
    try:
        payload = path.read_bytes()
        challenge = RecoveryChallenge.model_validate_json(payload)
    except (OSError, ValueError) as exc:
        raise RecoveryCandidateError(f"could not load frozen challenge: {exc}") from exc
    case_ids = [case.case_id for case in challenge.cases]
    if len(case_ids) != len(set(case_ids)):
        raise RecoveryCandidateError("frozen challenge contains duplicate case_id values")
    return challenge, hashlib.sha256(payload).hexdigest()


def _authority_category(url: str) -> Literal["regulatory", "clinical_registry"] | None:
    scope = authority_scope_for_url(url)
    if scope in {"regulatory", "clinical_registry"}:
        return scope
    return None


def _legacy_baseline(case: RecoveryCase) -> tuple[ExpectedAction, str | None]:
    """Reproduce the pre-candidate title seam without calling production code.

    Previously any market title of five or more characters survived unchanged;
    shorter titles were rejected before URL-specific handling. Out-of-scope
    hosts were rejected elsewhere by the market allowlist, so they remain a
    distinct scope outcome here rather than being counted as title successes.
    """

    if _authority_category(str(case.url)) is None:
        return "out_of_scope", None
    if len(case.input_title.strip()) < 5:
        return "reject", None
    return "preserve", case.input_title


def _matches(
    case: RecoveryCase,
    action: str,
    title: str | None,
) -> bool:
    return action == case.expected_action and title == case.expected_title


def evaluate_candidate(
    challenge_path: Path,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """Evaluate baseline and candidate deterministically over frozen cases."""

    challenge, challenge_sha256 = _read_challenge(challenge_path)
    rows: list[dict[str, object]] = []
    for case in challenge.cases:
        url = str(case.url)
        category = _authority_category(url)
        baseline_action, baseline_title = _legacy_baseline(case)
        decision = recover_official_source_title(
            case.input_title,
            url,
            authority_category=category,
        )
        candidate_title = decision.title
        idempotent = True
        if candidate_title is not None and decision.action in {"preserve", "recover"}:
            second = recover_official_source_title(
                candidate_title,
                url,
                authority_category=category,
            )
            idempotent = second.title == candidate_title
        rows.append(
            {
                "case_id": case.case_id,
                "source": case.source,
                "record_id": case.record_id,
                "url": url,
                "input_title": case.input_title,
                "label_provenance": case.label_provenance,
                "expected_action": case.expected_action,
                "baseline_action": baseline_action,
                "candidate_action": decision.action,
                "expected_title": case.expected_title or "",
                "baseline_title": baseline_title or "",
                "candidate_title": candidate_title or "",
                "reason_codes": "|".join(decision.reason_codes),
                "baseline_matches_expectation": _matches(
                    case,
                    baseline_action,
                    baseline_title,
                ),
                "candidate_matches_expectation": _matches(
                    case,
                    decision.action,
                    candidate_title,
                ),
                "idempotent_output": idempotent,
            }
        )

    provenance_counts = Counter(str(row["label_provenance"]) for row in rows)
    baseline_matches = sum(bool(row["baseline_matches_expectation"]) for row in rows)
    candidate_matches = sum(bool(row["candidate_matches_expectation"]) for row in rows)

    def matched(provenance: str) -> int:
        return sum(
            bool(row["candidate_matches_expectation"])
            for row in rows
            if row["label_provenance"] == provenance
        )

    official_selected = sum(item.selected_count for item in challenge.collections)
    checks = [
        {
            "name": "official_api_selection_is_frozen",
            "passed": official_selected == 24,
            "observed": official_selected,
            "requirement": 24,
        },
        {
            "name": "clean_controls_are_preserved",
            "passed": matched("official_api_clean_control") == 23,
            "observed": matched("official_api_clean_control"),
            "requirement": 23,
        },
        {
            "name": "observed_defects_are_recovered",
            "passed": (
                matched("official_api_observed_encoding_anomaly") == 1
                and matched("observed_production_failure") == 1
            ),
            "observed": (
                matched("official_api_observed_encoding_anomaly")
                + matched("observed_production_failure")
            ),
            "requirement": 2,
        },
        {
            "name": "synthetic_positive_controls_match",
            "passed": matched("synthetic_positive_control") == 3,
            "observed": matched("synthetic_positive_control"),
            "requirement": 3,
        },
        {
            "name": "scope_control_matches",
            "passed": matched("synthetic_scope_control") == 1,
            "observed": matched("synthetic_scope_control"),
            "requirement": 1,
        },
        {
            "name": "all_outputs_are_idempotent",
            "passed": all(bool(row["idempotent_output"]) for row in rows),
            "observed": sum(bool(row["idempotent_output"]) for row in rows),
            "requirement": len(rows),
        },
        {
            "name": "all_candidate_expectations_match",
            "passed": candidate_matches == len(rows),
            "observed": candidate_matches,
            "requirement": len(rows),
        },
    ]
    result: dict[str, object] = {
        "schema_version": 1,
        "protocol": challenge.protocol,
        "challenge_sha256": challenge_sha256,
        "measurement_design": challenge.measurement_design,
        "case_count": len(rows),
        "provenance_counts": dict(sorted(provenance_counts.items())),
        "baseline": {
            "matched_expectation_count": baseline_matches,
            "mismatched_expectation_count": len(rows) - baseline_matches,
        },
        "candidate": {
            "state": (
                "accepted_for_production_integration"
                if all(bool(check["passed"]) for check in checks)
                else "rejected"
            ),
            "matched_expectation_count": candidate_matches,
            "mismatched_expectation_count": len(rows) - candidate_matches,
        },
        "checks": checks,
        "contract_checks_passed": all(bool(check["passed"]) for check in checks),
        "network_calls": 0,
        "llm_calls": 0,
        "production_mutations": 0,
        "measurement_limit": (
            "This development challenge does not estimate real-world prevalence, "
            "semantic title accuracy, precision, recall, or report-quality impact."
        ),
    }
    return result, rows


def write_candidate(
    output: Path,
    result: dict[str, object],
    rows: list[dict[str, object]],
) -> None:
    """Persist the result once so reruns cannot silently replace evidence."""

    if output.exists():
        raise RecoveryCandidateError(f"refusing to overwrite existing output: {output}")
    output.mkdir(parents=True)
    (output / "result.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with (output / "cases.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CASE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("challenge", type=Path)
    parser.add_argument("output", type=Path)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    result, rows = evaluate_candidate(args.challenge)
    write_candidate(args.output, result, rows)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
