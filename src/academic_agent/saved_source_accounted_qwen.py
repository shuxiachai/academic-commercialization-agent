"""Explicit-key, one-shot accounting wrapper around the unchanged locator wire.

Construction owns a fresh private native ledger. Nothing discovers credentials,
reuses a batch, reads RQ output, configures a provider factory or grants live
authority. Only current-operation native events can supply usage observations.
"""

from copy import deepcopy
from decimal import Decimal
import hashlib
from pathlib import Path
import threading

from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_qwen_canary import RESERVATION_USD, _encoded
from academic_agent.report_evidence_qwen_transport import validate_key
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, content_hash
from academic_agent.report_evidence_source_locator_qwen_transport import LocatorQwenLedger, LocatorQwenTransport
from academic_agent.saved_source_usage import (
    AccountingError, NativeFactsV1, OperationContext, ReportedUsage, decimal_usd,
)

_MAX_EVENTS_BYTES = 96 * 1024


class AccountedQwenSelector:
    """One explicitly constructed snapshot/question/key and one attempted receipt."""

    def __init__(self, api_key, *, snapshot, question, ledger_dir):
        validate_key(api_key)
        if type(snapshot) is not ReportEvidenceSnapshot:
            raise AccountingError()
        self._snapshot = ReportEvidenceSnapshot.model_validate(snapshot.model_dump(warnings="error"))
        self._ledger = LocatorQwenLedger(Path(ledger_dir))
        self._native = LocatorQwenTransport(api_key, self._ledger, snapshot=self._snapshot, question=question)
        self._attempt_lock = threading.Lock()
        self._attempted = False
        self._operation = None

    def select(self, request, /, *, operation, observation):
        # Invalid input consumes this wrapper too. A second receipt cannot take
        # over a failed first attempt or replace its fresh ledger behind a GET.
        with self._attempt_lock:
            if self._attempted:
                raise AccountingError()
            self._attempted = True
        if type(operation) is not OperationContext:
            raise AccountingError()
        context = OperationContext.model_validate(operation.model_dump(warnings="error"))
        self._operation = context
        if (context != observation.operation or context.run_id != self._snapshot.report_ref
                or context.snapshot_hash != self._snapshot.snapshot_hash
                or context.catalog_hash != content_hash(build_catalog(self._snapshot))):
            raise AccountingError()

        durable_events = []
        failed_finish = None
        dispatch_entered = False
        append_failed = False
        wire_hash = None
        original_append, original_post = self._ledger._append, self._native._post

        def audited_append(event):
            nonlocal failed_finish, append_failed
            # This exact event comes from the frozen operation, not a global
            # mutable last-result. A failed fsync is never a durable finish.
            detached = deepcopy(event)
            try:
                original_append(event)
            except BaseException:
                append_failed = True
                if detached.get("event") == "request_finished":
                    failed_finish = detached
                raise
            durable_events.append(detached)

        def checked_events():
            expected = b"".join(_encoded(event) + b"\n" for event in durable_events)
            if len(expected) > _MAX_EVENTS_BYTES:
                raise AccountingError()
            with (self._ledger.output_dir / "events.jsonl").open("rb") as stream:
                actual = stream.read(_MAX_EVENTS_BYTES + 1)
            # An unacknowledged append tail is not durable evidence even when
            # its bytes happen to be readable after an fsync failure.
            if (len(actual) > _MAX_EVENTS_BYTES or actual[:len(expected)] != expected
                    or (not append_failed and actual != expected)):
                raise AccountingError()
            return deepcopy(durable_events)

        def checked_record(event, reserved, *, finishing=False):
            if (event.get("request_id") != 1 or type(event.get("request_id")) is not int
                    or event.get("case_id") is not None or event.get("request") != reserved.get("request")
                    or event.get("request_sha256") != reserved.get("request_sha256")
                    or _encoded(event.get("request")) != _encoded(reserved.get("request"))
                    or event.get("reservation_usd") != str(RESERVATION_USD)
                    or hashlib.sha256(_encoded(event["request"])).hexdigest() != event["request_sha256"]):
                raise AccountingError()
            if finishing and (type(event.get("provider_response_received")) is not bool
                    or type(event.get("protocol_accepted")) is not bool
                    or event.get("response_model_matches_authorized") not in (True, False, None)):
                raise AccountingError()

        async def guarded_post(wire, native_observation):
            nonlocal dispatch_entered, wire_hash
            events = checked_events()
            if len(events) != 1 or events[0].get("event") != "request_reserved":
                raise AccountingError()
            reserved = events[0]
            checked_record(reserved, reserved)
            if wire != _encoded(reserved["request"]) or dispatch_entered:
                raise AccountingError()
            wire_hash = hashlib.sha256(wire).hexdigest()
            # The native transport already validated and durably reserved this
            # exact wire. A failing sidecar fence must stop before original HTTP.
            observation.before_native_entry(wire_sha256=wire_hash, reservation_usd=decimal_usd(RESERVATION_USD))
            dispatch_entered = True
            return await original_post(wire, native_observation)

        def capture():
            events = checked_events()
            reserved = [event for event in events if event.get("event") == "request_reserved"]
            finished = [event for event in events if event.get("event") == "request_finished"]
            if len(reserved) > 1 or len(finished) > 1 or (finished and not reserved):
                raise AccountingError()
            usage = None
            model = None
            faults = []
            reservation = None
            digest = None
            journal = "not_started"
            dispatch = "may_have_dispatched" if dispatch_entered else "not_dispatched"
            if reserved:
                first = reserved[0]
                checked_record(first, first)
                digest, reservation = first["request_sha256"], decimal_usd(Decimal(first["reservation_usd"]))
                if wire_hash is not None and digest != wire_hash:
                    raise AccountingError()
                finish = finished[0] if finished else failed_finish
                journal = "complete" if finished else "unresolved"
                if not finished:
                    faults.append("native_journal_unresolved")
                if finish is not None:
                    checked_record(finish, first, finishing=True)
                    model = finish["response_model_matches_authorized"]
                    if finish["provider_response_received"]:
                        if not dispatch_entered:
                            raise AccountingError()
                        dispatch = "response_received"
                    if finish.get("usage_status") == "complete":
                        usage = ReportedUsage.model_validate(finish.get("reported_usage"))
                    elif finish.get("usage_status") != "unknown" or "reported_usage" in finish:
                        raise AccountingError()
                    if model is False:
                        faults.append("model_mismatch")
            elif dispatch_entered:
                raise AccountingError()
            # A coherent failed-finish event is only reported_partial after
            # capture itself commits to the sidecar. It never upgrades native
            # durability, receipt completion or the frozen transport's refusal.
            observation.capture(NativeFactsV1(
                wire_sha256=digest, dispatch_state=dispatch, native_journal_state=journal,
                model_matches_authorized=model, reported_usage=usage, reservation_usd=reservation,
                price_policy_id="locator_qwen_frozen_rates_v1" if reservation is not None else None,
                fault_codes=sorted(set(faults)),
            ))

        self._ledger._append = audited_append
        self._native._post = guarded_post
        try:
            return self._native(request)
        finally:
            try:
                capture()
            except Exception:  # noqa: BLE001 -- collector failures cannot replace a valid native message.
                pass
            finally:
                self._ledger._append = original_append
                self._native._post = original_post
