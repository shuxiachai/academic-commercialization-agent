"""Default-OFF main-API successor, separate from every frozen lab and canary."""

from contextvars import ContextVar
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import threading
import time

from fastapi import Request
from fastapi.responses import JSONResponse

from academic_agent import report_evidence_source_locator as locator
from academic_agent.report_evidence_catalog_followup import build_catalog
from academic_agent.report_evidence_snapshot import content_hash
from academic_agent.saved_source_loader import SavedSourceLoader, valid_run_id
from academic_agent.saved_source_usage import OperationContext
from api import saved_source_accounting as accounting
from api.maintenance import MaintenanceDeferred
from api.saved_source_controller import SavedSourceController, _validated_snapshot
from api.saved_source_production_assets import asset_response, page_response
from api.saved_source_production_policy import ControlStore, Settings, _plain
from api.saved_source_receipt_app import (
    MAX_CRITICAL_HEADER_BYTES, _CRITICAL, _DETAIL, _HEADERS, _body, _error, _question, _request_headers,
)
from api.saved_source_receipts import ReceiptError, canonical
from api.saved_source_usage_app import _wire_usage_reply

POST_PATH = "/api/runs/{run_id}/source-locator"
GET_PATH = "/api/source-locator/receipts"
PAGE_PATH = "/source-locator"
SELECTOR_IDENTITY = "production_source_locator_qwen35_plus_v1"
CONSENT_HEADER = b"x-source-locator-consent"
CONSENT_VALUE = b"question-catalog-v1"
_CURRENT = ContextVar("production_locator_operation", default=None)


@dataclass
class _BoundOperation:
    controller: object
    question: str
    claimed: object
    thread_id: int
    snapshot: object = None
    loaded: bool = False
    attempted: bool = False


def _load_key():
    # Deliberately not the pipeline resolver: no OPENAI key, BYOK, regional
    # base URL, model override or provider fallback can alter this wire.
    return os.environ.get("DASHSCOPE_API_KEY", "")


class _ProductionController(SavedSourceController):
    def __init__(self, runtime, loader):
        self.runtime, self.loader = runtime, loader
        super().__init__(self._load_bound, runtime.root, selector_identity=SELECTOR_IDENTITY,
                         accounted_selector=runtime, accounting_store=accounting.AccountingStore(runtime.root))

    def _load_bound(self, run_id):
        current = _CURRENT.get()
        if current is not None:
            if current.controller is not self or current.thread_id != threading.get_ident() or current.loaded:
                raise ReceiptError("execution_unavailable")
            current.loaded = True
        snapshot = _validated_snapshot(self.loader(run_id), run_id)
        if current is not None:
            current.snapshot = snapshot
        return snapshot

    def _begin(self, key, run_id, question, access_code, intent):
        with self._gate:
            if not self.runtime.execution_allowed:
                raise ReceiptError("selector_disabled")
            # Authenticate before even initializing the dedicated budget root.
            # super() repeats these checks and owns claim/thread linearization.
            owner, _ = self._authenticate(access_code)
            if not valid_run_id(run_id):
                raise ReceiptError("invalid_request")
            self._authorize_run(run_id, owner)
            self.runtime.control.prepare()
            return super()._begin(key, run_id, question, access_code, intent)

    def _operate(self, ticket, run_id, question, access_code, owner, intent, claimed):
        # Set inside the actual dedicated thread. Context inherited by the HTTP
        # waiter or a global last snapshot cannot bind a different operation.
        token = _CURRENT.set(_BoundOperation(self, question, claimed, threading.get_ident()))
        try:
            return super()._operate(ticket, run_id, question, access_code, owner, intent, claimed)
        finally:
            _CURRENT.reset(token)


