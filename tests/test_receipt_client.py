"""First-party paid identities must survive fresh-document reconstruction."""

from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("mode", ["run", "resume", "paper", "corrupt", "denied", "timeout"])
def test_persisted_client_identity_at_actual_fetch(mode):
    node = shutil.which("node")
    assert node, "Node is required for the receipt browser contract"
    result = subprocess.run([node, str(Path(__file__).with_name("js") / "receipt_client_contract.mjs"), mode],
        capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert f"PASS {mode}" in result.stdout
