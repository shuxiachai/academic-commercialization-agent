"""Run a fixture-only one/four/six-node agent-topology ablation.

The command is plan-only unless ``--execute`` is present. That asymmetry is
intentional: listing a ninety-cell study should be cheap and safe, while a
typo must not turn into ninety paid model runs.
"""


import argparse
import hashlib
import json
import os
import re
import subprocess
import time
import traceback
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from collections.abc import Callable, Sequence


import benchmark_fixtures
from ablation_check import analyse_report, reviewer_correction_count, write_summaries
from benchmark import TOPICS, _slug

# CrewAI 1.14.7 inspects a guardrail's raw runtime signature without resolving
# postponed annotations. Enabling ``from __future__ import annotations`` makes
# ``tuple[bool, Any]`` a string and Task construction rejects an otherwise
# correct callable. Keep annotations eager in this module until that pinned
# vendor version changes; the production guardrails rely on the same behaviour.


ABLATION_ROOT = Path(__file__).parent / "outputs" / "ablation"
VARIANTS = ("monolith", "specialists_writer", "full")
TOPOLOGY_NODES = {"monolith": 1, "specialists_writer": 4, "full": 6}
DEFAULT_PAUSE_SECONDS = 15.0


@dataclass(frozen=True)
class ScheduleCell:
    schedule_index: int
    block_id: str
    position: int
    num: str
    topic: str
    expected_trl_range: tuple[int, int]
    industry: str
    rep: int
    variant: str


@dataclass
class GuardrailAttempt:
    task_name: str
    passed: bool
    before_chars: int
    after_chars: int
    before_sha256_16: str
    after_sha256_16: str
    failure: str
    # Raw text stays in memory only long enough to calculate first-attempt
    # report metrics. Persisting every failed completion would duplicate large,
    # paid artifacts and encourage post-hoc qualitative cherry-picking.
    raw_before: str

    def summary(self) -> dict[str, Any]:
        return {
            "task_name": self.task_name,
            "passed": self.passed,
            "before_chars": self.before_chars,
            "after_chars": self.after_chars,
            "before_sha256_16": self.before_sha256_16,
            "after_sha256_16": self.after_sha256_16,
            "failure": self.failure,
        }


class GuardrailRecorder:
    """Observe the guardrail seam without changing its return value."""

    def __init__(self) -> None:
        self.attempts: dict[str, list[GuardrailAttempt]] = {}

    def wrap(
        self,
        task_name: str,
        guardrail: Callable[[Any], tuple[bool, Any]],
    ) -> Callable[[Any], tuple[bool, Any]]:
        def recorded(output: Any) -> tuple[bool, Any]:
            before = str(getattr(output, "raw", "") or "")
            passed, payload = guardrail(output)
            after = str(getattr(output, "raw", "") or "")
            attempt = GuardrailAttempt(
                task_name=task_name,
                passed=bool(passed),
                before_chars=len(before),
                after_chars=len(after),
                before_sha256_16=_digest(before),
                after_sha256_16=_digest(after),
                failure="" if passed else str(payload)[:2_000],
                raw_before=before,
            )
            self.attempts.setdefault(task_name, []).append(attempt)
            return passed, payload

        return recorded

    def instrument(self, tasks: Sequence[Any]) -> None:
        for index, task in enumerate(tasks, start=1):
            guardrail = getattr(task, "guardrail", None)
            if not callable(guardrail):
                continue
            task_name = str(getattr(task, "name", "") or f"task_{index}")
            task.guardrail = self.wrap(task_name, guardrail)

    def task_summary(self, task_name: str) -> dict[str, Any]:
        attempts = self.attempts.get(task_name, [])
        failures = sum(not attempt.passed for attempt in attempts)
        return {
            "calls": len(attempts),
            "failures": failures,
            # One initial call is not a retry. A failed call that aborts without
            # another attempt remains a failure but contributes zero retries.
            "retries": max(0, len(attempts) - 1),
            "attempts": [attempt.summary() for attempt in attempts],
        }

    def summaries(self) -> dict[str, dict[str, Any]]:
        return {name: self.task_summary(name) for name in self.attempts}


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _commit_sha() -> str:
    """Best-effort provenance; experiment execution must not depend on Git."""

    try:
        completed = subprocess.run(  # noqa: S603 - fixed executable and arguments
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).parent,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError:
        return "unknown"
    return completed.stdout.strip() if completed.returncode == 0 else "unknown"


