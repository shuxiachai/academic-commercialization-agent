"""Fresh JQ synthetic canary; the parent alone exercises its bounded authority.

Identity precedes keys and output. A CLI acknowledgement is not independently
verified user consent; the committed preregistration records the standing scope.
Frozen SQ/FQ cases, manifests and allowances are never reused. The final JSON
wire requirement is distinct from strict core acceptance or semantic support.
"""

import hashlib
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import tomllib

from academic_agent import report_evidence_followup as core
from academic_agent.report_evidence_guarded_followup import run_policy_followup
from academic_agent.report_evidence_qwen_canary import CanaryStopped, _encoded
from academic_agent.report_evidence_qwen_transport import validate_key
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource
from academic_agent.report_evidence_final_json_qwen_transport import (
    FROZEN_DEPENDENCY_COUPLING, FinalJsonQwenFollowupTransport, FinalJsonQwenLedger,
    TRANSPORT_IDENTITY, final_json_configuration,
)

PROTOCOL_IDENTITY = "report_evidence_final_json_qwen_canary_v1"
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = "tests/fixtures/report_evidence_final_json_qwen_canary.json"
FIXTURE_SHA256 = "f0e8233a7b0e0d86783f069d96880ace941cd0ac16dbfa934e723d653febb5ca"
PROTOCOL = "docs/prereg-2026-09-16-report-evidence-final-json-qwen.md"
IDENTITY_PATHS = tuple(dict.fromkeys((
    ".gitattributes", "src/academic_agent/__init__.py", *FROZEN_DEPENDENCY_COUPLING,
    "src/academic_agent/report_evidence_final_json_qwen_transport.py",
    "src/academic_agent/report_evidence_final_json_qwen_canary.py",
    "report_evidence_final_json_canary.py", "tests/test_report_evidence_final_json_qwen_canary.py",
    "tests/test_report_evidence_final_json_qwen_transport.py", FIXTURE, PROTOCOL,
)))
DEPENDENCIES = (
    "httpx", "httpcore", "anyio", "certifi", "h11", "idna", "sniffio", "typing-extensions",
    "pydantic", "pydantic-core", "annotated-types", "typing-inspection",
)
CASE_FIELDS = frozenset((
    "case_id", "source_id", "group", "title", "publisher", "accessed_date", "origin", "summary", "question",
))


def configuration() -> dict:
    return {**final_json_configuration(), "protocol_identity": PROTOCOL_IDENTITY,
            "transport_identity": TRANSPORT_IDENTITY, "case_ids": ["JQ01", "JQ02"],
            "max_tool_attempts_per_case": core.MAX_TOOL_REQUESTS, "max_turns_per_case": core.MAX_TURNS,
            "credential_source": "process_DASHSCOPE_API_KEY_only", "resume": False,
            "acknowledgement_is_independent_consent_verification": False}


def snapshot_for(case: dict) -> ReportEvidenceSnapshot:
    return ReportEvidenceSnapshot(report_ref=case["case_id"], sources=(SnapshotSource(
        **{key: value for key, value in case.items() if key not in {"case_id", "question"}},
        source_type=case["group"],
    ),))


def load_cases() -> list[dict]:
    """Accept only the parent's frozen flat list, never caller-selected data."""
    try:
        raw = (ROOT / FIXTURE).read_bytes()
        if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
            raise CanaryStopped("fixture_identity_mismatch")
        cases = core._strict_json(raw.decode("utf-8"))
        if type(cases) is not list or len(cases) != 2:
            raise ValueError("invalid case list")
        for case, expected in zip(cases, (("JQ01", "A9", "academic", "abstract"),
                                          ("JQ02", "M6", "market", "unknown")), strict=True):
            if type(case) is not dict or set(case) != CASE_FIELDS:
                raise ValueError("invalid case fields")
            if tuple(case[key] for key in ("case_id", "source_id", "group", "origin")) != expected:
                raise ValueError("invalid case identity")
            if (type(case["question"]) is not str or not 1 <= len(case["question"]) <= 4096
                    or case["publisher"] != "Synthetic example" or case["accessed_date"] != "2026-09-16"):
                raise ValueError("invalid case metadata")
            if case["case_id"] == "JQ01":
                if type(case["summary"]) is not str or not 1 <= len(case["summary"]) <= 1500:
                    raise ValueError("positive text required")
            elif case["summary"] is not None:
                raise ValueError("missing text required")
            snapshot_for(case)
        return cases
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise CanaryStopped("fixture_invalid_or_unavailable") from None


