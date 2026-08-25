"""Prepare and summarize the frozen Phase 3 human evidence-value review.

The live pilot's original directory is write-once evidence. This module only
reads that directory, copies stable candidate identities into a separate human
packet, and validates the returned labels without opening a socket.
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
from typing import Any


SOURCE_FILES = ("manifest.json", "execution.json", "candidates.csv", "review.csv")
REVIEW_FIELDS = (
    "case_id",
    "accepted_source_id",
    "title",
    "url",
    "relevant",
    "novel",
    "review_note",
)
CANDIDATE_FIELDS = (
    "case_id",
    "tool",
    "provider_request_id",
    "provider_result_index",
    "adapter_disposition",
    "local_disposition",
    "accepted_source_id",
    "title",
    "url",
    "provider_rejection_code",
    "local_rejection_code",
    "rejection_detail",
    "trace_id",
)
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
FROZEN_SOURCE_HASHES = {
    "manifest.json": "8989acda104e55066b91f42c7f3f78ec33141f440a9f91c6e2b322e315f6c84b",
    "execution.json": "2625c20b40d216fb067cbda307880342843ec22d38b76c1ea39e6762ce77b133",
    "candidates.csv": "0ba0c36518deff990dd36bf3c9a212aa1e61860c54bd0dd4ad273f5f50b762a5",
    "review.csv": "3eaee269f838c4d5b36a4dc16d1c797a713c9c95f2635c572686e8312020d52d",
}
FROZEN_CASES = {
    "L01": {
        "topic": "Engineered cutinases for enzymatic PET textile recycling",
        "gap_code": "retrieval_domain_failed",
        "gap_subject": "academic",
        "query": "engineered cutinases enzymatic PET textile recycling academic performance study",
    },
    "L02": {
        "topic": "Closed-pore hard-carbon anodes for sodium-ion batteries",
        "gap_code": "retrieval_domain_failed",
        "gap_subject": "patent",
        "query": "closed-pore hard-carbon anodes sodium-ion battery patent claims",
    },
    "L03": {
        "topic": "Solid-state transformers for medium-voltage data centres",
        "gap_code": "retrieval_domain_failed",
        "gap_subject": "market",
        "query": "solid-state transformers medium-voltage data centres market deployment adoption",
    },
    "L04": {
        "topic": "AI-enabled retinal screening medical devices",
        "gap_code": "authority_category_missing",
        "gap_subject": "regulatory",
        "query": "AI-enabled retinal screening medical devices FDA regulatory clearance",
    },
    "L05": {
        "topic": "Personalised neoantigen mRNA vaccines for pancreatic cancer",
        "gap_code": "authority_category_missing",
        "gap_subject": "clinical_registry",
        "query": "personalised neoantigen mRNA vaccines pancreatic cancer clinical trial registry",
    },
}
VALID_LABEL_PAIRS = {
    ("YES", "YES"),
    ("YES", "NO"),
    ("NO", "N/A"),
    ("UNVERIFIABLE", "UNVERIFIABLE"),
}
ELIGIBLE_AI_USE = {"NONE", "LANGUAGE_ONLY"}
ALL_AI_USE = ELIGIBLE_AI_USE | {"SOME_SUBSTANTIVE", "MOST_OR_ALL"}
WRONG_SOURCE_RATE_MAX = 0.05
NOVEL_RELEVANT_CASES_MIN = 3


class Phase3ReviewError(ValueError):
    """Raised when review provenance, identity, or labels are not trustworthy."""


@dataclass(frozen=True)
class ReviewCandidate:
    """One accepted source identity copied from the write-once live artifact."""

    case_id: str
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
    """Validated source state used at both packet and summary boundaries."""

    file_hashes: dict[str, str]
    candidates: tuple[ReviewCandidate, ...]


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _file_sha256(path: Path) -> str:
    try:
        return _sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise Phase3ReviewError(f"could not read source artifact {path}: {exc}") from exc


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Phase3ReviewError(f"could not parse JSON from {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise Phase3ReviewError(f"{path} must contain one JSON object")
    return payload


def _read_csv(path: Path, expected_fields: tuple[str, ...]) -> list[dict[str, str]]:
    try:
        # utf-8-sig accepts a BOM introduced by spreadsheet software without
        # weakening any row-identity check performed after parsing.
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != expected_fields:
                raise Phase3ReviewError(
                    f"{path} columns must be exactly: {', '.join(expected_fields)}"
                )
            return list(reader)
    except (OSError, csv.Error) as exc:
        raise Phase3ReviewError(f"could not read CSV from {path}: {exc}") from exc


def _write_csv_new(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="raise")
            writer.writeheader()
            writer.writerows(rows)
    except OSError as exc:
        raise Phase3ReviewError(f"could not create {path}: {exc}") from exc


def _write_text_new(path: Path, value: str) -> None:
    try:
        with path.open("x", encoding="utf-8", newline="") as handle:
            handle.write(value)
    except OSError as exc:
        raise Phase3ReviewError(f"could not create {path}: {exc}") from exc


def _expected_hashes(value: Mapping[str, str] | None) -> dict[str, str]:
    # Tests inject hashes for synthetic zero-network fixtures. The CLI exposes
    # no override and therefore remains pinned to the one authorized live run.
    hashes = dict(FROZEN_SOURCE_HASHES if value is None else value)
    if set(hashes) != set(SOURCE_FILES):
        raise Phase3ReviewError("expected source hashes must name exactly the four source artifacts")
    return hashes


def _validate_source_cases(manifest: dict[str, Any]) -> None:
    if manifest.get("mode") != "phase3_frozen_provider_compatibility":
        raise Phase3ReviewError("source manifest has the wrong mode")
    if manifest.get("production_connected") is not False:
        raise Phase3ReviewError("source manifest must remain production-disconnected")
    cases = manifest.get("cases")
    if not isinstance(cases, list) or len(cases) != len(FROZEN_CASES):
        raise Phase3ReviewError("source manifest must contain the five frozen cases")

    observed: dict[str, dict[str, str]] = {}
    for item in cases:
        if not isinstance(item, dict) or not isinstance(item.get("spec"), dict):
            raise Phase3ReviewError("every source manifest case must contain a spec object")
        spec = item["spec"]
        case_id = str(spec.get("case_id", ""))
        if not case_id or case_id in observed:
            raise Phase3ReviewError("source manifest case IDs must be non-empty and unique")
        observed[case_id] = {
            "topic": str(spec.get("topic", "")),
            "gap_code": str(spec.get("gap_code", "")),
            "gap_subject": str(spec.get("gap_subject", "")),
            "query": str(spec.get("query", "")),
        }
    if observed != FROZEN_CASES:
        raise Phase3ReviewError("source manifest case definitions drifted from the preregistration")


def _validate_execution(execution: dict[str, Any]) -> None:
    expected = {
        "mode": "phase3_live_provider_compatibility",
        "request_count": 5,
        "completed_case_count": 5,
        "review_state": "not_inspected",
        "production_connected": False,
        "report_workflow_connected": False,
    }
    mismatches = {
        field: {"expected": value, "observed": execution.get(field)}
        for field, value in expected.items()
        if execution.get(field) != value
    }
    if mismatches:
        raise Phase3ReviewError(f"source execution contract drifted: {mismatches}")


def _candidate_from_row(row: Mapping[str, str]) -> ReviewCandidate:
    candidate = ReviewCandidate(
        case_id=row.get("case_id", "").strip(),
        accepted_source_id=row.get("accepted_source_id", "").strip(),
        title=row.get("title", "").strip(),
        url=row.get("url", "").strip(),
    )
    if not all((candidate.case_id, candidate.accepted_source_id, candidate.title, candidate.url)):
        raise Phase3ReviewError("accepted review identities must not contain blank fields")
    if candidate.case_id not in FROZEN_CASES:
        raise Phase3ReviewError(f"unexpected case ID in review rows: {candidate.case_id}")
    return candidate


def validate_source_artifacts(
    source_dir: Path,
    *,
    expected_hashes: Mapping[str, str] | None = None,
) -> SourceSnapshot:
    """Validate all source seams without modifying the live output directory."""

    if not source_dir.is_dir():
        raise Phase3ReviewError(f"source directory does not exist: {source_dir}")
    expected = _expected_hashes(expected_hashes)
    file_hashes = {name: _file_sha256(source_dir / name) for name in SOURCE_FILES}
    if file_hashes != expected:
        drift = {
            name: {"expected": expected[name], "observed": file_hashes[name]}
            for name in SOURCE_FILES
            if file_hashes[name] != expected[name]
        }
        raise Phase3ReviewError(f"source artifact identity drifted: {drift}")

    _validate_source_cases(_read_json_object(source_dir / "manifest.json"))
    _validate_execution(_read_json_object(source_dir / "execution.json"))
    candidate_rows = _read_csv(source_dir / "candidates.csv", CANDIDATE_FIELDS)
    review_rows = _read_csv(source_dir / "review.csv", REVIEW_FIELDS)

    accepted_by_key: dict[tuple[str, str], ReviewCandidate] = {}
    for row in candidate_rows:
        if row["local_disposition"].strip() != "quarantined_accepted":
            continue
        candidate = _candidate_from_row(row)
        key = (candidate.case_id, candidate.accepted_source_id)
        if key in accepted_by_key:
            raise Phase3ReviewError(f"accepted candidates contain duplicate identity {candidate.row_id}")
        accepted_by_key[key] = candidate

    review_by_key: dict[tuple[str, str], ReviewCandidate] = {}
    for row in review_rows:
        if any(row[field].strip() for field in ("relevant", "novel", "review_note")):
            raise Phase3ReviewError("source review.csv is no longer the frozen blank artifact")
        candidate = _candidate_from_row(row)
        key = (candidate.case_id, candidate.accepted_source_id)
        if key in review_by_key:
            raise Phase3ReviewError(f"source review rows contain duplicate identity {candidate.row_id}")
        review_by_key[key] = candidate

    if review_by_key != accepted_by_key:
        missing = sorted(set(accepted_by_key) - set(review_by_key))
        extra = sorted(set(review_by_key) - set(accepted_by_key))
        changed = sorted(
            f"{case_id}/{source_id}"
            for case_id, source_id in set(review_by_key) & set(accepted_by_key)
            if review_by_key[(case_id, source_id)] != accepted_by_key[(case_id, source_id)]
        )
        raise Phase3ReviewError(
            f"blank review rows do not match accepted candidates; missing={missing}, "
            f"extra={extra}, changed={changed}"
        )
    if len(review_by_key) != 25:
        raise Phase3ReviewError(f"source review must contain 25 accepted candidates, got {len(review_by_key)}")
    case_counts = Counter(case_id for case_id, _ in review_by_key)
    if case_counts != Counter({case_id: 5 for case_id in FROZEN_CASES}):
        raise Phase3ReviewError(f"every frozen case must contain five candidates, got {dict(case_counts)}")

    ordered = tuple(review_by_key[key] for key in sorted(review_by_key))
    return SourceSnapshot(file_hashes=file_hashes, candidates=ordered)


def _packet_readme() -> str:
    rows = "\n".join(
        f"| {case_id} | {case['topic']} | {case['gap_subject']} | {case['query']} |"
        for case_id, case in FROZEN_CASES.items()
    )
    return f"""# Phase 3 evidence-gap human review packet

