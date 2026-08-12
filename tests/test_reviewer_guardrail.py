"""Tests for the reviewer guardrail — regression protection on Task 5.

Task 4 produces a report that has already passed structural and citation
validation. Task 5's job is to correct it, but correction can itself do
damage: summarising instead of editing, dropping a section, or stripping
citation markers while rewording a sentence.

This guardrail treats the Task 4 output as a baseline and refuses any review
that lost ground against it. Nothing else in the pipeline re-checks Task 5, so
a failure here reaches the user directly — pipeline_worker persists this task's
text, not Task 4's.

That last point is why the guardrail also re-runs Task 4's citation and
disclaimer validation when the evidence tasks are supplied: the baseline checks
only cover what the reviewer removed, and say nothing about what it added.
"""

from __future__ import annotations

import unittest
from datetime import date

from academic_agent.evidence import (
    EvidenceFinding,
    EvidenceReport,
    EvidenceSource,
    make_reviewer_guardrail,
)


class _Output:
    def __init__(self, raw: str):
        self.raw = raw
        self.pydantic = None


class _Task:
    """Stand-in for the completed Task 4 whose output is the baseline."""

    def __init__(self, raw: str):
        self.output = _Output(raw)


def _report(body_filler: int = 1, citations: str = "[A1][P1][M1]") -> str:
    """A report long enough to clear the 500-char floor."""
    body = "Evidence indicates commercial deployment is underway. " * body_filler
    return (
        "# Academic Commercialization Assessment: Solid Electrolyte\n\n"
        "## Executive Summary\n\n"
        f"{body} Findings are supported by {citations}.\n\n"
        "## 1. Technology Overview & Maturity\n\n"
        f"{body}\n\n"
        "## Evidence Limitations\n\n"
        "Single-source market estimates.\n\n"
        "## References\n\n"
        "- [A1] Kim et al. https://doi.org/10.1234/x\n"
        "- [P1] Patent record\n"
        "- [M1] Market report\n"
    )


_DRAFT = _report(6)


def _run(reviewed: str, draft: str = _DRAFT, **kw):
    guardrail = make_reviewer_guardrail(_Task(draft), **kw)
    ok, result = guardrail(_Output(reviewed))
    return ok, (result.raw if ok else result)


class _EvidenceTask:
    """A completed evidence task (1/2/3), whose sources define which citation
    IDs are real. collect_context_sources reads output.pydantic."""

    def __init__(self, report: EvidenceReport):
        self.output = _Output(report.model_dump_json())
        self.output.pydantic = report


def _evidence_report(prefix: str) -> EvidenceReport:
    source = EvidenceSource(
        source_id=f"{prefix}1",
        title=f"Source {prefix}1 with a sufficiently long title",
        url=f"https://records.test-domain.org/{prefix.lower()}1",
        publisher="Publisher",
        accessed_date=date.today(),
        source_type="academic_paper",
        evidence_summary=(
            "This source directly supports the corresponding finding with "
            "relevant experimental data and reported measurements."
        ),
    )
    finding = EvidenceFinding(
        finding_id=f"{prefix}F1",
        category="technology maturity",
        claim="A sufficiently detailed and externally supportable research conclusion.",
        claim_type="observed_fact",
        source_ids=[f"{prefix}1"],
        confidence="high",
        commercial_implication="This affects the commercialization pathway.",
    )
    return EvidenceReport(
        topic="Solid electrolyte",
        scope_summary="A bounded review of technical maturity and published evidence.",
        search_queries=["solid electrolyte commercial maturity"],
        findings=[finding],
        sources=[source],
        limitations=["Publicly available evidence may omit private deployments."],
    )


_EVIDENCE_TASKS = [_EvidenceTask(_evidence_report(p)) for p in ("A", "P", "M")]


