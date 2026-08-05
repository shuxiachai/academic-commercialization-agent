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


if __name__ == "__main__":
    unittest.main()
