"""Run the pre-registered zero-network checkpoint fault-recovery audit.

The public command is plan-only unless ``--execute`` is present.  Study units
launch the real pipeline worker in separate processes, but replace retrieval,
telemetry, and model execution with deterministic local doubles.  This keeps
the test on the worker/checkpoint/status seams without making a provider call
or adding a fault-injection switch to the production API.

See ``docs/prereg-2026-08-23-checkpoint-fault-recovery.md`` before changing the
fixture set, fault matrix, or pass criteria.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final
from unittest.mock import patch

from academic_agent.checkpoint_runtime import TASK_NODES
from academic_agent.run_spec import RESUME_SNAPSHOT_DIRECTORY, RUN_SPEC_FILENAME


SCHEMA_VERSION: Final[int] = 1
DEFAULT_FIXTURES_ROOT: Final[Path] = Path("outputs/benchmark")
DEFAULT_OUTPUT_ROOT: Final[Path] = Path(
    "outputs/checkpoint-fault-audit/20260823-offline-v1"
)
FROZEN_FIXTURES: Final[tuple[tuple[str, str], ...]] = (
    (
        "01-car-t-cell-therapy-for-blood-cancers",
        "e17a716a4a4d25a26e0292b9317b3c81db3a3c7c0b9d49a22806c48f56ce6a98",
    ),
    (
        "02-mrna-vaccines-for-cancer-immunotherapy",
        "f3380e820d4eccb4a2761f9b203266fb5e965332860f3ae707c0bcf01ef563d1",
    ),
    (
        "03-solid-state-batteries-for-electric-vehicles",
        "6ff31da36946834ac69d1151eb54845f770f0b8b5ac4820b15cc0a397ca8558f",
    ),
    (
        "04-perovskite-solar-cells-for-utility-scale-powe",
        "58b39151921a8a9ec5446c908d028b8b030f79b3b7da1d737853a3099b3abdf0",
    ),
    (
        "05-crispr-gene-editing-for-genetic-diseases",
        "a0bd1aefe3e91d171cacc6252cf2a3a6d9f096485c88f30ce519fc4447a83a18",
    ),
    (
        "06-carbon-capture-and-storage-for-industrial-emi",
        "6f541afb495a4657f73c3aa8566afb135c5cc59df1e9f0fd96c5819de7e8185a",
    ),
    (
        "07-cultivated-meat-for-food-industry",
        "bd7b7086c71bea82384167ce872172ac5697f12aa74bc705d08a9e8bbb48237c",
    ),
    (
        "08-quantum-computing-for-drug-discovery",
        "efc02a138bc6e7201cb2430bb5547d266fcbd43fdd19aaab1a5a953d980acb66",
    ),
    (
        "09-graphene-based-flexible-electronics",
        "0929309d40c3e957274facaaa7c85744a5f3393898748ebf1f6b5f679f40999d",
    ),
    (
        "10-room-temperature-ambient-pressure-superconduc",
        "a6b0486565c3fddcc672028ddbd2e1eb6878b02d453223a39993665c47b94b96",
    ),
)


@dataclass(frozen=True)
class FaultScenario:
    """One post-commit process-kill boundary frozen by the pre-registration."""

    scenario_id: str
    fault_after: str
    prefix_count: int

    @property
    def expected_prefix(self) -> tuple[str, ...]:
        return tuple(TASK_NODES[: self.prefix_count])

    @property
    def expected_suffix(self) -> tuple[str, ...]:
        return tuple(TASK_NODES[self.prefix_count :])


SCENARIOS: Final[tuple[FaultScenario, ...]] = (
    FaultScenario("after_academic", "academic", 1),
    FaultScenario("after_market", "market", 3),
    FaultScenario("after_reviewer", "reviewer", 5),
)
_SCENARIO_BY_ID: Final[dict[str, FaultScenario]] = {
    scenario.scenario_id: scenario for scenario in SCENARIOS
}


@dataclass(frozen=True)
class Fixture:
    """One verified historical SourceCollection used only as worker input."""

    fixture_id: str
    path: Path
    sha256: str
    topic: str


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_sha256(root: Path) -> str:
    """Hash relative names and bytes so a moved parent remains comparable."""

    if not root.is_dir():
        raise FileNotFoundError(f"tree does not exist: {root}")
    digest = hashlib.sha256()
    files = sorted(path for path in root.rglob("*") if path.is_file())
    for path in files:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        payload = path.read_bytes()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(payload).to_bytes(8, "big"))
        digest.update(payload)
    return digest.hexdigest()


def _atomic_write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


def discover_fixtures(root: Path) -> list[Fixture]:
    """Load the exact frozen inputs; never substitute a convenient repeat."""

    fixtures: list[Fixture] = []
    errors: list[str] = []
    for fixture_id, expected_sha256 in FROZEN_FIXTURES:
        path = root / fixture_id / "validated_sources.json"
        if not path.is_file():
            errors.append(f"{fixture_id}: missing validated_sources.json")
            continue
        actual_sha256 = _sha256_file(path)
        if actual_sha256 != expected_sha256:
            errors.append(
                f"{fixture_id}: sha256 {actual_sha256} != frozen {expected_sha256}"
            )
            continue
        payload = _read_json_object(path)
        topic = payload.get("topic") if payload is not None else None
        if not isinstance(topic, str) or not topic.strip():
            errors.append(f"{fixture_id}: missing non-empty topic")
            continue
        fixtures.append(
            Fixture(
                fixture_id=fixture_id,
                path=path.resolve(),
                sha256=actual_sha256,
                topic=topic.strip(),
            )
        )
    if errors:
        raise ValueError("Frozen fixture validation failed:\n- " + "\n- ".join(errors))
    return fixtures


def _frozen_contract() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "fixtures": [
            {"fixture_id": fixture_id, "sha256": digest}
            for fixture_id, digest in FROZEN_FIXTURES
        ],
        "scenarios": [
            {
                "scenario_id": scenario.scenario_id,
                "fault_after": scenario.fault_after,
                "expected_prefix": list(scenario.expected_prefix),
                "expected_suffix": list(scenario.expected_suffix),
            }
            for scenario in SCENARIOS
        ],
        "expected_units": len(FROZEN_FIXTURES) * len(SCENARIOS),
    }


def build_plan(fixtures: list[Fixture]) -> dict[str, Any]:
    return {
        "mode": "plan_only",
        "network_calls": 0,
        "model_calls": 0,
        "fixture_count": len(fixtures),
        "scenario_count": len(SCENARIOS),
        "unit_count": len(fixtures) * len(SCENARIOS),
        "fixtures": [
            {
                "fixture_id": fixture.fixture_id,
                "topic": fixture.topic,
                "sha256": fixture.sha256,
            }
            for fixture in fixtures
        ],
        "scenarios": [
            {
                "scenario_id": scenario.scenario_id,
                "fault_after": scenario.fault_after,
                "expected_reused_tasks": list(scenario.expected_prefix),
                "expected_executed_tasks": list(scenario.expected_suffix),
            }
            for scenario in SCENARIOS
        ],
    }


class _OfflineTelemetry:
    """No-op trace object that makes network isolation explicit in the worker."""

    def span(self, *_args: Any, **_kwargs: Any):
        return nullcontext()

    def set_attributes(self, _attributes: dict[str, Any]) -> None:
        return None

    def finish(self, _error: BaseException | None = None) -> None:
        return None

    def snapshot(self) -> dict[str, Any]:
        return {"state": "disabled", "reason": "offline_checkpoint_fault_audit"}


def _task_output(node: str):
    from crewai.tasks.task_output import OutputFormat as CrewOutputFormat
    from crewai.tasks.task_output import TaskOutput

    raw = (
        json.dumps(
            {"node": node, "findings": [], "audit_payload": True},
            sort_keys=True,
        )
        if node in {"academic", "patent", "market", "scorer"}
        else f"# {node.title()}\n\nValidated offline checkpoint audit output."
    )
    return TaskOutput(
        description=f"{node} description",
        expected_output=f"{node} expected",
        raw=raw,
        agent=f"{node} agent",
        output_format=(
            CrewOutputFormat.JSON
            if node in {"academic", "patent", "market", "scorer"}
            else CrewOutputFormat.RAW
        ),
    )


def _offline_tasks() -> list[Any]:
    from crewai.tasks.task_output import OutputFormat as CrewOutputFormat

    # The identity deliberately looks like a provider but has no credential or
    # callable LLM. If the fake executor is bypassed, the unit fails rather than
    # falling through to an accidentally configured model in the environment.
    llm = SimpleNamespace(
        provider="offline-audit",
        model="deterministic-checkpoint-double-v1",
        base_url="offline://checkpoint-fault-audit",
        temperature=0,
        response_format=None,
    )
    tasks: list[Any] = []
    for node in TASK_NODES:
        agent = SimpleNamespace(
            role=f"{node} agent",
            goal=f"return deterministic {node} output",
            backstory="Offline process fault-injection double.",
            inject_date=False,
            allow_delegation=False,
            tools=[],
            llm=llm,
        )
        tasks.append(
            SimpleNamespace(
                description=f"{node} description",
                expected_output=f"{node} expected",
                async_execution=node in {"academic", "patent", "market"},
                context=[],
                guardrail=object(),
                guardrail_max_retries=1,
                output_json=None,
                output_pydantic=None,
                output_format=(
                    CrewOutputFormat.JSON
                    if node in {"academic", "patent", "market", "scorer"}
                    else CrewOutputFormat.RAW
                ),
                agent=agent,
                tools=[],
                callback=None,
                output=None,
            )
        )
    tasks[3].context = tasks[:3]
    tasks[4].context = tasks[:4]
    tasks[5].context = tasks[:3]
    return tasks


class _OfflineCrew:
    """Executor double that honours CrewAI's hydrated-output skip boundary."""

    def __init__(self, run_directory: Path, *, pause_after: str | None) -> None:
        self.tasks = _offline_tasks()
        self.agents = [task.agent for task in self.tasks]
        self.task_callback = None
        self.checkpoint_kickoff_event_id = None
        self.run_directory = run_directory
        self.pause_after = pause_after

    def _record_execution(self, node: str) -> None:
        # Record before the callback: this represents provider work having
        # occurred, while the later manifest represents durable validation.
        path = self.run_directory / "audit-executions.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"node": node}, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    def kickoff(self, *, inputs: dict[str, Any]) -> SimpleNamespace:
        del inputs
        for node, task in zip(TASK_NODES, self.tasks, strict=True):
            if task.output is not None:
                continue
            self._record_execution(node)
            output = _task_output(node)
            task.output = output
            if task.callback is not None:
                task.callback(output)
            if self.task_callback is not None and self.task_callback is not task.callback:
                self.task_callback(output)
            if node == self.pause_after:
                # The controller does the hard termination. Waiting here keeps
                # the process alive after the callback's manifest commit and
                # avoids turning this into a cooperative exception test.
                _atomic_write_json(
                    self.run_directory / "audit-fault-ready.json",
                    {"node": node, "ready_at": _utc_now()},
                )
                while True:
                    time.sleep(60)
        outputs = [task.output for task in self.tasks]
        return SimpleNamespace(tasks_output=outputs, raw=outputs[-1].raw)