def build_schedule(
    cases: Sequence[tuple[str, str, tuple[int, int], str]],
    *,
    repeat: int,
    variants: Sequence[str] = VARIANTS,
) -> list[ScheduleCell]:
    """Deterministic Latin-square order, balanced over 10 x 3 full blocks."""

    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    unknown = set(variants) - set(VARIANTS)
    if unknown:
        raise ValueError(f"unknown variants: {', '.join(sorted(unknown))}")
    if len(set(variants)) != len(variants):
        raise ValueError("variants must not contain duplicates")

    cells: list[ScheduleCell] = []
    schedule_index = 0
    for case_index, (num, topic, trl_range, industry) in enumerate(cases):
        for rep in range(1, repeat + 1):
            offset = (case_index + rep - 1) % len(variants)
            ordered = list(variants[offset:]) + list(variants[:offset])
            block_id = f"{num}-r{rep}"
            for position, variant in enumerate(ordered, start=1):
                schedule_index += 1
                cells.append(ScheduleCell(
                    schedule_index=schedule_index,
                    block_id=block_id,
                    position=position,
                    num=num,
                    topic=topic,
                    expected_trl_range=trl_range,
                    industry=industry,
                    rep=rep,
                    variant=variant,
                ))
    return cells


def _all_sources(collection: Any) -> list[Any]:
    return (
        list(collection.academic_sources)
        + list(collection.patent_sources)
        + list(collection.market_sources)
    )


def _localized_headings(collection: Any) -> tuple[str, ...] | None:
    return tuple(collection.localized_headings) if collection.localized_headings else None


def make_monolith_report_guardrail(
    collection: Any,
) -> Callable[[Any], tuple[bool, Any]]:
    """Apply the production report policy directly to the frozen registry.

    Production obtains these sources from Tasks 1-3's validated Pydantic
    outputs. The monolith has no intermediate tasks, so requiring that route
    would either add three hidden nodes or silently weaken its guardrail. This
    adapter changes only how the immutable registry arrives; normalisation and
    blocking checks delegate to the exact production implementation.
    """

    from academic_agent.evidence import _normalize_and_find_blocking_errors
    from crewai.tasks.task_output import TaskOutput

    allowed_sources = {source.source_id: source for source in _all_sources(collection)}
    headings = _localized_headings(collection)

    def validate(output: TaskOutput) -> tuple[bool, Any]:
        if not allowed_sources:
            return False, "No validated evidence sources are available."
        if len(str(getattr(output, "raw", "") or "").strip()) < 500:
            return False, "Final report is too short to be usable."
        normalized, errors = _normalize_and_find_blocking_errors(
            output.raw,
            allowed_sources,
            {},
            required_headings=headings,
            output_language=collection.output_language,
        )
        output.raw = normalized
        if errors:
            return (
                False,
                "Final report has blocking validation errors:\n- " + "\n- ".join(errors),
            )
        return True, output

    return validate


