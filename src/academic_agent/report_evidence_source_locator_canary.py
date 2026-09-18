"""One fixed SLQ batch; identity-only by default, native execution parent-only.

The frozen locator owns the actual read. The runner reconciles its projection
with the admitted choice, not with a generated answer or a second model turn.
Single-owner local accounting is not execution attestation or disk-loss safety.
"""

import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import re
import stat
import subprocess
from time import monotonic
import tomllib

from academic_agent import report_evidence_source_locator as locator
from academic_agent import report_evidence_source_locator_qwen_transport as native
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_followup import _assistant_message, _strict_json
from academic_agent.report_evidence_qwen_canary import (
    CanaryStopped, INPUT_RATE, INPUT_RESERVATION, MAX_TOKENS, MODEL, OUTPUT_RATE,
    REQUEST_BYTES, RESERVATION_USD, _encoded,
)
from academic_agent.report_evidence_qwen_transport import _usage, validate_key
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource, content_hash

PROTOCOL_IDENTITY = "report_evidence_source_locator_qwen_canary_v1"
ROOT = Path(__file__).resolve().parents[2]
FIXED_OUTPUT = "outputs/report_evidence_source_locator_qwen_canary_v1"
FIXTURE = "tests/fixtures/report_evidence_source_locator_qwen.json"
FIXTURE_SHA256 = "c4301fe9d6d57427de3f0252492b88886964ed6b0a15bbf6f6a5c9e9fbaff36e"
PROTOCOL = "docs/prereg-2026-09-19-source-locator-qwen-canary.md"
CASE_IDS = ("SLQ01", "SLQ02", "SLQ03", "SLQ04")
REFERENCES = (("A12", "excerpt", "saved_text"), ("P21", "excerpt", "saved_text"),
              (None, "declined", "selector_declined"), ("P41", "missing_text", "saved_text_missing"))
SOURCE_METADATA = {"publisher": "Synthetic locator controls", "source_type": "synthetic_control",
                   "origin": "unknown", "accessed_date": "2026-09-19"}
MAX_REQUESTS = 4
USD_LIMIT = Decimal("0.05")
IDENTITY_PATHS = (
    ".gitattributes", "src/academic_agent/__init__.py", *native.FROZEN_DEPENDENCY_COUPLING,
    # The secret scanner imports the catalog adapter, which imports this module.
    "src/academic_agent/report_evidence_stage_qwen_transport.py",
    "src/academic_agent/report_evidence_source_locator_qwen_transport.py",
    "src/academic_agent/report_evidence_source_locator_canary.py",
    "tests/test_report_evidence_source_locator.py",
    "tests/test_report_evidence_source_locator_qwen_transport.py",
    "tests/test_report_evidence_source_locator_canary.py", FIXTURE, PROTOCOL,
    "docs/prereg-2026-09-18-saved-source-locator.md",
    "docs/prereg-2026-09-18-source-locator-qwen-transport.md",
)
DEPENDENCIES = (
    "httpx", "httpcore", "anyio", "certifi", "h11", "idna", "sniffio", "typing-extensions",
    "pydantic", "pydantic-core", "annotated-types", "typing-inspection",
)
_SAFE_REASONS = native._SAFE_ERRORS | frozenset({
    "runner_request_limit", "runner_budget_limit", "runner_unresolved_or_stopped",
    "runtime_identity_changed", "source_identity_mismatch", "committed_content_mismatch",
    "installed_dependency_mismatch", "identity_check_unavailable", "indirect_path_rejected",
    "fixture_identity_mismatch", "fixture_invalid_or_unavailable", "unsupported_text_normalization",
    "runner_preflight_or_transport_failed", "case_execution_failed", "reference_mismatch",
    "invalid_case_observation", "transport_observation_failed", "callback_native_audit_failed",
    "choice_projection_failed", "output_creation_failed_or_occupied",
})


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def configuration():
    return {"protocol_identity": PROTOCOL_IDENTITY, "fixed_output": FIXED_OUTPUT,
            "case_ids": list(CASE_IDS), "max_requests": MAX_REQUESTS, "max_requests_per_case": 1,
            "usd_soft_limit": str(USD_LIMIT), "four_request_reservation_usd": str(RESERVATION_USD * 4),
            "per_case_transport": native.locator_qwen_configuration(),
            "first_failure_stops_batch": True, "resume": False,
            "credential_source": "process_DASHSCOPE_API_KEY_only",
            "acknowledgement_is_independent_consent_verification": False,
            "elapsed_scope": "monotonic_case_setup_checks_callback_read_gate_then_publication_attempt",
            "elapsed_exclusions": "batch_setup_and_summary_publication_not_isolated_provider_latency_or_SLO"}


