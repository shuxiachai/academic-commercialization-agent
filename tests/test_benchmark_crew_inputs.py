"""The benchmark must give the crew every input production gives it.

When Decision Context added {decision_context_json} and related placeholders
to the Writer and Reviewer templates, pipeline_worker started supplying
them and benchmark.py did not. Every live benchmark run afterwards failed at
kickoff ("Missing required template variable 'decision_context_json'"), and
the first held-out batch stopped on three such failures. No test runs a real
crew, so these tests compare the inputs with the templates directly.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import benchmark
import benchmark_fixtures
from academic_agent.run_spec import RunSpec

_CONFIG = Path(__file__).resolve().parents[1] / "src" / "academic_agent" / "config"
# The pattern CrewAI interpolates; JSON examples in the templates contain
# quotes or spaces inside their braces and so never match it.
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def _template_placeholders() -> set[str]:
    names: set[str] = set()
    for name in ("tasks.yaml", "agents.yaml"):
        names |= set(_PLACEHOLDER.findall((_CONFIG / name).read_text(encoding="utf-8")))
    return names


def _fixture_collection():
    num, topic, *_ = benchmark.TOPICS[0]
    collection = benchmark_fixtures.load(num, benchmark._slug(topic))
    assert collection is not None, "committed fixture missing"
    return topic, collection


class BenchmarkCrewInputTests(unittest.TestCase):

    def test_every_template_placeholder_is_supplied(self):
        """Fails as soon as a template gains a variable the runner lacks."""
        _topic, collection = _fixture_collection()
        missing = _template_placeholders() - set(benchmark._crew_inputs(collection))
        self.assertFalse(missing, f"benchmark kickoff would fail on: {sorted(missing)}")

    def test_inputs_equal_production_for_a_run_without_decision_context(self):
        """Same dictionary pipeline_worker builds: collection + spec decision inputs."""
        topic, collection = _fixture_collection()
        production = collection.crew_inputs()
        production.update(RunSpec(topic=topic).decision_crew_inputs())
        self.assertEqual(benchmark._crew_inputs(collection), production)

    def test_benchmark_runs_are_orientation_runs(self):
        _topic, collection = _fixture_collection()
        inputs = benchmark._crew_inputs(collection)
        self.assertEqual(inputs["assessment_mode"], "orientation")
        self.assertEqual(inputs["decision_context_json"], "{}")

    def test_the_decision_placeholders_are_what_was_missing(self):
        """Pins the regression: retrieval inputs alone leave these unfilled."""
        _topic, collection = _fixture_collection()
        self.assertTrue(
            {"decision_context_json", "assessment_mode", "decision_mode_guidance"}
            <= _template_placeholders() - set(collection.crew_inputs())
        )

    def test_kickoff_uses_the_complete_inputs(self):
        source = Path(benchmark.__file__).read_text(encoding="utf-8")
        self.assertIn("kickoff(inputs=_crew_inputs(source_collection))", source)
        self.assertNotIn("kickoff(inputs=source_collection.crew_inputs())", source)
