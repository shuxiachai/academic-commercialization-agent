"""Subprocess worker: runs the full analysis pipeline for a single run.

Invoked as:
    python -m academic_agent.pipeline_worker <run_id> <topic>

Writes status.json to the run directory so the parent process can poll
for progress without shared memory. Results are saved to the run directory
via the standard run_output helpers.
"""
import argparse
import json
import re
import sys
import traceback

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

_STAGE_INITIAL = "Source Collection & Validation"
_TASK_STAGE_LABELS = [
    "Agent 1 — Academic Literature Analysis",
    "Agent 2 — Patent Landscape Analysis",
    "Agent 3 — Market Intelligence Analysis",
    "Agent 4 — Report Writing",
    "Agent 5 — Quality Review & Citation Check",
    "Agent 6 — Commercialization Scoring",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("topic")
    args = parser.parse_args()

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
        write_status(_TASK_STAGE_LABELS[0], output_language=source_collection.output_language)

        completed_tasks = [0]

        def on_task_complete(_task_output) -> None:
            completed_tasks[0] += 1
            idx = completed_tasks[0]
            stage = (
                _TASK_STAGE_LABELS[idx]
                if idx < len(_TASK_STAGE_LABELS)
                else _TASK_STAGE_LABELS[-1]
            )
            write_status(stage, output_language=source_collection.output_language)

        result = AcademicAgent(
            source_collection,
            task_callback=on_task_complete,
        ).crew().kickoff(inputs=source_collection.crew_inputs())

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
