"""Two ordered synthetic receipt controls, not a provider factory or live grant.

The frozen locator transport owns the HTTP protocol and its per-case journal.
This composition adds one non-resumable aggregate gate. Runner-supplied browser
facts and identity checks remain explicitly separate from native observations.
No code here discovers credentials, mounts a route or starts a runner.
"""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import re
import threading
from typing import Literal
import uuid

from academic_agent import report_evidence_source_locator as locator
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_followup import _strict_json
from academic_agent.report_evidence_qwen_canary import (
    CanaryStopped, INPUT_RATE, INPUT_RESERVATION, MAX_TOKENS, MODEL,
    OUTPUT_RATE, REQUEST_BYTES, RESERVATION_USD, _encoded,
)
from academic_agent.report_evidence_qwen_transport import _usage
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot
from academic_agent.report_evidence_source_locator_qwen_transport import (
    LocatorQwenLedger, LocatorQwenTransport,
)
from academic_agent.saved_source_loader import valid_run_id

ADAPTER_IDENTITY = "saved_source_receipt_qwen_adapter_v1"
CASE_IDS = ("RQ01", "RQ02")
USD_LIMIT = Decimal("0.05")
_HASH = re.compile(r"[0-9a-f]{64}")
_ENTRY_FIELDS = {
    "case_id", "run_id", "snapshot_sha256", "question_sha256",
    "selector_identity_sha256", "callback_sha256", "wire_sha256",
}
_FACT_GATES = {
    "http_contract_passed", "reference_passed", "replay_passed",
    "browser_delivery_passed", "refresh_no_redispatch_passed", "source_identity_passed",
}
_FACT_COUNTS = {
    "post_requests": 1, "callback_entries": 1, "daily_admissions": 1,
    "active_paid_operations_after_drain": 0, "physical_threads_after_drain": 0,
}
_REASONS = {
    "batch_already_stopped", "persistence_failed", "invalid_manifest",
    "invalid_binding", "invalid_http_intent", "case_order", "attempt_consumed",
    "budget_limit", "request_identity_mismatch", "source_identity_mismatch",
    "invalid_native_ledger", "native_failed", "native_usage_unknown",
    "native_pending", "native_observation_changed", "case_gate_failed",
    "invalid_callback", "runner_stopped", "native_entry_repeated",
}


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _is_hash(value) -> bool:
    return type(value) is str and _HASH.fullmatch(value) is not None


def _body(request: dict) -> dict:
    return {**request, "model": MODEL, "stream": False, "enable_thinking": False,
            "parallel_tool_calls": False, "temperature": 0, "max_tokens": MAX_TOKENS}


def atomic_write_once(path: Path, value: dict) -> None:
    """Publish complete fsynced JSON without replacing any existing destination.

    Hard-link publication is atomic/no-replace on the supported local filesystems.
    Unsupported filesystems fail closed. This is not disk-loss durability; Windows
    has no portable Python directory-fsync primitive.
    """
    path = Path(path)
    temporary = path.parent / (".pending-" + uuid.uuid4().hex)
    try:
        raw = _encoded(value) + b"\n"
        with temporary.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        if os.name != "nt":
            descriptor = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    except Exception:  # noqa: BLE001 -- no paths, JSON contents or arbitrary filesystem diagnostics escape.
        raise CanaryStopped("persistence_failed") from None
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            # A leftover complete temporary file is not permission to overwrite
            # the published destination or to reuse the occupied batch.
            pass


