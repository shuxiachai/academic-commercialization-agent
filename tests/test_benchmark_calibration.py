"""Tests for benchmark TRL calibration reporting.

Both defects here were found by re-running the benchmark after a long gap, and
both were silent: the suite reported "0 pass / 0 flag" for ten runs whose scores
were in fact accurate, because the calibration check rejected float TRLs.

A TRL is a float whenever the model writes something that is not a multiple of
ten — the scoring guardrail divides its x10 integer by 10, so 85 becomes 8.5
while 90 becomes 9.0 and compares equal to an int. Earlier benchmark runs
happened to produce only round numbers, which is why an `isinstance(trl, int)`
check survived this long.
"""

from __future__ import annotations

import re
import unittest

from benchmark import _trl_flag


class TrlFlagTests(unittest.TestCase):

    def test_float_inside_range_passes(self):
        """The case that was silently reported as unknown."""
        self.assertEqual(_trl_flag(8.5, (7, 9)), "pass")

    def test_float_outside_range_flags(self):
        self.assertEqual(_trl_flag(6.3, (3, 5)), "flag")

    def test_int_inside_range_still_passes(self):
        self.assertEqual(_trl_flag(2, (1, 2)), "pass")

    def test_int_outside_range_still_flags(self):
        self.assertEqual(_trl_flag(9, (1, 2)), "flag")

    def test_float_on_lower_boundary_passes(self):
        self.assertEqual(_trl_flag(5.0, (5, 7)), "pass")

    def test_float_on_upper_boundary_passes(self):
        self.assertEqual(_trl_flag(7.0, (5, 7)), "pass")

    def test_just_outside_upper_boundary_flags(self):
        """0.3 over the limit is still over — the real perovskite case."""
        self.assertEqual(_trl_flag(6.3, (4, 6)), "flag")

    def test_missing_score_is_unknown(self):
        self.assertEqual(_trl_flag(None, (1, 2)), "?")

    def test_non_numeric_is_unknown(self):
        self.assertEqual(_trl_flag("6.3", (4, 6)), "?")

    def test_bool_is_not_treated_as_a_score(self):
        """bool subclasses int, so a naive numeric check would accept True."""
        self.assertEqual(_trl_flag(True, (1, 2)), "?")

    def test_every_observed_benchmark_result(self):
        """The ten TRLs from the run that exposed the defect.

        Nine were floats and every one reported "?" before the fix.
        """
        observed = [
            (8.5, (7, 9), "pass"),
            (7.3, (6, 8), "pass"),
            (5.5, (5, 7), "pass"),
            (6.3, (4, 6), "flag"),
            (7.3, (6, 8), "pass"),
            (5.5, (5, 7), "pass"),
            (4.5, (4, 6), "pass"),
            (3.0, (2, 4), "pass"),
            (6.3, (3, 5), "flag"),
            (2.0, (1, 2), "pass"),
        ]
        for trl, rng, expected in observed:
            with self.subTest(trl=trl, expected_range=rng):
                self.assertEqual(_trl_flag(trl, rng), expected)

        self.assertEqual(sum(1 for t, r, _ in observed if _trl_flag(t, r) == "pass"), 8)

class NumericUncitedTests(unittest.TestCase):
    """The hallucination proxy must not count roadmap headings.

    A real report was reported as carrying three uncited numeric claims. All
    three were timeline labels — "**Near-Term (1-3 years):**" and friends —
    which name a section rather than assert a figure. The existing bold-header
    exclusion only matched numbered headings like "**1. Title**".
    """

    def _count(self, line: str) -> int:
        from benchmark_check import _count_numeric_uncited
        return _count_numeric_uncited(f"## Section\n\n{line}\n\n## References\n")

    def test_parenthesised_horizon_headings_not_counted(self):
        for heading in [
            "**Near-Term (1-3 years):**",
            "**Near-Term (1\u20133 years):**",   # en dash, as emitted
            "**Medium-Term (3-7 years):**",
            "**Long-Term (7+ years):**",
            "**Phase 2 (2027-2030):**",
        ]:
            with self.subTest(heading=heading):
                self.assertEqual(self._count(heading), 0)

    def test_genuine_uncited_figure_still_counted(self):
        """The check must keep catching what it exists to catch."""
        self.assertEqual(
            self._count("The market will reach USD 4.2 billion by 2030."), 1)

    def test_cited_figure_not_counted(self):
        self.assertEqual(
            self._count("The market will reach USD 4.2 billion by 2030 [M3]."), 0)

    def test_multi_id_citation_recognised(self):
        self.assertEqual(
            self._count("Seven records [P1, P2, P3] were filed since 2019."), 0)