def _plain_path(path: Path) -> None:
    """Refuse symlinks/junctions before following paths under the fixed root."""
    relative = path.relative_to(ROOT)
    current = ROOT
    for part in relative.parts:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise CanaryStopped("indirect_path_rejected")


def _git(*arguments: str) -> bytes:
    # No shell, filters, checkout, index mutation or unscoped private-file scan.
    return subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True,
                          check=True, timeout=10).stdout


def verify_identity(expected_commit: str, expected_fixture_sha256: str) -> dict:
    """Compare committed blobs even when status hides assume-unchanged files.

    These fixed inputs are text under the bound '* text=auto eol=lf' rule.
    CRLF normalization is used ONLY for blob comparison, never for fixture or
    disk hashes. This is a single-owner consistency check, not isolation from
    an adversarial concurrent process or a proof of installed package bytes.
    """
    if type(expected_commit) is not str or not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise CanaryStopped("invalid_expected_commit")
    if type(expected_fixture_sha256) is not str or expected_fixture_sha256 != FIXTURE_SHA256:
        raise CanaryStopped("fixture_authorization_mismatch")
    try:
        head = _git("rev-parse", "--verify", "HEAD").decode("ascii").strip()
        if head != expected_commit:
            raise CanaryStopped("source_identity_mismatch")
        if _git("status", "--porcelain", "--untracked-files=all", "--", *IDENTITY_PATHS).strip():
            raise CanaryStopped("source_identity_mismatch")
        disk_hashes, committed_hashes = {}, {}
        for name in IDENTITY_PATHS:
            path = ROOT / name
            _plain_path(path)
            raw = path.read_bytes()
            committed = _git("show", f"{expected_commit}:{name}")
            if raw.replace(b"\r\n", b"\n") != committed:
                raise CanaryStopped("committed_content_mismatch")
            disk_hashes[name] = hashlib.sha256(raw).hexdigest()
            committed_hashes[name] = hashlib.sha256(committed).hexdigest()
        if (ROOT / ".gitattributes").read_bytes().replace(b"\r\n", b"\n") != b"* text=auto eol=lf\n":
            raise CanaryStopped("unsupported_text_normalization")
        load_cases()
        locked = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))["package"]
        installed = {name: version(name) for name in DEPENDENCIES}
        if any(value not in {row["version"] for row in locked if row["name"] == name}
               for name, value in installed.items()):
            raise CanaryStopped("installed_dependency_mismatch")
        config = configuration()
        return {"protocol_identity": PROTOCOL_IDENTITY, "commit": head, "fixture_sha256": FIXTURE_SHA256,
                "disk_sha256": disk_hashes, "committed_sha256": committed_hashes,
                "comparison": "CRLF_to_LF_for_fixed_text_paths_only",
                "runtime": {"python": platform.python_version(), **installed},
                "configuration": config, "configuration_sha256": hashlib.sha256(_encoded(config)).hexdigest()}
    except (OSError, subprocess.SubprocessError, PackageNotFoundError, ValueError, TypeError, KeyError):
        raise CanaryStopped("identity_check_unavailable") from None


def validate_output(output_dir: Path) -> Path:
    try:
        output = Path(os.path.abspath(output_dir))
        relative = output.relative_to(ROOT / "outputs")
        if not relative.parts:
            raise CanaryStopped("invalid_output_destination")
        _plain_path(output)
        if output.exists():
            raise CanaryStopped("output_creation_failed_or_occupied")
        if not output.parent.is_dir():
            raise CanaryStopped("invalid_output_destination")
        return output
    except (OSError, ValueError, TypeError):
        raise CanaryStopped("invalid_output_destination") from None


def read_dedicated_key() -> str:
    key = os.environ.get("DASHSCOPE_API_KEY")
    validate_key(key)
    return key


def _stop(ledger: FinalJsonQwenLedger, reason: str) -> None:
    try:
        ledger.stop(reason)
    except CanaryStopped:
        # The ledger preserves received usage in memory if fsync/append fails.
        # There is no repair write or another dispatch after this condition.
        pass


