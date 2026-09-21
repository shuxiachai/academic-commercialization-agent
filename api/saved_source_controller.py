"""Isolated backend: explicit opt-in accounting, no provider/key discovery.

Each intent owns a dedicated thread and a separate durable receipt. Admission
is shared with runs/PDF, but a receipt is not a provider billing observation.
"""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
import hashlib
import json
import threading

from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, content_hash, read_source
from academic_agent.report_evidence_source_locator import (
    LocatorResult, LocatorSource, LocatorText, MAX_SAVED_CODEPOINTS,
    _expected_read, locate_saved_source, render_locator_result,
)
from academic_agent.saved_source_loader import SavedSourceMissing, valid_run_id
from academic_agent.saved_source_usage import (
    AccountingError, ExecutionFactsV1, MAX_ACCOUNTING_BYTES, UsageProjectionV1, unavailable_usage,
)
from api import access, runs
from api.saved_source_receipts import (
    Binding, Journal, OPERATION, Projection, ReceiptError, canonical,
)


def _digest(raw):
    return hashlib.sha256(raw.encode("ascii")).hexdigest()


def _validated_snapshot(value, run_id):
    if type(value) is not ReportEvidenceSnapshot:
        raise ValueError("invalid_snapshot")
    snapshot = ReportEvidenceSnapshot.model_validate(value.model_dump(warnings="error"))
    if snapshot.report_ref != run_id:
        raise ValueError("invalid_snapshot_identity")
    return snapshot


def _binding(snapshot):
    return Binding(snapshot_hash=snapshot.snapshot_hash, catalog_hash=content_hash(build_catalog(snapshot)))


def _projection(result):
    raw = render_locator_result(result)
    # The renderer revalidates nested objects; retain its checked facts rather
    # than trusting model_copy/model_construct or a callback's claimed hashes.
    checked = LocatorResult.model_validate_json(raw)
    source = checked.source
    return Projection(
        **checked.model_dump(include={"state", "reason", "catalog", "callback_entries", "callback_bytes",
                                      "read_attempts", "read_completed"}),
        source_id=source.source_id if source else None,
        source_hash=source.source_hash if source else None,
        summary_hash=source.summary_hash if source else None,
        result_digest=_digest(raw),
    ), json.loads(raw)


def _reconstruct(record, snapshot, *, delivery_read):
    """Restore original execution facts; fresh delivery reads are separate facts."""
    projection = record.projection
    source = text = None
    if projection.source_id is not None:
        saved = next(item for item in snapshot.sources if item.source_id == projection.source_id)
        source = LocatorSource(
            **saved.model_dump(exclude={"summary"}), stored_length=saved.stored_length,
            snapshot_hash=snapshot.snapshot_hash, source_hash=snapshot.source_hash(saved),
            summary_hash=content_hash(saved.summary),
        )
        if source.source_hash != projection.source_hash or source.summary_hash != projection.summary_hash:
            raise ValueError("changed_source")
        if projection.state in {"excerpt", "blank_text", "missing_text"}:
            actual = delivery_read(snapshot, saved.source_id, 0, MAX_SAVED_CODEPOINTS)
            if type(actual) is not dict or canonical(actual) != canonical(_expected_read(saved, source)):
                raise ValueError("invalid_delivery_read")
            if projection.state != "missing_text":
                text = LocatorText(**{key: actual[key] for key in LocatorText.model_fields})
    result = LocatorResult(
        **projection.model_dump(include={"state", "reason", "catalog", "callback_entries", "callback_bytes",
                                         "read_attempts", "read_completed"}),
        source=source, saved_text=text,
    )
    raw = render_locator_result(result)
    if _digest(raw) != projection.result_digest:
        raise ValueError("changed_projection")
    return json.loads(raw)


class _RequestIntent:
    """Linearize abandonment versus starting admission without blocking asyncio."""

    def __init__(self):
        self._lock = threading.Lock()
        self._abandoned = False
        self._admission_started = False

    def abandon(self):
        with self._lock:
            self._abandoned = True

    def check(self, *, start_admission=False):
        with self._lock:
            if self._abandoned and not self._admission_started:
                raise ReceiptError("request_abandoned")
            if start_admission:
                # This is the admission-start linearization point. No lock is
                # held across disk I/O. Cancellation after this point cannot
                # retract accounting, interrupt dispatch or justify a refund.
                self._admission_started = True


