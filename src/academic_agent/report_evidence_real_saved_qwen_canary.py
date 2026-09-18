"""One private RS batch, never a production route or historical reuse permit.

The parent alone may exercise the separately recorded authority after review,
CI and commit freeze. Packet hashes bind private bytes, not source truth; the
old preparation's commit/runtime are provenance, not current code authority.
"""

from dataclasses import dataclass
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
from academic_agent import report_evidence_real_saved_eval as rs
from academic_agent.report_evidence_catalog_followup import (
    MAX_CALLBACK_BYTES, build_catalog, run_catalog_followup,
)
from academic_agent.report_evidence_catalog_qwen_transport import (
    CatalogQwenFollowupTransport, CatalogQwenLedger, FROZEN_DEPENDENCY_COUPLING,
    TRANSPORT_IDENTITY, catalog_qwen_configuration,
)
from academic_agent.report_evidence_final_json_qwen_canary import _publish_result, _stop
from academic_agent.report_evidence_qwen_canary import CanaryStopped, REQUEST_BYTES, _encoded
from academic_agent.report_evidence_qwen_transport import validate_key
from academic_agent.report_evidence_snapshot import ReadArguments, content_hash, read_source

PROTOCOL_IDENTITY = "report_evidence_real_saved_qwen_canary_v1"
ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = "docs/prereg-2026-09-16-report-evidence-real-saved-qwen.md"
OFFLINE_PROTOCOL = "docs/prereg-2026-09-16-report-evidence-real-saved-offline.md"
MANIFEST = "packet-manifest.json"
MANIFEST_SHA256 = "087c2f6b82e3f775f9eadc8f57bb342dcf1b23a100fa7c1264eb624b845388cc"
PACKET_FILES = (
    "binding.private.json", "commercialization_report.md", "expected.private.json",
    "label-isolation.json", "meta.json", "offline-probe.json", "prepared-inputs.json",
    "questions.json", "reference-notes.md", "reference-review.md", "validated_sources.json",
)
ORIGINAL_FILES = ("commercialization_report.md", "validated_sources.json", "meta.json")
OUTPUT = "outputs/rs-qwen-20260916-v1"
MAX_REQUESTS = 4
MAX_CASE_REQUESTS = 2
# The reused publisher executes its own imports. Bind the complete local import
# closure, including that old runner, without invoking any old live entry point.
IDENTITY_PATHS = tuple(dict.fromkeys((
    ".gitattributes", "src/academic_agent/__init__.py", *FROZEN_DEPENDENCY_COUPLING,
    "src/academic_agent/report_evidence_catalog_qwen_transport.py",
    "src/academic_agent/report_evidence_final_json_qwen_canary.py",
    "src/academic_agent/report_evidence_final_json_qwen_transport.py",
    "src/academic_agent/report_evidence_guarded_followup.py",
    "src/academic_agent/report_evidence_real_saved_eval.py",
    "src/academic_agent/report_evidence_real_saved_qwen_canary.py",
    "report_evidence_real_saved_canary.py", "tests/test_report_evidence_real_saved_qwen_canary.py",
    PROTOCOL, OFFLINE_PROTOCOL,
)))
DEPENDENCIES = (
    "httpx", "httpcore", "anyio", "certifi", "h11", "idna", "sniffio", "typing-extensions",
    "pydantic", "pydantic-core", "annotated-types", "typing-inspection",
)


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def configuration() -> dict:
    adapter = catalog_qwen_configuration()
    return {**adapter, "max_requests": MAX_REQUESTS, "adapter_max_requests": adapter["max_requests"],
            "max_requests_per_case": MAX_CASE_REQUESTS, "max_tool_attempts_per_case": 1,
            "protocol_identity": PROTOCOL_IDENTITY, "transport_identity": TRANSPORT_IDENTITY,
            "case_ids": list(rs.CASE_IDS), "credential_source": "process_DASHSCOPE_API_KEY_only",
            "output": OUTPUT, "resume": False, "first_failure_stops_batch": True,
            "first_reply_mechanical_check": True,
            "acknowledgement_is_independent_consent_verification": False}


