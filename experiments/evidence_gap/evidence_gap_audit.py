"""Audit the phase-1 evidence-gap gate over frozen source collections.

The command is zero-network: it reads existing ``validated_sources.json``
files, refreshes coverage diagnostics on a copy for legacy fixtures, and
writes every gate decision. It never invokes a planner or a search adapter.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from academic_agent.evidence_gap import (
    EvidenceGapShadowAudit,
    parse_shadow_configuration,
    refresh_coverage_for_offline_audit,
    run_shadow_assessment,
    source_collection_sha256,
)
from academic_agent.source_pipeline import SourceCollection


CASE_FIELDS = (
    "fixture",
    "fixture_sha256",
    "topic",
    "academic_sources",
    "patent_sources",
    "market_sources",
    "authority_status",
    "component_status",
    "gate_state",
    "signal_count",
    "signal_codes",
    "signal_subjects",
    "executed_call_count",
    "evidence_changed",
)


class EvidenceGapAuditError(ValueError):
    """Raised when an audit would describe a partial or drifting fixture set."""


def discover_collections(fixtures: Path) -> list[Path]:
    """Return one-level benchmark collections, excluding nested test artifacts."""

    paths = sorted(fixtures.glob("*/validated_sources.json"))
    if not paths:
        raise EvidenceGapAuditError(
            f"no validated source collections found directly under {fixtures}"
        )
    return paths


def _read_collection(path: Path) -> tuple[SourceCollection, str]:
    try:
        payload = path.read_bytes()
        collection = SourceCollection.model_validate_json(payload)
    except (OSError, ValueError) as exc:
        raise EvidenceGapAuditError(f"could not load {path}: {exc}") from exc
    return collection, hashlib.sha256(payload).hexdigest()


def _case_row(
    fixtures: Path,
    path: Path,
    fixture_sha256: str,
    collection: SourceCollection,
    audit: EvidenceGapShadowAudit,
) -> dict[str, Any]:
    context = audit.context
    if context is None:
        raise EvidenceGapAuditError(f"enabled audit produced no context for {path}")
    return {
        "fixture": path.parent.relative_to(fixtures).as_posix(),
        "fixture_sha256": fixture_sha256,
        "topic": collection.topic,
        "academic_sources": context.source_counts["academic"],
        "patent_sources": context.source_counts["patent"],
        "market_sources": context.source_counts["market"],
        "authority_status": collection.authority_coverage.status,
        "component_status": collection.component_coverage.status,
        "gate_state": audit.gate_state,
        "signal_count": len(context.signals),
        "signal_codes": "|".join(signal.code for signal in context.signals),
        "signal_subjects": "|".join(signal.subject for signal in context.signals),
        "executed_call_count": audit.executed_call_count,
        "evidence_changed": audit.evidence_changed,
    }


def evaluate_collections(
    fixtures: Path,
    *,
    expected_count: int | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Run the frozen gate twice and prove its zero-call result is deterministic."""

    paths = discover_collections(fixtures)
    if expected_count is not None and len(paths) != expected_count:
        raise EvidenceGapAuditError(
            f"fixture count is {len(paths)}, expected exactly {expected_count}"
        )

    enabled = parse_shadow_configuration("true")
    rows: list[dict[str, Any]] = []
    deterministic = True
    input_mutation_count = 0
    fixture_manifest: list[dict[str, str]] = []
    for path in paths:
        original, fixture_sha256 = _read_collection(path)
        original_hash_before = source_collection_sha256(original)
        refreshed = refresh_coverage_for_offline_audit(original)
        first = run_shadow_assessment(refreshed, configuration=enabled)
        second = run_shadow_assessment(refreshed, configuration=enabled)
        deterministic = deterministic and first.model_dump() == second.model_dump()
        if source_collection_sha256(original) != original_hash_before:
            input_mutation_count += 1
        rows.append(_case_row(fixtures, path, fixture_sha256, refreshed, first))
        fixture_manifest.append(
            {
                "fixture": path.parent.relative_to(fixtures).as_posix(),
                "sha256": fixture_sha256,
            }
        )

    states = Counter(str(row["gate_state"]) for row in rows)
    signals = Counter(
        code
        for row in rows
        for code in str(row["signal_codes"]).split("|")
        if code
    )
    executed_calls = sum(int(row["executed_call_count"]) for row in rows)
    evidence_changes = sum(bool(row["evidence_changed"]) for row in rows)
    checks = [
        {
            "name": "loaded_expected_fixture_count",
            "passed": expected_count is None or len(rows) == expected_count,
            "observed": len(rows),
            "requirement": (
                "at least one" if expected_count is None else f"exactly {expected_count}"
            ),
        },
        {
            "name": "deterministic_repeat",
            "passed": deterministic,
            "observed": deterministic,
            "requirement": True,
        },
        {
            "name": "zero_tool_calls_executed",
            "passed": executed_calls == 0,
            "observed": executed_calls,
            "requirement": 0,
        },
        {
            "name": "zero_input_mutations",
            "passed": input_mutation_count == 0 and evidence_changes == 0,
            "observed": input_mutation_count + evidence_changes,
            "requirement": 0,
        },
        {
            "name": "every_fixture_checked",
            "passed": states["eligible"] + states["no_gap"] == len(rows),
            "observed": states["eligible"] + states["no_gap"],
            "requirement": len(rows),
        },
    ]
    result = {
        "schema_version": 1,
        "protocol": "evidence-gap-shadow-phase-1",
        "measurement_design": "retrospective_development_set_not_held_out",
        "fixture_count": len(rows),
        "gate_states": dict(sorted(states.items())),
        "signal_counts": dict(sorted(signals.items())),
        "executed_call_count": executed_calls,
        "input_mutation_count": input_mutation_count,
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
        "production_tool_calls_authorized": False,
        "fixture_manifest": fixture_manifest,
        "measurement_limit": (
            "The same stored collections informed gate development. This audit "
            "tests deterministic zero-call mechanics, not trigger precision or "
            "supplementary evidence value."
        ),
    }
    return result, rows


def write_audit(
    output: Path,
    result: dict[str, Any],
    rows: list[dict[str, Any]],
) -> None:
    """Write aggregate and case-level evidence without overwriting a prior audit."""

    if output.exists():
        raise EvidenceGapAuditError(f"refusing to overwrite audit output: {output}")
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
    parser.add_argument("fixtures", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-count", type=int, default=None)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    result, rows = evaluate_collections(
        args.fixtures,
        expected_count=args.expected_count,
    )
    write_audit(args.output, result, rows)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
