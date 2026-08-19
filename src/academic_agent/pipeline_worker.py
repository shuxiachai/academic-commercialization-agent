"""Subprocess worker: runs the full analysis pipeline for a single run.

Invoked as:
    python -m academic_agent.pipeline_worker <run_id> <topic>

Writes status.json for stage progress and steps.jsonl for the live agent
log, both polled by the parent process (app.py) without shared memory.
"""
import argparse
import json
import os
import re
import sys
import threading
import traceback

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


def _merge_status_fields(
    existing: dict,
    *,
    stage: str,
    done: bool,
    error: str | None,
    output_language: str | None,
    source_counts: dict | None,
    topic: str | None,
) -> dict:
    """Build the next status.json payload from the previous one plus updates.

    status.json is rewritten wholesale on every stage transition, but topic
    and source_counts are set once early on and must survive every later call
    that does not pass them again — otherwise a client polling mid-run would
    see the topic disappear the moment the pipeline moved past the stage that
    first reported it.
    """
    data: dict = {
        "stage": stage, "done": done, "error": error, "output_language": output_language,
    }
    # evidence_incomplete is sticky for the same reason topic is: it is set
    # once, mid-run, by the only code path that can discover it, and every
    # later status write would otherwise erase the warning it carries.
    for sticky in ("topic", "source_counts", "evidence_incomplete", "failed_domains", "usage",
                   "claim_grounding", "consistency"):
        if existing.get(sticky) is not None:
            data[sticky] = existing[sticky]
    if source_counts is not None:
        data["source_counts"] = source_counts
    if topic is not None:
        data["topic"] = topic
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("topic")
    parser.add_argument("--language", default="", help="Force output language (overrides auto-detect)")
    parser.add_argument("--weight-profile", default="", help="Force scoring weight profile (overrides auto-detect)")
    parser.add_argument("--paper-json", default="", help="Path to JSON file containing PaperContribution data")
    args = parser.parse_args()

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
    from academic_agent.source_pipeline import SourceCollectionError, collect_source_collection
    from academic_agent.token_usage import collect_usage

    run_dir = DEFAULT_OUTPUT_ROOT / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    status_path = run_dir / "status.json"
    steps_path  = run_dir / "steps.jsonl"

    def write_status(
        stage: str,
        *,
        done: bool = False,
        error: str | None = None,
        output_language: str | None = None,
        source_counts: dict | None = None,
        topic: str | None = None,
        evidence_incomplete: bool | None = None,
        failed_domains: list[str] | None = None,
        usage: dict | None = None,
        claim_grounding: dict | None = None,
        consistency: dict | None = None,
    ) -> None:
        try:
            try:
                existing = json.loads(status_path.read_text(encoding="utf-8"))
            except Exception as _e:
                print(f"[worker] write_status: could not read existing status: {_e}", file=sys.stderr)
                existing = {}
            data = _merge_status_fields(
                existing, stage=stage, done=done, error=error,
                output_language=output_language, source_counts=source_counts, topic=topic,
            )
            if evidence_incomplete is not None:
                data["evidence_incomplete"] = evidence_incomplete
            if failed_domains is not None:
                data["failed_domains"] = failed_domains
            if usage is not None:
                data["usage"] = usage
            if claim_grounding is not None:
                data["claim_grounding"] = claim_grounding
            if consistency is not None:
                data["consistency"] = consistency
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

    write_status(_STAGE_INITIAL, topic=args.topic)

    # Bound before the try so the failure path can still account for a run
    # that died after spending money. A crash halfway through is exactly when
    # someone wants to know what it cost, and it is also the only case where
    # this name might never be assigned.
    crew_obj = None

    def snapshot_usage() -> dict | None:
        if crew_obj is None:
            return None
        usage = collect_usage(crew_obj)
        if not usage.agents and usage.collection_error is None:
            return None
        cost = "unknown" if usage.cost_usd is None else f"${usage.cost_usd:.4f}"
        if not usage.cost_complete:
            cost += f" (at least; unpriced: {', '.join(usage.unpriced_models)})"
        print(f"[usage] {usage.total_tokens} tokens over {usage.total_requests} "
              f"requests, {cost}", flush=True)
        return usage.as_dict()

    try:
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
        if args.paper_json:
            import pathlib
            _pj = pathlib.Path(args.paper_json)
            if _pj.exists():
                _pc_data = json.loads(_pj.read_text(encoding="utf-8"))
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
        source_collection = collect_source_collection(
            args.topic,
            paper_seed=paper_seed,
            extra_market_queries=extra_market_queries,
            weight_profile=requested_profile,
        )
        if args.language and args.language != "Auto (detect from topic)":
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
        save_source_collection(
            source_collection.model_dump_json(indent=2), run_id=args.run_id, output_root=DEFAULT_OUTPUT_ROOT,
        )
        if source_collection.failed_domains:
            # An empty domain reads as a fact about the technology; this says
            # it is a fact about the infrastructure instead. Logged and put on
            # the status so the distinction reaches whoever reads the report.
            for _domain, _why in source_collection.failed_domains.items():
                print(f"[worker] {_domain} retrieval failed, continuing without it: "
                      f"{_why[:200]}", file=sys.stderr, flush=True)

        write_status(
            _PARALLEL_STAGE,
            source_counts={
                "academic": len(source_collection.academic_sources),
                "patent":   len(source_collection.patent_sources),
                "market":   len(source_collection.market_sources),
            },
            output_language=source_collection.output_language,
            failed_domains=sorted(source_collection.failed_domains) or None,
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
            write_status(stage, output_language=source_collection.output_language)

        crew_obj = AcademicAgent(
            source_collection,
            task_callback=on_task_complete,
        ).crew()

        # Build role → agent index mapping for event handlers.
        # CrewAI 1.14.7 uses AgentExecutor (event-bus-based) by default;
        # step_callback is only invoked by the deprecated CrewAgentExecutor.
        agent_role_to_idx: dict[str, int] = {
            a.role: i for i, a in enumerate(crew_obj.agents)
        }

        _sf = open(steps_path, "a", encoding="utf-8")
        _steps_fh = _sf
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

                # Pre-seed "started" action entries for all three parallel agents so
                # Phase 1 shows live activity even when agent events do not fire
                # consistently across threads. Empty tool signals "analyzing" state.
                for _i in range(_PARALLEL_COUNT):
                    _write_step({"agent_idx": _i, "type": "action", "thought": "",
                                 "tool": "", "tool_input": "", "result": ""})

                result = crew_obj.kickoff(inputs=source_collection.crew_inputs())
        finally:
            _steps_fh = None
            _sf.close()

        tasks_output = getattr(result, "tasks_output", None) or []

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
        grounding = save_claim_grounding(
            tasks_output, run_id=args.run_id, output_root=DEFAULT_OUTPUT_ROOT)
        if grounding:
            print(f"[grounding] {grounding['checked']} checkable claims, "
                  f"{grounding['ungrounded']} with a figure absent from the cited "
                  f"source, {grounding['unverifiable']} unverifiable", flush=True)

        report_raw, scores_raw = _select_report_and_scores(tasks_output, result.raw)

        m_rev = re.search(r"(?m)^##\s+Reviewer Notes\b", report_raw, re.IGNORECASE) if report_raw else None
        if m_rev:
            save_reviewer_notes(
                report_raw[m_rev.start():].strip(), run_id=args.run_id, output_root=DEFAULT_OUTPUT_ROOT,
            )
            report_raw = report_raw[: m_rev.start()].rstrip()

        if report_raw is not None:
            save_report(report_raw, run_id=args.run_id, output_root=DEFAULT_OUTPUT_ROOT)

        if scores_raw:
            save_scores(scores_raw, run_id=args.run_id, output_root=DEFAULT_OUTPUT_ROOT)

        # Only possible here: the reviewer never sees the scorecard and the
        # scorer never sees the reviewed report, so this is the first moment
        # anything holds both.
        consistency = save_consistency(
            report_raw or "", scores_raw, run_id=args.run_id,
            output_root=DEFAULT_OUTPUT_ROOT)
        if consistency and consistency.get("blockers"):
            print(f"[consistency] {consistency['blockers']} finding(s): the "
                  f"report's recommendation disagrees with its own scorecard",
                  flush=True)

        write_status(
            "Done", done=True,
            output_language=source_collection.output_language,
            evidence_incomplete=not evidence_saved,
            usage=snapshot_usage(),
            claim_grounding=grounding,
            consistency=consistency,
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
        write_status("Error", done=True, error=str(exc)[:400], usage=snapshot_usage())
        sys.exit(1)


if __name__ == "__main__":
    main()