_MONOLITH_DESCRIPTION = """
Produce a comprehensive commercialization assessment for {display_topic} by
working directly from all three immutable, code-validated source registries.
You are the only analysis node: no specialist summaries, reviewer, or scorer
will run before or after you.

Academic sources: {academic_sources_json}
Patent sources: {patent_sources_json}
Patent assignees exposed by retrieval: {patent_assignees_json}
Market sources: {market_sources_json}
Queries executed by code:
- academic: {academic_search_queries_json}
- patent: {patent_search_queries_json}
- market: {market_search_queries_json}

LANGUAGE REQUIREMENT: Write the entire report in {output_language}. Use these
headings exactly and in this order:
{localized_headings}

Evidence coverage for this run:
{retrieval_notice}

Evidence and citation rules:
- Use only facts and figures stated in the registries above.
- Cite every factual, numerical, patent, company, market, and maturity claim on
  the same line with source IDs such as [A1], [P2], and [M3].
- Never invent or alter a title, URL, DOI, applicant, publisher, date, market
  size, funding amount, customer, patent record, or legal status.
- Preserve the distinction between observed facts, estimates, and analyst
  inferences. State evidence gaps instead of filling them with prior knowledge.
- Treat search snippets as fragments and company disclosures as attributed
  first-party claims, not independent confirmation.
- Patent observations are preliminary landscape research, not legal advice or
  a freedom-to-operate opinion.
- End with a References section containing each cited validated source exactly
  once, including its validated URL or DOI. Add no uncited sources.
"""

_MONOLITH_EXPECTED = """
A complete Markdown commercialization assessment in {output_language}, using
the supplied headings in order. Every material claim has an inline validated
[source_id] citation and every citation resolves exactly once in References.
Do not include a scorecard or JSON wrapper.
"""


def _max_rpm() -> int:
    raw = os.getenv("MAX_RPM", "6")
    try:
        return int(raw)
    except ValueError:
        raise ValueError(f"MAX_RPM environment variable must be an integer, got {raw!r}") from None


def build_variant_crew(
    variant: str,
    collection: Any,
) -> tuple[Any, str]:
    """Build one treatment while leaving the production control untouched."""

    from academic_agent.crew import AcademicAgent
    from academic_agent.llm_config import create_llm
    from crewai import Agent, Crew, Process, Task

    if variant == "monolith":
        agent = Agent(
            role="Academic Commercialization Generalist",
            goal=(
                "Produce an evidence-bounded investment-facing commercialization "
                "assessment directly from validated academic, patent, and market sources."
            ),
            backstory=(
                "You combine technology-transfer, patent-landscape, and market-analysis "
                "skills, but you have no external tools and may use only the supplied registry."
            ),
            # Match the production report writer's free-text LLM construction
            # exactly. Forcing temperature zero here would confound topology
            # with a model-setting change even though it looks more deterministic.
            llm=create_llm(),
            verbose=True,
            allow_delegation=False,
        )
        task = Task(
            name="monolith_report_task",
            description=_MONOLITH_DESCRIPTION,
            expected_output=_MONOLITH_EXPECTED,
            agent=agent,
            guardrail=make_monolith_report_guardrail(collection),
            guardrail_max_retries=1,
            markdown=True,
        )
        return (
            Crew(
                agents=[agent],
                tasks=[task],
                process=Process.sequential,
                verbose=True,
                max_rpm=_max_rpm(),
            ),
            "monolith_report_task",
        )

    production = AcademicAgent(collection).crew()
    if variant == "full":
        return production, "commercialization_report_task"
    if variant == "specialists_writer":
        # Rebuild only the Crew container. Task and Agent instances are the
        # production first four, so prompts, context wiring, async specialist
        # execution, guardrails, and LLM settings are not experiment copies.
        return (
            Crew(
                agents=list(production.agents[:4]),
                tasks=list(production.tasks[:4]),
                process=Process.sequential,
                verbose=True,
                max_rpm=_max_rpm(),
            ),
            "commercialization_report_task",
        )
    raise ValueError(f"unknown variant: {variant}")


def select_report_outputs(
    variant: str,
    task_outputs: Sequence[Any],
) -> tuple[str | None, str | None]:
    """Select draft and delivered text at the topology boundary."""

    raw = [str(getattr(output, "raw", "") or "") for output in task_outputs]
    if variant == "full":
        draft = raw[3] if len(raw) > 3 else None
        delivered = raw[4] if len(raw) > 4 else draft
        return draft, delivered
    if variant == "specialists_writer":
        delivered = raw[3] if len(raw) > 3 else None
        return delivered, delivered
    if variant == "monolith":
        delivered = raw[0] if raw else None
        return delivered, delivered
    raise ValueError(f"unknown variant: {variant}")