def snapshot_for(case):
    return ReportEvidenceSnapshot(report_ref=case["case_id"], sources=tuple(
        SnapshotSource(**SOURCE_METADATA, **source) for source in case["sources"]))


def load_cases():
    try:
        raw = (ROOT / FIXTURE).read_bytes()
        if _digest(raw) != FIXTURE_SHA256:
            raise CanaryStopped("fixture_identity_mismatch")
        data = _strict_json(raw.decode("utf-8"))
        if (type(data) is not dict or set(data) != {
                "schema_version", "cohort_id", "origin", "reference_status", "source_metadata", "cases"}
                or type(data["schema_version"]) is not int or data["schema_version"] != 1
                or data["cohort_id"] != "source_locator_synthetic_development_v1"
                or data["origin"] != "author_generated_synthetic"
                or data["reference_status"] != "llm_label_blinded_context_limited_reviewed"
                or data["source_metadata"] != SOURCE_METADATA or type(data["cases"]) is not list
                or tuple(row["case_id"] for row in data["cases"]) != CASE_IDS):
            raise ValueError("fixture_contract")
        for case, reference in zip(data["cases"], REFERENCES, strict=True):
            if (set(case) != {"case_id", "question", "sources", "expected_source_id", "expected_state", "expected_reason"}
                    or tuple(case[key] for key in ("expected_source_id", "expected_state", "expected_reason")) != reference
                    or type(case["question"]) is not str or not 1 <= len(case["question"]) <= 4096
                    or not case["question"].strip() or type(case["sources"]) is not list or len(case["sources"]) != 3
                    or any(type(row) is not dict or set(row) != {"source_id", "group", "title", "summary"}
                           for row in case["sources"])):
                raise ValueError("fixture_contract")
            snapshot = snapshot_for(case)
            catalog = build_catalog(snapshot)
            if (catalog["omitted_count"] or catalog["title_truncation_count"]
                    or any(source.stored_length > 1500 for source in snapshot.sources)):
                raise ValueError("fixture_scope")
        return tuple(data["cases"])
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
    """Disk/blob identity and installed versions, not installed-package attestation."""
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
            disk[name], committed[name] = _digest(raw), _digest(blob)
        if (ROOT / ".gitattributes").read_bytes().replace(b"\r\n", b"\n") != b"* text=auto eol=lf\n":
            raise CanaryStopped("unsupported_text_normalization")
        load_cases()
        locked = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))["package"]
        installed = {name: version(name) for name in DEPENDENCIES}
        if any(value not in {row["version"] for row in locked if row["name"] == name} for name, value in installed.items()):
            raise CanaryStopped("installed_dependency_mismatch")
        config = configuration()
        return {"protocol_identity": PROTOCOL_IDENTITY, "commit": head, "fixture_sha256": FIXTURE_SHA256,
                "disk_sha256": disk, "committed_sha256": committed,
                "comparison": "CRLF_to_LF_for_fixed_text_paths_only",
                "runtime": {"python": platform.python_version(), **installed},
                "configuration": config, "configuration_sha256": _digest(_encoded(config))}
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


