"""Single-owner public-title comparison; identity-only CLI unless acknowledged.

This new batch never calls the closed SLQ runner. The unchanged locator owns
the read; all summaries are absent. Location is not evidence or entailment.
Native execution still requires parent review/CI/authority on the exact tree.
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
from academic_agent import report_evidence_source_locator_comparison as baseline
from academic_agent import report_evidence_source_locator_qwen_transport as native
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_followup import _assistant_message, _strict_json
from academic_agent.report_evidence_qwen_canary import (
    CanaryStopped, INPUT_RATE, INPUT_RESERVATION, MAX_TOKENS, MODEL, OUTPUT_RATE,
    REQUEST_BYTES, RESERVATION_USD, _encoded,
)
from academic_agent.report_evidence_qwen_transport import _usage, validate_key
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource, content_hash

PROTOCOL_IDENTITY = "report_evidence_source_locator_comparison_qwen_v1"
ROOT = Path(__file__).resolve().parents[2]
FIXED_OUTPUT = "outputs/" + PROTOCOL_IDENTITY
FIXTURE = "tests/fixtures/report_evidence_source_locator_comparison.json"
FIXTURE_SHA256 = baseline.FIXTURE_SHA256
PRIMARY_BASELINE_SHA256 = "ef2ba8075ebbcb7eac467071cd673ecd4ac6cca3b111e20d945d7feb9e7d66ce"
# Provenance only. Never normalize observations or admit this historical hash.
HISTORICAL_INTEGER_NORMALIZED_BASELINE_SHA256 = "8e8405087757368672736a43d858094349bea6c295029ffe4ea8a3ef15c385d8"
PROTOCOL = "docs/prereg-2026-09-19-public-source-locator-qwen-comparison.md"
ERRATUM = "docs/erratum-2026-09-19-slc-baseline-encoding.md"
CASE_IDS = tuple(f"SLC{i:02d}" for i in range(1, 7))
MAX_REQUESTS = 6
USD_LIMIT = Decimal("0.10")
IDENTITY_PATHS = (
    ".gitattributes", "src/academic_agent/__init__.py", *native.FROZEN_DEPENDENCY_COUPLING,
    "src/academic_agent/report_evidence_stage_qwen_transport.py",
    "src/academic_agent/report_evidence_source_locator_qwen_transport.py",
    "src/academic_agent/report_evidence_source_locator_comparison.py",
    "src/academic_agent/report_evidence_source_locator_comparison_qwen.py",
    "tests/test_report_evidence_source_locator.py",
    "tests/test_report_evidence_source_locator_qwen_transport.py",
    "tests/test_report_evidence_source_locator_comparison.py",
    "tests/test_report_evidence_source_locator_comparison_qwen.py",
    FIXTURE, PROTOCOL, ERRATUM, "examples/solid-state-batteries-ev.md",
    *(path for path, _ in baseline.ASSETS),
)
DEPENDENCIES = (
    "httpx", "httpcore", "anyio", "certifi", "h11", "idna", "sniffio", "typing-extensions",
    "pydantic", "pydantic-core", "annotated-types", "typing-inspection",
)
_SAFE_REASONS = native._SAFE_ERRORS | frozenset({
    "runner_request_limit", "runner_budget_limit", "runner_unresolved_or_stopped",
    "runtime_identity_changed", "source_identity_mismatch", "committed_content_mismatch",
    "identity_check_unavailable", "indirect_path_rejected", "installed_dependency_mismatch",
    "fixture_identity_mismatch", "fixture_invalid_or_unavailable", "unsupported_text_normalization",
    "baseline_unavailable_or_changed", "runner_preflight_or_transport_failed", "case_execution_failed",
    "reference_mismatch", "invalid_case_observation", "transport_observation_failed",
    "callback_native_audit_failed", "choice_projection_failed", "output_creation_failed_or_occupied",
})


def _digest(raw):
    return hashlib.sha256(raw).hexdigest()


def configuration():
    return {
        "protocol_identity": PROTOCOL_IDENTITY, "fixed_output": FIXED_OUTPUT,
        "case_ids": list(CASE_IDS), "max_requests": MAX_REQUESTS, "max_requests_per_case": 1,
        "usd_soft_limit": str(USD_LIMIT), "six_request_reservation_usd": str(RESERVATION_USD * 6),
        "per_case_transport": native.locator_qwen_configuration(), "baseline_sha256": PRIMARY_BASELINE_SHA256,
        "protocol_documents": [PROTOCOL, ERRATUM],
        "baseline_encoding": "unmodified_Python_JSON_sorted_compact_ASCII_allow_nan_false_no_newline",
        "historical_integer_normalized_baseline_sha256": HISTORICAL_INTEGER_NORMALIZED_BASELINE_SHA256,
        "first_failure_stops_batch": True, "resume": False,
        "credential_source": "process_DASHSCOPE_API_KEY_only",
        "elapsed_scope": "monotonic_case_setup_identity_callback_local_read_audit_and_publication_attempt",
        "elapsed_exclusions": "batch_setup_and_summary_publication_not_provider_latency_or_SLO",
        "count_scope": "local_callback_reservation_http_primitive_response_and_locator_read_observations",
        "count_limits": "not_network_delivery_attestation_provider_exactly_once_or_browser_delivery",
    }


def load_fixture():
    try:
        raw = (ROOT / FIXTURE).read_bytes()
        if _digest(raw) != FIXTURE_SHA256:
            raise CanaryStopped("fixture_identity_mismatch")
        fixture = _strict_json(raw.decode("utf-8"))
        if tuple(row["case_id"] for row in fixture["cases"]) != CASE_IDS:
            raise ValueError("case_order")
        catalog = build_catalog(snapshot_for(fixture))
        if (catalog["entries"] != [{**row, "title_truncated": False} for row in fixture["catalog"]]
                or catalog["total_count"] != 20
                or catalog["omitted_count"] or catalog["title_truncation_count"]):
            raise ValueError("catalog_projection")
        return fixture
    except (OSError, TypeError, ValueError, KeyError, RecursionError):
        raise CanaryStopped("fixture_invalid_or_unavailable") from None


def snapshot_for(fixture):
    # Unavailable provenance is literal, not a fabricated publisher/access date.
    return ReportEvidenceSnapshot(report_ref="public_bibliography_title_projection", sources=tuple(
        SnapshotSource(**row, group={"A": "academic", "P": "patent", "M": "market"}[row["source_id"][0]],
                       publisher="unavailable_public_bibliography_projection",
                       source_type="public_bibliography_title_projection", accessed_date="unavailable",
                       origin="unknown", summary=None)
        for row in fixture["catalog"]))


def _body(request):
    return {**request, "model": MODEL, "stream": False, "enable_thinking": False,
            "parallel_tool_calls": False, "temperature": 0, "max_tokens": MAX_TOKENS}


def request_identities(fixture):
    catalog = build_catalog(snapshot_for(fixture))
    identities = []
    for case in fixture["cases"]:
        callback = _encoded(locator._request(case["question"], catalog))
        wire = _encoded(_body(locator._request(case["question"], catalog)))
        if len(callback) > locator.MAX_CALLBACK_BYTES or len(wire) > REQUEST_BYTES:
            raise CanaryStopped("request_too_large")
        identities.append({"case_id": case["case_id"], "callback_sha256": _digest(callback),
                           "callback_bytes": len(callback), "native_sha256": _digest(wire),
                           "native_bytes": len(wire)})
    return identities


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
    """Bind disk/blobs/versions and requests; not installed-package attestation."""
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
        fixture = load_fixture()
        locked = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))["package"]
        installed = {name: version(name) for name in DEPENDENCIES}
        if any(value not in {row["version"] for row in locked if row["name"] == name} for name, value in installed.items()):
            raise CanaryStopped("installed_dependency_mismatch")
        config = configuration()
        return {"protocol_identity": PROTOCOL_IDENTITY, "commit": head, "fixture_sha256": FIXTURE_SHA256,
                "baseline_sha256": PRIMARY_BASELINE_SHA256, "snapshot_sha256": snapshot_for(fixture).snapshot_hash,
                "request_identities": request_identities(fixture), "disk_sha256": disk, "committed_sha256": committed,
                "comparison": "CRLF_to_LF_for_fixed_text_paths_only",
                "runtime": {"python": platform.python_version(), **installed},
                "configuration": config, "configuration_sha256": _digest(_encoded(config))}
    except (OSError, subprocess.SubprocessError, PackageNotFoundError, ValueError, TypeError, KeyError):
        raise CanaryStopped("identity_check_unavailable") from None


def require_baseline():
    try:
        observed = baseline.run_fixed_comparison()
        if (observed["state"] != "available" or observed["observed_cases"] != 6
                or observed["unavailable_cases"] != 0 or observed["paired_observations_observed"] != 12
                or _digest(_encoded(observed)) != PRIMARY_BASELINE_SHA256):
            raise ValueError("baseline")
        return observed
    except Exception:  # noqa: BLE001 -- baseline diagnostics cannot escape the admission boundary.
        raise CanaryStopped("baseline_unavailable_or_changed") from None


def validate_output():
    try:
        output = ROOT / FIXED_OUTPUT
        _plain_path(output)
        if os.path.lexists(output):
            raise CanaryStopped("output_creation_failed_or_occupied")
        if not output.parent.is_dir():
            raise ValueError("output_parent")
        return output
    except (OSError, ValueError, TypeError):
        raise CanaryStopped("invalid_output_destination") from None


def read_dedicated_key():
    key = os.environ.get("DASHSCOPE_API_KEY")
    validate_key(key)
    return key


def _safe_reason(exc, fallback):
    if type(exc) is CanaryStopped and len(exc.args) == 1:
        reason = exc.args[0]
        if type(reason) is str and reason in _SAFE_REASONS:
            return reason
    return fallback


def _publish(output, name, value):
    """Write once via atomic link, after full write/flush/fsync/close (local only)."""
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
    except Exception:  # noqa: BLE001 -- arbitrary paths/provider data/errors are never diagnostics.
        raise CanaryStopped("persistence_failed") from None
    try:
        pending.unlink()
    except OSError:
        pass  # Cleanup cannot revoke the already complete write-once publication.


class _Batch:
    def __init__(self, output):
        self.output, self.ledgers, self.stop_reason = output, [], None
        try:
            output.mkdir(exist_ok=False)
        except OSError:
            raise CanaryStopped("output_creation_failed_or_occupied") from None

    def totals(self):
        records = [row for ledger in self.ledgers for row in ledger.records]
        known = sum((Decimal(row.get("estimated_usd", "0")) for row in records), Decimal(0))
        consumed = sum((max(Decimal(row["reservation_usd"]), Decimal(row.get("estimated_usd", "0")))
                        for row in records), Decimal(0))
        unknown = sum(row["usage_status"] != "complete" for row in records)
        return {"request_count": len(records), "unknown_usage_requests": unknown,
                "known_usage_estimated_usd": str(known), "budget_consumed_usd": str(consumed),
                "reported_tokens": {key: sum(row.get("reported_usage", {}).get(key, 0) for row in records)
                                    for key in ("prompt_tokens", "completion_tokens", "total_tokens")},
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
            except Exception:  # noqa: BLE001 -- preserve in-memory usage/pending facts on persistence failure.
                ledger.stop_reason = self.stop_reason = "persistence_failed"


class _CheckedSelector:
    def __init__(self, transport, batch, identity):
        self.transport, self.batch, self.identity = transport, batch, identity
        self.entries, self.request, self.response, self.failure = 0, None, None, None
        self.http_entries, self.http_wire, self.http_received = 0, None, False
        original_post = transport._post

        async def observed_post(wire, observation):
            # Instance-local observation only: no global transport/limit override.
            self.http_entries += 1
            self.http_wire = wire
            try:
                return await original_post(wire, observation)
            finally:
                self.http_received = observation["received"]

        transport._post = observed_post

    def _identity(self):
        if verify_identity(self.identity["commit"], self.identity["fixture_sha256"]) != self.identity:
            raise CanaryStopped("runtime_identity_changed")

    def __call__(self, request, /):
        self.entries += 1
        try:
            if self.entries != 1:
                raise CanaryStopped("runner_request_limit")
            self.batch.admit()
            self._identity()
            self.request = deepcopy(request)
            try:
                self.response = deepcopy(self.transport(request))
                return deepcopy(self.response)
            finally:
                self._identity()  # Exceptional replies still retain accounting and post-call identity.
        except Exception as exc:  # noqa: BLE001 -- fixed categories only, including arbitrary CanaryStopped text.
            self.failure = _safe_reason(exc, "runner_preflight_or_transport_failed")
            self.batch.stop(self.failure, self.transport.ledger)
            raise CanaryStopped(self.failure) from None


def _accounting(ledger, case_id):
    """Reconcile memory with the durable journal; this audit performs file I/O."""
    if (type(ledger) is not native.LocatorQwenLedger or ledger.stop_reason is not None
            or ledger.pending is not None or len(ledger.records) != 1 or ledger.case_id != case_id):
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
    return (set(row) == set(reserved) | {"reported_usage", "estimated_usd", "error"}
            and (ledger.output_dir / "events.jsonl").read_bytes() == b"".join(_encoded(e) + b"\n" for e in expected))


def _serialized(result):
    if type(result) is not locator.LocatorResult:
        raise CanaryStopped("invalid_case_observation")
    observed = _strict_json(locator.render_locator_result(result))
    if _encoded(observed) != _encoded(result.model_dump(warnings="error")):
        raise CanaryStopped("invalid_case_observation")
    return observed


def _case_gate(case, snapshot, result, checked):
    """Mechanical audit, including journal reads, but never reference matching."""
    try:
        observed = _serialized(result)
        ledger = checked.transport.ledger
        if checked.failure is not None or not _accounting(ledger, case["case_id"]):
            return "transport_observation_failed", None
        catalog = build_catalog(snapshot)
        request = locator._request(case["question"], catalog)
        wire, callback = _encoded(_body(request)), _encoded(request)
        row = ledger.records[0]
        if (checked.entries != 1 or checked.http_entries != 1 or checked.http_received is not True
                or checked.http_wire != wire or _encoded(checked.request) != callback
                or _encoded(row["request"]) != wire or row["request_sha256"] != _digest(wire)
                or len(wire) > REQUEST_BYTES or len(callback) > locator.MAX_CALLBACK_BYTES):
            return "callback_native_audit_failed", None
        message = _assistant_message(checked.response)
        native._admit_selection(message, tuple(entry["source_id"] for entry in catalog["entries"]))
        calls = message.get("tool_calls") or []
        selected = None
        if calls:
            source_id = locator._Selection.model_validate(_strict_json(calls[0]["function"]["arguments"])).source_id
            source = next(source for source in snapshot.sources if source.source_id == source_id)
            if source.summary is not None:
                return "choice_projection_failed", None
            selected = {**source.model_dump(exclude={"summary"}), "stored_length": 0,
                        "snapshot_hash": snapshot.snapshot_hash, "source_hash": snapshot.source_hash(source),
                        "summary_hash": content_hash(None)}
            state, reason, reads = "missing_text", "saved_text_missing", 1
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
            "source": selected, "saved_text": None, "callback_entries": 1, "callback_bytes": len(callback),
            "read_attempts": reads, "read_completed": reads,
            "selection_relevance": "not_assessed", "semantic_support": "not_assessed",
        }
        # The locator checked the actual read; do not execute another read to
        # manufacture an observation. Compare the complete delivered JSON.
        if _encoded(observed) != _encoded(expected):
            return "choice_projection_failed", choice
        return None, choice
    except Exception:  # noqa: BLE001 -- malformed observations fail safely without raw diagnostics.
        return "invalid_case_observation", None


def _metrics(reference, ids, *, explicit_decline=False):
    intersection = None if ids is None else [source_id for source_id in ids if source_id in reference]
    return {"observed_ids": ids, "candidate_count": None if ids is None else len(ids),
            "acceptable_intersection": intersection,
            "reference_coverage": None if ids is None or not reference else len(intersection) / len(reference),
            "at_least_one_acceptable_location": None if ids is None or not reference else bool(intersection),
            "no_fit_control_match": None if ids is None or reference else explicit_decline and not ids}


def _reference_matches(case, choice):
    if case["acceptable_source_ids"]:
        return choice["kind"] == "selected" and choice["source_id"] in case["acceptable_source_ids"]
    return choice["kind"] == "declined"


def _counts(checked, ledger, result):
    # Native/callback counters are code-owned observations. Read/text counts
    # come from the locator projection and are unavailable unless that entire
    # projection passed mechanical reconciliation; rejection is not zero reads.
    return {"callback_entries": checked.entries if checked else 0,
            "reservations": len(ledger.records) if ledger else 0,
            "http_primitive_entries": checked.http_entries if checked else 0,
            "responses_received": int(checked.http_received) if checked else 0,
            "read_attempts": result.read_attempts if result else None,
            "read_completed": result.read_completed if result else None,
            "evidence_texts_delivered": int(result.saved_text is not None) if result else None}


def _aggregate_counts(outcomes):
    totals, coverage = {}, {}
    observed = [row for row in outcomes if row["state"] == "observed"]
    for key in _counts(None, None, None):
        available = [row["counts"][key] for row in observed if row["counts"][key] is not None]
        totals[key] = sum(available) if available else None
        coverage[key] = {
            "observed_cases": len(observed), "available_cases": len(available),
            "unavailable_cases": len(observed) - len(available),
            "state": "not_observed" if not available else
                     "partial" if len(available) != len(observed) else "complete_for_observed_cases",
        }
    return totals, coverage


def run_comparison(*, expected_commit, expected_fixture_sha256, authorize_paid):
    if type(authorize_paid) is not str or authorize_paid != PROTOCOL_IDENTITY:
        raise CanaryStopped("fresh_protocol_acknowledgement_required")
    identity = verify_identity(expected_commit, expected_fixture_sha256)
    fixture = load_fixture()
    observed_baseline = require_baseline()  # Before key lookup AND any directory/publication.
    validate_output()
    if verify_identity(expected_commit, expected_fixture_sha256) != identity:
        raise CanaryStopped("runtime_identity_changed")
    key = read_dedicated_key()
    batch = _Batch(validate_output())
    experiment = {"protocol_identity": PROTOCOL_IDENTITY, "configuration": configuration(),
                  "identity_sha256": _digest(_encoded(identity)), "baseline_sha256": PRIMARY_BASELINE_SHA256,
                  "protocol_documents": [PROTOCOL, ERRATUM],
                  "parent_operator_only": True, "old_allowance_reused": False}
    for name, value in (
        ("identity.json", identity), ("baseline.json", observed_baseline), ("experiment_manifest.json", experiment),
        ("authorization.json", {"operator_acknowledgement": authorize_paid, "expected_commit": expected_commit,
                                "expected_fixture_sha256": expected_fixture_sha256,
                                "standing_authorization_sources": [PROTOCOL, ERRATUM],
                                "identity_sha256": experiment["identity_sha256"],
                                "experiment_manifest_sha256": _digest(_encoded(experiment)),
                                "independent_user_consent_verified": False, "independent_review_verified": False,
                                "green_ci_verified": False, "old_allowance_reused": False}),
    ):
        _publish(batch.output, name, value)
    outcomes = []
    for case in fixture["cases"]:
        started = monotonic()
        ledger = result = observed = choice = checked = None
        try:
            batch.admit()
            snapshot = snapshot_for(fixture)
            ledger = native.LocatorQwenLedger(batch.output / case["case_id"])
            ledger.case_id = case["case_id"]
            batch.ledgers.append(ledger)
            transport = native.LocatorQwenTransport(key, ledger, snapshot=snapshot, question=case["question"])
            checked = _CheckedSelector(transport, batch, identity)
            result = locator.locate_saved_source(snapshot, case["question"], selector=checked)
            reason, choice = _case_gate(case, snapshot, result, checked)
            if checked.failure is not None:
                reason = checked.failure
            if reason is None:
                observed = _serialized(result)
        except Exception as exc:  # noqa: BLE001 -- retain paid facts, never raw errors or provider content.
            reason = _safe_reason(exc, "case_execution_failed")
        mechanical = reason is None
        if not mechanical:
            observed = choice = None
        reference = _reference_matches(case, choice) if mechanical else None
        if mechanical and reference is not True:
            reason = "reference_mismatch"
        ids = ([choice["source_id"]] if choice["kind"] == "selected" else []) if mechanical else None
        # A refusal is observed, but not an evaluable empty candidate set.
        if mechanical and choice["kind"] == "refused":
            ids = None
        outcome = {"case_id": case["case_id"], "state": "observed", "mechanical_passed": mechanical,
                   "reference_match_passed": reference, "gate_failure": reason, "choice": choice, "result": observed,
                   "metrics": _metrics(case["acceptable_source_ids"], ids,
                                       explicit_decline=mechanical and choice["kind"] == "declined"),
                   "counts": _counts(checked, ledger, result if mechanical else None),
                   "accounting": ledger.summary() if ledger else None,
                   "elapsed_before_case_publication_seconds": monotonic() - started}
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
    observed_count = len(outcomes)
    for case in fixture["cases"][observed_count:]:
        outcomes.append({"case_id": case["case_id"], "state": "unrun", "mechanical_passed": None,
                         "reference_match_passed": None, "gate_failure": None, "choice": None,
                         "metrics": _metrics(case["acceptable_source_ids"], None), "counts": None,
                         "accounting": None, "case_record_persisted": False,
                         "elapsed_before_case_publication_seconds": None,
                         "elapsed_through_case_publication_attempt_seconds": None})
    paired = []
    for case, outcome, assisted in zip(fixture["cases"], outcomes,
                                      observed_baseline["conditions"]["prepared_keyword_assisted"], strict=True):
        paired.append({"case_id": case["case_id"], "acceptable_source_ids": case["acceptable_source_ids"],
                       "prepared_keyword_assisted": _metrics(case["acceptable_source_ids"], assisted["observed_ids"],
                                                             explicit_decline=not assisted["observed_ids"]),
                       "native": outcome["metrics"]})
    totals = batch.totals()
    counts, count_coverage = _aggregate_counts(outcomes)
    summary = {
        "protocol_identity": PROTOCOL_IDENTITY, "mode": "public_title_development_comparison",
        "batch_passed": all(row["mechanical_passed"] and row["reference_match_passed"] is True
                            and row["case_record_persisted"] for row in outcomes)
        and totals["stop_reason"] is None and not totals["pending_cases"] and totals["unknown_usage_requests"] == 0,
        "planned_cases": 6, "positive_reference_cases": 5, "no_fit_cases": 1,
        "observed_cases": observed_count, "unrun_cases": list(CASE_IDS[observed_count:]),
        "mechanically_passed_cases": sum(row["mechanical_passed"] is True for row in outcomes),
        "reference_checks": sum(row["reference_match_passed"] is not None for row in outcomes),
        "reference_matches": sum(row["reference_match_passed"] is True for row in outcomes),
        "evaluable_positive_cases": sum(row["metrics"]["observed_ids"] is not None for row in outcomes[:5]),
        "evaluable_no_fit_cases": int(outcomes[5]["metrics"]["observed_ids"] is not None),
        "cases": outcomes, "paired_candidates": paired,
        "observed_counts": counts, "count_coverage": count_coverage,
        "reference_status": fixture["reference_status"], "semantic_support": "not_assessed",
        "benefit": "not_assessed", "human_time": "not_measured", "baseline_sha256": PRIMARY_BASELINE_SHA256,
        **{key: configuration()[key] for key in ("elapsed_scope", "elapsed_exclusions", "count_scope", "count_limits")},
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
        self.exit(2, "invalid_source_locator_comparison_arguments\n")


def main(argv=None):
    parser = _Parser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--expected-fixture-sha256", required=True)
    parser.add_argument("--authorize-paid", help="Exact SLCQ acknowledgement, not consent/review/CI verification.")
    args = parser.parse_args(argv)
    try:
        if args.authorize_paid is None:
            identity = verify_identity(args.expected_commit, args.expected_fixture_sha256)
            print(json.dumps({"mode": "identity_only", "identity_verified": True,
                              "live_authorized": False, "identity": identity}, ensure_ascii=True))
            return 0
        result = run_comparison(expected_commit=args.expected_commit, expected_fixture_sha256=args.expected_fixture_sha256,
                                authorize_paid=args.authorize_paid)
        print(json.dumps(result, ensure_ascii=True))
        return 0 if result["batch_passed"] and result["summary_persisted"] else 1
    except CanaryStopped:
        error = "source_locator_comparison_admission_or_persistence_failed"
    except Exception:  # noqa: BLE001 -- no arbitrary exception strings/credentials in CLI output.
        error = "source_locator_comparison_setup_failed"
    print(json.dumps({"batch_passed": False, "error": error}))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
