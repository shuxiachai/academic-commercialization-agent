"""Runtime adapter between validated CrewAI tasks and durable checkpoints.

The storage primitive in :mod:`academic_agent.checkpoints` intentionally knows
nothing about CrewAI.  This module owns the missing policy: what contributes to
a task identity, when a post-guardrail output is safe to commit, and which old
outputs may be placed back into a new crew.

Recovery is deliberately a *contiguous-prefix* operation.  CrewAI 1.14.7 can
resume from the first task whose ``output`` is absent, but it cannot safely
skip an arbitrary later task.  Reusing a patent result while re-running the
academic task would require a second scheduler and would change callback,
context, tracing, and rate-limit semantics.  The small amount of extra recall
is not worth that unmeasured execution path: the first missing, mismatched, or
corrupt node ends reuse for the run.

CrewAI also ships a native checkpoint serializer.  It is not used here because
its runtime state serializes each LLM object, and CrewAI's ``BaseLLM`` includes
``api_key`` as a model field.  This adapter persists only the non-secret model
identity defined by our own contract and hydrates only ``TaskOutput.raw``.
"""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any, Final, cast

from crewai.tasks.task_output import TaskOutput
from crewai.utilities.constants import NOT_SPECIFIED

from academic_agent.checkpoints import (
    CheckpointIdentity,
    CheckpointStore,
    ModelIdentity,
    NodeId,
    OutputFormat,
    hash_bytes,
    hash_json,
    hash_text,
)
from academic_agent.run_spec import RunSpec


TASK_NODES: Final[tuple[NodeId, ...]] = (
    "academic",
    "patent",
    "market",
    "writer",
    "reviewer",
    "scorer",
)
_ALL_NODES: Final[tuple[NodeId, ...]] = ("retrieval", *TASK_NODES)
_OUTPUT_FORMATS: Final[dict[NodeId, OutputFormat]] = {
    "retrieval": "json",
    "academic": "json",
    "patent": "json",
    "market": "json",
    "writer": "markdown",
    "reviewer": "markdown",
    "scorer": "json",
}
_UPSTREAMS: Final[dict[NodeId, tuple[NodeId, ...]]] = {
    "retrieval": (),
    "academic": ("retrieval",),
    "patent": ("retrieval",),
    "market": ("retrieval",),
    "writer": ("academic", "patent", "market"),
    "reviewer": ("academic", "patent", "market", "writer"),
    # Scoring is intentionally independent of prose.  Including writer or
    # reviewer here would retire valid score checkpoints when wording changed.
    "scorer": ("academic", "patent", "market"),
}
_REVISION_ENV_VARS: Final[tuple[str, ...]] = (
    "RAILWAY_GIT_COMMIT_SHA",
    "GITHUB_SHA",
    "SOURCE_VERSION",
)
_COMMIT_PATTERN = re.compile(r"[0-9a-fA-F]{7,64}")


def pipeline_revision() -> str:
    """Return the deployed commit, or a source-content fallback outside CI.

    A package version is too weak here: this project does not bump its version
    for every prompt or guardrail edit.  Railway and GitHub expose the commit;
    local/other-container runs hash the exact files that shape retrieval,
    prompts, validation, and this recovery adapter instead.
    """

    for name in _REVISION_ENV_VARS:
        candidate = os.getenv(name, "").strip()
        if _COMMIT_PATTERN.fullmatch(candidate):
            return f"git:{candidate.lower()}"

    package = Path(__file__).resolve().parent
    relevant = (
        package / "checkpoint_runtime.py",
        package / "checkpoints.py",
        package / "crew.py",
        package / "evidence.py",
        package / "llm_config.py",
        package / "pipeline_worker.py",
        package / "run_spec.py",
        package / "source_pipeline.py",
        package / "config" / "agents.yaml",
        package / "config" / "tasks.yaml",
    )
    payload = bytearray()
    for path in relevant:
        # A missing production file is itself a different revision.  Recording
        # the marker keeps the hash deterministic and lets the later import
        # raise the useful error rather than hiding it here.
        relative = path.relative_to(package).as_posix().encode("utf-8")
        payload.extend(len(relative).to_bytes(4, "big"))
        payload.extend(relative)
        if path.is_file():
            content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            payload.extend(len(content).to_bytes(8, "big"))
            payload.extend(content)
        else:
            payload.extend((0).to_bytes(8, "big"))
    return f"source:{hash_bytes(bytes(payload))}"