class SourceLocatorRuntime:
    """Main owns this instance, its maintenance and its actual-thread drain."""

    def __init__(self, settings, output_root, *, key_loader=None, load_snapshot=None):
        self.settings = settings
        self.root = Path(output_root) / ".source-locator-v1"
        self.control = ControlStore(self.root, settings)
        self.key_loader = _load_key if key_loader is None else key_loader
        self._disabled = threading.Event()
        self.controller = _ProductionController(self, SavedSourceLoader(output_root) if load_snapshot is None else load_snapshot)

    @property
    def execution_allowed(self):
        return self.settings.execution_allowed and not self._disabled.is_set() and not self.controller._closed

    def disable_execution(self):
        # Existing-intent GET is independent of execution policy. A disabled
        # instance is not re-enabled; a later deployment chooses fresh policy.
        self._disabled.set()

    def stop_accepting(self):
        self.disable_execution()

    def select(self, request, /, *, operation, observation):
        current = _CURRENT.get()
        if (current is None or current.controller is not self.controller
                or current.thread_id != threading.get_ident() or current.attempted
                or current.snapshot is None or not self.execution_allowed
                or type(operation) is not OperationContext):
            raise ReceiptError("execution_unavailable")
        current.attempted = True
        snapshot = _validated_snapshot(current.snapshot, current.claimed.run_id)
        catalog = build_catalog(snapshot)
        expected = OperationContext(
            receipt_key_sha256=current.claimed.key_hash, owner_id=current.claimed.owner,
            intent_fingerprint=current.claimed.fingerprint, run_id=current.claimed.run_id,
            expires_at=current.claimed.expires,
            selector_identity_sha256=hashlib.sha256(SELECTOR_IDENTITY.encode()).hexdigest(),
            snapshot_hash=snapshot.snapshot_hash, catalog_hash=content_hash(catalog),
        )
        if (operation != expected or observation.operation != expected
                or type(request) is not dict or canonical(request) != canonical(locator._request(current.question, catalog))):
            raise ReceiptError("execution_unavailable")
        ledger_dir = self.control.reserve(expected)
        # No constructor, health, lookup or denied request may discover a key.
        # The durable budget/inventory precedes key access and native creation.
        from academic_agent.report_evidence_qwen_canary import ENDPOINT, MODEL, RESERVATION_USD
        from academic_agent.saved_source_accounted_qwen import AccountedQwenSelector
        if (MODEL != "qwen3.5-plus" or ENDPOINT != "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
                or str(RESERVATION_USD) != "0.011149312"):
            raise ReceiptError("execution_unavailable")
        native = AccountedQwenSelector(self.key_loader(), snapshot=snapshot, question=current.question, ledger_dir=ledger_dir)
        return native.select(request, operation=operation, observation=observation)

    def _maintenance(self, operation):
        with self.controller._gate:
            # Frozen prune methods do not know physical thread ownership.
            # Conservatively skip the entire stage until every owner exits.
            if any(thread.is_alive() for thread in self.controller._threads.values()):
                raise MaintenanceDeferred()
            try:
                try:
                    self.root.lstat()
                except FileNotFoundError:
                    return 0
                _plain(self.root, directory=True)
                return operation()
            except Exception:  # noqa: BLE001 -- maintenance logging must not expose private paths or stored content.
                raise ReceiptError("execution_unavailable") from None

    def prune_receipts(self):
        def prune():
            from api.saved_source_receipts import FILENAME
            path = self.root / FILENAME
            try:
                path.lstat()
            except FileNotFoundError:
                return 0
            _plain(path, directory=False)
            return self.controller._journal.prune()
        return self._maintenance(prune)

    def prune_accounting(self):
        def prune():
            path = self.root / accounting.FILENAME
            try:
                path.lstat()
            except FileNotFoundError:
                return 0
            _plain(self.root, directory=True)
            _plain(path, directory=False)
            with accounting._database(self.root) as db, db:
                db.execute("BEGIN IMMEDIATE")
                rows = db.execute("SELECT key_hash, value FROM accounting LIMIT ?", (accounting.MAX_RECORDS + 1,)).fetchall()
                if len(rows) > accounting.MAX_RECORDS:
                    raise ReceiptError("execution_unavailable")
                expired = []
                for key, raw in rows:
                    if type(raw) is not str or len(raw.encode("ascii")) > accounting.MAX_RECORD_BYTES:
                        raise ReceiptError("execution_unavailable")
                    value = json.loads(raw)
                    entry = accounting._checked(value)
                    if canonical(entry.model_dump()) != raw or entry.claim.key_hash != key:
                        raise ReceiptError("execution_unavailable")
                    if entry.claim.expires <= time.time():
                        expired.append((key,))
                db.executemany("DELETE FROM accounting WHERE key_hash=?", expired)
                return len(expired)
        return self._maintenance(prune)

    def prune_native(self):
        return self._maintenance(self.control.prune_native)

    def maintenance_stages(self):
        return (("source_locator_receipts", self.prune_receipts),
                ("source_locator_accounting", self.prune_accounting),
                ("source_locator_native", self.prune_native))

    def feature_status(self):
        # Configuration observations only: no key discovery or disk probes in
        # health. Separate maintenance checks carry observed storage failures.
        return {"execution": "enabled" if self.execution_allowed else "disabled",
                "budget": "configured" if self.settings.execution_allowed else "disabled"}

    async def close(self):
        self.disable_execution()
        await self.controller.close()


def build_runtime(*, settings=None, output_root, key_loader=None, load_snapshot=None):
    settings = Settings.from_env() if settings is None else settings
    if not settings.enabled:
        return None
    return SourceLocatorRuntime(settings, output_root, key_loader=key_loader, load_snapshot=load_snapshot)


def _production_headers(request):
    headers = [(name.lower(), value) for name, value in request.scope["headers"]
               if name.lower() in _CRITICAL | {CONSENT_HEADER}]
    if sum(len(name) + len(value) for name, value in headers) > MAX_CRITICAL_HEADER_BYTES:
        raise ReceiptError("headers_too_large")
    consent = [value for name, value in headers if name == CONSENT_HEADER]
    if len(consent) > 1:
        raise ReceiptError("invalid_request")
    if request.method == "POST" and consent != [CONSENT_VALUE]:
        raise ReceiptError("consent_required")
    return _request_headers(request)


def register_routes(app, runtime):
    if runtime is None:
        return

    async def handle(request, run_id=None):
        try:
            key, code = _production_headers(request)
            body = await _body(request)
            if run_id is None:
                reply = await runtime.controller.lookup(key, code)
            else:
                reply = await runtime.controller.execute(key, run_id, _question(body), code)
            return _wire_usage_reply(reply, key, run_id=run_id)
        except ReceiptError as exc:
            if exc.code == "consent_required":
                return JSONResponse({"detail": _DETAIL, "error_code": "consent_required"}, status_code=403, headers=_HEADERS)
            return _error(exc.code)
        except Exception:  # noqa: BLE001 -- private paths, rejected input and provider diagnostics never leave this boundary.
            return _error("execution_unavailable")

    @app.post(POST_PATH, response_model=None, include_in_schema=False)
    async def locate(run_id: str, request: Request):
        return await handle(request, run_id)

    @app.get(GET_PATH, response_model=None, include_in_schema=False)
    async def lookup(request: Request):
        return await handle(request)

    @app.get(PAGE_PATH, response_model=None, include_in_schema=False)
    async def page():
        return page_response(runtime.execution_allowed)

    @app.get("/source-locator-static/{name}", response_model=None, include_in_schema=False)
    async def asset(name: str):
        return asset_response(name)
