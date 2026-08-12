"""Tests for persisting the evidence stage (Tasks 1-3).

Tasks 4 and 6 read the evidence JSON produced by the three analyst agents, not
the source registry — so those three outputs are the only record of how a
source became a finding. They existed only in process memory, which left the
middle of a six-agent pipeline unauditable: a questionable score could not be
traced back to the reasoning that produced it, and steps.jsonl recorded nothing
but "agent N finished" with an empty thought field.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory

from academic_agent.run_output import (
    EVIDENCE_ARTIFACTS,
    EvidenceArtifactsIncomplete,
    save_evidence_reports,
)


class _Output:
    def __init__(self, raw):
        self.raw = raw


def _outputs(*raws) -> list[_Output]:
    return [_Output(r) for r in raws]


_ACADEMIC = json.dumps({
    "scope_summary": "Graphene electrode literature review.",
    "findings": [{
        "finding_id": "AF1",
        "claim": "Flexible prototypes demonstrated at laboratory scale.",
        "claim_type": "observed_fact",
        "source_ids": ["A1", "A3"],
        "confidence": "high",
    }],
})
_PATENT = json.dumps({"scope_summary": "Patent landscape.", "findings": []})
_MARKET = json.dumps({"scope_summary": "Market signals.", "findings": []})


class SaveEvidenceReportsTests(unittest.TestCase):

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_writes_one_file_per_analyst_agent(self):
        written = save_evidence_reports(
            _outputs(_ACADEMIC, _PATENT, _MARKET, "report", "reviewed", "{}"),
            run_id="run1", output_root=self.root,
        )
        self.assertEqual(len(written), 3)
        for _idx, name in EVIDENCE_ARTIFACTS:
            self.assertTrue((self.root / "run1" / name).exists(), name)

    def test_partial_write_failure_is_reported_not_swallowed(self):
        """The gap this closes.

        Each artifact was written under its own try/except OSError that
        continued on failure, so losing two files out of three returned a
        short list and raised nothing. The worker treats "no exception" as
        "evidence saved", so a run whose sources-to-findings record was half
        gone looked exactly like a complete one — the single failure mode
        nobody can detect by looking at the result.
        """
        real_write = Path.write_text
        calls = {"n": 0}

        def fail_after_first(self_path, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] > 1:
                raise OSError("disk full")
            return real_write(self_path, *args, **kwargs)

        with patch.object(Path, "write_text", fail_after_first):
            with self.assertRaises(EvidenceArtifactsIncomplete) as caught:
                save_evidence_reports(
                    _outputs(_ACADEMIC, _PATENT, _MARKET, "report", "reviewed", "{}"),
                    run_id="run1", output_root=self.root,
                )

        message = str(caught.exception)
        self.assertIn("2 of 3", message)
        self.assertIn("disk full", message)

    def test_what_could_be_written_is_still_written(self):
        """Best-effort must survive the change: the artifacts that can be
        saved are saved, and only then is the failure raised."""
        real_write = Path.write_text
        calls = {"n": 0}

        def fail_on_second_only(self_path, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("transient")
            return real_write(self_path, *args, **kwargs)

        with patch.object(Path, "write_text", fail_on_second_only):
            with self.assertRaises(EvidenceArtifactsIncomplete):
                save_evidence_reports(
                    _outputs(_ACADEMIC, _PATENT, _MARKET, "report", "reviewed", "{}"),
                    run_id="run1", output_root=self.root,
                )

        present = [n for _i, n in EVIDENCE_ARTIFACTS if (self.root / "run1" / n).exists()]
        self.assertEqual(len(present), 2, present)

    def test_a_task_with_no_output_is_skipped_not_failed(self):
        """Nothing to write is not a failure — only a failed write is."""
        written = save_evidence_reports(
            _outputs("", _PATENT, _MARKET, "report", "reviewed", "{}"),
            run_id="run1", output_root=self.root,
        )
        self.assertEqual(len(written), 2)

    def test_content_matches_the_originating_task(self):
        """Index drift here would silently mislabel every artifact."""
        save_evidence_reports(
            _outputs(_ACADEMIC, _PATENT, _MARKET), run_id="run1", output_root=self.root)

        academic = json.loads((self.root / "run1" / "academic_evidence.json").read_text("utf-8"))
        self.assertEqual(academic["findings"][0]["source_ids"], ["A1", "A3"])
        market = json.loads((self.root / "run1" / "market_evidence.json").read_text("utf-8"))
        self.assertEqual(market["scope_summary"], "Market signals.")

    def test_json_is_reformatted_for_reading(self):
        save_evidence_reports(
            _outputs(_ACADEMIC, _PATENT, _MARKET), run_id="run1", output_root=self.root)
        text = (self.root / "run1" / "academic_evidence.json").read_text("utf-8")
        self.assertIn("\n  ", text, "expected indented JSON")

    def test_unparseable_output_is_kept_verbatim(self):
        """Malformed output is precisely what a debugger needs to see."""
        save_evidence_reports(
            _outputs("not json at all{{", _PATENT, _MARKET),
            run_id="run1", output_root=self.root)
        self.assertEqual(
            (self.root / "run1" / "academic_evidence.json").read_text("utf-8"),
            "not json at all{{",
        )

    def test_non_ascii_is_not_escaped(self):
        save_evidence_reports(
            _outputs(json.dumps({"scope_summary": "石墨烯柔性电子"}), _PATENT, _MARKET),
            run_id="run1", output_root=self.root)
        self.assertIn("石墨烯", (self.root / "run1" / "academic_evidence.json").read_text("utf-8"))

    def test_partial_run_writes_what_exists(self):
        """A crash after Task 2 must still leave the first two files."""
        written = save_evidence_reports(
            _outputs(_ACADEMIC, _PATENT), run_id="run1", output_root=self.root)
        self.assertEqual(len(written), 2)
        self.assertFalse((self.root / "run1" / "market_evidence.json").exists())

    def test_empty_output_list_is_harmless(self):
        self.assertEqual(save_evidence_reports([], run_id="run1", output_root=self.root), [])

    def test_blank_task_output_is_skipped(self):
        written = save_evidence_reports(
            _outputs("", _PATENT, _MARKET), run_id="run1", output_root=self.root)
        self.assertEqual(len(written), 2)
        self.assertFalse((self.root / "run1" / "academic_evidence.json").exists())

    def test_missing_raw_attribute_is_skipped(self):
        class _NoRaw:
            pass

        written = save_evidence_reports(
            [_NoRaw(), _Output(_PATENT), _Output(_MARKET)],
            run_id="run1", output_root=self.root)
        self.assertEqual(len(written), 2)

    def test_empty_run_id_rejected(self):
        with self.assertRaises(ValueError):
            save_evidence_reports(_outputs(_ACADEMIC), run_id="", output_root=self.root)

    def test_writes_alongside_the_other_run_artifacts(self):
        """Files must land in the run directory, not a nested one."""
        save_evidence_reports(
            _outputs(_ACADEMIC, _PATENT, _MARKET), run_id="run1", output_root=self.root)
        names = {p.name for p in (self.root / "run1").iterdir()}
        self.assertEqual(
            names, {"academic_evidence.json", "patent_evidence.json", "market_evidence.json"})


if __name__ == "__main__":
    unittest.main()
