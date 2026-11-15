"""CrewAI's own telemetry stays off in the test process.

CrewAI reports anonymous usage to telemetry.crewai.com from a background
thread. Nothing had turned that off for tests, and on CI the thread of one
test posted during the tests after it: an offline suite whose fixture fails
on any connection caught it twice on 2026-11-15, in two different tests,
depending on which files shared a CI part and on timing. tests/conftest.py
now sets the variable CrewAI reads and checks after every test that its
Telemetry object is not ready to send. This file holds that the two halves
do what they say.
"""

from __future__ import annotations

import os
import sys
from types import SimpleNamespace

from conftest import stop_crewai_telemetry


def _modules(instance):
    return {"crewai.telemetry.telemetry": SimpleNamespace(Telemetry=SimpleNamespace(_instance=instance))}


def test_the_variable_crewai_reads_is_set_for_every_test():
    assert os.environ["CREWAI_DISABLE_TELEMETRY"] == "true"


def test_crewai_built_here_is_not_ready_to_send():
    """The real object, as a crew would build it: with the variable set it
    starts no exporter and records nothing."""
    from crewai.telemetry.telemetry import Telemetry

    telemetry = Telemetry()
    assert telemetry.ready is False
    assert telemetry._should_execute_telemetry() is False
    assert stop_crewai_telemetry(sys.modules) is False


def test_a_ready_telemetry_is_found_and_switched_off():
    instance = SimpleNamespace(ready=True)
    assert stop_crewai_telemetry(_modules(instance)) is True
    assert instance.ready is False, "The tests after the one that built it are not blamed for it"
    assert stop_crewai_telemetry(_modules(instance)) is False


def test_nothing_is_imported_to_look():
    """Most tests load no CrewAI. The check must not load it for them, and
    a process where it was never built has nothing to stop."""
    assert stop_crewai_telemetry({}) is False
    assert stop_crewai_telemetry(_modules(None)) is False
    assert stop_crewai_telemetry({"crewai.telemetry.telemetry": SimpleNamespace()}) is False


def test_the_variable_is_set_before_any_test_module_is_imported():
    """CrewAI's Telemetry reads the variable when it is first built and stays
    as built, so a fixture alone would be too late for an object built while
    a test module is imported. The assignment is at conftest's module level."""
    from pathlib import Path

    conftest = Path(__file__).with_name("conftest.py").read_text(encoding="utf-8")
    assert '\nos.environ["CREWAI_DISABLE_TELEMETRY"] = "true"\n' in conftest
    assert conftest.index('os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"') < conftest.index("@pytest.fixture")
