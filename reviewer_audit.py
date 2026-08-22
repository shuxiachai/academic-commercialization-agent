"""Prepare and score a blinded human audit of Reviewer-edited reports.

The first topology ablation retained the Writer draft, the delivered report,
and a count of accepted Reviewer corrections.  It did not retain each
structured ``find``/``replace`` operation, so those historical runs support a
report-level A/B audit, not an exact correction-level audit.  This tool keeps
that distinction explicit and never treats an unfilled form as a tie or pass.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PAIR_LABELS = {"A", "B", "TIE", "UNCERTAIN"}
HARM_LABELS = {"A", "B", "NONE", "UNCERTAIN"}
REQUIRED_JUDGMENTS = (
    "preferred_version",
    "citation_support",
    "decision_usefulness",
    "harmful_version",
    "confidence",
)
FORM_FIELDS = ("sample_id", *REQUIRED_JUDGMENTS, "notes")


class AuditDataError(ValueError):
    """Raised when an audit would silently misrepresent missing evidence."""


@dataclass(frozen=True)
class ReviewCase:
    """One successful full-arm run with at least one accepted correction."""

    source_cell: str
    topic: str
    declared_corrections: int
    draft: str
    reviewed: str
    reviewer_cost_usd: float | None


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _without_reviewer_notes(report: str) -> str:
    """Remove deterministic notes that would reveal which side is reviewed."""

    return report.split("## Reviewer Notes", maxsplit=1)[0].rstrip()


def _reviewer_cost(meta: dict[str, Any]) -> float | None:
    agents = meta.get("usage", {}).get("agents", [])
    for agent in agents:
        if "quality reviewer" in str(agent.get("role", "")).lower():
            value = agent.get("cost_usd")
            return float(value) if value is not None else None
    return None


def discover_review_cases(experiment_dir: Path) -> list[ReviewCase]:
    """Read auditable historical pairs and fail loudly on missing artifacts."""

    cases: list[ReviewCase] = []
    for meta_path in sorted(experiment_dir.glob("*/meta.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        corrections = meta.get("reviewer_corrections")
        if (
            meta.get("variant") != "full"
            or meta.get("status") != "success"
            or not isinstance(corrections, int)
            or corrections <= 0
        ):
            continue

        draft_path = meta_path.parent / "draft_report.md"
        reviewed_path = meta_path.parent / "commercialization_report.md"
        missing = [path.name for path in (draft_path, reviewed_path) if not path.is_file()]
        if missing:
            raise AuditDataError(
                f"{meta_path.parent.name} declares {corrections} corrections but is missing "
                + ", ".join(missing)
            )

        draft = draft_path.read_text(encoding="utf-8").rstrip()
        reviewed = _without_reviewer_notes(reviewed_path.read_text(encoding="utf-8"))
        if draft == reviewed:
            raise AuditDataError(
                f"{meta_path.parent.name} declares corrections but the report bodies are equal"
            )
        cases.append(
            ReviewCase(
                source_cell=meta_path.parent.name,
                topic=str(meta.get("topic", "")),
                declared_corrections=corrections,
                draft=draft,
                reviewed=reviewed,
                reviewer_cost_usd=_reviewer_cost(meta),
            )
        )

    if not cases:
        raise AuditDataError("no successful full-arm runs with accepted corrections were found")
    return cases


def _assert_separate_key(packet_dir: Path, answer_key_path: Path) -> None:
    packet = packet_dir.resolve()
    key = answer_key_path.resolve()
    if key == packet or packet in key.parents:
        raise AuditDataError("the answer key must be outside the blinded packet directory")


def _write_form(path: Path, sample_ids: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FORM_FIELDS)
        writer.writeheader()
        for sample_id in sample_ids:
            writer.writerow({"sample_id": sample_id})


def _packet_readme(case_count: int) -> str:
    return f"""# Blinded Reviewer value audit

This packet contains {case_count} report pairs. A and B are randomly assigned;
neither filename indicates which report passed through the Reviewer.

Read both reports in each sample directory and complete `review_form.csv`:

- `preferred_version`, `citation_support`, `decision_usefulness`:
  `A`, `B`, `TIE`, or `UNCERTAIN`.
- `harmful_version`: `A`, `B`, `NONE`, or `UNCERTAIN`.
- `confidence`: integer 1-5.
- `notes`: concise evidence for the judgment.

