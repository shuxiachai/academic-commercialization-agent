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

if __name__ == "__main__":
    unittest.main()
