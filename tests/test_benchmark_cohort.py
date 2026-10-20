"""Separately registered benchmark cohorts (benchmark.load_cohort, --cohort).

The held-out cohort's ranges are evidence fixed before any run, so the file
that carries them, the protocol that publishes them and the loader that feeds
them to a batch must agree exactly. A drift between them is the failure mode
pre-registration exists to rule out.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import benchmark

_ROOT = Path(__file__).resolve().parents[1]
_COHORT = _ROOT / "evals" / "heldout_trl_v1" / "cohort.json"
_PROTOCOL = _ROOT / "docs" / "prereg-2026-10-18-heldout-trl-v1.md"


def _write(tmp: str, data: object) -> Path:
    path = Path(tmp) / "cohort.json"
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return path


def _case(**overrides) -> dict:
    case = {"id": "X01", "topic": "a valid topic", "expected_trl": [3, 5], "industry": "Test"}
    case.update(overrides)
    return case


class HeldOutCohortFileTests(unittest.TestCase):

    def test_committed_cohort_loads_as_ten_held_out_cases(self):
        cases = benchmark.load_cohort(_COHORT)
        self.assertEqual([c[0] for c in cases], [f"H{i:02d}" for i in range(1, 11)])
        self.assertFalse({c[0] for c in cases} & {num for num, *_ in benchmark.TOPICS})

    def test_protocol_table_matches_the_frozen_file(self):
        """The published ranges and the ranges fed to the batch are one set."""
        table = {
            m.group(1): (m.group(2), int(m.group(3)), int(m.group(4)))
            for m in re.finditer(
                r"^\| (H\d{2}) \| (.+?) \| (\d)–(\d) \|", _PROTOCOL.read_text(encoding="utf-8"), re.M)
        }
        loaded = {num: (topic, lo, hi) for num, topic, (lo, hi), _ in benchmark.load_cohort(_COHORT)}
        self.assertEqual(table, loaded)

    def test_every_case_records_evidence_and_sources(self):
        data = json.loads(_COHORT.read_text(encoding="utf-8"))
        self.assertEqual(data["protocol"], "docs/prereg-2026-10-18-heldout-trl-v1.md")
        for case in data["cases"]:
            with self.subTest(case=case["id"]):
                self.assertGreater(len(case["anchor"]), 80)
                self.assertTrue(case["sources"])
                self.assertTrue(all(s.startswith("https://") for s in case["sources"]))

    def test_cohort_covers_the_registered_input_shapes(self):
        data = json.loads(_COHORT.read_text(encoding="utf-8"))
        shapes = {c["id"]: c["input_shape"] for c in data["cases"]}
        self.assertEqual(shapes["H02"], "short")
        self.assertEqual({k for k, v in shapes.items() if v == "chinese"}, {"H06", "H07"})


class LoadCohortValidationTests(unittest.TestCase):

    def _rejects(self, data: object, message: str) -> None:
        with TemporaryDirectory() as tmp, self.assertRaisesRegex(ValueError, message):
            benchmark.load_cohort(_write(tmp, data))

    def test_schema_version_is_required(self):
        self._rejects({"cases": [_case()]}, "schema_version")

    def test_empty_cohort_is_rejected(self):
        self._rejects({"schema_version": 1, "cases": []}, "at least one case")

    def test_topics_numbers_cannot_be_reused(self):
        self._rejects({"schema_version": 1, "cases": [_case(id="01")]}, "reused")

    def test_duplicate_ids_are_rejected(self):
        self._rejects({"schema_version": 1, "cases": [_case(), _case()]}, "reused")

    def test_ids_must_be_safe_directory_names(self):
        for bad in ("../x", "H 1", "", 7):
            with self.subTest(id=bad):
                self._rejects({"schema_version": 1, "cases": [_case(id=bad)]}, "case id")

    def test_ranges_must_be_ordered_integers_within_one_to_nine(self):
        for bad in ([0, 3], [3, 10], [6, 4], [3.0, 5], [3], "3-5", [True, 5]):
            with self.subTest(expected=bad):
                self._rejects({"schema_version": 1, "cases": [_case(expected_trl=bad)]}, "expected_trl")

    def test_topic_must_be_trimmed_and_non_trivial(self):
        for bad in ("ai", " padded topic", "", None):
            with self.subTest(topic=bad):
                self._rejects({"schema_version": 1, "cases": [_case(topic=bad)]}, "topic")


class CohortCliTests(unittest.TestCase):
    """--cohort through main(), with simulated work only."""

    def _dry_run(self, *extra: str) -> list[dict]:
        captured: list[list[tuple]] = []

        def fake_serial(selected, *args, **kwargs):
            captured.append(selected)
            return []

        argv = ["benchmark.py", "--cohort", str(_COHORT), "--dry-run", *extra]
        with patch.object(sys, "argv", argv), \
             patch.object(benchmark, "_run_serial", fake_serial), \
             patch.object(benchmark, "_log"):
            benchmark.main()
        return captured[0]

    def test_cohort_replaces_topics_and_repeats_interleave(self):
        selected = self._dry_run("--repeat", "3")
        self.assertEqual(len(selected), 30)
        self.assertEqual([s[0] for s in selected[:10]], [f"H{i:02d}" for i in range(1, 11)])
        self.assertEqual({s[4] for s in selected}, {1, 2, 3})

    def test_only_selects_cohort_ids(self):
        selected = self._dry_run("--only", "H02,H07")
        self.assertEqual([(s[0], s[1]) for s in selected],
                         [("H02", "fusion power"), ("H07", "人工光合作用制备太阳能燃料")])

    def test_without_cohort_the_advertised_topics_are_unchanged(self):
        captured: list[list[tuple]] = []
        with patch.object(sys, "argv", ["benchmark.py", "--dry-run"]), \
             patch.object(benchmark, "_run_serial", lambda sel, *a, **k: captured.append(sel) or []), \
             patch.object(benchmark, "_log"):
            benchmark.main()
        self.assertEqual([s[0] for s in captured[0]], [num for num, *_ in benchmark.TOPICS])

    def test_invalid_cohort_is_a_usage_error_before_any_work(self):
        with TemporaryDirectory() as tmp:
            path = _write(tmp, {"schema_version": 1, "cases": [_case(id="01")]})
            with patch.object(sys, "argv", ["benchmark.py", "--cohort", str(path), "--dry-run"]), \
                 patch.object(benchmark, "_run_serial") as serial, \
                 patch.object(benchmark, "_log"), \
                 self.assertRaises(SystemExit):
                benchmark.main()
            serial.assert_not_called()
