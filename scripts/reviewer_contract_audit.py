"""How the six-node reviewer met its correction-plan contract in an ablation experiment.

    uv run python scripts/reviewer_contract_audit.py outputs/ablation/<experiment-id>

Reads the full-arm cells' persisted metadata and plans only; makes no call.
For every reviewer attempt it reports whether the plan passed and, if not,
why: a `reason` over the schema's character bound, more corrections than the
prompt allows, a `find` that is not unique, or other. For accepted plans it
reports how long the reasons were and how many corrections they held.

The guardrail keeps the first 700 or so characters of a failure. The total
error count comes from the message header ("12 validation errors"); the
per-field detail is whatever fits, so a count of too-long reasons read from
it is a lower bound and is labelled so.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "src")]

CAUSES = ("reason_too_long", "too_many_corrections", "find_not_unique", "other")


def failure_cause(message: str) -> str:
    if "string_too_long" in message and re.search(r"corrections\.\d+\.reason", message):
        return "reason_too_long"
    if re.search(r"List should have at most \d+ items", message):
        return "too_many_corrections"
    if re.search(r"target occurs \d+ times", message):
        return "find_not_unique"
    return "other"


def _error_count(message: str) -> int | None:
    match = re.search(r"(\d+) validation errors? for", message)
    return int(match.group(1)) if match else None


def audit(experiment: Path) -> dict[str, Any]:
    from academic_agent.evidence import ReviewerCorrection

    bound = ReviewerCorrection.model_fields["reason"].metadata
    reason_max = next(item.max_length for item in bound if hasattr(item, "max_length"))

    runs = first = second = 0
    first_causes: Counter = Counter()
    second_causes: Counter = Counter()
    terminal_causes: Counter = Counter()
    too_long_in_first: list[int] = []
    errors_in_first: list[int | None] = []
    reason_lengths: list[int] = []
    plan_sizes: list[int] = []
    for path in sorted(experiment.glob("*/meta.json")):
        cell = json.loads(path.read_text(encoding="utf-8"))
        if cell.get("variant") != "full":
            continue
        runs += 1
        attempts = ((cell.get("guardrails") or {}).get("report_review_task") or {}).get("attempts") or []
        if attempts and not attempts[0].get("passed"):
            first += 1
            cause = failure_cause(attempts[0].get("failure", ""))
            first_causes[cause] += 1
            if cause == "reason_too_long":
                too_long_in_first.append(len(set(re.findall(r"corrections\.(\d+)\.reason", attempts[0]["failure"]))))
                errors_in_first.append(_error_count(attempts[0]["failure"]))
        if len(attempts) > 1 and not attempts[1].get("passed"):
            second += 1
            second_causes[failure_cause(attempts[1].get("failure", ""))] += 1
        if cell.get("status") != "success":
            terminal_causes[failure_cause(str(cell.get("error", "")))] += 1
        plan = path.parent / "reviewer_correction_plan.json"
        if plan.exists():
            corrections = json.loads(plan.read_text(encoding="utf-8")).get("corrections") or []
            plan_sizes.append(len(corrections))
            reason_lengths += [len(item.get("reason", "")) for item in corrections]

    ordered = sorted(reason_lengths)
    return {
        "experiment": experiment.name,
        "reason_max_chars": reason_max,
        "full_arm_runs": runs,
        "first_attempt_failures": first,
        "first_attempt_causes": {cause: first_causes[cause] for cause in CAUSES},
        "too_long_reasons_per_failed_first_attempt_lower_bound": too_long_in_first,
        "validation_errors_per_failed_first_attempt": errors_in_first,
        "second_attempt_failures": second,
        "second_attempt_causes": {cause: second_causes[cause] for cause in CAUSES},
        "terminal_failures": sum(terminal_causes.values()),
        "terminal_causes": {cause: terminal_causes[cause] for cause in CAUSES},
        "accepted_plans": len(plan_sizes),
        "accepted_corrections": len(reason_lengths),
        "accepted_corrections_per_plan": {"median": median(plan_sizes), "max": max(plan_sizes)} if plan_sizes else None,
        "accepted_reason_chars": {
            "median": median(ordered),
            "p90": ordered[int(0.9 * (len(ordered) - 1))],
            "max": ordered[-1],
            "share_at_least_250": round(sum(n >= 250 for n in ordered) / len(ordered), 3),
        } if ordered else None,
    }


def per_block(experiment: Path) -> dict[str, dict[str, bool]]:
    """Reviewer outcome of each six-node cell, keyed by topic/repetition block."""
    blocks = {}
    for path in sorted(experiment.glob("*/meta.json")):
        cell = json.loads(path.read_text(encoding="utf-8"))
        if cell.get("variant") != "full":
            continue
        attempts = ((cell.get("guardrails") or {}).get("report_review_task") or {}).get("attempts") or []
        first_failed = bool(attempts) and not attempts[0].get("passed")
        blocks[str(cell.get("block_id"))] = {
            "first_failed": first_failed,
            "first_failed_on_reason": first_failed and failure_cause(attempts[0].get("failure", "")) == "reason_too_long",
            "terminal": cell.get("status") != "success",
        }
    return blocks


def paired(baseline: Path, experiment: Path) -> dict[str, Any]:
    """Before/after transitions on the blocks both experiments ran."""
    before, after = per_block(baseline), per_block(experiment)
    common = sorted(set(before) & set(after))
    result: dict[str, Any] = {"blocks": len(common),
                              "only_in_baseline": sorted(set(before) - set(after)),
                              "only_in_experiment": sorted(set(after) - set(before))}
    for key in ("first_failed_on_reason", "first_failed", "terminal"):
        result[key] = {
            "before_only": sum(before[b][key] and not after[b][key] for b in common),
            "after_only": sum(after[b][key] and not before[b][key] for b in common),
            "both": sum(before[b][key] and after[b][key] for b in common),
            "neither": sum(not before[b][key] and not after[b][key] for b in common),
        }
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("experiment", type=Path)
    parser.add_argument("--baseline", type=Path, help="also pair each block with this earlier experiment")
    args = parser.parse_args(argv)
    report = audit(args.experiment)
    if args.baseline:
        report["paired_with_baseline"] = {"baseline": args.baseline.name, **paired(args.baseline, args.experiment)}
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