def _complete_report(citations: str = "[A1][P1][M1]") -> str:
    """A report carrying every section _REQUIRED_REPORT_HEADINGS demands.

    The smaller _report() fixture above predates step 4 and omits most
    sections — fine for the baseline checks, which only look at a few
    headings, but step 4 runs the same full validation Task 4 does, and a
    real reviewer input has always been a complete Task 4 report.
    """
    body = "Evidence indicates commercial deployment is underway. " * 3
    return (
        "# Academic Commercialization Assessment: Solid Electrolyte\n\n"
        "## Executive Summary\n\n"
        f"{body} Findings are supported by {citations}.\n\n"
        "## 1. Technology Overview & Maturity\n\n"
        f"{body} [A1]\n\n"
        "## 2. Patent Landscape & White Spaces\n\n"
        f"{body} [P1]\n\n"
        "Patent analysis here is a landscape review and not a legal "
        "freedom-to-operate opinion; claims-level review by qualified patent "
        "counsel is required.\n\n"
        "## 3. Target Industries & Use Cases\n\n"
        f"{body} [M1]\n\n"
        "## 4. Competitive Landscape\n\n"
        f"{body} [M1]\n\n"
        "## 5. Commercialization Opportunities & Recommendations\n\n"
        f"{body} [A1]\n\n"
        "## Evidence Limitations\n\n"
        "Single-source market estimates.\n\n"
        "## References\n\n"
        "- [A1] Source A1 https://records.test-domain.org/a1\n"
        "- [P1] Source P1 https://records.test-domain.org/p1\n"
        "- [M1] Source M1 https://records.test-domain.org/m1\n"
    )


class ReviewerAddedContentTests(unittest.TestCase):
    """The baseline checks catch what the reviewer removed. These cover what
    it added — which matters more, because Task 5's text is what ships."""

    def test_citation_to_a_source_that_does_not_exist_is_rejected(self):
        """The reviewer inventing [A99] must not reach the delivered report."""
        draft = _complete_report()
        reviewed = _complete_report(citations="[A1][P1][M1][A99]")
        ok, message = _run(reviewed, draft=draft, context_tasks=_EVIDENCE_TASKS)
        self.assertFalse(ok)
        self.assertIn("A99", message)

    def test_dropping_the_patent_disclaimer_is_repaired(self):
        """A reviewer that deletes it gets it put back rather than failing the
        run — normalize_final_report restores the disclaimer deterministically.

        Reaching that repair at all is the point: before the reviewer output
        was normalized, a review that dropped the disclaimer shipped without
        it, leaving a landscape review that reads as legal clearance.
        """
        draft = _complete_report()
        reviewed = draft.replace(
            "Patent analysis here is a landscape review and not a legal "
            "freedom-to-operate opinion; claims-level review by qualified patent "
            "counsel is required.\n\n",
            "",
        )
        self.assertNotIn("freedom-to-operate", reviewed)

        ok, result = _run(reviewed, draft=draft, context_tasks=_EVIDENCE_TASKS)
        self.assertTrue(ok)
        self.assertIn("freedom-to-operate", result)

    def test_an_untouched_review_still_passes(self):
        """The added validation must not reject a genuinely correct review —
        a false positive here fails the whole run at its most expensive point."""
        draft = _complete_report()
        ok, _result = _run(draft, draft=draft, context_tasks=_EVIDENCE_TASKS)
        self.assertTrue(ok)

    def test_validation_is_skipped_when_no_evidence_tasks_are_supplied(self):
        """Backwards compatible: without the source registry there is nothing
        to validate citations against, so only the baseline checks apply."""
        ok, _result = _run(_report(6, citations="[A1][P1][M1][A99]"))
        self.assertTrue(ok)


# ---------------------------------------------------------------------------
# Length regression
# ---------------------------------------------------------------------------

