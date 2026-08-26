"""Prepare and inspect a zero-provider two-stage target-user pilot.

The earlier topology audit is a closed randomized comparison.  This tool does
not append to it.  It exposes only a topic catalog at Stage 1, locks the user's
baseline before report exposure, and materializes one historical full-workflow
report at Stage 2.  Every source and delivery seam is hashed because the useful
claim is about the artifact a person actually read, not merely the file that a
coordinator intended to send.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


STUDY_ID = "target-user-decision-pilot-20260826"
SOURCE_REPORT_DATE = "2026-08-21"
REVIEWER_IDS = ("T01", "T02")
TARGET_ROLES = {
    "TTO_COMMERCIALIZATION",
    "INVESTMENT_DUE_DILIGENCE",
    "INDUSTRY_STRATEGY",
    "OTHER_COMMERCIALIZATION_DECISION_MAKER",
}
ROLE_LABELS = {*TARGET_ROLES, "PROXY"}
EXPERIENCE_LABELS = {"0_2", "3_5", "6_10", "11_PLUS"}
AI_USE_LABELS = {"NONE", "TRANSLATION_OR_CLERICAL", "SUBSTANTIVE"}
CONSENT_LABELS = {"YES", "NO"}
COMPENSATION_LABELS = {"NONE", "HONORARIUM", "OTHER"}
DECISION_LABELS = {"GO", "NO_GO", "DEFER", "UNCERTAIN"}
REUSE_LABELS = {"YES", "MAYBE", "NO"}
CITATION_CHECK_LABELS = {"NONE", "SOME", "ALL"}
FACT_ERROR_LABELS = {"NOT_CHECKED", "NONE_FOUND", "ONE_FOUND", "TWO_PLUS_FOUND"}
BLOCKING_ERROR_LABELS = {"YES", "NO", "UNCERTAIN"}
SLOT_LABELS = {"OPEN", "CLOSED_NO_RESPONSE", "WITHDREW"}

CATALOG_FIELDS = ("topic_num", "topic", "industry")
PROFILE_FIELDS = (
    "reviewer_id",
    "role_category",
    "experience_band",
    "professional_context",
    "domain_experience",
    "generative_ai_use",
    "generative_ai_notes",
    "anonymous_aggregate_consent",
    "compensation",
    "compensation_notes",
)
BASELINE_FIELDS = (
    "reviewer_id",
    "selected_topic_num",
    "selected_topic",
    "selection_reason",
    "current_workflow_summary",
    "expected_research_minutes",
    "initial_decision",
    "initial_confidence",
    "information_needed",
)
FOLLOWUP_FIELDS = (
    "reviewer_id",
    "selected_topic_num",
    "selected_topic",
    "report_sha256",
    "post_report_decision",
    "post_report_confidence",
    "decision_usefulness",
    "information_gain",
    "actionability",
    "evidence_trust",
    "recommendation_acceptance",
    "reading_minutes",
    "estimated_revision_minutes",
    "would_use_again",
    "citation_check",
    "factual_error_state",
    "blocking_error",
    "blocking_error_details",
    "most_useful_content",
    "missing_information",
    "required_corrections",
    "rationale",
)
SLOT_FIELDS = ("reviewer_id", "slot_status", "closure_reason")
FOLLOWUP_REQUIRED_FIELDS = tuple(
    field for field in FOLLOWUP_FIELDS[4:] if field != "blocking_error_details"
)


class TargetUserPilotError(ValueError):
    """Raised when an artifact would overstate or corrupt the pilot evidence."""


@dataclass(frozen=True)
class FrozenReport:
    """One exact historical full-workflow report available in the catalog."""

    topic_num: str
    topic: str
    industry: str
    source_cell: str
    fixture_digest: str
    report_sha256: str
    meta_sha256: str
    report_path: Path
    meta_path: Path


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _sha256_bytes(encoded)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TargetUserPilotError(f"{path} must contain a JSON object")
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_csv(path: Path, expected_fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != expected_fields:
            raise TargetUserPilotError(f"{path} has an unexpected CSV schema")
        return list(reader)


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _assert_separate(packet_dir: Path, source_lock_path: Path) -> None:
    packet = packet_dir.resolve()
    lock = source_lock_path.resolve()
    if lock == packet or packet in lock.parents:
        raise TargetUserPilotError("the source lock must stay outside every reviewer packet directory")


def discover_reports(experiment_dir: Path, *, expected_count: int = 10) -> list[FrozenReport]:
    """Freeze each topic's successful full-workflow repetition-one artifact.

    Selecting by this rule is intentionally less flexible than "first report
    that looks useful".  A failed or missing repetition-one cell stops packet
    preparation instead of silently changing the human denominator.
    """

    reports: dict[str, FrozenReport] = {}
    for meta_path in sorted(experiment_dir.glob("*/meta.json")):
        raw_meta = meta_path.read_bytes()
        try:
            meta = json.loads(raw_meta.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TargetUserPilotError(f"{meta_path} is not valid UTF-8 JSON") from exc
        if not isinstance(meta, dict) or meta.get("variant") != "full" or meta.get("rep") != 1:
            continue
        if meta.get("status") != "success":
            raise TargetUserPilotError(f"frozen full cell {meta_path.parent.name} is not successful")

        topic_num = str(meta.get("num", "")).strip()
        topic = str(meta.get("topic", "")).strip()
        industry = str(meta.get("industry", "")).strip()
        fixture_digest = str(meta.get("fixture_digest", "")).strip()
        if not topic_num or not topic or not industry or not fixture_digest:
            raise TargetUserPilotError(f"{meta_path} is missing catalog or evidence identity")
        if topic_num in reports:
            raise TargetUserPilotError(f"duplicate full repetition-one topic: {topic_num}")

        report_path = meta_path.parent / "commercialization_report.md"
        if not report_path.is_file():
            raise TargetUserPilotError(f"{meta_path.parent.name} is missing commercialization_report.md")
        report_bytes = report_path.read_bytes()
        try:
            report_body = report_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TargetUserPilotError(f"{report_path} is not UTF-8") from exc
        if not report_body.strip():
            raise TargetUserPilotError(f"{report_path} is empty")

        reports[topic_num] = FrozenReport(
            topic_num=topic_num,
            topic=topic,
            industry=industry,
            source_cell=meta_path.parent.name,
            fixture_digest=fixture_digest,
            report_sha256=_sha256_bytes(report_bytes),
            meta_sha256=_sha256_bytes(raw_meta),
            report_path=report_path,
            meta_path=meta_path,
        )

    if len(reports) != expected_count:
        raise TargetUserPilotError(f"expected {expected_count} frozen full reports, found {len(reports)}")
    return [reports[key] for key in sorted(reports)]


def _catalog_rows(reports: list[FrozenReport]) -> list[dict[str, str]]:
    return [{field: getattr(report, field) for field in CATALOG_FIELDS} for report in reports]


def _source_rows(reports: list[FrozenReport]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for report in reports:
        row = asdict(report)
        # Absolute developer paths do not belong in an audit lock that may be
        # archived elsewhere.  The source cell plus fixed filenames is enough
        # to re-resolve the artifact against the explicit experiment argument.
        row["report_path"] = f"{report.source_cell}/commercialization_report.md"
        row["meta_path"] = f"{report.source_cell}/meta.json"
        rows.append(row)
    return rows


def _stage_one_readme(reviewer_id: str) -> str:
    return f"""# 目标用户决策试点：第一阶段