def retrieval_identity(
    spec: RunSpec,
    *,
    revision: str,
    as_of_date: date,
) -> CheckpointIdentity:
    """Identity for the deterministic retrieval-and-localisation stage.

    Search credentials and backend availability are intentionally not part of
    this identity.  They affect how the already-committed source collection was
    obtained, not whether that exact validated collection can be reused after
    a crash.  The one-day boundary prevents an old collection being presented
    as a fresh search on a later date.
    """

    return CheckpointIdentity(
        node_id="retrieval",
        input_sha256=hash_json(spec),
        evidence_sha256=hash_json(spec.paper_contribution or {}),
        config_sha256=hash_json({"stage": "source_collection", "contract": 1}),
        upstream_sha256={},
        pipeline_revision=revision,
        as_of_date=as_of_date,
        model=None,
    )


def _bounded_response_format(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, type):
        text = f"{value.__module__}.{value.__qualname__}"
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
        except (TypeError, ValueError):
            text = str(value)
    text = text.strip()
    if not text:
        return None
    return text if len(text) <= 100 else f"sha256:{hash_text(text)}"


def _model_identity(task: Any) -> ModelIdentity:
    agent = getattr(task, "agent", None)
    llm = getattr(agent, "llm", None)
    if llm is None:
        raise ValueError("checkpointed task has no configured LLM")

    provider = str(getattr(llm, "provider", "") or type(llm).__module__).strip()
    model = str(getattr(llm, "model", "") or type(llm).__qualname__).strip()
    endpoint = str(getattr(llm, "base_url", "") or "").strip().rstrip("/")
    temperature = getattr(llm, "temperature", None)
    if temperature is not None:
        temperature = float(temperature)

    response_format = getattr(llm, "response_format", None)
    if response_format is None:
        additional = getattr(llm, "additional_params", None)
        if isinstance(additional, Mapping):
            response_format = additional.get("response_format")

    return ModelIdentity(
        provider=provider,
        model=model,
        endpoint_sha256=hash_text(endpoint) if endpoint else None,
        temperature=temperature,
        response_format=_bounded_response_format(response_format),
    )


def _type_name(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, type):
        return f"{value.__module__}.{value.__qualname__}"
    return f"{type(value).__module__}.{type(value).__qualname__}"


def _task_config(task: Any, task_indices: Mapping[int, int]) -> dict[str, Any]:
    """Select output-affecting task fields without serializing CrewAI state.

    Serializing ``task`` or ``agent`` wholesale would reintroduce the native
    checkpoint's secret leak through ``agent.llm.api_key``.  This explicit
    projection is longer but auditable and stable across platforms.
    """

    agent = getattr(task, "agent", None)
    raw_context = getattr(task, "context", None)
    # CrewAI 1.14.7 deliberately distinguishes an omitted context from an
    # explicit None with this singleton. Both mean "no upstream task" to the
    # scheduler, so they must produce the same checkpoint identity. Checking
    # the exported singleton by identity keeps malformed context values loud.
    context = (
        []
        if raw_context is None or raw_context is NOT_SPECIFIED
        else list(raw_context)
    )
    tools = list(getattr(task, "tools", None) or getattr(agent, "tools", None) or [])
    return {
        "description": str(getattr(task, "description", "")),
        "expected_output": str(getattr(task, "expected_output", "")),
        "async_execution": bool(getattr(task, "async_execution", False)),
        "context_indices": [task_indices.get(id(item), -1) for item in context],
        "guardrail_present": getattr(task, "guardrail", None) is not None,
        "guardrail_max_retries": int(getattr(task, "guardrail_max_retries", 0) or 0),
        "output_json": _type_name(getattr(task, "output_json", None)),
        "output_pydantic": _type_name(getattr(task, "output_pydantic", None)),
        "agent": {
            "role": str(getattr(agent, "role", "")),
            "goal": str(getattr(agent, "goal", "")),
            "backstory": str(getattr(agent, "backstory", "")),
            "inject_date": bool(getattr(agent, "inject_date", False)),
            "allow_delegation": bool(getattr(agent, "allow_delegation", False)),
            "tools": [str(getattr(tool, "name", type(tool).__qualname__)) for tool in tools],
        },
    }


def _validated_payload(text: str, output_format: OutputFormat) -> bool:
    if not text.strip():
        return False
    if output_format != "json":
        return True
    try:
        json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return False
    return True


