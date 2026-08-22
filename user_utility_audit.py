"""Prepare and summarize a blinded user-utility audit of report topology.

The topology ablation already paid for comparable one-node and six-stage
reports over identical frozen evidence.  This tool turns those artifacts into
small reviewer-specific packets without sending another model request.  It is
deliberately strict at the file boundary: an empty form is incomplete, an
unchecked citation is not a clean factual result, and the answer key must stay
outside every directory a reviewer may receive.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PAIR_LABELS = {"A", "B", "TIE", "UNCERTAIN"}
CITATION_LABELS = {*PAIR_LABELS, "NOT_CHECKED"}
DECISION_LABELS = {"GO", "NO_GO", "DEFER", "UNCERTAIN"}
CITATION_CHECK_LABELS = {"NONE", "SOME", "ALL"}
FACT_ERROR_LABELS = {"NOT_CHECKED", "0", "1", "2_PLUS"}
ROLE_LABELS = {"TARGET_USER", "DOMAIN_PROXY", "TECHNICAL_PROXY", "OTHER"}
AI_USE_LABELS = {"NONE", "TRANSLATION_OR_CLERICAL", "SUBSTANTIVE"}
PAIR_METRICS = (
    "overall_preference",
    "decision_usefulness",
    "information_gain",
    "actionability",
    "citation_trust",
)
PROFILE_FIELDS = (
    "reviewer_id",
    "role_category",
    "relevant_experience_years",
    "generative_ai_use",
    "generative_ai_notes",
)
FORM_FIELDS = (
    "reviewer_id",
    "round",
    "case_id",
    "topic",
    "initial_decision",
    "decision_after_a",
    "decision_after_b",
    *PAIR_METRICS,
    "recommendation_acceptance_a",
    "recommendation_acceptance_b",
    "reading_minutes_a",
    "reading_minutes_b",
    "revision_minutes_a",
    "revision_minutes_b",
    "citation_check",
    "factual_errors_a",
    "factual_errors_b",
    "confidence",
    "rationale",
)
RESPONSE_FIELDS = FORM_FIELDS[4:]


class UtilityAuditError(ValueError):
    """Raised when an audit artifact would misstate its human evidence."""


@dataclass(frozen=True)
class VariantReport:
    """One successful historical report and the identity hidden from reviewers."""

    source_cell: str
    variant: str
    topic_num: str
    topic: str
    repetition: int
    fixture_digest: str
    body: str
    source_sha256: str
    blinded_body_sha256: str


@dataclass(frozen=True)
class UtilityCase:
    """The earliest comparable monolith/full pair for one benchmark topic."""

    topic_num: str
    topic: str
    repetition: int
    fixture_digest: str
    monolith: VariantReport
    full: VariantReport


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _without_reviewer_notes(report: str) -> str:
    """Remove the deterministic appendix that would reveal the full workflow."""

    return report.split("\n## Reviewer Notes", maxsplit=1)[0].rstrip()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise UtilityAuditError(f"{path} must contain a JSON object")
    return value


def _load_variant(meta_path: Path, meta: dict[str, Any]) -> VariantReport:
    report_path = meta_path.parent / "commercialization_report.md"
    if not report_path.is_file():
        raise UtilityAuditError(f"successful cell {meta_path.parent.name} is missing commercialization_report.md")
    source = report_path.read_text(encoding="utf-8").rstrip()
    body = _without_reviewer_notes(source)
    if not body:
        raise UtilityAuditError(f"{meta_path.parent.name} has an empty report body")

    try:
        repetition = int(meta["rep"])
    except (KeyError, TypeError, ValueError) as exc:
        raise UtilityAuditError(f"{meta_path} has no valid repetition") from exc

    topic_num = str(meta.get("num", "")).strip()
    topic = str(meta.get("topic", "")).strip()
    fixture_digest = str(meta.get("fixture_digest", "")).strip()
    variant = str(meta.get("variant", "")).strip()
    if not topic_num or not topic or not fixture_digest:
        raise UtilityAuditError(f"{meta_path} is missing topic or fixture identity")
    return VariantReport(
        source_cell=meta_path.parent.name,
        variant=variant,
        topic_num=topic_num,
        topic=topic,
        repetition=repetition,
        fixture_digest=fixture_digest,
        body=body,
        source_sha256=_sha256(source),
        blinded_body_sha256=_sha256(body),
    )


def discover_cases(experiment_dir: Path, *, expected_case_count: int = 10) -> list[UtilityCase]:
    """Select the earliest successful matched pair for every topic.

    A digest mismatch is an error rather than a reason to skip to a later
    repetition.  Silently doing so would select on a broken comparison boundary
    after seeing which cell happened to be convenient.
    """

    cells: dict[tuple[str, int, str], VariantReport] = {}
    topic_nums: set[str] = set()
    for meta_path in sorted(experiment_dir.glob("*/meta.json")):
        meta = _read_json(meta_path)
        variant = str(meta.get("variant", ""))
        if variant not in {"monolith", "full"}:
            continue
        topic_num = str(meta.get("num", "")).strip()
        if topic_num:
            topic_nums.add(topic_num)
        if meta.get("status") != "success":
            continue
        report = _load_variant(meta_path, meta)
        key = (report.topic_num, report.repetition, report.variant)
        if key in cells:
            raise UtilityAuditError(f"duplicate successful ablation cell: {key}")
        cells[key] = report

    if len(topic_nums) != expected_case_count:
        raise UtilityAuditError(f"expected {expected_case_count} topics, found {len(topic_nums)}")

    cases: list[UtilityCase] = []
    for topic_num in sorted(topic_nums):
        repetitions = sorted(
            {repetition for num, repetition, variant in cells if num == topic_num and variant == "monolith"}
            & {repetition for num, repetition, variant in cells if num == topic_num and variant == "full"}
        )
        if not repetitions:
            raise UtilityAuditError(f"topic {topic_num} has no successful matched pair")
        repetition = repetitions[0]
        monolith = cells[(topic_num, repetition, "monolith")]
        full = cells[(topic_num, repetition, "full")]
        if monolith.topic != full.topic:
            raise UtilityAuditError(f"topic {topic_num} pair disagrees on topic text at repetition {repetition}")
        if monolith.fixture_digest != full.fixture_digest:
            raise UtilityAuditError(f"topic {topic_num} pair has mismatched fixture digests at repetition {repetition}")
        if monolith.body == full.body:
            raise UtilityAuditError(f"topic {topic_num} pair has identical report bodies")
        cases.append(
            UtilityCase(
                topic_num=topic_num,
                topic=monolith.topic,
                repetition=repetition,
                fixture_digest=monolith.fixture_digest,
                monolith=monolith,
                full=full,
            )
        )
    return cases


def _assert_key_outside_packet(packet_dir: Path, answer_key_path: Path) -> None:
    packet = packet_dir.resolve()
    key = answer_key_path.resolve()
    if key == packet or packet in key.parents:
        raise UtilityAuditError("the answer key must be outside the blinded packet directory")


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _coordinator_readme(reviewer_count: int) -> str:
    return f"""# User-utility blind review — coordinator copy