@dataclass(frozen=True)
class CaseBinding:
    case_id: Literal["RQ01", "RQ02"]
    run_id: str
    snapshot: ReportEvidenceSnapshot
    question: str
    selector_identity: str

    def __post_init__(self):
        try:
            if (type(self.case_id) is not str or self.case_id not in CASE_IDS
                    or not valid_run_id(self.run_id)
                    or type(self.snapshot) is not ReportEvidenceSnapshot
                    or type(self.question) is not str or not 1 <= len(self.question) <= 4096
                    or not self.question.strip() or type(self.selector_identity) is not str
                    or not 1 <= len(self.selector_identity) <= 256 or not self.selector_identity.strip()):
                raise ValueError
            self.question.encode("utf-8")
            self.selector_identity.encode("utf-8")
            snapshot = ReportEvidenceSnapshot.model_validate(self.snapshot.model_dump(warnings="error"))
            if snapshot.report_ref != self.run_id:
                raise ValueError
            object.__setattr__(self, "snapshot", snapshot)
            request = locator._request(self.question, build_catalog(snapshot))
            if not snapshot.sources or len(_encoded(_body(request))) > REQUEST_BYTES:
                raise ValueError
        except Exception:  # noqa: BLE001 -- constructed model errors may contain synthetic/private input.
            raise CanaryStopped("invalid_binding") from None

    def manifest_entry(self) -> dict:
        request = locator._request(self.question, build_catalog(self.snapshot))
        return {
            "case_id": self.case_id, "run_id": self.run_id,
            "snapshot_sha256": self.snapshot.snapshot_hash,
            "question_sha256": _digest(self.question.encode("utf-8")),
            "selector_identity_sha256": _digest(self.selector_identity.encode("utf-8")),
            "callback_sha256": _digest(_encoded(request)),
            "wire_sha256": _digest(_encoded(_body(request))),
        }


