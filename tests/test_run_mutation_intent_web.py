"""Execute the actual client request functions without sending any HTTP.

The endpoint accepts a legacy unqualified DELETE, so backend tests alone would
miss a client that forgets intent and silently restores the destructive race.
Node fetch spies test the request seam; Chromium owns actual DOM affordances.
"""

import json
from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.mark.parametrize("operation,intent", [("cancelRun", "cancel"), ("deleteRun", "delete")])
def test_shipped_client_carries_exact_mutation_intent(operation, intent):
    node = shutil.which("node")
    assert node is not None, "Node is required for the shipped browser contract."
    module = (Path(__file__).resolve().parents[1] / "web/static/js/api.js").as_uri()
    script = """
        globalThis.localStorage = { getItem: () => "fixture-owner-code" };
        const seen = [];
        globalThis.fetch = async (url, options) => {
          seen.push({url, method: options.method, code: options.headers["X-Access-Code"]});
          return new Response(JSON.stringify({action: "fixture"}), {
            status: 200, headers: {"Content-Type": "application/json"}
          });
        };
        const api = await import(process.argv[1]);
        await api[process.argv[2]]("20260906T000000Z-aaaaaaaaaa");
        console.log(JSON.stringify(seen));
    """
    result = subprocess.run(
        [node, "--input-type=module", "-e", script, module, operation],
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=True,
    )
    assert json.loads(result.stdout) == [{
        "url": f"/api/runs/20260906T000000Z-aaaaaaaaaa?intent={intent}",
        "method": "DELETE", "code": "fixture-owner-code",
    }]