def _publish_result(ledger: FinalJsonQwenLedger, name: str, value: dict) -> None:
    """Publish a fully written/fsynced result without replacing an existing name.

    Only JQ01.json, JQ02.json and summary.json are authoritative result paths.
    The dot-prefixed .pending file is a provisional candidate, even when its
    bytes describe the intended successful result. An interrupted/failed write
    never promotes it. Retain failed candidates for diagnosis; do not resume.

    Same-directory hard linking publishes the completed inode without the
    POSIX rename-overwrite behavior. Unsupported links fail closed, with no
    replacement fallback. This file-fsync boundary is not a promise of directory
    entry durability after power loss or protection from another writer.
    """
    candidate = ledger.output_dir / ("." + name + ".pending")
    destination = ledger.output_dir / name
    try:
        raw = _encoded(value) + b"\n"
        with candidate.open("xb") as stream:
            if stream.write(raw) != len(raw):
                raise OSError("incomplete_result_write")
            stream.flush()
            os.fsync(stream.fileno())
        # Closing is also inside the success boundary, before the public name.
        # link fails if the destination exists, including an occupied symlink.
        os.link(candidate, destination)
    except OSError:
        ledger.stop_reason = "persistence_failed"
        raise CanaryStopped("persistence_failed") from None
    try:
        candidate.unlink()
    except OSError:
        # Optional removal cannot undo an already published complete result.
        # Any leftover .pending name remains non-authoritative, never resumed.
        pass


def _case_gate(case: dict, snapshot, result, records: list[dict], ledger) -> str | None:
    if (ledger.stop_reason is not None or ledger.pending is not None or not records
            or any(record["protocol_accepted"] is not True
                   or record["response_model_matches_authorized"] is not True
                   or record["provider_response_received"] is not True
                   or record["usage_status"] != "complete" or "reported_usage" not in record for record in records)):
        return "transport_observation_failed"
    audit = result.audit
    expected_reason = "final_answer" if case["case_id"] == "JQ01" else "model_abstained"
    if (result.state == "failed" or audit.refusal is not None or audit.downstream_exception_type is not None
            or audit.core.exception_type is not None or audit.core.tool_errors
            or audit.core.terminal_reason not in {"final_answer", "model_abstained"}):
        return "policy_core_failed"
    if (audit.core.no_tools or not 1 <= audit.core.tool_executions <= core.MAX_TOOL_REQUESTS
            or audit.core.tool_attempts != audit.core.tool_executions
            or audit.core.transport_turns != len(records) or audit.downstream_calls != len(records)
            or not 2 <= len(records) <= core.MAX_TURNS or audit.core.terminal_reason != expected_reason):
        return "case_gate_failed"
    # The new final-only wire identity must survive to the observed ledger.
    # This is separate from envelope/evidence admission by the unchanged core.
    if len(audit.advertised_tools) != len(records):
        return "stage_wire_observation_failed"
    for record, advertised in zip(records, audit.advertised_tools, strict=True):
        body = record["request"]
        if record["request_sha256"] != hashlib.sha256(_encoded(body)).hexdigest():
            return "stage_wire_observation_failed"
        if not advertised:
            if (body.get("tool_choice") != "none" or "tools" in body
                    or body.get("response_format") != {"type": "json_object"}):
                return "stage_wire_observation_failed"
        elif (body.get("tool_choice") != "auto" or "response_format" in body
              or tuple(tool["function"]["name"] for tool in body.get("tools", [])) != advertised):
            return "stage_wire_observation_failed"
    if audit.advertised_tools[-1]:
        return "stage_wire_observation_failed"
    # Match native read IDs to a later accepted request's ACTUAL paired tool
    # message. A lookup, wrapper diagnostic or a callback entry alone is not it.
    reads = {call["id"]: (record["request_id"], call) for record in records
             for call in record.get("assistant_message", {}).get("tool_calls", [])
             if call["function"]["name"] == "read_source"
             and core._strict_json(call["function"]["arguments"])["source_id"] == case["source_id"]}
    for record in records:
        messages = record["request"]["messages"]
        for index, message in enumerate(messages):
            call_id = message.get("tool_call_id")
            if (message.get("role") != "tool" or call_id not in reads or not index
                    or reads[call_id][0] >= record["request_id"]
                    or messages[index - 1].get("tool_calls") != [reads[call_id][1]]):
                continue
            delivered = core._strict_json(message["content"])
            observed = [item for item in audit.tool_results if item.call_id == call_id and item.name == "read_source"]
            if delivered.get("source_id") != case["source_id"] or len(observed) != 1:
                continue
            if case["case_id"] == "JQ02":
                if (delivered.get("status") == observed[0].status == "missing_text"
                        and "evidence_id" not in delivered and observed[0].evidence_id is None
                        and result.state == "abstained" and not result.evidence_ids and not result.served_evidence
                        and not audit.forwarded_read_ids and not audit.core.delivered_read_ids):
                    return None
            elif (delivered.get("status") == observed[0].status == "ok"
                    and delivered.get("text") == case["summary"] and delivered.get("start") == 0
                    and delivered.get("end") == delivered.get("stored_length") == len(case["summary"])
                    and delivered.get("window_truncated") is False
                    and delivered.get("snapshot_hash") == snapshot.snapshot_hash
                    and result.state == "answered_with_evidence" and len(result.served_evidence) == 1):
                served = result.served_evidence[0]
                if (result.evidence_ids == audit.forwarded_read_ids == audit.core.delivered_read_ids
                        == (served.evidence_id,)
                        and observed[0].evidence_id == served.evidence_id
                        and all(delivered.get(key) == value for key, value in served.model_dump().items())):
                    return None
    return "case_gate_failed"


