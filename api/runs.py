"""Run lifecycle management for the HTTP API.

Owns the registry of live worker processes, enforces the concurrency cap,
and derives run state from the artifacts on disk.

State is projected through durable files by design:
  • status.json — mutable worker progress and the latest completed-node usage
  • terminal.json — immutable worker/API join for the actual process outcome
  • legacy error/cancellation markers — compatibility for historical readers

The HTTP API, browser and CLI therefore observe the same run without sharing
process memory. The API writes terminal truth only after an externally stopped
worker can no longer write it itself.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from academic_agent.checkpoints import CheckpointStore, hash_json
from academic_agent.run_output import DEFAULT_OUTPUT_ROOT, create_run_id
from academic_agent.run_spec import (
    RESUME_SNAPSHOT_DIRECTORY,
    DecisionContext,
    RunSpec,
)
from academic_agent.run_terminal import (
    TerminalRecord,
    TerminalRecordUnreadable,
    UsageAccounting,
    commit_terminal_record,
    load_terminal_record,
)
from api.audit_projection import project_audit_metadata
from api.runtime_projection import project_runtime_metadata

# A run is killed after this long. The bound belongs to the worker contract,
# not to whichever client submitted or polls the run.
TIMEOUT_SECONDS = 1800

# Concurrent paid operations, not merely worker processes. A full assessment
# occupies a subprocess; PDF contribution extraction calls the same upstream
# LLM inline, so both paths draw from this one host/provider ceiling.
MAX_CONCURRENT = int(os.getenv("API_MAX_CONCURRENT", "2"))

# How many paid-operation slots visitors bringing their own key may hold at
# once, across worker runs and inline PDF extraction. They are exempt from the
# daily wallet cap because they pay for their own tokens, but not from finite
# host/provider capacity. Defaults to leaving one slot that only an
# access-code holder can take.
_BYOK_MAX_CONCURRENT_ENV = os.getenv("API_BYOK_MAX_CONCURRENT")
BYOK_MAX_CONCURRENT: int | None = (
    int(_BYOK_MAX_CONCURRENT_ENV) if _BYOK_MAX_CONCURRENT_ENV else None
)


def byok_limit() -> int:
    """Effective BYOK cap: the configured value, or one below the global cap.

    Derived when unset rather than frozen at import, so the default tracks
    MAX_CONCURRENT instead of silently keeping whatever that was the moment
    this module loaded. Freezing it made raising MAX_CONCURRENT stop meaning
    "allow more runs" — the global cap moved and this one did not, which is
    the sort of coupling that shows up as a test failing for a reason
    unrelated to what it tests.
    """
    if BYOK_MAX_CONCURRENT is not None:
        return BYOK_MAX_CONCURRENT
    return max(1, MAX_CONCURRENT - 1)

# Operator-funded paid operations admitted per UTC day, applied separately to
# each access code. Both a full run and PDF contribution extraction reach a
# paid provider, so counting only runs left an unmetered endpoint beside the
# cap. BYOK operations remain exempt because the visitor pays.
#
# API_DAILY_RUN_CAP is retained as a deployment-compatible fallback. The new
# name describes the boundary accurately; existing Railway environments do
# not have to change atomically with this release. 0 disables the cap.
_DAILY_CAP_ENV = os.getenv("API_DAILY_PAID_OPERATION_CAP")
if _DAILY_CAP_ENV is None:
    _DAILY_CAP_ENV = os.getenv("API_DAILY_RUN_CAP", "0")
DAILY_CAP = int(_DAILY_CAP_ENV)
_DAILY_LEDGER_SCHEMA_VERSION = 1
_DAILY_LEDGER_FILENAME = ".paid-operation-ledger.json"
_DAILY_LEDGER_OWNERLESS_KEY = "__ownerless__"

# Days a finished run is kept before it is deleted automatically. 0 (the
# default) keeps runs forever, which is right for local development where the
# outputs directory is the developer's own.
#
# A public deployment is a different situation. Reading a run needs only its
# id — that is the deliberate report-sharing model — so a link stays live for
# as long as the run does. An uploaded paper's bounded extraction is copied
# into that run contract, while the raw PDF is deleted immediately after
# successful extraction. Retention bounds the durable extraction and resulting
# assessment, and matters more once links are shareable rather than less.
RUN_RETENTION_DAYS = int(os.getenv("RUN_RETENTION_DAYS", "0"))

# Run directories are named <UTC timestamp>-<hex>; see create_run_id().
_RUN_ID_PATTERN = re.compile(r"\d{8}T\d{6}Z-[0-9a-f]+")

_CANCEL_MARKER = "cancelled.marker"

# Which access.owner_id() created this run, so list_runs() can scope the
# history each code holder sees to their own runs. Absent for BYOK runs and
# for any deployment with no code configured — both cases mean "no owner",
# not "everyone's owner", so those runs never appear in a filtered list.
_OWNER_FILE = ".owner"

_ARTIFACTS = {
    "report":  "commercialization_report.md",
    "scores":  "commercialization_scores.json",
    "sources": "validated_sources.json",
    "notes":   "reviewer_notes.md",
    "steps":   "steps.jsonl",
    # Downloadable so a reader can see *which* claims the screen could not
    # check, not only how many. The counts alone invite the wrong reading —
    # a low ungrounded count next to a high unverifiable one means the check
    # mostly could not run, which is a different thing from mostly passing.
    "grounding": "claim_grounding.json",
    "consistency": "consistency.json",
    # Present only when collection failed before validated_sources.json could
    # exist; preserves the search plan, candidate counts, and rejection audit.
    "retrieval": "retrieval_diagnostics.json",
    "gap-shadow": "evidence_gap_shadow.json",
    "report-audit": "report_audit.json",
    "terminal": "terminal.json",
}


# Environment variables that spend the operator's money or point a key at a
# host the visitor did not choose. Every one is neutralized before a BYOK
# subprocess starts, and only the visitor's own values are put back. Explicit
# empty sentinels prevent an import-time dotenv load from restoring a secret.
#
# Overriding the three keys was not enough, because none of these three
# mechanisms goes through the key that was overridden:
#
#   TAVILY_API_KEY   default_web_search_client() prefers Tavily whenever it is
#                    set, so the visitor's Serper key was never once used and
#                    every BYOK search came out of the operator's Tavily quota.
#   OPENAI_API_BASE  create_llm() reads the base URL from the environment while
#                    taking the api_key from the visitor. llm_config documents
#                    a supported setup where this points at DeepSeek — under
#                    which a visitor choosing "openai" had their own OpenAI key
#                    sent to api.deepseek.com. That is not a quota question.
#   *_MODEL          the visitor pays for whichever model the operator named.
#
#: Neutralized for a BYOK run: billed to the operator, or able to redirect
#: the visitor's key somewhere they did not choose. Empty sentinels are kept
#: so provider imports cannot repopulate them from the project's .env file.
_OPERATOR_BILLED_ENV: frozenset[str] = frozenset({
    "LLM_PROVIDER",
    "DEEPSEEK_API_KEY", "DEEPSEEK_API_BASE", "DEEPSEEK_MODEL",
    "OPENAI_API_KEY", "OPENAI_API_BASE", "OPENAI_MODEL", "OPENAI_MODEL_NAME",
    "DASHSCOPE_API_KEY", "QWEN_API_BASE", "QWEN_MODEL",
    "ANTHROPIC_API_KEY", "ANTHROPIC_API_BASE", "ANTHROPIC_MODEL",
    "SERPER_API_KEY", "TAVILY_API_KEY",
    "LENS_API_KEY", "OPENALEX_API_KEY",
})

#: Kept for a BYOK run. These are free-tier keys that raise a rate limit
#: rather than incur a charge, and the visitor has no way to supply their own —
#: stripping them would make BYOK runs measurably worse (PubMed drops from 10
#: to 3 requests/second) to honour a promise about cost that they do not cost
#: anything against. Listed explicitly, not by omission, so the distinction is
#: a decision on the record rather than an oversight.
_FREE_TO_SHARE_ENV: frozenset[str] = frozenset({
    "NCBI_API_KEY",             # PubMed rate limit; free to obtain
    "SEMANTIC_SCHOLAR_API_KEY", # same, for Semantic Scholar
})


@dataclass(frozen=True)
class BYOKCredentials:
    """A visitor's own LLM + Serper keys, for a run billed to them, not us.

    Scoped to a single subprocess via an explicit `env=` dict passed to
    Popen — never written to disk, never merged into this process's own
    os.environ, so one BYOK run cannot leak its key to another concurrent
    run (BYOK or not) and does not persist past the subprocess it was built
    for.
    """

    llm_provider: str
    llm_api_key: str
    serper_api_key: str

    def as_env(self, base: dict[str, str]) -> dict[str, str]:
        """The subprocess environment for this run: scrubbed, then filled in.

        Scrubbed first and injected second, deliberately. Copying the operator's
        environment and overriding three names left every other paid credential
        in place, and the search client, the LLM base URL and the model name are
        all chosen from names that were not among the three — see
        _OPERATOR_BILLED_ENV. Empty sentinels keep dotenv from restoring those
        names inside the child; a provider added later is therefore excluded by
        default rather than included by default.
        """
        # Keep an empty sentinel for every scrubbed name. CrewAI imports
        # python-dotenv as a side effect in the child process; deleting a name
        # would let that import repopulate the operator's real .env value after
        # this boundary had apparently removed it.
        env = dict(base)
        for name in _OPERATOR_BILLED_ENV:
            env[name] = ""
        env["LLM_PROVIDER"] = self.llm_provider

        # Most providers use PROVIDER_API_KEY, but Alibaba's public contract
        # names the credential DASHSCOPE_API_KEY. An explicit map keeps a new
        # provider fail-closed instead of inventing a name that create_llm
        # never reads and silently falling back to operator state.
        key_names = {
            "deepseek": "DEEPSEEK_API_KEY",
            "qwen": "DASHSCOPE_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }
        try:
            key_name = key_names[self.llm_provider]
        except KeyError as exc:
            raise ValueError(
                f"Unsupported BYOK LLM provider: {self.llm_provider!r}"
            ) from exc
        env[key_name] = self.llm_api_key
        env["SERPER_API_KEY"] = self.serper_api_key
        return env


class _PendingProcess:
    """Stands in for a subprocess that is being launched.

    Occupies a concurrency slot from the moment it is reserved until the real
    Popen replaces it, so a burst of submissions cannot all pass the cap check
    while their processes are still starting. Reports itself as alive for that
    reason; terminate() is a no-op because there is nothing to signal yet.
    """

    def poll(self) -> None:
        return None

    def terminate(self) -> None:
        return None

    def kill(self) -> None:
        return None

    def wait(self, timeout: float | None = None) -> int:
        return 0


@dataclass
class _Handle:
    """A live worker process tracked by the API."""

    run_id: str
    topic: str
    proc: subprocess.Popen
    started: float = field(default_factory=time.monotonic)
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    log_file: object = None
    #: Billed to the visitor rather than the operator, and therefore capped
    #: separately -- see BYOK_MAX_CONCURRENT.
    byok: bool = False

    @property
    def elapsed(self) -> int:
        return int(time.monotonic() - self.started)

    def alive(self) -> bool:
        return self.proc.poll() is None

    def terminate(self) -> str:
        """Terminate, then kill if needed, returning the observed method."""
        method = "already_exited"
        if self.proc.poll() is None:
            method = "terminate"
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                method = "kill"
                self.proc.kill()
                self.proc.wait(timeout=5)
        if self.log_file is not None:
            try:
                self.log_file.close()
            except OSError:
                pass
        return method


class ConcurrencyLimitReached(Exception):
    """Raised when the active-run cap would be exceeded."""


class DailyCapReached(Exception):
    """Raised when the day's operator-funded paid-operation budget is exhausted."""


