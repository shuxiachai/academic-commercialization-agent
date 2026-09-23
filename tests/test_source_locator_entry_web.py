"""Production-only hooks must reach the real receipt state machine."""

import json
from pathlib import Path
import shutil
import subprocess

from api.saved_source_production_assets import asset_response, page_response
from tests.test_saved_source_receipt_web import browser_fixtures


def test_production_projection_checks_consent_before_receipt_and_recovers_without_it():
    """An inert checkbox or a GET consent requirement breaks paid recovery."""
    node = shutil.which("node")
    assert node, "Node is required for the actual source-locator browser contract"
    root = Path(__file__).resolve().parents[1]
    replies = [asset_response(name) for name in ("result.js", "receipt.js", "accounting.js", "entry.js")]
    assert all(reply.status_code == 200 for reply in replies)
    page = page_response(True)
    assert page.status_code == 200
    completed = subprocess.run(
        [node, str(root / "tests/js/source_locator_entry_contract.mjs")],
        input=json.dumps({"modules": [reply.body.decode() for reply in replies],
                          "html": page.body.decode(), "fixtures": browser_fixtures()}, ensure_ascii=True),
        capture_output=True, text=True, encoding="utf-8", cwd=root, timeout=45, check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    observed = json.loads(completed.stdout)
    assert observed["passed"] is True and observed["cases"] >= 12
