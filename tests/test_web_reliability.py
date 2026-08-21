"""What the result page says about its own checks.

Four checks already ran on every assessment — report versus scorecard, claim
grounding, which retrieval domains failed, whether the audit trail was fully
written. All four reached the API. None of them reached the screen: the result
view was handed only the artifact name list, so the findings sat in JSON on a
server nobody was going to curl.

Run through Node against the shipped result.js for the same reason the other
web tests are. A Python transcription of these rules would pass while the file
users load stayed wrong.

Most of these are about what the panel is not allowed to claim. "Nothing
flagged" over checks that could not run is the failure this panel exists to
prevent, and it is one it could easily commit: every one of these findings has
a shape where absence and success produce the same empty result.
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
_RESULT_JS = _REPO / "web" / "static" / "js" / "result.js"
_I18N_JS = _REPO / "web" / "static" / "js" / "i18n.js"


def _node() -> str | None:
    return shutil.which("node")


@unittest.skipUnless(_node(), "node not installed")
class ReliabilityPanelTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls._tmp = TemporaryDirectory()
        work = Path(cls._tmp.name)

        source = _RESULT_JS.read_text(encoding="utf-8")
        source = source.replace('import * as api from "./api.js";', "const api = {};")
        (work / "result.mjs").write_text(source, encoding="utf-8")
        shutil.copy2(_I18N_JS, work / "i18n.js")

        (work / "harness.mjs").write_text(textwrap.dedent("""
            globalThis.localStorage = { getItem: () => null, setItem: () => {} };
            const { reliabilityRows, reliabilityVerdict } = await import("./result.mjs");
            const progress = JSON.parse(process.argv[2]);
            const rows = reliabilityRows(progress);
            console.log(JSON.stringify({ rows, verdict: reliabilityVerdict(rows) }));
        """), encoding="utf-8")
        cls._work = work

        warm = subprocess.run(
            [_node(), str(work / "harness.mjs"), "{}"],
            capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=work,
        )
        if warm.returncode != 0:
            raise RuntimeError(f"result.js failed to load: {warm.stderr[:400]}")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _panel(self, **progress) -> dict:
        result = subprocess.run(
            [_node(), str(self._work / "harness.mjs"), json.dumps(progress)],
            capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=self._work,
        )
        if result.returncode != 0:
            self.fail(f"harness failed: {result.stderr[:400]}")
        return json.loads(result.stdout)

    def _row(self, panel: dict, row_id: str) -> dict:
        for row in panel["rows"]:
            if row["id"] == row_id:
                return row
        self.fail(f"no {row_id!r} row in {[r['id'] for r in panel['rows']]}")

    # ── The findings that must reach the reader ──────────────────────────

    def test_a_recommendation_that_outruns_its_score_is_the_headline(self):
        """The case the whole check was written for: a report urging a move to
        market beside a scorecard that does not support it. Both artifacts are
        internally consistent, so nothing else in the pipeline objects."""
        panel = self._panel(consistency={"blockers": 1, "warnings": 0})
        self.assertEqual(self._row(panel, "consistency")["tone"], "risk")
        self.assertEqual(panel["verdict"]["tone"], "risk")

    def test_a_failed_retrieval_domain_is_named(self):
        """An empty market section reads as a finding about the technology.
        It has to read as a fact about the infrastructure instead."""
        panel = self._panel(failed_domains=["market"], source_counts={"academic": 8})
        row = self._row(panel, "sources")
        self.assertEqual(row["tone"], "warn")
        self.assertIn("market", row["detail"])

    def test_missing_clinical_authority_category_is_a_warning(self):
        """Missing coverage is a warning, never proof that no record exists."""
        panel = self._panel(
            source_counts={"academic": 8, "patent": 8, "market": 8},
            authority_coverage={
                "status": "incomplete",
                "missing_categories": ["clinical_registry"],
            },
        )
        row = self._row(panel, "authority")
        self.assertEqual(row["tone"], "warn")
        self.assertIn("clinical-trial registry", row["detail"])

    def test_complete_authority_coverage_does_not_invent_an_unrequired_category(self):
        """Complete means every required category, which may be regulator-only."""
        panel = self._panel(
            source_counts={"academic": 8, "patent": 8, "market": 8},
            authority_coverage={
                "status": "complete",
                "required_categories": ["regulatory"],
            },
        )
        row = self._row(panel, "authority")
        self.assertEqual(row["tone"], "ok")
        self.assertNotIn("clinical-trial registry", row["detail"])

    def test_an_unwritten_audit_trail_is_reported(self):
        panel = self._panel(evidence_incomplete=True)
        self.assertEqual(self._row(panel, "trail")["tone"], "warn")

    def test_figures_missing_from_their_cited_source_are_reported(self):
        panel = self._panel(claim_grounding={"checked": 12, "ungrounded": 3, "unverifiable": 5})
        row = self._row(panel, "grounding")
        self.assertEqual(row["tone"], "warn")
        self.assertIn("3", row["detail"])

    # ── What silence is not allowed to mean ──────────────────────────────

    def test_nothing_checked_is_not_reported_as_nothing_wrong(self):
        """Zero unsupported out of zero checked. The two numbers that mean "the
        screen could not run" are the same two that mean "everything passed",
        and only one of them may be shown as a result."""
        panel = self._panel(claim_grounding={"checked": 0, "ungrounded": 0, "unverifiable": 9})
        self.assertEqual(self._row(panel, "grounding")["tone"], "muted")

    def test_a_report_the_check_cannot_read_is_not_reported_as_consistent(self):
        """consistency is absent for a non-English report: the phrase table
        reads English conclusions, so the check did not run. Absent must not
        collapse into "no disagreement found"."""
        panel = self._panel(claim_grounding={"checked": 5, "ungrounded": 0, "unverifiable": 0})
        row = self._row(panel, "consistency")
        self.assertEqual(row["tone"], "muted")
        self.assertNotIn(row["tone"], ("ok",))

    def test_an_unchecked_check_outranks_successful_source_coverage(self):
        """This is the exact shape returned by the Chinese production run.

        Both content checks were unable to run, while source collection did
        complete.  The old rank let that one successful infrastructure row
        turn the entire headline into "Nothing was flagged".
        """
        panel = self._panel(
            consistency=None,
            claim_grounding={"checked": 0, "ungrounded": 0, "unverifiable": 12},
            source_counts={"academic": 8, "patent": 8, "market": 8},
        )
        self.assertEqual(self._row(panel, "sources")["tone"], "ok")
        self.assertEqual(self._row(panel, "authority")["tone"], "muted")
        self.assertEqual(panel["verdict"]["tone"], "muted")

    def test_a_clean_run_is_called_unflagged_rather_than_verified(self):
        """The strongest thing this panel is allowed to say. These are
        heuristics over whatever retrieval happened to return; presenting that
        as verification is exactly the overclaim it was built to avoid."""
        panel = self._panel(
            consistency={"blockers": 0, "warnings": 0},
            claim_grounding={"checked": 12, "ungrounded": 0, "unverifiable": 1},
            source_counts={"academic": 8, "patent": 5, "market": 6},
            authority_coverage={"status": "not_applicable"},
        )
        self.assertEqual(panel["verdict"]["tone"], "ok")
        self.assertNotIn("verified", panel["verdict"]["label"].lower())
        self.assertTrue(panel["verdict"].get("note"), "a clean verdict must carry its caveat")
        self.assertIn("not verification", panel["verdict"]["note"].lower())

    def test_a_run_with_nothing_to_report_produces_no_panel_but_one_note(self):
        """An empty payload still says the consistency check did not run,
        which is true and worth saying. What it must not do is render as an
        empty box, which reads as "checked, nothing found"."""
        panel = self._panel()
        self.assertEqual([r["id"] for r in panel["rows"]], ["consistency"])
        self.assertEqual(panel["verdict"]["tone"], "muted")

    # ── Ordering ─────────────────────────────────────────────────────────

    def test_the_worst_finding_decides_the_verdict(self):
        """A blocker beside three passes is still a blocker. Averaging the
        rows, or taking the first, would let one good check bury a bad one."""
        panel = self._panel(
            consistency={"blockers": 2, "warnings": 0},
            claim_grounding={"checked": 20, "ungrounded": 0, "unverifiable": 0},
            source_counts={"academic": 8},
        )
        self.assertEqual(panel["verdict"]["tone"], "risk")

    def test_a_warning_outranks_a_pass(self):
        panel = self._panel(
            consistency={"blockers": 0, "warnings": 0},
            failed_domains=["patent"],
            source_counts={"academic": 8},
        )
        self.assertEqual(panel["verdict"]["tone"], "warn")


@unittest.skipUnless(_node(), "node not installed")
class ConsistencyTabWiringTests(unittest.TestCase):
    """The seam, not the rendering.

    The last defect of this shape was a field computed correctly, stored
    correctly, returned correctly by one endpoint and dropped by another. So
    what is asserted here is that the artifact name the server serves is the
    same one the client asks for, and that the view is offered at all.
    """

    def test_the_client_requests_the_artifact_name_the_server_serves(self):
        from api.runs import _ARTIFACTS

        source = _RESULT_JS.read_text(encoding="utf-8")
        self.assertIn('getArtifact(runId, "consistency")', source)
        self.assertIn("consistency", _ARTIFACTS)

    def test_the_tab_appears_when_the_artifact_does(self):
        source = _RESULT_JS.read_text(encoding="utf-8")
        self.assertIn('artifacts.includes("consistency")', source)

    def test_the_result_view_is_given_the_whole_status_payload(self):
        """render() used to take {artifacts} alone, which is why four checks
        that were already on the payload never reached the page."""
        app = (_REPO / "web" / "static" / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("result.render(body, runId, progress)", app)


class RetrievalDiagnosticsWiringTests(unittest.TestCase):
    """A failed run has no report or source registry, so its diagnostic
    artifact needs its own view rather than merely existing on disk."""

    def test_the_client_offers_and_fetches_the_server_artifact(self):
        from api.runs import _ARTIFACTS

        source = _RESULT_JS.read_text(encoding="utf-8")
        self.assertIn('artifacts.includes("retrieval")', source)
        self.assertIn('getArtifact(runId, "retrieval")', source)
        self.assertIn("retrieval", _ARTIFACTS)


class InterfaceStringParityTests(unittest.TestCase):
    """Every key added to English exists in every other interface language.

    i18n.js falls back to English for a missing key, so an untranslated string
    shows up as English text in a Chinese interface rather than as an error —
    which is survivable but silent, and silence is how it stays that way.
    """

    def _tables(self) -> dict[str, set[str]]:
        import re

        source = _I18N_JS.read_text(encoding="utf-8")
        body = source[source.index("const STRINGS = {"):source.index("const STORAGE_KEY")]
        tables: dict[str, set[str]] = {}
        current = None
        for line in body.splitlines():
            header = re.match(r'^\s{2}(?:"([^"]+)"|(\w+)):\s*\{\s*$', line)
            if header:
                current = header.group(1) or header.group(2)
                tables[current] = set()
                continue
            key = re.match(r"^\s{4}(\w+):", line)
            if key and current:
                tables[current].add(key.group(1))
        return tables

    def test_the_scan_found_both_languages(self):
        """A parity test over an empty scan passes for the wrong reason."""
        tables = self._tables()
        self.assertIn("English", tables)
        self.assertIn("Simplified Chinese", tables)
        self.assertGreater(len(tables["English"]), 50)

    def test_no_language_is_missing_an_english_key(self):
        tables = self._tables()
        english = tables["English"]
        for name, keys in tables.items():
            if name == "English":
                continue
            with self.subTest(language=name):
                self.assertEqual(sorted(english - keys), [])

    def test_no_language_carries_a_key_english_does_not(self):
        """A stale key is a translation of a string nobody shows any more."""
        tables = self._tables()
        english = tables["English"]
        for name, keys in tables.items():
            if name == "English":
                continue
            with self.subTest(language=name):
                self.assertEqual(sorted(keys - english), [])


if __name__ == "__main__":
    unittest.main()