class LengthRegressionTests(unittest.TestCase):

    def test_unchanged_report_passes(self):
        ok, _ = _run(_DRAFT)
        self.assertTrue(ok)

    def test_minor_edits_pass(self):
        reviewed = _DRAFT.replace("is underway", "has begun")
        self.assertTrue(_run(reviewed)[0])

    def test_summary_instead_of_report_rejected(self):
        """The most common failure: the reviewer summarises rather than edits."""
        ok, msg = _run("## Executive Summary\n\nLooks fine. [A1][P1][M1]\n## References\n")
        self.assertFalse(ok)
        self.assertIn("too short", msg)

    def test_heavy_truncation_rejected(self):
        """Keeping under 80% of the draft means whole sections went missing.

        Sizes are chosen so the reviewed text clears the 500-char absolute
        floor — otherwise this would test that check instead of the ratio.
        """
        reviewed = _report(6)                    # 962 chars, well over the floor
        ok, msg = _run(reviewed, draft=_report(20))   # 2474 chars → 39% retained
        self.assertFalse(ok)
        self.assertIn("shrank", msg)

    def test_rejection_reports_the_retained_share(self):
        ok, msg = _run(_report(6), draft=_report(20))
        self.assertFalse(ok)
        self.assertIn("retained", msg)

    def test_modest_shrinkage_allowed(self):
        """Tightening prose is the reviewer's job — only large losses are blocked."""
        draft = _report(10)
        reviewed = _report(9)
        self.assertTrue(_run(reviewed, draft=draft)[0])

    def test_growth_is_fine(self):
        self.assertTrue(_run(_report(12), draft=_report(6))[0])


# ---------------------------------------------------------------------------
# Required sections
# ---------------------------------------------------------------------------

class RequiredSectionTests(unittest.TestCase):

    def test_missing_executive_summary_rejected(self):
        reviewed = _DRAFT.replace("## Executive Summary", "## Overview")
        ok, msg = _run(reviewed)
        self.assertFalse(ok)
        self.assertIn("missing", msg.lower())

    def test_reviewer_dropping_a_word_from_the_title_is_rejected(self):
        """The reviewer must not reword the document title.

        Observed in a real run: Task 4 emitted the correct
        "# Academic Commercialization Assessment: ..." and the reviewer returned
        "# Commercialization Assessment: ...". Task 4's guardrail enforces the
        full heading set, but only a subset was re-checked after review, so the
        edit reached the user and the benchmark reported a missing section.
        """
        reviewed = _DRAFT.replace(
            "# Academic Commercialization Assessment: Solid Electrolyte",
            "# Commercialization Assessment: Solid Electrolyte",   # "Academic" dropped
        )
        ok, msg = _run(reviewed)
        self.assertFalse(ok)
        self.assertIn("missing", msg.lower())

    def test_intact_title_still_passes(self):
        self.assertTrue(_run(_DRAFT)[0])

    def test_missing_references_rejected(self):
        reviewed = _DRAFT.replace("## References", "## Sources Consulted")
        ok, msg = _run(reviewed)
        self.assertFalse(ok)
        self.assertIn("missing", msg.lower())

    def test_localized_headings_accepted(self):
        """A Chinese report must not fail for lacking English headings."""
        localized = (
            "# 商业化评估\n\n## 执行摘要\n\n"
            + "证据表明商业化部署正在进行中。" * 40
            + " [A1][P1][M1]\n\n## 证据局限性\n\n单一来源。\n\n## 参考文献\n\n"
            "- [A1] Kim et al.\n- [P1] 专利\n- [M1] 市场报告\n"
        )
        ok, _ = _run(
            localized,
            draft=localized,
            localized_headings=("# 商业化评估", "## 执行摘要", "## 证据局限性", "## 参考文献"),
            output_language="Simplified Chinese",
        )
        self.assertTrue(ok)

    def test_english_references_accepted_in_localized_report(self):
        """References is emitted in English even for localized reports."""
        localized = (
            "# 商业化评估\n\n## 执行摘要\n\n"
            + "证据表明商业化部署正在进行中。" * 40
            + " [A1][P1][M1]\n\n## 证据局限性\n\n单一来源。\n\n## References\n\n"
            "- [A1] Kim et al.\n"
        )
        ok, _ = _run(
            localized,
            draft=localized,
            localized_headings=("# 商业化评估", "## 执行摘要", "## 证据局限性", "## 参考文献"),
            output_language="Simplified Chinese",
        )
        self.assertTrue(ok)


# ---------------------------------------------------------------------------
# Citation preservation
# ---------------------------------------------------------------------------