def _plain_path(path: Path) -> Path:
    """Check lexical scope and every ancestor before following files or directories.

    Reparse points include Windows junctions; checking only is_symlink misses
    them. This is single-owner consistency, not protection from hostile TOCTOU.
    """
    path = Path(path)
    if ".." in path.parts:
        raise CanaryStopped("traversal_path_rejected")
    absolute = Path(os.path.abspath(path))
    absolute.relative_to(ROOT)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise CanaryStopped("indirect_path_rejected")
    return absolute


@dataclass(frozen=True)
class PrivatePacket:
    prepared: rs.PreparedInputs
    expected: tuple[rs.ExpectedCase, ...]
    binding: rs.PacketBinding
    identity: dict


def load_packet(packet_dir: Path, expected_manifest_sha256: str) -> PrivatePacket:
    """No caches: read the eleven code-owned basenames and rebuild from originals.

    Neither caller paths in a manifest nor stored prepared/model hashes select
    model inputs. Only recomputation from raw approved bytes supplies inputs.
    """
    if type(expected_manifest_sha256) is not str or expected_manifest_sha256 != MANIFEST_SHA256:
        raise CanaryStopped("packet_authorization_mismatch")
    try:
        directory = _plain_path(packet_dir)
        manifest_raw = _plain_path(directory / MANIFEST).read_bytes()
        if _sha(manifest_raw) != MANIFEST_SHA256:
            raise CanaryStopped("packet_manifest_identity_mismatch")
        manifest = core._strict_json(manifest_raw.decode("utf-8"))
        if (type(manifest) is not dict or type(manifest.get("schema")) is not int or manifest["schema"] != 1
                or manifest.get("protocol") != rs.PROTOCOL_IDENTITY
                or manifest.get("state") != "offline_prepared_not_live_authorized"
                or manifest.get("live_authorization") is not False
                or type(manifest.get("provider_requests")) is not int or manifest["provider_requests"] != 0
                or type(manifest.get("files_sha256")) is not dict
                or set(manifest["files_sha256"]) != set(PACKET_FILES)):
            raise CanaryStopped("packet_manifest_invalid")
        raw_files = {}
        for name in PACKET_FILES:
            raw = _plain_path(directory / name).read_bytes()
            if _sha(raw) != manifest["files_sha256"][name]:
                raise CanaryStopped("packet_file_identity_mismatch")
            raw_files[name] = raw
        if manifest.get("original_bytes_sha256") != {name: _sha(raw_files[name]) for name in ORIGINAL_FILES}:
            raise CanaryStopped("packet_original_identity_mismatch")
        questions = core._strict_json(raw_files["questions.json"].decode("utf-8"))
        prepared = rs.prepare_inputs(*(raw_files[name] for name in ORIGINAL_FILES), questions)
        stored = core._strict_json(raw_files["prepared-inputs.json"].decode("utf-8"))
        if _encoded(stored) != _encoded(prepared.model_dump(mode="json")):
            raise CanaryStopped("packet_projection_mismatch")
        labels = raw_files["expected.private.json"]
        binding = rs.bind_inputs(prepared, labels)
        stored_binding = core._strict_json(raw_files["binding.private.json"].decode("utf-8"))
        if _encoded(stored_binding) != _encoded(binding.model_dump(mode="json")):
            raise CanaryStopped("packet_label_binding_mismatch")
        expected = rs._expected(prepared, labels)
        groups = [source.group for source in prepared.snapshot.sources]
        target = next(source for source in prepared.snapshot.sources if source.source_id == expected[0].source_id)
        if groups != ["academic"] * 4 + ["patent"] * 8 + ["market"] * 8 or target.stored_length != 1408:
            raise CanaryStopped("packet_scope_mismatch")
        hashes = {name: getattr(prepared, name) for name in (
            "prepared_sha256", "snapshot_sha256", "catalog_sha256", "questions_sha256",
            "configuration_sha256", "projection_sha256",
        )}
        hashes["binding_sha256"] = binding.binding_sha256
        if any(manifest.get(name) != value for name, value in hashes.items()):
            raise CanaryStopped("packet_derived_identity_mismatch")
        # Historical source_files_sha256/runtime/implementation_commit remain
        # opaque preparation provenance inside the bound manifest. They do not
        # waive the separate current git/blob/disk/version verification below.
        identity = {"manifest_sha256": MANIFEST_SHA256, "files_sha256": manifest["files_sha256"], **hashes,
                    "preparation_live_authorization": False,
                    "preparation_provenance_is_current_code_authority": False}
        return PrivatePacket(prepared, expected, binding, identity)
    except (OSError, ValueError, TypeError, KeyError, StopIteration, RecursionError):
        raise CanaryStopped("packet_invalid_or_unavailable") from None