评审编号：`{reviewer_id}`

这一阶段**不包含任何系统报告**。请先完成：

1. `reviewer_profile.csv`：填写你的角色背景和 AI 使用声明；
2. 查看 `case_catalog.csv`，选择一个与你真实工作最接近、你有直接经验的主题；
3. 在 `baseline_form.csv` 记录看报告之前的判断、信心和你通常需要的信息。

请不要搜索或向他人询问系统对这些主题的既有结论。可以查阅你正常工作中
本来就会使用的资料，但请在 `current_workflow_summary` 中如实说明。不要使用生成式
AI 代替实质判断；翻译或表格整理用途必须在 profile 中披露。

请只修改两个 CSV，不要改动主题目录。完成后把整个文件夹原样返还。第二阶段会在
这份基线锁定后才发送一份与你所选主题对应的历史报告。
"""


def _coordinator_readme() -> str:
    return """# Target-user pilot coordinator workspace

Do not send this whole directory. Stage 1 contains no report by design; send
only one reviewer's `stage-1/<reviewer_id>` directory. After the returned
profile and baseline are copied into the canonical directory, run the
`materialize` command to create that reviewer's Stage 2 packet.

The source lock must remain outside this packet root. Do not add a third slot,
replace a started slot, or reveal another reviewer's response. If an untouched
slot cannot be recruited, set its coordinator status to `CLOSED_NO_RESPONSE`.
"""


def _stage_two_readme(reviewer_id: str, topic: str) -> str:
    return f"""# 目标用户决策试点：第二阶段

- 评审编号：`{reviewer_id}`
- 锁定主题：`{topic}`

请完整阅读 `report.md`，然后填写 `followup_form.csv`。报告来自 2026-08-21
冻结证据，不是刚刚重新联网检索的材料。请按真实工作标准记录它是否有决策价值、
需要多少修订，以及哪些内容可能误导。