class PaidLedgerUnavailable(OSError):
    """Raised when the daily wallet ledger cannot be read or committed safely."""


class OwnerMarkerUnreadable(OSError):
    """Raised when persisted ownership cannot be distinguished from ownerless."""


class RunNotFound(Exception):
    """Raised for an unknown run_id."""


class RunStillActive(Exception):
    """Raised when delete_run is asked to remove a run that has not stopped."""


class RunNotResumable(Exception):
    """Raised when a run has no safe checkpoint recovery contract."""


_registry: dict[str, _Handle] = {}

# Inline paid operations live in the API process rather than a subprocess, so
# they cannot be represented by _Handle without making cancellation, polling
# and run history lie. The opaque token exists only for the duration of the
# context manager; the bool records whether it consumes the BYOK share.
_inline_paid_operations: dict[object, bool] = {}

# In-process cache of the durable UTC-day ledger. The atomic file survives an
# application restart, closing the easiest way to reset a leaked code's wallet
# cap. _registry_lock makes read/check/write one decision inside this process;
# it is deliberately not described as a distributed lock. Multiple replicas
# still need one external transactional store. Keys are already one-way owner
# ids, and BYOK is exempt before this ledger is consulted.
_daily_counts: dict[str | None, int] = {}
_daily_date: date | None = None

# Guards the worker registry, inline reservations, and daily accounting as one
# admission decision. FastAPI executes sync endpoints in a thread pool and PDF
# extraction in asyncio.to_thread, so check-and-reserve must be atomic across
# both paths. Reentrant because admission reaps finished worker handles.
_registry_lock = threading.RLock()


def active_count() -> int:
    """Number of runs still executing. Reaps finished handles as a side effect."""
    with _registry_lock:
        for run_id in [rid for rid, h in _registry.items() if not h.alive()]:
            h = _registry.pop(run_id, None)
            if h and h.log_file is not None:
                try:
                    h.log_file.close()
                except OSError:
                    pass
        return len(_registry)


def active_byok_count() -> int:
    """Live runs billed to a visitor's own key. Reaps first, via active_count,
    so a finished run cannot keep holding a slot it no longer occupies."""
    active_count()
    with _registry_lock:
        return sum(1 for h in _registry.values() if h.byok)


def _active_paid_operation_count_locked() -> int:
    """Live worker runs plus inline LLM calls; caller holds _registry_lock."""
    return active_count() + len(_inline_paid_operations)


def _active_byok_paid_operation_count_locked() -> int:
    """The BYOK share across both execution paths; caller holds the lock."""
    return active_byok_count() + sum(_inline_paid_operations.values())


