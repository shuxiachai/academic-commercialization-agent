"""The browser warns before a paid run starts with an obviously broad topic.

The detector is executed from the shipped JavaScript rather than reimplemented
in Python. It remains advisory because short, valid research terms exist; the
production failure only supports asking for confirmation, not rejecting them.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

_REPO = Path(__file__).resolve().parent.parent
_TOPIC_JS = _REPO / "web" / "static" / "js" / "topic.js"
_APP_JS = _REPO / "web" / "static" / "js" / "app.js"


def _node() -> str | None:
    return shutil.which("node")


@unittest.skipUnless(_node(), "node not installed")
class TopicScopeTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        work = Path(cls._tmp.name)
        shutil.copy2(_TOPIC_JS, work / "topic.mjs")
        (work / "harness.mjs").write_text(textwrap.dedent("""
            const { needsScopeWarning } = await import("./topic.mjs");
            const input = JSON.parse(process.argv[2]);
            console.log(JSON.stringify(needsScopeWarning(input.topic, {
              hasPaper: input.hasPaper,
            })));
        """), encoding="utf-8")
        cls._work = work

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _warns(self, topic: str, *, has_paper: bool = False) -> bool:
        result = subprocess.run(
            [
                _node(),
                str(self._work / "harness.mjs"),
                json.dumps({"topic": topic, "hasPaper": has_paper}),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=120,
            cwd=self._work,
        )
        if result.returncode != 0:
            self.fail(f"harness failed: {result.stderr[:400]}")
        return json.loads(result.stdout)

    def test_production_failure_shape_gets_a_warning(self):
        self.assertTrue(self._warns("AI education"))

    def test_specific_english_topic_is_not_warned(self):
        self.assertFalse(
            self._warns("Direct air capture technology for commercial carbon removal deployment")
        )

    def test_short_chinese_topic_gets_a_warning(self):
        self.assertTrue(self._warns("人工智能"))

    def test_specific_chinese_topic_is_not_warned(self):
        self.assertFalse(self._warns("钠离子电池在低成本储能系统中的商业化应用"))

    def test_attached_paper_supplies_scope(self):
        self.assertFalse(self._warns("AI education", has_paper=True))

    def test_warning_is_wired_before_the_paid_request(self):
        """A correct helper that never reaches submit protects no quota."""
        source = _APP_JS.read_text(encoding="utf-8")
        submit = source[source.index('$("#compose-form")'):]
        warning = submit.index("needsScopeWarning(submittedTopic")
        request = submit.index("api.startRun({")
        self.assertLess(warning, request)
        self.assertIn('confirm(t("confirm_broad_topic"))', submit[:request])
