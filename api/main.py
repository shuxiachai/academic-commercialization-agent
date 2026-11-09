"""FastAPI application exposing the analysis pipeline over HTTP.

Serves both the JSON API and the web client (web/) from one process, and
launches each run as a `pipeline_worker` subprocess writing to its own run
directory — so the API, the browser and the CLI all observe the same run
through the same files rather than through shared memory.

    uv run uvicorn api.main:app --reload
    → http://localhost:8000       (web client)
    → http://localhost:8000/docs  (OpenAPI)
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import os
import threading
import time
from collections import deque
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import (
    FastAPI, File, Form, HTTPException, Query, Request, Response, UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

# Load .env before anything reads os.environ. Some dependency imports also
# happen to load it, but that is a side effect to observe, not a configuration
# contract — an API server should be explicit about when its settings exist.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from academic_agent.byok_model import BYOK_MODEL_PATTERN  # noqa: E402
from academic_agent.checkpoint_runtime import pipeline_revision  # noqa: E402
# A run-directory record, like run_terminal and auxiliary_usage, so the ops
# report can read it without importing the API.
from academic_agent import report_feedback as feedback  # noqa: E402
from academic_agent.report_display import report_for_display  # noqa: E402
from academic_agent.llm_config import (  # noqa: E402
    _detect_provider,
    resolve_provider_config,
    validate_llm_configuration,
)
from academic_agent.pdf_extractor import (  # noqa: E402
    PaperContribution,
    extract_paper_contribution,
)
from api import access, accounts, identity, papers, receipts, runs  # noqa: E402  — must follow load_dotenv
from api import account_backup, admin, alerts, mail, auxiliary_usage, key_check, link_probe, notices, plan_preview, retrieval_health, samples
from api.cleanup import CleanupAudit  # noqa: E402
from api.maintenance import MaintenanceDeferred  # noqa: E402
from api.upload_boundary import PaperUploadBoundary, release_upload_slot  # noqa: E402
from api.models import (  # noqa: E402
    AlertStatus,
    AuthConfig,
    AuthCredentials,
    AccountDeleted,
    AccountDeletion,
    AdminAccounts,
    AdminBackups,
    AdminLinkProbe,
    AdminConfirm,
    AdminDisable,
    AdminPasswordReset,
    AuthMe,
    EmailVerified,
    MailStatus,
    VerifyEmail,
    AuthSession,
    PasswordChange,
    NotifyPreference,
    PasswordForgot,
    PasswordReset,
    PasswordResetDone,
    SiteInfo,
    BYOK_PROVIDERS,
    CleanupSummary,
    DailyQuota,
    HealthStatus,
    KeyCheckRequest,
    KeyCheckResult,
    MaintenanceStatus,
    MaintenanceTiming,
    PaperExtraction,
    PaidReceipt,
    FeedbackRequest,
    FeedbackState,
    PlanPreview,
    PlanRequest,
    ReadinessStatus,
    ResumeRunRequest,
    RetrievalHealth,
    RunAccepted,
    RunList,
    RunProgress,
    RunRequest,
    RunStatus,
    SourceLocatorStatus,
)

_LOGGER = logging.getLogger(__name__)
# Fixed for the life of the process; /health is polled every second.
_PIPELINE_REVISION = pipeline_revision()
_REAP_INTERVAL_SECONDS = 30
_maintenance_task: asyncio.Task | None = None
_maintenance_checks: dict[str, str] = {}
_maintenance_lock = threading.Lock()
# Keep shielded extraction waiters alive after request cancellation. Their
# threads own persistence/raw cleanup; cancellation is not a thread kill.
_paper_jobs: set[asyncio.Task] = set()


@dataclass(frozen=True)
class _MaintenanceTimes:
    """Process-local clock pairs; monotonic anchors never cross the HTTP seam."""

    current_started_at: datetime | None = None
    current_started_mono: float | None = None
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_duration_seconds: float | None = None
    last_finished_mono: float | None = None
    cleanup: CleanupSummary | None = None
    deferred_at: datetime | None = None


_maintenance_timings: dict[str, _MaintenanceTimes] = {}


def _maintenance_clock() -> tuple[datetime, float]:
    """Keep elapsed facts independent of NTP/manual changes to UTC labels."""
    return datetime.now(UTC), time.monotonic()


def _maintenance_finished(name: str, result: Literal["ok", "failed"], cleanup: CleanupSummary | None = None) -> None:
    # Sync HTTP handlers read on other threads. Publish the result and its
    # matching clock pair together, never new 'ok' next to an old completion.
    # This lock covers only snapshots, not I/O or the stage's blocking work.
    with _maintenance_lock:
        wall, mono = _maintenance_clock()
        previous = _maintenance_timings[name]
        _maintenance_timings[name] = _MaintenanceTimes(
            last_started_at=previous.current_started_at,
            last_finished_at=wall,
            last_duration_seconds=max(0.0, mono - previous.current_started_mono),
            last_finished_mono=mono,
            cleanup=cleanup,
        )
        _maintenance_checks[name] = result


def _maintenance_status() -> MaintenanceStatus:
    """Expose task death even when it bypassed the per-stage fault boundary."""
    with _maintenance_lock:
        task = _maintenance_task
        checks = dict(_maintenance_checks)
        records = dict(_maintenance_timings)
        wall, mono = _maintenance_clock()
    if task is None:
        state = "not_started"
    elif task.done():
        state = "stopped" if task.cancelled() else "failed"
    else:
        state = "degraded" if "failed" in checks.values() else "running"
    timings = {}
    for name in checks:
        record = records.get(name, _MaintenanceTimes())
        timings[name] = MaintenanceTiming(
            current_started_at=record.current_started_at,
            current_elapsed_seconds=(None if record.current_started_mono is None
                                     else max(0.0, mono - record.current_started_mono)),
            last_started_at=record.last_started_at,
            last_finished_at=record.last_finished_at,
            last_duration_seconds=record.last_duration_seconds,
            last_finished_age_seconds=(None if record.last_finished_mono is None
                                       else max(0.0, mono - record.last_finished_mono)),
        )
    cleanup = {}
    for name in ("papers", "retention"):
        if name in checks:
            record = records.get(name, _MaintenanceTimes())
            cleanup[name] = record.cleanup or CleanupSummary(
                state="not_checked" if checks[name] == "not_checked" else "unavailable",
            )
    return MaintenanceStatus(state=state, checks=checks, observed_at=wall, timings=timings, cleanup=cleanup)


async def _maintenance_stage(name: str, operation: Callable[..., object], *, collect_cleanup: bool = False) -> None:
    """Offload blocking work without abandoning it when the owner is cancelled."""
    async def execute() -> None:
        # No global collector or shared mutable tally: even direct legacy
        # cleanup callers cannot overwrite an in-flight reaper observation.
        audit = CleanupAudit() if collect_cleanup else None
        # Starting another attempt does not refresh its last completed result.
        # Preserve that observation while the new attempt queues/runs/drains.
        with _maintenance_lock:
            wall, mono = _maintenance_clock()
            previous = _maintenance_timings.get(name, _MaintenanceTimes())
            _maintenance_timings[name] = replace(previous, current_started_at=wall, current_started_mono=mono)
        try:
            changed = (await asyncio.to_thread(operation, cleanup=audit) if audit is not None
                       else await asyncio.to_thread(operation))
        except MaintenanceDeferred:
            # A live owner prevented any scan. Clear only the current dispatch;
            # keep the old result, cleanup facts and completion clocks aging.
            with _maintenance_lock:
                wall, _ = _maintenance_clock()
                previous = _maintenance_timings[name]
                _maintenance_timings[name] = replace(
                    previous, current_started_at=None, current_started_mono=None, deferred_at=wall,
                )
        except Exception:  # noqa: BLE001 - supervise one stage and preserve its completed fault observation
            _maintenance_finished(name, "failed", audit.snapshot(interrupted=True) if audit is not None else None)
            _LOGGER.exception("Background maintenance stage failed: %s", name)
        else:
            # Keep legacy normal-return checks and readiness stable. The
            # dedicated summary makes partial/absent/disabled outcomes explicit
            # without evicting a host with paid work for one cleanup failure.
            _maintenance_finished(name, "ok", audit.snapshot() if audit is not None else None)
            if changed:
                _LOGGER.info("Background maintenance %s: %s", name, changed)

    # Process waits and filesystem cleanup cannot run on the ASGI loop. Merely
    # awaiting to_thread is insufficient: cancelling that await does not stop
    # its thread. Shutdown would then race an abandoned timeout stop claim.
    # Keep a strong task reference, shield it, and drain it before propagating
    # cancellation. One serial stage is in flight, never a fire-and-forget batch.
    task = asyncio.create_task(execute())
    try:
        await asyncio.shield(task)
    except asyncio.CancelledError:
        # A second shutdown cancellation must not punch through the drain.
        # Do not mark a still-running stage as successful or proceed to the
        # next cleanup. Python cannot forcibly interrupt a stuck filesystem
        # thread: draining is ownership, not a bounded shutdown-time guarantee.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
        task.result()
        raise


def _prune_receipts() -> int:
    return receipts.prune(runs.DEFAULT_OUTPUT_ROOT)


def _source_locator_stages():
    return () if _source_locator is None else _source_locator.maintenance_stages()


def _source_locator_status() -> SourceLocatorStatus | None:
    # Configuration is not a completed maintenance check. Keep its different
    # vocabulary outside checks/timings and outside the readiness decision.
    if _source_locator is None:
        return None
    with _maintenance_lock:
        deferred = {
            name: {"reason": "active_operation", "observed_at": record.deferred_at}
            for name, _ in _source_locator_stages()
            if (record := _maintenance_timings.get(name)) is not None and record.deferred_at is not None
        }
    return SourceLocatorStatus(**_source_locator.feature_status(), deferred_maintenance=deferred)


def _failed_stages() -> list[str]:
    with _maintenance_lock:
        return [f"maintenance:{name}" for name, result in _maintenance_checks.items() if result == "failed"]


def _send_alerts() -> None:
    alerts.review(_failed_stages(), runs.drain_operator_failures(), revision=_PIPELINE_REVISION)


async def _review_alerts() -> None:
    """Tell the operator what this cycle found, if they asked to be told.

    Deliberately not a stage. A stage that fails is itself reported, and an
    alert about the alert not being delivered has nowhere to go. Its own
    state is in /health under `alerts`. Whatever happens here, the loop that
    holds the timeout watchdog carries on.
    """
    if alerts.configured() != "ready":
        return
    try:
        await asyncio.to_thread(_send_alerts)
    except Exception:  # noqa: BLE001 - an alert must never cost the watchdog its loop
        _LOGGER.exception("Operator alert review failed")


async def _send_notices() -> None:
    """Tell accounts about runs of theirs that have ended, if they asked.

    Not a stage, for the alert review's reason: a message that fails to send
    is logged, mail's own state says so in /health, and the run page is
    unchanged, none of which makes the service degraded.
    """
    if not notices.enabled():
        return
    try:
        await asyncio.to_thread(notices.sweep)
    except Exception:  # noqa: BLE001 - a notice must never cost the watchdog its loop
        _LOGGER.exception("Run notice sweep failed")


def _maintenance_ended(task: asyncio.Task) -> None:
    """The loop cannot report its own end, so its end is reported for it.

    Cancellation is shutdown and is nobody's news. Anything else leaves the
    process serving requests with no timeout watchdog. Sent from a thread of
    its own: the loop that would have sent it is the thing that ended.
    """
    if task.cancelled() or alerts.configured() != "ready":
        return
    threading.Thread(
        target=alerts.review, args=([*_failed_stages(), alerts.LOOP_STOPPED],),
        kwargs={"revision": _PIPELINE_REVISION}, name="alert-maintenance-ended", daemon=True,
    ).start()


async def _reaper() -> None:
    """Kill runs that exceed the deadline.

    No request remains open for the lifetime of a run, so timeout enforcement
    belongs to this application-level loop rather than to a polling endpoint.
    """
    while True:
        await asyncio.sleep(_REAP_INTERVAL_SECONDS)
        # A failed directory listing used to kill this task, silently removing
        # the timeout watchdog too. Isolate each operation, not just the whole
        # loop: one unavailable cleanup root must not starve another stage.
        # Errors remain visible until that same stage actually succeeds.
        for name, operation in (
            ("timeouts", runs.reap_timeouts),
            ("papers", papers.prune_old),
            ("retention", runs.prune_expired_runs),
            ("receipts", _prune_receipts),
            ("auxiliary_usage", auxiliary_usage.prune),
            # Last of the fixed stages, and advisory like the cleanups: a
            # backup that fails shows as a failed check and a degraded state
            # in /health, and does not make the service unready. Restarting
            # the container cannot repair a full disk.
            ("account_backup", account_backup.run_schedule),
        ) + _source_locator_stages():
            await _maintenance_stage(name, operation, collect_cleanup=name in {"papers", "retention"})
        await _review_alerts()
        await _send_notices()


@contextlib.asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    global _maintenance_task, _maintenance_checks, _maintenance_timings
    with _maintenance_lock:
        _maintenance_checks = dict.fromkeys(
            ("timeouts", "papers", "retention", "receipts", "auxiliary_usage", "account_backup"), "not_checked")
        _maintenance_checks.update(dict.fromkeys((name for name, _ in _source_locator_stages()), "not_checked"))
        _maintenance_timings = {}
    alerts.reset()
    if alerts.configured() == "misconfigured":
        # Said once, and without the value: it may be most of a real address.
        _LOGGER.warning("The alert robot setting is not usable, so no alerts will be sent. Set exactly one of "
                        "ALERT_FEISHU_WEBHOOK and ALERT_WECOM_WEBHOOK, to the webhook address its robot shows.")
    task = asyncio.create_task(_reaper())
    task.add_done_callback(_maintenance_ended)
    _maintenance_task = task
    try:
        yield
    finally:
        if _source_locator is not None:
            _source_locator.stop_accepting()
        try:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        except Exception:  # noqa: BLE001 - report failed supervisor without skipping worker shutdown
            _LOGGER.exception("Background maintenance task exited unexpectedly")
        finally:
            # Awaiting an already-failed task raises. Worker cleanup must run
            # even in that case; otherwise shutdown leaves paid work orphaned.
            # The cancelled supervisor drains its current off-loop operation
            # first, so shutdown cannot compete with that operation's stop.
            try:
                try:
                    if _source_locator is not None:
                        await _source_locator.close()
                finally:
                    runs.shutdown_all()
            finally:
                _maintenance_task = None


app = FastAPI(
    title="Academic Commercialization Assessment API",
    description=(
        "Submit a research topic, poll for progress, retrieve the report and "
        "scorecard. The web client and CLI execute the same six-agent pipeline."
    ),
    version="2.0.0",
    lifespan=_lifespan,
)
app.add_middleware(PaperUploadBoundary)

# Configuration and object construction are I/O-free. The main lifespan owns
# the physical operation threads; mounting a subapp would not own its lifespan.
_source_locator = None
if os.environ.get("SOURCE_LOCATOR_ENABLED") in {"1", "true"}:
    # Default OFF also keeps frozen experimental factories out of sys.modules,
    # not merely out of the router. Their historical absence probes stay valid.
    from api import saved_source_production
    _source_locator = saved_source_production.build_runtime(output_root=runs.DEFAULT_OUTPUT_ROOT)
    saved_source_production.register_routes(app, _source_locator)
app.state.source_locator = _source_locator


# Response headers applied to everything this app serves.
#
# The web client makes a strict policy affordable: it has no inline <script>,
# no inline <style>, no on* attributes, and loads every asset from its own
# origin — so none of the usual 'unsafe-inline' escape hatches are needed, and
# adding one later would be a signal that something regressed. Report text is
# model output plus third-party titles and URLs reaching innerHTML, so this is
# the layer that limits what a missed escape could do.
#
# style-src stays strict deliberately: the client sets individual properties
# (el.style.height = ...), which CSSOM permits under CSP; only cssText and
# style attributes would need an exception, and neither is used.
_SECURITY_HEADERS = {
    "Content-Security-Policy": "; ".join((
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",          # data: covers the inline SVG favicon
        "connect-src 'self'",
        "form-action 'self'",
        "base-uri 'none'",
        "frame-ancestors 'none'",        # clickjacking, and supersedes X-Frame-Options
        "object-src 'none'",
    )),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    # Reports link out to third-party sources; keep those tabs from reaching back.
    "Cross-Origin-Opener-Policy": "same-origin",
}


# Per-client request budget, refilled continuously (token bucket).
#
# Distinct from the paid-operation concurrency and daily caps: this counts
# *requests*, and exists because the endpoints that cost nothing to serve are
# the ones an unauthenticated caller can reach. A run id
# is a capability URL, so anyone holding one can poll a run as fast as they
# like; the gate itself (/api/access/check) is likewise open by construction,
# since rejecting a wrong code is what it is for. Neither is expensive per
# call, and both are unbounded without this.
#
# Generous on purpose. The client polls progress every 1.2-4s during a run and
# capacity once a second, so a person with two tabs open is already near 100
# requests/minute through normal use; this is sized to stop scripted abuse
# without ever touching that.
_RATE_LIMIT_REQUESTS = int(os.getenv("API_RATE_LIMIT_PER_MINUTE", "300"))
_RATE_LIMIT_WINDOW = 60.0

_rate_buckets: dict[str, tuple[float, float]] = {}   # client -> (tokens, last refill)
_rate_lock = threading.Lock()


def _client_key(request: Request) -> str:
    """Who to charge for this request.

    A *validated* access code gets its own bucket so people behind one campus
    NAT do not throttle each other. Arbitrary header text must never become an
    identity: changing an invalid code would otherwise mint a fresh bucket.

    The address comes from request.client, after any trusted-proxy handling by
    the ASGI server. Reading X-Forwarded-For again here would bypass that trust
    decision and let a direct caller choose a new address on every request.
    """
    # A malformed code or token is anonymous here (identity.resolve never
    # raises): it still spends the IP bucket and reaches the endpoint's strict
    # rejection. This is not an authenticated identity or a grant.
    who = identity.resolve(request)
    if who.kind == "code":
        return f"code:{who.tag}"
    if who.kind == "user":
        return f"{who.tag}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


def _rate_limit_exceeded(key: str) -> bool:
    """Spend one token for `key`; True when the bucket is empty.

    A bucket refills continuously rather than resetting on a fixed boundary,
    so a caller cannot save up a burst by waiting for the top of a window.
    """
    if _RATE_LIMIT_REQUESTS <= 0:            # 0 disables the limit entirely
        return False
    now = time.monotonic()
    rate = _RATE_LIMIT_REQUESTS / _RATE_LIMIT_WINDOW
    with _rate_lock:
        tokens, last = _rate_buckets.get(key, (float(_RATE_LIMIT_REQUESTS), now))
        tokens = min(float(_RATE_LIMIT_REQUESTS), tokens + (now - last) * rate)
        if tokens < 1.0:
            _rate_buckets[key] = (tokens, now)
            return True
        _rate_buckets[key] = (tokens - 1.0, now)

        # Drop buckets that have refilled completely; they carry no state a
        # new one would not reproduce. Without this the dict is a slow leak
        # keyed by every address that ever called.
        if len(_rate_buckets) > 2048:
            full = _RATE_LIMIT_REQUESTS - 0.5
            for k, (t, seen) in list(_rate_buckets.items()):
                if k != key and t + (now - seen) * rate >= full:
                    del _rate_buckets[k]
    return False


@app.middleware("http")
async def _rate_limit(request: Request, call_next):
    """Bound request volume per client.

    The /health endpoints are exempt: platform health checks poll them on
    their own schedule and must never be throttled into reporting the service
    as down. Matched by prefix so /health/ready is covered — it is the one the
    container healthcheck actually polls, and a 429 there would restart a
    perfectly healthy container.

    So are the files a page is made of and the documents that load them
    (_is_page_asset). A page is some seventeen modules that import one
    another, each confirmed with the server before reuse, so one load is
    seventeen requests and a reload is seventeen more; a person reloading
    with a few tabs open, or several people behind one address, reached the
    budget through the page alone. A 429 on one module stops the whole
    module graph, and the visitor is left with a document that never ran
    its script: no gate, no badge, nothing to say why. The files are cheap,
    static and cacheable; a scripted abuser gains nothing from them, and
    the API they would abuse stays behind the limit.
    """
    path = request.url.path
    if not (path.startswith("/health") or _is_page_asset(path)) and _rate_limit_exceeded(_client_key(request)):
        return JSONResponse(
            {"detail": "Too many requests. Slow down and retry shortly."},
            status_code=429,
            headers={"Retry-After": "10", "X-Error-Code": "rate_limited"},
        )
    return await call_next(request)


def _is_page_asset(path: str) -> bool:
    """The files a page is made of, and the documents that load them."""
    return (path.startswith("/static/") or path in ("/", "/history", "/privacy", "/samples", "/admin", "/verify", "/reset")
            or path.startswith(("/run/", "/compare/", "/samples/")))


@app.middleware("http")
async def _revalidate_page_assets(request: Request, call_next):
    """Tell browsers to confirm a script or stylesheet before reusing it.

    The page is some seventeen modules that import one another, each cached
    under its own unversioned URL. They were sent with a validator and no
    caching instruction, which leaves the browser to guess how long a copy
    stays good: commonly a tenth of the time since the file last changed, so
    the longer since the last deploy, the longer the guess. After a deploy a
    returning visitor could therefore run a new module beside an old one it
    imports, and a call to something the old one does not have yet fails in
    the page.

    `no-cache` keeps the copy and asks first. An unchanged file costs one
    conditional request answered 304 with no body; a changed one is fetched.
    The documents get the same instruction as their scripts: a page kept
    longer than the modules it names is the same mismatch from the other
    side. The main page was `no-store` only where the saved-source locator
    rewrites it; served as a plain file, which is the default, it had no
    instruction at all. Set only where nothing chose a policy already, so
    that `no-store` stands.
    """
    response = await call_next(request)
    if request.method in ("GET", "HEAD") and _is_page_asset(request.url.path):
        response.headers.setdefault("Cache-Control", "no-cache")
    return response


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    """Attach the response headers above to every response.

    Deliberately not HSTS: that is the platform's to set. Railway terminates
    TLS ahead of this process and already redirects http→https, and an app
    that sends max-age on a host it does not control can outlive its own
    certificate story.
    """
    response = await call_next(request)
    for name, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


@app.middleware("http")
async def _access_gate(request: Request, call_next):
    """Reject ungated requests before they reach any endpoint.

    Runs ahead of routing, so a missing/wrong code never gets as far as
    starting a worker or spending a search-API call. Three exceptions:

    - /health — costs nothing; platform load balancers poll it without a header.
    - POST /api/runs and POST /api/papers — both authorize themselves with
      either the code or bring-your-own-key credentials in the body. That
      decision needs the parsed body, which a middleware does not cheaply
      have — for /api/papers the body is a multipart upload, less cheaply
      still.
    - /api/runs/{id}/... routes bypass this global list gate because reads
      use the run id as a capability. Their mutating handlers independently
      verify ownership before cancellation, deletion, or a paid child resume.
      Keeping that decision in the handler also lets resume parse fresh BYOK
      credentials without consuming and rebuilding the request body here.
      GET /api/runs itself stays gated because it lists deployment history.
    - GET /api/samples and /api/samples/{slug} — committed example reports
      from an allowlist (api/samples.py). They exist so a visitor without a
      code can see a finished report; nothing behind them spends money or
      reads deployment state.
    """
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)
    if path in ("/api/runs", "/api/papers") and request.method == "POST":
        return await call_next(request)
    if request.method == "GET" and (path == "/api/samples" or path.startswith("/api/samples/")):
        return await call_next(request)
    if request.method == "GET" and path == "/api/site":
        # What the privacy page states about this deployment; nothing private.
        return await call_next(request)
    if path.startswith("/api/runs/"):
        return await call_next(request)
    if path in _AUTH_OPEN_PATHS.get(request.method, ()):
        # Signing up and signing in are how an anonymous visitor stops being
        # one; the config read tells the page whether to offer them at all.
        return await call_next(request)
    if path == "/api/receipts" and request.method == "GET":
        # Receipt keys are header-only read capabilities. The handler still
        # requires the original code for code-owned records, including when
        # the global gate was subsequently disabled.
        return await call_next(request)
    if _source_locator is not None and path == "/api/source-locator/receipts" and request.method == "GET":
        # The locator independently requires a current code, even after the
        # legacy global gate is disabled. Preserve its bounded safe diagnostics.
        return await call_next(request)

    who = identity.resolve(request)
    if who.anonymous and identity.required():
        body = {"detail": _ANONYMOUS_DETAIL()}
        if accounts.enabled():
            # The refusal tells the page what the gate should offer, so the
            # boot stays one request whether the deployment uses codes or
            # accounts; the shipped-client smoke accounts for every request.
            body["accounts"] = _accounts_config()
        return JSONResponse(body, status_code=401)
    # Who answered, if anyone — GET /api/runs uses this to show each code
    # holder or account only the runs made under their own identity. None
    # means "don't filter": with neither codes nor accounts configured there
    # is nothing to scope by (the single-tenant behaviour from before either
    # existed), and an admin deliberately opts out of scoping to see every
    # identity's history at once.
    request.state.is_admin = who.is_admin
    request.state.owner = who.owner
    return await call_next(request)


_AUTH_OPEN_PATHS = {
    "GET": ("/api/auth/config",),
    # Opening a verification link is also how a visitor becomes someone: the
    # token in it is the credential, and the browser it is opened in may not
    # be the one that signed up.
    # A reset link is opened by someone who has no password, and the form
    # that asks for one is for the same person.
    "POST": ("/api/auth/register", "/api/auth/login", "/api/auth/verify",
             "/api/auth/password/forgot", "/api/auth/password/reset"),
}


def _ANONYMOUS_DETAIL() -> str:  # noqa: N802 - reads as the constant it replaces
    if accounts.enabled() and access.gate_enabled():
        return "Sign in, or provide a valid access code."
    if accounts.enabled():
        return "Sign in to use this deployment."
    return "Missing or invalid access code."


def _admission_code(exc: Exception) -> str:
    """The stable code for a refused admission; an account's own caps have their own."""
    if isinstance(exc, runs.AccountBusy):
        return "account_busy"
    if isinstance(exc, runs.ConcurrencyLimitReached):
        return "concurrency_limit"
    if isinstance(exc, runs.AccountDailyCapReached):
        return "account_daily_quota_exceeded"
    return "daily_quota_exceeded"