def capacity_counts() -> tuple[int, int]:
    """Atomic (worker runs, all paid operations) capacity snapshot."""
    with _registry_lock:
        active_runs = active_count()
        return active_runs, active_runs + len(_inline_paid_operations)


def active_paid_operation_count() -> int:
    """Current worker runs plus inline provider calls sharing the host cap."""
    return capacity_counts()[1]


def _daily_ledger_path() -> Path:
    """Location follows DEFAULT_OUTPUT_ROOT so tests and deployments share policy."""
    return DEFAULT_OUTPUT_ROOT / _DAILY_LEDGER_FILENAME


def _read_daily_ledger_locked(today: date) -> dict[str | None, int]:
    """Load the active counts; malformed state fails closed before a paid call."""
    path = _daily_ledger_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        raise PaidLedgerUnavailable(
            "The paid-operation ledger is unreadable."
        ) from exc

    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != _DAILY_LEDGER_SCHEMA_VERSION
        or not isinstance(payload.get("date"), str)
    ):
        raise PaidLedgerUnavailable(
            "The paid-operation ledger has an unsupported format."
        )
    if payload["date"] != today.isoformat():
        return {}

    encoded_counts = payload.get("counts")
    if not isinstance(encoded_counts, dict):
        raise PaidLedgerUnavailable("The paid-operation ledger counts are invalid.")

    counts: dict[str | None, int] = {}
    for encoded_owner, count in encoded_counts.items():
        if (
            not isinstance(encoded_owner, str)
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
        ):
            raise PaidLedgerUnavailable(
                "The paid-operation ledger contains an invalid entry."
            )
        owner = (
            None
            if encoded_owner == _DAILY_LEDGER_OWNERLESS_KEY
            else encoded_owner
        )
        counts[owner] = count
    return counts


def validate_paid_ledger() -> None:
    """Validate enabled accounting state without changing admission caches.

    Readiness must consult the file directly even after this process cached a
    valid day. Otherwise an operator could replace or corrupt the ledger and
    the deployment would keep claiming it can admit paid work until restart.
    A missing ledger is the expected first-boot state and therefore valid.
    """
    if not DAILY_CAP:
        return
    with _registry_lock:
        _read_daily_ledger_locked(datetime.now(UTC).date())