Do not open the separately stored answer key until every row is complete. An
empty row means *not evaluated*, never a tie. The historical artifacts did not
retain the 34 exact patch-plan items, so the unit here is a complete report
pair. Do not report this as a correction-level audit.
"""


def prepare_packet(
    experiment_dir: Path,
    packet_dir: Path,
    answer_key_path: Path,
    *,
    seed: int,
) -> dict[str, Any]:
    """Create a deterministic, anonymized packet and a physically separate key."""

    _assert_separate_key(packet_dir, answer_key_path)
    if packet_dir.exists() or answer_key_path.exists():
        raise AuditDataError("packet and answer-key paths must not already exist")

    cases = discover_review_cases(experiment_dir)
    rng = random.Random(seed)
    rng.shuffle(cases)
    packet_dir.mkdir(parents=True)
    answer_key_path.parent.mkdir(parents=True, exist_ok=True)

    key_cases: list[dict[str, Any]] = []
    sample_ids: list[str] = []
    for index, case in enumerate(cases, start=1):
        sample_id = f"R{index:02d}"
        sample_ids.append(sample_id)
        reviewed_side = rng.choice(("A", "B"))
        reports = (
            {"A": case.reviewed, "B": case.draft}
            if reviewed_side == "A"
            else {"A": case.draft, "B": case.reviewed}
        )
        sample_dir = packet_dir / sample_id
        sample_dir.mkdir()
        for side, report in reports.items():
            (sample_dir / f"{side}.md").write_text(report + "\n", encoding="utf-8")

        key_cases.append(
            {
                "sample_id": sample_id,
                "source_cell": case.source_cell,
                "topic": case.topic,
                "reviewed_side": reviewed_side,
                "declared_corrections": case.declared_corrections,
                "reviewer_cost_usd": case.reviewer_cost_usd,
                "report_sha256": {side: _sha256(report) for side, report in reports.items()},
            }
        )

    declared_total = sum(case.declared_corrections for case in cases)
    manifest = {
        "schema_version": 1,
        "audit_unit": "report_pair",
        "case_count": len(cases),
        "declared_correction_count": declared_total,
        "review_status": "not_started",
        "blinding": "randomized A/B; answer key stored separately",
        "historical_limit": (
            "Exact find/replace plans were not persisted; correction-level claims are invalid."
        ),
    }
    (packet_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (packet_dir / "README.md").write_text(_packet_readme(len(cases)), encoding="utf-8")
    _write_form(packet_dir / "review_form.csv", sample_ids)

    answer_key = {
        "schema_version": 1,
        "seed": seed,
        "experiment_dir": experiment_dir.name,
        "cases": key_cases,
    }
    answer_key_path.write_text(
        json.dumps(answer_key, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def _normalize_label(value: str) -> str:
    return value.strip().upper()


def _validate_complete_row(row: dict[str, str]) -> bool:
    if any(not row.get(field, "").strip() for field in REQUIRED_JUDGMENTS):
        return False
    for field in ("preferred_version", "citation_support", "decision_usefulness"):
        if _normalize_label(row[field]) not in PAIR_LABELS:
            raise AuditDataError(f"{row['sample_id']} has invalid {field}: {row[field]}")
    if _normalize_label(row["harmful_version"]) not in HARM_LABELS:
        raise AuditDataError(
            f"{row['sample_id']} has invalid harmful_version: {row['harmful_version']}"
        )
    try:
        confidence = int(row["confidence"])
    except ValueError as exc:
        raise AuditDataError(f"{row['sample_id']} confidence must be an integer") from exc
    if confidence not in range(1, 6):
        raise AuditDataError(f"{row['sample_id']} confidence must be between 1 and 5")
    return True


def _relative_outcome(label: str, reviewed_side: str) -> str:
    normalized = _normalize_label(label)
    if normalized in {"TIE", "NONE", "UNCERTAIN"}:
        return normalized.lower()
    return "reviewed" if normalized == reviewed_side else "draft"


def summarize_form(form_path: Path, answer_key_path: Path) -> dict[str, Any]:
    """Unblind completed rows while preserving not-evaluated as a distinct state."""

    key = json.loads(answer_key_path.read_text(encoding="utf-8"))
    key_by_id = {case["sample_id"]: case for case in key["cases"]}
    with form_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    row_ids = [row.get("sample_id", "") for row in rows]
    if len(row_ids) != len(set(row_ids)) or set(row_ids) != set(key_by_id):
        raise AuditDataError("review form sample IDs do not match the answer key")

    counts = {
        metric: {label: 0 for label in ("reviewed", "draft", "tie", "uncertain")}
        for metric in ("preferred_version", "citation_support", "decision_usefulness")
    }
    harm = {label: 0 for label in ("reviewed", "draft", "none", "uncertain")}
    incomplete: list[str] = []
    completed: list[dict[str, Any]] = []
    for row in rows:
        sample_id = row["sample_id"]
        if not _validate_complete_row(row):
            incomplete.append(sample_id)
            continue
        reviewed_side = key_by_id[sample_id]["reviewed_side"]
        outcomes: dict[str, str] = {}
        for metric in counts:
            outcome = _relative_outcome(row[metric], reviewed_side)
            counts[metric][outcome] += 1
            outcomes[metric] = outcome
        harmful_outcome = _relative_outcome(row["harmful_version"], reviewed_side)
        harm[harmful_outcome] += 1
        completed.append(
            {
                "sample_id": sample_id,
                **outcomes,
                "harmful_version": harmful_outcome,
                "confidence": int(row["confidence"]),
            }
        )

    evaluable = not incomplete
    preferred = counts["preferred_version"]
    citation = counts["citation_support"]
    criterion_passed = (
        evaluable
        and preferred["reviewed"] >= 6
        and harm["reviewed"] <= 1
        and citation["draft"] <= 1
    )
    return {
        "schema_version": 1,
        "protocol_status": "complete" if evaluable else "incomplete",
        "case_count": len(rows),
        "completed_case_count": len(completed),
        "incomplete_sample_ids": incomplete,
        "outcomes": {**counts, "harmful_version": harm},
        "pre_registered_criterion_passed": criterion_passed if evaluable else None,
        "cases": completed,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="create a blinded review packet")
    prepare.add_argument("experiment_dir", type=Path)
    prepare.add_argument("packet_dir", type=Path)
    prepare.add_argument("answer_key", type=Path)
    prepare.add_argument("--seed", type=int, default=20260822)

    summarize = commands.add_parser("summarize", help="unblind a completed form")
    summarize.add_argument("review_form", type=Path)
    summarize.add_argument("answer_key", type=Path)
    summarize.add_argument("output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "prepare":
        result = prepare_packet(
            args.experiment_dir,
            args.packet_dir,
            args.answer_key,
            seed=args.seed,
        )
    else:
        result = summarize_form(args.review_form, args.answer_key)
        args.output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