def _without_reviewer_notes(report: str) -> str:
    return report.split("## Reviewer Notes", maxsplit=1)[0].rstrip()


def draft_retention_ratio(draft: str | None, delivered: str | None) -> float | None:
    if not draft or not delivered:
        return None
    final_body = _without_reviewer_notes(delivered)
    return round(SequenceMatcher(None, draft, final_body, autojunk=False).ratio(), 6)


def _task_filename(index: int, output: Any) -> str:
    name = str(getattr(output, "name", "") or f"task-{index}").lower()
    safe = re.sub(r"[^a-z0-9]+", "-", name).strip("-") or f"task-{index}"
    return f"task-{index:02d}-{safe}.txt"


def _cell_directory(root: Path, cell: ScheduleCell) -> Path:
    return root / (
        f"{cell.schedule_index:03d}-{cell.num}-{cell.variant}-r{cell.rep}"
    )


def _fixture(collection_num: str, topic: str) -> tuple[Any, dict[str, Any]]:
    collection = benchmark_fixtures.load(collection_num, _slug(topic))
    if collection is None:
        # This is deliberately the end of the path. Calling live retrieval here
        # would relabel retrieval variance as topology variance.
        raise FileNotFoundError(
            f"no frozen fixture for case {collection_num}; live fallback is forbidden"
        )
    entry = benchmark_fixtures.load_manifest().get("fixtures", {}).get(collection_num)
    if not entry:
        raise ValueError(f"fixture {collection_num} has no manifest provenance")
    return collection, entry

def preflight_fixtures(
    cases: Sequence[tuple[str, str, tuple[int, int], str]],
) -> dict[str, dict[str, Any]]:
    """Validate every frozen input before the first paid request."""

    entries: dict[str, dict[str, Any]] = {}
    for num, topic, _trl_range, _industry in cases:
        _collection_value, entry = _fixture(num, topic)
        entries[num] = entry
    return entries


def _reusable_cell_meta(
    experiment_root: Path,
    cell: ScheduleCell,
    *,
    commit_sha: str,
    fixture_digest: str,
) -> dict[str, Any] | None:
    """Reuse only the same code, frozen input, block, and topology."""

    path = _cell_directory(experiment_root, cell) / "meta.json"
    try:
        meta = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    expected = {
        "status": "success",
        "evidence_mode": "fixture",
        "block_id": cell.block_id,
        "variant": cell.variant,
        "commit_sha": commit_sha,
        "fixture_digest": fixture_digest,
    }
    if all(meta.get(key) == value for key, value in expected.items()):
        return meta
    return None