def _write_daily_ledger_locked(today: date) -> None:
    """Atomically commit the cached counts before provider work is admitted."""
    path = _daily_ledger_path()
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    encoded_counts = {
        (_DAILY_LEDGER_OWNERLESS_KEY if owner is None else owner): count
        for owner, count in _daily_counts.items()
        if count > 0
    }
    payload = {
        "schema_version": _DAILY_LEDGER_SCHEMA_VERSION,
        "date": today.isoformat(),
        "counts": encoded_counts,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise PaidLedgerUnavailable(
            "The paid-operation ledger could not be committed."
        ) from exc
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            # A committed ledger or the admission failure above is the useful
            # outcome; an unreferenced temporary file must not replace it.
            pass


def _charge_daily_ledger_locked(owner: str | None, charged_on: date) -> None:
    """Increment durably, rolling memory back when the commit fails."""
    previous = _daily_counts.get(owner, 0)
    _daily_counts[owner] = previous + 1
    try:
        _write_daily_ledger_locked(charged_on)
    except PaidLedgerUnavailable:
        if previous:
            _daily_counts[owner] = previous
        else:
            _daily_counts.pop(owner, None)
        raise


def _daily_window_locked() -> date:
    """Load today's durable ledger once per process; caller holds the lock."""
    global _daily_date
    today = datetime.now(UTC).date()
    if _daily_date != today:
        counts = _read_daily_ledger_locked(today)
        _daily_counts.clear()
        _daily_counts.update(counts)
        # Publish the cache date only after a successful read. A corrupt
        # ledger must be retried and remain fail-closed on every admission.
        _daily_date = today
    return today


def _admit_paid_operation_locked(*, owner: str | None, byok: bool) -> date | None:
    """Check every limit and charge one operation atomically.

    The returned date identifies an operator-funded charge that can be
    refunded only if a worker process fails to launch. Once an inline
    extraction begins, an exception cannot prove that the provider was never
    reached, so that attempt remains charged even though its concurrency slot
    is always released.
    """
    charged_on: date | None = None
    if not byok and DAILY_CAP:
        charged_on = _daily_window_locked()
        owner_count = _daily_counts.get(owner, 0)
        if owner_count >= DAILY_CAP:
            raise DailyCapReached(
                f"Daily limit reached: {DAILY_CAP} operator-funded paid "
                "operations already admitted today"
            )

    active = _active_paid_operation_count_locked()
    if active >= MAX_CONCURRENT:
        raise ConcurrencyLimitReached(
            f"{active} of {MAX_CONCURRENT} concurrent paid operations in use"
        )

    if byok:
        active_byok = _active_byok_paid_operation_count_locked()
        if active_byok >= byok_limit():
            raise ConcurrencyLimitReached(
                f"{active_byok} of {byok_limit()} concurrent bring-your-own-key "
                "paid operations in use; the remaining capacity is reserved "
                "for access-code holders"
            )

    if charged_on is not None:
        _charge_daily_ledger_locked(owner, charged_on)
    return charged_on


def _refund_daily_charge_locked(
    owner: str | None, charged_on: date | None
) -> bool:
    """Persist a safe pre-provider refund; False means the charge remains."""
    if charged_on is None or _daily_date != charged_on:
        return True
    remaining = _daily_counts.get(owner, 0)
    if remaining <= 0:
        return True
    if remaining == 1:
        _daily_counts.pop(owner, None)
    else:
        _daily_counts[owner] = remaining - 1
    try:
        _write_daily_ledger_locked(charged_on)
    except PaidLedgerUnavailable:
        # Do not replace the worker-launch exception with a refund error.
        # Restore memory to the still-charged durable state and tell the
        # caller to emit an operator-visible diagnostic.
        _daily_counts[owner] = remaining
        return False
    return True


@contextmanager
def reserve_inline_paid_operation(
    *, owner: str | None, byok: bool
) -> Iterator[None]:
    """Reserve one shared slot for an in-process provider call.

    Concurrency is released in finally on success, cancellation, or failure.
    Daily accounting deliberately is not: after the extractor starts, this
    layer cannot know whether a failed provider request was billed.
    """
    token = object()
    with _registry_lock:
        _admit_paid_operation_locked(owner=owner, byok=byok)
        _inline_paid_operations[token] = byok
    try:
        yield
    finally:
        with _registry_lock:
            _inline_paid_operations.pop(token, None)


def run_dir_for(run_id: str) -> Path:
    return DEFAULT_OUTPUT_ROOT / run_id


def _is_valid_run_id(run_id: str) -> bool:
    """Reject anything that could escape the outputs directory."""
    return (
        bool(run_id)
        and "/" not in run_id
        and "\\" not in run_id
        and ".." not in run_id
        and run_id == Path(run_id).name
    )


def _start_run_from_spec(
    spec: RunSpec,
    *,
    byok: BYOKCredentials | None = None,
    owner: str | None = None,
    resume_from: str | None = None,
) -> tuple[str, Path]:
    """Launch a worker subprocess. Returns (run_id, run_dir).

    `byok`, if given, is billed to the requester, not the deployment — so it
    is exempt from the daily cap, which exists only to bound the operator's
    own bill. The concurrency cap still applies to every run regardless of
    who is paying: it protects host resources, not a wallet.

    BYOK runs are additionally bounded by BYOK_MAX_CONCURRENT. Being exempt
    from the daily cap otherwise let anonymous traffic hold every slot — and
    a submission with a wrong key holds one while it fails — so the visitors
    who cost the operator nothing could shut out the code holders the
    deployment exists for.

    `owner` is the access.owner_id() of whichever code authorized this run —
    None for BYOK (and for a deployment with no code configured at all). Also
    what DAILY_CAP is scoped by: each owner gets their own budget, not one
    pool every code holder draws from together. Written to the run directory
    so list_runs() can show each code holder only the runs made under their
    own code.
    """
    # Claim the wallet budget and the shared provider/host slot in one atomic
    # step. The placeholder remains visible while the slow filesystem and
    # subprocess launch happen outside the lock, so a concurrent PDF
    # extraction cannot slip through the same slot.
    run_id = create_run_id()
    charged_on: date | None = None
    with _registry_lock:
        charged_on = _admit_paid_operation_locked(
            owner=owner, byok=byok is not None
        )
        try:
            _registry[run_id] = _Handle(
                run_id=run_id, topic=spec.topic, proc=_PendingProcess(), log_file=None,
                byok=byok is not None,
            )
        except BaseException:
            if not _refund_daily_charge_locked(owner, charged_on):
                print(
                    "[api] paid-operation refund could not be persisted; charge retained",
                    file=sys.stderr,
                )
            raise

    run_dir = run_dir_for(run_id)

    # Any failure from here on must release the reserved slot, or the cap
    # leaks permanently: a placeholder counts as alive and nothing else
    # removes it. This has to start at run_dir.mkdir, not just the Popen
    # call below — a mkdir failure (e.g. an unwritable outputs volume) is
    # exactly the kind of failure this guards against, and one that left
    # outside the boundary leaked a slot per attempt with no way to clear
    # it short of restarting the process.
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        spec_path = spec.save(run_dir)
        if owner is not None:
            (run_dir / _OWNER_FILE).write_text(owner, encoding="utf-8")
        if resume_from is not None:
            # Snapshot before Popen. The source can be deleted manually or by
            # retention while the child is starting; making the worker read
            # it later would turn a valid recovery request into a race. The
            # child copy contains only manifests and non-secret outputs.
            if not _is_valid_run_id(resume_from):
                raise RunNotFound(f"Invalid run id: {resume_from!r}")
            source_directory = run_dir_for(resume_from).resolve(strict=True)
            output_root = DEFAULT_OUTPUT_ROOT.resolve()
            if source_directory.parent != output_root:
                raise RunNotFound(f"No run with id {resume_from}")
            source_checkpoints = (source_directory / "checkpoints").resolve(strict=True)
            if source_checkpoints.parent != source_directory:
                raise OSError("Source checkpoint directory escaped its run directory.")
            snapshot_root = run_dir / RESUME_SNAPSHOT_DIRECTORY
            shutil.copytree(source_checkpoints, snapshot_root / "checkpoints")


        # One deadline travels to both the worker and the parent reaper. The
        # monotonic handle remains authoritative here; the wall value is
        # converted once by the child so clock changes cannot extend it.
        worker_started = time.monotonic()
        worker_started_at = datetime.now(UTC)
        hard_deadline_epoch = time.time() + TIMEOUT_SECONDS
        cmd = [
            sys.executable, "-m", "academic_agent.pipeline_worker",
            run_id, spec.topic, "--run-spec", str(spec_path),
            "--hard-deadline-epoch", repr(hard_deadline_epoch),
            "--hard-timeout-seconds", str(TIMEOUT_SECONDS),
        ]
        # Keep the explicit flags for CLI/process introspection and backwards
        # compatibility, while RunSpec remains the worker's authoritative
        # contract. The worker verifies and then overwrites these values from
        # the frozen spec, so duplicated argv cannot cause identity drift.
        if spec.language is not None:
            cmd += ["--language", spec.language]
        if spec.weight_profile is not None:
            cmd += ["--weight-profile", spec.weight_profile]

        if resume_from is not None:
            # The id remains provenance; the worker reads the immutable local
            # snapshot above rather than racing the source directory.
            cmd += ["--resume-from", resume_from]

        # BYOK credentials travel as env, never as argv: command-line arguments
        # are visible to any other process on the same host via `ps`/the process
        # list, which a shared or multi-tenant deployment cannot rule out.
        env = byok.as_env(os.environ) if byok is not None else None

        log_file = open(run_dir / "process.log", "w", encoding="utf-8")
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=log_file, env=env)
        except BaseException:
            log_file.close()
            raise
    except BaseException:
        with _registry_lock:
            _registry.pop(run_id, None)
            # No worker exists, so no LLM/search provider could have been
            # reached. Unlike a failed running worker, this attempt is safe
            # to refund rather than silently consuming the user's day.
            if not _refund_daily_charge_locked(owner, charged_on):
                print(
                    "[api] paid-operation refund could not be persisted; charge retained",
                    file=sys.stderr,
                )
        raise

    with _registry_lock:
        # byok has to be carried across: this replaces the placeholder handle
        # reserved above, and dropping the flag here would clear it the moment
        # the process actually started — so the limit would only ever see runs
        # that had not launched yet, which is to say none of them.
        _registry[run_id] = _Handle(
            run_id=run_id, topic=spec.topic, proc=proc, log_file=log_file,
            started=worker_started,
            started_at=worker_started_at,
            byok=byok is not None,
        )
    return run_id, run_dir

def _spec_from_submission(
    topic: str,
    language: str | None,
    weight_profile: str | None,
    paper_json_path: str | None,
    decision_context: DecisionContext | None,
) -> RunSpec:
    """Freeze a submission before reserving money or starting its worker."""

    paper_contribution = None
    if paper_json_path is not None:
        path = Path(paper_json_path)
        if not path.is_file():
            raise OSError(f"Paper contribution no longer exists: {path.name}")
        try:
            candidate = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OSError(f"Could not read paper contribution: {exc}") from exc
        if not isinstance(candidate, dict):
            raise OSError("Paper contribution must be a JSON object.")
        paper_contribution = candidate

    return RunSpec(
        topic=topic,
        language=language,
        weight_profile=weight_profile,
        paper_contribution=paper_contribution,
        decision_context=decision_context,
    )


def start_run(
    topic: str,
    language: str | None = None,
    weight_profile: str | None = None,
    paper_json_path: str | None = None,
    decision_context: DecisionContext | None = None,
    byok: BYOKCredentials | None = None,
    owner: str | None = None,
) -> tuple[str, Path]:
    """Launch a new worker from a durable, non-secret input contract."""

    spec = _spec_from_submission(
        topic,
        language,
        weight_profile,
        paper_json_path,
        decision_context,
    )
    return _start_run_from_spec(spec, byok=byok, owner=owner)


