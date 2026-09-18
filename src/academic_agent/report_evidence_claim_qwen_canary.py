"""One fresh, fixed-output CLQ batch; no production route or inherited authority.

Identity/dispatch checks are adapted from the frozen CQ runner, not imported
from it. The exact claim ledger and adapter own payment accounting and HTTP.
The parent, not this acknowledgement parser, verifies review/CI/live authority.
"""

from decimal import Decimal
import hashlib
from importlib.metadata import PackageNotFoundError, version
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
import tomllib

from academic_agent import report_evidence_claim_relation as claim_policy
from academic_agent import report_evidence_followup as core
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_catalog_qwen_transport import _system_content
from academic_agent.report_evidence_claim_qwen_transport import (
    ClaimQwenFollowupTransport, ClaimQwenLedger, FROZEN_DEPENDENCY_COUPLING,
    TRANSPORT_IDENTITY, claim_qwen_configuration,
)
from academic_agent.report_evidence_qwen_canary import (
    CanaryStopped, INPUT_RATE, INPUT_RESERVATION, MAX_TOKENS, MODEL, OUTPUT_RATE,
    REQUEST_BYTES, RESERVATION_USD, _encoded,
)
from academic_agent.report_evidence_qwen_transport import _usage, validate_key
from academic_agent.report_evidence_snapshot import (
    CONTENT_WARNING, ReadArguments, ReportEvidenceSnapshot, SnapshotSource, content_hash,
)

PROTOCOL_IDENTITY = "report_evidence_claim_qwen_canary_v1"
ROOT = Path(__file__).resolve().parents[2]
FIXED_OUTPUT = "outputs/report_evidence_claim_qwen_canary_v1"
FIXTURE = "tests/fixtures/report_evidence_claim_qwen_canary.json"
FIXTURE_SHA256 = "d89f3a0f00888b01ff678043be87949fed538d5575d43c6caff785190a2af624"
PROTOCOL = "docs/prereg-2026-09-16-claim-qwen-canary.md"
MAX_REQUESTS = 6
MAX_CASE_REQUESTS = 2
CASE_IDS = ("CLQ01", "CLQ02", "CLQ03")
RELATIONS = ("supported", "refuted", "insufficient")
IDENTITY_PATHS = tuple(dict.fromkeys((
    ".gitattributes", "src/academic_agent/__init__.py", *FROZEN_DEPENDENCY_COUPLING,
    "src/academic_agent/report_evidence_claim_qwen_transport.py",
    "tests/test_report_evidence_claim_qwen_transport.py",
    "src/academic_agent/report_evidence_claim_qwen_canary.py",
    "report_evidence_claim_canary.py", "tests/test_report_evidence_claim_qwen_canary.py",
    FIXTURE, PROTOCOL,
)))
DEPENDENCIES = (
    "httpx", "httpcore", "anyio", "certifi", "h11", "idna", "sniffio", "typing-extensions",
    "pydantic", "pydantic-core", "annotated-types", "typing-inspection",
)
CASE_FIELDS = frozenset(("case_id", "target_source_id", "claim", "expected_relation", "sources"))
SOURCE_FIELDS = frozenset((
    "source_id", "group", "title", "publisher", "accessed_date", "origin", "summary",
))


def configuration() -> dict:
    adapter = claim_qwen_configuration()
    return {**adapter, "max_requests": MAX_REQUESTS, "adapter_max_requests": adapter["max_requests"],
            "max_requests_per_case": MAX_CASE_REQUESTS, "max_tool_attempts_per_case": 1,
            "protocol_identity": PROTOCOL_IDENTITY, "transport_identity": TRANSPORT_IDENTITY,
            "case_ids": list(CASE_IDS), "credential_source": "process_DASHSCOPE_API_KEY_only",
            "fixed_output": FIXED_OUTPUT, "resume": False, "first_failure_stops_batch": True,
            "six_request_reservation_usd": str(RESERVATION_USD * MAX_REQUESTS),
            "acknowledgement_is_independent_consent_verification": False}


def snapshot_for(case: dict) -> ReportEvidenceSnapshot:
    # Local expected labels/target IDs never enter the model projection.
    return ReportEvidenceSnapshot(report_ref=case["case_id"], sources=tuple(
        SnapshotSource(**source, source_type=source["group"]) for source in case["sources"]))


