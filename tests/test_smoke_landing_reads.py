"""Which requests the request-auditing smokes accept as the landing's own.

The landing is shown before the access check answers and asks for the sample
list and one scorecard (app.js ensureAccess). The keyboard and composer
smokes fail on any request they do not know; they answer these two through
e2e/landing_reads.py. The rule is narrow on purpose: a credential on such a
read would be an identity sent with a page painted for nobody, and must stay
an unexpected request.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from e2e.landing_reads import is_landing_read

_E2E = Path(__file__).resolve().parents[1] / "e2e"


@pytest.mark.parametrize("path", ["/api/samples", "/api/samples/continuous-glucose-monitoring/scores",
                                  "/api/samples/hyperloop/scores"])
def test_the_landings_two_reads_are_accepted_without_a_credential(path):
    assert is_landing_read("GET", path, {})
    assert is_landing_read("GET", path, {"accept": "application/json", "x-access-code": ""})


@pytest.mark.parametrize("headers", [{"x-access-code": "fixture-A"}, {"authorization": "Bearer fixture-token"}])
def test_a_read_that_carries_an_identity_is_not_the_landings(headers):
    assert not is_landing_read("GET", "/api/samples", headers)
    assert not is_landing_read("GET", "/api/samples/hyperloop/scores", headers)


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/samples"), ("DELETE", "/api/samples/hyperloop/scores"),
    ("GET", "/api/samples/hyperloop"), ("GET", "/api/samples/hyperloop/scores/extra"),
    ("GET", "/api/samples/../runs/scores"), ("GET", "/api/samples/Hyperloop/scores"),
    ("GET", "/api/runs"), ("GET", "/api/samplesX"), ("GET", "/api/samples/"),
])
def test_nothing_else_is(method, path):
    assert not is_landing_read(method, path, {})


def test_every_request_audit_in_the_two_smokes_answers_them():
    """One line per intercept, placed where the audit would otherwise fail."""
    for name, audits in (("keyboard_smoke.py", 1), ("composer_smoke.py", 7)):
        text = (_E2E / name).read_text(encoding="utf-8")
        assert "from e2e.landing_reads import answer_landing_read" in text, name
        assert text.count("elif answer_landing_read(route):") == audits, name
        assert text.count('elif url.path == "/" or url.path.startswith("/static/"):') == audits, name
