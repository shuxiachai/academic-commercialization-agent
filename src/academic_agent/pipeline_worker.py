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
        save_report,
        save_reviewer_notes,
        save_scores,
        save_source_collection,
    )
    from academic_agent.pdf_extractor import PaperContribution, paper_to_evidence_source
    from academic_agent.source_pipeline import collect_source_collection

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
    ) -> None:
        try:
            # Preserve sticky fields (topic, source_counts) set by earlier calls.
            try:
                existing = json.loads(status_path.read_text(encoding="utf-8"))
            except Exception as _e:
                print(f"[worker] write_status: could not read existing status: {_e}", file=sys.stderr)
                existing = {}
            data: dict = {
                "stage": stage,
                "done": done,
                "error": error,
                "output_language": output_language,
            }
            for sticky in ("topic", "source_counts"):
                if existing.get(sticky) is not None:
                    data[sticky] = existing[sticky]
            if source_counts is not None:
                data["source_counts"] = source_counts
            if topic is not None:
                data["topic"] = topic
            status_path.write_text(json.dumps(data), encoding="utf-8")
        except Exception as _e:
            print(f"[worker] write_status failed (stage={stage!r}): {_e}", file=sys.stderr)

    write_status(_STAGE_INITIAL, topic=args.topic)

    try:
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

        source_collection = collect_source_collection(
            args.topic,
            paper_seed=paper_seed,
            extra_market_queries=extra_market_queries,
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
        if args.weight_profile and args.weight_profile != "Auto (detect from topic)":
            source_collection.weight_profile = args.weight_profile
        save_source_collection(source_collection.model_dump_json(indent=2), run_id=args.run_id)
        write_status(
            _PARALLEL_STAGE,
            source_counts={
                "academic": len(source_collection.academic_sources),
                "patent":   len(source_collection.patent_sources),
                "market":   len(source_collection.market_sources),
            },
            output_language=source_collection.output_language,
        )

        parallel_done   = [0]   # counts completions of the 3 async evidence tasks
        sequential_done = [0]   # counts completions of tasks 4/5/6
        _steps_fh = None        # open steps.jsonl handle during kickoff (set before kickoff)

        def _write_step(entry: StepEntry) -> None:
            try:
                if _steps_fh is not None:
                    line = json.dumps(entry, ensure_ascii=False) + "\n"
                    _steps_fh.write(line)
                    _steps_fh.flush()
            except Exception as _e:
                print(f"[worker] _write_step failed: {_e}", file=sys.stderr)

        _total_agents = _PARALLEL_COUNT + len(_SEQUENTIAL_STAGES)
        _task_lock = threading.Lock()

        def on_task_complete(_task_output) -> None:
            with _task_lock:
                if parallel_done[0] < _PARALLEL_COUNT:
                    parallel_done[0] += 1
                    agent_idx = parallel_done[0] - 1   # 0 = Academic, 1 = Patent, 2 = Market
                    stage = (
                        _SEQUENTIAL_STAGES[0]
                        if parallel_done[0] == _PARALLEL_COUNT
                        else _PARALLEL_STAGE
                    )
                    _write_step({"agent_idx": agent_idx, "type": "finish", "thought": ""})
                    # All parallel tasks done — signal writer starting
                    if parallel_done[0] == _PARALLEL_COUNT:
                        _write_step({"agent_idx": _PARALLEL_COUNT, "type": "action",
                                     "thought": "", "tool": "reasoning",
                                     "tool_input": "", "result": ""})
                else:
                    sequential_done[0] += 1
                    agent_idx = _PARALLEL_COUNT + sequential_done[0] - 1  # 3, 4, 5
                    seq_idx = sequential_done[0]
                    stage = (
                        _SEQUENTIAL_STAGES[seq_idx]
                        if seq_idx < len(_SEQUENTIAL_STAGES)
                        else _SEQUENTIAL_STAGES[-1]
                    )
                    _write_step({"agent_idx": agent_idx, "type": "finish", "thought": ""})
                    # Signal the next sequential agent starting, if any remain
                    next_idx = agent_idx + 1
                    if next_idx < _total_agents:
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
                    idx = agent_role_to_idx.get(event.agent_role or "", parallel_done[0] + sequential_done[0])
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
                    idx = agent_role_to_idx.get(event.agent_role or "", parallel_done[0] + sequential_done[0])
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

        # Crew has 6 tasks (0-indexed): academic(0) patent(1) market(2)
        # report(3) review(4) scoring(5).  Use explicit indices so a new task
        # inserted in the middle doesn't silently corrupt which output we read.
        _IDX_REVIEW  = 4   # report_review_task
        _IDX_SCORING = 5   # commercialization_scoring_task
        tasks_output = getattr(result, "tasks_output", None) or []
        if len(tasks_output) > _IDX_SCORING:
            report_raw = tasks_output[_IDX_REVIEW].raw
            scores_raw = tasks_output[_IDX_SCORING].raw
        elif len(tasks_output) == _IDX_SCORING:
            report_raw = tasks_output[_IDX_REVIEW].raw
            scores_raw = None
        elif len(tasks_output) >= 2:
            report_raw = tasks_output[-1].raw
            scores_raw = None
        else:
            report_raw = result.raw
            scores_raw = None

        m_rev = re.search(r"(?m)^##\s+Reviewer Notes\b", report_raw, re.IGNORECASE) if report_raw else None
        if m_rev:
            save_reviewer_notes(report_raw[m_rev.start():].strip(), run_id=args.run_id)
            report_raw = report_raw[: m_rev.start()].rstrip()

        if report_raw is not None:
            save_report(report_raw, run_id=args.run_id)

        if scores_raw:
            save_scores(scores_raw, run_id=args.run_id)

        write_status("Done", done=True, output_language=source_collection.output_language)

    except Exception as exc:
        error_details = traceback.format_exc()
        try:
            save_error(error_details, run_id=args.run_id)
        except Exception as _save_err:
            print(f"[worker] save_error failed: {_save_err}", file=sys.stderr)
        print(error_details, file=sys.stderr, flush=True)
        write_status("Error", done=True, error=str(exc)[:400])
        sys.exit(1)


if __name__ == "__main__":
    main()
