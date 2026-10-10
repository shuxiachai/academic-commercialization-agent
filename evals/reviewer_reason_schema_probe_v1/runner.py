"""Default identity-only entry point and bounded parent-owned dispatch.

No production imports. Native output is exclusive, immutable and non-resumable.
Never invoke --live without a new explicit grant for the final private identity.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from decimal import Decimal
from pathlib import Path

from evals.reviewer_reason_schema_probe_v1 import core

STDOUT_LIMIT = 256 * 1024
STDERR_LIMIT = 8192
SLOT_SECONDS = 90
BATCH_SECONDS = 270
EXIT_SECONDS = 5
DRAIN_SECONDS = 10


def clean_environment() -> dict:
    # No inherited credential, proxy, Python startup or application configuration.
    return {name: os.environ[name] for name in ("SystemRoot", "WINDIR", "PATH") if name in os.environ}


def run_child(command: list[str], deadline: float, cwd: Path) -> tuple[dict, bytes]:
    """Observe a real process plus both pipes; cleanup has its own bounded clock.

    This is process ownership, not an OS sandbox or remote request cancellation.
    The deadline is established before Popen, and includes startup/key reading.
    """
    observed = {"state": "startup_unavailable", "physical_exit": False, "pipes_drained": False,
                "stdout_bytes": 0, "stderr_bytes": 0}
    if time.monotonic() >= deadline:
        observed["state"] = "deadline_before_start"
        return observed, b""
    overflow = threading.Event()
    captures = [bytearray(), bytearray()]
    counts = [0, 0]
    read_errors = [False, False]

    def drain(index, pipe, limit):
        try:
            while True:
                chunk = pipe.read(4096)
                if not chunk:
                    break
                counts[index] += len(chunk)
                captures[index].extend(chunk[:max(0, limit + 1 - len(captures[index]))])
                if counts[index] > limit:
                    overflow.set()
        except OSError:
            read_errors[index] = True
            overflow.set()
        finally:
            pipe.close()

    readers = []
    started_readers = []
    reason = "completed"
    interrupted = None
    try:
        process = subprocess.Popen(command, cwd=cwd, env=clean_environment(), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except OSError:
        return observed, b""
    pipes = (process.stdout, process.stderr)
    try:
        observed["pid"] = process.pid
        readers = [threading.Thread(target=drain, args=(i, pipe, limit), daemon=True)
                   for i, (pipe, limit) in enumerate(zip(pipes, (STDOUT_LIMIT, STDERR_LIMIT), strict=True))]
        for reader in readers:
            reader.start()
            started_readers.append(reader)
        while True:
            if overflow.is_set():
                reason = "pipe_bound_or_read_fault"
                break
            if time.monotonic() >= deadline:
                reason = "deadline_exceeded"
                break
            if process.poll() is not None and not any(reader.is_alive() for reader in started_readers):
                break
            overflow.wait(min(0.01, max(0, deadline - time.monotonic())))
    except Exception:  # noqa: BLE001 -- retain process ownership after supervisor/thread startup faults.
        reason = "supervisor_fault"
    except BaseException as exc:
        interrupted = exc
        reason = "supervisor_interrupted"
    finally:
        # Ownership begins at successful Popen, including failed reader startup.
        # Cleanup uses one exit window and one drain window; no exception from
        # the observing loop may leave a child running without a reap attempt.
        exit_deadline = time.monotonic() + EXIT_SECONDS
        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
            try:
                process.wait(timeout=max(0, exit_deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except OSError:
                    pass
        drain_deadline = time.monotonic() + DRAIN_SECONDS
        if process.poll() is None:
            try:
                process.wait(timeout=max(0, drain_deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                pass
        for reader in started_readers:
            reader.join(timeout=max(0, drain_deadline - time.monotonic()))
        for pipe in pipes[len(started_readers):]:
            pipe.close()  # No reader existed: close is cleanup, not observed EOF.
    observed.update(physical_exit=process.poll() is not None,
                    pipes_drained=len(started_readers) == 2 and not any(reader.is_alive() for reader in started_readers),
                    stdout_bytes=counts[0], stderr_bytes=counts[1], returncode=process.returncode)
    if not observed["physical_exit"] or not observed["pipes_drained"]:
        reason = "drain_unconfirmed"
    elif any(read_errors) or overflow.is_set():
        reason = "pipe_bound_or_read_fault"
    elif process.returncode != 0 and reason == "completed":
        reason = "worker_exit_failed"
    elif counts[1] and reason == "completed":
        reason = "unexpected_stderr"
    observed["state"] = reason
    if interrupted is not None:
        raise interrupted
    # Invalid/noisy pipes are not persisted, hashed or printed: they may be secret.
    return observed, bytes(captures[0]) if reason == "completed" else b""


def require_committed(root: Path) -> None:
    git = root / ".git"
    if git.is_file():
        git = (root / core.read_bounded(git, 4096).decode().strip()[8:]).resolve()
    prefix = ["git", "--no-pager", "--git-dir=" + str(git), "--work-tree=" + str(root)]
    commands = [prefix + ["ls-files", "--error-unmatch", "--", *core.SOURCE_FILES],
                prefix + ["diff", "--no-ext-diff", "--quiet", "HEAD", "--", *core.SOURCE_FILES]]
    for command in commands:
        result = subprocess.run(command, cwd=root, env=clean_environment(), stdin=subprocess.DEVNULL,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False)
        if result.returncode != 0:
            raise core.ProbeError("source_not_committed")


def dispatch(packet_path: Path, grant_path: Path, expected: str, expected_commit: str,
             root: Path = core.ROOT) -> dict:
    observed = core.identity(packet_path, root)
    if observed["identity"] != expected or observed["commit"] != expected_commit:
        raise core.ProbeError("identity_changed")
    grant_hash = core.validate_grant(grant_path, observed, root)
    require_committed(root)
    output = root / "outputs" / core.NATIVE_OUTPUT
    output.mkdir(exist_ok=False)  # An occupied batch never means resume or retry.
    core.durable_new(output / "identity.json", core.canonical(observed))
    summary = {"schema": "reviewer-reason-schema-batch-v1", "identity": expected,
               "status": "unavailable", "reserved_cny": "0", "known_estimated_cny": "0",
               "reservation_policy": "never_reclaimed", "cases": []}
    batch_start = time.monotonic()
    continuing = True
    for case in core.CASES:
        if not continuing:
            summary["cases"].append(core.empty_observation(case, "not_run"))
            continue
        slot_start = time.monotonic()
        deadline = min(slot_start + SLOT_SECONDS, batch_start + BATCH_SECONDS)
        result = core.empty_observation(case)
        try:
            # Re-check immediately before every durable reservation. Worker repeats
            # this after startup, so a changed packet/body cannot spend the slot.
            if core.identity(packet_path, root) != observed:
                raise core.ProbeError("identity_changed")
            if time.monotonic() >= deadline:
                raise core.ProbeError("deadline_before_reservation")
            reservation = {"schema": "reviewer-reason-schema-reservation-v1", "case": case,
                           "identity": expected, "grant_sha256": grant_hash,
                           "body_sha256": observed["bodies"][case]["sha256"],
                           "reserved_cny": core.RESERVATION_CNY}
            core.durable_new(output / (case + ".request.json"), core.request_body(case, root))
            core.durable_new(output / (case + ".reservation.json"), core.canonical(reservation))
            summary["reserved_cny"] = str(Decimal(summary["reserved_cny"]) + Decimal(core.RESERVATION_CNY))
            if Decimal(summary["reserved_cny"]) > Decimal(core.BATCH_SOFT_CNY):
                raise core.ProbeError("reservation_limit")
            command = [sys.executable, "-I", "-S", "-B", str(root / core.SOURCE_FILES[3]), "--live",
                       "--packet", str(packet_path.resolve()), "--grant", str(grant_path.resolve()),
                       "--expected-identity", expected, "--case", case]
            process, raw = run_child(command, deadline, root)
            if process["state"] == "completed":
                candidate = core.strict_json(raw)
                # Worker output is code-owned; unexpected output is withheld.
                if (not isinstance(candidate, dict) or candidate.get("case") != case
                        or type(candidate.get("continue")) is not bool
                        or not isinstance(candidate.get("usage"), dict)):
                    raise core.ProbeError("worker_output_invalid")
                result = candidate
            result["process"] = process
            if process["state"] != "completed":
                result["failure"] = process["state"]
                result["continue"] = False
            if time.monotonic() > deadline:
                result.update(disposition="observation_unavailable", failure="deadline_exceeded")
                result["continue"] = False
            if result["usage"]["state"] in ("known", "over_estimate"):
                summary["known_estimated_cny"] = str(Decimal(summary["known_estimated_cny"])
                                                    + Decimal(result["usage"]["estimated_cny"]))
            if Decimal(summary["known_estimated_cny"]) > Decimal(core.BATCH_SOFT_CNY):
                result["continue"] = False
                result["failure"] = "cost_soft_stop"
            core.durable_new(output / (case + ".observation.json"), core.canonical(result))
            continuing = result["continue"] and result["usage"]["state"] == "known"
        except Exception:  # noqa: BLE001 -- persistence/parse failures seal the batch without raw exceptions.
            result["continue"] = False
            result["disposition"] = "observation_unavailable"
            result["failure"] = "preflight_or_evidence_persistence_failed"
            continuing = False
        summary["cases"].append(result)
    if continuing and len(summary["cases"]) == 3:
        summary["status"] = "observed_small_contract_compatibility"
    try:
        core.durable_new(output / "summary.json", core.canonical(summary))
    except OSError:
        summary["status"] = "evidence_persistence_failed"
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--grant", type=Path)
    parser.add_argument("--expected-identity")
    parser.add_argument("--expected-commit")
    args = parser.parse_args(argv)
    try:
        if not args.live:
            observed = core.identity(args.packet)
            # Identity digests also stay local; exact endpoint/path are never echoed.
            print(core.canonical({"mode": "identity_only", "native_execution": "not_run",
                                  "credential_reads": 0, "identity": observed["identity"],
                                  "source_identity": observed["source_identity"],
                                  "commit": observed["commit"], "bodies": observed["bodies"]}).decode())
            return 0
        if not args.grant or not args.expected_identity or not args.expected_commit:
            raise core.ProbeError("live_bindings_missing")
        result = dispatch(args.packet, args.grant, args.expected_identity, args.expected_commit)
        print(core.canonical({"status": result["status"], "cases": [
            {"case": row["case"], "disposition": row["disposition"]} for row in result["cases"]]}).decode())
        return 0 if result["status"] == "observed_small_contract_compatibility" else 1
    except Exception:  # noqa: BLE001 -- CLI never exposes raw config, key paths or provider exceptions.
        print('{"status":"unavailable","detail":"identity_grant_output_or_runtime_gate_failed"}')
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