class BatchGate:
    """One fresh batch directory; locks serialize bookkeeping, not provider work.

    A runner may hand ownership to a controller thread and back after draining.
    No process recovery, new-directory retry authority or distributed quota is
    implied. Only the caller can enforce the protocol's fixed output location.
    """

    def __init__(self, output_dir: Path, manifest: dict):
        try:
            if (type(manifest) is not dict or set(manifest) != {
                    "schema_version", "fixture_sha256", "source_identity_sha256", "cases"}
                    or type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1
                    or not _is_hash(manifest["fixture_sha256"])
                    or not _is_hash(manifest["source_identity_sha256"])
                    or type(manifest["cases"]) is not list or len(manifest["cases"]) != 2):
                raise ValueError
            entries = deepcopy(manifest["cases"])
            for case_id, entry in zip(CASE_IDS, entries, strict=True):
                if (type(entry) is not dict or set(entry) != _ENTRY_FIELDS or entry["case_id"] != case_id
                        or not valid_run_id(entry["run_id"])
                        or not all(_is_hash(entry[key]) for key in _ENTRY_FIELDS - {"case_id", "run_id"})):
                    raise ValueError
            if entries[0]["run_id"] == entries[1]["run_id"]:
                raise ValueError
        except Exception:  # noqa: BLE001 -- a manifest is data, never authority or a safe error string.
            raise CanaryStopped("invalid_manifest") from None
        self.output_dir = Path(output_dir)
        self._lock = threading.RLock()
        self._sequence = 0
        self.stop_reason = None
        self._entries = {row["case_id"]: row for row in entries}
        self._cases = {case_id: {
            "http_intent": None, "attempts_consumed": 0, "reservation_usd": "0",
            "native_transport_entries": 0, "native_http_entries": 0,
            "native": None, "completed": False,
        } for case_id in CASE_IDS}
        self._ledgers = {}
        try:
            self.output_dir.mkdir(exist_ok=False)
            atomic_write_once(self.output_dir / "manifest.json", deepcopy(manifest))
        except Exception:  # noqa: BLE001 -- never recreate or resume a partially created batch.
            raise CanaryStopped("persistence_failed") from None

    def _event(self, event: dict):
        try:
            atomic_write_once(self.output_dir / f"event-{self._sequence + 1:04d}.json", event)
            self._sequence += 1
        except Exception:  # noqa: BLE001 -- a failed durable event permanently closes this in-memory gate.
            self.stop_reason = "persistence_failed"
            raise CanaryStopped("persistence_failed") from None

    def stop(self, reason: str) -> None:
        with self._lock:
            reason = reason if type(reason) is str and reason in _REASONS else "runner_stopped"
            if self.stop_reason is None:
                self.stop_reason = reason
                self._event({"event": "batch_stopped", "reason": reason})

    def _fail(self, reason):
        self.stop(reason)
        raise CanaryStopped(self.stop_reason) from None

    def _current(self, case_id):
        if self.stop_reason is not None:
            raise CanaryStopped("batch_already_stopped") from None
        if type(case_id) is not str or case_id not in CASE_IDS:
            self._fail("case_order")
        if case_id == "RQ02" and not self._cases["RQ01"]["completed"]:
            self._fail("case_order")
        return self._cases[case_id]

    def bind_http_intent(self, case_id: str, receipt_key_sha256: str, owner_id: str) -> None:
        with self._lock:
            row = self._current(case_id)
            if (row["http_intent"] is not None or not _is_hash(receipt_key_sha256)
                    or type(owner_id) is not str or re.fullmatch(r"[0-9a-f]{16}", owner_id) is None
                    or any(other["http_intent"] is not None
                           and other["http_intent"]["receipt_key_sha256"] == receipt_key_sha256
                           for other in self._cases.values())):
                self._fail("invalid_http_intent")
            intent = {"receipt_key_sha256": receipt_key_sha256, "owner_id": owner_id}
            self._event({"event": "runner_pre_post_intent", "case_id": case_id, **intent})
            row["http_intent"] = intent

    def reserve(self, binding: CaseBinding, callback_sha256: str | None, wire_sha256: str | None) -> None:
        with self._lock:
            if type(binding) is not CaseBinding:
                self._fail("invalid_binding")
            row = self._current(binding.case_id)
            if row["attempts_consumed"]:
                self._fail("attempt_consumed")
            # Consume before validating input. A new wrapper cannot repair an
            # invalid callback or reset an aggregate failure.
            row["attempts_consumed"] = 1
            self._event({"event": "attempt_consumed", "case_id": binding.case_id})
            if row["http_intent"] is None:
                self._fail("invalid_http_intent")
            try:
                matches = binding.manifest_entry() == self._entries[binding.case_id]
            except Exception:  # noqa: BLE001 -- object-level model mutation is not an alternate binding.
                matches = False
            if (not matches or callback_sha256 != self._entries[binding.case_id]["callback_sha256"]
                    or wire_sha256 != self._entries[binding.case_id]["wire_sha256"]):
                self._fail("request_identity_mismatch")
            if Decimal(self.summary()["budget_consumed_usd"]) + RESERVATION_USD > USD_LIMIT:
                self._fail("budget_limit")
            row["reservation_usd"] = str(RESERVATION_USD)
            self._event({"event": "aggregate_reserved", "case_id": binding.case_id,
                         "reservation_usd": str(RESERVATION_USD),
                         "callback_sha256": callback_sha256, "wire_sha256": wire_sha256})

    def _enter_native(self, binding, ledger):
        with self._lock:
            row = self._current(binding.case_id)
            if (row["native_transport_entries"] or row["reservation_usd"] != str(RESERVATION_USD)
                    or type(ledger) is not LocatorQwenLedger
                    or ledger.output_dir.resolve() != (self.output_dir / binding.case_id).resolve()
                    or ledger.records or ledger.pending is not None or ledger.stop_reason is not None):
                self._fail("invalid_native_ledger")
            self._ledgers[binding.case_id] = ledger
            ledger.case_id = binding.case_id
            row["native_transport_entries"] = 1
            self._event({"event": "native_transport_entry", "case_id": binding.case_id})

    def _http_entry(self, case_id, wire):
        with self._lock:
            row = self._current(case_id)
            ledger = self._ledgers[case_id]
            if row["native_http_entries"]:
                self._fail("native_entry_repeated")
            if (type(wire) is not bytes or _digest(wire) != self._entries[case_id]["wire_sha256"]
                    or len(ledger.records) != 1 or ledger.pending != 1
                    or ledger.records[0]["request_sha256"] != _digest(wire)
                    or _encoded(ledger.records[0]["request"]) != wire):
                self._fail("request_identity_mismatch")
            self._event({"event": "native_http_entry", "case_id": case_id})
            row["native_http_entries"] = 1

    def observe_native(self, case_id: str, ledger: LocatorQwenLedger) -> None:
        with self._lock:
            if (type(case_id) is not str or case_id not in CASE_IDS
                    or self._ledgers.get(case_id) is not ledger):
                self._fail("invalid_native_ledger")
            row = self._cases[case_id]
            records = ledger.records
            record = records[0] if len(records) == 1 else {}
            usage = _usage({"usage": record.get("reported_usage")})
            estimate = (Decimal(usage["prompt_tokens"]) * INPUT_RATE
                        + Decimal(usage["completion_tokens"]) * OUTPUT_RATE) / 1_000_000 if usage else Decimal(0)
            observation = {
                "reserved_requests": len(records), "pending": ledger.pending is not None,
                "provider_response_received": record.get("provider_response_received") is True,
                "usage_status": "complete" if usage is not None else "unknown",
                "reported_usage": usage, "estimated_usd": str(estimate),
                "protocol_accepted": record.get("protocol_accepted") is True,
                "model_matches": record.get("response_model_matches_authorized") is True,
                "request_matches": record.get("request_sha256") == self._entries[case_id]["wire_sha256"],
                "ledger_stopped": ledger.stop_reason is not None,
            }
            if row["native"] is not None:
                if row["native"] != observation:
                    self._fail("native_observation_changed")
                return
            # Retain actual usage in memory even if this publication fails.
            row["native"] = observation
            self._event({"event": "native_observed", "case_id": case_id, **observation})
            if observation["pending"]:
                self._fail("native_pending")
            if usage is None:
                self._fail("native_usage_unknown")
            if (len(records) != 1 or row["native_http_entries"] != 1
                    or not all(observation[key] for key in (
                        "provider_response_received", "protocol_accepted", "model_matches", "request_matches"))
                    or observation["ledger_stopped"] or usage["prompt_tokens"] > INPUT_RESERVATION
                    or usage["completion_tokens"] > MAX_TOKENS):
                self._fail("native_failed")

    def complete_case(self, case_id: str, checked_http_browser_facts: dict) -> None:
        with self._lock:
            row = self._current(case_id)
            if case_id not in self._ledgers:
                self._fail("case_gate_failed")
            self.observe_native(case_id, self._ledgers[case_id])
            fields = _FACT_GATES | set(_FACT_COUNTS) | {
                "get_requests", "run_id", "receipt_key_sha256",
                "snapshot_sha256_before", "snapshot_sha256_after",
            }
            facts = checked_http_browser_facts
            if (row["completed"] or row["native"] is None
                    or type(facts) is not dict or set(facts) != fields
                    or any(facts[key] is not True for key in _FACT_GATES)
                    or any(type(facts[key]) is not int or facts[key] != expected
                           for key, expected in _FACT_COUNTS.items())
                    or type(facts["get_requests"]) is not int or facts["get_requests"] < 1
                    or facts["run_id"] != self._entries[case_id]["run_id"]
                    or facts["receipt_key_sha256"] != row["http_intent"]["receipt_key_sha256"]
                    or any(facts[key] != self._entries[case_id]["snapshot_sha256"]
                           for key in ("snapshot_sha256_before", "snapshot_sha256_after"))):
                self._fail("case_gate_failed")
            self._event({"event": "case_completed", "case_id": case_id, "facts": deepcopy(facts)})
            row["completed"] = True

    def summary(self) -> dict:
        with self._lock:
            rows = tuple(self._cases.values())
            native = [row["native"] for row in rows if row["native"] is not None]
            known = sum((Decimal(item["estimated_usd"]) for item in native), Decimal(0))
            consumed = sum((max(Decimal(row["reservation_usd"]),
                                Decimal((row["native"] or {}).get("estimated_usd", "0"))) for row in rows), Decimal(0))
            return {
                "adapter_identity": ADAPTER_IDENTITY,
                "attempts_consumed": sum(row["attempts_consumed"] for row in rows),
                "native_transport_entries": sum(row["native_transport_entries"] for row in rows),
                "native_http_entries": sum(row["native_http_entries"] for row in rows),
                "native_reserved_requests": sum(len(ledger.records) for ledger in self._ledgers.values()),
                "provider_responses_received": sum(item["provider_response_received"] for item in native),
                "unknown_usage_requests": sum(row["reservation_usd"] != "0" and
                    (row["native"] is None or row["native"]["usage_status"] != "complete") for row in rows),
                "known_usage_estimated_usd": str(known), "budget_consumed_usd": str(consumed),
                "price_scope": "frozen_conservative_estimate_not_invoice",
                "pending_cases": [case_id for case_id, row in self._cases.items()
                                  if row["reservation_usd"] != "0" and
                                  (row["native"] is None or row["native"]["pending"])],
                "stop_reason": self.stop_reason,
                "case_gates": {case_id: row["completed"] for case_id, row in self._cases.items()},
            }


