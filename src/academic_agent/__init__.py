"""The assessment pipeline. One thing is arranged here: CrewAI's own usage
reporting is off unless the operator turns it on.

CrewAI reports anonymous usage to telemetry.crewai.com from every process
that imports it. Its Telemetry object is built when CrewAI is imported and
stays as built, so ``CREWAI_DISABLE_TELEMETRY`` has to be in the environment
before that import. Until 2026-11-16 nothing set it: not this repository,
not the deployment. The worker of each assessment reported the framework
and Python versions, the number of agents and tasks, and each agent's role
name, model name and tool names. Not the topic, a prompt, a report, a key
or an email address (CrewAI sends those only with ``share_crew``, which
nothing here sets), but a recipient the privacy page does not list.

The default is set at the moment CrewAI is about to be imported, by a finder
on ``sys.meta_path`` that finds nothing and only watches for that name. Two
plainer places were tried first and the test suite refused both:

- setting it here, at import of the package. Parts of the package run in
  processes that must not read the environment at all and never load CrewAI
  (the saved-source application; tests/test_saved_source_app.py), and
  ``setdefault`` reads before it writes;
- importing a small module ahead of CrewAI in each module that uses it.
  ``evidence.py`` is one of them, and pre-registered experiments hold it by
  its hash; a line added there is a different implementation to them.

So importing the package reads nothing and sets nothing; a process that
never loads CrewAI is untouched; one that does has the default in place
first, whichever module gets there. A process that imports CrewAI before
this package is outside its reach.

Off is the default, not a rule: a value already in the environment is the
operator's and is kept. Only CrewAI's own switch is touched.
``OTEL_SDK_DISABLED`` would turn it off too, along with the trace this
project sends to the operator's own collector (observability/tracing.py),
which is a different thing and is theirs to enable.
tests/test_crewai_telemetry_default.py holds all of this in fresh processes.
"""

import os
import sys


class _BeforeCrewAI:
    """Finds no module. Sets the default when CrewAI is about to be imported."""

    @staticmethod
    def find_spec(name, path=None, target=None):
        if name == "crewai" or name.startswith("crewai."):
            os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
        return None


sys.meta_path.insert(0, _BeforeCrewAI)