不要求逐个打开引用；但如果没有打开任何外部来源，`citation_check` 必须填写
`NONE`，`factual_error_state` 必须填写 `NOT_CHECKED`。这代表“没有核查”，不是
“没有错误”。不要使用生成式 AI 代替你的实质判断。

请只修改 `followup_form.csv`，不要修改报告或 selection snapshot。完成后原样返还
整个文件夹。
"""


def prepare_pilot(experiment_dir: Path, packet_dir: Path, source_lock_path: Path) -> dict[str, Any]:
    """Create report-free Stage 1 packets and a physically separate source lock."""

    _assert_separate(packet_dir, source_lock_path)
    if packet_dir.exists() or source_lock_path.exists():
        raise TargetUserPilotError("packet and source-lock paths must not already exist")

    reports = discover_reports(experiment_dir)
    catalog = _catalog_rows(reports)
    catalog_digest = _canonical_sha256(catalog)
    packet_dir.mkdir(parents=True)
    (packet_dir / "README.md").write_text(_coordinator_readme(), encoding="utf-8")
    _write_csv(
        packet_dir / "coordinator" / "slot_status.csv",
        SLOT_FIELDS,
        [
            {"reviewer_id": reviewer_id, "slot_status": "OPEN", "closure_reason": ""}
            for reviewer_id in REVIEWER_IDS
        ],
    )

    for reviewer_id in REVIEWER_IDS:
        reviewer_dir = packet_dir / "stage-1" / reviewer_id
        reviewer_dir.mkdir(parents=True)
        (reviewer_dir / "README.md").write_text(_stage_one_readme(reviewer_id), encoding="utf-8")
        _write_csv(reviewer_dir / "case_catalog.csv", CATALOG_FIELDS, catalog)
        _write_csv(
            reviewer_dir / "reviewer_profile.csv",
            PROFILE_FIELDS,
            [{"reviewer_id": reviewer_id}],
        )
        _write_csv(
            reviewer_dir / "baseline_form.csv",
            BASELINE_FIELDS,
            [{"reviewer_id": reviewer_id}],
        )

    manifest = {
        "schema_version": 1,
        "study_id": STUDY_ID,
        "reviewer_ids": list(REVIEWER_IDS),
        "source_count": len(reports),
        "catalog_sha256": catalog_digest,
        "stage_1_contains_reports": False,
        "human_response_count": 0,
        "status": "not_started",
    }
    _write_json(packet_dir / "manifest.json", manifest)
    source_lock = {
        "schema_version": 1,
        "study_id": STUDY_ID,
        "source_experiment": experiment_dir.name,
        "reviewer_ids": list(REVIEWER_IDS),
        "catalog_sha256": catalog_digest,
        "packet_manifest_sha256": _sha256_bytes((packet_dir / "manifest.json").read_bytes()),
        "sources": _source_rows(reports),
    }
    _write_json(source_lock_path, source_lock)
    return manifest


def _source_projection(report: FrozenReport) -> dict[str, str]:
    return _source_rows([report])[0]


def _verify_base(
    experiment_dir: Path, packet_dir: Path, source_lock_path: Path
) -> dict[str, FrozenReport]:
    _assert_separate(packet_dir, source_lock_path)
    manifest = _read_json(packet_dir / "manifest.json")
    source_lock = _read_json(source_lock_path)
    if manifest.get("study_id") != STUDY_ID or source_lock.get("study_id") != STUDY_ID:
        raise TargetUserPilotError("packet or source lock belongs to a different study")
    if manifest.get("reviewer_ids") != list(REVIEWER_IDS) or source_lock.get("reviewer_ids") != list(REVIEWER_IDS):
        raise TargetUserPilotError("reviewer slots drifted from the pre-registration")
    if source_lock.get("packet_manifest_sha256") != _sha256_bytes((packet_dir / "manifest.json").read_bytes()):
        raise TargetUserPilotError("packet manifest drifted after source lock creation")

    reports = discover_reports(experiment_dir)
    expected_sources = _source_rows(reports)
    if source_lock.get("sources") != expected_sources:
        raise TargetUserPilotError("frozen source report or metadata drifted")
    catalog = _catalog_rows(reports)
    catalog_digest = _canonical_sha256(catalog)
    if manifest.get("catalog_sha256") != catalog_digest or source_lock.get("catalog_sha256") != catalog_digest:
        raise TargetUserPilotError("catalog identity drifted")

    for reviewer_id in REVIEWER_IDS:
        reviewer_dir = packet_dir / "stage-1" / reviewer_id
        rows = _read_csv(reviewer_dir / "case_catalog.csv", CATALOG_FIELDS)
        if rows != catalog:
            raise TargetUserPilotError(f"{reviewer_id} catalog drifted after packet creation")
        # Stage 1 must remain a real information barrier.  Checking filenames
        # rather than searching for one sample phrase protects every future
        # report body and catches accidental coordinator copies.
        unexpected = [path for path in reviewer_dir.rglob("*") if path.is_file() and path.suffix.lower() == ".md" and path.name != "README.md"]
        if unexpected:
            raise TargetUserPilotError(f"{reviewer_id} Stage 1 unexpectedly contains a report-like file")
    return {report.topic_num: report for report in reports}


def _single_row(path: Path, fields: tuple[str, ...]) -> dict[str, str]:
    rows = _read_csv(path, fields)
    if len(rows) != 1:
        raise TargetUserPilotError(f"{path} must contain exactly one row")
    return rows[0]


def _empty_except_identity(row: dict[str, str], identity_fields: set[str]) -> bool:
    return all(not value.strip() for key, value in row.items() if key not in identity_fields)


def _require_complete(row: dict[str, str], required: tuple[str, ...], *, context: str) -> None:
    missing = [field for field in required if not row.get(field, "").strip()]
    if missing:
        raise TargetUserPilotError(f"{context} is partially completed; missing {', '.join(missing)}")


def _parse_int(value: str, *, field: str, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise TargetUserPilotError(f"{field} must be an integer") from exc
    if not minimum <= parsed <= maximum:
        raise TargetUserPilotError(f"{field} must be between {minimum} and {maximum}")
    return parsed


def _validate_profile(row: dict[str, str], reviewer_id: str) -> dict[str, Any] | None:
    if row.get("reviewer_id", "").strip() != reviewer_id:
        raise TargetUserPilotError(f"{reviewer_id} profile changed reviewer_id")
    if _empty_except_identity(row, {"reviewer_id"}):
        return None
    required = (
        "role_category",
        "experience_band",
        "professional_context",
        "domain_experience",
        "generative_ai_use",
        "anonymous_aggregate_consent",
        "compensation",
    )
    _require_complete(row, required, context=f"{reviewer_id} profile")
    role = row["role_category"].strip().upper()
    experience = row["experience_band"].strip().upper()
    ai_use = row["generative_ai_use"].strip().upper()
    consent = row["anonymous_aggregate_consent"].strip().upper()
    compensation = row["compensation"].strip().upper()
    if role not in ROLE_LABELS:
        raise TargetUserPilotError(f"{reviewer_id} has invalid role_category")
    if experience not in EXPERIENCE_LABELS:
        raise TargetUserPilotError(f"{reviewer_id} has invalid experience_band")
    if ai_use not in AI_USE_LABELS:
        raise TargetUserPilotError(f"{reviewer_id} has invalid generative_ai_use")
    if consent not in CONSENT_LABELS:
        raise TargetUserPilotError(f"{reviewer_id} has invalid anonymous_aggregate_consent")
    if compensation not in COMPENSATION_LABELS:
        raise TargetUserPilotError(f"{reviewer_id} has invalid compensation")
    if ai_use != "NONE" and not row["generative_ai_notes"].strip():
        raise TargetUserPilotError(f"{reviewer_id} must describe non-NONE generative AI use")
    if compensation == "OTHER" and not row["compensation_notes"].strip():
        raise TargetUserPilotError(f"{reviewer_id} must describe OTHER compensation")
    return {
        **row,
        "role_category": role,
        "experience_band": experience,
        "generative_ai_use": ai_use,
        "anonymous_aggregate_consent": consent,
        "compensation": compensation,
    }


def _validate_baseline(
    row: dict[str, str], reviewer_id: str, reports: dict[str, FrozenReport]
) -> dict[str, Any] | None:
    if row.get("reviewer_id", "").strip() != reviewer_id:
        raise TargetUserPilotError(f"{reviewer_id} baseline changed reviewer_id")
    if _empty_except_identity(row, {"reviewer_id"}):
        return None
    _require_complete(row, BASELINE_FIELDS[1:], context=f"{reviewer_id} baseline")
    topic_num = row["selected_topic_num"].strip()
    if topic_num not in reports:
        raise TargetUserPilotError(f"{reviewer_id} selected an unknown topic")
    report = reports[topic_num]
    if row["selected_topic"].strip() != report.topic:
        raise TargetUserPilotError(f"{reviewer_id} changed the selected topic text")
    decision = row["initial_decision"].strip().upper()
    if decision not in DECISION_LABELS:
        raise TargetUserPilotError(f"{reviewer_id} has invalid initial_decision")
    return {
        **row,
        "selected_topic_num": topic_num,
        "selected_topic": report.topic,
        "expected_research_minutes": _parse_int(
            row["expected_research_minutes"],
            field=f"{reviewer_id} expected_research_minutes",
            minimum=1,
            maximum=10000,
        ),
        "initial_decision": decision,
        "initial_confidence": _parse_int(
            row["initial_confidence"],
            field=f"{reviewer_id} initial_confidence",
            minimum=1,
            maximum=5,
        ),
    }


def _profile_and_baseline(
    packet_dir: Path, reviewer_id: str, reports: dict[str, FrozenReport]
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    reviewer_dir = packet_dir / "stage-1" / reviewer_id
    profile = _validate_profile(
        _single_row(reviewer_dir / "reviewer_profile.csv", PROFILE_FIELDS), reviewer_id
    )
    baseline = _validate_baseline(
        _single_row(reviewer_dir / "baseline_form.csv", BASELINE_FIELDS), reviewer_id, reports
    )
    if (profile is None) != (baseline is None):
        raise TargetUserPilotError(f"{reviewer_id} intake has only one of profile and baseline")
    return profile, baseline


def materialize_followup(
    experiment_dir: Path, packet_dir: Path, source_lock_path: Path, reviewer_id: str
) -> dict[str, Any]:
    """Release one report only after the corresponding baseline is complete."""

    if reviewer_id not in REVIEWER_IDS:
        raise TargetUserPilotError("unknown reviewer_id")
    reports = _verify_base(experiment_dir, packet_dir, source_lock_path)
    profile, baseline = _profile_and_baseline(packet_dir, reviewer_id, reports)
    if profile is None or baseline is None:
        raise TargetUserPilotError(f"{reviewer_id} intake must be complete before Stage 2")

    stage_two = packet_dir / "stage-2" / reviewer_id
    if stage_two.exists():
        raise TargetUserPilotError(f"{reviewer_id} Stage 2 already exists")
    report = reports[baseline["selected_topic_num"]]
    report_bytes = report.report_path.read_bytes()
    if _sha256_bytes(report_bytes) != report.report_sha256:
        raise TargetUserPilotError("selected source report drifted before materialization")

    stage_two.mkdir(parents=True)
    (stage_two / "README.md").write_text(
        _stage_two_readme(reviewer_id, report.topic), encoding="utf-8"
    )
    (stage_two / "report.md").write_bytes(report_bytes)
    snapshot = {
        "schema_version": 1,
        "study_id": STUDY_ID,
        "reviewer_id": reviewer_id,
        "selected_topic_num": report.topic_num,
        "selected_topic": report.topic,
        "fixture_digest": report.fixture_digest,
        "source_cell": report.source_cell,
        "source_report_sha256": report.report_sha256,
        "delivered_report_sha256": _sha256_bytes((stage_two / "report.md").read_bytes()),
        "profile_sha256": _canonical_sha256(profile),
        "baseline_sha256": _canonical_sha256(baseline),
    }
    _write_json(stage_two / "selection_snapshot.json", snapshot)
    _write_csv(
        stage_two / "followup_form.csv",
        FOLLOWUP_FIELDS,
        [
            {
                "reviewer_id": reviewer_id,
                "selected_topic_num": report.topic_num,
                "selected_topic": report.topic,
                "report_sha256": report.report_sha256,
            }
        ],
    )
    return snapshot


def _validate_followup(
    row: dict[str, str], reviewer_id: str, report: FrozenReport
) -> dict[str, Any] | None:
    identities = {
        "reviewer_id": reviewer_id,
        "selected_topic_num": report.topic_num,
        "selected_topic": report.topic,
        "report_sha256": report.report_sha256,
    }
    for field, expected in identities.items():
        if row.get(field, "").strip() != expected:
            raise TargetUserPilotError(f"{reviewer_id} follow-up changed {field}")
    if _empty_except_identity(row, set(identities)):
        return None
    _require_complete(row, FOLLOWUP_REQUIRED_FIELDS, context=f"{reviewer_id} follow-up")

    decision = row["post_report_decision"].strip().upper()
    reuse = row["would_use_again"].strip().upper()
    citation_check = row["citation_check"].strip().upper()
    factual = row["factual_error_state"].strip().upper()
    blocking = row["blocking_error"].strip().upper()
    if decision not in DECISION_LABELS:
        raise TargetUserPilotError(f"{reviewer_id} has invalid post_report_decision")
    if reuse not in REUSE_LABELS:
        raise TargetUserPilotError(f"{reviewer_id} has invalid would_use_again")
    if citation_check not in CITATION_CHECK_LABELS:
        raise TargetUserPilotError(f"{reviewer_id} has invalid citation_check")
    if factual not in FACT_ERROR_LABELS:
        raise TargetUserPilotError(f"{reviewer_id} has invalid factual_error_state")
    if blocking not in BLOCKING_ERROR_LABELS:
        raise TargetUserPilotError(f"{reviewer_id} has invalid blocking_error")
    if citation_check == "NONE" and factual != "NOT_CHECKED":
        raise TargetUserPilotError(f"{reviewer_id} cannot report factual errors without source checking")
    if citation_check != "NONE" and factual == "NOT_CHECKED":
        raise TargetUserPilotError(f"{reviewer_id} opened sources but left factual errors unchecked")
    if blocking == "YES" and not row["blocking_error_details"].strip():
        raise TargetUserPilotError(f"{reviewer_id} must describe a blocking error")

    parsed: dict[str, Any] = {
        **row,
        "post_report_decision": decision,
        "would_use_again": reuse,
        "citation_check": citation_check,
        "factual_error_state": factual,
        "blocking_error": blocking,
    }
    for field in (
        "post_report_confidence",
        "decision_usefulness",
        "information_gain",
        "actionability",
        "evidence_trust",
        "recommendation_acceptance",
    ):
        parsed[field] = _parse_int(row[field], field=f"{reviewer_id} {field}", minimum=1, maximum=5)
    parsed["reading_minutes"] = _parse_int(
        row["reading_minutes"], field=f"{reviewer_id} reading_minutes", minimum=1, maximum=10000
    )
    parsed["estimated_revision_minutes"] = _parse_int(
        row["estimated_revision_minutes"],
        field=f"{reviewer_id} estimated_revision_minutes",
        minimum=0,
        maximum=10000,
    )
    return parsed


def _slot_states(packet_dir: Path) -> dict[str, dict[str, str]]:
    rows = _read_csv(packet_dir / "coordinator" / "slot_status.csv", SLOT_FIELDS)
    if len(rows) != len(REVIEWER_IDS):
        raise TargetUserPilotError("slot status must contain exactly the registered reviewers")
    states: dict[str, dict[str, str]] = {}
    for row in rows:
        reviewer_id = row["reviewer_id"].strip()
        state = row["slot_status"].strip().upper()
        reason = row["closure_reason"].strip()
        if reviewer_id not in REVIEWER_IDS or reviewer_id in states:
            raise TargetUserPilotError("slot status has an unknown or duplicate reviewer")
        if state not in SLOT_LABELS:
            raise TargetUserPilotError(f"{reviewer_id} has invalid slot_status")
        if state == "OPEN" and reason:
            raise TargetUserPilotError(f"{reviewer_id} OPEN slot cannot have a closure reason")
        if state != "OPEN" and not reason:
            raise TargetUserPilotError(f"{reviewer_id} closed slot requires a reason")
        states[reviewer_id] = {"slot_status": state, "closure_reason": reason}
    if set(states) != set(REVIEWER_IDS):
        raise TargetUserPilotError("slot status does not match the registered reviewers")
    return states


def _verify_stage_two(
    stage_two: Path,
    reviewer_id: str,
    report: FrozenReport,
    profile: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any] | None:
    snapshot = _read_json(stage_two / "selection_snapshot.json")
    expected = {
        "study_id": STUDY_ID,
        "reviewer_id": reviewer_id,
        "selected_topic_num": report.topic_num,
        "selected_topic": report.topic,
        "fixture_digest": report.fixture_digest,
        "source_cell": report.source_cell,
        "source_report_sha256": report.report_sha256,
        "delivered_report_sha256": report.report_sha256,
        "profile_sha256": _canonical_sha256(profile),
        "baseline_sha256": _canonical_sha256(baseline),
    }
    for field, value in expected.items():
        if snapshot.get(field) != value:
            raise TargetUserPilotError(f"{reviewer_id} selection snapshot drifted at {field}")
    if _sha256_bytes((stage_two / "report.md").read_bytes()) != report.report_sha256:
        raise TargetUserPilotError(f"{reviewer_id} delivered report drifted")
    return _validate_followup(
        _single_row(stage_two / "followup_form.csv", FOLLOWUP_FIELDS), reviewer_id, report
    )


def _median(values: list[int]) -> float | None:
    return float(statistics.median(values)) if values else None


def _aggregate_observations(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Project only structured outcomes from the explicitly supplied rows."""

    metric_fields = (
        "decision_usefulness",
        "information_gain",
        "actionability",
        "evidence_trust",
        "recommendation_acceptance",
        "reading_minutes",
        "estimated_revision_minutes",
    )
    return {
        "decision_changed_count": sum(1 for row in rows if row["derived"]["decision_changed"]),
        "would_use_again": {
            label: sum(1 for row in rows if row["followup"]["would_use_again"] == label)
            for label in sorted(REUSE_LABELS)
        },
        "citation_check": {
            label: sum(1 for row in rows if row["followup"]["citation_check"] == label)
            for label in sorted(CITATION_CHECK_LABELS)
        },
        "blocking_error": {
            label: sum(1 for row in rows if row["followup"]["blocking_error"] == label)
            for label in sorted(BLOCKING_ERROR_LABELS)
        },
        "eligible_medians": {
            field: _median([int(row["followup"][field]) for row in rows])
            for field in metric_fields
        },
    }