def _offline_environment() -> dict[str, str]:
    """Strip credentials and exporters from audit subprocesses defensively."""

    environment = dict(os.environ)
    explicit = {
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "OPENAI_API_KEY",
        "PHOENIX_API_KEY",
        "PHOENIX_COLLECTOR_ENDPOINT",
        "SERPER_API_KEY",
    }
    for name in list(environment):
        if name in explicit or name.startswith("OTEL_"):
            environment.pop(name, None)
    environment["OTEL_SDK_DISABLED"] = "true"
    environment["PYTHONUTF8"] = "1"
    return environment


def _internal_worker_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--source-file", type=Path, required=True)
    parser.add_argument("--pause-after", choices=TASK_NODES)
    parser.add_argument("--resume-from")
    args = parser.parse_args(argv)

    from academic_agent.source_pipeline import SourceCollection

    source_collection = SourceCollection.model_validate_json(
        args.source_file.read_text(encoding="utf-8")
    )
    output_root = args.output_root.resolve()
    run_directory = output_root / args.run_id
    crew = _OfflineCrew(run_directory, pause_after=args.pause_after)
    worker_argv = ["pipeline_worker.py", args.run_id, source_collection.topic]
    if args.resume_from:
        worker_argv.extend(
            [
                "--resume-from",
                args.resume_from,
                "--run-spec",
                str(run_directory / RUN_SPEC_FILENAME),
            ]
        )

    def collection_double(*_args: Any, **_kwargs: Any) -> SourceCollection:
        if args.resume_from:
            raise AssertionError("resumed worker must reuse the retrieval checkpoint")
        return source_collection

    empty_usage = SimpleNamespace(agents=[], collection_error=None)
    with (
        patch.object(sys, "argv", worker_argv),
        patch("academic_agent.run_output.DEFAULT_OUTPUT_ROOT", output_root),
        patch(
            "academic_agent.source_pipeline.collect_source_collection",
            side_effect=collection_double,
        ),
        patch("academic_agent.crew.AcademicAgent") as agent_class,
        patch("academic_agent.token_usage.collect_usage", return_value=empty_usage),
        patch(
            "academic_agent.observability.start_run_telemetry",
            return_value=_OfflineTelemetry(),
        ),
    ):
        agent_class.return_value.crew.return_value = crew
        from academic_agent.pipeline_worker import main as worker_main

        worker_main()
    return 0


