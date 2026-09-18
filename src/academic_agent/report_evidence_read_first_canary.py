"""Fixed RF batch, identity-only by default; native authority belongs to parent.

Identity/publication patterns are deliberately local rather than delegating to
a closed runner. Original RP callback audits cannot be recovered by stripping
fields from the new forced-choice wire. No dotenv, fallback or production hook.
"""

import argparse
from copy import deepcopy
from decimal import Decimal
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import tomllib

from academic_agent import report_evidence_claim_relation as claim_policy
from academic_agent import report_evidence_followup as core
from academic_agent import report_evidence_relation_policy as policy
from academic_agent import report_evidence_read_first_qwen_transport as native
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_catalog_qwen_transport import _system_content
from academic_agent.report_evidence_qwen_canary import (
    CanaryStopped, INPUT_RATE, INPUT_RESERVATION, MAX_TOKENS, OUTPUT_RATE, RESERVATION_USD, _encoded,
)
from academic_agent.report_evidence_qwen_transport import _usage, validate_key
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource, content_hash

PROTOCOL_IDENTITY = "report_evidence_read_first_qwen_canary_v1"
ROOT = Path(__file__).resolve().parents[2]
FIXED_OUTPUT = "outputs/report_evidence_read_first_qwen_canary_v1"
FIXTURE = "tests/fixtures/report_evidence_read_first_qwen.json"
FIXTURE_SHA256 = "ab4813b2479e14cecbf8834a44979e6f6a01aa847b05ea478c4735aaaa9fc500"
PROTOCOL = "docs/prereg-2026-09-18-read-first-followup.md"
CASE_IDS = ("RF01", "RF02", "RF03")
RELATIONS = ("insufficient", "refuted", "supported")
SOURCE_METADATA = {
    "source_id": "A1", "group": "academic", "title": "Fictional laboratory record",
    "publisher": "Synthetic controls", "source_type": "synthetic_control",
    "origin": "unknown", "accessed_date": "2026-09-18",
}
IDENTITY_PATHS = (
    ".gitattributes", "src/academic_agent/__init__.py", *native.FROZEN_DEPENDENCY_COUPLING,
    "src/academic_agent/report_evidence_read_first_qwen_transport.py",
    "src/academic_agent/report_evidence_read_first_canary.py",
    "tests/test_report_evidence_read_first_qwen_transport.py",
    "tests/test_report_evidence_read_first_canary.py", FIXTURE, PROTOCOL,
)
DEPENDENCIES = (
    "httpx", "httpcore", "anyio", "certifi", "h11", "idna", "sniffio", "typing-extensions",
    "pydantic", "pydantic-core", "annotated-types", "typing-inspection",
)


def configuration():
    return {**native.configuration(), "protocol_identity": PROTOCOL_IDENTITY, "fixed_output": FIXED_OUTPUT,
            "case_ids": list(CASE_IDS), "relations_in_case_order": list(RELATIONS),
            "source_metadata": dict(SOURCE_METADATA), "first_failure_stops_batch": True,
            "credential_source": "process_DASHSCOPE_API_KEY_only", "resume": False,
            "max_requests_per_case": 2, "six_request_reservation_usd": str(RESERVATION_USD * 6),
            "acknowledgement_is_independent_consent_verification": False}


def snapshot_for(case):
    return ReportEvidenceSnapshot(report_ref=case["case_id"], sources=(
        SnapshotSource(**SOURCE_METADATA, summary=case["text"]),))


def load_cases():
    try:
        raw = (ROOT / FIXTURE).read_bytes()
        if native.digest(raw) != FIXTURE_SHA256:
            raise CanaryStopped("fixture_identity_mismatch")
        data = core._strict_json(raw.decode("utf-8"))
        if (type(data["schema_version"]) is not int or data["schema_version"] != 1
                or data["cohort_id"] != "read_first_saved_evidence_development_v1"
                or data["origin"] != "author_generated_synthetic"
                or data["reference_status"] != "llm_label_blinded_context_limited_reviewed"
                or tuple(row["case_id"] for row in data["cases"]) != CASE_IDS):
            raise CanaryStopped("fixture_contract_mismatch")
        cases = tuple(data["cases"])
        for case, relation in zip(cases, RELATIONS, strict=True):
            if (case["expected_relation"] != relation or type(case["claim"]) is not str
                    or not 1 <= len(case["claim"]) <= 4096 or type(case["text"]) is not str
                    or not case["text"].strip()):
                raise CanaryStopped("fixture_contract_mismatch")
            native.admitted_snapshot(snapshot_for(case))
        return cases
    except (OSError, TypeError, ValueError, KeyError, RecursionError):
        raise CanaryStopped("fixture_invalid_or_unavailable") from None