def resume_run(
    source_run_id: str,
    *,
    byok: BYOKCredentials | None = None,
    owner: str | None = None,
) -> tuple[str, Path]:
    """Launch an immutable child run that may reuse the source's checkpoints.

    The failed source directory is never rewritten.  That preserves the crash
    evidence and avoids a restarted worker racing a reader of the original
    capability URL.  The child receives fresh credentials through the normal
    subprocess boundary and copies each reused checkpoint into its own run.
    """

    if not _is_valid_run_id(source_run_id):
        raise RunNotFound(f"Invalid run id: {source_run_id!r}")
    source_directory = run_dir_for(source_run_id)
    if not source_directory.is_dir():
        raise RunNotFound(f"No run with id {source_run_id}")

    state = get_state(source_run_id)["state"]
    if state not in {"failed", "cancelled", "timeout"}:
        if state == "running":
            raise RunNotResumable("A running assessment cannot be resumed.")
        if state == "completed":
            raise RunNotResumable("A completed assessment has no unfinished work to resume.")
        raise RunNotResumable(
            "An assessment with unreadable state cannot be resumed safely."
        )

    try:
        spec = RunSpec.load(source_directory)
    except (OSError, ValueError) as exc:
        raise RunNotResumable(
            "This run predates durable input contracts or its contract is unreadable."
        ) from exc

    # Retrieval is the root of every task identity.  Starting a paid child
    # without an intact commit could only produce a full rerun while claiming
    # to be recovery. Existence alone is insufficient: a truncated manifest or
    # missing content-addressed payload used to pass this endpoint, consume a
    # daily charge, and reach the worker before being discovered as corrupt.
    retrieval = CheckpointStore(source_directory).inspect_existing("retrieval")
    if retrieval.state != "reusable" or retrieval.manifest is None:
        raise RunNotResumable(
            "This run has no intact retrieval checkpoint to resume."
        )

    # Bind the root checkpoint to the durable input contract before admitting
    # paid work. Revision and date are intentionally left to the worker: a
    # valid-but-stale checkpoint is an explicit cold start, while a checkpoint
    # copied from another input is not evidence that this run can be resumed.
    if retrieval.manifest.identity.input_sha256 != hash_json(spec):
        raise RunNotResumable(
            "The retrieval checkpoint does not match this run's input contract."
        )

    return _start_run_from_spec(
        spec,
        byok=byok,
        owner=owner,
        resume_from=source_run_id,
    )


def cancel_run(run_id: str) -> None:
    """Terminate a live run and mark it cancelled."""
    # Removed under the lock so two concurrent cancels cannot both decide the
    # run is theirs to terminate.
    with _registry_lock:
        handle = _registry.get(run_id)
        if handle is None or not handle.alive():
            raise RunNotFound(f"No live run with id {run_id}")
        _registry.pop(run_id, None)
    method = handle.terminate()
    try:
        (run_dir_for(run_id) / _CANCEL_MARKER).write_text(
            datetime.now(UTC).isoformat(), encoding="utf-8"
        )
    except OSError:
        # The directory can vanish here if a concurrent delete_run() call for
        # the same id already popped this handle's twin registration and won
        # the race to remove it — see delete_run's docstring. Nothing left to
        # mark at that point is a fine outcome, not a failure to report.
        pass
    try:
        _commit_external_terminal(
            handle,
            state="cancelled",
            reason_code="user_cancelled",
            termination_method=method,
            timeout_seconds=TIMEOUT_SECONDS,
        )
    except (OSError, ValueError) as exc:
        # The legacy marker still preserves cancellation if the stronger
        # audit record cannot be committed; never turn cancel into HTTP 500.
        print(f"[api] terminal record failed for {run_id}: {exc}", file=sys.stderr)



def delete_run(run_id: str) -> None:
    """Permanently remove a finished run's directory and every artifact in it.

    Refuses a run that is still active — cancel_run() first — so a delete
    can never pull the filesystem out from under a subprocess still writing
    to it. The registry check and the active-run rejection happen under the
    lock together so a run that starts finishing mid-call cannot slip
    through between the two.
    """
    if not _is_valid_run_id(run_id):
        raise RunNotFound(f"Invalid run id: {run_id!r}")

    run_dir = run_dir_for(run_id)
    if not run_dir.is_dir():
        raise RunNotFound(f"No run with id {run_id}")

    with _registry_lock:
        handle = _registry.get(run_id)
        if handle is not None and handle.alive():
            raise RunStillActive(f"Run {run_id} is still active — cancel it first")
        _registry.pop(run_id, None)

    shutil.rmtree(run_dir)


def reap_timeouts() -> list[str]:
    """Kill runs past the deadline. Returns the run_ids that were killed."""
    killed: list[str] = []
    # Claim each expired run under the lock before terminating it, so a
    # concurrent cancel_run cannot terminate the same handle twice.
    with _registry_lock:
        expired = [
            (rid, h) for rid, h in _registry.items()
            if h.alive() and h.elapsed > TIMEOUT_SECONDS
        ]
        for run_id, _handle in expired:
            _registry.pop(run_id, None)

    for run_id, handle in expired:
        method = handle.terminate()
        if method == "already_exited":
            # It won the race with the watchdog; do not relabel it timeout.
            continue
        try:
            (run_dir_for(run_id) / "error.log").write_text(
                f"Analysis timed out after {TIMEOUT_SECONDS // 60} minutes.",
                encoding="utf-8",
            )
        except OSError:
            # The immutable record below is authoritative; this text file is
            # retained only for compatibility with historical readers.
            pass
        try:
            _commit_external_terminal(
                handle,
                state="timeout",
                reason_code="hard_timeout",
                termination_method=method,
                timeout_seconds=TIMEOUT_SECONDS,
            )
        except (OSError, ValueError) as exc:
            # One damaged run directory must not stop the global reaper.
            print(
                f"[api] terminal record failed for {run_id}: {exc}",
                file=sys.stderr,
            )
        killed.append(run_id)
    return killed


def shutdown_all() -> None:
    """Terminate every live run. Called on application shutdown."""
    with _registry_lock:
        handles = list(_registry.values())
        _registry.clear()
    for handle in handles:
        handle.terminate()


class StatusUnreadable(Exception):
    """status.json exists but cannot be read as a usable progress object.

    Distinct from "not written yet", which is an empty dict and means the run
    has only just started. Conflating them made a torn read look like a run
    that had produced no status at all, which get_state() derives as failed.
    """


def _read_status(run_dir: Path) -> dict:
    """The run's status, or {} when it has not been written yet.

    Raises StatusUnreadable for a file that is present but unparseable. The
    worker now writes atomically so this should not happen from a torn read,
    but a truncated file on a full disk still must not be reported as a
    failed run — the run may have finished perfectly.
    """
    return _read_status_snapshot(run_dir)[0]


def _read_status_snapshot(run_dir: Path) -> tuple[dict, str]:
    """Classify absence during the read, not with a racy second exists() call.

    Keep legacy optional fields optional. This validates the container and
    outcome flags, not every historical nested audit schema. In particular,
    JSON null/arrays are parseable but cannot support .get(), and the string
    "false" must not become a truthy completion flag. Do not repair stored
    bytes while serving a capability URL.
    """
    path = run_dir / "status.json"
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}, "absent"
    except (OSError, UnicodeError):
        raise StatusUnreadable(str(path)) from None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise StatusUnreadable(f"{path}: {exc}") from exc
    if (
        not isinstance(data, dict)
        or ("done" in data and not isinstance(data["done"], bool))
        or (data.get("error") is not None and not isinstance(data["error"], str))
    ):
        raise StatusUnreadable(f"{path}: invalid progress container or outcome flags")
    return data, "readable"


