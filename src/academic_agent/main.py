#!/usr/bin/env python
"""Command-line entry points for the commercialization assessment crew."""

import argparse
import sys
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


def train():
    source_collection = _build_collection()
    try:
        AcademicAgent(source_collection).crew().train(
            n_iterations=int(sys.argv[1]),
            filename=sys.argv[2],
            inputs=source_collection.crew_inputs(),
        )
    except Exception as exc:
        raise RuntimeError(f"An error occurred while training the crew: {exc}") from exc


def replay():
    source_collection = _build_collection()
    try:
        AcademicAgent(source_collection).crew().replay(task_id=sys.argv[1])
    except Exception as exc:
        raise RuntimeError(f"An error occurred while replaying the crew: {exc}") from exc


def test():
    source_collection = _build_collection()
    try:
        AcademicAgent(source_collection).crew().test(
            n_iterations=int(sys.argv[1]),
            eval_llm=sys.argv[2],
            inputs=source_collection.crew_inputs(),
        )
    except Exception as exc:
        raise RuntimeError(f"An error occurred while testing the crew: {exc}") from exc