This packet contains 25 candidates from one production-disconnected Tavily
compatibility pilot. Preparing and summarizing it makes zero API or LLM calls.

Do not edit `packet_manifest.json`. Complete only `labels.csv` and
`reviewer_declaration.csv`. You may reorder label rows, but do not change case
IDs, accepted source IDs, titles, or URLs.

## Case targets

| Case | Topic | Gap | Search target |
|---|---|---|---|
{rows}

Judge relevance against the named gap, not broad topic overlap. Attempt every
URL and inspect the abstract, claims, market evidence, regulatory document, or
trial record rather than relying on the title.

## Labels

- `relevant=YES`: directly answers the declared gap.
- `relevant=NO`: generic, adjacent, or mismatched.
- `relevant=UNVERIFIABLE`: attempted but insufficient content was inspectable.
- `novel=YES`: adds material evidence absent from the frozen baseline.
- `novel=NO`: relevant but duplicative.
- `novel=N/A`: required with `relevant=NO`.
- `novel=UNVERIFIABLE`: required with `relevant=UNVERIFIABLE`.

The only valid pairs are `YES/YES`, `YES/NO`, `NO/N/A`, and
`UNVERIFIABLE/UNVERIFIABLE`. Every completed row needs a source-grounded
`review_note`; do not write only "relevant" or "not relevant".

