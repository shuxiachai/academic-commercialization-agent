"""Tests for the claim-grounding screen.

Two properties matter more than any individual case, and they pull against
each other:

  * it must fire on a figure that is not in the cited source — otherwise it
    is decoration
  * it must stay silent on correct output — a check that flags sound
    reasoning is one people stop reading, and then it protects nothing

The bound-qualifier rule exists because of the second. Run against 30 real
baseline runs, the first version produced three flags and all three were
sound sentences ("more than 10 years before", "above 100 GPa" where the
sources said 120 and 140). Those are the analyst's thresholds, not quoted
measurements, and the distinction is what these tests pin down.
"""

from __future__ import annotations

from unittest import TestCase

from academic_agent.claim_grounding import (
    GroundingReport,
    check_report,
    checkable_figures,
)


class _Source:
    def __init__(self, source_id, summary, *, title="", publisher="",
                 summary_source="abstract"):
        self.source_id = source_id
        self.evidence_summary = summary
        self.title = title
        self.publisher = publisher
        self.summary_source = summary_source


class _Finding:
    def __init__(self, finding_id, claim, source_ids):
        self.finding_id = finding_id
        self.claim = claim
        self.source_ids = source_ids


class _Report:
    def __init__(self, findings, sources):
        self.findings = findings
        self.sources = sources


def _abstract(text: str) -> str:
    """Pad to the length that marks a summary as substantive rather than a
    fragment, without changing the figures it contains."""
    return text + " " + ("filler prose. " * 40)


class FigureExtractionTests(TestCase):

    def test_figures_with_units_or_decimals_are_checkable(self):
        for claim, expected in [
            ("efficiency reached 26.1%", ["26.1"]),
            ("energy density of 500 Wh/kg", ["500"]),
            ("raised $50.5 million", ["50.5"]),
            ("survived 10000 cycles", ["10000"]),
        ]:
            with self.subTest(claim=claim):
                self.assertEqual(checkable_figures(claim), expected)

    def test_bare_small_integers_are_not_checkable(self):
        """'TRL 5', 'three approaches' — these appear in prose constantly and
        would bury the signal."""
        for claim in ("TRL 5 across 3 approaches", "two of the four programmes",
                      "at stage 7"):
            with self.subTest(claim=claim):
                self.assertEqual(checkable_figures(claim), [])

    def test_bare_years_are_not_checkable(self):
        """A claim dates itself against the analyst's present while citing an
        older source; demanding the year appear there flags a correct
        sentence."""
        self.assertEqual(checkable_figures("as of 2026 no product exists"), [])

    def test_a_year_with_a_unit_is_a_quantity_not_a_date(self):
        self.assertIn("2024", checkable_figures("shipped 2024 GWh of capacity"))

    def test_round_numbers_behind_a_comparative_are_bounds_not_quotations(self):
        """The false positives that motivated this rule. Each is sound given
        sources stating a larger figure."""
        for claim in ("pressures above 100 GPa", "more than 10 years before",
                      "up to 500 Wh/kg", "nearly 50 million", "at least 20%"):
            with self.subTest(claim=claim):
                self.assertEqual(checkable_figures(claim), [])

    def test_precise_figures_survive_a_qualifier(self):
        """'approximately 26.1%' is still quoting 26.1 — only round numbers
        behind a comparative are treated as the analyst's own threshold."""
        self.assertEqual(checkable_figures("approximately 26.1%"), ["26.1"])

    def test_thousands_separators_and_trailing_zeros_are_formatting(self):
        self.assertEqual(checkable_figures("1,250.0 Wh/kg"), ["1250"])


class DetectionTests(TestCase):

    def _report(self, claim, summary, **source_kw):
        return _Report(
            findings=[_Finding("F1", claim, ["A1"])],
            sources=[_Source("A1", _abstract(summary), **source_kw)],
        )

    def test_figure_absent_from_the_cited_source_is_flagged(self):
        """The whole point: a specific number attached to a citation that
        never mentions it."""
        result = check_report(self._report(
            "efficiency reached 26.1%", "This paper reports 19.2% efficiency."))
        self.assertEqual(result.ungrounded_count, 1)
        self.assertEqual(result.checks[0].ungrounded, ("26.1",))

    def test_figure_present_in_the_cited_source_is_not_flagged(self):
        result = check_report(self._report(
            "efficiency reached 26.1%", "We measured 26.1% under AM1.5G."))
        self.assertEqual(result.ungrounded_count, 0)
        self.assertEqual(result.checks[0].status, "grounded")

    def test_a_claim_rounding_a_source_figure_is_not_flagged(self):
        """26.1 against a source's 26.15 is quoting it, not inventing it."""
        result = check_report(self._report(
            "efficiency reached 26.1%", "A certified 26.15% was achieved."))
        self.assertEqual(result.ungrounded_count, 0)

    def test_the_figure_may_come_from_any_cited_source(self):
        report = _Report(
            findings=[_Finding("F1", "reached 500 Wh/kg", ["A1", "A2"])],
            sources=[_Source("A1", _abstract("unrelated chemistry discussion")),
                     _Source("A2", _abstract("we report 500 Wh/kg in a pouch cell"))],
        )
        self.assertEqual(check_report(report).ungrounded_count, 0)

    def test_only_cited_sources_count(self):
        """A figure that appears in some other source in the registry does not
        make this citation support the claim."""
        report = _Report(
            findings=[_Finding("F1", "reached 500 Wh/kg", ["A1"])],
            sources=[_Source("A1", _abstract("unrelated chemistry discussion")),
                     _Source("A2", _abstract("we report 500 Wh/kg in a pouch cell"))],
        )
        self.assertEqual(check_report(report).ungrounded_count, 1)


