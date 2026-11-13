"""Contract tests for the Codespaces / VS Code dev container configuration."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEVCONTAINER_PATH = ROOT / ".devcontainer" / "devcontainer.json"


class DevcontainerContractTests(unittest.TestCase):
    """Ensure the dev container provisions the test runtime without secrets."""

    def test_devcontainer_json_is_valid_and_provisions_test_dependencies(self):
        config = json.loads(DEVCONTAINER_PATH.read_text(encoding="utf-8"))

        self.assertIn("3.12", config.get("image", ""))
        features = config.get("features", {})
        self.assertTrue(
            any("node" in feature for feature in features),
            "Dev container must install Node for tests/js/*.mjs contracts",
        )

        post_create = config.get("postCreateCommand", "")
        if isinstance(post_create, list):
            post_create = " ".join(post_create)
        self.assertIn("fonts-wqy-zenhei", post_create)
        self.assertNotIn("fonts-noto-cjk", post_create)
        self.assertIn("/usr/local/bin", post_create)
        self.assertIn("uv sync", post_create)

    def test_devcontainer_includes_no_secrets_or_env_files(self):
        config = json.loads(DEVCONTAINER_PATH.read_text(encoding="utf-8"))

        self.assertNotIn("containerEnv", config)
        self.assertNotIn("remoteEnv", config)
        self.assertNotIn("runArgs", config)
        raw = DEVCONTAINER_PATH.read_text(encoding="utf-8")
        self.assertNotIn(".env", raw)
        self.assertNotIn("API_KEY", raw)


if __name__ == "__main__":
    unittest.main()
