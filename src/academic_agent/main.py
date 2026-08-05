#!/usr/bin/env python
"""Command-line entry points for the commercialization assessment crew."""

import argparse
import warnings

from academic_agent.crew import AcademicAgent
from academic_agent.run_output import create_run_id, save_report, save_scores, save_source_collection
from academic_agent.source_pipeline import collect_source_collection

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

_DEFAULT_TOPIC = "CRISPR gene editing applications in agriculture"


def run():
    parser = argparse.ArgumentParser(description="Academic commercialization assessment")
    parser.add_argument(
        "--topic",
        default=_DEFAULT_TOPIC,
        help="Research topic to analyse (default: %(default)s)",
    )
    args, _ = parser.parse_known_args()

    try:
        run_id = create_run_id()
        source_collection = collect_source_collection(args.topic)
        save_source_collection(source_collection.model_dump_json(indent=2), run_id)
        result = AcademicAgent(source_collection).crew().kickoff(
            inputs=source_collection.crew_inputs()
        )
        # tasks_output[-2] = Task 5 (reviewer) = Markdown report
        # tasks_output[-1] = Task 6 (scorer)   = JSON scorecard
        tasks_output = getattr(result, "tasks_output", None) or []
        if len(tasks_output) >= 2:
            report_raw = tasks_output[-2].raw
            scores_raw = tasks_output[-1].raw
        else:
            report_raw = result.raw
            scores_raw = None
        run_id, report_path = save_report(report_raw, run_id=run_id)
        if scores_raw:
            save_scores(scores_raw, run_id=run_id)
        print(f"Run {run_id} completed. Report saved to {report_path}")
    except Exception as exc:
        raise RuntimeError(f"An error occurred while running the crew: {exc}") from exc


# The CrewAI scaffold also ships train/replay/test entry points. They were
# removed here rather than fixed: each called a _build_collection() helper that
# never existed, so every one of them raised NameError on invocation — they had
# never been run. Restoring them would mean re-running the full source
# collection on each invocation, which is neither cheap nor what those commands
# are for. `benchmark.py` covers the evaluation need this project actually has.
