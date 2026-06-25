#!/usr/bin/env python
import sys
import warnings

from academic_agent.crew import AcademicAgent
from academic_agent.run_output import save_report

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")


def run():
    inputs = {
        "research_topic": "CRISPR gene editing applications in agriculture",
    }

    try:
        result = AcademicAgent().crew().kickoff(inputs=inputs)
        run_id, report_path = save_report(result.raw)
        print(f"Run {run_id} completed. Report saved to {report_path}")
    except Exception as exc:
        raise RuntimeError(f"An error occurred while running the crew: {exc}") from exc


def train():
    inputs = {
        "research_topic": "CRISPR gene editing applications in agriculture",
    }
    try:
        AcademicAgent().crew().train(
            n_iterations=int(sys.argv[1]),
            filename=sys.argv[2],
            inputs=inputs,
        )
    except Exception as exc:
        raise RuntimeError(f"An error occurred while training the crew: {exc}") from exc


def replay():
    try:
        AcademicAgent().crew().replay(task_id=sys.argv[1])
    except Exception as exc:
        raise RuntimeError(f"An error occurred while replaying the crew: {exc}") from exc


def test():
    inputs = {
        "research_topic": "CRISPR gene editing applications in agriculture",
    }
    try:
        AcademicAgent().crew().test(
            n_iterations=int(sys.argv[1]),
            eval_llm=sys.argv[2],
            inputs=inputs,
        )
    except Exception as exc:
        raise RuntimeError(f"An error occurred while testing the crew: {exc}") from exc