def _safe_reason(exc, fallback):
    # Even the shared exception class can carry arbitrary text. Never str(exc).
    if type(exc) is CanaryStopped and len(exc.args) == 1:
        reason = exc.args[0]
        if type(reason) is str and reason in _SAFE_REASONS:
            return reason
    return fallback


def _publish(output, name, value):
    """Local write-once atomic link after complete write/flush/fsync/close."""
    pending, destination = output / ("." + name + ".pending"), output / name
    try:
        _plain_path(destination)
        _plain_path(pending)
        raw = _encoded(value) + b"\n"
        with pending.open("xb") as stream:
            if stream.write(raw) != len(raw):
                raise OSError("short_write")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(pending, destination)
    except Exception:  # noqa: BLE001 -- paths, data and arbitrary filesystem errors are not safe diagnostics.
        raise CanaryStopped("persistence_failed") from None
    try:
        pending.unlink()
    except OSError:
        pass  # Optional cleanup cannot revoke an already complete publication.


class _Batch:
    """Aggregate admission only; never reuse one native ledger across cases."""

    def __init__(self, output):
        self.output, self.ledgers, self.stop_reason = output, [], None
        try:
            output.mkdir(exist_ok=False)
        except OSError:
            raise CanaryStopped("output_creation_failed_or_occupied") from None

    def totals(self):
        records = [record for ledger in self.ledgers for record in ledger.records]
        known = sum((Decimal(row.get("estimated_usd", "0")) for row in records), Decimal(0))
        consumed = sum((max(Decimal(row["reservation_usd"]), Decimal(row.get("estimated_usd", "0")))
                        for row in records), Decimal(0))
        unknown = sum(row["usage_status"] != "complete" for row in records)
        return {"request_count": len(records), "unknown_usage_requests": unknown,
                "known_usage_estimated_usd": str(known), "budget_consumed_usd": str(consumed),
                "cost_coverage": "not_observed" if not records else "lower_bound" if unknown else "complete_for_reported_requests",
                "price_scope": "frozen_conservative_estimate_not_invoice",
                "pending_cases": [ledger.case_id for ledger in self.ledgers if ledger.pending is not None],
                "stop_reason": self.stop_reason}

    def admit(self):
        totals = self.totals()
        if (self.stop_reason is not None or totals["pending_cases"] or totals["unknown_usage_requests"]
                or any(ledger.stop_reason is not None for ledger in self.ledgers)):
            raise CanaryStopped("runner_unresolved_or_stopped")
        if totals["request_count"] >= MAX_REQUESTS:
            raise CanaryStopped("runner_request_limit")
        if Decimal(totals["budget_consumed_usd"]) + RESERVATION_USD > USD_LIMIT:
            raise CanaryStopped("runner_budget_limit")

    def stop(self, reason, ledger=None):
        if self.stop_reason is None or reason == "persistence_failed":
            self.stop_reason = reason
        if ledger is not None:
            try:
                ledger.stop(reason)
            except Exception:  # noqa: BLE001 -- retain observed usage and pending intent when stop persistence fails.
                ledger.stop_reason = self.stop_reason = "persistence_failed"


class _CheckedSelector:
    def __init__(self, transport, batch, identity):
        self.transport, self.batch, self.identity = transport, batch, identity
        self.entries, self.request, self.response, self.failure = 0, None, None, None

    def _identity(self):
        if verify_identity(self.identity["commit"], self.identity["fixture_sha256"]) != self.identity:
            raise CanaryStopped("runtime_identity_changed")

    def __call__(self, request, /):
        self.entries += 1
        try:
            if self.entries != 1:
                raise CanaryStopped("runner_request_limit")
            self.batch.admit()
            self._identity()  # Pre-dispatch identity is independent of post-call detection.
            self.request = deepcopy(request)
            try:
                self.response = deepcopy(self.transport(request))
                return deepcopy(self.response)
            finally:
                # Rejected replies and post-call drift must retain observed usage.
                self._identity()
        except Exception as exc:  # noqa: BLE001 -- only fixed categories survive even arbitrary CanaryStopped text.
            self.failure = _safe_reason(exc, "runner_preflight_or_transport_failed")
            self.batch.stop(self.failure, self.transport.ledger)
            raise CanaryStopped(self.failure) from None