Complete `reviewer_declaration.csv` after all rows. `NONE` or `LANGUAGE_ONLY`
generative-AI use is eligible. Substantive AI judgments are retained but
excluded from the human-value headline. An unreachable source is
`UNVERIFIABLE`, never silently negative or positive.

The frozen exploratory thresholds are at most one wrong source among 25 rows
and novel relevant evidence in at least three of five cases. Passing both does
not authorize production Tool Calling because planner trigger precision remains
unmeasured.
"""


def _packet_manifest(snapshot: SourceSnapshot) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": "phase3_human_value_review_packet",
        "prepared_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source_mode": "frozen live-provider artifacts; zero network",
        "source_file_sha256": snapshot.file_hashes,
        "case_contexts": [
            {"case_id": case_id, **context} for case_id, context in FROZEN_CASES.items()
        ],
        "row_count": len(snapshot.candidates),
        "rows": [
            {
                "case_id": candidate.case_id,
                "accepted_source_id": candidate.accepted_source_id,
                "title": candidate.title,
                "url": candidate.url,
                "identity_sha256": candidate.identity_sha256,
            }
            for candidate in snapshot.candidates
        ],
        "valid_label_pairs": [list(pair) for pair in sorted(VALID_LABEL_PAIRS)],
        "thresholds": {
            "wrong_source_rate_max": WRONG_SOURCE_RATE_MAX,
            "novel_relevant_cases_min": NOVEL_RELEVANT_CASES_MIN,
            "case_count": len(FROZEN_CASES),
        },
        "production_connected": False,
        "measurement_limit": (
            "This injected-intent review can measure candidate relevance and novelty, "
            "not planner trigger precision, report improvement, or production value."
        ),
    }


def prepare_packet(
    source_dir: Path,
    packet_dir: Path,
    *,
    expected_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Create a separate, deterministic-identity packet from frozen artifacts."""

    if packet_dir.exists():
        raise Phase3ReviewError(f"refusing to overwrite existing packet: {packet_dir}")
    snapshot = validate_source_artifacts(source_dir, expected_hashes=expected_hashes)
    try:
        packet_dir.mkdir(parents=True, exist_ok=False)
    except OSError as exc:
        raise Phase3ReviewError(f"could not create packet directory {packet_dir}: {exc}") from exc

    manifest = _packet_manifest(snapshot)
    label_rows = [
        {
            "case_id": candidate.case_id,
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
    _write_csv_new(packet_dir / "reviewer_declaration.csv", DECLARATION_FIELDS, [{}])
    _write_text_new(packet_dir / "README.md", _packet_readme())
    _write_text_new(
        packet_dir / "packet_manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return manifest


def _manifest_candidates(manifest: dict[str, Any]) -> dict[tuple[str, str], ReviewCandidate]:
    if manifest.get("schema_version") != 1 or manifest.get("mode") != "phase3_human_value_review_packet":
        raise Phase3ReviewError("packet manifest has an unsupported schema or mode")
    if manifest.get("production_connected") is not False:
        raise Phase3ReviewError("packet manifest must remain production-disconnected")
    if manifest.get("source_file_sha256") is None:
        raise Phase3ReviewError("packet manifest is missing source artifact identities")
    if manifest.get("case_contexts") != [
        {"case_id": case_id, **context} for case_id, context in FROZEN_CASES.items()
    ]:
        raise Phase3ReviewError("packet case contexts drifted from the preregistration")
    expected_thresholds = {
        "wrong_source_rate_max": WRONG_SOURCE_RATE_MAX,
        "novel_relevant_cases_min": NOVEL_RELEVANT_CASES_MIN,
        "case_count": len(FROZEN_CASES),
    }
    if manifest.get("thresholds") != expected_thresholds:
        raise Phase3ReviewError("packet thresholds drifted from the preregistration")
    if manifest.get("valid_label_pairs") != [list(pair) for pair in sorted(VALID_LABEL_PAIRS)]:
        raise Phase3ReviewError("packet label contract drifted from the preregistration")

    rows = manifest.get("rows")
    if not isinstance(rows, list) or len(rows) != 25 or manifest.get("row_count") != 25:
        raise Phase3ReviewError("packet manifest must contain exactly 25 rows")
    candidates: dict[tuple[str, str], ReviewCandidate] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise Phase3ReviewError("packet manifest rows must be objects")
        candidate = _candidate_from_row(row)
        if row.get("identity_sha256") != candidate.identity_sha256:
            raise Phase3ReviewError(f"packet identity hash drifted for {candidate.row_id}")
        key = (candidate.case_id, candidate.accepted_source_id)
        if key in candidates:
            raise Phase3ReviewError(f"packet manifest contains duplicate identity {candidate.row_id}")
        candidates[key] = candidate
    return candidates


def _validate_packet_provenance(
    packet_dir: Path,
    snapshot: SourceSnapshot,
) -> tuple[dict[str, Any], dict[tuple[str, str], ReviewCandidate]]:
    manifest_path = packet_dir / "packet_manifest.json"
    manifest = _read_json_object(manifest_path)
    if manifest.get("source_file_sha256") != snapshot.file_hashes:
        raise Phase3ReviewError("packet source hashes do not match the frozen source directory")
    manifest_candidates = _manifest_candidates(manifest)
    source_candidates = {
        (candidate.case_id, candidate.accepted_source_id): candidate
        for candidate in snapshot.candidates
    }
    if manifest_candidates != source_candidates:
        raise Phase3ReviewError("packet candidate identities do not match the frozen source artifacts")
    return manifest, manifest_candidates


def _validated_label(
    row: dict[str, str],
    expected: ReviewCandidate,
) -> dict[str, str] | None:
    observed = _candidate_from_row(row)
    if observed != expected:
        raise Phase3ReviewError(f"label identity drifted for {expected.row_id}")
    values = [row[field].strip() for field in ("relevant", "novel", "review_note")]
    if not any(values):
        return None
    if not all(values):
        raise Phase3ReviewError(f"{expected.row_id} is partially completed")
    relevant = values[0].upper()
    novel = values[1].upper()
    if (relevant, novel) not in VALID_LABEL_PAIRS:
        raise Phase3ReviewError(
            f"{expected.row_id} has invalid relevant/novel pair: {relevant}/{novel}"
        )
    note = values[2]
    if len("".join(note.split())) < 12:
        raise Phase3ReviewError(f"{expected.row_id} review_note is too short to ground the judgment")
    return {
        "case_id": expected.case_id,
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
        raise Phase3ReviewError(f"reviewer declaration is partially completed; missing={missing}")

    reviewed_all = row["reviewed_all"].strip().upper()
    if reviewed_all not in {"YES", "NO"}:
        raise Phase3ReviewError("reviewed_all must be YES or NO")
    ai_use = row["generative_ai_use"].strip().upper()
    if ai_use not in ALL_AI_USE:
        raise Phase3ReviewError(f"invalid generative_ai_use: {ai_use}")
    external = row["external_sources_checked"].strip().upper()
    if external not in {"ALL_ATTEMPTED", "SOME", "NONE"}:
        raise Phase3ReviewError(
            "external_sources_checked must be ALL_ATTEMPTED, SOME, or NONE"
        )
    try:
        elapsed = int(row["elapsed_minutes"].strip())
    except ValueError as exc:
        raise Phase3ReviewError("elapsed_minutes must be an integer") from exc
    if elapsed <= 0:
        raise Phase3ReviewError("elapsed_minutes must be positive")
    try:
        completed = date.fromisoformat(row["completed_date"].strip())
    except ValueError as exc:
        raise Phase3ReviewError("completed_date must use YYYY-MM-DD") from exc

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


def summarize_packet(
    source_dir: Path,
    packet_dir: Path,
    *,
    expected_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Validate returned labels before exposing either exploratory metric."""

    if not packet_dir.is_dir():
        raise Phase3ReviewError(f"packet directory does not exist: {packet_dir}")
    snapshot = validate_source_artifacts(source_dir, expected_hashes=expected_hashes)
    manifest, expected_candidates = _validate_packet_provenance(packet_dir, snapshot)

    label_rows = _read_csv(packet_dir / "labels.csv", REVIEW_FIELDS)
    observed_keys = [
        (row["case_id"].strip(), row["accepted_source_id"].strip()) for row in label_rows
    ]
    if len(observed_keys) != len(set(observed_keys)):
        raise Phase3ReviewError("labels contain duplicate case/source identities")
    if set(observed_keys) != set(expected_candidates):
        missing = sorted(set(expected_candidates) - set(observed_keys))
        extra = sorted(set(observed_keys) - set(expected_candidates))
        raise Phase3ReviewError(
            f"label identities do not match packet manifest; missing={missing}, extra={extra}"
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
        raise Phase3ReviewError("reviewer_declaration.csv must contain exactly one row")
    declaration = _validated_declaration(declaration_rows[0])

    ordered_completed = [completed[key] for key in sorted(completed)]
    observed_counts = None
    uninspectable_row_ids: list[str] = []
    if not incomplete_row_ids:
        relevant_counts = Counter(row["relevant"] for row in ordered_completed)
        novel_counts = Counter(row["novel"] for row in ordered_completed)
        uninspectable_row_ids = [
            row["row_id"] for row in ordered_completed if row["relevant"] == "UNVERIFIABLE"
        ]
        observed_counts = {
            "relevant": dict(sorted(relevant_counts.items())),
            "novel": dict(sorted(novel_counts.items())),
        }

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

    metrics = None
    threshold_results = {
        "wrong_source_rate": "not_evaluated",
        "novel_relevant_cases": "not_evaluated",
    }
    decision = "not_evaluated"
    remaining_blockers = ["human_value_thresholds", "planner_trigger_precision", "disabled_path_regression"]
    if protocol_status == "complete":
        wrong_source_count = sum(row["relevant"] == "NO" for row in ordered_completed)
        wrong_source_rate = wrong_source_count / len(ordered_completed)
        novel_case_ids = sorted(
            {
                row["case_id"]
                for row in ordered_completed
                if row["relevant"] == "YES" and row["novel"] == "YES"
            }
        )
        wrong_source_pass = wrong_source_rate <= WRONG_SOURCE_RATE_MAX
        novel_cases_pass = len(novel_case_ids) >= NOVEL_RELEVANT_CASES_MIN
        metrics = {
            "wrong_source_count": wrong_source_count,
            "wrong_source_rate": wrong_source_rate,
            "novel_relevant_case_ids": novel_case_ids,
            "novel_relevant_case_count": len(novel_case_ids),
        }
        threshold_results = {
            "wrong_source_rate": "pass" if wrong_source_pass else "fail",
            "novel_relevant_cases": "pass" if novel_cases_pass else "fail",
        }
        decision = "pass" if wrong_source_pass and novel_cases_pass else "fail"
        remaining_blockers = ["planner_trigger_precision", "disabled_path_regression"]
        if decision == "fail":
            remaining_blockers.insert(0, "human_value_thresholds")

    return {
        "schema_version": 1,
        "mode": "phase3_human_value_review_result",
        "source_file_sha256": snapshot.file_hashes,
        "packet_manifest_sha256": _file_sha256(packet_dir / "packet_manifest.json"),
        "protocol_status": protocol_status,
        "decision": decision,
        "row_count": len(expected_candidates),
        "completed_row_count": len(completed),
        "incomplete_row_ids": sorted(incomplete_row_ids),
        "uninspectable_row_ids": sorted(uninspectable_row_ids),
        "method_issues": method_issues,
        "reviewer_declaration": declaration,
        "observed_label_counts": observed_counts,
        "metrics": metrics,
        "thresholds": manifest["thresholds"],
        "threshold_results": threshold_results,
        "production_connection_authorized": False,
        "remaining_production_blockers": remaining_blockers,
        "measurement_limit": manifest.get("measurement_limit"),
    }


def write_summary(path: Path, result: dict[str, Any]) -> None:
    """Persist one result without replacing an earlier interpretation."""

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise Phase3ReviewError(f"could not create summary parent {path.parent}: {exc}") from exc
    _write_text_new(
        path,
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def _stdout_json(value: object) -> str:
    # Keep the same reversible projection as the live runner: a completed local
    # review must not look failed merely because the caller uses a legacy codec.
    return json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="create a separate blank human-review packet")
    prepare.add_argument("source", type=Path)
    prepare.add_argument("packet", type=Path)

    summarize = commands.add_parser("summarize", help="validate returned labels and write one result")
    summarize.add_argument("source", type=Path)
    summarize.add_argument("packet", type=Path)
    summarize.add_argument("output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "prepare":
        result = prepare_packet(args.source, args.packet)
    else:
        result = summarize_packet(args.source, args.packet)
        write_summary(args.output, result)
    print(_stdout_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