def _worker_command(
    *,
    output_root: Path,
    run_id: str,
    source_file: Path,
    pause_after: str | None = None,
    resume_from: str | None = None,
) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "_worker",
        "--output-root",
        str(output_root),
        "--run-id",
        run_id,
        "--source-file",
        str(source_file),
    ]
    if pause_after is not None:
        command.extend(["--pause-after", pause_after])
    if resume_from is not None:
        command.extend(["--resume-from", resume_from])
    return command


def _wait_for_sentinel(process: subprocess.Popen[str], sentinel: Path, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if sentinel.is_file():
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.05)
    return sentinel.is_file()


def _terminate(process: subprocess.Popen[str]) -> tuple[int | None, str, str]:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    stdout, stderr = process.communicate()
    return process.returncode, stdout, stderr


def _execution_nodes(run_directory: Path) -> list[str] | None:
    path = run_directory / "audit-executions.jsonl"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError, UnicodeError):
        return None
    nodes: list[str] = []
    try:
        for line in lines:
            value = json.loads(line)
            if not isinstance(value, dict) or not isinstance(value.get("node"), str):
                return None
            nodes.append(value["node"])
    except json.JSONDecodeError:
        return None
    return nodes


def _checkpoint_nodes(run_directory: Path) -> list[str]:
    return [
        node
        for node in ("retrieval", *TASK_NODES)
        if (run_directory / "checkpoints" / node / "manifest.json").is_file()
    ]