This packet was generated for {reviewer_count} reviewer slots. Do not send this
whole directory to a reviewer. Send only that person's directory from
`round-1/`, then the matching `round-2/` directory only if they agree to the
optional replication round.

The answer key is intentionally stored somewhere else. Keep it closed until
all forms included in an analysis have been returned and locked. Round 1 is the
primary ten-topic result. Round 2 cannot replace or rescue it.

If a reviewer withdraws, leave their rows blank. Do not copy another person's
judgment, fill a blank as `TIE`, or reduce the denominator. Regenerate a new
packet before anyone starts if the reviewer count changes.
"""


def _reviewer_readme(reviewer_id: str, round_num: int, case_count: int) -> str:
    profile_note = "先填写 `reviewer_profile.csv`。" if round_num == 1 else "个人背景只在第一轮填写；本轮无需重复填写。"
    return f"""# 商业化报告用户效用盲评

评审编号：`{reviewer_id}`
轮次：第 {round_num} 轮
本轮报告对数：{case_count}

{profile_note}

每个 `cases/<case_id>/` 目录包含同一研究主题的 `A.md` 与 `B.md`。文件名不
表示来源或优劣。请不要猜测系统架构，也不要在全部表格提交前向其他评审者
讨论内容。

对每一行：

1. 只看 `topic`，先填写 `initial_decision`；
2. 阅读 A 后填写 `decision_after_a`，再阅读 B 并填写 `decision_after_b`；
3. 完成其余比较项、时间估计、引用检查和简短理由；
4. 允许值请严格使用表头约定的英文大写枚举。