def _admission_refusal(exc: Exception) -> HTTPException:
    code = _admission_code(exc)
    tail = {
        "account_busy": " Wait for it to finish, or cancel it, then start this one.",
        "concurrency_limit": " Retry once another paid operation finishes.",
        "account_daily_quota_exceeded": " The account's allowance resets at 00:00 UTC.",
        "daily_quota_exceeded": " The daily paid-operation budget resets at 00:00 UTC.",
    }[code]
    return HTTPException(status_code=429, detail=f"{exc}.{tail}", headers={"X-Error-Code": code})


def _operator_funds_admins() -> bool:
    """Whether a signed-in administrator's paid operation may run on the deployment's keys.

    Three things must hold: the operator left it on (accounts.admin_funded),
    the deployment has a model key, and it has a search key. Without the
    last two the request would be admitted and the worker would fail on the
    operator's behalf, which is worse than asking for keys. Everyone who is
    not an administrator keeps paying with their own keys.
    """
    if not accounts.admin_funded():
        return False
    try:
        validate_llm_configuration()
    except RuntimeError:
        return False
    return bool(os.getenv("SERPER_API_KEY") or os.getenv("TAVILY_API_KEY"))


def _paid_owner(http_request: Request, *, byok: bool, detail: str) -> str | None:
    """Authorize a paid operation and name the owner tag it is recorded under.

    Three callers (runs, resumes, uploads) and the receipt claim used to make
    this decision separately from the access header alone. The rules, in one
    place:

    - An account pays with its own keys: without them the request is refused
      with `byok_required`, never billed to the deployment. The one exception
      is an administrator on a deployment that can fund them
      (_operator_funds_admins): their request without keys runs on the
      operator's keys, counted against the operator's daily cap, tagged to
      the account as any account run is. An account that has not yet opened
      its verification link is refused first, with `email_unverified`: it
      may sign in, save keys and preview, but a paid operation waits for the
      address to be proven.
    - A code holder is billed to the deployment and tagged to the code; a
      code holder who brings keys anyway is untagged, as before.
    - Anonymous requests: refused when accounts are enabled (sign in first),
      refused without keys when the gate is on, otherwise untagged.
    """
    who = identity.resolve(http_request)
    if who.kind == "user":
        if not who.user.verified:
            raise HTTPException(
                status_code=403,
                detail="Verify your email address first: open the link in the message sent to it, "
                       "or ask for a new one from the page.",
                headers={"X-Error-Code": "email_unverified"},
            )
        if not byok and not (who.is_admin and _operator_funds_admins()):
            raise HTTPException(
                status_code=401,
                detail="Accounts run on their own API keys. Add your LLM key, model and a "
                       "search key, then retry; this deployment does not pay for account runs.",
                headers={"X-Error-Code": "byok_required"},
            )
        return who.tag
    if who.kind == "code":
        return None if byok else who.tag
    if accounts.enabled():
        raise HTTPException(status_code=401, detail=_ANONYMOUS_DETAIL(),
                            headers={"X-Error-Code": "sign_in_required"})
    if not byok and access.gate_enabled():
        raise HTTPException(status_code=401, detail=detail)
    return None