class BoundCaseSelector:
    """Strict positional callback; actual HTTP and receipt authority stay separate."""

    def __init__(self, api_key: str, binding: CaseBinding, batch: BatchGate,
                 ledger: LocatorQwenLedger, *, check_identity: Callable[[], None]):
        if type(binding) is not CaseBinding or type(batch) is not BatchGate or not callable(check_identity):
            raise CanaryStopped("invalid_binding") from None
        self.binding = CaseBinding(binding.case_id, binding.run_id, binding.snapshot,
                                   binding.question, binding.selector_identity)
        self._batch, self._ledger, self._check_identity = batch, ledger, check_identity
        self._transport = LocatorQwenTransport(api_key, ledger, snapshot=self.binding.snapshot,
                                              question=self.binding.question)
        self.native_transport_entries = 0
        self._audit = {"callback_entries": 0, "callback_sha256": None,
                       "native_transport_entries": 0, "native_http_entries": 0, "selection": None}
        original_post = self._transport._post

        async def observed_post(wire, observation):
            # Observe only this call edge; delegate the original pinned primitive
            # unchanged. A reservation alone never increments this counter.
            self._batch._http_entry(self.binding.case_id, wire)
            self._audit["native_http_entries"] += 1
            return await original_post(wire, observation)

        self._transport._post = observed_post

    def audit(self) -> dict:
        return deepcopy(self._audit)

    def _identity(self):
        try:
            if self._check_identity() is not None:
                raise ValueError
        except Exception:  # noqa: BLE001 -- identity failures cannot disclose fixture, source or credential text.
            self._batch._fail("source_identity_mismatch")

    def __call__(self, *args, **kwargs):
        # Validate the positional-only contract inside the gate so wrong arity
        # and keyword entry consume the sole attempt instead of permitting repair.
        self._audit["callback_entries"] += 1
        request = None
        callback_sha256 = wire_sha256 = None
        try:
            if len(args) == 1 and not kwargs and type(args[0]) is dict:
                request = deepcopy(args[0])
                callback_sha256 = _digest(_encoded(request))
                wire_sha256 = _digest(_encoded(_body(request)))
        except Exception:  # noqa: BLE001 -- invalid input consumes the attempt without saving raw input.
            request = None
        self._audit["callback_sha256"] = callback_sha256
        self._batch.reserve(self.binding, callback_sha256, wire_sha256)
        self._identity()
        self._batch._enter_native(self.binding, self._ledger)
        self.native_transport_entries += 1
        self._audit["native_transport_entries"] += 1
        message = None
        error = False
        try:
            message = self._transport(request)
        except Exception:  # noqa: BLE001 -- the native ledger, not an exception string, carries safe observations.
            error = True
        finally:
            try:
                self._identity()
            finally:
                self._batch.observe_native(self.binding.case_id, self._ledger)
        if error:
            self._batch._fail("native_failed")
        calls = message.get("tool_calls") or []
        self._audit["selection"] = {
            "kind": "read_source" if calls else "refusal" if message.get("refusal") else "decline",
            "source_id": _strict_json(calls[0]["function"]["arguments"])["source_id"] if calls else None,
        }
        return message