决策：`GO / NO_GO / DEFER / UNCERTAIN`。比较项：
`A / B / TIE / UNCERTAIN`；未打开引用时，`citation_trust`、
`factual_errors_a` 和 `factual_errors_b` 必须写 `NOT_CHECKED`，不能写 0。
引用检查为 `NONE / SOME / ALL`。事实错误为
`NOT_CHECKED / 0 / 1 / 2_PLUS`。接受度和信心为 1–5 分。

请不要用生成式 AI 代替你的实质判断。翻译或纯格式帮助必须在个人背景表中
披露；若 AI 直接生成判断，该评审会保留归档但不进入主要人类结果。空白表示
未评审，不会被当成平局或通过。
"""


def _assignment_plan(
    cases: list[tuple[str, UtilityCase]], reviewer_count: int
) -> dict[int, list[tuple[str, str, UtilityCase]]]:
    """Assign each case once per round and rotate its second reviewer."""

    reviewers = [f"R{index:02d}" for index in range(1, reviewer_count + 1)]
    round_one: list[tuple[str, str, UtilityCase]] = []
    round_two: list[tuple[str, str, UtilityCase]] = []
    for index, (case_id, case) in enumerate(cases):
        first_index = index % reviewer_count
        round_one.append((reviewers[first_index], case_id, case))
        round_two.append((reviewers[(first_index + 1) % reviewer_count], case_id, case))
    return {1: round_one, 2: round_two}


def prepare_packet(
    experiment_dir: Path,
    packet_dir: Path,
    answer_key_path: Path,
    *,
    reviewer_count: int,
    seed: int,
) -> dict[str, Any]:
    """Create deterministic reviewer packets and a physically separate key."""

    if reviewer_count not in range(3, 6):
        raise UtilityAuditError("reviewer_count must be between 3 and 5")
    _assert_key_outside_packet(packet_dir, answer_key_path)
    if packet_dir.exists() or answer_key_path.exists():
        raise UtilityAuditError("packet and answer-key paths must not already exist")

    cases = discover_cases(experiment_dir)
    rng = random.Random(seed)
    shuffled = list(cases)
    rng.shuffle(shuffled)
    identified = [(f"U{index:02d}", case) for index, case in enumerate(shuffled, start=1)]
    plan = _assignment_plan(identified, reviewer_count)

    packet_dir.mkdir(parents=True)
    answer_key_path.parent.mkdir(parents=True, exist_ok=True)
    (packet_dir / "README.md").write_text(_coordinator_readme(reviewer_count), encoding="utf-8")

    key_cases: list[dict[str, Any]] = []
    for case_id, case in identified:
        key_cases.append(
            {
                "case_id": case_id,
                "topic_num": case.topic_num,
                "topic": case.topic,
                "repetition": case.repetition,
                "fixture_digest": case.fixture_digest,
                "source_reports": {
                    "monolith": {
                        "source_cell": case.monolith.source_cell,
                        "source_sha256": case.monolith.source_sha256,
                        "blinded_body_sha256": case.monolith.blinded_body_sha256,
                        "word_count": len(case.monolith.body.split()),
                    },
                    "full": {
                        "source_cell": case.full.source_cell,
                        "source_sha256": case.full.source_sha256,
                        "blinded_body_sha256": case.full.blinded_body_sha256,
                        "word_count": len(case.full.body.split()),
                    },
                },
            }
        )

    key_assignments: list[dict[str, Any]] = []
    blinded_rounds: dict[str, Any] = {}
    for round_num, assignments in plan.items():
        by_reviewer: dict[str, list[tuple[str, UtilityCase]]] = {
            f"R{index:02d}": [] for index in range(1, reviewer_count + 1)
        }
        for reviewer_id, case_id, case in assignments:
            by_reviewer[reviewer_id].append((case_id, case))

        blinded_rounds[str(round_num)] = {
            "assignment_count": len(assignments),
            "reviewer_loads": {reviewer_id: len(reviewer_cases) for reviewer_id, reviewer_cases in by_reviewer.items()},
        }
        for reviewer_id, reviewer_cases in by_reviewer.items():
            reviewer_dir = packet_dir / f"round-{round_num}" / reviewer_id
            cases_dir = reviewer_dir / "cases"
            cases_dir.mkdir(parents=True)
            (reviewer_dir / "README.md").write_text(
                _reviewer_readme(reviewer_id, round_num, len(reviewer_cases)),
                encoding="utf-8",
            )
            if round_num == 1:
                _write_csv(
                    reviewer_dir / "reviewer_profile.csv",
                    PROFILE_FIELDS,
                    [{"reviewer_id": reviewer_id}],
                )

            form_rows: list[dict[str, Any]] = []
            for case_id, case in reviewer_cases:
                full_side = rng.choice(("A", "B"))
                reports = (
                    {"A": case.full.body, "B": case.monolith.body}
                    if full_side == "A"
                    else {"A": case.monolith.body, "B": case.full.body}
                )
                case_dir = cases_dir / case_id
                case_dir.mkdir()
                for side, report in reports.items():
                    (case_dir / f"{side}.md").write_text(report + "\n", encoding="utf-8")
                form_rows.append(
                    {
                        "reviewer_id": reviewer_id,
                        "round": round_num,
                        "case_id": case_id,
                        "topic": case.topic,
                    }
                )
                key_assignments.append(
                    {
                        "reviewer_id": reviewer_id,
                        "round": round_num,
                        "case_id": case_id,
                        "topic": case.topic,
                        "full_side": full_side,
                        "report_sha256": {side: _sha256(report) for side, report in reports.items()},
                    }
                )
            _write_csv(reviewer_dir / "review_form.csv", FORM_FIELDS, form_rows)

    manifest = {
        "schema_version": 1,
        "audit_unit": "report_pair_judgment",
        "case_count": len(cases),
        "reviewer_count": reviewer_count,
        "round_1_role": "primary",
        "round_2_role": "optional_replication",
        "review_status": "not_started",
        "blinding": "randomized A/B identity; treatment key stored outside packet",
        "rounds": blinded_rounds,
    }
    (packet_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    answer_key = {
        "schema_version": 1,
        "seed": seed,
        "experiment_dir": experiment_dir.name,
        "reviewer_count": reviewer_count,
        "cases": key_cases,
        "assignments": key_assignments,
    }
    answer_key_path.write_text(json.dumps(answer_key, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return manifest


def _read_csv(path: Path, expected_fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != expected_fields:
            raise UtilityAuditError(f"{path} columns do not match the frozen form")
        return list(reader)


def _normalize(value: str) -> str:
    return value.strip().upper()


def _parse_int(value: str, *, field: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise UtilityAuditError(f"{field} must be an integer") from exc
    if parsed not in range(minimum, maximum + 1):
        raise UtilityAuditError(f"{field} must be between {minimum} and {maximum}")
    return parsed


def _validate_profile(row: dict[str, str], reviewer_id: str) -> dict[str, Any] | None:
    if row.get("reviewer_id", "").strip() != reviewer_id:
        raise UtilityAuditError(f"{reviewer_id} profile has a changed reviewer_id")
    response = [row.get(field, "").strip() for field in PROFILE_FIELDS[1:4]]
    if not any(response):
        return None
    if not all(response):
        raise UtilityAuditError(f"{reviewer_id} profile is partially completed")
    role = _normalize(row["role_category"])
    ai_use = _normalize(row["generative_ai_use"])
    if role not in ROLE_LABELS:
        raise UtilityAuditError(f"{reviewer_id} has invalid role_category")
    if ai_use not in AI_USE_LABELS:
        raise UtilityAuditError(f"{reviewer_id} has invalid generative_ai_use")
    experience = _parse_int(
        row["relevant_experience_years"],
        field=f"{reviewer_id} relevant_experience_years",
        minimum=0,
        maximum=60,
    )
    notes = row.get("generative_ai_notes", "").strip()
    if ai_use != "NONE" and not notes:
        raise UtilityAuditError(f"{reviewer_id} must describe non-NONE generative AI use")
    return {
        "reviewer_id": reviewer_id,
        "role_category": role,
        "relevant_experience_years": experience,
        "generative_ai_use": ai_use,
        "generative_ai_notes": notes,
    }


def _validate_form_row(row: dict[str, str], assignment: dict[str, Any]) -> dict[str, Any] | None:
    identity = {
        "reviewer_id": assignment["reviewer_id"],
        "round": str(assignment["round"]),
        "case_id": assignment["case_id"],
        "topic": assignment["topic"],
    }
    for field, expected in identity.items():
        if row.get(field, "").strip() != str(expected):
            raise UtilityAuditError(f"{assignment['reviewer_id']} {assignment['case_id']} changed {field}")

    values = [row.get(field, "").strip() for field in RESPONSE_FIELDS]
    if not any(values):
        return None
    if not all(values):
        raise UtilityAuditError(f"{assignment['reviewer_id']} {assignment['case_id']} is partially completed")

    for field in ("initial_decision", "decision_after_a", "decision_after_b"):
        if _normalize(row[field]) not in DECISION_LABELS:
            raise UtilityAuditError(f"{assignment['reviewer_id']} {assignment['case_id']} has invalid {field}")
    for field in PAIR_METRICS[:-1]:
        if _normalize(row[field]) not in PAIR_LABELS:
            raise UtilityAuditError(f"{assignment['reviewer_id']} {assignment['case_id']} has invalid {field}")
    if _normalize(row["citation_trust"]) not in CITATION_LABELS:
        raise UtilityAuditError(f"{assignment['reviewer_id']} {assignment['case_id']} has invalid citation_trust")

    numeric: dict[str, int] = {}
    for field in ("recommendation_acceptance_a", "recommendation_acceptance_b", "confidence"):
        numeric[field] = _parse_int(row[field], field=f"{assignment['case_id']} {field}", minimum=1, maximum=5)
    for field in ("reading_minutes_a", "reading_minutes_b"):
        numeric[field] = _parse_int(row[field], field=f"{assignment['case_id']} {field}", minimum=1, maximum=240)
    for field in ("revision_minutes_a", "revision_minutes_b"):
        numeric[field] = _parse_int(row[field], field=f"{assignment['case_id']} {field}", minimum=0, maximum=480)

    citation_check = _normalize(row["citation_check"])
    factual_a = _normalize(row["factual_errors_a"])
    factual_b = _normalize(row["factual_errors_b"])
    if citation_check not in CITATION_CHECK_LABELS:
        raise UtilityAuditError(f"{assignment['case_id']} has invalid citation_check")
    if factual_a not in FACT_ERROR_LABELS or factual_b not in FACT_ERROR_LABELS:
        raise UtilityAuditError(f"{assignment['case_id']} has invalid factual error label")
    if citation_check == "NONE" and (
        _normalize(row["citation_trust"]) != "NOT_CHECKED" or factual_a != "NOT_CHECKED" or factual_b != "NOT_CHECKED"
    ):
        raise UtilityAuditError(f"{assignment['case_id']} cannot report citation trust or zero errors without checking")
    rationale = row["rationale"].strip()
    if len(rationale) < 20:
        raise UtilityAuditError(f"{assignment['case_id']} rationale must be at least 20 characters")

    return {
        **identity,
        "initial_decision": _normalize(row["initial_decision"]),
        "decision_after_a": _normalize(row["decision_after_a"]),
        "decision_after_b": _normalize(row["decision_after_b"]),
        **{field: _normalize(row[field]) for field in PAIR_METRICS},
        **numeric,
        "citation_check": citation_check,
        "factual_errors_a": factual_a,
        "factual_errors_b": factual_b,
        "rationale": rationale,
    }


def _relative(label: str, full_side: str) -> str:
    if label in {"TIE", "UNCERTAIN", "NOT_CHECKED"}:
        return label.lower()
    return "full" if label == full_side else "monolith"


def _empty_metric_counts() -> dict[str, int]:
    return {label: 0 for label in ("full", "monolith", "tie", "uncertain", "not_checked")}


def _median(values: list[int]) -> float | None:
    return float(statistics.median(values)) if values else None


def _verify_packet(packet_dir: Path, key: dict[str, Any]) -> None:
    manifest = _read_json(packet_dir / "manifest.json")
    reviewer_count = key.get("reviewer_count")
    cases = key.get("cases", [])
    assignments = key.get("assignments", [])
    if not isinstance(reviewer_count, int) or reviewer_count not in range(3, 6):
        raise UtilityAuditError("answer key has an invalid reviewer count")
    if manifest.get("reviewer_count") != reviewer_count:
        raise UtilityAuditError("packet manifest and answer key disagree on reviewer count")
    if manifest.get("case_count") != len(cases):
        raise UtilityAuditError("packet manifest and answer key disagree on case count")

    if not isinstance(cases, list) or not isinstance(assignments, list):
        raise UtilityAuditError("answer key cases and assignments must be lists")
    case_ids = [item.get("case_id") for item in cases if isinstance(item, dict)]
    if len(case_ids) != len(cases) or len(case_ids) != len(set(case_ids)):
        raise UtilityAuditError("answer key has duplicate or malformed case identities")
    expected_reviewers = {f"R{index:02d}" for index in range(1, reviewer_count + 1)}
    expected_pairs = {(round_num, case_id) for round_num in (1, 2) for case_id in case_ids}
    observed_pairs: set[tuple[int, str]] = set()
    reviewers_by_case: dict[str, set[str]] = {case_id: set() for case_id in case_ids}
    reviewer_loads = {round_num: {reviewer_id: 0 for reviewer_id in expected_reviewers} for round_num in (1, 2)}

    for assignment in assignments:
        if not isinstance(assignment, dict):
            raise UtilityAuditError("answer key contains a malformed assignment")
        round_num = assignment.get("round")
        case_id = assignment.get("case_id")
        reviewer_id = assignment.get("reviewer_id")
        if round_num not in (1, 2) or case_id not in case_ids:
            raise UtilityAuditError("answer key contains an unknown round or case")
        if reviewer_id not in expected_reviewers:
            raise UtilityAuditError("answer key contains an unknown reviewer")
        pair = (round_num, case_id)
        if pair in observed_pairs:
            raise UtilityAuditError(f"duplicate assignment for round {round_num} {case_id}")
        observed_pairs.add(pair)
        reviewers_by_case[case_id].add(reviewer_id)
        reviewer_loads[round_num][reviewer_id] += 1
        if assignment.get("full_side") not in {"A", "B"}:
            raise UtilityAuditError(f"{reviewer_id} {case_id} has an invalid answer key")
        report_hashes = assignment.get("report_sha256")
        if not isinstance(report_hashes, dict) or set(report_hashes) != {"A", "B"}:
            raise UtilityAuditError(f"{reviewer_id} {case_id} has invalid report hashes")

    if observed_pairs != expected_pairs:
        raise UtilityAuditError("answer key does not assign every case exactly once per round")
    if any(len(reviewers) != 2 for reviewers in reviewers_by_case.values()):
        raise UtilityAuditError("a case was assigned to the same reviewer in both rounds")
    for round_num, loads in reviewer_loads.items():
        if max(loads.values()) - min(loads.values()) > 1:
            raise UtilityAuditError(f"round {round_num} reviewer loads are not balanced")
        declared = manifest.get("rounds", {}).get(str(round_num), {})
        if declared.get("assignment_count") != len(case_ids):
            raise UtilityAuditError(f"round {round_num} manifest count is incorrect")
        if declared.get("reviewer_loads") != loads:
            raise UtilityAuditError(f"round {round_num} manifest loads are incorrect")
    for assignment in assignments:
        base = packet_dir / f"round-{assignment['round']}" / assignment["reviewer_id"] / "cases" / assignment["case_id"]
        for side in ("A", "B"):
            path = base / f"{side}.md"
            if not path.is_file():
                raise UtilityAuditError(f"missing blinded report: {path}")
            body = path.read_text(encoding="utf-8").rstrip()
            if _sha256(body) != assignment["report_sha256"][side]:
                raise UtilityAuditError(f"blinded report drifted after packet creation: {path}")


def _summarize_round(
    round_num: int,
    assignments: list[dict[str, Any]],
    completed: list[dict[str, Any]],
    incomplete_ids: list[str],
    missing_profile_reviewers: set[str],
    substantive_ai_reviewers: set[str],
) -> dict[str, Any]:
    metric_counts = {metric: _empty_metric_counts() for metric in PAIR_METRICS}
    numeric = {
        name: {"full": [], "monolith": []}
        for name in ("recommendation_acceptance", "reading_minutes", "revision_minutes")
    }
    factual = {variant: {label: 0 for label in FACT_ERROR_LABELS} for variant in ("full", "monolith")}
    citation_checks = {label.lower(): 0 for label in CITATION_CHECK_LABELS}
    decision_changes = {variant: {"changed": 0, "unchanged": 0} for variant in ("full", "monolith")}
    cases: list[dict[str, Any]] = []
    excluded_ids: list[str] = []
    eligible_reviewers: set[str] = set()
    assignment_by_id = {(item["reviewer_id"], item["case_id"]): item for item in assignments}

    for row in completed:
        assignment = assignment_by_id[(row["reviewer_id"], row["case_id"])]
        reviewer_id = row["reviewer_id"]
        if reviewer_id in missing_profile_reviewers or reviewer_id in substantive_ai_reviewers:
            excluded_ids.append(f"{reviewer_id}:{row['case_id']}")
            continue
        eligible_reviewers.add(reviewer_id)
        full_side = assignment["full_side"]
        outcomes = {metric: _relative(row[metric], full_side) for metric in PAIR_METRICS}
        for metric, outcome in outcomes.items():
            metric_counts[metric][outcome] += 1

        for stem in ("recommendation_acceptance", "reading_minutes", "revision_minutes"):
            full_key = f"{stem}_{full_side.lower()}"
            other_side = "B" if full_side == "A" else "A"
            mono_key = f"{stem}_{other_side.lower()}"
            numeric[stem]["full"].append(row[full_key])
            numeric[stem]["monolith"].append(row[mono_key])

        full_fact = row[f"factual_errors_{full_side.lower()}"]
        other_side = "B" if full_side == "A" else "A"
        mono_fact = row[f"factual_errors_{other_side.lower()}"]
        factual["full"][full_fact] += 1
        factual["monolith"][mono_fact] += 1
        citation_checks[row["citation_check"].lower()] += 1

        full_decision = row[f"decision_after_{full_side.lower()}"]
        mono_decision = row[f"decision_after_{other_side.lower()}"]
        for variant, decision in (("full", full_decision), ("monolith", mono_decision)):
            change = "changed" if decision != row["initial_decision"] else "unchanged"
            decision_changes[variant][change] += 1
        cases.append(
            {
                "reviewer_id": reviewer_id,
                "case_id": row["case_id"],
                "topic": assignment["topic"],
                "full_side": full_side,
                "outcomes": outcomes,
                "citation_check": row["citation_check"],
                "confidence": row["confidence"],
            }
        )

    expected_count = len(assignments)
    raw_completed = len(completed)
    if raw_completed == 0:
        status = "not_started"
    elif incomplete_ids:
        status = "incomplete"
    elif missing_profile_reviewers:
        status = "incomplete_profile"
    elif substantive_ai_reviewers:
        status = "ai_excluded"
    elif len(eligible_reviewers) < 3:
        status = "pilot_only"
    else:
        status = "complete"

    usefulness = metric_counts["decision_usefulness"]
    non_uncertain = expected_count - usefulness["uncertain"]
    criterion = usefulness["full"] >= 6 and usefulness["monolith"] <= 2 and non_uncertain >= 8
    return {
        "round": round_num,
        "role": "primary" if round_num == 1 else "optional_replication",
        "protocol_status": status,
        "expected_assignment_count": expected_count,
        "raw_completed_count": raw_completed,
        "eligible_completed_count": len(cases),
        "eligible_reviewer_count": len(eligible_reviewers),
        "incomplete_assignment_ids": incomplete_ids,
        "excluded_assignment_ids": excluded_ids,
        "outcomes": metric_counts,
        "numeric_medians": {
            stem: {variant: _median(values) for variant, values in by_variant.items()}
            for stem, by_variant in numeric.items()
        },
        "factual_error_observations": factual,
        "citation_check_coverage": citation_checks,
        "decision_changes": decision_changes,
        "pre_registered_criterion_passed": criterion if status == "complete" else None,
        "cases": cases,
    }


def summarize_packet(packet_dir: Path, answer_key_path: Path) -> dict[str, Any]:
    """Verify, unblind, and summarize returned forms without shrinking denominators."""

    key = _read_json(answer_key_path)
    _verify_packet(packet_dir, key)
    reviewer_count = int(key["reviewer_count"])
    reviewer_ids = [f"R{index:02d}" for index in range(1, reviewer_count + 1)]

    profiles: dict[str, dict[str, Any] | None] = {}
    for reviewer_id in reviewer_ids:
        path = packet_dir / "round-1" / reviewer_id / "reviewer_profile.csv"
        rows = _read_csv(path, PROFILE_FIELDS)
        if len(rows) != 1:
            raise UtilityAuditError(f"{reviewer_id} profile must contain exactly one row")
        profiles[reviewer_id] = _validate_profile(rows[0], reviewer_id)

    missing_profile_reviewers = {reviewer_id for reviewer_id, profile in profiles.items() if profile is None}
    substantive_ai_reviewers = {
        reviewer_id
        for reviewer_id, profile in profiles.items()
        if profile is not None and profile["generative_ai_use"] == "SUBSTANTIVE"
    }
    assignments = key.get("assignments", [])
    summaries: list[dict[str, Any]] = []
    for round_num in (1, 2):
        round_assignments = [item for item in assignments if item["round"] == round_num]
        completed: list[dict[str, Any]] = []
        incomplete: list[str] = []
        for reviewer_id in reviewer_ids:
            expected = [item for item in round_assignments if item["reviewer_id"] == reviewer_id]
            path = packet_dir / f"round-{round_num}" / reviewer_id / "review_form.csv"
            rows = _read_csv(path, FORM_FIELDS)
            row_ids = [row.get("case_id", "") for row in rows]
            expected_ids = [item["case_id"] for item in expected]
            if len(row_ids) != len(set(row_ids)) or set(row_ids) != set(expected_ids):
                raise UtilityAuditError(f"{reviewer_id} round {round_num} form does not match assignments")
            row_by_id = {row["case_id"]: row for row in rows}
            for assignment in expected:
                value = _validate_form_row(row_by_id[assignment["case_id"]], assignment)
                if value is None:
                    incomplete.append(f"{reviewer_id}:{assignment['case_id']}")
                else:
                    completed.append(value)
        summaries.append(
            _summarize_round(
                round_num,
                round_assignments,
                completed,
                incomplete,
                missing_profile_reviewers,
                substantive_ai_reviewers,
            )
        )

    role_mix = {label.lower(): 0 for label in ROLE_LABELS}
    ai_use = {label.lower(): 0 for label in AI_USE_LABELS}
    for profile in profiles.values():
        if profile is None:
            continue
        role_mix[profile["role_category"].lower()] += 1
        ai_use[profile["generative_ai_use"].lower()] += 1
    return {
        "schema_version": 1,
        "protocol_status": summaries[0]["protocol_status"],
        "reviewer_count": reviewer_count,
        "completed_profile_count": reviewer_count - len(missing_profile_reviewers),
        "missing_profile_reviewers": sorted(missing_profile_reviewers),
        "substantive_ai_reviewers": sorted(substantive_ai_reviewers),
        "role_mix": role_mix,
        "generative_ai_use": ai_use,
        "primary_criterion_passed": summaries[0]["pre_registered_criterion_passed"],
        "rounds": summaries,
        "interpretation": (
            "Small proxy-user comparison of full versus monolith reports on identical frozen "
            "evidence; not adoption, ROI, decision accuracy, or ordinary-ChatGPT superiority."
        ),
    }


def write_summary(output_path: Path, result: dict[str, Any]) -> None:
    """Persist one immutable summary so a later run cannot replace the denominator."""

    if output_path.exists():
        raise UtilityAuditError(f"refusing to overwrite existing summary: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="create blinded reviewer packets")
    prepare.add_argument("experiment_dir", type=Path)
    prepare.add_argument("packet_dir", type=Path)
    prepare.add_argument("answer_key", type=Path)
    prepare.add_argument("--reviewers", type=int, required=True, choices=range(3, 6))
    prepare.add_argument("--seed", type=int, default=20260822)

    summarize = commands.add_parser("summarize", help="verify and unblind returned forms")
    summarize.add_argument("packet_dir", type=Path)
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
            reviewer_count=args.reviewers,
            seed=args.seed,
        )
    else:
        result = summarize_packet(args.packet_dir, args.answer_key)
        write_summary(args.output, result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