class CheckpointRuntime:
    """Commit validated task outputs and hydrate a safe prior-run prefix."""

    def __init__(
        self,
        *,
        crew: Any,
        source_collection: Any,
        crew_inputs: Mapping[str, Any],
        destination_run_directory: Path | str,
        retrieval_output_sha256: str,
        revision: str,
        as_of_date: date,
        resume_run_id: str | None = None,
        resume_run_directory: Path | str | None = None,
        retrieval_committed: bool = True,
        initial_errors: Sequence[str] = (),
        retrieval_reused: bool = False,
        retrieval_inspection: Mapping[str, Any] | None = None,
    ) -> None:
        self.crew = crew
        self.tasks = list(getattr(crew, "tasks", ()) or ())
        self.destination_store = CheckpointStore(destination_run_directory)
        self.resume_store = (
            CheckpointStore(resume_run_directory)
            if resume_run_directory is not None
            else None
        )
        self.resume_run_id = resume_run_id
        self.revision = revision
        self.as_of_date = as_of_date
        self.input_sha256 = hash_json(dict(crew_inputs))
        evidence_payload = source_collection.model_dump(mode="json")
        if not isinstance(evidence_payload, dict):
            # Production supplies SourceCollection, but lightweight orchestration
            # tests and third-party callers may provide a duck-typed collection.
            # Hash the exact Crew input in that degraded topology rather than
            # failing an otherwise valid report solely in auxiliary recovery.
            evidence_payload = dict(crew_inputs)
        self.evidence_sha256 = hash_json(evidence_payload)
        self._output_hashes: dict[NodeId, str] = {
            "retrieval": retrieval_output_sha256,
        }
        self._committed: set[NodeId] = {"retrieval"} if retrieval_committed else set()
        self._reused: list[NodeId] = ["retrieval"] if retrieval_reused else []
        self._inspections: dict[NodeId, dict[str, Any]] = (
            {"retrieval": dict(retrieval_inspection)}
            if retrieval_inspection is not None
            else {}
        )
        self._errors: list[str] = list(initial_errors)
        self._lock = threading.RLock()
        self._callbacks_installed = False
        self._reused_prefix = 0

        if len(self.tasks) == len(TASK_NODES):
            indices = {id(task): index for index, task in enumerate(self.tasks)}
            self._config_hashes = {
                node: hash_json(_task_config(task, indices))
                for node, task in zip(TASK_NODES, self.tasks, strict=True)
            }
            self._models = {
                node: _model_identity(task)
                for node, task in zip(TASK_NODES, self.tasks, strict=True)
            }
        else:
            # Production has exactly six tasks.  A topology drift must be
            # visible as degraded checkpointing, not silently treated as a
            # successful run with no recoverable nodes.  Several orchestration
            # tests use a minimal MagicMock crew, so the report path still runs.
            self._config_hashes: dict[NodeId, str] = {}
            self._models: dict[NodeId, ModelIdentity] = {}
            self._errors.append(
                f"topology:expected_{len(TASK_NODES)}_tasks_got_{len(self.tasks)}"
            )

    @property
    def reusable_prefix(self) -> int:
        return self._reused_prefix

    @property
    def enabled(self) -> bool:
        return len(self.tasks) == len(TASK_NODES)

    def _identity(self, node: NodeId) -> CheckpointIdentity:
        upstream: dict[NodeId, str] = {}
        missing = []
        for dependency in _UPSTREAMS[node]:
            digest = self._output_hashes.get(dependency)
            if digest is None:
                missing.append(dependency)
            else:
                upstream[dependency] = digest
        if missing:
            raise RuntimeError(
                f"{node} checkpoint missing upstream output hashes: {', '.join(missing)}"
            )
        return CheckpointIdentity(
            node_id=node,
            input_sha256=self.input_sha256,
            evidence_sha256=self.evidence_sha256,
            config_sha256=self._config_hashes[node],
            upstream_sha256=upstream,
            pipeline_revision=self.revision,
            as_of_date=self.as_of_date,
            model=self._models[node],
        )

    def restore_contiguous_prefix(self) -> int:
        """Hydrate only the longest reusable prefix from the source run."""

        if self.resume_store is None or not self.enabled:
            return 0

        with self._lock:
            for node, task in zip(TASK_NODES, self.tasks, strict=True):
                expected = self._identity(node)
                inspection = self.resume_store.inspect(expected)
                self._inspections[node] = {
                    "state": inspection.state,
                    "reasons": list(inspection.reasons),
                }
                if inspection.state != "reusable" or inspection.manifest is None:
                    break

                text = inspection.text()
                output_format = _OUTPUT_FORMATS[node]
                if not _validated_payload(text, output_format):
                    self._inspections[node] = {
                        "state": "corrupt",
                        "reasons": ["payload_format"],
                    }
                    break

                task.output = TaskOutput(
                    description=str(getattr(task, "description", "")),
                    expected_output=str(getattr(task, "expected_output", "")),
                    raw=text,
                    agent=str(getattr(getattr(task, "agent", None), "role", "")),
                )
                # CrewAI Task has no output_format before execution in 1.14.7,
                # and these production tasks consume exact post-guardrail raw
                # text. Inferring CrewAI JSON from the checkpoint's storage
                # format would make TaskOutput.__str__ prefer json_dict and
                # change the downstream context bytes. RAW is its default and
                # faithfully preserves the validated text.
                self._output_hashes[node] = inspection.manifest.output_sha256
                self._reused.append(node)
                self._reused_prefix += 1

                # A child run must become independently resumable.  Copy by
                # recommitting the already-verified bytes rather than storing a
                # parent path that can be pruned out from underneath it.
                try:
                    self.destination_store.commit(
                        expected,
                        text,
                        output_format=output_format,
                        usage=inspection.manifest.usage,
                        completed_at=inspection.manifest.completed_at,
                    )
                    self._committed.add(node)
                except (OSError, TypeError, ValueError) as exc:
                    self._errors.append(
                        f"{node}:copy:{type(exc).__name__}:{str(exc)[:160]}"
                    )

            if self._reused_prefix:
                # CrewAI 1.14.7's sequential executor checks this field and
                # then starts at the first task whose output is None.  The
                # pinned-version seam is covered by a real Crew kickoff test;
                # upgrading CrewAI remains explicitly forbidden on main.
                self.crew.checkpoint_kickoff_event_id = (
                    f"academic-agent:{self.resume_run_id or 'external'}"
                )
        return self._reused_prefix

    def _commit_output(self, node: NodeId, task_output: Any) -> None:
        raw = getattr(task_output, "raw", None)
        if not isinstance(raw, str) or not _validated_payload(raw, _OUTPUT_FORMATS[node]):
            with self._lock:
                self._errors.append(f"{node}:callback_payload_invalid")
            return

        with self._lock:
            # Set the digest before publishing.  A downstream task may start as
            # soon as this callback returns; even if the checkpoint disk write
            # fails, its identity must still bind the exact upstream bytes it
            # received rather than pretending no dependency existed.
            self._output_hashes[node] = hash_text(raw)
            try:
                identity = self._identity(node)
                manifest = self.destination_store.commit(
                    identity,
                    raw,
                    output_format=_OUTPUT_FORMATS[node],
                )
                self._output_hashes[node] = manifest.output_sha256
                self._committed.add(node)
            except (OSError, TypeError, ValueError, RuntimeError) as exc:
                # Checkpointing improves recovery but is not report validity.
                # Raising here would discard a paid, guardrail-validated task
                # solely because an auxiliary disk write failed.  The terminal
                # status exposes the degradation instead.
                self._errors.append(
                    f"{node}:commit:{type(exc).__name__}:{str(exc)[:160]}"
                )

    def install_task_callbacks(self) -> None:
        """Attach post-validation persistence without doubling progress calls."""

        if not self.enabled or self._callbacks_installed:
            return
        crew_callback = getattr(self.crew, "task_callback", None)
        for node, task in zip(TASK_NODES, self.tasks, strict=True):
            original = getattr(task, "callback", None)

            def checkpoint_callback(
                output: Any,
                *,
                node_id: NodeId = node,
                previous: Callable[[Any], None] | None = original,
            ) -> None:
                self._commit_output(node_id, output)
                # CrewAI invokes crew.task_callback after task.callback when
                # the two objects differ.  Calling the same callback here too
                # would advance the UI twice for one paid node.
                if previous is not None and previous is not crew_callback:
                    previous(output)

            task.callback = checkpoint_callback
        self._callbacks_installed = True

    def commit_manual_output(self, node: NodeId, task_output: Any) -> None:
        """Commit a validated output executed outside normal Crew callbacks."""

        if node not in TASK_NODES or not self.enabled:
            return
        self._commit_output(node, task_output)

    def snapshot(self) -> dict[str, Any]:
        """Return distinct checkpointing and recovery states for status.json."""

        with self._lock:
            committed = [node for node in _ALL_NODES if node in self._committed]
            if self._errors:
                checkpoint_state = "degraded"
            elif len(committed) == len(_ALL_NODES):
                checkpoint_state = "complete"
            else:
                checkpoint_state = "partial"

            if self.resume_store is None:
                recovery_state = "not_requested"
            elif not self.enabled:
                recovery_state = "unavailable"
            elif self._reused:
                recovery_state = "reused"
            else:
                recovery_state = "cold_start"

            next_node: NodeId | None = (
                TASK_NODES[self._reused_prefix]
                if self._reused_prefix < len(TASK_NODES)
                else None
            )
            return {
                "checkpointing": {
                    "state": checkpoint_state,
                    "committed_nodes": committed,
                    "errors": list(self._errors),
                },
                "recovery": {
                    "state": recovery_state,
                    "source_run_id": self.resume_run_id,
                    "reused_nodes": list(self._reused),
                    "next_node": next_node,
                    "inspections": dict(self._inspections),
                },
            }


def task_node(index: int) -> NodeId:
    """Typed task-index mapping used by recovery/fallback integration."""

    return cast(NodeId, TASK_NODES[index])
