"""Subprocess worker: runs the full analysis pipeline for a single run.

Invoked as:
    python -m academic_agent.pipeline_worker <run_id> <topic>

Writes status.json for stage progress and steps.jsonl for the live agent
log; API and CLI readers observe both files without shared memory.
"""
import argparse
import copy
import json
import os
import re
import sys
import threading
import time
import traceback
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from academic_agent.run_terminal import (
    TerminalRecord,
    UsageAccounting,
    commit_terminal_record,
)
from academic_agent.runtime_budget import RuntimeBudget, WORKER_LLM_TIMEOUT_ENV

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

_STAGE_INITIAL    = "Source Collection & Validation"
_PARALLEL_COUNT   = 3
_PARALLEL_STAGE   = "Phase 1 — Evidence Collection (Academic · Patent · Market)"
_SEQUENTIAL_STAGES = [
    "Agent 4 — Report Writing",
    "Agent 5 — Quality Review & Citation Check",
    "Agent 6 — Commercialization Scoring",
]

# Tasks are 0-indexed: academic(0) patent(1) market(2) report(3) review(4)
# scoring(5).
_IDX_REVIEW = 4
_IDX_SCORING = 5

def _resolve_resume_directory(output_root: Path, run_id: str) -> Path:
    """Resolve a source run id without allowing an arbitrary checkpoint path.

    The API supplies this value, but the worker is also a public CLI module.
    Treating it as a path would let ``--resume-from ..\\...`` read manifests
    outside ``outputs`` before checkpoint integrity checks had a chance to run.
    """

    if not run_id or run_id != Path(run_id).name or ".." in run_id:
        raise ValueError(f"Invalid resume run id: {run_id!r}")
    root = output_root.resolve()
    candidate = (root / run_id).resolve(strict=True)
    if candidate.parent != root or not candidate.is_dir():
        raise ValueError(f"Resume run is outside the output root: {run_id!r}")
    return candidate




def _select_report_and_scores(
    tasks_output: list, fallback_raw: str | None,
) -> tuple[str | None, str | None]:
    """Pick the report and scorecard text out of the crew's task outputs.

    Indices are explicit rather than reading tasks_output[-1] throughout, so a
    task inserted in the middle of the pipeline cannot silently shift which
    output gets read as the report — a mistake here means every run persists
    the wrong text with no error raised anywhere.

    Degrades for partial completion (a run that crashed mid-pipeline, so its
    task list is shorter than 6) rather than raising: the caller's job is to
    persist whatever exists so a partial failure still has diagnostic
    artifacts, not to demand a complete run.
    """
    if len(tasks_output) > _IDX_SCORING:
        return tasks_output[_IDX_REVIEW].raw, tasks_output[_IDX_SCORING].raw
    if len(tasks_output) == _IDX_SCORING:
        return tasks_output[_IDX_REVIEW].raw, None
    if len(tasks_output) >= 2:
        return tasks_output[-1].raw, None
    return fallback_raw, None


def _review_quality_from_outputs(tasks_output: list[Any]) -> dict[str, Any]:
    """Report whether the Reviewer completed every proposed exact correction.

    A successful Crew kickoff is not itself proof that review was complete.
    Deriving this at the task-output seam keeps the status truthful for both
    fresh outputs and hydrated checkpoints before Reviewer Notes are separated
    from the delivered report.
    """
    if len(tasks_output) <= _IDX_REVIEW:
        return {
            "status": "unavailable",
            "reason": "Reviewer output was absent after crew completion.",
        }

    raw = str(getattr(tasks_output[_IDX_REVIEW], "raw", "") or "")
    if not raw.strip():
        return {
            "status": "unavailable",
            "reason": "Reviewer output was empty after crew completion.",
        }

    from academic_agent.evidence import reviewer_quality_summary

    return reviewer_quality_summary(raw)


def _recover_from_reviewer_failure(
    crew_obj: Any,
    error: Exception,
    *,
    task_complete: Callable[[Any], None] | None = None,
    checkpoint_complete: Callable[[int, Any], None] | None = None,
) -> tuple[list[Any], dict[str, str]] | None:
    """Deliver Task 4's validated draft when only Task 5 failed.

    Review is defense in depth, not the sole validator: Task 4 has already
    passed the full structure, citation-registry, and disclaimer guardrail.
    Throwing that paid artifact away because a second model could not finish
    repeating it made reliability worse, not better. Recovery is deliberately
    narrow: it is available only when the draft exists and neither review nor
    scoring completed. A Task 4 or Task 6 failure still fails the run.

    Scoring remains independent of prose and reads Tasks 1-3 only, so it can be
    executed through CrewAI's public Task API without weakening its guardrail.
    Both callback locations are temporarily disabled to avoid counting the
    manually executed task twice; this helper emits the two missing completion
    events explicitly after their outputs exist.  Only the independently
    validated scorer output is checkpointed.  The copied draft is deliberately
    not published as a reviewer checkpoint: a future resume must not mistake a
    review that never happened for a completed quality inspection.
    """
    tasks = list(getattr(crew_obj, "tasks", ()) or ())
    if len(tasks) <= _IDX_SCORING:
        return None

    report_output = getattr(tasks[3], "output", None)
    review_task = tasks[_IDX_REVIEW]
    scoring_task = tasks[_IDX_SCORING]
    if (
        report_output is None
        or getattr(review_task, "output", None) is not None
        or getattr(scoring_task, "output", None) is not None
    ):
        return None

    review_output = copy.copy(report_output)
    review_task.output = review_output
    if task_complete is not None:
        task_complete(review_output)

    from crewai.utilities.formatter import aggregate_raw_outputs_from_tasks

    scoring_context = aggregate_raw_outputs_from_tasks(scoring_task.context or [])
    original_task_callback = getattr(scoring_task, "callback", None)
    original_crew_callback = getattr(crew_obj, "task_callback", None)
    try:
        scoring_task.callback = None
        crew_obj.task_callback = None
        scoring_output = scoring_task.execute_sync(context=scoring_context)
    finally:
        scoring_task.callback = original_task_callback
        crew_obj.task_callback = original_crew_callback
    if checkpoint_complete is not None:
        checkpoint_complete(_IDX_SCORING, scoring_output)

    if task_complete is not None:
        task_complete(scoring_output)

    outputs = [getattr(task, "output", None) for task in tasks]
    if any(output is None for output in outputs):
        # This should be unreachable after the narrow state check above, but a
        # partial list would shift fixed task indices and could persist evidence
        # JSON as a report. Refuse that unsafe shape rather than filtering it.
        raise RuntimeError("Reviewer fallback produced an incomplete task output list.")

    print(
        "[worker] reviewer did not complete; delivering the validated Task 4 "
        f"draft unchanged ({type(error).__name__}: {error})",
        file=sys.stderr,
        flush=True,
    )
    return outputs, {
        "status": "fallback",
        "reason": (
            "Quality review did not complete; the report is the unchanged "
            "Task 4 draft that passed structure and citation validation."
        ),
        "failure_type": type(error).__name__,
    }


