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

from pathlib import Path
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
            ("efficiency reached 26.1%", [("26.1", "%")]),
            ("energy density of 500 Wh/kg", [("500", "wh/kg")]),
            ("raised $50.5 million", [("50.5", "million")]),
            ("survived 10000 cycles", [("10000", "cycles")]),
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
        self.assertIn(("2024", "gwh"), checkable_figures("shipped 2024 GWh of capacity"))

    def test_year_before_european_is_not_misread_as_eur_currency(self):
        """The paid pilot's "2013 European patent" is a date plus adjective."""
        self.assertEqual(checkable_figures("The 2013 European patent describes casting"), [])

    def test_explicit_eur_amount_after_year_shaped_number_remains_checkable(self):
        self.assertEqual(checkable_figures("The contract value was 2013 EUR"), [("2013", "eur")])

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
        self.assertEqual(checkable_figures("approximately 26.1%"), [("26.1", "%")])

    def test_thousands_separators_and_trailing_zeros_are_formatting(self):
        self.assertEqual(checkable_figures("1,250.0 Wh/kg"), [("1250", "wh/kg")])


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
        self.assertEqual(result.checks[0].ungrounded, ("26.1%",))

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


class UnitTests(TestCase):
    """Same digits, different quantity.

    Without the unit, "efficiency reached 26.1%" is satisfied by a source
    reporting "26.1 million in revenue" — a verified citation to a sentence
    about something else entirely. Raised by an external review; the first
    version of this screen compared numbers only.
    """

    def _report(self, claim, summary):
        return _Report(
            findings=[_Finding("F1", claim, ["A1"])],
            sources=[_Source("A1", _abstract(summary))],
        )

    def test_a_percentage_is_not_satisfied_by_a_money_figure(self):
        result = check_report(self._report(
            "efficiency reached 26.1%", "Revenue of 26.1 million was reported."))
        self.assertEqual(result.ungrounded_count, 1)

    def test_power_is_not_satisfied_by_mass(self):
        result = check_report(self._report(
            "a 100 MW plant", "The 100 kg sample was characterised."))
        self.assertEqual(result.ungrounded_count, 1)

    def test_the_same_unit_still_matches(self):
        result = check_report(self._report(
            "a 100 MW plant", "They commissioned a 100 MW installation."))
        self.assertEqual(result.ungrounded_count, 0)

    def test_spellings_of_one_unit_are_the_same_unit(self):
        """A claim writing % against a source writing percent is quoting it."""
        result = check_report(self._report(
            "efficiency reached 26.1%", "We measured 26.1 percent efficiency."))
        self.assertEqual(result.ungrounded_count, 0)

    def test_a_source_figure_without_a_unit_still_counts(self):
        """Absence of a unit is not evidence of a different one. Refusing it
        would turn "the source wrote the number without repeating the unit"
        into an accusation of fabrication — the same error this module refuses
        to make about missing text."""
        result = check_report(self._report(
            "efficiency reached 26.1%", "The measured value was 26.1 under AM1.5G."))
        self.assertEqual(result.ungrounded_count, 0)

    def test_the_reported_figure_keeps_its_unit(self):
        """A report saying "26.1 is absent" when the claim said "26.1%" sends
        the reader looking for the wrong thing."""
        result = check_report(self._report(
            "efficiency reached 26.1%", "Revenue of 26.1 million was reported."))
        self.assertEqual(result.checks[0].ungrounded, ("26.1%",))


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


