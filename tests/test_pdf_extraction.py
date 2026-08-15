"""Tests for reading an uploaded PDF and turning it into a contribution.

This is the only place in the system that parses a file a stranger uploaded,
and on the public deployment that stranger is whoever has an access code. The
parsing half had no coverage at all.

The PDFs here are generated rather than mocked. Faking pypdfium2 would test
the page-selection arithmetic against my belief about what a PDF library
returns, which is the same mistake the test doubles in difficulty 36 made —
the double was cleaner than the real upstream, so the bug lived in the gap.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from academic_agent.pdf_extractor import (
    PaperContribution,
    extract_paper_contribution,
    extract_pdf_text,
)


def _pdf(pages: list[str]) -> Path:
    """Write a real PDF whose n-th page contains the n-th string."""
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    path = Path(tempfile.mkdtemp()) / "paper.pdf"
    pdf = canvas.Canvas(str(path), pagesize=letter)
    for body in pages:
        y = 750
        # One drawString per line: reportlab does not wrap, and a single long
        # call would silently run off the page and out of the extracted text.
        for line in body.split("\n"):
            pdf.drawString(60, y, line)
            y -= 14
        pdf.showPage()
    pdf.save()
    return path


class PageSelectionTests(unittest.TestCase):
    """Which pages are read decides what the LLM ever sees. A paper whose
    result is on a page that never gets selected is assessed on its
    introduction, and nothing anywhere reports that."""

    def test_a_short_paper_is_read_whole(self):
        path = _pdf([f"Page {i} content marker{i}" for i in range(1, 4)])
        text = extract_pdf_text(path)
        for i in range(1, 4):
            with self.subTest(page=i):
                self.assertIn(f"marker{i}", text)

    def test_pages_are_labelled_with_their_number(self):
        """The label is what lets a reader check a quote against the source
        document rather than trusting the extraction."""
        text = extract_pdf_text(_pdf(["alpha", "beta"]))
        self.assertIn("[Page 1]", text)
        self.assertIn("[Page 2]", text)

    def test_head_and_tail_overlap_is_not_duplicated(self):
        """On a four-page paper the first three and last two pages overlap at
        page 3. They are unioned as sets; concatenating the ranges instead
        would send that page to the model twice and spend the budget on it."""
        text = extract_pdf_text(_pdf([f"page{i} unique{i}" for i in range(1, 5)]))
        self.assertEqual(text.count("[Page 3]"), 1)

    def test_the_densest_middle_pages_are_preferred(self):
        """Results and methods sit in the middle and are the densest pages;
        the selection exists to reach them without reading the whole paper."""
        # The dense page sits LAST among the middle pages on purpose. Put it
        # first and a selector that ignores density entirely — taking the
        # first two middle pages by position — passes anyway, which is what
        # the first version of this test did until the fault was injected.
        pages = ["head one", "head two", "head three"]
        pages += [f"sparse{i}" for i in range(1, 5)]                     # pages 4-7
        pages.append("\n".join([f"dense line {i}" for i in range(30)]))  # page 8
        pages += ["tail one", "tail two"]                                # pages 9-10
        text = extract_pdf_text(_pdf(pages))
        self.assertIn("dense line 29", text)
        self.assertNotIn("sparse1", text)

    def test_only_two_middle_pages_are_taken(self):
        """Uncapped, a long paper would blow the character budget before
        reaching its conclusions."""
        pages = ["h1", "h2", "h3"]
        pages += [f"middle{i} " + "filler " * 40 for i in range(1, 6)]
        pages += ["t1", "t2"]
        text = extract_pdf_text(_pdf(pages))
        middles = sum(1 for i in range(1, 6) if f"middle{i}" in text)
        self.assertEqual(middles, 2)

    def test_the_character_budget_is_enforced(self):
        """The extracted text goes into a prompt. Over budget it is the model
        that truncates, silently, from whichever end it chooses."""
        pages = ["x " * 2000 for _ in range(3)]
        self.assertLessEqual(len(extract_pdf_text(_pdf(pages), max_chars=500)), 500)

    def test_a_blank_page_contributes_no_marker(self):
        """Scanned papers routinely carry blank separator pages; a page marker
        with nothing under it is noise in an already tight budget."""
        text = extract_pdf_text(_pdf(["real content here", "", "more content"]))
        self.assertNotIn("[Page 2]", text)

    def test_a_single_page_paper_works(self):
        """n=1 makes the head range, the tail range and the middle list
        degenerate at once."""
        self.assertIn("only page", extract_pdf_text(_pdf(["only page here"])))


class ContributionAssemblyTests(unittest.TestCase):
    """The identifier chain: an uploaded paper has to end up with a DOI or a
    URL, because EvidenceSource will not validate without one and the paper is
    injected into the pipeline as source A1."""

    _LLM_FIELDS = {
        "title": "A Solid Electrolyte Study",
        "authors": "Zhang et al.",
        "core_contribution": "A sulfide electrolyte reaching high conductivity at room temperature.",
        "application_domain": "electric vehicles",
        "key_metrics": ["25 mS/cm"],
        "delta_from_prior": "Higher conductivity than prior sulfides.",
        "commercialization_topic": "sulfide solid electrolyte for EV batteries",
        "search_keywords": ["solid electrolyte", "sulfide", "lithium metal"],
        "abstract_excerpt": "We report a sulfide electrolyte.",
    }

    def _extract(self, pages: list[str], **llm_over) -> PaperContribution:
        data = dict(self._LLM_FIELDS)
        data.update(llm_over)
        with patch("academic_agent.pdf_extractor._call_llm_json", return_value=data):
            return extract_paper_contribution(_pdf(pages))

    def test_a_doi_the_model_returns_wins(self):
        pc = self._extract(["doi:10.1000/from-text"], doi="10.1000/from-model")
        self.assertEqual(pc.doi, "10.1000/from-model")

    def test_a_doi_in_the_text_is_used_when_the_model_returns_none(self):
        """The regex is the check on the model: a DOI it invented would not
        appear in the paper, and one it missed still gets found."""
        pc = self._extract(["Preprint. doi:10.1000/from-text here"])
        self.assertEqual(pc.doi, "10.1000/from-text")

    def test_an_arxiv_url_is_used_when_there_is_no_doi(self):
        pc = self._extract(["Available at https://arxiv.org/abs/2501.01234"])
        self.assertEqual(str(pc.url), "https://arxiv.org/abs/2501.01234")
        self.assertIsNone(pc.doi)

    def test_a_placeholder_doi_is_minted_when_nothing_identifies_the_paper(self):
        """Without one the paper cannot become an EvidenceSource, so the
        upload fails at validation with nothing pointing at the cause."""
        pc = self._extract(["No identifier anywhere in this document"])
        self.assertTrue(pc.doi)
        self.assertIsNone(pc.url)

    def test_unknown_keys_from_the_model_are_dropped(self):
        """The model is asked for a fixed set of keys and is not bound to
        return exactly those. An extra one would raise on construction."""
        pc = self._extract(["text"], unexpected_field="ignore me",
                           another="also ignored")
        self.assertEqual(pc.application_domain, "electric vehicles")

    def test_a_model_response_missing_a_required_field_is_rejected(self):
        """Better a loud validation error at upload than a contribution with
        an empty core_contribution flowing into the pipeline as source A1."""
        broken = {k: v for k, v in self._LLM_FIELDS.items() if k != "core_contribution"}
        with patch("academic_agent.pdf_extractor._call_llm_json", return_value=broken), \
             self.assertRaises(ValidationError):
            extract_paper_contribution(_pdf(["text"]))