def _plain_path(path):
    path.relative_to(ROOT)
    for current in reversed((path, *path.parents)):
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise CanaryStopped("indirect_path_rejected")


def _git(*arguments):
    return subprocess.run(["git", "--no-optional-locks", *arguments], cwd=ROOT,
                          capture_output=True, check=True, timeout=10).stdout


def verify_identity(expected_commit, expected_fixture_sha256):
    """Bind fixed disk/blob bytes; package versions do not attest package bytes."""
    if type(expected_commit) is not str or not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise CanaryStopped("invalid_expected_commit")
    if type(expected_fixture_sha256) is not str or expected_fixture_sha256 != FIXTURE_SHA256:
        raise CanaryStopped("fixture_authorization_mismatch")
    try:
        head = _git("rev-parse", "--verify", "HEAD").decode("ascii").strip()
        if head != expected_commit or _git("status", "--porcelain", "--untracked-files=all", "--", *IDENTITY_PATHS).strip():
            raise CanaryStopped("source_identity_mismatch")
        disk, committed = {}, {}
        for name in IDENTITY_PATHS:
            path = ROOT / name
            _plain_path(path)
            raw, blob = path.read_bytes(), _git("show", f"{expected_commit}:{name}")
            if raw.replace(b"\r\n", b"\n") != blob:
                raise CanaryStopped("committed_content_mismatch")
            disk[name], committed[name] = native.digest(raw), native.digest(blob)
        if (ROOT / ".gitattributes").read_bytes().replace(b"\r\n", b"\n") != b"* text=auto eol=lf\n":
            raise CanaryStopped("unsupported_text_normalization")
        load_cases()
        locked = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))["package"]
        installed = {name: version(name) for name in DEPENDENCIES}
        if any(value not in {row["version"] for row in locked if row["name"] == name} for name, value in installed.items()):
            raise CanaryStopped("installed_dependency_mismatch")
        config = configuration()
        return {"protocol_identity": PROTOCOL_IDENTITY, "commit": head, "fixture_sha256": FIXTURE_SHA256,
                "disk_sha256": disk, "committed_sha256": committed, "comparison": "CRLF_to_LF_for_fixed_text_paths_only",
                "runtime": {"python": platform.python_version(), **installed},
                "configuration": config, "configuration_sha256": native.digest(_encoded(config))}
    except (OSError, subprocess.SubprocessError, PackageNotFoundError, ValueError, TypeError, KeyError):
        raise CanaryStopped("identity_check_unavailable") from None


def validate_output():
    try:
        output = ROOT / FIXED_OUTPUT
        _plain_path(output)
        if os.path.lexists(output):
            raise CanaryStopped("output_creation_failed_or_occupied")
        if not output.parent.is_dir():
            raise CanaryStopped("invalid_output_destination")
        return output
    except (OSError, ValueError, TypeError):
        raise CanaryStopped("invalid_output_destination") from None


def read_dedicated_key():
    key = os.environ.get("DASHSCOPE_API_KEY")
    validate_key(key)
    return key


def _stop(ledger, reason):
    try:
        ledger.stop(reason)
    except CanaryStopped:
        pass  # Failed persistence still leaves the in-memory stop/usage intact.


def _publish(ledger, name, value):
    """Close/fsync before write-once link publication; pending is not complete."""
    pending, destination = ledger.output_dir / ("." + name + ".pending"), ledger.output_dir / name
    try:
        raw = _encoded(value) + b"\n"
        with pending.open("xb") as stream:
            if stream.write(raw) != len(raw):
                raise OSError("short_write")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(pending, destination)
    except OSError:
        ledger.stop_reason = "persistence_failed"
        raise CanaryStopped("persistence_failed") from None
    try:
        pending.unlink()
    except OSError:
        pass  # Optional cleanup cannot revoke a complete published artifact.