class SummarySourceLabellingTests(TestCase):
    """The screen decides whether absence means anything by reading
    summary_source, so the label has to be accurate at the point it is set.

    It was not. Two different things both landed on None: a real Lens patent
    abstract (the builder never set the field) and a truncated Google Patents
    extract (the web builder labelled only the market domain). One field, two
    opposite meanings, and this screen read both as complete text — so it was
    reasoning about absence in roughly two thirds of the patent domain on
    fragments that end in "[...]".
    """

    def test_lens_patent_abstract_is_labelled_abstract(self):
        from datetime import date

        from academic_agent.source_pipeline import _patent_source_from_lens

        record = {
            "lens_id": "123-456-789",
            "biblio": {
                "invention_title": [{"text": "Solid state battery with solid electrolyte for electric vehicles", "lang": "en"}],
                "publication_reference": {"jurisdiction": "US", "doc_number": "11111111"},
                "parties": {"applicants": [{"extracted_name": {"value": "Acme Corp"}}]},
                "publication_date": "2021-05-04",
            },
            "abstract": [{"text": "A solid-state electrochemical cell achieving "
                                  "500 Wh/kg with a sulfide electrolyte. " * 4}],
        }
        source, reason = _patent_source_from_lens(
            record, "P1", date(2026, 1, 1), "solid state batteries")
        self.assertIsNotNone(source, reason)
        self.assertEqual(source.summary_source, "abstract")

    def test_lens_record_without_an_abstract_is_not_labelled_abstract(self):
        """The builder falls back to a synthesised one-liner when the record
        carries no abstract; calling that an abstract would be the same lie in
        the other direction."""
        from datetime import date

        from academic_agent.source_pipeline import _patent_source_from_lens

        record = {
            "lens_id": "123-456-789",
            "biblio": {
                "invention_title": [{"text": "A solid electrolyte cell for vehicles",
                                     "lang": "en"}],
                "publication_reference": {"jurisdiction": "US", "doc_number": "11111111"},
                "parties": {"applicants": [{"extracted_name": {"value": "Acme Corp"}}]},
                "publication_date": "2021-05-04",
            },
        }
        source, reason = _patent_source_from_lens(
            record, "P1", date(2026, 1, 1), "solid state batteries")
        if source is not None:
            self.assertNotEqual(source.summary_source, "abstract")

    def test_web_extracts_are_labelled_snippet_in_every_domain(self):
        """Not only market. A Google Patents page extract is as truncated as a
        market report's, and labelling one and not the other is what made the
        field unreadable."""
        from datetime import date

        from academic_agent.source_pipeline import _web_source

        snippet = ("FIELD OF THE INVENTION The present invention relates to "
                   "batteries for electric vehicles. " * 6)
        # Each domain applies its own host allowlist, so the URL has to be one
        # that domain accepts; the label is what is under test, not the filter.
        for domain, link in (
            ("patent", "https://patents.google.com/patent/US11111111B2/en"),
            ("market", "https://www.reuters.com/business/energy/solid-state-2026"),
        ):
            with self.subTest(domain=domain):
                source, reason = _web_source(
                    {"title": "Solid-state battery cell with sulfide electrolyte",
                     "link": link, "snippet": snippet},
                    "P1", domain, date(2026, 1, 1), lambda _u: (True, ""))
                self.assertIsNotNone(source, reason)
                self.assertEqual(source.summary_source, "search_snippet")