def _accounting(ledger, case_id):
    if type(ledger) is not native.LocatorQwenLedger or ledger.stop_reason is not None or ledger.pending is not None:
        return False
    if len(ledger.records) != 1 or ledger.case_id != case_id:
        return False
    row = ledger.records[0]
    if (type(row["request_id"]) is not int or row["request_id"] != 1 or row["case_id"] != case_id
            or row["protocol_accepted"] is not True or row["provider_response_received"] is not True
            or row["response_model_matches_authorized"] is not True or row["usage_status"] != "complete"
            or row["error"] is not None or row["reservation_usd"] != str(RESERVATION_USD)):
        return False
    usage = _usage({"usage": row["reported_usage"]})
    if (usage is None or _encoded(usage) != _encoded(row["reported_usage"])
            or usage["prompt_tokens"] > INPUT_RESERVATION or usage["completion_tokens"] > MAX_TOKENS):
        return False
    cost = (Decimal(usage["prompt_tokens"]) * INPUT_RATE + Decimal(usage["completion_tokens"]) * OUTPUT_RATE) / 1_000_000
    if row["estimated_usd"] != str(cost):
        return False
    reserved = {key: row[key] for key in ("request_id", "case_id", "request", "request_sha256", "reservation_usd")}
    reserved.update(usage_status="unknown", provider_response_received=False,
                    response_model_matches_authorized=None, protocol_accepted=False)
    expected = [{"event": "request_reserved", **reserved}, {"event": "request_finished", **row}]
    # Exact event order/shape rules out duplicate, partial, extra or missing facts.
    raw = (ledger.output_dir / "events.jsonl").read_bytes()
    if raw != b"".join(_encoded(event) + b"\n" for event in expected):
        return False
    return set(row) == set(reserved) | {"reported_usage", "estimated_usd", "error"}


def _serialized(result):
    if type(result) is not locator.LocatorResult:
        raise CanaryStopped("invalid_case_observation")
    observed = _strict_json(locator.render_locator_result(result))
    if _encoded(observed) != _encoded(result.model_dump(warnings="error")):
        raise CanaryStopped("invalid_case_observation")
    return observed