def run_canary(*, expected_commit: str, expected_fixture_sha256: str,
               authorize_paid: str, output_dir: Path) -> dict:
    """Separate one-shot entry; an arbitrary caller manifest cannot skip preflight."""
    if type(authorize_paid) is not str or authorize_paid != PROTOCOL_IDENTITY:
        raise CanaryStopped("fresh_protocol_acknowledgement_required")
    identity = verify_identity(expected_commit, expected_fixture_sha256)
    cases = load_cases()
    output = validate_output(output_dir)
    key = read_dedicated_key()
    ledger = FinalJsonQwenLedger(output)
    ledger.save("identity.json", identity)
    ledger.save("authorization.json", {
        "protocol_identity": PROTOCOL_IDENTITY, "operator_acknowledgement": authorize_paid,
        "expected_commit": expected_commit, "expected_fixture_sha256": expected_fixture_sha256,
        "identity_sha256": hashlib.sha256(_encoded(identity)).hexdigest(),
        "configuration_sha256": identity["configuration_sha256"],
        "independent_user_consent_verified": False, "standing_authorization_source": PROTOCOL,
        "parent_operator_only": True, "old_allowance_reused": False,
    })
    transport = FinalJsonQwenFollowupTransport(key, ledger)

    def checked_transport(**kwargs):
        try:
            # Check both sides of the request: observed usage survives identity
            # loss during a reply, but the reply cannot authorize another call.
            if verify_identity(expected_commit, expected_fixture_sha256) != identity:
                raise CanaryStopped("runtime_identity_changed")
            reply = transport(**kwargs)
            if verify_identity(expected_commit, expected_fixture_sha256) != identity:
                raise CanaryStopped("runtime_identity_changed")
            return reply
        except CanaryStopped as exc:
            _stop(ledger, str(exc))
            raise

    outcomes = []
    for case in cases:
        ledger.case_id = case["case_id"]
        snapshot = snapshot_for(case)
        first = len(ledger.records)
        result = run_policy_followup(snapshot, case["question"], transport=checked_transport)
        reason = _case_gate(case, snapshot, result, ledger.records[first:], ledger)
        outcome = {"case_id": case["case_id"], "passed": reason is None,
                   "gate_failure": reason, "result": result.model_dump(mode="json"),
                   "narrow_content_control": "requires_parent_review" if case["case_id"] == "JQ01" else "not_applicable"}
        persisted = False
        try:
            _publish_result(ledger, case["case_id"] + ".json", outcome)
            persisted = True
        except CanaryStopped:
            reason = "persistence_failed"
        outcomes.append({"case_id": case["case_id"], "passed": reason is None,
                         "gate_failure": reason, "case_record_persisted": persisted})
        if reason is not None:
            _stop(ledger, reason)
            break
    summary = {"mode": "synthetic_final_json_qwen_canary", "protocol_identity": PROTOCOL_IDENTITY,
               "passed": len(outcomes) == 2 and all(row["passed"] for row in outcomes)
                         and ledger.stop_reason is None and ledger.pending is None,
               "cases": outcomes, "unrun_cases": [case["case_id"] for case in cases[len(outcomes):]],
               "semantic_support": "not_assessed", "answer_verification": "not_verified",
               "summary_persisted": True, **ledger.summary()}
    try:
        _publish_result(ledger, "summary.json", summary)
    except CanaryStopped:
        summary.update(ledger.summary(), passed=False, summary_persisted=False)
    return summary
