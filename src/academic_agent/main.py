#!/usr/bin/env python
"""Command-line entry points for the commercialization assessment crew."""

import sys
import warnings

from academic_agent.crew import AcademicAgent
from academic_agent.run_output import create_run_id, save_report, save_source_collection
from academic_agent.source_pipeline import collect_source_collection

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

_DEFAULT_TOPIC = "CRISPR gene editing applications in agriculture"


def _build_collection():
    return collect_source_collection(_DEFAULT_TOPIC)


def run():
    try:
        run_id = create_run_id()
        source_collection = _build_collection()
        save_source_collection(source_collection.model_dump_json(indent=2), run_id)
        result = AcademicAgent(source_collection).crew().kickoff(
            inputs=source_collection.crew_inputs()
        )
        # tasks_output[-2] = Task 5 (reviewer) = Markdown report
        # tasks_output[-1] = Task 6 (scorer)   = JSON scorecard
        tasks_output = getattr(result, "tasks_output", None) or []
        report_raw = tasks_output[-2].raw if len(tasks_output) >= 2 else result.raw
        run_id, report_path = save_report(report_raw, run_id=run_id)
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