def _authorize_run_mutation(run_id: str, http_request: Request) -> None:
    """Require proof of ownership before mutating or restarting a run.

    The access-gate middleware exempts /api/runs/{id}/... so a report link
    can be shared without an access code. That exemption is right for reads
    and insufficient for cancellation, deletion, or a paid recovery child,
    which is why each mutating handler calls this check explicitly.

    Raises 404 rather than 403 on a mismatch: a distinct "forbidden" would
    confirm to a caller probing ids that a given run exists. Capability URLs
    are credentials, but their entropy is not a reason to leak their validity.
    """
    if not identity.required():
        return                      # nothing configured to authorize against

    who = identity.resolve(http_request)
    if who.is_admin:
        return

    try:
        owner = runs.owner_of(run_id)
    except runs.OwnerMarkerUnreadable as exc:
        # Missing means an intentionally ownerless capability; unreadable means
        # authorization could not be established. Returning 503 keeps those
        # states distinct without reflecting the filesystem error or marker.
        _LOGGER.exception("Run ownership metadata could not be read for %s", run_id)
        raise HTTPException(
            status_code=503,
            detail="Run authorization is temporarily unavailable. Retry later.",
        ) from exc
    if owner is None:
        # A BYOK run carries no owner tag by design, and its submitter holds
        # no code to prove ownership with — the id is the only credential
        # that exists for it, so it stays the credential here too. Nothing
        # else in the deployment references these runs.
        return

    if who.tag != owner:
        raise HTTPException(status_code=404, detail=f"No run with id {run_id}")


@app.get("/api/access/check", include_in_schema=False)
def access_check(http_request: Request) -> dict:
    """No-op the frontend calls to validate a code before storing it.

    Reaching this handler at all means the middleware already accepted the
    header — there is nothing left to verify here. `plan_preview` and
    `daily_quota` tell the browser whether POST /api/plan and GET /api/quota
    are worth calling on this deployment. On a deployment with accounts the
    answer also says which account, if any, the request was, so the page
    learns everything about its identity from this one boot request.
    """
    who = identity.resolve(http_request)
    # Whose cap: an account's own, a code's operator-funded one. Either way the
    # page shows what is left only where there is a number to show.
    payload = {"ok": True, "plan_preview": plan_preview.enabled(),
               "daily_quota": bool(runs.daily_cap_for(who.tag if who.kind == "user" else None if who.kind == "none" else "code"))}
    if accounts.enabled():
        payload["accounts"] = _accounts_config()
        payload["account"] = ({"email": who.user.email, "admin": who.is_admin, "verified": who.user.verified,
                               "notify_done": who.user.notify_done}
                              if who.kind == "user" else None)
    return payload


def _accounts_config() -> dict:
    """What the sign-in screen and a fresh account need to know, in one dict."""
    return {"enabled": True, "signup_open": accounts.signup_open(),
            "signup": accounts.signup_mode(), "access_codes": access.gate_enabled(),
            "key_check": key_check.enabled(), "contact": _operator_contact(),
            "plan_preview": plan_preview.enabled(),
            # An account has a daily allowance of its own; the page shows it once signed in.
            "daily_quota": bool(runs.ACCOUNT_DAILY_CAP),
            # A forgotten password is reset by a link, when there is mail to send it with,
            # and an account may ask for a message when a run of its ends.
            "password_reset": mail.configured(), "notices": mail.configured(),
            # An administrator's runs on the deployment's keys: the page then
            # does not stop them for keys they do not need.
            "admin_funded": _operator_funds_admins()}


def _operator_contact() -> str | None:
    """Who runs this deployment, as the operator chose to say it; None when unset.

    Already public on the privacy page. The sign-up form shows it too, beside
    the invite code field, so it is one value read in one place.
    """
    return (os.getenv("OPERATOR_CONTACT") or "").strip()[:300] or None


@app.get("/api/site", response_model=SiteInfo, tags=["site"])
def site_info() -> SiteInfo:
    """The facts about this deployment that its privacy page states: how long
    assessments are kept and who to ask. Ungated; nothing here is private."""
    return SiteInfo(retention_days=runs.RUN_RETENTION_DAYS or None, contact=_operator_contact(),
                    accounts=accounts.enabled(), account_backup_days=account_backup.kept_days())


# ── Accounts ─────────────────────────────────────────────────────────────────
# Email-and-password identities (api/accounts.py). Keys are never stored:
# an account scopes history and authorizes requests; its runs still carry the
# account's own LLM and search keys, request by request, like any BYOK run.

def _client_address(http_request: Request) -> str | None:
    """The caller's address as the ASGI server reports it after its own
    proxy-trust decision (FORWARDED_ALLOW_IPS); never a header read here."""
    return http_request.client.host if http_request.client else None


def _account_refusal(exc: accounts.AccountError) -> HTTPException:
    status = {"invalid_credentials": 401, "locked": 429, "signup_throttled": 429, "disabled": 403,
              "invite_required": 403, "signup_closed": 403, "email_taken": 409, "accounts_disabled": 404,
              "verification_invalid": 400, "verification_expired": 410, "verification_cooldown": 429,
              "already_verified": 409, "reset_invalid": 400, "reset_expired": 410}.get(exc.code, 422)
    headers = {"X-Error-Code": exc.code}
    if exc.code == "locked":
        headers["Retry-After"] = str(accounts.LOCKOUT_SECONDS)
    if exc.code == "signup_throttled":
        headers["Retry-After"] = "3600"
    if exc.code == "verification_cooldown":
        headers["Retry-After"] = str(accounts.VERIFY_RESEND_SECONDS)
    return HTTPException(status_code=status, detail=exc.message, headers=headers)