class RunDirRepetitionTests(unittest.TestCase):
    """--repeat needs a directory per execution, without renaming the ones
    already on disk from before the flag existed."""

    def test_first_repetition_keeps_the_historic_name(self):
        from benchmark import _run_dir
        self.assertEqual(_run_dir("01", "solid state batteries", 1).name,
                         _run_dir("01", "solid state batteries").name)

    def test_later_repetitions_get_distinct_names(self):
        from benchmark import _run_dir
        names = {_run_dir("01", "solid state batteries", r).name for r in (1, 2, 3)}
        self.assertEqual(len(names), 3)

    def test_repetition_suffix_is_recoverable(self):
        from benchmark import _run_dir
        self.assertTrue(_run_dir("01", "topic here", 2).name.endswith("__r2"))


class BenchmarkContaminationTests(unittest.TestCase):
    """A benchmark topic must not be named in the rubric that scores it.

    Four of the ten topics were once calibration anchors carrying an explicit
    TRL, and six appeared as patent_strength examples. Three scored their
    anchor's value exactly, identically across repeated runs — which reads as
    a confident, stable judgement and is in fact recitation. For perovskite
    the anchor (7.3) even contradicted the range the suite expects (4-6), so
    the rubric was marking its own test wrong.

    The failure is easy to reintroduce, because the canonical example of a
    technology at a given maturity is exactly the technology worth testing:
    the SCOPE MATCH RULE was written with two benchmark topics as its worked
    examples, and one of them then echoed that wording back in its rationale.
    Hence a test rather than a note.
    """


    @classmethod
    def setUpClass(cls):
        import re
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent / "src" / "academic_agent" / "config"
        text = "\n".join(
            (root / name).read_text(encoding="utf-8").lower()
            for name in ("agents.yaml", "tasks.yaml")
        )

        # Weight-profile keyword lists are exempt. They route a topic to a set
        # of dimension weights and assert nothing about how mature it is, so
        # naming a technology there gives away no answer — unlike an anchor,
        # which states the score outright.
        text = re.sub(
            r"^\s{4}[a-z_]+ \([^)]*\):\s*\n\s+w_market=.*?(?=\n\n)",
            "", text, flags=re.S | re.M,
        )
        # The passage documenting this rule necessarily names the topics it is
        # about; excluding it keeps the test from failing on its own rationale.
        text = re.sub(
            r"none of these anchors may name.*?enforces the separation\.",
            "", text, flags=re.S,
        )
        cls._rubric = text

    @staticmethod
    def _technology_name(topic: str) -> str:
        """The technology a rubric example would name it by.

        Matched as a phrase rather than word by word: the words a topic is
        built from ("state", "storage", "capture", "solar") are ordinary
        English that appears all over a long prompt, and flagging those
        reports contamination everywhere and so gets ignored. What matters is
        whether the technology itself is named, which is the part before the
        application clause — "solid-state batteries", not "for electric
        vehicles".
        """
        name = topic.lower().split(" for ")[0]
        return name.replace("-", " ").strip()

    def test_no_benchmark_topic_is_named_in_the_scoring_rubric(self):
        from benchmark import TOPICS

        haystack = self._rubric.replace("-", " ")
        for num, topic, _range, _industry in TOPICS:
            name = self._technology_name(topic)
            with self.subTest(topic=f"{num} {topic}"):
                self.assertNotIn(
                    name, haystack,
                    f"topic {num} is named in the rubric as {name!r}. Scoring a "
                    "topic whose answer appears in its own prompt measures "
                    "recall, not judgement — rename the rubric's example rather "
                    "than the benchmark topic.",
                )