def _external_usage_accounting(
    status: dict,
    *,
    ended_at: datetime,
) -> UsageAccounting:
    """Classify the last worker snapshot after an external process stop.

    Even a durable snapshot is only a lower bound: the killed request may
    have reached the provider before its usage counters returned. No snapshot
    is reported as unavailable, never as zero.
    """

    usage = status.get("usage")
    has_trustworthy_snapshot = (
        isinstance(usage, dict) and not usage.get("collection_error")
    )
    return UsageAccounting(
        state="lower_bound" if has_trustworthy_snapshot else "unavailable",
        snapshot_at=ended_at,
        through_stage=str(status.get("stage") or ""),
        run_complete=False,
        in_flight_request_may_have_spent=True,
    )


def _commit_external_terminal(
    handle: _Handle,
    *,
    state: str,
    reason_code: str,
    termination_method: str,
    timeout_seconds: int | None,
) -> None:
    """Persist facts the stopped worker can no longer record itself."""

    run_dir = run_dir_for(handle.run_id)
    try:
        status = _read_status(run_dir)
    except StatusUnreadable:
        # Terminal state remains knowable even when the last live projection
        # is damaged. Its missing stage/usage must stay unavailable rather
        # than preventing the stronger process outcome from being committed.
        status = {}
    ended_at = datetime.now(UTC)
    accounting = _external_usage_accounting(status, ended_at=ended_at)
    record = TerminalRecord(
        state=state,
        reason_code=reason_code,
        termination_method=termination_method,
        started_at=handle.started_at,
        ended_at=ended_at,
        elapsed_seconds=handle.elapsed,
        last_stage=str(status.get("stage") or ""),
        timeout_seconds=timeout_seconds,
        usage=status.get("usage"),
        usage_accounting=accounting,
        checkpointing=status.get("checkpointing"),
        recovery=status.get("recovery"),
    )
    commit_terminal_record(run_dir, record)


def _read_terminal(run_dir: Path) -> tuple[TerminalRecord | None, dict | None]:
    """Return a valid record and its projection, or an explicit unreadable state."""

    try:
        record = load_terminal_record(run_dir)
    except TerminalRecordUnreadable:
        return None, {"record_state": "unreadable"}
    if record is None:
        return None, None
    return record, record.public_projection()


def read_steps(run_id: str, since: int = 0) -> list[dict]:
    """Step events from steps.jsonl, skipping the first `since` entries.

    The worker appends to this file while running, so a partially written
    trailing line is normal and is skipped rather than treated as corruption.
    """
    if not _is_valid_run_id(run_id):
        raise RunNotFound(f"Invalid run id: {run_id!r}")

    path = run_dir_for(run_id) / "steps.jsonl"
    if not path.exists():
        return []

    events: list[dict] = []
    try:
        with path.open(encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if index < since:
                    continue
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue      # the writer is mid-line; it will be there next poll
    except OSError:
        return []
    return events


def _failure_reason(run_dir: Path) -> str:
    """Best internal explanation for a run that did not complete.

    This text comes from provider responses and worker stderr. It stays in
    the run directory for operators and must pass through
    _public_failure_reason() before crossing an HTTP response boundary.
    """
    try:
        msg = (run_dir / "error.log").read_text(encoding="utf-8", errors="replace").strip()
        if msg:
            return msg[:800]
    except OSError:
        pass
    try:
        log = (run_dir / "process.log").read_text(encoding="utf-8", errors="replace").strip()
        if log:
            return log[-800:]
    except OSError:
        pass
    return ""


_TIMEOUT_FAILURE_MARKERS = ("timed out", "timeout", "deadline exceeded")
_PUBLIC_FAILURE_CATEGORIES: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        _TIMEOUT_FAILURE_MARKERS,
        "The analysis exceeded its time limit. Retry with a narrower topic.",
    ),
    (
        (
            "invalid api key",
            "incorrect api key",
            "authentication failed",
            "authentication error",
            "unauthorized",
            "error code: 401",
        ),
        "An upstream provider rejected authentication. "
        "Check the configured credentials.",
    ),
    (
        (
            "rate limit",
            "rate_limit",
            "insufficient_quota",
            "quota exceeded",
            "error code: 429",
        ),
        "An upstream provider rate or quota limit was reached. Retry later.",
    ),
    (
        (
            "validated sources",
            "sourcecollectionerror",
            "source collection",
            "retrieval produced",
        ),
        "The system could not collect enough validated evidence for this topic. "
        "Retry later or refine the topic.",
    ),
    (
        (
            "response_format",
            "failed to convert text into a pydantic model",
            "not json serializable",
            "jsondecodeerror",
            "invalid json",
        ),
        "An upstream model returned an unsupported response format. "
        "Retry the analysis.",
    ),
    (
        (
            "guardrail",
            "blocking validation errors",
            "evidence validation failed",
            "final report validation failed",
        ),
        "The generated analysis did not pass the evidence-quality checks. "
        "Retry the analysis.",
    ),
    (
        (
            "connection error",
            "connection refused",
            "connection reset",
            "network error",
            "name resolution",
            "temporarily unavailable",
            "service unavailable",
        ),
        "An upstream service could not be reached. Retry later.",
    ),
)


def _is_timeout_failure(raw_reason: object) -> bool:
    lowered = str(raw_reason).lower()
    return any(marker in lowered for marker in _TIMEOUT_FAILURE_MARKERS)


def _public_failure_reason(raw_reason: object) -> str:
    """Map untrusted diagnostics to a stable client-safe category.

    Error artifacts remain untouched for operator debugging. Returning only
    allowlisted prose here prevents provider bodies, credentials, prompts,
    and host paths from being reflected by status and list endpoints.
    """
    lowered = str(raw_reason).lower()
    for markers, message in _PUBLIC_FAILURE_CATEGORIES:
        if any(marker in lowered for marker in markers):
            return message
    return "The analysis failed. Retry or contact the operator with the run ID."


def artifact_names() -> list[str]:
    """Every artifact name the API can serve, whether or not a given run has it."""
    return sorted(_ARTIFACTS)


def available_artifacts(run_dir: Path) -> list[str]:
    return [name for name, fname in _ARTIFACTS.items() if (run_dir / fname).exists()]


def artifact_path(run_id: str, name: str) -> Path | None:
    """Resolve an artifact name to a path, or None if unknown/missing.

    Validates run_id itself rather than trusting the caller. Both current
    callers happen to call get_state() first, which rejects a traversing id —
    so this function was safe by call order rather than by construction, and a
    new endpoint that resolved an artifact directly would have reintroduced the
    traversal. The filename is already confined by the _ARTIFACTS allowlist.
    """
    if not _is_valid_run_id(run_id):
        return None
    fname = _ARTIFACTS.get(name)
    if fname is None:
        return None
    path = run_dir_for(run_id) / fname
    return path if path.exists() else None