def summarize_pilot(experiment_dir: Path, packet_dir: Path, source_lock_path: Path) -> dict[str, Any]:
    """Validate every handoff and return private plus consent-safe projections."""

    reports = _verify_base(experiment_dir, packet_dir, source_lock_path)
    slot_states = _slot_states(packet_dir)
    reviewers: list[dict[str, Any]] = []
    open_incomplete = False

    for reviewer_id in REVIEWER_IDS:
        profile, baseline = _profile_and_baseline(packet_dir, reviewer_id, reports)
        slot = slot_states[reviewer_id]
        stage_two = packet_dir / "stage-2" / reviewer_id
        if slot["slot_status"] != "OPEN":
            if profile is not None or baseline is not None or stage_two.exists():
                raise TargetUserPilotError(f"{reviewer_id} closed slot contains participant data")
            reviewers.append({"reviewer_id": reviewer_id, "status": slot["slot_status"].lower()})
            continue
        if profile is None or baseline is None:
            open_incomplete = True
            reviewers.append({"reviewer_id": reviewer_id, "status": "not_started"})
            continue

        report = reports[baseline["selected_topic_num"]]
        if not stage_two.is_dir():
            open_incomplete = True
            reviewers.append(
                {
                    "reviewer_id": reviewer_id,
                    "status": "report_not_materialized",
                    "profile": profile,
                    "baseline": baseline,
                }
            )
            continue
        followup = _verify_stage_two(stage_two, reviewer_id, report, profile, baseline)
        if followup is None:
            open_incomplete = True
            reviewers.append(
                {
                    "reviewer_id": reviewer_id,
                    "status": "followup_incomplete",
                    "profile": profile,
                    "baseline": baseline,
                }
            )
            continue

        is_target = profile["role_category"] in TARGET_ROLES
        ai_excluded = profile["generative_ai_use"] == "SUBSTANTIVE"
        eligible = is_target and not ai_excluded
        reviewers.append(
            {
                "reviewer_id": reviewer_id,
                "status": "complete",
                "eligible_target_user": eligible,
                "publicly_reportable": eligible and profile["anonymous_aggregate_consent"] == "YES",
                "profile": profile,
                "baseline": baseline,
                "followup": followup,
                "derived": {
                    "decision_changed": baseline["initial_decision"] != followup["post_report_decision"],
                    "confidence_delta": followup["post_report_confidence"] - baseline["initial_confidence"],
                    "self_reported_estimated_minutes_delta": baseline["expected_research_minutes"]
                    - followup["reading_minutes"]
                    - followup["estimated_revision_minutes"],
                    "source_truth_status": (
                        "not_evaluated" if followup["citation_check"] == "NONE" else "partially_checked"
                    ),
                },
            }
        )

    completed = [row for row in reviewers if row["status"] == "complete"]
    eligible = [row for row in completed if row["eligible_target_user"]]
    public_rows = [row for row in eligible if row["publicly_reportable"]]
    if open_incomplete:
        status = "in_progress"
    elif len(eligible) == 2:
        status = "descriptive_pilot_complete"
    elif len(eligible) == 1:
        status = "single_target_user_observation"
    else:
        status = "no_eligible_target_user_observation"

    private_metrics = _aggregate_observations(eligible)
    public_metrics = _aggregate_observations(public_rows)
    if not eligible:
        publication_status = "no_eligible_observations"
    elif len(public_rows) == len(eligible):
        publication_status = "all_eligible_observations_public"
    elif public_rows:
        publication_status = "partial_public_consent"
    else:
        publication_status = "no_eligible_observation_consent"

    reportable_role_mix = {
        label: sum(1 for row in public_rows if row["profile"]["role_category"] == label)
        for label in sorted(TARGET_ROLES)
        if any(row["profile"]["role_category"] == label for row in public_rows)
    }
    reportable_ai_use = {
        label: sum(1 for row in public_rows if row["profile"]["generative_ai_use"] == label)
        for label in sorted(AI_USE_LABELS)
        if any(row["profile"]["generative_ai_use"] == label for row in public_rows)
    }
    closed_states = {"closed_no_response", "withdrew"}
    closed_count = sum(1 for row in reviewers if row["status"] in closed_states)
    incomplete_count = len(REVIEWER_IDS) - len(completed) - closed_count
    public_projection = {
        "schema_version": 1,
        "study_id": STUDY_ID,
        # Study completion and publication consent are orthogonal.  Folding
        # them into one status made a complete two-user pilot look unfinished
        # when one person declined publication.
        "status": status,
        "publication_status": publication_status,
        "registered_slots": len(REVIEWER_IDS),
        "complete_observation_count": len(completed),
        "closed_slot_count": closed_count,
        "incomplete_slot_count": incomplete_count,
        "publicly_reportable_count": len(public_rows),
        "reportable_role_mix": reportable_role_mix,
        "reportable_ai_use": reportable_ai_use,
        "reportable_selected_topics": [
            {
                "topic_num": row["baseline"]["selected_topic_num"],
                "topic": row["baseline"]["selected_topic"],
            }
            for row in public_rows
        ],
        "source_material": {
            "report_generation_date": SOURCE_REPORT_DATE,
            "evidence_state": "frozen_historical",
            "fresh_retrieval": False,
            "topic_assignment": "reviewer_self_selected_before_report",
        },
        **public_metrics,
        "claim_boundary": (
            "descriptive target-user observations only; not adoption, ROI, decision accuracy, "
            "hallucination rate, or population-level product validation"
        ),
    }
    return {
        "schema_version": 1,
        "study_id": STUDY_ID,
        "status": status,
        "registered_slots": len(REVIEWER_IDS),
        "completed_count": len(completed),
        "eligible_target_user_count": len(eligible),
        "publicly_reportable_count": len(public_rows),
        "substantive_ai_excluded_count": sum(
            1
            for row in completed
            if row["profile"]["generative_ai_use"] == "SUBSTANTIVE"
        ),
        "proxy_completed_count": sum(
            1 for row in completed if row["profile"]["role_category"] == "PROXY"
        ),
        **private_metrics,
        "claim_boundary": public_projection["claim_boundary"],
        "reviewers": reviewers,
        "public_projection": public_projection,
    }