def load_cases() -> list[dict]:
    try:
        raw = (ROOT / FIXTURE).read_bytes()
        if hashlib.sha256(raw).hexdigest() != FIXTURE_SHA256:
            raise CanaryStopped("fixture_identity_mismatch")
        cases = core._strict_json(raw.decode("utf-8"))
        if type(cases) is not list or len(cases) != 3:
            raise ValueError("invalid case list")
        for case, case_id, relation in zip(cases, CASE_IDS, RELATIONS, strict=True):
            if (type(case) is not dict or set(case) != CASE_FIELDS or case["case_id"] != case_id
                    or case["target_source_id"] != "A1" or case["expected_relation"] != relation
                    or type(case["claim"]) is not str or not 1 <= len(case["claim"]) <= 4096
                    or type(case["sources"]) is not list or len(case["sources"]) != 1):
                raise ValueError("invalid case identity")
            source = case["sources"][0]
            if (type(source) is not dict or set(source) != SOURCE_FIELDS or source["source_id"] != "A1"
                    or source["group"] != "academic" or source["origin"] != "abstract"
                    or source["publisher"] != "Synthetic example" or source["accessed_date"] != "2026-09-16"
                    or type(source["title"]) is not str or not source["title"].strip()
                    or type(source["summary"]) is not str or not source["summary"].strip()
                    or not 1 <= len(source["summary"]) < 500):
                raise ValueError("invalid synthetic source")
            catalog = build_catalog(snapshot_for(case))
            if (catalog["returned_count"] != 1 or catalog["coverage"] != "complete"
                    or catalog["omitted_count"] != 0 or catalog["title_truncation_count"] != 0):
                raise ValueError("complete single-source catalog required")
        return cases
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        raise CanaryStopped("fixture_invalid_or_unavailable") from None


def _plain_path(path: Path) -> None:
    # Check ROOT too: resolving a child alone would conceal an indirect ancestor.
    path.relative_to(ROOT)
    for current in reversed((path, *path.parents)):
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise CanaryStopped("indirect_path_rejected")


def _git(*arguments: str) -> bytes:
    return subprocess.run(["git", "--no-optional-locks", *arguments], cwd=ROOT,
                          capture_output=True, check=True, timeout=10).stdout


def verify_identity(expected_commit: str, expected_fixture_sha256: str) -> dict:
    """CQ-derived fixed-text blob/disk checks; versions do not attest package bytes."""
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


def validate_output() -> Path:
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


def read_dedicated_key() -> str:
    key = os.environ.get("DASHSCOPE_API_KEY")
    validate_key(key)
    return key


def _stop(ledger: ClaimQwenLedger, reason: str) -> None:
    # Copied from JQ's tiny stop helper to avoid executing JQ/guarded imports.
    try:
        ledger.stop(reason)
    except CanaryStopped:
        # Failed append retains observed usage and blocks dispatch; never repair.
        pass