def _send_verification(user: accounts.User, *, cooldown: bool) -> None:
    """Issue a fresh link for the account and send it. Raises AccountError or MailError.

    The link is built on PUBLIC_URL, never on the request's Host header: what
    a request says about itself must not be able to choose where the link in
    someone's inbox points.
    """
    token = accounts.issue_verification(user, cooldown=cooldown)
    link = f"{mail.public_url()}/verify?token={token}"
    subject, text, html_body = mail.verification_message(link, hours=accounts.VERIFY_SECONDS // 3600)
    mail.send(user.email, subject, text, html_body)


def _send_reset(user: accounts.User, token: str) -> None:
    """Send the account the link that lets it choose a new password. Raises MailError.

    On PUBLIC_URL, like the verification link, and for the same reason."""
    link = f"{mail.public_url()}/reset?token={token}"
    subject, text, html_body = mail.reset_message(link, minutes=accounts.RESET_SECONDS // 60)
    mail.send(user.email, subject, text, html_body)


@app.get("/api/auth/config", response_model=AuthConfig, tags=["accounts"])
def auth_config() -> AuthConfig:
    """What the sign-in screen should offer. Ungated: it is how a visitor
    learns whether this deployment has accounts, codes, or neither."""
    return AuthConfig(enabled=accounts.enabled(), signup_open=accounts.enabled() and accounts.signup_open(),
                      signup=accounts.signup_mode() if accounts.enabled() else "closed",
                      access_codes=access.gate_enabled(),
                      key_check=accounts.enabled() and key_check.enabled(),
                      contact=_operator_contact() if accounts.enabled() else None,
                      plan_preview=accounts.enabled() and plan_preview.enabled(),
                      daily_quota=accounts.enabled() and bool(runs.ACCOUNT_DAILY_CAP),
                      password_reset=accounts.enabled() and mail.configured(),
                      notices=accounts.enabled() and mail.configured(),
                      admin_funded=accounts.enabled() and _operator_funds_admins())


@app.post("/api/auth/register", response_model=AuthSession, status_code=201, tags=["accounts"],
          responses={403: {"description": "Sign-up is closed"}, 409: {"description": "Email already registered"},
                     422: {"description": "Invalid email or weak password"}})
def auth_register(request: AuthCredentials, http_request: Request, response: Response) -> AuthSession:
    """Create an account and sign it in. Sends the session token once."""
    if not accounts.enabled():
        raise HTTPException(status_code=404, detail="Accounts are not enabled on this deployment.")
    try:
        created = accounts.register(request.email, request.password, invite=request.invite,
                                    client=_client_address(http_request))
        token, user = accounts.login(request.email, request.password, client=_client_address(http_request))
    except accounts.AccountError as exc:
        raise _account_refusal(exc) from None
    if not created.verified:
        # The account exists whether or not the message leaves: a mail outage
        # is not a reason to refuse a sign-up. The page offers to send again,
        # and a run is refused until the link has been opened.
        try:
            _send_verification(created, cooldown=False)
        except (accounts.AccountError, mail.MailError) as exc:
            _LOGGER.warning("Verification email for account %d not sent: %s", created.id, exc)
    response.headers["Cache-Control"] = "no-store"
    return AuthSession(token=token, email=user.email, admin=user.admin, verified=user.verified)


@app.post("/api/auth/login", response_model=AuthSession, tags=["accounts"],
          responses={401: {"description": "Email or password not accepted"},
                     429: {"description": "Too many failed attempts for this email"}})
def auth_login(request: AuthCredentials, http_request: Request, response: Response) -> AuthSession:
    if not accounts.enabled():
        raise HTTPException(status_code=404, detail="Accounts are not enabled on this deployment.")
    try:
        token, user = accounts.login(request.email, request.password, client=_client_address(http_request))
    except accounts.AccountError as exc:
        raise _account_refusal(exc) from None
    response.headers["Cache-Control"] = "no-store"
    return AuthSession(token=token, email=user.email, admin=user.admin, verified=user.verified)


@app.post("/api/auth/verify", response_model=EmailVerified, tags=["accounts"],
          responses={400: {"description": "The link is not one this deployment issued"},
                     410: {"description": "The link has expired; sign in and ask for another"}})
def auth_verify(request: VerifyEmail, response: Response) -> EmailVerified:
    """Prove an address by presenting the token from the link sent to it.

    A POST from the page, not the GET of the link itself: mail clients and
    link scanners open links on the reader's behalf, and a scanner's visit
    must not be what verifies an address. Ungated, since the browser the link
    is opened in need not hold the session that signed up.
    """
    if not accounts.enabled():
        raise HTTPException(status_code=404, detail="Accounts are not enabled on this deployment.")
    try:
        user = accounts.verify_email(request.token)
    except accounts.AccountError as exc:
        raise _account_refusal(exc) from None
    response.headers["Cache-Control"] = "no-store"
    return EmailVerified(email=user.email)


@app.post("/api/auth/verify/resend", status_code=202, tags=["accounts"],
          responses={409: {"description": "The address is already verified"},
                     429: {"description": "A message was sent moments ago"},
                     503: {"description": "The message could not be sent"}})
def auth_verify_resend(http_request: Request) -> Response:
    """Send the signed-in account a fresh verification link.

    The earlier link stops working. At most one message a minute per account,
    and the deployment's own daily allowance of email above that.
    """
    user = _signed_in_account(http_request)
    if not mail.configured():
        raise HTTPException(status_code=503, detail="This deployment cannot send email at the moment.",
                            headers={"X-Error-Code": "mail_unavailable"})
    try:
        _send_verification(user, cooldown=True)
    except accounts.AccountError as exc:
        raise _account_refusal(exc) from None
    except mail.MailError as exc:
        _LOGGER.warning("Verification email for account %d not sent: %s", user.id, exc)
        raise HTTPException(status_code=503, detail="The verification email could not be sent. Try again in a while.",
                            headers={"X-Error-Code": "mail_unavailable"}) from None
    return Response(status_code=202, headers={"Cache-Control": "no-store"})


@app.post("/api/auth/password/forgot", status_code=202, tags=["accounts"],
          responses={503: {"description": "This deployment cannot send email"}})
def auth_password_forgot(request: PasswordForgot) -> Response:
    """Send a password-reset link to an address, if an account has it.

    202 whether or not one does, and whether or not a message left: the form
    is open to anyone, so its answer must not say which addresses have
    accounts. What the form can do is put one message a minute into the
    inbox of the address itself, within the deployment's daily allowance of
    mail; nothing arrives anywhere else. 503 only when the deployment cannot
    send mail at all, which is true of every address alike. A delivery
    failure is logged by account id, never by address.
    """
    if not accounts.enabled():
        raise HTTPException(status_code=404, detail="Accounts are not enabled on this deployment.")
    if not mail.configured():
        raise HTTPException(status_code=503, detail="This deployment cannot send email at the moment.",
                            headers={"X-Error-Code": "mail_unavailable"})
    issued = accounts.issue_password_reset(request.email)
    if issued is not None:
        user, token = issued
        try:
            _send_reset(user, token)
        except mail.MailError as exc:
            _LOGGER.warning("Password reset email for account %d not sent: %s", user.id, exc)
    return Response(status_code=202, headers={"Cache-Control": "no-store"})


@app.post("/api/auth/password/reset", response_model=PasswordResetDone, tags=["accounts"],
          responses={400: {"description": "The link is not one this deployment issued"},
                     403: {"description": "The account is disabled"},
                     410: {"description": "The link has expired; ask for another"},
                     422: {"description": "The new password does not meet the policy"}})
def auth_password_reset(request: PasswordReset, response: Response) -> PasswordResetDone:
    """Set a new password with the token from a reset link.

    Ungated: the person holding the link has no session, and once this
    returns neither does anyone else, since every session of the account
    ends. A POST from the page rather than the GET of the link, as with
    verification, so a scanner opening the link spends nothing. The answer
    names the address so the page can offer to sign it in.
    """
    if not accounts.enabled():
        raise HTTPException(status_code=404, detail="Accounts are not enabled on this deployment.")
    try:
        user = accounts.redeem_reset_link(request.token, request.new_password)
    except accounts.AccountError as exc:
        raise _account_refusal(exc) from None
    response.headers["Cache-Control"] = "no-store"
    return PasswordResetDone(email=user.email)


@app.post("/api/auth/logout", status_code=204, tags=["accounts"])
def auth_logout(http_request: Request) -> Response:
    """End the presented session. Idempotent: an unknown token is already out."""
    accounts.logout(identity._bearer(http_request))
    return Response(status_code=204)


@app.get("/api/auth/me", response_model=AuthMe, tags=["accounts"],
         responses={404: {"description": "The request is not an account session"}})
def auth_me(http_request: Request) -> AuthMe:
    """The signed-in account, for the page to show. The middleware already
    admitted the request; this only says which kind of identity it was."""
    who = identity.resolve(http_request)
    if who.kind != "user":
        raise HTTPException(status_code=404, detail="Not signed in with an account.")
    return AuthMe(email=who.user.email, admin=who.is_admin, verified=who.user.verified,
                  notify_done=who.user.notify_done)


def _signed_in_account(http_request: Request) -> accounts.User:
    who = identity.resolve(http_request)
    if who.kind != "user":
        raise HTTPException(status_code=404, detail="Not signed in with an account.")
    return who.user


@app.post("/api/auth/notify", status_code=204, tags=["accounts"],
          responses={503: {"description": "This deployment cannot send email"}})
def auth_notify(request: NotifyPreference, http_request: Request) -> Response:
    """Ask for, or stop, an email when one of the account's runs ends (api/notices.py).

    Off until asked. Refused where there is no mail to send it with, so the
    switch is never on without meaning anything.
    """
    user = _signed_in_account(http_request)
    if not mail.configured():
        raise HTTPException(status_code=503, detail="This deployment cannot send email at the moment.",
                            headers={"X-Error-Code": "mail_unavailable"})
    accounts.set_notify_done(user, request.enabled)
    return Response(status_code=204)


@app.post("/api/auth/password", status_code=204, tags=["accounts"],
          responses={401: {"description": "The current password was not accepted"},
                     422: {"description": "The new password does not meet the policy"},
                     429: {"description": "Too many failed attempts"}})
def auth_change_password(request: PasswordChange, http_request: Request) -> Response:
    """Change the password of the signed-in account.

    Needs the current password as well as the session, and ends every other
    session of the account; this one stays signed in.
    """
    user = _signed_in_account(http_request)
    try:
        accounts.change_password(user, request.current_password, request.new_password,
                                 keep_token=identity._bearer(http_request),
                                 client=_client_address(http_request))
    except accounts.AccountError as exc:
        raise _account_refusal(exc) from None
    return Response(status_code=204)


@app.post("/api/auth/delete-account", response_model=AccountDeleted, tags=["accounts"],
          responses={401: {"description": "The password was not accepted"},
                     409: {"description": "An assessment of this account is still running"},
                     429: {"description": "Too many failed attempts"}})
def auth_delete_account(request: AccountDeletion, http_request: Request) -> AccountDeleted:
    """Delete the signed-in account and everything recorded under it.

    Assessments, uploaded papers and paid-request receipts go first, the
    account last, so a failure part-way leaves an account that can sign in
    and try again. Nothing is recoverable afterwards. A run that is still
    going must be cancelled first: its worker is writing into the directory
    this would remove.
    """
    user = _signed_in_account(http_request)
    try:
        accounts.confirm_password(user, request.password, client=_client_address(http_request))
    except accounts.AccountError as exc:
        raise _account_refusal(exc) from None
    try:
        if runs.active_run_ids(user.owner):
            raise HTTPException(
                status_code=409,
                detail="An assessment is still running. Cancel it, then delete the account.",
                headers={"X-Error-Code": "active_runs"},
            )
        deleted_runs = 0
        for directory in runs.run_directories(owner=user.owner):
            runs.delete_run(directory.name)
            deleted_runs += 1
    except runs.RunStillActive as exc:
        raise HTTPException(status_code=409, detail=f"{exc}.",
                            headers={"X-Error-Code": "active_runs"}) from exc
    except (runs.OwnerMarkerUnreadable, OSError) as exc:
        _LOGGER.exception("Account deletion could not remove a run for %s", user.owner)
        raise HTTPException(status_code=503,
                            detail="Some assessments could not be deleted. Retry later.") from exc
    uploads = papers.discard_owned(user.owner)
    try:
        receipts.forget_owner(runs.DEFAULT_OUTPUT_ROOT, user.owner)
    except receipts.ReceiptError:
        # Receipts expire on their own within a day; they must not keep an
        # account alive that has already lost everything else.
        _LOGGER.exception("Receipts of %s could not be removed with the account", user.owner)
    try:
        accounts.delete_account(user, request.password, client=_client_address(http_request))
    except accounts.AccountError as exc:
        raise _account_refusal(exc) from None
    return AccountDeleted(runs=deleted_runs, uploads=uploads)


# ── Admin console ───────────────────────────────────────────────────────────

def _admin_account(http_request: Request) -> accounts.User:
    """The signed-in admin account, or 404.

    404 and not 403: a non-admin probing for the console learns nothing from
    the answer, the same as a wrong run id. An admin access code is not an
    admin account (see api/admin.py): it cannot be asked for a password.
    """
    who = identity.resolve(http_request)
    if who.kind != "user" or not who.is_admin:
        raise HTTPException(status_code=404, detail="Not found.")
    return who.user


def _admin_refusal(exc: Exception) -> HTTPException:
    if isinstance(exc, accounts.AccountError):
        return _account_refusal(exc)
    assert isinstance(exc, admin.AdminRefusal)
    status = {"unknown_account": 404, "own_account": 409}.get(exc.code, 422)
    return HTTPException(status_code=status, detail=exc.message, headers={"X-Error-Code": exc.code})


@app.get("/api/admin/accounts", response_model=AdminAccounts, tags=["admin"],
         responses={404: {"description": "Not an admin account"}})
def admin_accounts(http_request: Request) -> AdminAccounts:
    """Every account, newest first: for the operator's console only."""
    _admin_account(http_request)
    return AdminAccounts(accounts=[account.__dict__ for account in admin.list_accounts()])


@app.post("/api/admin/accounts/{user_id}/password-reset", response_model=AdminPasswordReset, tags=["admin"],
          responses={401: {"description": "The admin's password was not accepted"},
                     404: {"description": "Not an admin account, or no such account"},
                     409: {"description": "The admin's own account"},
                     429: {"description": "Too many failed attempts"}})
def admin_password_reset(user_id: int, request: AdminConfirm, http_request: Request) -> AdminPasswordReset:
    """Give an account a new random password and end its sessions.

    The admin's own password is confirmed first. The new password is in the
    answer once; the server keeps its hash. Send it to the account's own
    address: registration verifies none, so the admin is the check that the
    person asking owns the account.
    """
    acting = _admin_account(http_request)
    try:
        email, password, ended = admin.reset_password(user_id, acting, request.password,
                                                      client=_client_address(http_request))
    except (accounts.AccountError, admin.AdminRefusal) as exc:
        raise _admin_refusal(exc) from None
    return AdminPasswordReset(email=email, temporary_password=password, sessions_ended=ended)


@app.post("/api/admin/accounts/{user_id}/disabled", status_code=204, tags=["admin"],
          responses={401: {"description": "The admin's password was not accepted"},
                     404: {"description": "Not an admin account, or no such account"},
                     409: {"description": "The admin's own account"},
                     429: {"description": "Too many failed attempts"}})
def admin_set_disabled(user_id: int, request: AdminDisable, http_request: Request) -> Response:
    """Stop an account signing in, or let it again. Disabling ends its sessions."""
    acting = _admin_account(http_request)
    try:
        admin.set_disabled(user_id, acting, request.password, request.disabled,
                           client=_client_address(http_request))
    except (accounts.AccountError, admin.AdminRefusal) as exc:
        raise _admin_refusal(exc) from None
    return Response(status_code=204)


@app.get("/api/admin/backups", response_model=AdminBackups, tags=["admin"],
         responses={404: {"description": "Not an admin account"}})
def admin_backups(http_request: Request) -> AdminBackups:
    """The scheduled backups of the account database, each verified."""
    _admin_account(http_request)
    hours = account_backup.schedule_hours()
    scheduled = account_backup.kept_days() is not None
    return AdminBackups(scheduled=scheduled, every_hours=hours if scheduled else None,
                        keep=account_backup.schedule_keep() if scheduled else None,
                        backups=[row.__dict__ for row in admin.list_backups()])


@app.post("/api/admin/link-probe", response_model=AdminLinkProbe, tags=["admin"],
          responses={404: {"description": "Not an admin account"},
                     409: {"description": "A probe is already running"},
                     503: {"description": "No provider endpoint is configured"}})
def admin_link_probe(http_request: Request) -> AdminLinkProbe:
    """Measure, from this host, the path to the provider's endpoint.

    A 1 KB and a 100 KB chat request with no key, on new connections, to
    the configured endpoint and (for Bailian) its sibling across the
    border; the servers read the body and answer 401, so nothing is
    billed and the time to the answer is the path's. The targets are
    fixed: nothing in the request chooses where this server posts. Takes
    up to two minutes when a path is dead. See api/link_probe.py.
    """
    _admin_account(http_request)
    try:
        return AdminLinkProbe(**link_probe.run())
    except link_probe.NoEndpoint as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None
    except link_probe.Busy as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


# A key check has this server put a question to a provider on an account's
# behalf. That is worth doing a few times while someone corrects a typo and
# not worth offering as a way to try keys in bulk, so it is bounded per
# account, far below the general request limit.
_KEY_CHECK_LIMIT = 10
_KEY_CHECK_WINDOW = 600.0
_key_check_times: dict[str, deque[float]] = {}
_key_check_lock = threading.Lock()


def _key_check_exceeded(owner: str) -> bool:
    """Record one check for `owner`; True when the window is already full."""
    now = time.monotonic()
    with _key_check_lock:
        times = _key_check_times.setdefault(owner, deque())
        while times and now - times[0] >= _KEY_CHECK_WINDOW:
            times.popleft()
        if len(times) >= _KEY_CHECK_LIMIT:
            return True
        times.append(now)
        if len(_key_check_times) > 2048:
            for key in [k for k, seen in _key_check_times.items()
                        if k != owner and (not seen or now - seen[-1] >= _KEY_CHECK_WINDOW)]:
                del _key_check_times[key]
    return False


_KEY_CHECK_BODY_BYTES = 8_000


async def _key_check_body(http_request: Request) -> KeyCheckRequest:
    """Read and validate the body here rather than in the handler's signature.

    The framework's own refusal of a malformed body quotes the body back,
    and this body is nothing but keys. A refusal from here names the field
    and the rule, never the value. The size is bounded for the same reason
    the keys are: nothing that fits the model is larger than this.
    """
    raw = bytearray()
    async for chunk in http_request.stream():
        raw.extend(chunk)
        if len(raw) > _KEY_CHECK_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Key check body is too large.")
    try:
        return KeyCheckRequest.model_validate(json.loads(raw))
    except ValidationError as exc:
        problems = exc.errors(include_input=False, include_context=False, include_url=False)
        raise HTTPException(status_code=422, detail=[
            {"loc": ["body", *problem["loc"]], "msg": problem["msg"], "type": problem["type"]}
            for problem in problems]) from None
    except ValueError:
        raise HTTPException(status_code=422, detail="Body must be a JSON object of keys.") from None


@app.post("/api/keys/check", response_model=KeyCheckResult, tags=["accounts"],
          responses={404: {"description": "Not signed in with an account"},
                     413: {"description": "Body larger than any key set"},
                     422: {"description": "Incomplete or malformed key set; the reply quotes no value"},
                     429: {"description": "Too many key checks for this account"}},
          openapi_extra={"requestBody": {"required": True, "content": {
              "application/json": {"schema": KeyCheckRequest.model_json_schema()}}}})
async def check_keys(http_request: Request) -> KeyCheckResult:
    """Ask the providers whether they accept the keys an account is saving.

    For signed-in accounts only: they are the visitors who must bring keys,
    and an account is an identity this can be bounded by. An access-code
    holder or an anonymous visitor using their own keys is not offered it.

    One unbilled read per service, to the provider's own endpoint; see
    api/key_check.py. The keys are used for those two requests and are not
    stored, logged or echoed. A refusal here is advice to the person typing:
    nothing on the server depends on it, and a run with the same keys is
    admitted or refused exactly as before.
    """
    user = _signed_in_account(http_request)
    request = await _key_check_body(http_request)
    if not key_check.enabled():
        return KeyCheckResult(checked=False, llm="unverified", model="unknown", search="unverified")
    if _key_check_exceeded(user.owner):
        raise HTTPException(
            status_code=429,
            detail="Too many key checks. The keys can still be saved; wait a few minutes to check again.",
            headers={"Retry-After": "60", "X-Error-Code": "rate_limited"},
        )
    result = await key_check.check(
        provider=request.llm_provider, llm_api_key=request.llm_api_key, model=request.llm_model,
        search=request.search, search_api_key=request.search_api_key,
    )
    return KeyCheckResult(checked=True, llm=result.llm, model=result.model, search=result.search)


@app.get("/api/quota", response_model=DailyQuota | None, tags=["runs"])
def daily_quota(http_request: Request) -> DailyQuota | None:
    """Paid operations left today for this code or account; null when uncapped.

    Counted per validated code (the admin code too) against the operator's
    budget, and per account against the account's own allowance, exactly as
    admission counts them. A BYOK visitor without an account has neither.
    """
    who = identity.resolve(http_request)
    try:
        quota = runs.daily_quota(who.tag if who.kind in ("code", "user") else None)
    except runs.PaidLedgerUnavailable as exc:
        _LOGGER.exception("Paid-operation ledger unreadable for the quota view")
        raise HTTPException(status_code=503, detail="Daily quota is temporarily unavailable.") from exc
    return DailyQuota(**quota) if quota is not None else None


@app.post(
    "/api/plan",
    response_model=PlanPreview,
    tags=["runs"],
    responses={
        401: {"description": "An account must send its own keys"},
        404: {"description": "Plan previews are turned off on this deployment"},
        429: {"description": "Daily preview limit reached for this access code or account"},
    },
)
def preview_plan(request: PlanRequest, http_request: Request) -> PlanPreview:
    """How the planner reads a topic, before a run is started on it.

    One small model call. Whoever sends a complete key set pays for it with
    that set's model key; an account must, because an account is never billed
    to the deployment. Otherwise it runs on the deployment's key, behind the
    access code. It does not take a daily run; it has its own daily cap, per
    code or per account. Pass the confirmed or edited result to
    POST /api/runs as `search_plan`.
    """
    if not plan_preview.enabled():
        raise HTTPException(status_code=404, detail="Plan previews are turned off.")
    credentials = None
    if request.byok:
        credentials = {"provider": request.llm_provider, "api_key": request.llm_api_key,
                       "model": request.llm_model}
    else:
        who = identity.resolve(http_request)
        if who.kind == "user" and not (who.is_admin and _operator_funds_admins()):
            raise HTTPException(
                status_code=401,
                detail="Add your API keys to preview the search: accounts run on their own keys.",
                headers={"X-Error-Code": "byok_required"},
            )
    try:
        plan_preview.admit(http_request.state.owner)
    except plan_preview.PreviewLimitReached as exc:
        raise HTTPException(
            status_code=429,
            detail=f"{exc}. Start the run without a preview, or try again after 00:00 UTC.",
            headers={"X-Error-Code": "plan_preview_limit"},
        ) from exc
    return PlanPreview(**plan_preview.preview(request.topic, credentials))


_WEB_ROOT = Path(__file__).resolve().parents[1] / "web"

# Mounted before the API routes are declared below only in source order; the
# router matches /api/* first regardless, because StaticFiles is mounted at a
# sub-path rather than at "/". The SPA entry point is served explicitly.
if _WEB_ROOT.is_dir():
    app.mount("/static", StaticFiles(directory=_WEB_ROOT / "static"), name="static")

    @app.get("/", include_in_schema=False)
    @app.get("/history", include_in_schema=False)
    @app.get("/run/{run_id}", include_in_schema=False)
    @app.get("/compare/{run_id}/{other_run_id}", include_in_schema=False)
    @app.get("/verify", include_in_schema=False)
    @app.get("/reset", include_in_schema=False)
    def _spa(run_id: str = "", other_run_id: str = "") -> Response:
        """Serve the single page for every client-side route.

        Routing happens in the browser, so a deep link must return the same
        document rather than a 404 — the client reads the path and renders the
        matching view.
        """
        if _source_locator is None:
            return FileResponse(_WEB_ROOT / "index.html", media_type="text/html")
        from academic_agent.saved_source_loader import valid_run_id
        marker = "<!-- SOURCE_LOCATOR_LINK -->"
        page = (_WEB_ROOT / "index.html").read_text(encoding="utf-8")
        if page.count(marker) != 1:
            raise HTTPException(status_code=503, detail="Page navigation is unavailable.")
        fragment = "#" + run_id if valid_run_id(run_id) else ""
        link = '<a id="source-locator-link" href="/source-locator' + fragment + '">Saved-source locator</a>'
        return Response(page.replace(marker, link, 1), media_type="text/html", headers={"Cache-Control": "no-store"})

    @app.get("/samples", include_in_schema=False)
    @app.get("/samples/{slug}", include_in_schema=False)
    def _samples_page(slug: str = "") -> FileResponse:
        """Serve the sample-report reader for the list and every deep link.

        A separate document rather than a route inside the main page: the main
        page asks for a sign-in before any view renders (or, at "/" on a
        deployment with accounts, shows its landing page, which links here),
        and the point of this one is to be readable by someone who has no
        account and no code.
        """
        return FileResponse(_WEB_ROOT / "samples.html", media_type="text/html")

    @app.get("/privacy", include_in_schema=False)
    def _privacy_page() -> FileResponse:
        """Serve the privacy and terms page.

        Its own document for the same reason as the sample reader: it has to
        be readable before signing in, which is when someone decides whether
        to hand this deployment a paper and an email address.
        """
        return FileResponse(_WEB_ROOT / "privacy.html", media_type="text/html")

    @app.get("/admin", include_in_schema=False)
    def _admin_page() -> FileResponse:
        """Serve the operator's console.

        The document is public and says nothing; everything on it comes from
        /api/admin/..., which answers only an admin account. Serving it to
        everyone keeps the page a plain file, like the others.
        """
        return FileResponse(_WEB_ROOT / "admin.html", media_type="text/html")


@app.get("/api/samples", tags=["samples"])
def list_sample_reports() -> list[dict[str, str]]:
    """Committed example reports readable without credentials.

    Historical outputs from an earlier pipeline version, listed with the
    commit that added them; not current model accuracy or market data.
    """
    return samples.list_samples()


@app.get("/api/samples/{slug}", tags=["samples"], response_class=PlainTextResponse)
def read_sample_report(
    slug: str,
    view: Literal["saved", "display"] = Query(
        default="display",
        description="'display' (the default, what the sample reader fetches) is the report as the "
                    "page shows it: the code-owned applicability paragraph as sentences and a "
                    "cleaned reference list; 'saved' is the committed file, every byte as committed",
    ),
) -> PlainTextResponse:
    """One example report as Markdown. Unknown or missing samples are 404."""
    try:
        text = samples.read_sample(slug)
    except (KeyError, FileNotFoundError):
        raise HTTPException(status_code=404, detail="No sample with that name.") from None
    # The reader renders the display view, as the run page does. The download
    # link asks for view=saved, because a saved file should be the committed
    # file, not the text cleaned up for reading. Same two views as
    # GET /api/runs/{run_id}/report, but display stays the default here so the
    # reader's own fetch is unchanged.
    return PlainTextResponse(
        report_for_display(text) if view == "display" else text,
        media_type="text/markdown; charset=utf-8",
    )


@app.get("/health", response_model=HealthStatus, tags=["meta"])
def health() -> HealthStatus:
    """Liveness, shared paid-operation capacity, and resolved LLM provider.

    `llm_provider` is null when no key is configured — a run submitted in that
    state will start but fail inside the worker, so check this first.
    """
    # Reuse the pipeline's own resolution so this never disagrees with what a
    # run would actually use (it handles LLM_PROVIDER and the legacy
    # OPENAI_API_BASE-pointing-at-DeepSeek setup).
    try:
        provider = _detect_provider()
    except RuntimeError:
        provider = None
    # The model name comes from the full resolution, not a second env read:
    # QWEN_MODEL has a fallback variable and DeepSeek strips a vendor prefix,
    # and /health must report what a run would actually send. Only the name
    # is exposed; the resolved config also holds the key and endpoint.
    try:
        model = resolve_provider_config().model
    except RuntimeError:
        model = None

    # One locked snapshot prevents a worker finishing between two reads from
    # producing the impossible-looking state
    # active_paid_operations < active_runs.
    active_runs, active_paid_operations = runs.capacity_counts()
    return HealthStatus(
        status="ok",
        # Keep active_runs for clients and operators that specifically care
        # about subprocesses. Capacity indicators must use the broader value:
        # an inline PDF extraction holds the same slot even though it has no
        # run id and never appears in the worker registry.
        active_runs=active_runs,
        active_paid_operations=active_paid_operations,
        max_concurrent=runs.MAX_CONCURRENT,
        retention_days=runs.RUN_RETENTION_DAYS,
        llm_provider=provider,
        llm_model=model,
        pipeline_revision=_PIPELINE_REVISION,
        maintenance=_maintenance_status(),
        source_locator=_source_locator_status(),
        alerts=AlertStatus(**alerts.status()),
        mail=MailStatus(**mail.status()),
    )


def readiness() -> ReadinessStatus:
    """Everything a submitted run needs before it can get past its first minute.

    Split out of the endpoint so the checks can be exercised without HTTP, and
    so each one is a named string rather than a count — an operator staring at
    a deploy that will not go healthy needs to know which check failed.
    """
    # Configuration helpers are imported at module scope, not here. Importing
    # llm_config pulls in crewai, which calls load_dotenv() as a side effect —
    # so a lazy import inside this function would repopulate os.environ from
    # .env part-way through the very checks that are reading it, and report
    # keys the running process does not actually have.
    checks: dict[str, str] = {}

    try:
        provider = validate_llm_configuration()
        checks["llm"] = "ok"
    except RuntimeError as exc:
        provider = None
        checks["llm"] = str(exc).splitlines()[0]

    # Retrieval has no fallback: without a web search key the pipeline raises
    # SourceCollectionError before the first agent runs. Which of the two is
    # configured decides who is billed and how results are shaped, so it is
    # reported rather than reduced to a boolean.
    search = ("tavily" if os.getenv("TAVILY_API_KEY")
              else "serper" if os.getenv("SERPER_API_KEY") else None)
    checks["search"] = "ok" if search else (
        "no web search key: set SERPER_API_KEY or TAVILY_API_KEY")

    # A read-only outputs volume is the failure this catches that the other two
    # cannot: every key is right, the page loads, and each run dies at its
    # first write. Probed with a real file rather than os.access, which reports
    # the permission bits and not what the filesystem will actually allow.
    probe = runs.DEFAULT_OUTPUT_ROOT / f".readiness-{uuid4().hex}"
    created = False
    checks["outputs"] = "ok"
    try:
        runs.DEFAULT_OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
        # Concurrent Docker/operator probes must not delete each other's file.
        # Exclusive creation also prevents a collision from overwriting an
        # existing artifact. Clean up only files this request actually created.
        with probe.open("x", encoding="utf-8") as handle:
            created = True
            handle.write("ready\n")
    except OSError as exc:
        checks["outputs"] = f"outputs directory is not writable: {exc}"
    finally:
        if created:
            try:
                probe.unlink()
            except OSError as exc:
                # Preserve an earlier write failure; cleanup failure alone is
                # not proof of an unwritable mount. Neither failure is a pass.
                if checks["outputs"] == "ok":
                    checks["outputs"] = f"output probe cleanup failed: {exc}"

    # A malformed paid-operation ledger makes every operator-funded request
    # fail closed at admission. Treating that state as ready would route users
    # to an instance that cannot do its primary job. The check is conditional:
    # when the daily cap is disabled there is no ledger contract to satisfy.
    if runs.DAILY_CAP:
        try:
            runs.validate_paid_ledger()
            checks["paid_accounting"] = "ok"
        except runs.PaidLedgerUnavailable:
            # Do not expose the output path or parser details. Operators need
            # the failed boundary; clients do not need filesystem internals.
            checks["paid_accounting"] = (
                "paid-operation accounting is unavailable; paid work is blocked"
            )

    try:
        receipts.validate(runs.DEFAULT_OUTPUT_ROOT)
        checks["paid_receipts"] = "ok"
    except receipts.ReceiptError:
        checks["paid_receipts"] = "paid-request receipt storage is unavailable"

    return ReadinessStatus(
        ready=all(v == "ok" for v in checks.values()),
        checks=checks,
        llm_provider=provider,
        search_provider=search,
    )


@app.get(
    "/health/ready",
    response_model=ReadinessStatus,
    tags=["meta"],
    responses={503: {"description": "The container is running but cannot complete an assessment"}},
)
def health_ready(response: Response) -> ReadinessStatus:
    """Readiness, as distinct from liveness — 503 when a run would fail.

    /health answers "is this process alive", which a load balancer needs, and
    it returns 200 for a container that serves every page and fails every run.
    That gap was real: the Docker healthcheck asserted in a comment that such a
    container would be reported unhealthy, and it was not, because it only
    checked that /health returned at all.
    """
    status = readiness()
    # Pure readiness() is also used offline, without an ASGI lifecycle. Only
    # an actually managed task is a readiness precondition here. Liveness
    # always exposes not_started/stopped explicitly. Retention failures are
    # advisory: restarting paid workers cannot repair a cleanup permission.
    maintenance = _maintenance_status()
    status.maintenance = maintenance
    status.source_locator = _source_locator_status()
    if maintenance.state != "not_started":
        watchdog_ok = (
            maintenance.state in {"running", "degraded"}
            and maintenance.checks.get("timeouts") != "failed"
        )
        status.checks["watchdog"] = "ok" if watchdog_ok else "timeout watchdog unavailable"
        status.ready = status.ready and watchdog_ok
    if not status.ready:
        response.status_code = 503
    return status


@app.exception_handler(RequestValidationError)
async def request_validation_error(_request: Request, exc: RequestValidationError):
    """Refuse a malformed request by naming the field and the rule, never the value.

    The framework's own reply quotes what was sent. For a rule that looks at
    the whole body, such as "a key set is complete or absent", that is the
    whole body: a run request with a misspelt model name came back with the
    model key and the search key in it. They went only to whoever sent them,
    but an error reply is read by code that shows, logs and reports errors,
    and the privacy page says keys are not carried anywhere else.

    Every route gets the same three fields the API description already
    documents for a 422. The sentence in `msg` is the validator's own and is
    written without the value; tests/test_validation_errors.py sends secrets
    through every body-taking route and looks for them in the reply.
    """
    return JSONResponse(
        {"detail": [{"type": problem.get("type"), "loc": list(problem.get("loc", ())), "msg": problem.get("msg")}
                    for problem in exc.errors()]},
        status_code=422,
    )


@app.exception_handler(receipts.ReceiptError)
async def receipt_error(_request: Request, exc: receipts.ReceiptError):
    return JSONResponse({"detail": str(exc)}, status_code=exc.status,
                        headers={"X-Error-Code": exc.code, "Cache-Control": "no-store"})


class _PaperHTTPError(HTTPException):
    """Existing HTTP failure plus an independent, already-projected observation."""

    def __init__(self, original: HTTPException, summary: dict):
        super().__init__(original.status_code, original.detail, headers=original.headers)
        self.auxiliary_usage = summary


@app.exception_handler(_PaperHTTPError)
async def paper_http_error(_request: Request, exc: _PaperHTTPError):
    return JSONResponse({"detail": exc.detail, "auxiliary_usage": exc.auxiliary_usage},
                        status_code=exc.status_code, headers={"Cache-Control": "no-store", **(exc.headers or {})})


def _receipt_http_contract(*, required=False):
    return {"parameters": [{"name": "Idempotency-Key", "in": "header", "required": required,
        "schema": {"type": "string", "pattern": r"^v1\.[0-9]{10}\.[0-9a-f]{64}$"},
        "description": "256-bit random paid-intent capability. New keys need a recent UTC timestamp; replays/read-only lookup expire after 24 hours. Never put in a URL or log."}]}


def _claim_receipt(http_request: Request, *, byok: bool, kind: str, payload: dict):
    key = http_request.headers.get("Idempotency-Key")
    if key is None:
        # Backwards-compatible direct clients retain their old contract.
        # First-party clients always opt in; do not claim unkeyed idempotency.
        return None, None
    owner = _paid_owner(http_request, byok=byok,
                        detail="Provide the access code or complete BYOK credentials.")
    return receipts.claim(runs.DEFAULT_OUTPUT_ROOT, key, owner, kind, payload)


def _receipt_body(record: dict) -> dict:
    """Validate saved results at delivery, and never keep a second PDF copy."""
    try:
        body = record["response"]
        if record["state"] == "failed":
            if not 400 <= record["status"] <= 599 or not isinstance(body.get("detail"), str):
                raise ValueError("Invalid failed receipt")
            if body.get("error_code") not in {None, "concurrency_limit", "daily_quota_exceeded", "account_busy",
                                              "account_daily_quota_exceeded", "upload_capacity", "rate_limited"}:
                raise ValueError("Invalid failure category")
            body = {"detail": body["detail"], "error_code": body.get("error_code")}
            if record["kind"] == "paper" and record.get("resource_id"):
                # A parsing failure can follow a billed extraction. Project the
                # same authorized observation as GET without rewriting receipts
                # or depending on the discarded paper's extraction metadata.
                body["auxiliary_usage"] = auxiliary_usage.paper_summary(record["resource_id"])
            return body
        if record["kind"] == "paper":
            if record["status"] != 200 or body["paper_id"] != record["resource_id"]:
                raise ValueError("Invalid paper receipt")
            body = {"paper_id": body["paper_id"], **papers.load_extraction(body["paper_id"]),
                    "auxiliary_usage": auxiliary_usage.paper_summary(body["paper_id"])}
            return PaperExtraction.model_validate(body).model_dump(mode="json")
        if record["status"] != 202 or body["run_id"] != record["resource_id"]:
            raise ValueError("Invalid run receipt")
        return RunAccepted.model_validate(body).model_dump(mode="json")
    except papers.PaperNotFound as exc:
        raise receipts.ReceiptError(410, "receipt_result_expired", "The accepted paper result is no longer available; no extraction was repeated.") from exc
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise receipts.ReceiptError(503, "receipt_unavailable", "The saved receipt result is unreadable; do not resubmit with a new key.") from exc


def _replay_receipt(record: dict):
    if record["state"] == "pending":
        raise receipts.ReceiptError(409, "paid_receipt_pending", "This request already has an unresolved reservation. Query its receipt; do not create another paid request.")
    body = _receipt_body(record)
    metadata = {"Idempotency-Replayed": "true", "Cache-Control": "no-store"}
    if record["state"] == "failed" and body.get("error_code"):
        metadata["X-Error-Code"] = body["error_code"]
    return JSONResponse(body, status_code=record["status"], headers=metadata)


def _record_rejection(ticket: receipts.Ticket, exc: HTTPException):
    # A PDF's 422 can follow a billed call. Failed means outcome recorded,
    # never refunded/free. 5xx remains unresolved rather than false rejection.
    if 400 <= exc.status_code < 500 and exc.status_code != 408:
        ticket.finish({"detail": "The original request failed and was not retried. This does not establish zero cost.",
                       "error_code": (exc.headers or {}).get("X-Error-Code")},
                      exc.status_code, failed=True)


def _run_with_receipt(http_request: Request, request, kind: str, payload: dict, execute):
    ticket, prior = _claim_receipt(http_request, byok=request.byok, kind=kind, payload=payload)
    if prior is not None:
        return _replay_receipt(prior)
    with receipts.activate(ticket):
        try:
            result = execute()
            if ticket is not None:
                ticket.finish(result.model_dump(mode="json"), 202)
            return result
        except HTTPException as exc:
            if ticket is not None:
                _record_rejection(ticket, exc)
            raise


@app.get("/api/receipts", response_model=PaidReceipt, tags=["runs"],
         openapi_extra=_receipt_http_contract(required=True),
         responses={404: {"description": "Missing receipt or wrong owner; not proof of zero cost"},
                    410: {"description": "Expired receipt key or unavailable accepted paper"},
                    503: {"description": "Receipt observation unavailable"}})
def get_paid_receipt(http_request: Request, response: Response) -> PaidReceipt:
    """Read using Idempotency-Key header, never a credential-bearing URL.

    This endpoint cannot dispatch, retry, resume, cancel or refund anything.
    A pending resource id is an intended target, not proof of process launch.
    """
    key = http_request.headers.get("Idempotency-Key", "")
    who = identity.resolve(http_request)
    record = receipts.lookup(runs.DEFAULT_OUTPUT_ROOT, key, who.tag, admin=who.is_admin)
    public = receipts.public_record(record)
    if record["kind"] == "paper" and record.get("resource_id"):
        public["auxiliary_usage"] = auxiliary_usage.paper_summary(record["resource_id"])
    if record["state"] != "pending":
        public["response"] = _receipt_body(record)
    response.headers["Cache-Control"] = "no-store"
    return PaidReceipt.model_validate(public)


@app.post(
    "/api/runs",
    openapi_extra=_receipt_http_contract(),
    response_model=RunAccepted,
    status_code=202,
    tags=["runs"],
    responses={
        401: {"description": "Neither the access code nor complete bring-your-own-key credentials were provided"},
        429: {"description": "Concurrency or daily paid-operation limit reached"},
    },
)
def submit_run(request: RunRequest, http_request: Request) -> RunAccepted:
    return _run_with_receipt(http_request, request, "run", request.model_dump(mode="json"),
                             lambda: _submit_run_without_receipt(request, http_request))


def _byok_credentials(request: RunRequest | ResumeRunRequest) -> runs.BYOKCredentials | None:
    """The visitor's complete credential set, or None for operator billing.

    The request model has already rejected partial sets, so a BYOK request
    never falls back to the deployment's keys.
    """
    if not request.byok:
        return None
    return runs.BYOKCredentials(
        request.llm_provider, request.llm_api_key, request.serper_api_key,
        llm_model=request.llm_model, tavily_api_key=request.tavily_api_key,
    )


def _submit_run_without_receipt(request: RunRequest, http_request: Request) -> RunAccepted:
    """Queue an assessment. Returns immediately with a run_id to poll.

    Run time is provider-bound and may take several minutes; the 30-minute
    watchdog is the hard availability boundary. Authorized either by the
    X-Access-Code header (billed to the deployment) or by supplying
    llm_provider/llm_api_key/serper_api_key in the body (billed to the
    caller) — not gated by the middleware because that choice needs the
    parsed body.
    """
    # A code holder's BYOK run gets no owner tag — never recorded in anyone's
    # history, billed to the requester, gone once the tab closes (the frontend
    # keeps its own session-only list; see web/static/js/app.js). An account's
    # BYOK run is tagged to the account: that is what the account is for.
    owner = _paid_owner(
        http_request, byok=request.byok,
        detail="Provide the access code, or your own llm_provider/llm_api_key "
               "and a tavily_api_key or serper_api_key.",
    )

    paper_json_path: str | None = None
    auxiliary_pdf_reference = None
    if request.paper_id:
        try:
            paper_json_path = str(
                papers.extraction_path_for_run(request.paper_id, owner=owner)
            )
            auxiliary_pdf_reference = auxiliary_usage.paper_reference(request.paper_id)
        except papers.PaperNotFound as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    byok = _byok_credentials(request)

    try:
        run_id, _ = runs.start_run(
            topic=request.topic,
            language=request.language,
            weight_profile=request.weight_profile,
            paper_json_path=paper_json_path,
            **({"auxiliary_pdf_reference": auxiliary_pdf_reference} if auxiliary_pdf_reference is not None else {}),
            decision_context=request.decision_context,
            byok=byok,
            owner=owner,
            search_plan=request.search_plan,
        )
    except (runs.ConcurrencyLimitReached, runs.DailyCapReached) as exc:
        raise _admission_refusal(exc) from exc
    except runs.PaidLedgerUnavailable as exc:
        _LOGGER.exception("Paid-operation accounting blocked run admission")
        raise HTTPException(
            status_code=503,
            detail=(
                "Paid-operation accounting is temporarily unavailable. "
                "No provider call was started; retry later."
            ),
        ) from exc
    except OSError as exc:
        _LOGGER.exception("Failed to start analysis worker")
        raise HTTPException(
            status_code=500,
            detail="The analysis worker could not be started. Retry later.",
        ) from exc

    return RunAccepted(
        run_id=run_id,
        state="running",
        topic=request.topic,
        assessment_mode=request.assessment_mode,
    )

@app.post(
    "/api/runs/{run_id}/resume",
    openapi_extra=_receipt_http_contract(),
    response_model=RunAccepted,
    status_code=202,
    tags=["runs"],
    responses={
        401: {"description": "Fresh access-code or BYOK credentials are required"},
        404: {"description": "Unknown run_id or caller does not own the source run"},
        409: {"description": "Run is active, completed, or has no resumable checkpoint"},
        429: {"description": "Concurrency or daily paid-operation limit reached"},
    },
)
def resume_run(
    run_id: str,
    request: ResumeRunRequest,
    http_request: Request,
) -> RunAccepted:
    return _run_with_receipt(http_request, request, "resume", {"parent": run_id, **request.model_dump(mode="json")},
                             lambda: _resume_run_without_receipt(run_id, request, http_request))


def _resume_run_without_receipt(run_id: str, request: ResumeRunRequest, http_request: Request) -> RunAccepted:
    """Start an immutable child that reuses only validated source checkpoints.

    A resume is a new paid operation, not an in-place process restart. The
    failed source remains untouched for audit, fresh credentials cross the
    subprocess boundary, and the worker independently validates every content
    hash before skipping a node. A stale or corrupt prefix therefore falls
    back to execution rather than becoming an unearned successful recovery.
    """
    _authorize_run_mutation(run_id, http_request)
    owner = _paid_owner(http_request, byok=request.byok,
                        detail="Provide the access code, or fresh BYOK credentials to resume.")
    byok = _byok_credentials(request)

    try:
        child_id, child_directory = runs.resume_run(
            run_id, byok=byok, owner=owner
        )
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except runs.RunNotResumable as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (runs.ConcurrencyLimitReached, runs.DailyCapReached) as exc:
        raise _admission_refusal(exc) from exc
    except runs.PaidLedgerUnavailable as exc:
        _LOGGER.exception(
            "Paid-operation accounting blocked resume for run %s", run_id
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "Paid-operation accounting is temporarily unavailable. "
                "No provider call was started; retry later."
            ),
        ) from exc
    except OSError as exc:
        _LOGGER.exception("Failed to resume analysis worker for run %s", run_id)
        raise HTTPException(
            status_code=500,
            detail="The analysis worker could not be resumed. Retry later.",
        ) from exc

    # Read from the child's frozen contract rather than trusting status.json;
    # the worker may not have produced its first status write before this 202.
    child_spec = runs.RunSpec.load(child_directory)
    return RunAccepted(
        run_id=child_id,
        state="running",
        topic=child_spec.topic,
        assessment_mode=child_spec.assessment_mode,
        resumed_from=run_id,
    )



@app.get("/api/health/retrieval", response_model=RetrievalHealth, tags=["meta"])
def retrieval_health_summary(
    http_request: Request,
    window: int = Query(default=retrieval_health.DEFAULT_WINDOW, ge=1, le=100),
) -> RetrievalHealth:
    """Which retrieval lanes came back empty or refused across recent runs.

    /health/ready checks that keys are configured; this reports whether the
    sources behind them have actually been answering. Behind the access code,
    scoped as GET /api/runs is, because it reads run history.
    """
    try:
        run_dirs = runs.run_directories(owner=http_request.state.owner)
    except runs.OwnerMarkerUnreadable as exc:
        _LOGGER.exception("Run history ownership metadata could not be read")
        raise HTTPException(
            status_code=503,
            detail="Run history is temporarily unavailable. Retry later.",
        ) from exc
    return RetrievalHealth(**retrieval_health.summarize(run_dirs, window=window))


@app.get("/api/runs", response_model=RunList, tags=["runs"])
def list_runs(http_request: Request, limit: int = Query(default=50, ge=1, le=200),
              offset: int = Query(default=0, ge=0, le=100_000)) -> RunList:
    """List runs, newest first — scoped to the calling code's own history.

    `offset` skips that many of the newest runs; `total` in the reply is the
    size of the whole history. There is no search parameter on purpose: a
    topic typed into a query string would be written to the access log, and
    the page filters what it has loaded instead.

    `request.state.owner`/`.is_admin` were set by the access-gate
    middleware, which ran ahead of this handler for every path that isn't
    POST /api/runs or /api/runs/{id}/...; this path falls into neither, so
    both are always set (owner to None when the gate is disabled entirely,
    meaning no filter).
    """
    try:
        summaries, total = runs.list_runs(
            limit=limit, owner=http_request.state.owner, offset=offset
        )
    except runs.OwnerMarkerUnreadable as exc:
        # Omitting the affected entry would make a protected run look absent;
        # labelling it ownerless would expose it to the admin view incorrectly.
        # Fail the snapshot explicitly and preserve the storage detail in logs.
        _LOGGER.exception("Run history ownership metadata could not be read")
        raise HTTPException(
            status_code=503,
            detail="Run history is temporarily unavailable. Retry later.",
        ) from exc
    if http_request.state.is_admin:
        # An unlabelled merge of everyone's history answers "what ran" but
        # not "who ran it" — the entire reason to hold the admin code
        # rather than just leaving the gate unfiltered for everyone.
        for summary in summaries:
            summary["owner_label"] = identity.label_for_owner(summary.pop("_owner", None))
    else:
        for summary in summaries:
            summary.pop("_owner", None)
    return RunList(runs=summaries, total=total)


@app.get(
    "/api/runs/{run_id}",
    response_model=RunStatus,
    tags=["runs"],
    responses={404: {"description": "Unknown run_id"}},
)
def get_run(run_id: str) -> RunStatus:
    """Current stage and state. Poll this while `state` is `running`."""
    try:
        return RunStatus(**runs.get_state(run_id))
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete(
    "/api/runs/{run_id}",
    tags=["runs"],
    responses={
        404: {"description": "Unknown run_id"},
        409: {"description": "Run state conflicts with the requested mutation intent"},
        503: {"description": "Worker stop could not be confirmed; refresh status before retrying"},
    },
)
def delete_run(
    run_id: str, http_request: Request,
    intent: Literal["cancel", "delete"] | None = Query(
        default=None,
        description="cancel never deletes; delete never cancels. Omit only for legacy cancel-or-delete behavior.",
    ),
) -> dict:
    """Stop a live run, or permanently delete a finished one's record.

    Without intent, a live run is terminated (kept, marked cancelled) so its partial
    progress stays inspectable — call this again once it has stopped to
    actually remove it. A run that is already completed, failed, cancelled,
    or timed out is deleted immediately: its directory, report, and every
    other artifact are gone for good, not just hidden from the list.

    The web client specifies intent so a stale Cancel cannot erase a newly
    completed report and a stale Delete cannot stop paid work. Omitted intent
    retains the documented dual-purpose behavior for older API callers.

    Code-owned mutations still require their owner/admin code, unlike shared
    reads. Ownerless BYOK retains its existing capability-based mutation
    contract because it has no second server-side identity. Intent constrains
    the operation; it does not replace either authorization boundary.
    """
    _authorize_run_mutation(run_id, http_request)

    if intent != "delete":
        try:
            runs.cancel_run(run_id)
            return {"run_id": run_id, "action": "cancelled"}
        except runs.RunStillActive as exc:
            # A second stop (including legacy DELETE) cannot fall through to
            # deletion while the first owns process exit or terminal writes.
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except runs.RunStopFailed as exc:
            _LOGGER.exception("Failed to stop run %s", run_id)
            raise HTTPException(
                status_code=503,
                detail="The run could not be stopped. Refresh its status before trying again.",
            ) from exc
        except runs.RunNotFound:
            if intent == "cancel":
                # A preflight GET in the browser cannot close this race: the
                # worker may finish before DELETE arrives. Preserve the user's
                # operation at dispatch instead of promoting it to destruction.
                # The existing reader validates the id and distinguishes a
                # missing run from a retained one without guessing from stage.
                try:
                    runs.get_state(run_id)
                except runs.RunNotFound as exc:
                    raise HTTPException(status_code=404, detail=str(exc)) from exc
                raise HTTPException(
                    status_code=409,
                    detail="Run is no longer active. Refresh its status; no artifacts were deleted.",
                ) from None
            # Legacy callers explicitly retain the old cancel-or-delete route.

    try:
        # delete_run owns the locked active-process check. A caller asking to
        # delete must never route through cancel_run, even if its UI is stale.
        runs.delete_run(run_id)
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except runs.RunStillActive as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        _LOGGER.exception("Failed to delete run %s", run_id)
        raise HTTPException(
            status_code=500,
            detail="The run could not be deleted. Retry later.",
        ) from exc
    return {"run_id": run_id, "action": "deleted"}


@app.get(
    "/api/runs/{run_id}/report",
    response_class=PlainTextResponse,
    tags=["artifacts"],
    responses={
        200: {"content": {"text/markdown": {}}},
        409: {"description": "Run has not produced a report yet"},
    },
)
def get_report(
    run_id: str,
    view: Literal["saved", "display"] = Query(
        default="saved",
        description="'display' is the report as the page shows it: the code-owned applicability paragraph "
                    "as sentences and a cleaned reference list; 'saved' is every byte as saved",
    ),
) -> PlainTextResponse:
    """The final Markdown report, as saved unless view=display."""
    try:
        state = runs.get_state(run_id)
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    path = runs.artifact_path(run_id, "report")
    if path is None:
        raise HTTPException(
            status_code=409,
            detail=f"No report available; run state is '{state['state']}'.",
        )
    text = path.read_text(encoding="utf-8")
    return PlainTextResponse(
        report_for_display(text) if view == "display" else text,
        media_type="text/markdown; charset=utf-8",
    )


@app.get(
    "/api/runs/{run_id}/progress",
    response_model=RunProgress,
    tags=["runs"],
    responses={404: {"description": "Unknown run_id"}},
)
def get_progress(run_id: str, since: int = Query(default=0, ge=0)) -> RunProgress:
    """Status plus new step events, for a client polling during a run.

    `since` is the physical-line cursor returned as `steps_next_cursor`, not
    the number of valid events received. The append-only log can contain
    rejected rows; its failure must not hide a committed run outcome.

    Registered before /api/runs/{run_id}/{artifact} because that route would
    otherwise match "progress" as an artifact name.
    """
    try:
        state = runs.get_state(run_id)
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return RunProgress(
        run_id=run_id,
        state=state["state"],
        status_record_state=state.get("status_record_state"),
        audit_metadata_unreadable=state.get("audit_metadata_unreadable", []),
        runtime_metadata_unreadable=state.get("runtime_metadata_unreadable", []),
        stage=state.get("stage", ""),
        topic=state.get("topic", ""),
        pipeline_revision=state.get("pipeline_revision"),
        # Unknown is retryable, not evidence that execution finished.
        done=state["state"] in {"completed", "failed", "cancelled", "timeout"},
        error=state.get("error"),
        error_code=state.get("error_code"),
        funded_by=state.get("funded_by"),
        daily_charge=state.get("daily_charge", "not_recorded"),
        elapsed_seconds=state.get("elapsed_seconds"),
        stage_timings=state.get("stage_timings", []),
        eta=state.get("eta"),
        source_counts=state.get("source_counts"),
        evidence_incomplete=state.get("evidence_incomplete", False),
        failed_domains=state.get("failed_domains", []),
        output_language=state.get("output_language", "English"),
        # Threaded explicitly, like every other field here. That is the flaw
        # this pair of lines is fixing: RunStatus builds itself with
        # RunStatus(**get_state(...)) and picks up new keys automatically,
        # while this constructor names each one, so a field added to
        # get_state() reaches one endpoint and silently not the other.
        # test_api_contract.py now fails when they diverge.
        usage=state.get("usage"),
        usage_accounting=state.get("usage_accounting"),
        auxiliary_usage=state.get("auxiliary_usage"),
        runtime_budget=state.get("runtime_budget"),
        terminal=state.get("terminal"),
        claim_grounding=state.get("claim_grounding"),
        authority_coverage=state.get("authority_coverage"),
        component_coverage=state.get("component_coverage"),
        evidence_gap_shadow=state.get("evidence_gap_shadow"),
        decision_gate=state.get("decision_gate"),
        report_audit=state.get("report_audit"),
        quality_review=state.get("quality_review"),
        consistency=state.get("consistency"),
        observability=state.get("observability"),
        checkpointing=state.get("checkpointing"),
        recovery=state.get("recovery"),
        **runs.read_step_page(run_id, since=since),
        artifacts=state.get("artifacts", []),
    )


#: Read the body in pieces so an oversized upload is refused partway rather
#: than after it is entirely in memory. The previous code did `await
#: file.read()` and only then compared the length, so a 2 GB body was
#: allocated in full before being rejected — the check ran, but only once the
#: damage it was meant to prevent had already happened.
_UPLOAD_CHUNK = 1024 * 1024


async def _read_capped(file: UploadFile, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(_UPLOAD_CHUNK)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise papers.PaperTooLarge(
                f"Upload exceeds the {limit // 1024 // 1024} MB limit"
            )
        chunks.append(chunk)
    return b"".join(chunks)


def _extract_paper_with_paid_reservation(
    pdf_path: str,
    *,
    owner: str | None,
    byok: bool,
    llm_provider: str | None,
    llm_api_key: str | None,
    llm_model: str | None = None,
) -> PaperContribution:
    """Extract while the actual worker thread owns the paid-operation slot.

    asyncio cancellation stops awaiting ``to_thread`` but cannot stop its
    underlying thread. Keeping the reservation in the request coroutine would
    therefore publish a free slot while the provider call was still running.
    The worker thread instead releases it only when extraction really exits.
    """
    with runs.reserve_inline_paid_operation(owner=owner, byok=byok):
        return extract_paper_contribution(
            pdf_path,
            llm_provider=llm_provider if byok else None,
            llm_api_key=llm_api_key if byok else None,
            llm_model=llm_model if byok else None,
        )


class _PaperStorageError(OSError):
    """Separate local publication/privacy failure from provider output failure."""


class _PaperAbandoned(RuntimeError):
    """Queued work lost its waiter before provider admission; cleanup only."""


async def _process_uploaded_paper(paper_id: str, pdf_path: str, **credentials) -> PaperContribution:
    """The actual thread finalizes raw storage even if its HTTP waiter leaves.

    Shielding keeps a queued thread from being cancelled before it starts and
    orphaning the already-saved PDF. A legacy abandoned result is discarded by that
    thread. If cancellation arrives after finalization, only derived metadata
    may remain for normal pending-paper retention, never the raw PDF. Hard
    process death and failing storage still require retention/reconciliation.
    """
    abandoned = threading.Event()
    ticket = receipts.current()

    def execute_owned() -> PaperContribution:
        stored = False
        try:
            # Shielding assigns cleanup ownership, not permission to spend
            # money for a request already abandoned while waiting for a thread.
            if abandoned.is_set():
                if ticket is not None:
                    ticket.finish({"detail": "The request was abandoned before provider admission; no extraction started."},
                                  409, failed=True)
                raise _PaperAbandoned
            receipts.bind_resource(paper_id)
            contribution = _extract_paper_with_paid_reservation(pdf_path, **credentials)
            try:
                papers.save_extraction(paper_id, contribution.model_dump())
            except OSError as exc:
                raise _PaperStorageError("Could not safely store the paper extraction.") from exc
            stored = True
            if ticket is not None:
                # Receipt-enabled running work publishes in the actual thread,
                # even if its HTTP waiter disappeared. The derived result has
                # the normal paper TTL; raw input was removed by save_extraction.
                ticket.finish({"paper_id": paper_id}, 200)
            return contribution
        except (receipts.ReceiptError, _PaperAbandoned):
            # A failed commit is unavailable acknowledgement, not extraction
            # failure. Queued abandonment already has its own final receipt.
            raise
        except Exception as exc:  # noqa: BLE001 - SDK/parser failures vary; actual thread owns finality
            if ticket is not None:
                if isinstance(exc, (runs.ConcurrencyLimitReached, runs.DailyCapReached)):
                    status = 429
                    code = _admission_code(exc)
                else:
                    status = (503 if isinstance(exc, runs.PaidLedgerUnavailable) else
                              500 if isinstance(exc, _PaperStorageError) else 422)
                    code = None
                # A cancelled waiter cannot run its HTTP exception mapping.
                # Record known execution failure here, including local 5xx.
                # No exception text, refund claim or inferred zero usage.
                ticket.finish({"detail": "The original request failed and was not retried. This does not establish zero cost.",
                               "error_code": code}, status, failed=True)
            raise
        finally:
            if not stored or (abandoned.is_set() and ticket is None):
                papers.discard(paper_id)

    def execute() -> PaperContribution:
        # Bind inside the actual thread, not the cancellable HTTP waiter.
        with auxiliary_usage.paper_operation(paper_id) as collector:
            contribution = execute_owned()
        contribution._auxiliary_usage = collector.summary()
        return contribution

    task = asyncio.create_task(asyncio.to_thread(execute))
    _paper_jobs.add(task)

    def finished(done: asyncio.Task) -> None:
        _paper_jobs.discard(done)
        if done.cancelled():
            abandoned.set()
        else:
            # A disconnected waiter cannot retrieve an exception. Observe it
            # without logging provider messages that may contain credentials.
            error = done.exception()
            if abandoned.is_set() and error is not None and not isinstance(error, _PaperAbandoned):
                _LOGGER.warning("Abandoned paper extraction failed: %s", type(error).__name__)

    task.add_done_callback(finished)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        abandoned.set()
        raise


@app.post(
    "/api/papers",
    openapi_extra=_receipt_http_contract(),
    response_model=PaperExtraction,
    tags=["papers"],
    responses={
        408: {"description": "Upload receive deadline exceeded before extraction"},
        413: {"description": "File or complete multipart request exceeds its size limit"},
        429: {"description": "Upload preprocessing, paid concurrency or daily operation limit reached"},
        422: {"description": "PDF could not be parsed into a contribution"},
    },
)
async def upload_paper(
    http_request: Request,
    file: UploadFile = File(...),
    llm_provider: str | None = Form(default=None),
    llm_api_key: str | None = Form(default=None),
    llm_model: str | None = Form(default=None),
) -> PaperExtraction:
    """Extract a paper's contribution from an uploaded PDF.

    Returns the extraction and a paper_id. Pass that id to POST /api/runs to
    anchor a run on the paper; the fields are editable first, since the topic
    the model derives is a starting point rather than an answer.

    Authorized like POST /api/runs and for the same reason: by the access code
    header, or by bringing your own key. This endpoint makes an LLM call, so it
    cannot simply be opened — but leaving it gated by the code alone meant a
    visitor using their own keys could run a topic assessment and not attach a
    paper, which is half of an advertised path. Supplying the two credentials
    bills the extraction to whoever supplied them.

    Runs the extractor in a worker thread: it makes an LLM call and would
    otherwise block the event loop for several seconds.
    """
    credential_fields = (llm_provider, llm_api_key)
    if any(credential_fields) and not all(credential_fields):
        raise HTTPException(
            status_code=422,
            detail="llm_provider and llm_api_key must be provided together or both omitted.",
        )
    if llm_provider is not None and llm_provider not in BYOK_PROVIDERS:
        raise HTTPException(
            status_code=422,
            detail=f"llm_provider must be one of {BYOK_PROVIDERS}.",
        )
    # Extraction never searches, so no search key is involved here; the model
    # only applies to the visitor's own key, and is required with it: there is
    # no default. Direct (non-HTTP) callers receive the Form() default object
    # rather than None, and an empty form field names no model, so only a
    # non-empty string counts.
    llm_model = (llm_model.strip() or None) if isinstance(llm_model, str) else None
    if llm_model is not None and (not llm_provider or not BYOK_MODEL_PATTERN.fullmatch(llm_model)):
        raise HTTPException(
            status_code=422,
            detail="llm_model requires llm_provider and must be a plain model identifier.",
        )
    if llm_provider and llm_model is None:
        raise HTTPException(
            status_code=422,
            detail="llm_model is required with llm_provider: there is no default model.",
        )
    byok = bool(llm_provider)
    owner = _paid_owner(http_request, byok=byok,
                        detail="Provide the access code, or your own llm_provider/llm_api_key.")

    try:
        data = await _read_capped(file, papers.MAX_UPLOAD_BYTES)
    except papers.PaperTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    ticket, prior = await asyncio.to_thread(
        _claim_receipt, http_request, byok=byok, kind="paper",
        payload={"pdf_sha256": hashlib.sha256(data).hexdigest(),
                 "llm_provider": llm_provider, "llm_api_key": llm_api_key,
                 "llm_model": llm_model},
    )
    if prior is not None:
        del data
        release_upload_slot(http_request.scope)
        return await asyncio.to_thread(_replay_receipt, prior)
    # A shared one-item holder lets the storage helper release the bounded
    # buffer before model latency instead of retaining it in both coroutines.
    buffer = [data]
    del data
    with receipts.activate(ticket):
        try:
            return await _upload_paper_bytes(buffer, http_request, owner=owner, byok=byok,
                                             llm_provider=llm_provider, llm_api_key=llm_api_key,
                                             llm_model=llm_model)
        except HTTPException as exc:
            if ticket is not None:
                await asyncio.to_thread(_record_rejection, ticket, exc)
            raise


async def _upload_paper_bytes(buffer: list[bytes], http_request: Request, *, owner, byok, llm_provider, llm_api_key,
                              llm_model=None):
    data = buffer.pop()
    try:
        paper_id, pdf_path = papers.save_upload(data, owner=owner)
    except papers.PaperTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except papers.PaperNotAPdf as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    # Keep preprocessing capacity through the bounded spool-to-storage copy,
    # not just multipart parsing. Do not retain another 50 MiB bytes object
    # across model latency. Paid admission still belongs to the worker thread.
    del data
    release_upload_slot(http_request.scope)
    try:
        return await _uploaded_paper_result(paper_id, pdf_path, owner=owner, byok=byok,
                                            llm_provider=llm_provider, llm_api_key=llm_api_key,
                                            llm_model=llm_model)
    except HTTPException as exc:
        summary = await asyncio.to_thread(auxiliary_usage.paper_summary, paper_id)
        raise _PaperHTTPError(exc, summary) from exc
    except receipts.ReceiptError as exc:
        summary = await asyncio.to_thread(auxiliary_usage.paper_summary, paper_id)
        original = HTTPException(exc.status, str(exc), headers={"X-Error-Code": exc.code})
        raise _PaperHTTPError(original, summary) from exc


async def _uploaded_paper_result(paper_id, pdf_path, *, owner, byok, llm_provider, llm_api_key,
                                 llm_model=None):
    try:
        contribution = await _process_uploaded_paper(
            paper_id, str(pdf_path),
            owner=owner,
            byok=byok,
            llm_provider=llm_provider,
            llm_api_key=llm_api_key,
            llm_model=llm_model,
        )
    except (runs.ConcurrencyLimitReached, runs.DailyCapReached) as exc:
        raise _admission_refusal(exc) from exc
    except runs.PaidLedgerUnavailable as exc:
        _LOGGER.error("Paid-operation accounting blocked paper (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail=(
                "Paid-operation accounting is temporarily unavailable. "
                "No provider call was started; retry later."
            ),
        ) from exc
    except _PaperStorageError as exc:
        _LOGGER.error("Paper extraction storage failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=500, detail="Could not safely store the paper extraction."
        ) from exc
    except receipts.ReceiptError:
        # A failed receipt write is an unknown acknowledgement, not malformed
        # provider output and never permission to send a second extraction.
        raise
    except Exception as exc:  # noqa: BLE001 - provider failures vary by SDK
        # The upload is unreachable from here on — no paper_id reaches the
        # client, so no run can name it — and it is somebody's unpublished
        # paper. Deleted now rather than left for the day-long pruner.
        # Exception text/chains can contain model output, input validation
        # echoes, credentials and capability paths. Ordinary deployment logs
        # retain the failure category, never the private response or paper id.
        _LOGGER.error("Paper contribution extraction failed (%s)", type(exc).__name__)
        raise HTTPException(
            status_code=422,
            detail=(
                "The paper could not be converted into a structured contribution. "
                "Retry or use another PDF."
            ),
        ) from exc

    summary = getattr(contribution, "_auxiliary_usage", None)
    if not isinstance(summary, dict):
        # No eager getattr default: a private-store/pruner lock and filesystem
        # access must never execute on the ASGI event loop, even on fallback.
        summary = await asyncio.to_thread(auxiliary_usage.paper_summary, paper_id)
    return PaperExtraction(paper_id=paper_id, **contribution.model_dump(), auxiliary_usage=summary)


@app.get(
    "/api/runs/{run_id}/report.pdf",
    tags=["artifacts"],
    responses={
        200: {"content": {"application/pdf": {}}},
        409: {"description": "Run has not produced a report yet"},
    },
)
def get_report_pdf(run_id: str) -> FileResponse:
    """The report as a PDF, with CJK glyphs embedded.

    Generated on first request and cached beside the report: rendering takes a
    second or two, and most runs are never exported. The embedded font matters
    here — a reader without a CJK typeface installed would otherwise see blank
    boxes, which is why the image build verifies one resolves.
    """
    try:
        state = runs.get_state(run_id)
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    markdown_path = runs.artifact_path(run_id, "report")
    if markdown_path is None:
        raise HTTPException(
            status_code=409,
            detail=f"No report available; run state is '{state['state']}'.",
        )

    pdf_path = markdown_path.parent / "commercialization_report.pdf"
    from ui.pdf_export import _generate_pdf, pdf_cache_complete, pdf_cache_lock

    try:
        # Check inside the lock. Atomic publication prevents torn reads, but
        # alone still lets simultaneous first downloads build the same report.
        with pdf_cache_lock(markdown_path.parent):
            if not pdf_cache_complete(pdf_path):
                # The PDF is read like the page, not like the audit file.
                _generate_pdf(
                    report_for_display(markdown_path.read_text(encoding="utf-8")),
                    markdown_path.parent,
                    output_language=state.get("output_language", "English"),
                )
    except Exception as exc:  # noqa: BLE001 - renderer/filesystem backends vary; sanitize HTTP detail
        _LOGGER.exception("Report PDF rendering failed for run %s", run_id)
        raise HTTPException(
            status_code=500,
            detail=(
                "The report PDF could not be rendered. "
                "The Markdown report is still available."
            ),
        ) from exc

    if not pdf_path.exists():
        raise HTTPException(status_code=500, detail="PDF rendering produced no file.")

    return FileResponse(
        pdf_path, media_type="application/pdf", filename=f"{run_id}.pdf"
    )


def _feedback_run(run_id: str, http_request: Request):
    """Authorize as a mutation and resolve the run and the responder.

    404 when the run is unknown or not the caller's. The responder is who the
    answer is filed under: an ownerless run has one, whoever holds its URL,
    whatever code they also present; a code-owned run files under the code
    that answered (the owner's or the admin's), or under the owner when no
    gate is configured and there is no code to tell callers apart.
    """
    _authorize_run_mutation(run_id, http_request)
    try:
        state = runs.get_state(run_id)
        owner = runs.owner_of(run_id)
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except runs.OwnerMarkerUnreadable as exc:
        raise HTTPException(
            status_code=503, detail="Run authorization is temporarily unavailable. Retry later.",
        ) from exc
    who = identity.resolve(http_request)
    if owner is None:
        responder = feedback.responder_key(None)
    else:
        responder = who.tag if who.tag is not None else owner
    return state, runs.run_dir_for(run_id), responder


def _feedback_state(record: dict | None) -> FeedbackState:
    if record is None:
        return FeedbackState(recorded=False)
    return FeedbackState(recorded=True, changed_view=record["changed_view"],
                         part=record.get("part"), recorded_at=record["recorded_at"])


@app.get(
    "/api/runs/{run_id}/feedback",
    response_model=FeedbackState,
    tags=["runs"],
    responses={
        404: {"description": "Unknown run_id, or a code-owned run without its code"},
        503: {"description": "The stored feedback could not be read"},
    },
)
def get_feedback(run_id: str, http_request: Request) -> FeedbackState:
    """The caller's own answer about this report, if they gave one.

    Registered before /api/runs/{run_id}/{artifact}, which would otherwise
    take "feedback" as an artifact name. Reading needs what writing needs: a
    code-owned run answers only to its code or the admin, an ownerless run to
    whoever holds its URL. Answers are kept per responder, so no reader sees
    another's.
    """
    _state, run_dir, responder = _feedback_run(run_id, http_request)
    try:
        record = feedback.read(run_dir, responder)
    except feedback.FeedbackUnreadable as exc:
        raise HTTPException(
            status_code=503, detail="Stored feedback is unreadable; no answer is claimed.",
        ) from exc
    return _feedback_state(record)


@app.post(
    "/api/runs/{run_id}/feedback",
    response_model=FeedbackState,
    tags=["runs"],
    responses={
        404: {"description": "Unknown run_id, or a code-owned run without its code"},
        409: {"description": "The run delivered no report to answer about"},
        503: {"description": "The answer could not be stored"},
    },
)
def post_feedback(run_id: str, body: FeedbackRequest, http_request: Request) -> FeedbackState:
    """Record one reader's answer about a delivered report.

    Not a paid operation, and bounded without a cap of its own: the body is
    a closed vocabulary and each responder holds one record, so the most a
    caller can do is change their own answer. A run that delivered no report
    has nothing to answer about.
    """
    state, run_dir, responder = _feedback_run(run_id, http_request)
    if state["state"] != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Feedback is recorded for delivered reports only; this run is '{state['state']}'.",
        )
    try:
        record = feedback.record(run_dir, responder, body.changed_view, body.part)
    except feedback.FeedbackUnreadable as exc:
        raise HTTPException(
            status_code=503,
            detail="Stored feedback is unreadable, so a new answer cannot be added to it.",
        ) from exc
    except OSError as exc:
        _LOGGER.exception("Feedback could not be stored for run %s", run_id)
        raise HTTPException(status_code=503, detail="The answer could not be stored. Retry later.") from exc
    return _feedback_state(record)


@app.get(
    "/api/runs/{run_id}/{artifact}",
    tags=["artifacts"],
    responses={
        404: {"description": "Unknown run_id or artifact name"},
        409: {"description": "Artifact not produced by this run"},
    },
)
def get_artifact(run_id: str, artifact: str) -> FileResponse:
    """Fetch a named run artifact advertised by the status endpoint."""
    try:
        state = runs.get_state(run_id)
    except runs.RunNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    path = runs.artifact_path(run_id, artifact)
    if path is None:
        known = runs.artifact_names()
        if artifact not in known:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown artifact '{artifact}'. Available names: {known}",
            )
        raise HTTPException(
            status_code=409,
            detail=(
                f"Run produced no '{artifact}'; state is '{state['state']}'. "
                f"Available: {state['artifacts']}"
            ),
        )

    media = "application/json" if path.suffix == ".json" else "text/plain; charset=utf-8"
    return FileResponse(path, media_type=media, filename=path.name)