class _CheckedTransport:
    def __init__(self, transport, identity, first):
        self.transport, self.identity, self.first = transport, identity, first

    def _identity(self):
        if verify_identity(self.identity["commit"], self.identity["fixture_sha256"]) != self.identity:
            raise CanaryStopped("runtime_identity_changed")

    def __call__(self, request, /):
        ledger = self.transport.ledger
        try:
            if ledger.stop_reason is not None or ledger.pending is not None:
                raise CanaryStopped("runner_unresolved_or_stopped")
            if len(ledger.records) >= 6 or len(ledger.records) - self.first >= 2:
                raise CanaryStopped("runner_request_limit")
            self._identity()
            try:
                return self.transport(request)
            finally:
                # Rejected replies cost money too; a post-call identity error
                # must never erase the adapter's already observed usage.
                self._identity()
        except CanaryStopped as exc:
            _stop(ledger, str(exc))
            raise
        except Exception:  # noqa: BLE001 -- do not disclose arbitrary callback/setup text.
            _stop(ledger, "runner_preflight_or_transport_failed")
            raise CanaryStopped("runner_preflight_or_transport_failed") from None


def _serialized(result):
    if type(result) is not policy.PolicyResult or type(result.audit) is not policy.PolicyAudit:
        raise CanaryStopped("invalid_case_observation")
    audit, catalog = result.inner.audit, result.inner.audit.catalog
    inner = catalog.core
    counts = (audit.downstream_calls, catalog.downstream_calls, inner.transport_turns,
              inner.observed_tool_requests, inner.tool_attempts, inner.tool_executions, inner.tool_errors,
              catalog.total_count, catalog.returned_count, catalog.omitted_count, catalog.title_truncation_count,
              catalog.catalog_bytes, *audit.callback_bytes, *catalog.callback_bytes,
              *(entry.ordinal for entry in result.audit.callback_entries),
              *(entry.request_bytes for entry in result.audit.callback_entries))
    if any(type(value) is not int or value < 0 for value in counts) or type(inner.no_tools) is not bool:
        raise CanaryStopped("invalid_raw_counter_type")
    observed = result.model_dump(mode="json", warnings="error")
    checked = policy.PolicyResult.model_validate_json(_encoded(observed))
    if _encoded(observed) != _encoded(checked.model_dump(mode="json")):
        raise CanaryStopped("serialized_observation_changed")
    return observed