def _case_gate(case, snapshot, result, checked):
    """Mechanical reconciliation only; deliberately independent of reference IDs."""
    try:
        observed = _serialized(result)
        ledger = checked.transport.ledger
        if checked.failure is not None or not _accounting(ledger, case["case_id"]):
            return "transport_observation_failed", None
        catalog = build_catalog(snapshot)
        request = locator._request(case["question"], catalog)
        body = {**request, "model": MODEL, "stream": False, "enable_thinking": False,
                "parallel_tool_calls": False, "temperature": 0, "max_tokens": MAX_TOKENS}
        wire, callback = _encoded(body), _encoded(request)
        row = ledger.records[0]
        if (checked.entries != 1 or _encoded(checked.request) != callback
                or _encoded(row["request"]) != wire or row["request_sha256"] != _digest(wire)
                or len(wire) > REQUEST_BYTES or len(callback) > locator.MAX_CALLBACK_BYTES):
            return "callback_native_audit_failed", None
        message = _assistant_message(checked.response)
        visible = tuple(entry["source_id"] for entry in catalog["entries"])
        native._admit_selection(message, visible)
        calls = message.get("tool_calls") or []
        selected, text = None, None
        if calls:
            source_id = locator._Selection.model_validate(_strict_json(calls[0]["function"]["arguments"])).source_id
            source = next(source for source in snapshot.sources if source.source_id == source_id)
            selected = {**source.model_dump(exclude={"summary"}), "stored_length": source.stored_length,
                        "snapshot_hash": snapshot.snapshot_hash, "source_hash": snapshot.source_hash(source),
                        "summary_hash": content_hash(source.summary)}
            if source.stored_length > locator.MAX_SAVED_CODEPOINTS:
                state, reason, reads = "out_of_scope", "selected_text_too_long", 0
            elif not source.summary:
                state, reason, reads = "missing_text", "saved_text_missing", 1
            else:
                state = "excerpt" if source.summary.strip() else "blank_text"
                reason, reads = ("saved_text" if source.summary.strip() else "saved_text_blank"), 1
                text = {"text": source.summary, "start": 0, "end": source.stored_length,
                        "window_truncated": False, "text_sha256": _digest(source.summary.encode("utf-8")),
                        "text_scope": "saved_summary_only"}
            choice = {"kind": "selected", "source_id": source_id}
        else:
            state, reads = "declined", 0
            reason = "selector_refused" if message.get("refusal") else "selector_declined"
            choice = {"kind": "refused" if message.get("refusal") else "declined", "source_id": None}
        expected = {
            "method_id": locator.METHOD_ID, "state": state, "reason": reason,
            "catalog": {"catalog_hash": content_hash(catalog), "catalog_bytes": len(_encoded(catalog)),
                        **{key: catalog[key] for key in ("total_count", "returned_count", "omitted_count",
                                                       "coverage", "title_truncation_count")}},
            "source": selected, "saved_text": text, "callback_entries": 1, "callback_bytes": len(callback),
            "read_attempts": reads, "read_completed": reads,
            "selection_relevance": "not_assessed", "semantic_support": "not_assessed",
        }
        # No extra read is executed to fabricate a receipt. The frozen locator
        # checks the actual read; this comparison independently binds its JSON.
        if _encoded(observed) != _encoded(expected):
            return "choice_projection_failed", choice
        return None, choice
    except Exception:  # noqa: BLE001 -- malformed observations are failures, never raw diagnostics.
        return "invalid_case_observation", None


def _reference_matches(case, result):
    selected = result.source.source_id if result.source is not None else None
    return (selected, result.state, result.reason) == tuple(
        case[key] for key in ("expected_source_id", "expected_state", "expected_reason"))