def _git(*arguments: str) -> bytes:
    return subprocess.run(["git", "--no-optional-locks", *arguments], cwd=ROOT,
                          capture_output=True, check=True, timeout=10).stdout


def verify_identity(expected_commit: str, expected_manifest_sha256: str, packet_dir: Path) -> dict:
    """Bind every current executing dependency; installed versions are not byte attestation."""
    if type(expected_commit) is not str or not re.fullmatch(r"[0-9a-f]{40}", expected_commit):
        raise CanaryStopped("invalid_expected_commit")
    try:
        head = _git("rev-parse", "--verify", "HEAD").decode("ascii").strip()
        if head != expected_commit or _git("status", "--porcelain", "--untracked-files=all",
                                            "--", *IDENTITY_PATHS).strip():
            raise CanaryStopped("source_identity_mismatch")
        disk_hashes, committed_hashes = {}, {}
        for name in IDENTITY_PATHS:
            raw = _plain_path(ROOT / name).read_bytes()
            committed = _git("show", f"{expected_commit}:{name}")
            if raw.replace(b"\r\n", b"\n") != committed:
                raise CanaryStopped("committed_content_mismatch")
            disk_hashes[name], committed_hashes[name] = _sha(raw), _sha(committed)
        if (ROOT / ".gitattributes").read_bytes().replace(b"\r\n", b"\n") != b"* text=auto eol=lf\n":
            raise CanaryStopped("unsupported_text_normalization")
        packet = load_packet(packet_dir, expected_manifest_sha256)
        locked = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))["package"]
        installed = {name: version(name) for name in DEPENDENCIES}
        if any(value not in {row["version"] for row in locked if row["name"] == name}
               for name, value in installed.items()):
            raise CanaryStopped("installed_dependency_mismatch")
        config = configuration()
        return {"protocol_identity": PROTOCOL_IDENTITY, "commit": head, "packet": packet.identity,
                "disk_sha256": disk_hashes, "committed_sha256": committed_hashes,
                "comparison": "CRLF_to_LF_for_fixed_text_paths_only",
                "runtime": {"python": platform.python_version(), **installed},
                "configuration": config, "configuration_sha256": _sha(_encoded(config))}
    except (OSError, subprocess.SubprocessError, PackageNotFoundError, ValueError, TypeError, KeyError):
        raise CanaryStopped("identity_check_unavailable") from None


def validate_output() -> Path:
    try:
        output = _plain_path(ROOT / OUTPUT)
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


def _first_reply_gate(message, expected, snapshot) -> str | None:
    """Evaluate an ALREADY accounted model choice, never choose or repair it."""
    calls = message.get("tool_calls") or []
    if len(calls) != 1 or calls[0]["function"]["name"] != "read_source":
        return "first_reply_read_required"
    args = ReadArguments.model_validate(core._strict_json(calls[0]["function"]["arguments"]))
    if args.source_id != expected.source_id:
        return "first_reply_reference_source_mismatch"
    target = next(source for source in snapshot.sources if source.source_id == expected.source_id)
    if args.offset != 0 or args.length < target.stored_length:
        return "first_reply_complete_window_required"
    return None


