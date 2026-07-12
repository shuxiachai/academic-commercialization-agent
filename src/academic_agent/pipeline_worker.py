"""Subprocess worker: runs the full analysis pipeline for a single run.

Invoked as:
    python -m academic_agent.pipeline_worker <run_id> <topic>

Writes status.json for stage progress and steps.jsonl for the live agent
log, both polled by the parent process (app.py) without shared memory.
"""
import argparse
import json
import re
import sys
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
    args = parser.parse_args()

    from crewai.events.event_bus import crewai_event_bus
    from crewai.events.types.agent_events import AgentExecutionCompletedEvent
    from crewai.events.types.tool_usage_events import (
        ToolUsageFinishedEvent,
        ToolUsageStartedEvent,
    )

    from academic_agent.crew import AcademicAgent
    from academic_agent.run_output import (
        DEFAULT_OUTPUT_ROOT,
        save_error,
        save_report,
        save_reviewer_notes,
        save_scores,
        save_source_collection,
    )
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
    ) -> None:
        try:
            status_path.write_text(
                json.dumps({
                    "stage": stage,
                    "done": done,
                    "error": error,
                    "output_language": output_language,
                }),
                encoding="utf-8",
            )
        except Exception:
            pass

    write_status(_STAGE_INITIAL)

    try:
        source_collection = collect_source_collection(args.topic)
        save_source_collection(source_collection.model_dump_json(indent=2), run_id=args.run_id)
        write_status(_PARALLEL_STAGE, output_language=source_collection.output_language)

        parallel_done   = [0]   # counts completions of the 3 async evidence tasks
        sequential_done = [0]   # counts completions of tasks 4/5/6

        def on_task_complete(_task_output) -> None:
            if parallel_done[0] < _PARALLEL_COUNT:
                parallel_done[0] += 1
                stage = (
                    _SEQUENTIAL_STAGES[0]   # all evidence done → report writing next
                    if parallel_done[0] == _PARALLEL_COUNT
                    else _PARALLEL_STAGE    # still collecting
                )
            else:
                sequential_done[0] += 1
                idx = sequential_done[0]
                stage = (
                    _SEQUENTIAL_STAGES[idx]
                    if idx < len(_SEQUENTIAL_STAGES)
                    else _SEQUENTIAL_STAGES[-1]
                )
            write_status(stage, output_language=source_collection.output_language)

        def _write_step(entry: dict) -> None:
            try:
                with open(steps_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except Exception:
                pass

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

        with crewai_event_bus.scoped_handlers():

            @crewai_event_bus.on(ToolUsageStartedEvent)
            def on_tool_started(source, event: ToolUsageStartedEvent) -> None:
                idx = agent_role_to_idx.get(event.agent_role or "", parallel_done[0])
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
                idx = agent_role_to_idx.get(event.agent_role or "", parallel_done[0])
                _write_step({
                    "agent_idx": idx,
                    "type": "result",
                    "tool": event.tool_name or "",
                    "result": str(event.output or "").strip()[:400],
                })

            @crewai_event_bus.on(AgentExecutionCompletedEvent)
            def on_agent_done(source, event: AgentExecutionCompletedEvent) -> None:
                role = getattr(event.agent, "role", "") if event.agent else ""
                idx = agent_role_to_idx.get(role, parallel_done[0])
                _write_step({
                    "agent_idx": idx,
                    "type": "finish",
                    "thought": "",
                })

            result = crew_obj.kickoff(inputs=source_collection.crew_inputs())

        tasks_output = getattr(result, "tasks_output", None) or []
        if len(tasks_output) >= 2:
            report_raw = tasks_output[-2].raw
            scores_raw = tasks_output[-1].raw
        else:
            report_raw = result.raw
            scores_raw = None

        m_rev = re.search(r"(?m)^##\s+Reviewer Notes\b", report_raw, re.IGNORECASE)
        if m_rev:
            save_reviewer_notes(report_raw[m_rev.start():].strip(), run_id=args.run_id)
            report_raw = report_raw[: m_rev.start()].rstrip()

        save_report(report_raw, run_id=args.run_id)

        if scores_raw:
            save_scores(scores_raw, run_id=args.run_id)

        write_status("Done", done=True, output_language=source_collection.output_language)

    except Exception as exc:
        error_details = traceback.format_exc()
        save_error(error_details, run_id=args.run_id)
        print(error_details, file=sys.stderr, flush=True)
        first_line = next((ln.strip() for ln in str(exc).splitlines() if ln.strip()), str(exc))
        write_status("Error", done=True, error=first_line)
        sys.exit(1)


if __name__ == "__main__":
    main()
