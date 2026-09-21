"""Shipped envelope/state/accounting scripts, never a second implementation."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from tests.test_saved_source_receipt_web import browser_fixtures

ROOT = Path(__file__).resolve().parents[1]


def run_usage_node(scenario, fixtures=None):
    node = shutil.which("node")
    assert node, "Node is required for shipped usage browser contracts"
    result = subprocess.run(
        [node, str(ROOT / "tests/js/saved_source_usage_contract.mjs"), scenario],
        input=json.dumps(fixtures or browser_fixtures(), ensure_ascii=True),
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=45,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    observed = json.loads(result.stdout)
    assert observed["passed"] is True and observed["cases"] > 0


@pytest.mark.parametrize("scenario", ["accounting", "identity", "lifecycle", "storage", "late", "states", "bounds", "numeric_accounting", "numeric_boundaries"])
def test_shipped_usage_contract(scenario):
    """Unknown fees and lost/late replies must neither hide valid text nor resend."""
    run_usage_node(scenario)