class CitationPreservationTests(unittest.TestCase):

    def test_all_citations_kept_passes(self):
        self.assertTrue(_run(_DRAFT)[0])

    def test_dropped_citation_rejected(self):
        """Rewording a sentence must not take its citation with it.

        The reference entry is removed too — otherwise the ID would still be
        present in the References block and nothing would have been lost.
        """
        reviewed = (_DRAFT
                    .replace("[A1][P1][M1]", "[A1][P1]")
                    .replace("- [M1] Market report\n", ""))
        ok, msg = _run(reviewed)
        self.assertFalse(ok)
        self.assertIn("M1", msg)

    def test_all_dropped_citations_listed(self):
        reviewed = (_DRAFT
                    .replace("[A1][P1][M1]", "[A1]")
                    .replace("- [P1] Patent record\n", "")
                    .replace("- [M1] Market report\n", ""))
        ok, msg = _run(reviewed)
        self.assertFalse(ok)
        self.assertIn("M1", msg)
        self.assertIn("P1", msg)

    def test_citation_kept_in_references_only_still_counts(self):
        """An ID surviving in the References block has not been lost.

        The check is about losing provenance, not about where it appears.
        """
        reviewed = _DRAFT.replace("[A1][P1][M1]", "[A1][P1]")
        self.assertTrue(_run(reviewed)[0])

    def test_added_citation_allowed(self):
        """The reviewer may strengthen support; it may not weaken it."""
        reviewed = _DRAFT.replace("[A1][P1][M1]", "[A1][P1][M1][A2]")
        self.assertTrue(_run(reviewed)[0])

    def test_only_bracketed_ids_count(self):
        """Bare tokens like 'A1 grade' are prose, not citations.

        Counting them would make the check fire on unrelated wording changes.
        """
        draft = _DRAFT + "\nThe A1 grade material and P2 process are standard.\n"
        reviewed = _DRAFT + "\nStandard materials and processes are used.\n"
        self.assertTrue(_run(reviewed, draft=draft)[0])

    def test_citation_moved_between_sections_is_fine(self):
        reviewed = _DRAFT.replace(
            "Findings are supported by [A1][P1][M1].", "Findings are supported."
        ).replace(
            "## Evidence Limitations", "Supported by [A1][P1][M1].\n\n## Evidence Limitations"
        )
        self.assertTrue(_run(reviewed)[0])


# ---------------------------------------------------------------------------
# Patent disclaimer re-insertion
# ---------------------------------------------------------------------------

class PatentDisclaimerTests(unittest.TestCase):
    """The disclaimer is legally required, so a reviewer that drops it is fixed
    rather than rejected — failing the task would lose the whole review."""

    def test_missing_disclaimer_is_reinserted(self):
        ok, raw = _run(_DRAFT)
        self.assertTrue(ok)
        self.assertGreater(len(raw), len(_DRAFT))

    def test_disclaimer_lands_before_evidence_limitations(self):
        ok, raw = _run(_DRAFT)
        self.assertTrue(ok)
        self.assertLess(raw.index("## Evidence Limitations"), raw.index("## References"))

    def test_existing_disclaimer_not_duplicated(self):
        ok, once = _run(_DRAFT)
        self.assertTrue(ok)
        ok2, twice = _run(once, draft=_DRAFT)
        self.assertTrue(ok2)
        self.assertEqual(len(once), len(twice))


# ---------------------------------------------------------------------------
# Error aggregation
# ---------------------------------------------------------------------------

class ErrorAggregationTests(unittest.TestCase):

    def test_multiple_problems_reported_together(self):
        """One retry should carry every problem, not just the first."""
        reviewed = "## Overview\n\nToo short and missing citations.\n"
        ok, msg = _run(reviewed)
        self.assertFalse(ok)
        self.assertGreaterEqual(msg.count("\n- "), 2)

    def test_message_is_actionable(self):
        ok, msg = _run("tiny")
        self.assertFalse(ok)
        self.assertIn("blocking issues", msg)

    def test_absent_baseline_still_enforces_floor(self):
        """With no Task 4 output, only absolute checks can run — they still do."""
        guardrail = make_reviewer_guardrail(None)
        ok, msg = guardrail(_Output("tiny"))
        self.assertFalse(ok)
        self.assertIn("too short", msg)


if __name__ == "__main__":
    unittest.main()