class StabilityAggregationTests(unittest.TestCase):
    """Spread across repetitions is what makes a scoring change measurable:
    a shift smaller than the run-to-run spread is not evidence of anything."""

    @staticmethod
    def _row(case_num, rep, trl, overall, calibration):
        return {
            "case_num": case_num, "rep": rep, "topic": f"topic {case_num}",
            "status": "success", "trl_score": trl, "overall_score": overall,
            "expected_trl": "5-7", "trl_calibration": calibration,
        }

    def test_mean_and_spread_are_reported_per_topic(self):
        from benchmark_check import _stability_rows
        rows = [
            self._row("01", 1, 6.0, 60.0, "pass"),
            self._row("01", 2, 7.0, 66.0, "pass"),
            self._row("01", 3, 8.0, 72.0, "flag"),
        ]
        [stat] = _stability_rows(rows)
        self.assertEqual(stat["n"], 3)
        self.assertEqual(stat["trl_mean"], 7.0)
        self.assertEqual(stat["trl_sd"], 1.0)
        self.assertEqual((stat["trl_min"], stat["trl_max"]), (6.0, 8.0))
        self.assertEqual(stat["calibrated"], "2/3")

    def test_single_run_reports_zero_spread_not_an_error(self):
        """Directories from before --repeat existed are a sample of one, and
        statistics.stdev raises on those rather than returning 0."""
        from benchmark_check import _stability_rows
        [stat] = _stability_rows([self._row("01", 1, 6.0, 60.0, "pass")])
        self.assertEqual(stat["n"], 1)
        self.assertEqual(stat["trl_sd"], 0.0)

    def test_failed_runs_are_excluded_from_the_statistics(self):
        """A crashed run has no score; averaging it in would drag the mean."""
        from benchmark_check import _stability_rows
        failed = self._row("01", 2, "", "", "")
        failed["status"] = "error_crew"
        [stat] = _stability_rows([self._row("01", 1, 6.0, 60.0, "pass"), failed])
        self.assertEqual(stat["n"], 1)

    def test_topics_are_aggregated_separately(self):
        from benchmark_check import _stability_rows
        stats = _stability_rows([
            self._row("01", 1, 6.0, 60.0, "pass"),
            self._row("02", 1, 3.0, 30.0, "flag"),
        ])
        self.assertEqual([s["case_num"] for s in stats], ["01", "02"])


class CsvFieldCoverageTests(unittest.TestCase):
    """Every field analyse_run produces must reach the CSV.

    The writer uses extrasaction="ignore", so a key missing from the explicit
    fieldnames list is dropped in silence — the run succeeds, the file is
    written, and the column simply is not there. That is how evidence_mode was
    first added and first lost, and the next field would go the same way.
    """

    def test_no_analysed_field_is_silently_dropped(self):
        import ast
        import inspect

        import benchmark_check

        # The keys analyse_run builds, read from the source rather than by
        # running it, so this needs no benchmark output on disk.
        tree = ast.parse(inspect.getsource(benchmark_check.analyse_run))
        produced = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                produced.update(k.value for k in node.keys
                                if isinstance(k, ast.Constant) and isinstance(k.value, str))
            if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
                if isinstance(node.slice.value, str):
                    produced.add(node.slice.value)

        source = inspect.getsource(benchmark_check.main)
        declared = set(re.findall(r'"([a-z_]+)"', source.split("fieldnames = [", 1)[1]
                                                        .split("]", 1)[0]))
        # Keys read from meta.json rather than written to the row are picked up
        # by the subscript walk above; only assert on ones the row actually has.
        row_keys = produced & set(re.findall(r'"([a-z_]+)":', inspect.getsource(
            benchmark_check.analyse_run)))
        missing = row_keys - declared
        self.assertFalse(missing, f"produced but never written to the CSV: {sorted(missing)}")


class ExpectedRangeProvenanceTests(unittest.TestCase):
    """Every expected TRL range must cite a milestone somebody can check.

    The ranges started as my own estimate, which the benchmark could not
    detect as a problem: the same person wrote the topics, the rubric, the
    ranges and the pass criterion, so the headline measured agreement with
    one opinion. Checking them against public milestones found three set too
    low — and in all three the system had scored at the ceiling of the range
    and been recorded as a pass.

    This does not stop anyone widening a range to make a number look better;
    no test can read intent. What it stops is doing it *silently*: moving a
    range without stating what the new one is anchored to now fails here.
    """

    def _anchor_block(self) -> str:
        import inspect

        import benchmark

        source = inspect.getsource(benchmark)
        start = source.index("# ANCHORS")
        return source[start:source.index("TOPICS = [", start)]

    def test_every_topic_has_an_anchor(self):
        import benchmark

        block = self._anchor_block()
        for num, topic, _range, _industry in benchmark.TOPICS:
            with self.subTest(num=num, topic=topic):
                # (?m) so ^ means "start of a line" rather than "start of the
                # block" — without it this passes only for the first case and
                # silently stops checking the other nine.
                self.assertRegex(
                    block, rf"(?m)^#\s+{num}\s",
                    f"case {num} has an expected range but no anchor line",
                )

    def test_the_anchor_block_is_dated(self):
        """A milestone list with no date cannot be judged for staleness, and
        these do go stale — an approval that had not happened when the range
        was set is exactly what moved three of them."""
        self.assertRegex(self._anchor_block(), r"verified \d{4}-\d{2}-\d{2}")

    def test_unresolved_anchors_are_named_as_such(self):
        """One case could not be anchored to a primary source. Leaving that
        implicit would let a guess sit among the verified ones looking the
        same."""
        self.assertIn("UNRESOLVED", self._anchor_block())


if __name__ == "__main__":
    unittest.main()