class _CheckedTransport:
    """Independent runner ceiling and identity guard outside the frozen transport."""

    def __init__(self, transport, ledger, identity, packet_dir, packet, expected, first):
        self.transport, self.ledger, self.identity = transport, ledger, identity
        self.packet_dir, self.packet, self.expected, self.first = packet_dir, packet, expected, first

    def _verify(self):
        if verify_identity(self.identity["commit"], self.identity["packet"]["manifest_sha256"],
                           self.packet_dir) != self.identity:
            raise CanaryStopped("runtime_identity_changed")

    def __call__(self, **kwargs):
        try:
            if self.ledger.stop_reason is not None or self.ledger.pending is not None:
                raise CanaryStopped("runner_unresolved_or_stopped")
            if len(self.ledger.records) >= MAX_REQUESTS:
                raise CanaryStopped("runner_request_limit")
            if len(self.ledger.records) - self.first >= MAX_CASE_REQUESTS:
                raise CanaryStopped("runner_case_request_limit")
            self._verify()
            try:
                reply = self.transport(**kwargs)
            finally:
                # Even a failing adapter can have parsed usage. Never replace
                # the ledger or refund its reservations after identity loss.
                self._verify()
            if len(self.ledger.records) - self.first == 1:
                reason = _first_reply_gate(reply, self.expected, self.packet.prepared.snapshot)
                if reason is not None:
                    raise CanaryStopped(reason)
            return reply
        except CanaryStopped as exc:
            _stop(self.ledger, str(exc))
            raise
        except Exception:  # noqa: BLE001 -- never publish private callback exception text.
            _stop(self.ledger, "runner_preflight_or_transport_failed")
            raise CanaryStopped("runner_preflight_or_transport_failed") from None


def review_case_mechanics(packet: PrivatePacket, index: int, result) -> rs.MechanicalReview:
    """Single-case copy of the frozen offline gates; no fake unrun RS02 result.

    Keep this coupling explicit: the offline helper requires TWO observations.
    This runner must decide whether to spend on RS02 using only RS01 evidence.
    """
    prepared, case = packet.prepared, packet.expected[index]
    failures, audit = [], result.audit
    if (audit.downstream_calls != 2 or len(audit.callback_bytes) != 2
            or any(not 0 < count <= MAX_CALLBACK_BYTES for count in audit.callback_bytes)
            or audit.blocked_callback_bytes is not None or audit.refusal is not None
            or audit.downstream_exception_type is not None or audit.advertised_tools != (("read_source",), ())):
        failures.append("two_callback_read_to_final_required")
    if (audit.catalog_hash != prepared.catalog_sha256 or audit.catalog_bytes != len(prepared.catalog_json)
            or audit.total_count != len(prepared.snapshot.sources) or audit.returned_count != audit.total_count
            or audit.coverage != "complete" or audit.omitted_count or audit.title_truncation_count):
        failures.append("complete_bound_catalog_required")
    if (audit.core.transport_turns != 2 or audit.core.observed_tool_requests != 1
            or audit.core.tool_attempts != 1 or audit.core.tool_executions != 1 or audit.core.tool_errors
            or audit.core.no_tools or len(audit.core.call_ids) != 1 or audit.core.exception_type is not None):
        failures.append("one_actual_read_required")
    target = next(item for item in prepared.snapshot.sources if item.source_id == case.source_id)
    full = read_source(prepared.snapshot, case.source_id, 0, target.stored_length)
    payload = {name: full[name] for name in core.ServedEvidence.model_fields if name != "evidence_id"}
    evidence_id = "ev_" + content_hash(payload)
    receipt = core.ServedEvidence(evidence_id=evidence_id, **payload)
    if (result.served_evidence != (receipt,) or audit.forwarded_read_ids != (evidence_id,)
            or audit.core.delivered_read_ids != (evidence_id,) or len(audit.tool_results) != 1
            or audit.tool_results[0].status != "ok" or audit.tool_results[0].evidence_id != evidence_id
            or (audit.tool_results[0].call_id,) != audit.core.call_ids):
        failures.append("complete_current_conversation_receipt_required")
    required_ids = (evidence_id,) if case.required_state == "answered_with_evidence" else ()
    if result.state != case.required_state or result.evidence_ids != required_ids:
        failures.append("preregistered_state_and_citations_required")
    return rs.MechanicalReview(case_id=case.case_id, passed=not failures, failures=tuple(failures),
                               binding_sha256=packet.binding.binding_sha256)