def _accounting(ledger):
    if type(ledger) is not native.ReadFirstQwenLedger or ledger.stop_reason is not None or ledger.pending is not None:
        return False
    events = [core._strict_json(line) for line in (ledger.output_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()]
    reserved = [row for row in events if row["event"] == "request_reserved"]
    finished = [row for row in events if row["event"] == "request_finished"]
    if not 1 <= len(ledger.records) <= 6 or len(reserved) != len(finished) or len(finished) != len(ledger.records):
        return False
    for index, row in enumerate(ledger.records, 1):
        if (type(row["request_id"]) is not int or row["request_id"] != index
                or row["protocol_accepted"] is not True or row["provider_response_received"] is not True
                or row["response_model_matches_authorized"] is not True or row["usage_status"] != "complete"
                or row["error"] is not None or row["reservation_usd"] != str(RESERVATION_USD)):
            return False
        usage = _usage({"usage": row["reported_usage"]})
        if (usage is None or _encoded(usage) != _encoded(row["reported_usage"])
                or usage["prompt_tokens"] > INPUT_RESERVATION or usage["completion_tokens"] > MAX_TOKENS):
            return False
        cost = (Decimal(usage["prompt_tokens"]) * INPUT_RATE + Decimal(usage["completion_tokens"]) * OUTPUT_RATE) / 1_000_000
        if row["estimated_usd"] != str(cost) or _encoded(finished[index - 1]) != _encoded({"event": "request_finished", **row}):
            return False
        if any(_encoded(reserved[index - 1][key]) != _encoded(row[key]) for key in (
                "request_id", "case_id", "request", "request_sha256", "reservation_usd")):
            return False
    return True


def _wire_audits(case, snapshot, result, transport, records):
    """Compare original callbacks, independent RP entries and transformed bytes.

    Never invert a forced wire choice into a fictitious RP callback. The original
    request was journaled before POST, separately from its reserved native body.
    """
    audit = result.audit
    entries = transport.exchanges
    if (audit.configured_policy_id != policy.POLICY_ID or audit.configured_policy_hash != native.FROZEN_POLICY_SHA256
            or audit.blocked_reason is not None or audit.blocked_callback_bytes is not None
            or audit.callback_exception_type is not None or len(entries) != 2 or len(audit.callback_entries) != 2):
        return False
    events = [core._strict_json(line) for line in (transport.ledger.output_dir / "events.jsonl").read_text(
        encoding="utf-8").splitlines()]
    linked = [row for row in events if row["event"] == "read_first_callback"
              and row["native_ordinal"] in {record["request_id"] for record in records}]
    if _encoded(linked) != _encoded([{"event": "read_first_callback", **entry} for entry in entries]):
        return False
    previous = records[0]["assistant_message"]
    call = native.full_read_call(previous, "A1")
    claim_sizes, catalog_sizes = [], []
    for index, (entry, rp, record) in enumerate(zip(entries, audit.callback_entries, records, strict=True)):
        request = entry["request"]
        tool = request["messages"][-1] if index else None
        if index and (set(tool) != {"role", "content", "tool_call_id"} or tool["role"] != "tool"
                      or tool["tool_call_id"] != call["id"]
                      or _encoded(core._strict_json(tool["content"])) != _encoded(native.expected_read_result(snapshot))):
            return False
        expected = native.callback_template(snapshot, case["claim"], previous=previous if index else None, tool_message=tool)
        if _encoded(expected) != _encoded(request):
            return False
        original, wire = _encoded(request), _encoded(native.native_body(request))
        facts = native.read_facts(request)
        rp_expected = {"ordinal": index + 1, "request_hash": native.digest(original), "request_bytes": len(original),
                       "policy_hash": native.FROZEN_POLICY_SHA256, **facts}
        expected_entry = {**rp_expected, "request": request, "tool_choice": "auto" if not index else "none",
                          "transform_identity": native.TRANSFORM_IDENTITY, "native_ordinal": record["request_id"],
                          "native_body_hash": native.digest(wire), "native_body_bytes": len(wire)}
        if (_encoded(rp.model_dump(mode="json")) != _encoded(rp_expected) or _encoded(entry) != _encoded(expected_entry)
                or wire != _encoded(record["request"]) or record["request_sha256"] != native.digest(wire)
                or len(wire) > 12 * 1024 or len(original) > 12 * 1024):
            return False
        # Inner-to-policy delivery precedes the RP append; do not inflate those
        # counters with policy/native overhead or copy RP delivery into them.
        catalog_system = _system_content(snapshot, not index)
        claim_system = catalog_system.replace(claim_policy._OLD_FINAL, claim_policy._NEW_FINAL, 1)
        for system, sizes in ((catalog_system, catalog_sizes), (claim_system, claim_sizes)):
            before = deepcopy(request)
            before["messages"][0]["content"] = system
            sizes.append(len(_encoded(before)))
    return (result.inner.audit.callback_bytes == tuple(claim_sizes)
            and result.inner.audit.catalog.callback_bytes == tuple(catalog_sizes)
            and records[1]["request_id"] == records[0]["request_id"] + 1)


def _case_gate(case, snapshot, result, transport, first):
    """Engineering admission only; reference agreement is a subsequent gate."""
    try:
        observed = _serialized(result)
        result = policy.PolicyResult.model_validate_json(_encoded(observed))
        ledger, inner = transport.ledger, result.inner
        records = ledger.records[first:]
        if len(records) != 2 or not _accounting(ledger) or any(row["case_id"] != case["case_id"] for row in records):
            return "transport_observation_failed"
        if not _wire_audits(case, snapshot, result, transport, records):
            return "callback_native_audit_failed"
        audit, assessment = inner.audit, inner.model_assessment
        catalog, execution = audit.catalog, audit.catalog.core
        if (assessment is None or inner.claim != case["claim"] or inner.answer != assessment.answer
                or audit.refusal is not None or audit.downstream_exception_type is not None
                or catalog.refusal is not None or catalog.downstream_exception_type is not None
                or execution.exception_type is not None or audit.blocked_callback_bytes is not None
                or catalog.blocked_callback_bytes is not None):
            return "policy_core_failed"
        answered = assessment.claim_relation in {"supported", "refuted"}
        if (assessment.claim_relation not in RELATIONS or inner.state != ("answered_with_evidence" if answered else "abstained")
                or execution.terminal_reason != ("final_answer" if answered else "model_abstained")
                or inner.read_status != "usable_text" or audit.read_result_reason != "ok"
                or execution.tool_attempts != 1 or execution.tool_executions != 1 or execution.observed_tool_requests != 1
                or execution.tool_errors != 0 or execution.no_tools or execution.transport_turns != 2
                or audit.downstream_calls != 2 or catalog.downstream_calls != 2
                or catalog.advertised_tools != (("read_source",), ())
                or inner.semantic_support != "not_assessed" or inner.answer_verification != "not_verified"
                or inner.assessment_origin != "injected_transport_unverified"):
            return "claim_wrapper_observation_failed"
        expected_catalog = build_catalog(snapshot)
        if (catalog.catalog_hash != content_hash(expected_catalog) or catalog.catalog_bytes != len(_encoded(expected_catalog))
                or (catalog.total_count, catalog.returned_count, catalog.omitted_count, catalog.title_truncation_count)
                != (1, 1, 0, 0) or catalog.coverage != "complete"):
            return "catalog_observation_failed"
        expected = native.expected_read_result(snapshot)
        receipt = {key: expected[key] for key in core.ServedEvidence.model_fields}
        ids = (receipt["evidence_id"],)
        call_id = records[0]["assistant_message"]["tool_calls"][0]["id"]
        if (_encoded([row.model_dump() for row in inner.served_evidence]) != _encoded([receipt])
                or audit.delivered_read_ids != ids or audit.usable_read_ids != ids
                or catalog.forwarded_read_ids != ids or execution.delivered_read_ids != ids
                or execution.call_ids != (call_id,)
                or _encoded([row.model_dump() for row in catalog.tool_results]) != _encoded([
                    {"call_id": call_id, "status": "ok", "evidence_id": ids[0]}])
                or assessment.supporting_evidence_ids != (list(ids) if answered else [])):
            return "full_read_receipt_failed"
        message = records[1]["assistant_message"]
        if (message.get("tool_calls") or message.get("refusal")
                or _encoded(core._strict_json(message["content"])) != _encoded(assessment.model_dump())):
            return "native_assessment_failed"
        return None
    except (CanaryStopped, OSError, KeyError, IndexError, TypeError, ValueError, AttributeError, RecursionError):
        return "invalid_case_observation"


def run_canary(*, expected_commit, expected_fixture_sha256, authorize_paid):
    if type(authorize_paid) is not str or authorize_paid != PROTOCOL_IDENTITY:
        raise CanaryStopped("fresh_protocol_acknowledgement_required")
    identity = verify_identity(expected_commit, expected_fixture_sha256)
    cases = load_cases()
    validate_output()
    key = read_dedicated_key()
    ledger = native.ReadFirstQwenLedger(validate_output())
    experiment = {"protocol_identity": PROTOCOL_IDENTITY, "configuration": configuration(),
                  "identity_sha256": native.digest(_encoded(identity)), "parent_operator_only": True,
                  "adapter_manifest_grants_live_authorization": False, "old_allowance_reused": False}
    _publish(ledger, "identity.json", identity)
    _publish(ledger, "experiment_manifest.json", experiment)
    _publish(ledger, "authorization.json", {
        "operator_acknowledgement": authorize_paid, "expected_commit": expected_commit,
        "expected_fixture_sha256": expected_fixture_sha256, "standing_authorization_source": PROTOCOL,
        "identity_sha256": experiment["identity_sha256"], "experiment_manifest_sha256": native.digest(_encoded(experiment)),
        "independent_user_consent_verified": False, "parent_operator_only": True, "old_allowance_reused": False})
    outcomes = []
    for case in cases:
        ledger.case_id = case["case_id"]
        first, result, observed, availability = len(ledger.records), None, None, None
        try:
            snapshot = snapshot_for(case)
            transport = native.ReadFirstQwenFollowupTransport(key, ledger, snapshot=snapshot, claim=case["claim"])
            result = policy.run_relation_policy_followup(
                snapshot, case["claim"], callback=_CheckedTransport(transport, identity, first))
            reason = _case_gate(case, snapshot, result, transport, first)
            observed = _serialized(result)
            availability = native.availability_audit(snapshot, result, records=ledger.records[first:])
        except Exception:  # noqa: BLE001 -- keep usage and safe categories, never arbitrary downstream text.
            reason = "case_execution_failed"
        mechanical = reason is None
        label = result.inner.model_assessment.claim_relation == case["expected_relation"] if mechanical else None
        if mechanical and label is not True:
            reason = "expected_relation_mismatch"
        outcome = {"case_id": case["case_id"], "mechanical_passed": mechanical, "label_match_passed": label,
                   "gate_failure": reason, "semantic_review": "pending" if mechanical else "not_reviewable",
                   "availability": availability, "result": observed,
                   "message_representation": "projected_native_assistant_message_not_raw_http"}
        persisted = False
        try:
            _publish(ledger, case["case_id"] + ".json", outcome)
            persisted = True
        except CanaryStopped:
            reason = "persistence_failed"
        outcomes.append({**{key: value for key, value in outcome.items() if key != "result"},
                         "gate_failure": reason, "case_record_persisted": persisted})
        if reason is not None:
            _stop(ledger, reason)
            break
    labels = [row["label_match_passed"] for row in outcomes]
    summary = {
        "protocol_identity": PROTOCOL_IDENTITY, "mode": "synthetic_read_first_qwen_canary",
        "batch_passed": len(outcomes) == 3 and all(
            row["mechanical_passed"] and row["label_match_passed"] is True and row["case_record_persisted"]
            for row in outcomes) and ledger.stop_reason is None and ledger.pending is None
            and ledger.summary()["unknown_usage_requests"] == 0,
        "mechanically_passed_cases": sum(row["mechanical_passed"] for row in outcomes),
        "label_match_passed": False if False in labels else True if len(labels) == 3 and all(labels) else None,
        "label_checks": sum(label is not None for label in labels), "label_matches": sum(label is True for label in labels),
        "cases": outcomes, "unrun_cases": list(CASE_IDS[len(outcomes):]),
        "semantic_review": "pending" if any(row["mechanical_passed"] for row in outcomes) else "not_reviewable",
        "semantic_support": "not_assessed", "answer_verification": "not_verified",
        "summary_persisted": True, **ledger.summary(),
    }
    try:
        _publish(ledger, "summary.json", summary)
    except CanaryStopped:
        summary.update(ledger.summary(), batch_passed=False, summary_persisted=False)
    return summary


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "invalid_read_first_canary_arguments\n")


def main(argv=None):
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-fixture-sha256", required=True)
    parser.add_argument("--authorize-paid", help="Exact RF acknowledgement, not consent/review/CI verification.")
    args = parser.parse_args(argv)
    try:
        if args.authorize_paid is None:
            identity = verify_identity(args.expected_commit, args.expected_fixture_sha256)
            print(json.dumps({"mode": "identity_only", "identity_verified": True, "live_authorized": False,
                              "identity": identity}, ensure_ascii=True))
            return 0
        result = run_canary(expected_commit=args.expected_commit, expected_fixture_sha256=args.expected_fixture_sha256,
                            authorize_paid=args.authorize_paid)
        print(json.dumps(result, ensure_ascii=True))
        return 0 if result["batch_passed"] and result["summary_persisted"] else 1
    except CanaryStopped:
        error = "read_first_canary_admission_or_persistence_failed"
    except Exception:  # noqa: BLE001 -- CLI diagnostics must not expose keys or arbitrary exception strings.
        error = "read_first_canary_setup_failed"
    print(json.dumps({"batch_passed": False, "semantic_review": "not_reviewable", "error": error}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
