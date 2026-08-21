#!/usr/bin/env python
"""Command-line entry point for the commercialization assessment crew.

Delegates to `pipeline_worker` rather than driving the crew itself.

It used to drive the crew inline, and drifted a full generation behind: no
evidence artifacts, no token accounting, no citation screen, no per-domain
degradation, and no way to pass a language or an uploaded paper. Every one of
those was added to the worker and none reached here, because nothing exercised
this path — a shipped entry point that no test and no user ran.

It was also still selecting the report with `tasks_output[-2]`, which the
worker abandoned deliberately: with negative indices, inserting a task in the
middle of the pipeline silently changes which output is persisted as the
report, and nothing raises. The indices happen to coincide at six tasks, which
is exactly why the divergence survived.

Delegating removes the class of problem rather than this instance of it. There
is one implementation of a run, and every entry point starts the same
subprocess against the same outputs directory — which is what the architecture
already claimed.
"""

import argparse
import subprocess
import sys
import warnings

from academic_agent.run_output import DEFAULT_OUTPUT_ROOT, create_run_id

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")

_DEFAULT_TOPIC = "CRISPR gene editing applications in agriculture"


def build_command(run_id: str, args: argparse.Namespace) -> list[str]:
    """The worker invocation for `args`. Separated so it can be tested without
    starting a run that costs money."""
    cmd = [sys.executable, "-m", "academic_agent.pipeline_worker",
           run_id, args.topic.strip()]
    if args.language:
        cmd += ["--language", args.language]
    if args.weight_profile:
        cmd += ["--weight-profile", args.weight_profile]
    if args.paper_json:
        cmd += ["--paper-json", args.paper_json]
    return cmd


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Academic commercialization assessment")
    parser.add_argument(
        "--topic", default=_DEFAULT_TOPIC,
        help="Research topic to analyse (default: %(default)s)")
    parser.add_argument(
        "--language", default="",
        help="Force the report language instead of detecting it from the topic")
    parser.add_argument(
        "--weight-profile", default="",
        help="Force the scoring weight profile instead of detecting it")
    parser.add_argument(
        "--paper-json", default="",
        help="Path to a JSON file holding an extracted PaperContribution")
    return parser


def run() -> None:
    args, _ = _parser().parse_known_args()

    run_id = create_run_id()
    run_dir = DEFAULT_OUTPUT_ROOT / run_id
    print(f"Run {run_id} starting. Output directory: {run_dir}", flush=True)

    # stdout and stderr are inherited on purpose: the worker's stage log is the
    # only progress a terminal user gets, and swallowing it would make a
    # three-minute run look like a hang.
    completed = subprocess.run(build_command(run_id, args), check=False)

    if completed.returncode == 0:
        print(f"Run {run_id} completed. Report saved to "
              f"{run_dir / 'commercialization_report.md'}")
    else:
        # The worker already wrote error.log and printed the traceback; adding
        # another wrapper exception on top would bury it.
        print(f"Run {run_id} failed. See {run_dir / 'error.log'}",
              file=sys.stderr)
    sys.exit(completed.returncode)


# The CrewAI scaffold also ships train/replay/test entry points. They were
# removed rather than fixed: each called a _build_collection() helper that never
# existed, so every one raised NameError on invocation — they had never been
# run. `benchmark.py` covers the evaluation need this project actually has.


if __name__ == "__main__":
    run()