def _case_gate(packet, index, result, records, ledger) -> str | None:
    try:
        return _check_case(packet, index, result, records, ledger)
    except (KeyError, IndexError, TypeError, ValueError, AttributeError, RecursionError):
        return "invalid_case_observation"


def _check_case(packet, index, result, records, ledger):
    prepared, expected = packet.prepared, packet.expected[index]
    snapshot, question = prepared.snapshot, prepared.questions[index]
    if (ledger.stop_reason is not None or ledger.pending is not None or len(records) != 2
            or any(record["protocol_accepted"] is not True or record["provider_response_received"] is not True
                   or record["response_model_matches_authorized"] is not True
                   or record["usage_status"] != "complete" or "reported_usage" not in record
                   or record["case_id"] != question.case_id for record in records)):
        return "transport_observation_failed"
    review = review_case_mechanics(packet, index, result)
    if not review.passed:
        return review.failures[0]
    reason = "final_answer" if index == 0 else "model_abstained"
    if (result.audit.core.terminal_reason != reason or result.semantic_support != "not_assessed"
            or result.answer_verification != "not_verified"):
        return "policy_core_failed"
    catalog = build_catalog(snapshot)
    for record in records:
        body = record["request"]
        if (record["request_sha256"] != _sha(_encoded(body)) or len(_encoded(body)) > REQUEST_BYTES
                or body["model"] != configuration()["model"]
                or body["messages"][1] != {"role": "user", "content": question.question}
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
    if _first_reply_gate(native, expected, snapshot) is not None or _encoded(final["messages"][3]) != _encoded(native):
        return "native_read_observation_failed"
    call = native["tool_calls"][0]
    tool = final["messages"][4]
    if (result.audit.core.call_ids != (call["id"],) or set(tool) != {"role", "tool_call_id", "content"}
            or tool["role"] != "tool" or tool["tool_call_id"] != call["id"]):
        return "native_read_observation_failed"
    # Compare actual second HTTP bytes with the COMPLETE issued read, not an
    # audit counter or receipt ID alone. RS02 keeps this same nonempty receipt.
    source = next(item for item in snapshot.sources if item.source_id == expected.source_id)
    full = read_source(snapshot, source.source_id, 0, source.stored_length)
    full["evidence_id"] = result.served_evidence[0].evidence_id
    if _encoded(core._strict_json(tool["content"])) != _encoded(full):
        return "paired_read_payload_mismatch"
    message = records[1]["assistant_message"]
    if message.get("tool_calls") or core._strict_json(message["content"]) != {
        "answer": result.answer, "status": "answered" if index == 0 else "abstained",
        "evidence_ids": list(result.evidence_ids),
    }:
        return "final_envelope_mismatch"
    return None


def run_canary(*, expected_commit: str, expected_manifest_sha256: str,
               packet_dir: Path, authorize_paid: str) -> dict:
    """Fresh single-batch path only; no output override, retry, resume or fallback."""
    if type(authorize_paid) is not str or authorize_paid != PROTOCOL_IDENTITY:
        raise CanaryStopped("fresh_protocol_acknowledgement_required")
    identity = verify_identity(expected_commit, expected_manifest_sha256, packet_dir)
    packet = load_packet(packet_dir, expected_manifest_sha256)
    if packet.identity != identity["packet"]:
        raise CanaryStopped("runtime_identity_changed")
    output = validate_output()
    key = read_dedicated_key()
    ledger = CatalogQwenLedger(output)
    experiment = {
        "protocol_identity": PROTOCOL_IDENTITY, "scope": "parent_only_single_real_saved_live_batch",
        "transport_identity": TRANSPORT_IDENTITY, "configuration": configuration(),
        "identity_sha256": _sha(_encoded(identity)), "standing_authorization_source": PROTOCOL,
        "adapter_manifest": "manifest.json", "adapter_manifest_grants_live_authorization": False,
        "preparation_manifest_grants_live_authorization": False, "old_allowance_reused": False,
        "allowed_model_inputs": ["two_fixed_questions", "complete_20_title_catalog_and_citation_metadata",
                                 "one_selected_saved_window_up_to_1500_codepoints_per_case"],
        "excluded_model_inputs": ["report_prose", "raw_run_metadata", "paths", "reference_labels",
                                  "reviewer_notes", "credentials"],
    }
    _publish_result(ledger, "identity.json", identity)
    _publish_result(ledger, "experiment_manifest.json", experiment)
    _publish_result(ledger, "authorization.json", {
        "protocol_identity": PROTOCOL_IDENTITY, "operator_acknowledgement": authorize_paid,
        "expected_commit": expected_commit, "expected_manifest_sha256": expected_manifest_sha256,
        "identity_sha256": experiment["identity_sha256"],
        "experiment_manifest_sha256": _sha(_encoded(experiment)),
        "configuration_sha256": identity["configuration_sha256"],
        "standing_authorization_source": PROTOCOL, "independent_user_consent_verified": False,
        "parent_operator_only": True, "old_allowance_reused": False, "max_requests": MAX_REQUESTS,
    })
    outcomes = []
    for index, question in enumerate(packet.prepared.questions):
        ledger.case_id, first, result = question.case_id, len(ledger.records), None
        try:
            transport = CatalogQwenFollowupTransport(key, ledger, snapshot=packet.prepared.snapshot)
            checked = _CheckedTransport(transport, ledger, identity, packet_dir, packet, packet.expected[index], first)
            result = run_catalog_followup(packet.prepared.snapshot, question.question, transport=checked)
            reason = _case_gate(packet, index, result, ledger.records[first:], ledger)
        except Exception:  # noqa: BLE001 -- retain ledger facts, not private setup/source exception text.
            reason = "case_execution_failed"
        outcome = {"case_id": question.case_id, "passed": reason is None, "gate_failure": reason,
                   "result": None if result is None else result.model_dump(mode="json"),
                   "semantic_support": "not_assessed", "answer_verification": "not_verified",
                   "semantic_review": "separate_parent_review_required"}
        persisted = False
        try:
            _publish_result(ledger, question.case_id + ".json", outcome)
            persisted = True
        except CanaryStopped:
            reason = "persistence_failed"
        outcomes.append({"case_id": question.case_id, "passed": reason is None,
                         "gate_failure": reason, "case_record_persisted": persisted})
        if reason is not None:
            _stop(ledger, reason)
            break
    summary = {"mode": "real_saved_qwen_canary", "protocol_identity": PROTOCOL_IDENTITY,
               "passed": len(outcomes) == 2 and all(row["passed"] for row in outcomes)
                         and ledger.stop_reason is None and ledger.pending is None,
               "cases": outcomes, "unrun_cases": list(rs.CASE_IDS[len(outcomes):]),
               "semantic_support": "not_assessed", "answer_verification": "not_verified",
               "summary_persisted": True, **ledger.summary()}
    try:
        _publish_result(ledger, "summary.json", summary)
    except CanaryStopped:
        summary.update(ledger.summary(), passed=False, summary_persisted=False)
    return summary