class ProgressTracker:
    """Which agent just finished, what stage the run is now in, and which
    agent to show as starting next.

    Extracted from the callback it used to live in. CrewAI fires that callback
    from the three parallel evidence agents' own threads, so the counters need
    a lock — and a closure holding a lock inside a 300-line function cannot be
    tested without running a real crew, which is why the ordering it encodes
    had never been checked.

    The rule it encodes is not obvious from either end: the first two parallel
    completions announce no successor, because the other two evidence agents
    are already running and marking one "starting" would show the same agent
    twice. Only the third does, when the report writer genuinely begins.
    """

    def __init__(self, parallel_count: int, sequential_stages: list[str],
                 parallel_stage: str) -> None:
        self._parallel_count = parallel_count
        self._sequential_stages = sequential_stages
        self._parallel_stage = parallel_stage
        self._total = parallel_count + len(sequential_stages)
        self._parallel_done = 0
        self._sequential_done = 0
        self._lock = threading.Lock()

    @property
    def total_agents(self) -> int:
        return self._total

    @property
    def completed(self) -> int:
        """Completions so far, used as the agent index when a tool event
        arrives with a role the crew's role map does not know. Reading it
        needs the lock too: the tool events fire from the same threads."""
        with self._lock:
            return self._parallel_done + self._sequential_done

    def restore_completed_prefix(self, count: int) -> None:
        """Seed progress for tasks skipped from validated checkpoints.

        CrewAI does not fire completion callbacks for restored tasks.  Without
        this seed, the next real callback would label the writer as evidence
        Agent 1 and the browser would finish with fewer than six completions
        even though all six outputs reached it.
        """

        if not 0 <= count <= self._total:
            raise ValueError(f"completed prefix must be between 0 and {self._total}")
        with self._lock:
            if self._parallel_done or self._sequential_done:
                raise RuntimeError("progress can only be restored before callbacks begin")
            self._parallel_done = min(count, self._parallel_count)
            self._sequential_done = max(0, count - self._parallel_count)

    def next_incomplete(self) -> int | None:
        """Agent index to announce after restored completion events."""

        completed = self.completed
        return completed if completed < self._total else None
    def on_complete(self) -> tuple[int, str, int | None]:
        """Record one completion. Returns (finished_idx, stage, next_idx)."""
        with self._lock:
            if self._parallel_done < self._parallel_count:
                self._parallel_done += 1
                finished = self._parallel_done - 1
                last_parallel = self._parallel_done == self._parallel_count
                stage = (self._sequential_stages[0] if last_parallel
                         else self._parallel_stage)
                return finished, stage, (self._parallel_count if last_parallel else None)

            self._sequential_done += 1
            finished = self._parallel_count + self._sequential_done - 1
            seq_idx = self._sequential_done
            stage = (self._sequential_stages[seq_idx]
                     if seq_idx < len(self._sequential_stages)
                     else self._sequential_stages[-1])
            nxt = finished + 1
            return finished, stage, (nxt if nxt < self._total else None)




_USAGE_COUNTER_FIELDS = (
    "prompt_tokens",
    "cached_prompt_tokens",
    "cache_creation_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "total_tokens",
    "requests",
)