class SilenceIsNotDisagreementTests(TestCase):
    """The distinction the module exists to preserve: an absent signal read as
    a negative finding is the failure mode this codebase keeps meeting."""

    def test_snippet_sourced_claims_are_unverifiable_not_ungrounded(self):
        report = _Report(
            findings=[_Finding("F1", "efficiency reached 26.1%", ["A1"])],
            sources=[_Source("A1", _abstract("a long snippet without the figure"),
                             summary_source="search_snippet")],
        )
        result = check_report(report)
        self.assertEqual(result.ungrounded_count, 0)
        self.assertEqual(result.unverifiable_count, 1)
        self.assertIn("fragment", result.checks[0].unverifiable_reason)

    def test_a_long_snippet_is_still_a_fragment(self):
        """Length does not make a truncation complete. The label wins, or
        'we did not see it' silently becomes 'it is not there'."""
        report = _Report(
            findings=[_Finding("F1", "efficiency reached 26.1%", ["A1"])],
            sources=[_Source("A1", "x " * 5000, summary_source="search_snippet")],
        )
        self.assertEqual(check_report(report).unverifiable_count, 1)

    def test_short_unlabelled_summaries_are_treated_as_fragments(self):
        report = _Report(
            findings=[_Finding("F1", "efficiency reached 26.1%", ["A1"])],
            sources=[_Source("A1", "Short note, no figure.", summary_source=None)],
        )
        self.assertEqual(check_report(report).unverifiable_count, 1)

    def test_a_claim_citing_nothing_in_the_registry_is_unverifiable(self):
        report = _Report(
            findings=[_Finding("F1", "efficiency reached 26.1%", ["A9"])],
            sources=[_Source("A1", _abstract("something else"))],
        )
        result = check_report(report)
        self.assertEqual(result.unverifiable_count, 1)
        self.assertEqual(result.ungrounded_count, 0)

    def test_qualitative_claims_are_neither_passed_nor_failed(self):
        """No figure means this screen has no opinion. Counting it as checked
        would imply a verification that never happened."""
        report = _Report(
            findings=[_Finding("F1", "the field is maturing steadily", ["A1"])],
            sources=[_Source("A1", _abstract("a discussion"))],
        )
        result = check_report(report)
        self.assertEqual((result.checked_count, result.ungrounded_count,
                          result.unverifiable_count), (0, 0, 0))
        self.assertEqual(result.checks, ())


class RobustnessTests(TestCase):

    def test_check_never_raises(self):
        """It runs beside a finished assessment; an audit bug must not
        destroy the thing it was auditing."""
        class _Exploding:
            @property
            def findings(self):
                raise RuntimeError("boom")

        result = check_report(_Exploding())
        self.assertIn("boom", result.error)

    def test_empty_report_is_handled(self):
        result = check_report(_Report([], []))
        self.assertEqual(result.checked_count, 0)
        self.assertIsNone(result.error)

    def test_payload_is_json_serialisable_and_omits_the_clean_rows(self):
        """A run where everything is grounded should produce a short file, or
        nobody opens it."""
        import json

        report = _Report(
            findings=[_Finding("F1", "reached 500 Wh/kg", ["A1"]),
                      _Finding("F2", "reached 900 Wh/kg", ["A1"])],
            sources=[_Source("A1", _abstract("we report 500 Wh/kg"))],
        )
        data = check_report(report).as_dict()
        self.assertIsInstance(json.dumps(data), str)
        self.assertEqual([f["finding_id"] for f in data["findings"]], ["F2"])
        self.assertEqual(data["checked"], 2)
        self.assertEqual(data["ungrounded"], 1)

    def test_empty_report_serialises(self):
        self.assertEqual(GroundingReport().as_dict()["checked"], 0)