def run_cell(
    cell: ScheduleCell,
    *,
    experiment_id: str,
    experiment_root: Path,
    commit_sha: str,
) -> dict[str, Any]:
    """Run and persist one paid cell; failures retain usage and diagnostics."""

    collection, fixture_entry = _fixture(cell.num, cell.topic)
    cell_dir = _cell_directory(experiment_root, cell)
    from academic_agent.token_usage import collect_usage

    cell_dir.mkdir(parents=True, exist_ok=True)
    fixture_age = benchmark_fixtures.age_days(cell.num)
    meta: dict[str, Any] = {
        "schema_version": 1,
        "experiment_id": experiment_id,
        "block_id": cell.block_id,
        "schedule_index": cell.schedule_index,
        "position": cell.position,
        "num": cell.num,
        "rep": cell.rep,
        "topic": cell.topic,
        "industry": cell.industry,
        "expected_trl_range": list(cell.expected_trl_range),
        "variant": cell.variant,
        "nodes": TOPOLOGY_NODES[cell.variant],
        "status": "running",
        "evidence_mode": "fixture",
        "fixture_digest": fixture_entry.get("sha256_16", ""),
        "fixture_age_days": None if fixture_age is None else round(fixture_age, 3),
        "commit_sha": commit_sha,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (cell_dir / "validated_sources.json").write_text(
        collection.model_dump_json(indent=2), encoding="utf-8"
    )

    crew_obj: Any | None = None
    recorder = GuardrailRecorder()
    report_task_name = ""
    start = time.perf_counter()
    try:
        crew_obj, report_task_name = build_variant_crew(cell.variant, collection)
        recorder.instrument(crew_obj.tasks)
        result = crew_obj.kickoff(inputs=collection.crew_inputs())
        task_outputs = list(getattr(result, "tasks_output", None) or [])
        draft, delivered = select_report_outputs(cell.variant, task_outputs)
        if not delivered:
            raise RuntimeError("topology completed without a delivered report")

        for index, output in enumerate(task_outputs, start=1):
            (cell_dir / _task_filename(index, output)).write_text(
                str(getattr(output, "raw", "") or ""), encoding="utf-8"
            )
        if draft is not None:
            (cell_dir / "draft_report.md").write_text(draft, encoding="utf-8")
        (cell_dir / "commercialization_report.md").write_text(delivered, encoding="utf-8")

        headings = _localized_headings(collection)
        metrics = analyse_report(
            delivered,
            _all_sources(collection),
            required_headings=headings,
            output_language=collection.output_language,
        )
        meta["report_metrics"] = metrics.as_dict()
        meta["reviewer_corrections"] = (
            reviewer_correction_count(delivered) if cell.variant == "full" else None
        )
        meta["draft_retention_ratio"] = (
            draft_retention_ratio(draft, delivered) if cell.variant == "full" else None
        )
        meta["status"] = "success"
    except Exception as exc:  # noqa: BLE001 - one failed cell must not erase the batch
        meta["status"] = "error_crew"
        meta["error"] = f"{type(exc).__name__}: {exc}"[:2_000]
        (cell_dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
    finally:
        meta["elapsed_seconds"] = round(time.perf_counter() - start, 3)
        if crew_obj is not None:
            meta["usage"] = collect_usage(crew_obj).as_dict()
        meta["guardrails"] = recorder.summaries()
        meta["report_guardrail"] = recorder.task_summary(report_task_name)

        attempts = recorder.attempts.get(report_task_name, [])
        if attempts:
            first_metrics = analyse_report(
                attempts[0].raw_before,
                _all_sources(collection),
                required_headings=_localized_headings(collection),
                output_language=collection.output_language,
            )
            meta["first_attempt_report_metrics"] = first_metrics.as_dict()

        meta["finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        (cell_dir / "meta.json").write_text(
            json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return meta


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    scope = parser.add_mutually_exclusive_group()
    scope.add_argument("--pilot", action="store_true", help="case 03, one repetition")
    scope.add_argument("--full", action="store_true", help="all ten cases")
    parser.add_argument("--only", action="append", default=[], metavar="CASE")
    parser.add_argument("--repeat", type=int, default=None)
    parser.add_argument("--variants", nargs="+", choices=VARIANTS, default=list(VARIANTS))
    parser.add_argument("--execute", action="store_true", help="make paid model calls")
    parser.add_argument("--confirm-full-study", action="store_true")
    parser.add_argument("--experiment-id")
    parser.add_argument("--pause-seconds", type=float, default=DEFAULT_PAUSE_SECONDS)
    parser.add_argument(
        "--stop-after-usd",
        type=float,
        help=(
            "stop after observed complete cost reaches this value; one cell may "
            "cross it, so this is a stop rule rather than a hard provider cap"
        ),
    )
    args = parser.parse_args(argv)
    if args.repeat is not None and args.repeat < 1:
        parser.error("--repeat must be at least 1")
    if args.pause_seconds < 0:
        parser.error("--pause-seconds must not be negative")
    if args.stop_after_usd is not None and args.stop_after_usd <= 0:
        parser.error("--stop-after-usd must be positive")
    if (args.pilot or args.full) and args.only:
        parser.error("--only cannot be combined with --pilot or --full")
    if args.execute and not (args.pilot or args.full or args.only):
        parser.error("paid execution requires an explicit --pilot, --full, or --only scope")
    if args.execute and args.pilot:
        if args.repeat not in (None, 1) or tuple(args.variants) != VARIANTS:
            parser.error("the registered pilot requires one repetition of all three variants")
    if args.execute and args.full:
        if not args.confirm_full_study:
            parser.error("paid --full requires --confirm-full-study")
        if args.repeat not in (None, 3) or tuple(args.variants) != VARIANTS:
            parser.error("the registered full study requires three repetitions of all variants")
    return args


def _selected_cases(args: argparse.Namespace) -> list[tuple[str, str, tuple[int, int], str]]:
    if args.pilot:
        requested = {"03"}
    elif args.only:
        requested = {str(num).zfill(2) for num in args.only}
    else:
        requested = {num for num, *_ in TOPICS}
    selected = [case for case in TOPICS if case[0] in requested]
    missing = requested - {case[0] for case in selected}
    if missing:
        raise ValueError(f"unknown benchmark cases: {', '.join(sorted(missing))}")
    return selected


def _experiment_id(args: argparse.Namespace, commit_sha: str) -> str:
    if args.experiment_id:
        return args.experiment_id
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{commit_sha[:8]}"


def _print_plan(cells: Sequence[ScheduleCell], *, execute: bool) -> None:
    mode = "PAID EXECUTION" if execute else "PLAN ONLY — no model calls"
    print(f"Agent-topology ablation: {mode}")
    print(f"cells: {len(cells)}")
    for cell in cells:
        print(
            f"  {cell.schedule_index:03d}  {cell.block_id:<7}  "
            f"position={cell.position}  {cell.variant:<20}  {cell.topic}"
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    cases = _selected_cases(args)
    repeat = args.repeat if args.repeat is not None else (3 if args.full else 1)
    cells = build_schedule(cases, repeat=repeat, variants=args.variants)
    _print_plan(cells, execute=args.execute)
    if not args.execute:
        print("Add --execute for the paid pilot. No files or API calls were made.")
        return 0

    fixture_entries = preflight_fixtures(cases)
    commit_sha = _commit_sha()
    experiment_id = _experiment_id(args, commit_sha)
    experiment_root = ABLATION_ROOT / experiment_id
    experiment_root.mkdir(parents=True, exist_ok=True)
    cumulative_cost = 0.0

    for index, cell in enumerate(cells):
        fixture_digest = str(fixture_entries[cell.num].get("sha256_16", ""))
        meta = _reusable_cell_meta(
            experiment_root,
            cell,
            commit_sha=commit_sha,
            fixture_digest=fixture_digest,
        )
        reused = meta is not None
        if reused:
            print(
                f"[{cell.schedule_index}/{len(cells)}] {cell.block_id} "
                f"{cell.variant} already succeeded — reusing",
                flush=True,
            )
        else:
            print(
                f"[{cell.schedule_index}/{len(cells)}] {cell.block_id} "
                f"{cell.variant} starting",
                flush=True,
            )
            meta = run_cell(
                cell,
                experiment_id=experiment_id,
                experiment_root=experiment_root,
                commit_sha=commit_sha,
            )
        usage = meta.get("usage") or {}
        cost = usage.get("cost_usd")
        complete = usage.get("cost_complete")
        if isinstance(cost, (int, float)):
            cumulative_cost += float(cost)
        print(
            f"[{cell.schedule_index}/{len(cells)}] {meta['status']}  "
            f"{meta['elapsed_seconds']}s  observed cost=${cumulative_cost:.4f}",
            flush=True,
        )

        if args.stop_after_usd is not None:
            if complete is not True:
                print("Stopping: cost is incomplete, so the USD stop rule cannot be trusted.")
                break
            if cumulative_cost >= args.stop_after_usd:
                print(f"Stopping: observed cost reached ${args.stop_after_usd:.4f}.")
                break
        if not reused and index < len(cells) - 1 and args.pause_seconds:
            time.sleep(args.pause_seconds)

    summary_path, pairwise_path, _ = write_summaries(experiment_root)
    print(f"summary: {summary_path}")
    print(f"paired deltas: {pairwise_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