class SavedSourceController:
    """Single-process preparation; injected loader/selector are trusted Python.

    Execute is disabled without a selector and explicit immutable configuration
    identity. Lookup deliberately works when disabled, allowing safe rollback.
    """

    def __init__(self, load_snapshot, journal_root, selector=None, selector_identity=None, *,
                 accounted_selector=None, accounting_store=None):
        if not callable(load_snapshot) or (selector is not None and not callable(selector)):
            raise ValueError("invalid_saved_source_controller")
        if selector is not None and accounted_selector is not None:
            raise ValueError("mutually_exclusive_selectors")
        if accounted_selector is not None and (
                not callable(getattr(accounted_selector, "select", None)) or accounting_store is None):
            raise ValueError("invalid_accounted_selector")
        if accounting_store is not None and not all(callable(getattr(accounting_store, name, None))
                                                     for name in ("begin", "observe")):
            raise ValueError("invalid_accounting_store")
        if (selector is not None or accounted_selector is not None) and (type(selector_identity) is not str
                or not 1 <= len(selector_identity) <= 256 or not selector_identity.strip()):
            raise ValueError("invalid_selector_identity")
        self._load_snapshot = load_snapshot
        self._selector = selector
        self._selector_identity = selector_identity
        self._accounted_selector = accounted_selector
        self._accounting_store = accounting_store
        self._journal = Journal(journal_root)
        self._gate = threading.RLock()
        self._closed = False
        self._threads: dict[str, threading.Thread] = {}

    @staticmethod
    def _authenticate(access_code):
        # matching_code returns None with the legacy gate unset. Never use
        # access.check here: its development-mode free pass cannot name a payer.
        if type(access_code) is not str:
            raise ReceiptError("access_denied")
        try:
            code = access.matching_code(access_code)
        except (TypeError, ValueError):
            code = None
        if code is None:
            raise ReceiptError("access_denied")
        return access.owner_id(code), access.is_admin(code)

    @staticmethod
    def _authorize_run(run_id, owner):
        try:
            actual = runs.owner_of(run_id)
        except (OSError, UnicodeDecodeError):
            # Invalid UTF-8 owner bytes are unavailable authorization evidence,
            # just like unreadable storage; never expose decoder input/paths.
            raise ReceiptError("access_denied") from None
        # Admin may observe another owner's receipt, but execute never changes
        # the payer or spends on an ownerless/read-capability-only report.
        if actual is None or actual != owner:
            raise ReceiptError("access_denied")

    def _observe(self, record, *, result=None):
        with self._gate:
            thread = self._threads.get(record.key_hash)
            active = thread is not None and thread.is_alive()
        state = "unknown" if record.state == "pending" and not active else record.state
        reply = {
            "schema_version": 1, "operation": OPERATION, "state": state,
            "run_id": record.run_id, "expires_at": record.expires,
            "admission_state": record.admission,
            "provider_usage": "not_observed", "provider_cost": "not_observed",
            "error_code": record.error_code, "delivery": "not_ready",
            "delivery_snapshot_reads": 0, "delivery_source_reads": 0, "result": None,
        }
        if self._accounting_store is not None:
            try:
                value = self._accounting_store.observe(record)
                if type(value) is not dict or len(canonical(value).encode("ascii")) > MAX_ACCOUNTING_BYTES:
                    raise AccountingError()
                checked = UsageProjectionV1.model_validate(value)
                if (checked.receipt_key_sha256 != record.key_hash or checked.run_id != record.run_id
                        or checked.expires_at != record.expires):
                    raise AccountingError()
                reply["accounting"] = checked.model_dump(mode="json")
            except Exception:  # noqa: BLE001 -- accounting delivery faults must not erase a valid saved result.
                reply["accounting"] = unavailable_usage(record.key_hash, record.run_id, record.expires)
        if record.state != "completed":
            return reply
        if result is not None:
            return {**reply, "delivery": "available", "result": result}
        reply["delivery_snapshot_reads"] = 1
        try:
            snapshot = _validated_snapshot(self._load_snapshot(record.run_id), record.run_id)
        except SavedSourceMissing:
            return {**reply, "delivery": "expired"}
        except Exception:  # noqa: BLE001 -- loader details and private paths never leave this boundary.
            return {**reply, "delivery": "unavailable"}

        def delivery_read(*args):
            # Count the actual attempt before entering the reader. Returning
            # counters only from successful reconstruction erased attempts when
            # reading, validation or the final digest check failed. This is not
            # a successful-read count and never changes historical locator facts.
            reply["delivery_source_reads"] += 1
            return read_source(*args)

        try:
            if _binding(snapshot) != record.binding:
                return {**reply, "delivery": "changed"}
            result = _reconstruct(record, snapshot, delivery_read=delivery_read)
            return {**reply, "delivery": "available", "result": result}
        except Exception:  # noqa: BLE001 -- malformed reads/digests are not permission to select again.
            return {**reply, "delivery": "unavailable"}

    def _operate(self, ticket, run_id, question, access_code, owner, intent, claimed):
        admission = "not_admitted"
        admission_error = None
        observation = None
        accounted_entries = 0

        def seal(record=None):
            if observation is not None:
                try:
                    observation.seal(ExecutionFactsV1(
                        receipt_state=record.state if record is not None else "unresolved",
                        admission_state=record.admission if record is not None else admission,
                        accounted_selector_entries=accounted_entries,
                        result_digest=record.projection.result_digest if record is not None and record.projection else None,
                    ))
                except Exception:  # noqa: BLE001 -- a sidecar fault cannot overwrite durable receipt truth.
                    pass

        def finish(record, *, result=None):
            # This runs on the actual operation thread, before reply publication
            # and physical lease release, whether or not an HTTP waiter exists.
            seal(record)
            return self._observe(record, result=result)

        def admitted_selector(request):
            nonlocal admission, admission_error, accounted_entries
            try:
                # Revocation during a slow loader must stop before paid entry.
                current_owner, _ = self._authenticate(access_code)
                if current_owner != owner:
                    raise ReceiptError("access_denied")
                self._authorize_run(run_id, owner)
                intent.check(start_admission=True)
                ticket.admitting()
                admission = "unknown"
                runs.reserve_thread_paid_operation(owner=owner, byok=False)
                admission = "admitted"
                ticket.admitted()
            except runs.ConcurrencyLimitReached:
                admission, admission_error = "not_admitted", "concurrency_limit"
                raise
            except runs.DailyCapReached:
                admission, admission_error = "not_admitted", "daily_quota_exceeded"
                raise
            except runs.PaidLedgerUnavailable:
                admission_error = "paid_ledger_unavailable"
                raise
            except ReceiptError as exc:
                admission_error = exc.code
                raise
            if self._accounted_selector is not None:
                operation = observation.operation
                accounted_entries += 1
                return self._accounted_selector.select(request, operation=operation, observation=observation)
            return self._selector(request)

        try:
            if self._accounted_selector is not None:
                observation = self._accounting_store.begin(claimed)
            try:
                snapshot = _validated_snapshot(self._load_snapshot(run_id), run_id)
            except SavedSourceMissing:
                return finish(ticket.fail("saved_source_missing", admission=admission))
            except Exception:  # noqa: BLE001 -- a loader fault is safely classified before any paid callback.
                return finish(ticket.fail("saved_source_unavailable", admission=admission))
            bound = ticket.bind(_binding(snapshot))
            if observation is not None:
                observation.bind(bound, self._selector_identity)
            result = locate_saved_source(snapshot, question, selector=admitted_selector)
            # The frozen locator intentionally catches callback exceptions.
            # Preserve admission categories out-of-band instead of calling a
            # concurrency/daily rejection a provider fault or valid completion.
            if admission_error is not None:
                if admission_error not in {"concurrency_limit", "daily_quota_exceeded", "paid_ledger_unavailable",
                                           "access_denied", "request_abandoned"}:
                    raise ReceiptError("receipt_unavailable")
                return finish(ticket.fail(admission_error, admission=admission))
            projection, delivered = _projection(result)
            record = ticket.complete(projection)
            return finish(record, result=delivered)
        except ReceiptError:
            # A lost durable write stays unresolved. Never overwrite it with a
            # guessed failure/free status, even when no waiter remains.
            seal()
            raise ReceiptError("receipt_unavailable") from None
        except BaseException:  # Trusted-code SystemExit must settle the future without leaking its content.
            try:
                return finish(ticket.fail("execution_unavailable", admission=admission))
            except Exception:  # noqa: BLE001 -- failed finalization cannot be reported as a durable failure.
                seal()
                raise ReceiptError("receipt_unavailable") from None

    def _begin(self, key, run_id, question, access_code, intent):
        with self._gate:
            intent.check()
            owner, _ = self._authenticate(access_code)
            if self._closed:
                raise ReceiptError("controller_closed")
            if self._selector is None and self._accounted_selector is None:
                raise ReceiptError("selector_disabled")
            if (not valid_run_id(run_id) or type(question) is not str
                    or not 1 <= len(question) <= 4096 or not question.strip()):
                raise ReceiptError("invalid_request")
            try:
                question.encode("utf-8")
            except UnicodeError:
                raise ReceiptError("invalid_request") from None
            self._authorize_run(run_id, owner)
            self._threads = {key_hash: thread for key_hash, thread in self._threads.items() if thread.is_alive()}
            # Bound preprocessing too: a loader has no paid slot yet. Existing
            # intents may still be observed, but new ones cannot create a fanout
            # of thousands of blocked loader threads from the receipt ceiling.
            ticket, record = self._journal.claim(key, owner, run_id, question, self._selector_identity,
                                                 allow_new=not self._threads)
            if ticket is None:
                return self._observe(record)
            try:
                intent.check()
            except ReceiptError:
                return self._observe(ticket.fail("request_abandoned", admission="not_admitted"))
            future = Future()

            def worker():
                try:
                    future.set_result(self._operate(ticket, run_id, question, access_code, owner, intent, record))
                except BaseException:  # An abandoned waiter must not produce a private thread traceback.
                    future.set_result(ReceiptError("receipt_unavailable"))

            self._threads = {key_hash: thread for key_hash, thread in self._threads.items() if thread.is_alive()}
            thread = threading.Thread(target=worker, name="saved-source-controller")
            self._threads[ticket.key_hash] = thread
            try:
                thread.start()
            except RuntimeError:
                del self._threads[ticket.key_hash]
                return self._observe(ticket.fail("execution_unavailable", admission="not_admitted"))
            return future

    async def execute(self, key, run_id, question, access_code):
        # Even claim/loader/replay I/O stays off the event loop. Cancellation
        # cannot retract a committed intent or cancel the physical owner.
        intent = _RequestIntent()
        startup = asyncio.create_task(asyncio.to_thread(self._begin, key, run_id, question, access_code, intent))
        # If a queued waiter disappears, retrieve its eventual safe exception
        # without an unobserved-task warning; the queued begin checks abandonment.
        startup.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        try:
            reply = await asyncio.shield(startup)
            if isinstance(reply, Future):
                reply = await asyncio.shield(asyncio.wrap_future(reply))
            if isinstance(reply, ReceiptError):
                raise reply
            return reply
        except asyncio.CancelledError:
            intent.abandon()
            raise

    def _lookup(self, key, access_code):
        owner, admin = self._authenticate(access_code)
        return self._observe(self._journal.lookup(key, owner, admin=admin))

    async def lookup(self, key, access_code):
        return await asyncio.to_thread(self._lookup, key, access_code)

    async def close(self):
        # Take the gate off-loop too: a startup reservation may be in SQLite.
        def drain():
            with self._gate:
                self._closed = True
                threads = tuple(self._threads.values())
            for thread in threads:
                thread.join()
            # Observe exited thread leases without altering inline ownership.
            runs.active_paid_operation_count()

        waiter = asyncio.create_task(asyncio.to_thread(drain))
        cancelled = False
        while not waiter.done():
            try:
                await asyncio.shield(waiter)
            except asyncio.CancelledError:
                cancelled = True
        waiter.result()
        if cancelled:
            raise asyncio.CancelledError
