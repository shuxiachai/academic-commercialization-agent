"""Billing identity and connectivity cross actual JS request/callback seams."""
import json
from pathlib import Path
import re
import shutil
import subprocess

import pytest

from api.models import BYOK_PROVIDERS

ROOT = Path(__file__).resolve().parents[1]
VALID = {"provider": "qwen", "llmKey": "fixture-secret", "serperKey": "fixture-search"}


def execute(scenario, argument=None):
    node = shutil.which("node")
    assert node, "Node must execute the shipped client; absence is not a pass"
    result = subprocess.run([node, str(ROOT / "tests/js/client_boundary_contract.mjs"), scenario,
                             json.dumps(argument)], capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {scenario}" in result.stdout


@pytest.mark.parametrize("operation", ["run", "resume", "pdf"])
@pytest.mark.parametrize("raw,valid", [(None, True), ("null", False), ("{}", False), ("[]", False),
    ('"fixture-secret"', False), ("true", False), ("42", False), ("{broken", False),
    *[(json.dumps({**VALID, field: value}), False) for field, value in [
        ("provider", "other"), ("provider", None), ("llmKey", None), ("llmKey", " "),
        ("llmKey", 1), ("serperKey", ""), ("serperKey", [])]],
    *[(json.dumps({**VALID, "provider": provider}), True) for provider in BYOK_PROVIDERS]])
def test_malformed_byok_never_selects_operator_billing(operation, raw, valid):
    """A valid residual access code used to turn corrupt BYOK into a paid POST."""
    execute("credentials", {"operation": operation, "raw": raw, "valid": valid})


@pytest.mark.parametrize("scenario", ["setter", "read_timeout", "body_timeout", "poll_recovery", "poll_initial", "poll_stop", "poll_missing"])
def test_client_observation_and_identity_boundaries(scenario):
    execute(scenario)


def test_provider_allowlists_match_server_and_visible_choices():
    source = (ROOT / "web/static/js/api.js").read_text(encoding="utf-8")
    providers = json.loads(re.search(r"BYOK_PROVIDERS = (\[.*?\]);", source)[1])
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")
    select = re.search(r'id="byok-provider".*?</select>', html, re.S)[0]
    assert set(providers) == set(BYOK_PROVIDERS) == set(re.findall(r'value="([^"]+)"', select))