def _publish_result(ledger: ClaimQwenLedger, name: str, value: dict) -> None:
    """JQ-derived write/fsync/close/link publication, with no old runner import.

    A pending file is never authoritative, even if it contains success-shaped
    bytes. A same-directory hard link cannot replace an occupied destination.
    Unsupported linking fails closed. This is not power-loss/directory-fsync
    durability or protection against hostile deletion by a different writer.
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
        os.link(candidate, destination)
    except OSError:
        ledger.stop_reason = "persistence_failed"
        raise CanaryStopped("persistence_failed") from None
    try:
        candidate.unlink()
    except OSError:
        # Optional cleanup cannot revoke an already published complete result.
        pass


def _full_read_call(message, case, snapshot):
    calls = core._assistant_message(message).get("tool_calls") or []
    if len(calls) != 1:
        raise CanaryStopped("full_native_read_required")
    call = calls[0]
    args = ReadArguments.model_validate(core._strict_json(call["function"]["arguments"]))
    if (call["function"]["name"] != "read_source" or args.source_id != case["target_source_id"]
            or args.offset != 0 or args.length < snapshot.sources[0].stored_length):
        raise CanaryStopped("full_native_read_required")
    return call


class _CheckedTransport:
    """CQ-derived guard around the exact adapter, never a ledger subclass."""

    def __init__(self, transport, ledger, identity, first, case, snapshot):
        self.transport, self.ledger, self.identity = transport, ledger, identity
        self.first, self.case, self.snapshot = first, case, snapshot

    def _identity(self):
        if verify_identity(self.identity["commit"], self.identity["fixture_sha256"]) != self.identity:
            raise CanaryStopped("runtime_identity_changed")

    def __call__(self, **kwargs):
        try:
            if self.ledger.stop_reason is not None or self.ledger.pending is not None:
                raise CanaryStopped("runner_unresolved_or_stopped")
            if len(self.ledger.records) >= MAX_REQUESTS:
                raise CanaryStopped("runner_request_limit")
            count = len(self.ledger.records) - self.first
            if count >= MAX_CASE_REQUESTS:
                raise CanaryStopped("runner_case_request_limit")
            self._identity()
            try:
                reply = self.transport(**kwargs)
            finally:
                # A rejected response can still cost money. Check post-call
                # drift on errors too, without deleting the adapter's usage.
                self._identity()
            if count == 0:
                # The adapter permits partial reads generally; this one batch
                # does not. Stop before a second paid turn, never repair args.
                _full_read_call(reply, self.case, self.snapshot)
            return reply
        except CanaryStopped as exc:
            _stop(self.ledger, str(exc))
            raise
        except Exception:  # noqa: BLE001 -- arbitrary downstream text is never a runner diagnostic.
            _stop(self.ledger, "runner_preflight_or_transport_failed")
            raise CanaryStopped("runner_preflight_or_transport_failed") from None


def _check_accounting(case, records, ledger):
    if (type(ledger) is not ClaimQwenLedger or ledger.stop_reason is not None or ledger.pending is not None
            or len(records) != 2 or len(ledger.records) > MAX_REQUESTS):
        return False
    # Journal equality is separate from callback lengths and in-memory rows.
    events = [core._strict_json(line) for line in (ledger.output_dir / "events.jsonl").read_text(
        encoding="utf-8").splitlines()]
    reserved = [row for row in events if row["event"] == "request_reserved"]
    finished = [row for row in events if row["event"] == "request_finished"]
    if len(reserved) != len(finished) or len(finished) != len(ledger.records):
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
        cost = (Decimal(usage["prompt_tokens"]) * INPUT_RATE
                + Decimal(usage["completion_tokens"]) * OUTPUT_RATE) / 1_000_000
        if row["estimated_usd"] != str(cost) or _encoded(finished[index - 1]) != _encoded(
                {"event": "request_finished", **row}):
            return False
        intent = reserved[index - 1]
        if any(_encoded(intent[key]) != _encoded(row[key]) for key in (
                "request_id", "case_id", "request", "request_sha256", "reservation_usd")):
            return False
    return all(row["case_id"] == case["case_id"] for row in records)


def _case_gate(case, snapshot, result, records, ledger):
    """Mechanical admission only; frozen label agreement is checked separately."""
    try:
        return _check_case(case, snapshot, result, records, ledger)
    except (OSError, KeyError, IndexError, TypeError, ValueError, AttributeError, RecursionError):
        return "invalid_case_observation"


def _check_case(case, snapshot, result, records, ledger):
    if not _check_accounting(case, records, ledger):
        return "transport_observation_failed"
    audit, assessment = result.audit, result.model_assessment
    catalog_audit, inner = audit.catalog, audit.catalog.core
    if (result.state == "failed" or assessment is None or result.claim != case["claim"]
            or audit.refusal is not None or audit.downstream_exception_type is not None
            or catalog_audit.refusal is not None or catalog_audit.downstream_exception_type is not None
            or inner.exception_type is not None or inner.tool_errors):
        return "policy_core_failed"
    relation = assessment.claim_relation
    answered = relation in {"supported", "refuted"}
    if (relation not in RELATIONS or result.state != ("answered_with_evidence" if answered else "abstained")
            or inner.terminal_reason != ("final_answer" if answered else "model_abstained")
            or result.answer != assessment.answer or result.read_status != "usable_text"
            or audit.method_id != claim_policy.METHOD_ID or audit.read_result_reason != "ok"
            or audit.blocked_callback_bytes is not None or catalog_audit.blocked_callback_bytes is not None
            or inner.no_tools or inner.tool_attempts != 1 or inner.tool_executions != 1
            or inner.observed_tool_requests != 1 or inner.transport_turns != 2
            or audit.downstream_calls != 2 or catalog_audit.downstream_calls != 2
            or catalog_audit.advertised_tools != (("read_source",), ())
            or len(catalog_audit.tool_results) != 1
            or result.semantic_support != "not_assessed" or result.answer_verification != "not_verified"
            or result.assessment_origin != "injected_transport_unverified"):
        return "claim_wrapper_observation_failed"
    catalog = build_catalog(snapshot)
    if (catalog_audit.catalog_hash != content_hash(catalog) or catalog_audit.catalog_bytes != len(_encoded(catalog))
            or catalog_audit.total_count != 1 or catalog_audit.returned_count != 1 or catalog_audit.omitted_count != 0
            or catalog_audit.coverage != "complete" or catalog_audit.title_truncation_count != 0):
        return "catalog_observation_failed"
    schema = [core.tool_definitions()[1]]
    schema[0]["function"]["parameters"]["properties"]["source_id"]["enum"] = ["A1"]
    claim_sizes, catalog_sizes = [], []
    for index, record in enumerate(records):
        body = record["request"]
        wire = _encoded(body)
        can_read = index == 0
        system = _system_content(snapshot, can_read).replace(claim_policy._OLD_FINAL, claim_policy._NEW_FINAL, 1)
        messages = body["messages"]
        if (record["request_sha256"] != hashlib.sha256(wire).hexdigest() or len(wire) > REQUEST_BYTES
                or len(messages) != (3 if can_read else 5) or messages[:3] != [
                    {"role": "system", "content": system}, {"role": "user", "content": case["claim"]},
                    {"role": "user", "content": _encoded(catalog).decode("ascii")}]):
            return "claim_wire_observation_failed"
        expected = {"model": MODEL, "messages": messages, "tool_choice": "auto" if can_read else "none",
                    "stream": False, "enable_thinking": False, "parallel_tool_calls": False,
                    "temperature": 0, "max_tokens": MAX_TOKENS}
        expected.update({"tools": schema} if can_read else {"response_format": {"type": "json_object"}})
        if wire != _encoded(expected):
            return "claim_wire_observation_failed"
        callback = {"messages": messages, "tools": schema if can_read else [],
                    "tool_choice": expected["tool_choice"]}
        claim_sizes.append(len(_encoded(callback)))
        old_messages = [{"role": "system", "content": _system_content(snapshot, can_read)}, *messages[1:]]
        catalog_sizes.append(len(_encoded({**callback, "messages": old_messages})))
    if (audit.callback_bytes != tuple(claim_sizes) or catalog_audit.callback_bytes != tuple(catalog_sizes)
            or any(size > REQUEST_BYTES for size in claim_sizes + catalog_sizes)
            or records[1]["request_id"] != records[0]["request_id"] + 1):
        return "callback_observation_failed"
    native = records[0]["assistant_message"]
    call = _full_read_call(native, case, snapshot)
    final_messages = records[1]["request"]["messages"]
    if _encoded(final_messages[3]) != _encoded(native):
        return "native_read_pairing_failed"
    target = snapshot.sources[0]
    receipt = {"source_id": target.source_id, "origin": target.origin, "stored_length": target.stored_length,
               "text_scope": "saved_summary_only", "snapshot_hash": snapshot.snapshot_hash,
               "source_hash": snapshot.source_hash(target), "summary_hash": content_hash(target.summary),
               "start": 0, "end": target.stored_length, "text": target.summary,
               "text_sha256": hashlib.sha256(target.summary.encode("utf-8")).hexdigest(), "window_truncated": False}
    receipt["evidence_id"] = "ev_" + content_hash(receipt)
    ids = (receipt["evidence_id"],)
    tool_message, observed = final_messages[4], catalog_audit.tool_results[0]
    if (set(tool_message) != {"role", "tool_call_id", "content"} or tool_message["role"] != "tool"
            or tool_message["tool_call_id"] != call["id"] or inner.call_ids != (call["id"],)
            or observed.call_id != call["id"] or observed.status != "ok" or observed.evidence_id != ids[0]
            or _encoded(core._strict_json(tool_message["content"])) != _encoded(
                {**receipt, "status": "ok", "content_warning": CONTENT_WARNING})
            or len(result.served_evidence) != 1 or _encoded(result.served_evidence[0].model_dump()) != _encoded(receipt)
            or audit.delivered_read_ids != ids or audit.usable_read_ids != ids
            or catalog_audit.forwarded_read_ids != ids or inner.delivered_read_ids != ids
            or assessment.supporting_evidence_ids != (list(ids) if answered else [])):
        return "full_read_receipt_failed"
    message = records[1]["assistant_message"]
    if (message.get("tool_calls") or message.get("refusal") or _encoded(core._strict_json(message["content"]))
            != _encoded(assessment.model_dump())):
        return "native_assessment_failed"
    return None


def run_canary(*, expected_commit: str, expected_fixture_sha256: str, authorize_paid: str) -> dict:
    if type(authorize_paid) is not str or authorize_paid != PROTOCOL_IDENTITY:
        raise CanaryStopped("fresh_protocol_acknowledgement_required")
    identity = verify_identity(expected_commit, expected_fixture_sha256)
    cases = load_cases()
    output = validate_output()
    key = read_dedicated_key()
    # mkdir(exist_ok=False) in this EXACT type arbitrates competing admissions.
    # Recheck indirect paths after key lookup, before any ledger construction.
    validate_output()
    ledger = ClaimQwenLedger(output)
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
        first, result = len(ledger.records), None
        try:
            snapshot = snapshot_for(case)
            transport = ClaimQwenFollowupTransport(key, ledger, snapshot=snapshot, claim=case["claim"])
            checked = _CheckedTransport(transport, ledger, identity, first, case, snapshot)
            result = claim_policy.run_claim_relation_followup(snapshot, case["claim"], transport=checked)
            reason = _case_gate(case, snapshot, result, ledger.records[first:], ledger)
        except Exception:  # noqa: BLE001 -- preserve accounting, never disclose downstream exception text.
            reason = "case_execution_failed"
        mechanical = reason is None
        label = result.model_assessment.claim_relation == case["expected_relation"] if mechanical else None
        if mechanical and label is not True:
            reason = "expected_relation_mismatch"
        outcome = {"case_id": case["case_id"], "mechanical_passed": mechanical, "label_match_passed": label,
                   "semantic_review": "pending" if mechanical else "not_reviewable", "gate_failure": reason,
                   "result": None if result is None else result.model_dump(mode="json")}
        persisted = False
        try:
            _publish_result(ledger, case["case_id"] + ".json", outcome)
            persisted = True
        except CanaryStopped:
            reason, mechanical = "persistence_failed", False
        outcomes.append({**{key: value for key, value in outcome.items() if key != "result"},
                         "mechanical_passed": mechanical, "gate_failure": reason, "case_record_persisted": persisted})
        if reason is not None:
            _stop(ledger, reason)
            break
    labels = [row["label_match_passed"] for row in outcomes]
    summary = {
        "mode": "synthetic_claim_qwen_canary", "protocol_identity": PROTOCOL_IDENTITY,
        "mechanical_passed": len(outcomes) == 3 and all(row["mechanical_passed"] for row in outcomes)
                             and ledger.stop_reason is None and ledger.pending is None,
        "label_match_passed": False if False in labels else True if len(labels) == 3 and all(labels) else None,
        "semantic_review": "pending" if any(row["semantic_review"] == "pending" for row in outcomes) else "not_reviewable",
        "cases": outcomes, "unrun_cases": [case["case_id"] for case in cases[len(outcomes):]],
        "semantic_support": "not_assessed", "answer_verification": "not_verified",
        "summary_persisted": True, **ledger.summary(),
    }
    try:
        _publish_result(ledger, "summary.json", summary)
    except CanaryStopped:
        summary.update(ledger.summary(), mechanical_passed=False, summary_persisted=False)
    return summary
