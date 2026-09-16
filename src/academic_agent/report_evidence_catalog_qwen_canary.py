"""Fresh CQ orchestration; frozen adapters do not grant live authorization.

Only the parent operator executes the committed synthetic batch. The independent
runner cap is stricter than the immutable ledger ceiling. No ambient discovery,
old allowance, retry, repair or resume is part of this entry point.
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
from academic_agent.report_evidence_catalog_followup import build_catalog, run_catalog_followup
from academic_agent.report_evidence_catalog_qwen_transport import (
    CatalogQwenFollowupTransport, CatalogQwenLedger, FROZEN_DEPENDENCY_COUPLING,
    TRANSPORT_IDENTITY, catalog_qwen_configuration,
)
from academic_agent.report_evidence_final_json_qwen_canary import _publish_result, _stop
from academic_agent.report_evidence_qwen_canary import CanaryStopped, REQUEST_BYTES, _encoded
from academic_agent.report_evidence_qwen_transport import validate_key
from academic_agent.report_evidence_snapshot import (
    CONTENT_WARNING, ReadArguments, ReportEvidenceSnapshot, SnapshotSource, content_hash,
)

PROTOCOL_IDENTITY = "report_evidence_catalog_qwen_canary_v1"
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = "tests/fixtures/report_evidence_catalog_qwen_canary.json"
FIXTURE_SHA256 = "f0426492e137c33214fc6db7063b89f790f4d19ee416b07eeebff0014313b60c"
PROTOCOL = "docs/prereg-2026-09-16-report-evidence-catalog-qwen-canary.md"
MAX_REQUESTS = 4
MAX_CASE_REQUESTS = 2
# Importing the generic publisher also executes the old module's imports. Bind
# that complete closure, without calling its identity/fixture/runner functions.
IDENTITY_PATHS = tuple(dict.fromkeys((
    ".gitattributes", "src/academic_agent/__init__.py", *FROZEN_DEPENDENCY_COUPLING,
    "src/academic_agent/report_evidence_catalog_qwen_transport.py",
    "src/academic_agent/report_evidence_final_json_qwen_canary.py",
    "src/academic_agent/report_evidence_final_json_qwen_transport.py",
    "src/academic_agent/report_evidence_guarded_followup.py",
    "src/academic_agent/report_evidence_catalog_qwen_canary.py",
    "report_evidence_catalog_canary.py", "tests/test_report_evidence_catalog_qwen_canary.py",
    FIXTURE, PROTOCOL,
)))
DEPENDENCIES = (
    "httpx", "httpcore", "anyio", "certifi", "h11", "idna", "sniffio", "typing-extensions",
    "pydantic", "pydantic-core", "annotated-types", "typing-inspection",
)
CASE_FIELDS = frozenset(("case_id", "target_source_id", "question", "sources"))
SOURCE_FIELDS = frozenset((
    "source_id", "group", "title", "publisher", "accessed_date", "origin", "summary",
))


def configuration() -> dict:
    adapter = catalog_qwen_configuration()
    return {**adapter, "max_requests": MAX_REQUESTS, "adapter_max_requests": adapter["max_requests"],
            "max_requests_per_case": MAX_CASE_REQUESTS, "max_tool_attempts_per_case": 1,
            "protocol_identity": PROTOCOL_IDENTITY, "transport_identity": TRANSPORT_IDENTITY,
            "case_ids": ["CQ01", "CQ02"], "credential_source": "process_DASHSCOPE_API_KEY_only",
            "resume": False, "first_failure_stops_batch": True,
            "acknowledgement_is_independent_consent_verification": False}


def snapshot_for(case: dict) -> ReportEvidenceSnapshot:
    # Gate labels are deliberately not part of any source or question projection.
    return ReportEvidenceSnapshot(report_ref=case["case_id"], sources=tuple(
        SnapshotSource(**source, source_type=source["group"]) for source in case["sources"]))


def load_cases() -> list[dict]:
    try:
        raw = (ROOT / FIXTURE).read_bytes()
        if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
            raise CanaryStopped("fixture_identity_mismatch")
        cases = core._strict_json(raw.decode("utf-8"))
        if type(cases) is not list or len(cases) != 2:
            raise ValueError("invalid case list")
        for case, case_id, prefix, group in zip(cases, ("CQ01", "CQ02"), ("A", "M"),
                                               ("academic", "market"), strict=True):
            if (type(case) is not dict or set(case) != CASE_FIELDS or case["case_id"] != case_id
                    or case["target_source_id"] != prefix + "6" or type(case["question"]) is not str
                    or not 1 <= len(case["question"]) <= 4096
                    or type(case["sources"]) is not list or len(case["sources"]) != 6):
                raise ValueError("invalid case identity")
            for index, source in enumerate(case["sources"], 1):
                missing = case_id == "CQ02" and index == 6
                origin = "unknown" if missing else "abstract" if group == "academic" else "search_snippet"
                if (type(source) is not dict or set(source) != SOURCE_FIELDS
                        or source["source_id"] != prefix + str(index) or source["group"] != group
                        or source["origin"] != origin or source["publisher"] != "Synthetic example"
                        or source["accessed_date"] != "2026-09-16"):
                    raise ValueError("invalid source identity")
                if missing:
                    if source["summary"] is not None:
                        raise ValueError("missing text required")
                elif type(source["summary"]) is not str or not 1 <= len(source["summary"]) <= 1500:
                    raise ValueError("complete readable summary required")
            catalog = build_catalog(snapshot_for(case))
            if (catalog["returned_count"] != 6 or catalog["coverage"] != "complete"
                    or catalog["omitted_count"] != 0 or catalog["title_truncation_count"] != 0):
                raise ValueError("complete six-source catalog required")
        return cases
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise CanaryStopped("fixture_invalid_or_unavailable") from None


def _plain_path(path: Path) -> None:
    current = ROOT
    for part in path.relative_to(ROOT).parts:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise CanaryStopped("indirect_path_rejected")


def _git(*arguments: str) -> bytes:
    # Optional index refresh is unnecessary: this verifier only reads fixed paths.
    return subprocess.run(["git", "--no-optional-locks", *arguments], cwd=ROOT,
                          capture_output=True, check=True, timeout=10).stdout


def verify_identity(expected_commit: str, expected_fixture_sha256: str) -> dict:
    """Check committed blobs as well as disk; versions are not package-byte proof."""
    if type(expected_commit) is not str or not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise CanaryStopped("invalid_expected_commit")
    if type(expected_fixture_sha256) is not str or expected_fixture_sha256 != FIXTURE_SHA256:
        raise CanaryStopped("fixture_authorization_mismatch")
    try:
        head = _git("rev-parse", "--verify", "HEAD").decode("ascii").strip()
        if head != expected_commit or _git("status", "--porcelain", "--untracked-files=all",
                                            "--", *IDENTITY_PATHS).strip():
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
        if not output.relative_to(ROOT / "outputs").parts:
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


class _CheckedTransport:
    """Single-owner runner guard; never changes the adapter or ledger methods."""

    def __init__(self, transport, ledger, identity, first):
        self.transport, self.ledger, self.identity, self.first = transport, ledger, identity, first

    def __call__(self, **kwargs):
        try:
            if self.ledger.stop_reason is not None or self.ledger.pending is not None:
                raise CanaryStopped("runner_unresolved_or_stopped")
            if len(self.ledger.records) >= MAX_REQUESTS:
                raise CanaryStopped("runner_request_limit")
            if len(self.ledger.records) - self.first >= MAX_CASE_REQUESTS:
                raise CanaryStopped("runner_case_request_limit")
            if verify_identity(self.identity["commit"], self.identity["fixture_sha256"]) != self.identity:
                raise CanaryStopped("runtime_identity_changed")
            reply = self.transport(**kwargs)
            if verify_identity(self.identity["commit"], self.identity["fixture_sha256"]) != self.identity:
                raise CanaryStopped("runtime_identity_changed")
            return reply
        except CanaryStopped as exc:
            _stop(self.ledger, str(exc))
            raise
        except Exception:  # noqa: BLE001 -- private exception text never crosses the runner boundary.
            _stop(self.ledger, "runner_preflight_or_transport_failed")
            raise CanaryStopped("runner_preflight_or_transport_failed") from None


def _case_gate(case, snapshot, result, records, ledger):
    """Gate actual accounted request pairs, not callback delivery or prose quality."""
    try:
        return _check_case(case, snapshot, result, records, ledger)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError, RecursionError):
        return "invalid_case_observation"


def _check_case(case, snapshot, result, records, ledger):
    if (ledger.stop_reason is not None or ledger.pending is not None or len(records) != 2
            or any(record["protocol_accepted"] is not True or record["provider_response_received"] is not True
                   or record["response_model_matches_authorized"] is not True
                   or record["usage_status"] != "complete" or "reported_usage" not in record
                   or record["case_id"] != case["case_id"] for record in records)):
        return "transport_observation_failed"
    audit = result.audit
    negative = case["case_id"] == "CQ02"
    reason = "model_abstained" if negative else "final_answer"
    if (result.state == "failed" or audit.refusal is not None or audit.downstream_exception_type is not None
            or audit.core.exception_type is not None or audit.core.tool_errors
            or audit.core.terminal_reason != reason):
        return "policy_core_failed"
    if (audit.core.no_tools or audit.core.tool_attempts != 1 or audit.core.tool_executions != 1
            or audit.core.observed_tool_requests != 1 or audit.core.transport_turns != 2
            or audit.downstream_calls != 2 or len(audit.tool_results) != 1
            or audit.advertised_tools != (("read_source",), ()) or audit.blocked_callback_bytes is not None
            or result.semantic_support != "not_assessed" or result.answer_verification != "not_verified"):
        return "case_gate_failed"
    catalog = build_catalog(snapshot)
    if (audit.catalog_hash != content_hash(catalog) or audit.catalog_bytes != len(_encoded(catalog))
            or audit.total_count != 6 or audit.returned_count != 6 or audit.omitted_count != 0
            or audit.coverage != "complete" or audit.title_truncation_count != 0):
        return "catalog_observation_failed"
    for record in records:
        body = record["request"]
        if (record["request_sha256"] != hashlib.sha256(_encoded(body)).hexdigest()
                or len(_encoded(body)) > REQUEST_BYTES or body["model"] != configuration()["model"]
                or body["messages"][1] != {"role": "user", "content": case["question"]}
                or body["messages"][2] != {"role": "user", "content": _encoded(catalog).decode("ascii")}):
            return "catalog_wire_observation_failed"
    initial, final = (record["request"] for record in records)
    schema = [core.tool_definitions()[1]]
    schema[0]["function"]["parameters"]["properties"]["source_id"]["enum"] = [
        source.source_id for source in snapshot.sources]
    if (initial.get("tool_choice") != "auto" or "response_format" in initial
            or _encoded(initial.get("tools")) != _encoded(schema) or len(initial["messages"]) != 3
            or final.get("tool_choice") != "none" or "tools" in final
            or final.get("response_format") != {"type": "json_object"} or len(final["messages"]) != 5
            or records[1]["request_id"] != records[0]["request_id"] + 1):
        return "catalog_wire_observation_failed"
    native = records[0]["assistant_message"]
    if len(native.get("tool_calls", [])) != 1 or _encoded(final["messages"][3]) != _encoded(native):
        return "case_gate_failed"
    call = native["tool_calls"][0]
    args = ReadArguments.model_validate(core._strict_json(call["function"]["arguments"]))
    tool_message = final["messages"][4]
    observed = audit.tool_results[0]
    if (call["function"]["name"] != "read_source" or args.source_id != case["target_source_id"]
            or audit.core.call_ids != (call["id"],) or observed.call_id != call["id"]
            or set(tool_message) != {"role", "tool_call_id", "content"}
            or tool_message["role"] != "tool" or tool_message["tool_call_id"] != call["id"]):
        return "case_gate_failed"
    delivered = core._strict_json(tool_message["content"])
    target = snapshot.sources[5]
    common = {"source_id": target.source_id, "origin": target.origin,
              "stored_length": target.stored_length, "text_scope": "saved_summary_only"}
    if negative:
        expected = {**common, "status": "missing_text", "content_warning": CONTENT_WARNING}
        if (observed.status != "missing_text" or observed.evidence_id is not None or result.state != "abstained"
                or result.evidence_ids or result.served_evidence or audit.forwarded_read_ids
                or audit.core.delivered_read_ids):
            return "case_gate_failed"
    else:
        if args.offset != 0 or args.length < target.stored_length:
            return "case_gate_failed"
        receipt = {**common, "snapshot_hash": snapshot.snapshot_hash, "source_hash": snapshot.source_hash(target),
                   "summary_hash": content_hash(target.summary), "start": 0, "end": target.stored_length,
                   "text": target.summary, "text_sha256": hashlib.sha256(target.summary.encode("utf-8")).hexdigest(),
                   "window_truncated": False}
        receipt["evidence_id"] = "ev_" + content_hash(receipt)
        expected = {**receipt, "status": "ok", "content_warning": CONTENT_WARNING}
        if (observed.status != "ok" or observed.evidence_id != receipt["evidence_id"]
                or result.state != "answered_with_evidence" or len(result.served_evidence) != 1
                or _encoded(result.served_evidence[0].model_dump()) != _encoded(receipt)
                or result.evidence_ids != (receipt["evidence_id"],)
                or audit.forwarded_read_ids != result.evidence_ids or audit.core.delivered_read_ids != result.evidence_ids):
            return "case_gate_failed"
    if _encoded(delivered) != _encoded(expected):
        return "case_gate_failed"
    message = records[1]["assistant_message"]
    if message.get("tool_calls") or core._strict_json(message["content"]) != {
        "answer": result.answer, "status": "abstained" if negative else "answered",
        "evidence_ids": list(result.evidence_ids),
    }:
        return "case_gate_failed"
    return None


def run_canary(*, expected_commit: str, expected_fixture_sha256: str,
               authorize_paid: str, output_dir: Path) -> dict:
    if type(authorize_paid) is not str or authorize_paid != PROTOCOL_IDENTITY:
        raise CanaryStopped("fresh_protocol_acknowledgement_required")
    identity = verify_identity(expected_commit, expected_fixture_sha256)
    cases = load_cases()
    output = validate_output(output_dir)
    key = read_dedicated_key()
    ledger = CatalogQwenLedger(output)
    experiment = {
        "protocol_identity": PROTOCOL_IDENTITY, "scope": "parent_only_single_synthetic_live_batch",
        "transport_identity": TRANSPORT_IDENTITY, "configuration": configuration(),
        "identity_sha256": hashlib.sha256(_encoded(identity)).hexdigest(),
        "adapter_manifest": "manifest.json", "adapter_manifest_grants_live_authorization": False,
        "standing_authorization_source": PROTOCOL, "old_allowance_reused": False,
    }
    _publish_result(ledger, "identity.json", identity)
    _publish_result(ledger, "experiment_manifest.json", experiment)
    _publish_result(ledger, "authorization.json", {
        "protocol_identity": PROTOCOL_IDENTITY, "operator_acknowledgement": authorize_paid,
        "expected_commit": expected_commit, "expected_fixture_sha256": expected_fixture_sha256,
        "identity_sha256": experiment["identity_sha256"],
        "experiment_manifest_sha256": hashlib.sha256(_encoded(experiment)).hexdigest(),
        "configuration_sha256": identity["configuration_sha256"],
        "standing_authorization_source": PROTOCOL, "independent_user_consent_verified": False,
        "parent_operator_only": True, "old_allowance_reused": False, "max_requests": MAX_REQUESTS,
    })
    outcomes = []
    for case in cases:
        ledger.case_id = case["case_id"]
        snapshot = snapshot_for(case)
        first = len(ledger.records)
        result = None
        try:
            # The adapter owns snapshot/question/history state: never share it
            # across cases even though accounting MUST use the same ledger.
            transport = CatalogQwenFollowupTransport(key, ledger, snapshot=snapshot)
            checked = _CheckedTransport(transport, ledger, identity, first)
            result = run_catalog_followup(snapshot, case["question"], transport=checked)
            reason = _case_gate(case, snapshot, result, ledger.records[first:], ledger)
        except Exception:  # noqa: BLE001 -- preserve accounting, never expose setup or source exception text.
            reason = "case_execution_failed"
        outcome = {"case_id": case["case_id"], "passed": reason is None, "gate_failure": reason,
                   "result": None if result is None else result.model_dump(mode="json"),
                   "narrow_content_control": "requires_parent_review"}
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
    summary = {"mode": "synthetic_catalog_qwen_canary", "protocol_identity": PROTOCOL_IDENTITY,
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