def write_summary(path: Path, result: dict[str, Any], *, public_only: bool = False) -> None:
    """Persist an immutable private result or its consent-safe projection."""

    if path.exists():
        raise TargetUserPilotError("summary output already exists")
    value = result["public_projection"] if public_only else result
    _write_json(path, value)


def write_summaries(
    private_path: Path, public_path: Path | None, result: dict[str, Any]
) -> None:
    """Preflight the output pair so an expected collision cannot half-write it."""

    paths = [private_path, *([] if public_path is None else [public_path])]
    resolved = [path.resolve() for path in paths]
    if len(set(resolved)) != len(resolved):
        raise TargetUserPilotError("private and public summary outputs must be distinct")
    existing = [path for path in paths if path.exists()]
    if existing:
        raise TargetUserPilotError(
            "summary output already exists: " + ", ".join(str(path) for path in existing)
        )

    write_summary(private_path, result)
    if public_path is not None:
        write_summary(public_path, result, public_only=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    prepare = commands.add_parser("prepare", help="create report-free Stage 1 packets")
    prepare.add_argument("experiment_dir", type=Path)
    prepare.add_argument("packet_dir", type=Path)
    prepare.add_argument("source_lock", type=Path)

    materialize = commands.add_parser("materialize", help="create one Stage 2 packet after intake")
    materialize.add_argument("experiment_dir", type=Path)
    materialize.add_argument("packet_dir", type=Path)
    materialize.add_argument("source_lock", type=Path)
    materialize.add_argument("reviewer_id", choices=REVIEWER_IDS)

    summarize = commands.add_parser("summarize", help="validate and summarize the pilot")
    summarize.add_argument("experiment_dir", type=Path)
    summarize.add_argument("packet_dir", type=Path)
    summarize.add_argument("source_lock", type=Path)
    summarize.add_argument("output", type=Path)
    summarize.add_argument("--public-output", type=Path)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "prepare":
        result = prepare_pilot(args.experiment_dir, args.packet_dir, args.source_lock)
    elif args.command == "materialize":
        result = materialize_followup(
            args.experiment_dir, args.packet_dir, args.source_lock, args.reviewer_id
        )
    else:
        result = summarize_pilot(args.experiment_dir, args.packet_dir, args.source_lock)
        write_summaries(args.output, args.public_output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