def get_state(run_id: str) -> dict:
    """Derive the full state of a run from disk plus the live registry."""
    if not _is_valid_run_id(run_id):
        raise RunNotFound(f"Invalid run id: {run_id!r}")

    run_dir = run_dir_for(run_id)
    if not run_dir.is_dir():
        raise RunNotFound(f"No run with id {run_id}")

    try:
        status, status_record_state = _read_status_snapshot(run_dir)
    except StatusUnreadable:
        # Report what is known rather than guessing. "unknown" is a state a
        # client can retry; "failed" is one it reports to the user.
        status, status_record_state = {}, "unreadable"
    status, audit_metadata_unreadable = project_audit_metadata(status)
    terminal_record, terminal_projection = _read_terminal(run_dir)
    handle = _registry.get(run_id)

    if handle is not None and handle.alive():
        state = "running"
        error = None
        elapsed = handle.elapsed
    else:
        if terminal_record is not None:
            elapsed = terminal_record.elapsed_seconds
            state = terminal_record.state
            if state == "cancelled":
                error = "Cancelled by request."
            elif state == "timeout":
                error = (
                    "The analysis exceeded its time limit. Resume from the "
                    "last validated checkpoint or start a new run."
                )
            elif state == "failed":
                error = _public_failure_reason(status.get("error") or _failure_reason(run_dir))
            else:
                error = None
        elif terminal_projection is not None:
            # A damaged write-once outcome is not a historical run that never
            # had one. Falling through to done/error/cancel markers invents a
            # definitive result from the weaker mutable projection.
            state, elapsed = "unknown", None
            error = "Run terminal record is unreadable; the outcome cannot be verified."
        else:
            # Historical runs have no terminal record. Preserve their legacy
            # derivation without mistaking status mtime for new-run truth.
            elapsed = _elapsed_seconds(run_dir)
            if (run_dir / _CANCEL_MARKER).exists():
                state, error = "cancelled", "Cancelled by request."
            elif status.get("error"):
                state, error = "failed", _public_failure_reason(status["error"])
            elif status.get("done"):
                state, error = "completed", None
            elif status_record_state == "unreadable":
                state = "unknown"
                elapsed = None
                error = ("Run status is temporarily unreadable; the run itself may "
                         "have completed. Retry in a moment.")
            else:
                reason = _failure_reason(run_dir)
                state = "timeout" if _is_timeout_failure(reason) else "failed"
                error = _public_failure_reason(reason)

    usage = status.get("usage")
    usage_accounting = status.get("usage_accounting")
    checkpointing = status.get("checkpointing")
    recovery = status.get("recovery")
    if terminal_record is not None:
        # None is an authoritative unavailable observation too. Rehydrating
        # it from a mutable live file would silently resurrect stale counters.
        usage = terminal_record.usage
        usage_accounting = terminal_record.usage_accounting.model_dump(mode="json")
        # None means the optional terminal snapshot was not recorded. A
        # present empty/broken object is NOT permission to resurrect stale
        # mutable claims about checkpoint persistence or successful reuse.
        if terminal_record.checkpointing is not None:
            checkpointing = terminal_record.checkpointing
        if terminal_record.recovery is not None:
            recovery = terminal_record.recovery
    elif terminal_projection is not None or status_record_state == "unreadable":
        # A readable node snapshot is still useful, but a damaged outcome
        # cannot certify its completeness. Keep the observation and its known
        # timestamp; never fabricate an end time from the reader's wall clock.
        # An unreadable projection supplies no measurement, not a zero bill.
        usage = usage if isinstance(usage, dict) and not usage.get("collection_error") else None
        usage_accounting = {
            "state": "lower_bound" if usage is not None else "unavailable",
            "snapshot_at": usage_accounting.get("snapshot_at") if isinstance(usage_accounting, dict) else None,
            "through_stage": str(status.get("stage") or ""),
            "run_complete": False,
            "in_flight_request_may_have_spent": True,
        }
    # Validate only the selected runtime view: a valid immutable snapshot can
    # legitimately shadow a damaged live one. This does not rewrite either
    # record or change the process outcome derived above.
    runtime, runtime_metadata_unreadable = project_runtime_metadata({
        "usage": usage, "usage_accounting": usage_accounting,
        "checkpointing": checkpointing, "recovery": recovery,
    })

    return {
        "run_id": run_id,
        "state": state,
        "status_record_state": status_record_state,
        "audit_metadata_unreadable": audit_metadata_unreadable,
        "runtime_metadata_unreadable": runtime_metadata_unreadable,
        "stage": status.get("stage") or (terminal_record.last_stage if terminal_record else ""),
        "topic": status.get("topic") or (handle.topic if handle else ""),
        "output_language": status.get("output_language") or "English",
        # This is the immutable identity persisted by the executing worker.
        # Never backfill it from the live API process: an old run served after
        # a deploy would otherwise be attributed to code that never executed it.
        # None therefore means unknown (principally historical runs), not the
        # current deployment.
        "pipeline_revision": status.get("pipeline_revision"),
        "decision_gate": status.get("decision_gate"),
        "error": error,
        "elapsed_seconds": elapsed,
        "source_counts": status.get("source_counts"),
        # True when the run finished but its per-agent evidence files could not
        # be written. The report is still valid; what is missing is the record
        # of how sources became findings — which is precisely what someone
        # checking a citation would open. Surfaced rather than logged so that
        # gap is visible to whoever reads the report, not only to whoever reads
        # the server's stderr.
        "evidence_incomplete": bool(status.get("evidence_incomplete")),
        # Domains whose retrieval backend failed, so the assessment was made
        # without them. An empty domain otherwise reads as a finding about the
        # technology rather than an outage.
        "failed_domains": list(status.get("failed_domains") or []),
        # Tokens and estimated cost, per agent and in total. Present once the
        # crew has run, including on failed runs — a run that died halfway
        # still spent whatever it spent, and that is the case where the number
        # is least guessable and most worth showing.
        "usage": runtime["usage"],
        # Temporal completeness is independent of price completeness. A
        # lower-bound token total can still have a complete price table.
        "usage_accounting": runtime["usage_accounting"],
        "runtime_budget": status.get("runtime_budget"),
        "terminal": terminal_projection,
        # Counts from the claim-grounding screen: how many quantitative claims
        # could be checked against the text of the sources they cite, how many
        # cited a figure absent from it, and how many could not be checked at
        # all because the retrieved source text is a fragment. The third
        # number is the honest one to read first — it bounds what the other
        # two can mean.
        "claim_grounding": status.get("claim_grounding"),
        # Applicable clinical topics need both regulator and trial-registry
        # evidence. Missing coverage is distinct from a search-domain outage:
        # the search ran, but its bounded accepted set lacks an authority class.
        # It is deliberately advisory so a temporary registry gap does not
        # discard a paid report.
        "authority_coverage": status.get("authority_coverage"),
        # A combined topic can retrieve abundant evidence for one component
        # while silently missing another. This advisory field exposes that
        # bounded-set coverage without turning it into an absence claim.
        "component_coverage": status.get("component_coverage"),
        # Zero-call phase-1 eligibility audit. None means the run predates the
        # feature; disabled, checked, and failed states remain explicit inside
        # the object so an unperformed planner never reads as a passing check.
        "evidence_gap_shadow": status.get("evidence_gap_shadow"),
        # A narrow, advisory post-generation screen. Its status distinguishes
        # no applicable segment, partial coverage, failure, and a completed
        # check; absence is reserved for historical runs.
        "report_audit": status.get("report_audit"),

        # Review is a separate model pass after the draft's deterministic
        # validation. A fallback remains a completed run, but it must not look
        # indistinguishable from an inspection that actually happened.
        "quality_review": status.get("quality_review"),

        # Where the report's own advice disagrees with its own
        # scorecard. Nothing in the pipeline compares them: the
        # reviewer never sees the scorecard, the scorer never sees
        # the reviewed report.
        "consistency": status.get("consistency"),
        # Optional OTLP projection. Its state distinguishes disabled, active,
        # and degraded; delivery="attempted" deliberately does not claim the
        # collector persisted a span because OTLP gives this process no such
        # acknowledgement.
        "observability": status.get("observability"),
        # Persisting a node and reusing it are different claims. Both remain
        # explicit so a failed auxiliary write cannot look like successful
        # recovery, and a cold start cannot look like a cache hit simply
        # because checkpointing itself was healthy.
        "checkpointing": runtime["checkpointing"],
        "recovery": runtime["recovery"],
        "artifacts": available_artifacts(run_dir),
    }