def _merge_usage_snapshots(
    previous: dict[str, Any] | None,
    current: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Merge provider counters monotonically at every completed-node seam.

    CrewAI's counters are cumulative, but the first three callbacks originate
    from parallel threads. Serializing status writes prevents torn JSON; this
    per-agent maximum additionally prevents a later observation from erasing
    an already persisted counter if a provider updates its summary slightly
    after invoking the task callback.
    """

    if previous is None:
        return dict(current) if current is not None else None
    if current is None:
        return dict(previous)

    merged_agents: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for snapshot in (previous, current):
        for candidate in snapshot.get("agents") or []:
            if not isinstance(candidate, dict):
                continue
            key = (str(candidate.get("role") or ""), str(candidate.get("model") or ""))
            if key not in merged_agents:
                merged_agents[key] = dict(candidate)
                order.append(key)
                continue
            target = merged_agents[key]
            for field in _USAGE_COUNTER_FIELDS:
                target[field] = max(
                    int(target.get(field) or 0), int(candidate.get(field) or 0)
                )
            costs = [
                value
                for value in (target.get("cost_usd"), candidate.get("cost_usd"))
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            ]
            target["cost_usd"] = max(costs) if costs else None

    agents = [merged_agents[key] for key in order]
    merged = dict(previous)
    merged.update(current)
    merged["agents"] = agents
    if agents:
        merged["total_tokens"] = sum(int(a.get("total_tokens") or 0) for a in agents)
        merged["total_requests"] = sum(int(a.get("requests") or 0) for a in agents)
        known_costs = [a.get("cost_usd") for a in agents if a.get("cost_usd") is not None]
        merged["cost_usd"] = round(sum(known_costs), 6) if known_costs else None
    else:
        merged["total_tokens"] = max(
            int(previous.get("total_tokens") or 0), int(current.get("total_tokens") or 0)
        )
        merged["total_requests"] = max(
            int(previous.get("total_requests") or 0), int(current.get("total_requests") or 0)
        )
        costs = [
            value
            for value in (previous.get("cost_usd"), current.get("cost_usd"))
            if isinstance(value, (int, float)) and not isinstance(value, bool)
        ]
        merged["cost_usd"] = max(costs) if costs else None

    merged["cost_complete"] = bool(previous.get("cost_complete", True)) and bool(
        current.get("cost_complete", True)
    )
    merged["unpriced_models"] = sorted(
        set(previous.get("unpriced_models") or ())
        | set(current.get("unpriced_models") or ())
    )
    bases = [
        str(value)
        for value in (previous.get("price_basis"), current.get("price_basis"))
        if value
    ]
    merged["price_basis"] = " + ".join(dict.fromkeys(bases))
    if current.get("collection_error") or previous.get("collection_error"):
        merged["collection_error"] = (
            current.get("collection_error") or previous.get("collection_error")
        )
    return merged


def _usage_accounting_snapshot(
    usage: dict[str, Any] | None,
    *,
    stage: str,
    run_complete: bool,
    in_flight_request_may_have_spent: bool,
) -> dict[str, Any]:
    """Serialize temporal completeness separately from price completeness."""

    # A collector error is not an observed zero. Preserve its diagnostic in
    # ``usage`` while making the accounting state explicitly unavailable.
    if usage is None or usage.get("collection_error"):
        state = "unavailable"
    elif run_complete:
        state = "complete"
    else:
        state = "lower_bound"
    return UsageAccounting(
        state=state,
        snapshot_at=datetime.now(UTC),
        through_stage=stage,
        run_complete=run_complete,
        in_flight_request_may_have_spent=in_flight_request_may_have_spent,
    ).model_dump(mode="json")


def _merge_status_fields(
    existing: dict,
    *,
    stage: str,
    done: bool,
    error: str | None,
    output_language: str | None,
    source_counts: dict | None,
    topic: str | None,
    pipeline_revision: str | None = None,
) -> dict:
    """Build the next status.json payload from the previous one plus updates.

    status.json is rewritten wholesale on every stage transition, but topic
    and source_counts are set once early on and must survive every later call.
    pipeline_revision is stricter: it identifies the code that began this run,
    so the first persisted value wins even if a later caller accidentally
    offers the identity of a newer deployment. Deriving it in the API would
    mislabel historical runs after each deploy.
    """
    data: dict = {"stage": stage, "done": done, "error": error}
    if output_language is not None:
        data["output_language"] = output_language
    elif existing.get("output_language") is not None:
        # Language is discovered during source planning. A later error write
        # used to replace it with None, so a failed Chinese run appeared as
        # English in the API even though all paid agent prompts were Chinese.
        data["output_language"] = existing["output_language"]
    else:
        data["output_language"] = None
    # evidence_incomplete is sticky for the same reason topic is: it is set
    # once, mid-run, by the only code path that can discover it, and every
    # later status write would otherwise erase the warning it carries.
    for sticky in (
        "topic", "source_counts", "evidence_incomplete", "failed_domains", "usage",
        "usage_accounting", "runtime_budget",
        "claim_grounding", "consistency", "observability", "authority_coverage",
        "component_coverage", "evidence_gap_shadow", "decision_gate", "report_audit",
        "quality_review",
        "checkpointing", "recovery",
        "pipeline_revision",
    ):
        if existing.get(sticky) is not None:
            data[sticky] = existing[sticky]
    if pipeline_revision is not None and existing.get("pipeline_revision") is None:
        data["pipeline_revision"] = pipeline_revision
    if source_counts is not None:
        data["source_counts"] = source_counts
    if topic is not None:
        data["topic"] = topic
    return data


def main() -> None:
    worker_started_at = datetime.now(UTC)
    worker_started_monotonic = time.monotonic()
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("topic")
    parser.add_argument("--language", default="", help="Force output language (overrides auto-detect)")
    parser.add_argument("--weight-profile", default="", help="Force scoring weight profile (overrides auto-detect)")
    parser.add_argument("--paper-json", default="", help="Path to JSON file containing PaperContribution data")
    parser.add_argument(
        "--run-spec", default="",
        help="Path to the durable RunSpec stored inside this run directory",
    )
    parser.add_argument(
        "--resume-from", default="",
        help="Prior run id whose validated checkpoint prefix may be reused",
    )
    parser.add_argument(
        "--hard-deadline-epoch",
        type=float,
        default=None,
        help="API-owned wall deadline converted once to a monotonic worker budget",
    )
    parser.add_argument(
        "--hard-timeout-seconds",
        type=int,
        default=None,
        help="Public watchdog duration recorded in the immutable terminal outcome",
    )
    args = parser.parse_args()
    runtime_budget = RuntimeBudget.from_wall_deadline(
        args.hard_deadline_epoch,
        args.hard_timeout_seconds,
    )
    if runtime_budget.active:
        os.environ[WORKER_LLM_TIMEOUT_ENV] = str(runtime_budget.request_timeout_seconds)
    else:
        # This is a private parent-to-worker contract, not an operator setting.
        # Removing an inherited stale value keeps direct CLI runs unbounded.
        os.environ.pop(WORKER_LLM_TIMEOUT_ENV, None)

    _max_rpm_env = os.getenv("MAX_RPM", "6")
    try:
        int(_max_rpm_env)
    except ValueError:
        print(f"[worker] MAX_RPM must be an integer, got {_max_rpm_env!r}", file=sys.stderr)
        sys.exit(1)

    from crewai.events.event_bus import crewai_event_bus
    from crewai.events.types.tool_usage_events import (
        ToolUsageFinishedEvent,
        ToolUsageStartedEvent,
    )

    from academic_agent.checkpoint_runtime import (
        CheckpointRuntime,
        pipeline_revision,
        retrieval_identity,
        task_node,
    )
    from academic_agent.checkpoints import CheckpointStore, hash_text
    from academic_agent.llm_config import configure_llm_deadline
    from academic_agent.evidence_gap import (
        persist_shadow_audit,
        run_shadow_assessment,
        shadow_configuration_from_environment,
    )
    from academic_agent.report_audit import save_report_audit
    from academic_agent.run_spec import (
        RESUME_SNAPSHOT_DIRECTORY, RUN_SPEC_FILENAME, RunSpec,
    )
    from academic_agent.observability import start_run_telemetry
    from academic_agent.crew import AcademicAgent
    from academic_agent.run_output import (
        DEFAULT_OUTPUT_ROOT,
        StepEntry,
        save_error,
        save_claim_grounding,
        save_consistency,
        save_evidence_reports,
        save_report,
        save_reviewer_notes,
        save_retrieval_diagnostics,
        save_scores,
        save_source_collection,
    )
    from academic_agent.pdf_extractor import PaperContribution, paper_to_evidence_source
    from academic_agent.source_pipeline import (
        SourceCollection, SourceCollectionError, collect_source_collection,
    )
    from academic_agent.token_usage import collect_usage

    run_dir = DEFAULT_OUTPUT_ROOT / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    status_path = run_dir / "status.json"
    steps_path  = run_dir / "steps.jsonl"
    status_lock = threading.RLock()
    usage_lock = threading.Lock()
    usage_snapshot: dict[str, Any] | None = None

    def write_status(
        stage: str,
        *,
        done: bool = False,
        error: str | None = None,
        output_language: str | None = None,
        source_counts: dict | None = None,
        topic: str | None = None,
        pipeline_revision: str | None = None,
        evidence_incomplete: bool | None = None,
        failed_domains: list[str] | None = None,
        usage: dict | None = None,
        usage_accounting: dict | None = None,
        runtime_budget: dict | None = None,
        claim_grounding: dict | None = None,
        observability: dict | None = None,
        consistency: dict | None = None,
        authority_coverage: dict | None = None,
        component_coverage: dict | None = None,
        evidence_gap_shadow: dict | None = None,
        decision_gate: dict | None = None,
        report_audit: dict | None = None,
        checkpointing: dict | None = None,
        recovery: dict | None = None,
        quality_review: dict | None = None,
    ) -> None:
        status_lock.acquire()
        try:
            try:
                existing = json.loads(status_path.read_text(encoding="utf-8"))
            except Exception as _e:
                print(f"[worker] write_status: could not read existing status: {_e}", file=sys.stderr)
                existing = {}
            data = _merge_status_fields(
                existing, stage=stage, done=done, error=error,
                output_language=output_language,
                source_counts=source_counts,
                topic=topic,
                pipeline_revision=pipeline_revision,
            )
            if evidence_incomplete is not None:
                data["evidence_incomplete"] = evidence_incomplete
            if failed_domains is not None:
                data["failed_domains"] = failed_domains
            if usage is not None:
                data["usage"] = usage
            if usage_accounting is not None:
                data["usage_accounting"] = usage_accounting
            if runtime_budget is not None:
                data["runtime_budget"] = runtime_budget
            if claim_grounding is not None:
                data["claim_grounding"] = claim_grounding
            if consistency is not None:
                data["consistency"] = consistency
            if observability is not None:
                data["observability"] = observability
            if authority_coverage is not None:
                data["authority_coverage"] = authority_coverage
            if component_coverage is not None:
                data["component_coverage"] = component_coverage
            if evidence_gap_shadow is not None:
                data["evidence_gap_shadow"] = evidence_gap_shadow
            if decision_gate is not None:
                data["decision_gate"] = decision_gate
            if report_audit is not None:
                data["report_audit"] = report_audit
            if quality_review is not None:
                data["quality_review"] = quality_review
            if checkpointing is not None:
                data["checkpointing"] = checkpointing
            if recovery is not None:
                data["recovery"] = recovery
            # Atomic: the API polls this file while the worker rewrites it on
            # every stage transition. A plain write leaves a window where the
            # reader sees a truncated document, and an unreadable status was
            # being derived as a failed run — so a finished run could be
            # reported as failed for as long as it took to write one line.
            tmp_path = status_path.with_suffix(".json.tmp")
            with tmp_path.open("w", encoding="utf-8") as fh:
                json.dump(data, fh)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, status_path)
        except Exception as _e:
            print(f"[worker] write_status failed (stage={stage!r}): {_e}", file=sys.stderr)
        finally:
            status_lock.release()

    def commit_worker_terminal(
        *,
        state: str,
        reason_code: str,
        stage: str,
        usage: dict[str, Any] | None,
        usage_accounting: dict[str, Any],
        checkpoint_state: dict[str, Any],
    ) -> None:
        """Publish one worker-owned outcome after the final live status write."""

        ended_at = datetime.now(UTC)
        record = TerminalRecord(
            state=state,
            reason_code=reason_code,
            termination_method="worker_exit",
            started_at=worker_started_at,
            ended_at=ended_at,
            elapsed_seconds=max(
                0, int(time.monotonic() - worker_started_monotonic)
            ),
            last_stage=stage,
            timeout_seconds=args.hard_timeout_seconds,
            usage=usage,
            usage_accounting=UsageAccounting.model_validate(usage_accounting),
            checkpointing=checkpoint_state.get("checkpointing"),
            recovery=checkpoint_state.get("recovery"),
        )
        try:
            commit_terminal_record(run_dir, record)
        except (OSError, ValueError) as terminal_error:
            # status.json remains a usable compatibility path. Do not rewrite
            # a completed report as failed merely because its stronger audit
            # record could not be published; surface the persistence fault.
            print(
                f"[worker] terminal record failed: {terminal_error}",
                file=sys.stderr,
                flush=True,
            )

    # Execution identity belongs to the worker that actually runs the paid
    # workflow, not to whichever API deployment later serves its files. Capture
    # it before the first durable status write so configuration failures remain
    # attributable too; later rewrites preserve this first value.
    revision = pipeline_revision()

    # Start tracing after write_status exists so configuration failures can be
    # made visible, but before source collection so topic planning and retrieval
    # belong to the same root Trace as the six CrewAI tasks.
    telemetry = start_run_telemetry(args.run_id, topic_length=len(args.topic))
    write_status(
        _STAGE_INITIAL, topic=args.topic, pipeline_revision=revision,
        observability=telemetry.snapshot(),
        runtime_budget=runtime_budget.public_snapshot(),
    )

    # Bound before the try so the failure path can still account for a run
    # that died after spending money. A crash halfway through is exactly when
    # someone wants to know what it cost, and it is also the only case where
    # this name might never be assigned.
    crew_obj = None
    checkpoint_runtime = None
    checkpoint_snapshot: dict[str, Any] = {}

    def snapshot_usage(*, emit: bool = False) -> dict[str, Any] | None:
        nonlocal usage_snapshot
        with usage_lock:
            if crew_obj is not None:
                observed = collect_usage(crew_obj)
                candidate = None
                if observed.agents or observed.collection_error is not None:
                    candidate = observed.as_dict()
                usage_snapshot = _merge_usage_snapshots(usage_snapshot, candidate)
            if usage_snapshot is None:
                return None
            if emit:
                cost = usage_snapshot.get("cost_usd")
                cost_text = "unknown" if cost is None else f"${float(cost):.4f}"
                if not usage_snapshot.get("cost_complete", True):
                    unpriced = ", ".join(usage_snapshot.get("unpriced_models") or ())
                    cost_text += f" (at least; unpriced: {unpriced})"
                print(
                    f"[usage] {usage_snapshot.get('total_tokens', 0)} tokens over "
                    f"{usage_snapshot.get('total_requests', 0)} requests, {cost_text}",
                    flush=True,
                )
            return copy.deepcopy(usage_snapshot)

    try:
        if args.run_spec:
            expected_spec = (run_dir / RUN_SPEC_FILENAME).resolve()
            supplied_spec = Path(args.run_spec).resolve()
            if supplied_spec != expected_spec:
                raise ValueError("RunSpec must be stored inside the current run directory.")
            spec = RunSpec.load(run_dir)
            if spec.topic != args.topic.strip():
                raise ValueError("RunSpec topic does not match the worker topic argument.")
        else:
            paper_contribution = None
            if args.paper_json:
                paper_path = Path(args.paper_json)
                if paper_path.is_file():
                    candidate = json.loads(paper_path.read_text(encoding="utf-8"))
                    if not isinstance(candidate, dict):
                        raise ValueError("Paper contribution must be a JSON object.")
                    paper_contribution = candidate
            spec = RunSpec(
                topic=args.topic,
                language=args.language or None,
                weight_profile=args.weight_profile or None,
                paper_contribution=paper_contribution,
            )
            spec.save(run_dir)

        # From this point the persisted contract, not a second interpretation of
        # argv, is the source of truth for both normal execution and recovery.
        args.language = spec.language or ""
        args.weight_profile = spec.weight_profile or ""
        # Publish the code-derived mode as soon as the durable contract is
        # known. Later stage writes keep it sticky, including failures before
        # the Crew is constructed.
        write_status(_STAGE_INITIAL, decision_gate=spec.decision_gate())
        checkpoint_date = datetime.now(UTC).date()
        retrieval_contract = retrieval_identity(
            spec, revision=revision, as_of_date=checkpoint_date
        )
        resume_directory = None
        if args.resume_from:
            local_snapshot = (run_dir / RESUME_SNAPSHOT_DIRECTORY).resolve()
            if (
                local_snapshot.is_dir()
                and local_snapshot.parent == run_dir.resolve()
            ):
                resume_directory = local_snapshot
            else:
                resume_directory = _resolve_resume_directory(
                    DEFAULT_OUTPUT_ROOT, args.resume_from
                )
        if resume_directory == run_dir.resolve():
            raise ValueError("A run cannot resume from its own directory.")

        source_collection: SourceCollection | None = None
        retrieval_reused = False
        retrieval_payload = ""
        retrieval_inspection: dict[str, Any] | None = None
        if resume_directory is not None:
            prior = CheckpointStore(resume_directory).inspect(retrieval_contract)
            retrieval_inspection = {
                "state": prior.state,
                "reasons": list(prior.reasons),
            }
            if prior.state == "reusable":
                try:
                    source_collection = SourceCollection.model_validate_json(prior.text())
                except ValueError as exc:
                    retrieval_inspection = {
                        "state": "corrupt",
                        "reasons": [f"payload_model:{type(exc).__name__}"],
                    }
                else:
                    retrieval_reused = True
                    retrieval_payload = prior.text()

        retrieval_errors: list[str] = []
        retrieval_committed = False
        retrieval_output_sha256 = ""
        checkpoint_snapshot = {
            "checkpointing": {
                "state": "partial",
                "committed_nodes": [],
                "errors": [],
            },
            "recovery": {
                "state": (
                    "reused" if retrieval_reused
                    else "cold_start" if resume_directory is not None
                    else "not_requested"
                ),
                "source_run_id": args.resume_from or None,
                "reused_nodes": ["retrieval"] if retrieval_reused else [],
                "next_node": "academic",
                "inspections": (
                    {"retrieval": retrieval_inspection}
                    if retrieval_inspection is not None else {}
                ),
            },
        }
        # "Auto (detect from topic)" is the UI's own label for "no preference",
        # not a profile name — resolved to None here so the one place that
        # knows the profile names does not have to know the dropdown's.
        requested_profile = (
            args.weight_profile
            if args.weight_profile and args.weight_profile != "Auto (detect from topic)"
            else None
        )
        paper_seed = None
        extra_market_queries = None
        if spec.paper_contribution is not None:
            _pc_data = spec.paper_contribution
            paper_seed = paper_to_evidence_source(PaperContribution(**_pc_data))
            _domain = _pc_data.get("application_domain", "").strip()
            if _domain:
                # Non-ASCII domain (e.g. Chinese) produces queries whose
                # results are rejected by the English keyword relevance filter.
                # Translate to English so Serper results are filterable.
                if any(ord(c) > 127 for c in _domain):
                    from academic_agent.language import translate_to_english
                    _domain = translate_to_english(_domain) or _domain
                extra_market_queries = [
                    f"{_domain} commercial product company revenue manufacturer 2024 2025",
                    f"{_domain} startup investment funding market leader industry",
                ]

        # Passed in rather than assigned to the returned collection, which is
        # where it used to happen. Retrieval branches on the profile — the
        # biomedical path runs a PubMed MeSH expansion no other profile does —
        # so overriding it afterwards changed which rubric scored the evidence
        # without changing which evidence was gathered. A user correcting a
        # misdetected topic to "biomedical" still got the industrial search.
        with telemetry.span(
            "source_collection",
            "RETRIEVER",
            {"academic_agent.source.paper_seeded": paper_seed is not None},
        ):
            source_collection = source_collection or collect_source_collection(
                args.topic,
                paper_seed=paper_seed,
                extra_market_queries=extra_market_queries,
                weight_profile=requested_profile,
            )
        if not retrieval_reused and args.language and args.language != "Auto (detect from topic)":
            # Map UI dropdown values to canonical API language names.
            _UI_TO_API_LANG: dict[str, str] = {"Chinese": "Simplified Chinese"}
            canonical_lang = _UI_TO_API_LANG.get(args.language, args.language)
            source_collection.output_language = canonical_lang
            # When the topic was English but the user forced a non-English output
            # language, localized_headings will be empty — generate them now so
            # the report guardrail validates Chinese/etc. headings correctly.
            if canonical_lang != "English" and not source_collection.localized_headings:
                from academic_agent.language import translate_headings, translate_to_language
                from academic_agent.evidence import _REQUIRED_REPORT_HEADINGS
                source_collection.localized_headings = list(
                    translate_headings(_REQUIRED_REPORT_HEADINGS, canonical_lang)
                )
                # Translate the report title topic so the heading is fully in the
                # target language (e.g. English PDF topics stay English otherwise).
                if source_collection.display_topic:
                    translated_topic = translate_to_language(
                        source_collection.display_topic, canonical_lang
                    )
                    if translated_topic and translated_topic != source_collection.display_topic:
                        source_collection.display_topic = translated_topic
            elif canonical_lang != "English":
                from academic_agent.language import translate_to_language
                if source_collection.display_topic:
                    translated_topic = translate_to_language(
                        source_collection.display_topic, canonical_lang
                    )
                    if translated_topic and translated_topic != source_collection.display_topic:
                        source_collection.display_topic = translated_topic
        # Phase 1 stops at observation. The worker intentionally injects no
        # planner callback, so even an eligible run proposes and executes zero
        # searches. Keeping this between retrieval and source serialization
        # lets the audit hash the exact collection the Crew will receive while
        # leaving the retrieval checkpoint contract unchanged.
        gap_shadow = run_shadow_assessment(
            source_collection,
            configuration=shadow_configuration_from_environment(),
        )
        gap_shadow = persist_shadow_audit(run_dir, gap_shadow)
        telemetry.set_attributes({
            "academic_agent.evidence_gap.gate_state": gap_shadow.gate_state,
            "academic_agent.evidence_gap.planner_state": gap_shadow.planner_state,
            "academic_agent.evidence_gap.signal_count": (
                len(gap_shadow.context.signals) if gap_shadow.context else 0
            ),
            "academic_agent.evidence_gap.executed_calls": (
                gap_shadow.executed_call_count
            ),
        })

        source_json = source_collection.model_dump_json(indent=2)
        if not retrieval_payload:
            retrieval_payload = source_json
        try:
            retrieval_manifest = CheckpointStore(run_dir).commit(
                retrieval_contract,
                retrieval_payload,
                output_format="json",
            )
            retrieval_output_sha256 = retrieval_manifest.output_sha256
            retrieval_committed = True
        except (OSError, TypeError, ValueError) as exc:
            # Retrieval remains usable for this process.  The terminal status
            # reports that a later process cannot safely resume from it.
            retrieval_output_sha256 = hash_text(retrieval_payload)
            retrieval_errors.append(
                f"retrieval:commit:{type(exc).__name__}:{str(exc)[:160]}"
            )
        telemetry.set_attributes({
            "academic_agent.checkpoint.retrieval.reused": retrieval_reused,
            "academic_agent.checkpoint.retrieval.committed": retrieval_committed,
        })
        checkpoint_snapshot["checkpointing"] = {
            "state": "degraded" if retrieval_errors else "partial",
            "committed_nodes": ["retrieval"] if retrieval_committed else [],
            "errors": list(retrieval_errors),
        }
        save_source_collection(
            source_json, run_id=args.run_id, output_root=DEFAULT_OUTPUT_ROOT,
        )
        if source_collection.failed_domains:
            # An empty domain reads as a fact about the technology; this says
            # it is a fact about the infrastructure instead. Logged and put on
            # the status so the distinction reaches whoever reads the report.
            for _domain, _why in source_collection.failed_domains.items():
                print(f"[worker] {_domain} retrieval failed, continuing without it: "
                      f"{_why[:200]}", file=sys.stderr, flush=True)

        source_counts = {
            "academic": len(source_collection.academic_sources),
            "patent": len(source_collection.patent_sources),
            "market": len(source_collection.market_sources),
        }
        telemetry.set_attributes({
            "academic_agent.source.academic.count": source_counts["academic"],
            "academic_agent.source.patent.count": source_counts["patent"],
            "academic_agent.source.market.count": source_counts["market"],
            "academic_agent.source.failed_domains": len(source_collection.failed_domains),
        })
        write_status(
            _PARALLEL_STAGE,
            source_counts=source_counts,
            output_language=source_collection.output_language,
            failed_domains=sorted(source_collection.failed_domains) or None,
            authority_coverage=source_collection.authority_coverage.model_dump(
                mode="json"
            ),
            component_coverage=source_collection.component_coverage.model_dump(
                mode="json"
            ),
            evidence_gap_shadow=gap_shadow.model_dump(mode="json"),
            **checkpoint_snapshot,
        )

        tracker = ProgressTracker(
            _PARALLEL_COUNT, _SEQUENTIAL_STAGES, _PARALLEL_STAGE)
        _steps_fh = None        # open steps.jsonl handle during kickoff (set before kickoff)

        def _write_step(entry: StepEntry) -> None:
            try:
                if _steps_fh is not None:
                    line = json.dumps(entry, ensure_ascii=False) + "\n"
                    _steps_fh.write(line)
                    _steps_fh.flush()
            except Exception as _e:
                print(f"[worker] _write_step failed: {_e}", file=sys.stderr)

        _total_agents = tracker.total_agents

        def on_task_complete(_task_output) -> None:
            finished, stage, next_idx = tracker.on_complete()
            _write_step({"agent_idx": finished, "type": "finish", "thought": ""})
            if next_idx is not None:
                _write_step({"agent_idx": next_idx, "type": "action",
                             "thought": "", "tool": "reasoning",
                             "tool_input": "", "result": ""})
            current_checkpoint_snapshot = (
                checkpoint_runtime.snapshot()
                if checkpoint_runtime is not None else checkpoint_snapshot
            )
            current_usage = snapshot_usage()
            current_accounting = _usage_accounting_snapshot(
                current_usage,
                stage=stage,
                run_complete=False,
                # Parallel nodes or the next sequential node may already have
                # entered a provider call when this callback takes its view.
                in_flight_request_may_have_spent=True,
            )
            write_status(
                stage,
                output_language=source_collection.output_language,
                usage=current_usage,
                usage_accounting=current_accounting,
                **current_checkpoint_snapshot,
            )

        crew_obj = AcademicAgent(
            source_collection,
            task_callback=on_task_complete,
        ).crew()
        if runtime_budget.active:
            for index, agent in enumerate(crew_obj.agents):
                # Agent instances are constructed before the API deadline is
                # available to their wrapped call methods. Configure that
                # mutable seam once, before either checkpoint hydration or
                # paid execution can invoke a provider.
                configure_llm_deadline(
                    agent.llm,
                    deadline_monotonic=runtime_budget.deadline_for_agent(index),
                    stage=str(agent.role or f"Agent {index + 1}"),
                    request_timeout_seconds=runtime_budget.request_timeout_seconds,
                )
        crew_inputs = source_collection.crew_inputs()
        # Decision context does not alter retrieval or scoring. It enters only
        # the Writer/Reviewer placeholders, while remaining part of the exact
        # checkpoint input hash so recovery cannot cross decision owners.
        crew_inputs.update(spec.decision_crew_inputs())
        checkpoint_runtime = CheckpointRuntime(
            crew=crew_obj,
            source_collection=source_collection,
            crew_inputs=crew_inputs,
            destination_run_directory=run_dir,
            retrieval_output_sha256=retrieval_output_sha256,
            revision=revision,
            as_of_date=checkpoint_date,
            resume_run_id=args.resume_from or None,
            resume_run_directory=resume_directory,
            retrieval_committed=retrieval_committed,
            initial_errors=retrieval_errors,
            retrieval_reused=retrieval_reused,
            retrieval_inspection=retrieval_inspection,
        )
        reused_prefix = checkpoint_runtime.restore_contiguous_prefix()
        tracker.restore_completed_prefix(reused_prefix)
        checkpoint_runtime.install_task_callbacks()
        checkpoint_snapshot = checkpoint_runtime.snapshot()
        write_status(
            _PARALLEL_STAGE,
            output_language=source_collection.output_language,
            **checkpoint_snapshot,
        )

        # Build role → agent index mapping for event handlers.
        # CrewAI 1.14.7 uses AgentExecutor (event-bus-based) by default;
        # step_callback is only invoked by the deprecated CrewAgentExecutor.
        agent_role_to_idx: dict[str, int] = {
            a.role: i for i, a in enumerate(crew_obj.agents)
        }

        _sf = open(steps_path, "a", encoding="utf-8")
        _steps_fh = _sf
        result = None
        quality_review = {
            "status": "unavailable",
            "reason": "Reviewer output was not yet available.",
        }
        try:
            with crewai_event_bus.scoped_handlers():

                @crewai_event_bus.on(ToolUsageStartedEvent)
                def on_tool_started(source, event: ToolUsageStartedEvent) -> None:
                    idx = agent_role_to_idx.get(event.agent_role or "", tracker.completed)
                    _write_step({
                        "agent_idx": idx,
                        "type": "action",
                        "thought": "",
                        "tool": event.tool_name or "",
                        "tool_input": str(event.tool_args or "")[:300],
                        "result": "",
                    })

                @crewai_event_bus.on(ToolUsageFinishedEvent)
                def on_tool_finished(source, event: ToolUsageFinishedEvent) -> None:
                    idx = agent_role_to_idx.get(event.agent_role or "", tracker.completed)
                    _write_step({
                        "agent_idx": idx,
                        "type": "result",
                        "tool": event.tool_name or "",
                        "result": str(event.output or "").strip()[:400],
                    })

                # CrewAI does not emit completion callbacks for hydrated tasks,
                # so reflect the restored prefix explicitly before announcing
                # only the work that will really execute. This is a client
                # seam: without it recovery succeeds on disk while the browser
                # still reports the wrong agent and completion count.
                for _i in range(reused_prefix):
                    _write_step({
                        "agent_idx": _i,
                        "type": "finish",
                        "thought": "Reused validated checkpoint",
                    })
                for _i in range(reused_prefix, _PARALLEL_COUNT):
                    _write_step({"agent_idx": _i, "type": "action", "thought": "",
                                 "tool": "", "tool_input": "", "result": ""})
                if reused_prefix >= _PARALLEL_COUNT:
                    next_idx = tracker.next_incomplete()
                    if next_idx is not None:
                        _write_step({
                            "agent_idx": next_idx,
                            "type": "action",
                            "thought": "",
                            "tool": "reasoning",
                            "tool_input": "",
                            "result": "",
                        })

                with telemetry.span(
                    "crew_execution", "CHAIN", {"academic_agent.pipeline.agents": 6}
                ):
                    result = crew_obj.kickoff(inputs=crew_inputs)
            tasks_output = getattr(result, "tasks_output", None) or []
            quality_review = _review_quality_from_outputs(tasks_output)
        except Exception as crew_error:  # noqa: BLE001 - narrow recovery below
            recovered = _recover_from_reviewer_failure(
                crew_obj,
                crew_error,
                task_complete=on_task_complete,
                checkpoint_complete=lambda index, output: (
                    checkpoint_runtime.commit_manual_output(task_node(index), output)
                ),
            )
            if recovered is None:
                raise
            tasks_output, quality_review = recovered
        finally:
            _steps_fh = None
            _sf.close()

        # Persist the evidence stage before anything that can fail below. Tasks
        # 4 and 6 read these outputs rather than the source registry, so they
        # are the only record of how sources became findings — and they used to
        # exist solely in memory, leaving half the pipeline unauditable.
        evidence_saved = True
        try:
            save_evidence_reports(tasks_output, run_id=args.run_id, output_root=DEFAULT_OUTPUT_ROOT)
        except Exception as exc:  # noqa: BLE001 - inspection files must not fail a run
            # Still not fatal: a report the user can read beats no report at
            # all. But swallowing this silently produced the one outcome
            # nobody can detect — a run that looks completely successful while
            # the record of how its sources became findings is missing, which
            # is exactly what someone auditing a citation would go looking for.
            evidence_saved = False
            print(f"[worker] evidence artifacts could not be saved: "
                  f"{type(exc).__name__}: {exc}", file=sys.stderr, flush=True)

        # Screens the evidence agents' quantitative claims against the text of
        # the sources they cite. Runs off tasks_output rather than the files
        # above, so a failed artifact write does not also cost the audit.
        with telemetry.span("claim_grounding", "EVALUATOR"):
            grounding = save_claim_grounding(
                tasks_output, run_id=args.run_id, output_root=DEFAULT_OUTPUT_ROOT)
        if grounding:
            print(f"[grounding] {grounding['status']}: {grounding['checked']} checkable claims, "
                  f"{grounding['ungrounded']} with a figure absent from the cited "
                  f"source, {grounding['unverifiable']} unverifiable", flush=True)

        report_raw, scores_raw = _select_report_and_scores(
            tasks_output, getattr(result, "raw", None)
        )

        m_rev = re.search(r"(?m)^##\s+Reviewer Notes\b", report_raw, re.IGNORECASE) if report_raw else None
        if m_rev:
            save_reviewer_notes(
                report_raw[m_rev.start():].strip(), run_id=args.run_id, output_root=DEFAULT_OUTPUT_ROOT,
            )
            report_raw = report_raw[: m_rev.start()].rstrip()

        report_audit = {
            "status": "unavailable",
            "non_blocking": True,
            "reason": "No report was available for post-generation audit.",
        }
        if report_raw is not None:
            try:
                with telemetry.span("report_delivery_audit", "EVALUATOR"):
                    report_audit = save_report_audit(
                        report_raw,
                        collection=source_collection,
                        decision_gate=spec.decision_gate(),
                        output_language=source_collection.output_language,
                        run_id=args.run_id,
                        output_root=DEFAULT_OUTPUT_ROOT,
                    )
            except Exception as exc:  # noqa: BLE001 - advisory audit
                # A persistence or heuristic failure must remain visible, but
                # it must not discard a report that already passed the paid
                # writer and reviewer stages.
                report_audit = {
                    "status": "failed",
                    "non_blocking": True,
                    "reason": f"Report audit failed: {type(exc).__name__}",
                }
                print(
                    "[report-audit] failed without blocking delivery: "
                    f"{type(exc).__name__}",
                    file=sys.stderr,
                    flush=True,
                )
            save_report(
                report_raw,
                run_id=args.run_id,
                output_root=DEFAULT_OUTPUT_ROOT,
                decision_gate=spec.decision_gate(),
                output_language=source_collection.output_language,
            )

        if scores_raw:
            save_scores(scores_raw, run_id=args.run_id, output_root=DEFAULT_OUTPUT_ROOT)

        # Only possible here: the reviewer never sees the scorecard and the
        # scorer never sees the reviewed report, so this is the first moment
        # anything holds both.
        with telemetry.span("report_score_consistency", "EVALUATOR"):
            consistency = save_consistency(
                report_raw or "", scores_raw, run_id=args.run_id,
                output_root=DEFAULT_OUTPUT_ROOT)
        if consistency and consistency.get("blockers"):
            print(f"[consistency] {consistency['blockers']} finding(s): the "
                  f"report's recommendation disagrees with its own scorecard",
                  flush=True)

        final_usage = snapshot_usage(emit=True)
        final_accounting = _usage_accounting_snapshot(
            final_usage,
            stage="Done",
            run_complete=True,
            in_flight_request_may_have_spent=False,
        )
        telemetry.set_attributes({
            "academic_agent.usage.total_tokens": (
                final_usage.get("total_tokens") if final_usage else None
            ),
            "academic_agent.usage.total_requests": (
                final_usage.get("total_requests") if final_usage else None
            ),
            "academic_agent.grounding.ungrounded": (
                grounding.get("ungrounded") if grounding else None
            ),
        })
        telemetry.finish()
        checkpoint_snapshot = (
            checkpoint_runtime.snapshot()
            if checkpoint_runtime is not None else checkpoint_snapshot
        )
        write_status(
            "Done", done=True,
            output_language=source_collection.output_language,
            evidence_incomplete=not evidence_saved,
            report_audit=report_audit,
            usage=final_usage,
            usage_accounting=final_accounting,
            claim_grounding=grounding,
            consistency=consistency,
            observability=telemetry.snapshot(),
            quality_review=quality_review,
            **checkpoint_snapshot,
        )
        commit_worker_terminal(
            state="completed",
            reason_code="worker_completed",
            stage="Done",
            usage=final_usage,
            usage_accounting=final_accounting,
            checkpoint_state=checkpoint_snapshot,
        )

    except Exception as exc:
        error_details = traceback.format_exc()
        if isinstance(exc, SourceCollectionError) and exc.diagnostics:
            try:
                save_retrieval_diagnostics(
                    exc.diagnostics, run_id=args.run_id,
                    output_root=DEFAULT_OUTPUT_ROOT,
                )
            except (OSError, TypeError, ValueError) as _diagnostic_err:
                # The traceback remains the terminal artifact if even the
                # structured diagnostic cannot be written. Reporting this
                # separately avoids hiding the original retrieval failure.
                print(
                    f"[worker] save_retrieval_diagnostics failed: {_diagnostic_err}",
                    file=sys.stderr,
                )
        try:
            save_error(error_details, run_id=args.run_id, output_root=DEFAULT_OUTPUT_ROOT)
        except Exception as _save_err:
            print(f"[worker] save_error failed: {_save_err}", file=sys.stderr)
        print(error_details, file=sys.stderr, flush=True)
        error_usage = snapshot_usage(emit=True)
        error_accounting = _usage_accounting_snapshot(
            error_usage,
            stage="Error",
            run_complete=False,
            # Before Crew construction no LLM request can have started. Once
            # it exists, fail conservatively because a transport error may
            # have reached the provider without returning usage counters.
            in_flight_request_may_have_spent=crew_obj is not None,
        )
        telemetry.finish(exc)
        checkpoint_snapshot = (
            checkpoint_runtime.snapshot()
            if checkpoint_runtime is not None else checkpoint_snapshot
        )
        write_status(
            "Error", done=True, error=str(exc)[:400],
            usage=error_usage,
            usage_accounting=error_accounting,
            observability=telemetry.snapshot(),
            **checkpoint_snapshot,
        )
        commit_worker_terminal(
            state="failed",
            reason_code="worker_exception",
            stage="Error",
            usage=error_usage,
            usage_accounting=error_accounting,
            checkpoint_state=checkpoint_snapshot,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