def run_canary(*, expected_commit, expected_fixture_sha256, authorize_paid):
    if type(authorize_paid) is not str or authorize_paid != PROTOCOL_IDENTITY:
        raise CanaryStopped("fresh_protocol_acknowledgement_required")
    identity = verify_identity(expected_commit, expected_fixture_sha256)
    cases = load_cases()
    validate_output()
    key = read_dedicated_key()
    batch = _Batch(validate_output())
    experiment = {"protocol_identity": PROTOCOL_IDENTITY, "configuration": configuration(),
                  "identity_sha256": _digest(_encoded(identity)), "parent_operator_only": True,
                  "adapter_manifest_grants_live_authorization": False, "old_allowance_reused": False}
    _publish(batch.output, "identity.json", identity)
    _publish(batch.output, "experiment_manifest.json", experiment)
    _publish(batch.output, "authorization.json", {
        "operator_acknowledgement": authorize_paid, "expected_commit": expected_commit,
        "expected_fixture_sha256": expected_fixture_sha256, "standing_authorization_source": PROTOCOL,
        "identity_sha256": experiment["identity_sha256"], "experiment_manifest_sha256": _digest(_encoded(experiment)),
        "independent_user_consent_verified": False, "parent_operator_only": True, "old_allowance_reused": False})
    outcomes = []
    for case in cases:
        started = monotonic()
        ledger, result, observed, choice, checked = None, None, None, None, None
        try:
            snapshot = snapshot_for(case)
            ledger = native.LocatorQwenLedger(batch.output / case["case_id"])
            ledger.case_id = case["case_id"]
            batch.ledgers.append(ledger)
            transport = native.LocatorQwenTransport(key, ledger, snapshot=snapshot, question=case["question"])
            checked = _CheckedSelector(transport, batch, identity)
            result = locator.locate_saved_source(snapshot, case["question"], selector=checked)
            reason, choice = _case_gate(case, snapshot, result, checked)
            if checked.failure is not None:
                reason = checked.failure
            observed = _serialized(result)
        except Exception as exc:  # noqa: BLE001 -- retain existing usage without leaking arbitrary exception text.
            reason = _safe_reason(exc, "case_execution_failed")
        mechanical = reason is None
        reference = _reference_matches(case, result) if mechanical else None
        if mechanical and reference is not True:
            reason = "reference_mismatch"
        outcome = {"case_id": case["case_id"], "mechanical_passed": mechanical,
                   "reference_match_passed": reference, "gate_failure": reason,
                   "choice": choice, "result": observed,
                   "elapsed_before_case_publication_seconds": monotonic() - started,
                   "choice_observation": "admitted_projected_reply_in_memory_not_raw_http_attestation"}
        persisted = False
        try:
            _publish(batch.output, case["case_id"] + ".json", outcome)
            persisted = True
        except CanaryStopped:
            reason = "persistence_failed"
        outcomes.append({**{name: value for name, value in outcome.items() if name != "result"},
                         "gate_failure": reason, "case_record_persisted": persisted,
                         "elapsed_through_case_publication_attempt_seconds": monotonic() - started})
        if reason is not None:
            batch.stop(reason, ledger)
            break
    references = [row["reference_match_passed"] for row in outcomes]
    totals = batch.totals()
    summary = {
        "protocol_identity": PROTOCOL_IDENTITY, "mode": "synthetic_source_locator_qwen_canary",
        "batch_passed": len(outcomes) == 4 and all(row["mechanical_passed"] and row["reference_match_passed"] is True
                                                and row["case_record_persisted"] for row in outcomes)
        and totals["stop_reason"] is None and not totals["pending_cases"] and totals["unknown_usage_requests"] == 0,
        "mechanically_passed_cases": sum(row["mechanical_passed"] for row in outcomes),
        "reference_checks": sum(value is not None for value in references),
        "reference_matches": sum(value is True for value in references),
        "reference_match_passed": False if False in references else True if len(references) == 4 and all(references) else None,
        "cases": outcomes, "unrun_cases": list(CASE_IDS[len(outcomes):]),
        "reference_status": "llm_label_blinded_context_limited_reviewed_not_human_truth",
        "selection_relevance": "not_assessed", "semantic_support": "not_assessed",
        "elapsed_scope": configuration()["elapsed_scope"], "elapsed_exclusions": configuration()["elapsed_exclusions"],
        "summary_persisted": True, **totals,
    }
    try:
        _publish(batch.output, "summary.json", summary)
    except CanaryStopped:
        batch.stop("persistence_failed")
        summary.update(batch.totals(), batch_passed=False, summary_persisted=False)
    return summary


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "invalid_source_locator_canary_arguments\n")


def main(argv=None):
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-fixture-sha256", required=True)
    parser.add_argument("--authorize-paid", help="Exact SLQ acknowledgement, not consent/review/CI verification.")
    args = parser.parse_args(argv)
    try:
        if args.authorize_paid is None:
            identity = verify_identity(args.expected_commit, args.expected_fixture_sha256)
            print(json.dumps({"mode": "identity_only", "identity_verified": True,
                              "live_authorized": False, "identity": identity}, ensure_ascii=True))
            return 0
        result = run_canary(expected_commit=args.expected_commit, expected_fixture_sha256=args.expected_fixture_sha256,
                            authorize_paid=args.authorize_paid)
        print(json.dumps(result, ensure_ascii=True))
        return 0 if result["batch_passed"] and result["summary_persisted"] else 1
    except CanaryStopped:
        error = "source_locator_canary_admission_or_persistence_failed"
    except Exception:  # noqa: BLE001 -- CLI output must not include arbitrary exception messages or credentials.
        error = "source_locator_canary_setup_failed"
    print(json.dumps({"batch_passed": False, "error": error}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