class PerDomainReportingTests(TestCase):
    """One aggregate number cannot say both things.

    Across the 30-run baseline the overall figure was 14% checkable, which
    reads as "this screen barely works". Split by domain it was academic 92%,
    market 0% — and the market zero is a fact about market reports, which have
    no abstract anywhere, not a shortfall in the check. Reporting only the
    aggregate invites exactly the wrong conclusion about both.
    """

    def _tasks(self):
        import json

        class _Task:
            def __init__(self, raw):
                self.raw = raw

        def report(prefix, claim, summary, summary_source):
            return json.dumps({
                # EvidenceReport requires these; the screen ignores them, but
                # a report that fails to parse is skipped entirely and the
                # test would pass vacuously.
                "topic": "solid state batteries", "scope_summary": "s" * 40,
                "search_queries": ["q"], "limitations": ["l" * 40],
                "findings": [{
                    "finding_id": f"{prefix}F1", "category": "performance", "claim": claim,
                    "claim_type": "observed_fact", "source_ids": [f"{prefix}1"],
                    "confidence": "high",
                    "commercial_implication": "implication text",
                    "limitations": None,
                }],
                "sources": [{
                    "source_id": f"{prefix}1", "title": "a source title",
                    "url": "https://example.test/a", "doi": None, "publisher": "Publisher",
                    "published_date": None, "accessed_date": "2026-01-01",
                    "source_type": "academic_paper", "credibility_tier": "high",
                    "credibility_reason": "a stated reason", "evidence_summary": summary,
                    "summary_source": summary_source, "citation_count": None,
                }],
            })

        long = " ".join(["filler prose."] * 60)
        return [
            # academic: a real abstract, and the figure is in it
            _Task(report("A", "efficiency reached 26.1%", f"We measured 26.1%. {long}",
                         "abstract")),
            # patent: nothing quantitative to check
            _Task(report("P", "the filing describes a layered cell", f"text. {long}",
                         "abstract")),
            # market: a figure, but only a truncated page extract to check against
            _Task(report("M", "the market reached $12.5 billion",
                         f"a page extract. {long}", "search_snippet")),
        ]

    def test_counts_are_broken_out_by_domain(self):
        import tempfile

        from academic_agent.run_output import save_claim_grounding

        with tempfile.TemporaryDirectory() as tmp:
            totals = save_claim_grounding(self._tasks(), run_id="r",
                                          output_root=Path(tmp))
        by_domain = totals["by_domain"]
        self.assertEqual(by_domain["academic"]["checked"], 1)
        self.assertEqual(by_domain["academic"]["ungrounded"], 0)
        self.assertEqual(by_domain["market"]["checked"], 0)
        self.assertEqual(by_domain["market"]["unverifiable"], 1)

    def test_the_breakdown_reaches_the_artifact_too(self):
        import json
        import tempfile

        from academic_agent.run_output import save_claim_grounding

        with tempfile.TemporaryDirectory() as tmp:
            save_claim_grounding(self._tasks(), run_id="r", output_root=Path(tmp))
            payload = json.loads(
                (Path(tmp) / "r" / "claim_grounding.json").read_text(encoding="utf-8"))
        self.assertIn("by_domain", payload)
        self.assertEqual(payload["checked"], 1)

    def test_no_distinctive_figures_is_recorded_as_not_applicable(self):
        import json
        import tempfile

        from academic_agent.run_output import save_claim_grounding

        tasks = self._tasks()
        for task in tasks:
            payload = json.loads(task.raw)
            for finding in payload["findings"]:
                finding["claim"] = "The source describes a qualitative outcome."
            task.raw = json.dumps(payload)

        with tempfile.TemporaryDirectory() as tmp:
            summary = save_claim_grounding(
                tasks, run_id="r", output_root=Path(tmp)
            )
            artifact = json.loads(
                (Path(tmp) / "r" / "claim_grounding.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(summary["status"], "not_applicable")
        self.assertEqual(artifact["status"], "not_applicable")
        self.assertEqual(set(summary["screened_domains"]), {"academic", "patent", "market"})
        self.assertEqual(summary["unavailable_domains"], [])

    def test_missing_evidence_outputs_are_recorded_as_unavailable(self):
        import json
        import tempfile

        from academic_agent.run_output import save_claim_grounding

        with tempfile.TemporaryDirectory() as tmp:
            summary = save_claim_grounding(
                [object(), object(), object()], run_id="r", output_root=Path(tmp)
            )
            artifact = json.loads(
                (Path(tmp) / "r" / "claim_grounding.json").read_text(
                    encoding="utf-8"
                )
            )

        self.assertEqual(summary["status"], "unavailable")
        self.assertEqual(artifact["status"], "unavailable")
        self.assertEqual(
            set(summary["unavailable_domains"]), {"academic", "patent", "market"}
        )

    def test_artifact_write_failure_returns_a_visible_failed_state(self):
        import tempfile
        from unittest.mock import patch

        from academic_agent.run_output import save_claim_grounding

        with tempfile.TemporaryDirectory() as tmp, \
             patch("pathlib.Path.write_text", side_effect=OSError("private disk path")):
            with self.assertWarnsRegex(UserWarning, "claim grounding screen failed"):
                summary = save_claim_grounding(
                    self._tasks(), run_id="r", output_root=Path(tmp)
                )

        self.assertEqual(summary["status"], "failed")
        self.assertNotIn("private disk path", str(summary))


class FigureNotationBoundaryTests(TestCase):
    """Separators, signs, exponents and scripts at the edges of the lexer."""

    def test_a_comma_before_one_or_two_digits_is_a_decimal_comma(self):
        """'0,49 miliardi' was read as 49: every figure of an Italian report
        on disk was off a hundredfold, on both sides of the comparison."""
        self.assertEqual(checkable_figures("26,1%"), [("26.1", "%")])
        self.assertEqual(checkable_figures("12,5 mm"), [("12.5", "mm")])
        self.assertEqual(checkable_figures("-26,1%"), [("-26.1", "%")])
        self.assertEqual(checkable_figures("1234,5%"), [("1234.5", "%")])
        self.assertEqual(checkable_figures("0,49 miliardi")[0][0], "0.49")

    def test_three_digit_groups_remain_thousands_separators(self):
        self.assertEqual(checkable_figures("1,000 cycles"), [("1000", "cycles")])
        self.assertEqual(checkable_figures("1,000.5 kg"), [("1000.5", "kg")])
        self.assertEqual(checkable_figures("1,00,000 kg"), [("100000", "kg")])

    def test_signs_and_exponents_normalise_to_one_spelling(self):
        self.assertEqual(checkable_figures("−5 °C"), [("-5", "°c")])
        self.assertEqual(checkable_figures("1e3 kg"), [("1000", "kg")])
        self.assertEqual(checkable_figures("1e-3%"), [("0.001", "%")])

    def test_ranges_powers_and_unknown_units_abstain_rather_than_guess(self):
        for text in ("10–20%", "5 ×10^3 K", "328 mAh/g", "1.5 mM"):
            with self.subTest(text=text):
                figures = checkable_figures(text)
                self.assertEqual(len(figures), 1)
                self.assertTrue(figures[0][1].startswith("?unknown:"), figures)

    def test_fullwidth_digits_and_percent_are_not_read(self):
        """Pinned, not endorsed: a Chinese report writing ５０％ states a figure
        this screen cannot see, so it is neither checked nor flagged."""
        self.assertEqual(checkable_figures("５０％"), [])
        self.assertEqual(checkable_figures("50 ％"), [])

    def test_a_claim_may_round_a_source_figure_but_not_add_precision_to_it(self):
        from academic_agent.claim_grounding import _same_numeric_value

        self.assertTrue(_same_numeric_value("26", "26.1"))
        self.assertFalse(_same_numeric_value("26.1", "26"))
        self.assertTrue(_same_numeric_value("0.5", ".5"))
        self.assertTrue(_same_numeric_value("100", "1e2"))
        self.assertFalse(_same_numeric_value("abc", "abc"))


class ScreenEdgeTests(TestCase):
    """Paths the coverage run showed untested: notation limits, date ranges,
    the unit on each side of a comparison, and how an unknown unit is reported."""

    def test_milli_and_mega_prefixes_never_become_the_same_unit(self):
        self.assertEqual(checkable_figures("1.5 mWh"), [("1.5", "milliwatt-hour")])
        self.assertEqual(checkable_figures("1.5 MWh"), [("1.5", "mwh")])
        self.assertEqual(checkable_figures("2.5 mPa"), [("2.5", "millipascal")])

    def test_absurdly_long_or_large_notation_is_unknown_not_a_number(self):
        for text in ("1" * 140 + " kg", "1e200 kg", "1e-150%"):
            with self.subTest(text=text[:20]):
                figures = checkable_figures(text)
                self.assertEqual(len(figures), 1)
                self.assertEqual(figures[0][1], "?unknown:numeric notation")

    def test_year_ranges_and_small_count_ranges_are_not_figures_but_a_large_range_is_visible(self):
        self.assertEqual(checkable_figures("the 2020-2024 programme"), [])
        self.assertEqual(checkable_figures("funded 2019–23"), [])
        self.assertEqual(checkable_figures("TRL 4-5 today"), [])
        self.assertEqual(checkable_figures("costs 1000-2000"), [("1000-2000", "?unknown:numeric notation")])

    def test_a_rendered_figure_keeps_its_unit_spacing(self):
        report = _Report(
            findings=[_Finding("F1", "Energy density reached 500 Wh/kg at 26.1% efficiency.", ["A1"])],
            sources=[_Source("A1", _abstract("The cell delivered 500 Wh/kg and 26.1% efficiency."))],
        )
        shown = check_report(report).checks[0].as_dict()
        self.assertEqual(shown["status"], "grounded")
        self.assertEqual(shown["grounded_figures"], ["500 wh/kg", "26.1%"])

    def test_non_finite_values_never_compare_equal(self):
        from academic_agent.claim_grounding import _same_numeric_value

        self.assertFalse(_same_numeric_value("Infinity", "Infinity"))
        self.assertFalse(_same_numeric_value("NaN", "NaN"))
        self.assertFalse(_same_numeric_value("1", "Infinity"))

    def test_an_unknown_unit_on_either_side_neither_supports_nor_accuses(self):
        from academic_agent.claim_grounding import _supported

        self.assertFalse(_supported("26.1", "%", [("26.1", "?unknown:foo")], "26.1 foo"))
        self.assertFalse(_supported("26.1", "?unknown:foo", [("26.1", "%")], "26.1%"))
        # The unitless fallback skips haystack figures with an unknown suffix too.
        self.assertFalse(_supported("1000", "", [], "about 1000 foo"))
        self.assertTrue(_supported("1000", "", [], "1e kg then 1000 of them"))

    def test_an_unrecognised_unit_in_the_claim_is_reported_as_notation_not_as_a_result(self):
        """The production walkthrough's own case: 328 mAh/g is a real figure
        this screen cannot compare, and the source saying the same thing must
        not turn it into a pass, nor its silence into an accusation."""
        report = _Report(
            findings=[_Finding("F1", "Capacity reached 328 mAh/g.", ["A1"])],
            sources=[_Source("A1", _abstract("A reversible capacity of 328 mAh/g was measured."))],
        )
        audit = check_report(report).as_dict()
        self.assertEqual((audit["checked"], audit["ungrounded"], audit["unverifiable"]), (0, 0, 1))
        self.assertIn("unrecognised numeric or unit notation", audit["findings"][0]["unverifiable_reason"])

    def test_identical_claims_with_the_same_sources_collapse_but_different_sources_do_not(self):
        findings = [_Finding("F1", "Efficiency reached 26.1%.", ["A1"]),
                    _Finding("F2", "Efficiency reached 26.1%.", ["A1"]),
                    _Finding("F3", "Efficiency reached 26.1%.", ["A2"])]
        sources = [_Source("A1", _abstract("Efficiency reached 26.1%.")),
                   _Source("A2", _abstract("Efficiency reached 26.1%."))]
        audit = check_report(_Report(findings, sources)).as_dict()
        self.assertEqual(audit["duplicates_collapsed"], 1)
        self.assertEqual(audit["checked"], 2)

    def test_structured_fields_count_as_what_the_source_states(self):
        """"10,614 citations for the 2012 paper" was once reported absent from
        a source that carried the number in citation_count."""
        source = _Source("A1", _abstract("A foundational paper."))
        source.citation_count = 10614
        source.published_date = "2012-05-01"
        report = _Report([_Finding("F1", "The paper has 10,614 citations.", ["A1"])], [source])
        audit = check_report(report).as_dict()
        self.assertEqual((audit["checked"], audit["ungrounded"]), (1, 0))

    def test_the_substantive_summary_boundary_is_exact(self):
        from academic_agent.claim_grounding import _SUBSTANTIVE_SUMMARY_CHARS, _source_is_checkable

        short = _Source("A1", "x" * (_SUBSTANTIVE_SUMMARY_CHARS - 1), summary_source=None)
        long = _Source("A1", "x" * _SUBSTANTIVE_SUMMARY_CHARS, summary_source=None)
        snippet = _Source("A1", "x" * 5000, summary_source="search_snippet")
        self.assertFalse(_source_is_checkable(short))
        self.assertTrue(_source_is_checkable(long))
        self.assertFalse(_source_is_checkable(snippet))