def _started_at(run_id: str) -> str:
    try:
        stamp = run_id.split("-")[0]
        dt = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        return dt.isoformat()
    except ValueError:
        return ""


def _elapsed_seconds(run_dir: Path) -> int | None:
    """Wall-clock seconds for a finished run, from what is on disk.

    The run_id encodes the start; status.json's mtime is the last thing the
    worker wrote. Used for runs whose handle is gone, where the in-memory
    timer is no longer available.
    """
    terminal_record, projection = _read_terminal(run_dir)
    if terminal_record is not None:
        return terminal_record.elapsed_seconds
    if projection is not None:
        return None

    # Historical runs fall back to the last live-status write timestamp.
    try:
        stamp = run_dir.name.split("-")[0]
        start = datetime.strptime(stamp, "%Y%m%dT%H%M%SZ").replace(tzinfo=UTC)
        status_path = run_dir / "status.json"
        if not status_path.exists():
            return None
        end = datetime.fromtimestamp(os.path.getmtime(status_path), tz=UTC)
        secs = int((end - start).total_seconds())
        return secs if secs >= 0 else None
    except (ValueError, OSError):
        return None


def _duration(run_dir: Path) -> str:
    try:
        return _format_duration(_elapsed_seconds(run_dir))
    except (ValueError, OSError):
        return "—"


def _format_duration(secs: int | None) -> str:
    if secs is None:
        return "—"
    return f"{secs}s" if secs < 60 else f"{secs // 60}m {secs % 60:02d}s"


def prune_expired_runs(retention_days: int | None = None) -> list[str]:
    """Delete runs older than the retention window. Returns the ids removed.

    Age is taken from the run id's own timestamp rather than the directory's
    mtime: reading a run rewrites nothing, but generating its PDF on first
    download does, and mtime would silently grant an extension to exactly the
    runs someone had been opening.

    Never touches a live run: a worker is still writing into that directory,
    and its id is in the registry regardless of how old the id looks — which
    matters for a run that outlived the window while executing.

    Best-effort, like the paper pruning it runs beside: a directory that
    cannot be removed is skipped rather than raising, because this is called
    from a timer whose failure would take the reaper down with it.
    """
    days = RUN_RETENTION_DAYS if retention_days is None else retention_days
    if days <= 0 or not DEFAULT_OUTPUT_ROOT.is_dir():
        return []

    cutoff = datetime.now(UTC) - timedelta(days=days)
    with _registry_lock:
        live = {rid for rid, h in _registry.items() if h.alive()}

    removed: list[str] = []
    for directory in DEFAULT_OUTPUT_ROOT.iterdir():
        if not directory.is_dir() or not _RUN_ID_PATTERN.fullmatch(directory.name):
            continue
        if directory.name in live:
            continue
        try:
            stamp = datetime.strptime(
                directory.name.split("-")[0], "%Y%m%dT%H%M%SZ"
            ).replace(tzinfo=UTC)
        except ValueError:
            continue
        if stamp >= cutoff:
            continue
        try:
            shutil.rmtree(directory)
        except OSError:
            continue
        removed.append(directory.name)
    return removed


def _read_owner(run_dir: Path) -> str | None:
    marker = run_dir / _OWNER_FILE
    if not marker.exists():
        return None
    try:
        owner = marker.read_text(encoding="utf-8").strip()
    except OSError as exc:
        # The absence of a marker deliberately means an ownerless BYOK/local
        # run. An unreadable marker says ownership could not be established;
        # collapsing those cases lets a storage fault erase authorization.
        raise OwnerMarkerUnreadable("Run ownership metadata is unreadable") from exc
    if not owner:
        # A partially written or externally damaged marker is not evidence
        # that the original run was ownerless. Fail closed for the same reason
        # as a read error instead of converting corruption into permission.
        raise OwnerMarkerUnreadable("Run ownership metadata is empty")
    return owner


def owner_of(run_id: str) -> str | None:
    """The access.owner_id() that created this run, or None if it has no owner.

    None covers a BYOK/local run (deliberately untagged) and a run directory
    that does not exist. Callers deciding authorization still check existence
    separately. A marker that exists but cannot be read raises instead of
    becoming None, because that conversion would fail open at mutation routes.
    """
    if not _is_valid_run_id(run_id):
        return None
    return _read_owner(run_dir_for(run_id))


def list_runs(limit: int = 50, owner: str | None = None) -> tuple[list[dict], int]:
    """Return (summaries, total) for finished and running runs, newest first.

    `owner`, when given, scopes the result to runs created under that same
    access.owner_id() — a code holder sees only their own history, not
    every code's combined. None means no filter: every run, the behaviour
    for a deployment with no access code configured at all.
    """
    if not DEFAULT_OUTPUT_ROOT.is_dir():
        return [], 0

    # Match the run_id shape rather than excluding known non-runs one at a
    # time. The old rule skipped only "benchmark", so adding outputs/_papers
    # for uploads immediately put a storage directory in the run list, where
    # it rendered as a run with no topic and no status.
    dirs = sorted(
        (d for d in DEFAULT_OUTPUT_ROOT.iterdir()
         if d.is_dir() and _RUN_ID_PATTERN.fullmatch(d.name)),
        key=lambda d: d.name,
        reverse=True,
    )
    if owner is not None:
        dirs = [d for d in dirs if _read_owner(d) == owner]
    summaries = []
    for d in dirs[:limit]:
        try:
            projection = get_state(d.name)
        except RunNotFound:
            continue
        summaries.append({
            "run_id": d.name,
            "state": projection["state"],
            "topic": projection["topic"] or "—",
            "started_at": _started_at(d.name),
            # Do not re-read the raw status after get_state handled a storage
            # fault: that second read used to turn one bad row into HTTP 500
            # for the entire owner's history. The same snapshot owns duration.
            "duration": _format_duration(projection["elapsed_seconds"]),
            # Not part of RunSummary — the API layer strips this back out
            # for everyone except an admin request, which resolves it to a
            # readable code via access.label_for_owner() first. Included
            # unconditionally here because this function has no notion of
            # "admin"; that decision belongs to the caller, not this layer.
            "_owner": _read_owner(d),
        })
    return summaries, len(dirs)