def _process_record(
    *,
    command: list[str],
    exit_code: int | None,
    stdout: str,
    stderr: str,
) -> dict[str, Any]:
    return {
        # Commands contain only audit paths and ids. Credentials were removed
        # from the environment and are never serialized into this record.
        "command": command,
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
    }


def _minimal_failed_record(
    fixture: Fixture,
    scenario: FaultScenario,
    unit_id: str,
    error: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "unit_id": unit_id,
        "fixture_id": fixture.fixture_id,
        "fixture_sha256": fixture.sha256,
        "topic": fixture.topic,
        "scenario_id": scenario.scenario_id,
        "fault_after": scenario.fault_after,
        "controller_error": error,
        "parent": None,
        "child": None,
        "passed": False,
        "failure_reasons": ["controller_error"],
    }


def run_fault_unit(
    *,
    unit_root: Path,
    fixture: Fixture,
    scenario: FaultScenario,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Execute one hard-kill/restart unit and persist its raw seam evidence."""

    unit_root.mkdir(parents=True, exist_ok=False)
    parent_id = "parent"
    child_id = "child"
    parent_directory = unit_root / parent_id
    child_directory = unit_root / child_id
    detached_parent = unit_root / "detached-parent"
    sentinel = parent_directory / "audit-fault-ready.json"
    target_manifest = (
        parent_directory
        / "checkpoints"
        / scenario.fault_after
        / "manifest.json"
    )
    parent_command = _worker_command(
        output_root=unit_root,
        run_id=parent_id,
        source_file=fixture.path,
        pause_after=scenario.fault_after,
    )
    parent_process = subprocess.Popen(
        parent_command,
        cwd=Path(__file__).resolve().parent,
        env=_offline_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    sentinel_observed = _wait_for_sentinel(
        parent_process, sentinel, timeout_seconds
    )
    target_manifest_exists = target_manifest.is_file()
    parent_exit, parent_stdout, parent_stderr = _terminate(parent_process)
    parent_process_record = _process_record(
        command=parent_command,
        exit_code=parent_exit,
        stdout=parent_stdout,
        stderr=parent_stderr,
    )
    _atomic_write_json(unit_root / "parent-process.json", parent_process_record)

    if not sentinel_observed or not target_manifest_exists:
        record = _minimal_failed_record(
            fixture,
            scenario,
            unit_root.name,
            "fault boundary was not reached before the parent stopped",
        )
        record["parent"] = {
            "process": parent_process_record,
            "sentinel_observed": sentinel_observed,
            "target_manifest_exists": target_manifest_exists,
            "execution_nodes": _execution_nodes(parent_directory),
            "checkpoint_manifest_nodes": _checkpoint_nodes(parent_directory),
        }
        record["failure_reasons"] = evaluate_unit(record)
        _atomic_write_json(unit_root / "unit.json", record)
        return record

    child_directory.mkdir()
    shutil.copy2(
        parent_directory / RUN_SPEC_FILENAME,
        child_directory / RUN_SPEC_FILENAME,
    )
    snapshot_checkpoints = (
        child_directory / RESUME_SNAPSHOT_DIRECTORY / "checkpoints"
    )
    shutil.copytree(parent_directory / "checkpoints", snapshot_checkpoints)

    parent_hash_before = _tree_sha256(parent_directory)
    parent_directory.rename(detached_parent)
    parent_path_absent_before_child = not parent_directory.exists()

    child_command = _worker_command(
        output_root=unit_root,
        run_id=child_id,
        source_file=fixture.path,
        resume_from=parent_id,
    )
    try:
        child_completed = subprocess.run(
            child_command,
            cwd=Path(__file__).resolve().parent,
            env=_offline_environment(),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        child_process_record = _process_record(
            command=child_command,
            exit_code=child_completed.returncode,
            stdout=child_completed.stdout,
            stderr=child_completed.stderr,
        )
    except subprocess.TimeoutExpired as exc:
        child_process_record = _process_record(
            command=child_command,
            exit_code=None,
            stdout=str(exc.stdout or ""),
            stderr=str(exc.stderr or "") + "\nchild timeout",
        )
    _atomic_write_json(unit_root / "child-process.json", child_process_record)

    parent_hash_after = _tree_sha256(detached_parent)
    parent_path_absent_after_child = not parent_directory.exists()
    parent_executions = _execution_nodes(detached_parent)
    child_executions = _execution_nodes(child_directory)
    duplicate_nodes = (
        sorted(set(parent_executions).intersection(child_executions))
        if parent_executions is not None and child_executions is not None
        else None
    )
    record = {
        "schema_version": SCHEMA_VERSION,
        "unit_id": unit_root.name,
        "fixture_id": fixture.fixture_id,
        "fixture_sha256": fixture.sha256,
        "topic": fixture.topic,
        "scenario_id": scenario.scenario_id,
        "fault_after": scenario.fault_after,
        "controller_error": None,
        "parent": {
            "process": parent_process_record,
            "sentinel_observed": sentinel_observed,
            "target_manifest_exists": target_manifest_exists,
            "execution_nodes": parent_executions,
            "checkpoint_manifest_nodes": _checkpoint_nodes(detached_parent),
            "tree_sha256_before_child": parent_hash_before,
            "tree_sha256_after_child": parent_hash_after,
            "original_path_absent_before_child": parent_path_absent_before_child,
            "original_path_absent_after_child": parent_path_absent_after_child,
        },
        "child": {
            "process": child_process_record,
            "execution_nodes": child_executions,
            "checkpoint_manifest_nodes": _checkpoint_nodes(child_directory),
            "status": _read_json_object(child_directory / "status.json"),
        },
        "duplicate_execution_nodes": duplicate_nodes,
    }
    reasons = evaluate_unit(record)
    record["passed"] = not reasons
    record["failure_reasons"] = reasons
    _atomic_write_json(unit_root / "unit.json", record)
    return record


def _expect_equal(
    reasons: list[str],
    label: str,
    actual: Any,
    expected: Any,
) -> None:
    if actual != expected:
        reasons.append(f"{label}: expected {expected!r}, got {actual!r}")


def evaluate_unit(record: dict[str, Any]) -> list[str]:
    """Recompute a unit verdict; never trust its persisted ``passed`` field."""

    reasons: list[str] = []
    scenario_id = record.get("scenario_id")
    scenario = _SCENARIO_BY_ID.get(scenario_id) if isinstance(scenario_id, str) else None
    if scenario is None:
        return [f"scenario_id: unknown {scenario_id!r}"]
    if record.get("controller_error") is not None:
        reasons.append(f"controller_error: {record.get('controller_error')}")

    parent = record.get("parent")
    child = record.get("child")
    if not isinstance(parent, dict):
        reasons.append("parent: missing or invalid")
        return reasons
    if not isinstance(child, dict):
        reasons.append("child: missing or invalid")
        return reasons

    expected_prefix = list(scenario.expected_prefix)
    expected_suffix = list(scenario.expected_suffix)
    expected_parent_checkpoints = ["retrieval", *expected_prefix]
    expected_all_checkpoints = ["retrieval", *TASK_NODES]
    _expect_equal(reasons, "fault_after", record.get("fault_after"), scenario.fault_after)
    _expect_equal(reasons, "parent.sentinel_observed", parent.get("sentinel_observed"), True)
    _expect_equal(
        reasons,
        "parent.target_manifest_exists",
        parent.get("target_manifest_exists"),
        True,
    )
    _expect_equal(reasons, "parent.execution_nodes", parent.get("execution_nodes"), expected_prefix)
    _expect_equal(
        reasons,
        "parent.checkpoint_manifest_nodes",
        parent.get("checkpoint_manifest_nodes"),
        expected_parent_checkpoints,
    )
    parent_process = parent.get("process")
    if not isinstance(parent_process, dict) or parent_process.get("exit_code") in {None, 0}:
        reasons.append("parent.process.exit_code: hard-terminated parent must be non-zero")
    _expect_equal(
        reasons,
        "parent.original_path_absent_before_child",
        parent.get("original_path_absent_before_child"),
        True,
    )
    _expect_equal(
        reasons,
        "parent.original_path_absent_after_child",
        parent.get("original_path_absent_after_child"),
        True,
    )
    before_hash = parent.get("tree_sha256_before_child")
    after_hash = parent.get("tree_sha256_after_child")
    if not isinstance(before_hash, str) or not before_hash:
        reasons.append("parent.tree_sha256_before_child: not checked")
    if not isinstance(after_hash, str) or not after_hash:
        reasons.append("parent.tree_sha256_after_child: not checked")
    if before_hash != after_hash:
        reasons.append("parent.tree_sha256: parent changed during child execution")

    child_process = child.get("process")
    if not isinstance(child_process, dict):
        reasons.append("child.process: missing or invalid")
    else:
        _expect_equal(reasons, "child.process.exit_code", child_process.get("exit_code"), 0)
    _expect_equal(reasons, "child.execution_nodes", child.get("execution_nodes"), expected_suffix)
    _expect_equal(
        reasons,
        "child.checkpoint_manifest_nodes",
        child.get("checkpoint_manifest_nodes"),
        expected_all_checkpoints,
    )
    _expect_equal(reasons, "duplicate_execution_nodes", record.get("duplicate_execution_nodes"), [])

    status = child.get("status")
    if not isinstance(status, dict):
        reasons.append("child.status: missing or invalid")
        return reasons
    _expect_equal(reasons, "child.status.stage", status.get("stage"), "Done")
    _expect_equal(reasons, "child.status.done", status.get("done"), True)
    checkpointing = status.get("checkpointing")
    if not isinstance(checkpointing, dict):
        reasons.append("child.status.checkpointing: not checked")
    else:
        _expect_equal(reasons, "checkpointing.state", checkpointing.get("state"), "complete")
        _expect_equal(
            reasons,
            "checkpointing.committed_nodes",
            checkpointing.get("committed_nodes"),
            expected_all_checkpoints,
        )
        _expect_equal(reasons, "checkpointing.errors", checkpointing.get("errors"), [])

    recovery = status.get("recovery")
    if not isinstance(recovery, dict):
        reasons.append("child.status.recovery: not checked")
    else:
        expected_reused = ["retrieval", *expected_prefix]
        _expect_equal(reasons, "recovery.state", recovery.get("state"), "reused")
        _expect_equal(reasons, "recovery.source_run_id", recovery.get("source_run_id"), "parent")
        _expect_equal(reasons, "recovery.reused_nodes", recovery.get("reused_nodes"), expected_reused)
        _expect_equal(reasons, "recovery.next_node", recovery.get("next_node"), expected_suffix[0])
        inspections = recovery.get("inspections")
        if not isinstance(inspections, dict):
            reasons.append("recovery.inspections: not checked")
        else:
            for node in expected_reused:
                inspection = inspections.get(node)
                if not isinstance(inspection, dict):
                    reasons.append(f"recovery.inspections.{node}: not checked")
                else:
                    _expect_equal(
                        reasons,
                        f"recovery.inspections.{node}.state",
                        inspection.get("state"),
                        "reusable",
                    )
    return reasons


def _unit_id(fixture_id: str, scenario_id: str) -> str:
    return f"{fixture_id[:2]}-{scenario_id}"


def check_experiment(root: Path) -> dict[str, Any]:
    """Validate the frozen Cartesian product and every persisted unit seam."""

    study_errors: list[str] = []
    manifest = _read_json_object(root / "study-manifest.json")
    expected_contract = _frozen_contract()
    if manifest is None:
        study_errors.append("study-manifest.json: missing or invalid")
    elif manifest.get("contract") != expected_contract:
        study_errors.append("study-manifest.json: contract differs from pre-registration")

    expected_ids = {
        _unit_id(fixture_id, scenario.scenario_id)
        for fixture_id, _digest in FROZEN_FIXTURES
        for scenario in SCENARIOS
    }
    records: dict[str, dict[str, Any]] = {}
    for path in sorted(root.glob("*/unit.json")):
        record = _read_json_object(path)
        if record is None:
            study_errors.append(f"{path.parent.name}: unit.json missing or invalid")
            continue
        unit_id = record.get("unit_id")
        if not isinstance(unit_id, str):
            study_errors.append(f"{path.parent.name}: unit_id missing")
            continue
        if unit_id in records:
            study_errors.append(f"{unit_id}: duplicate unit record")
            continue
        records[unit_id] = record

    actual_ids = set(records)
    missing = sorted(expected_ids - actual_ids)
    extra = sorted(actual_ids - expected_ids)
    if missing:
        study_errors.append(f"missing units: {', '.join(missing)}")
    if extra:
        study_errors.append(f"unexpected units: {', '.join(extra)}")

    unit_results: list[dict[str, Any]] = []
    for unit_id in sorted(expected_ids):
        record = records.get(unit_id)
        if record is None:
            unit_results.append(
                {"unit_id": unit_id, "passed": False, "failure_reasons": ["missing unit"]}
            )
            continue
        fixture_id = record.get("fixture_id")
        expected_digest = dict(FROZEN_FIXTURES).get(fixture_id)
        reasons = evaluate_unit(record)
        if expected_digest is None:
            reasons.append(f"fixture_id: unknown {fixture_id!r}")
        elif record.get("fixture_sha256") != expected_digest:
            reasons.append("fixture_sha256: differs from pre-registration")
        expected_unit_id = (
            _unit_id(fixture_id, record.get("scenario_id", ""))
            if isinstance(fixture_id, str)
            else None
        )
        if unit_id != expected_unit_id:
            reasons.append(f"unit_id: expected {expected_unit_id!r}, got {unit_id!r}")
        unit_results.append(
            {"unit_id": unit_id, "passed": not reasons, "failure_reasons": reasons}
        )

    expected_units = len(expected_ids)
    passing_units = sum(result["passed"] for result in unit_results)
    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": _utc_now(),
        "expected_units": expected_units,
        "observed_unit_records": len(records),
        "passing_units": passing_units,
        "recovery_success_rate": passing_units / expected_units,
        "study_passed": not study_errors and passing_units == expected_units,
        "study_errors": study_errors,
        "units": unit_results,
    }


def execute_study(
    *,
    fixtures: list[Fixture],
    output_root: Path,
    timeout_seconds: float,
) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(
            f"output root already exists; refusing to overwrite study evidence: {output_root}"
        )
    output_root.mkdir(parents=True)
    _atomic_write_json(
        output_root / "study-manifest.json",
        {
            "created_at": _utc_now(),
            "mode": "offline_process_fault_injection",
            "network_calls": 0,
            "model_calls": 0,
            "contract": _frozen_contract(),
        },
    )

    for fixture in fixtures:
        for scenario in SCENARIOS:
            unit_id = _unit_id(fixture.fixture_id, scenario.scenario_id)
            unit_root = output_root / unit_id
            try:
                record = run_fault_unit(
                    unit_root=unit_root,
                    fixture=fixture,
                    scenario=scenario,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001 - preserve a failed study unit
                # One infrastructure failure must not erase the other 29
                # observations. Persist it as an explicit failed unit; the
                # checker still applies the all-or-nothing criterion.
                unit_root.mkdir(parents=True, exist_ok=True)
                record = _minimal_failed_record(
                    fixture,
                    scenario,
                    unit_id,
                    f"{type(exc).__name__}: {exc}",
                )
                _atomic_write_json(unit_root / "unit.json", record)
            state = "PASS" if record.get("passed") else "FAIL"
            print(f"[{state}] {unit_id}", flush=True)

    summary = check_experiment(output_root)
    _atomic_write_json(output_root / "summary.json", summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixtures-root",
        type=Path,
        default=DEFAULT_FIXTURES_ROOT,
        help="directory containing the ten frozen benchmark SourceCollections",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="new directory for ignored per-unit evidence",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="run the zero-network process fault matrix (default: plan only)",
    )
    parser.add_argument(
        "--check",
        type=Path,
        help="recompute a verdict from an existing frozen audit directory",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=30.0,
        help="per parent-boundary and child-process timeout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "_worker":
        return _internal_worker_main(arguments[1:])

    args = _parser().parse_args(arguments)
    if args.timeout_seconds <= 0:
        raise ValueError("--timeout-seconds must be positive")
    if args.check is not None:
        if args.execute:
            raise ValueError("--check and --execute are mutually exclusive")
        summary = check_experiment(args.check)
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0 if summary["study_passed"] else 1

    fixtures = discover_fixtures(args.fixtures_root)
    if not args.execute:
        print(json.dumps(build_plan(fixtures), indent=2, ensure_ascii=False))
        print("Add --execute to run the offline matrix. No files or API calls were made.")
        return 0

    summary = execute_study(
        fixtures=fixtures,
        output_root=args.output_root,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if summary["study_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
