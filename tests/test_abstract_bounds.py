"""Bounded abstracts keep their closing sentences.

Abstracts end with results and conclusions. Cutting at the first 1,500
characters dropped exactly that part: 42 of 120 abstract-backed academic
sources in 95 saved runs stopped at the cap, all mid-sentence. The cap stays
1,500 because the saved-source locator reads at most 1,500 code points per
source; what changes is which part is kept.
"""

from __future__ import annotations

from datetime import date
from unittest import TestCase

from academic_agent.evidence import EvidenceSource
from academic_agent.source_pipeline import (
    _ABSTRACT_MAX_CHARS,
    _ABSTRACT_TAIL_CHARS,
    _ELISION,
    _academic_source,
    _bounded_abstract,
)

_OPENING = "Solid electrolytes promise safer lithium-metal batteries."
_CONCLUSION = "The cell retained 91.4% capacity after 800 cycles at 1C."


def _long_abstract(middle_sentences: int = 40) -> str:
    middle = " ".join(
        f"Method detail {i} describes an intermediate processing step."
        for i in range(middle_sentences)
    )
    return f"{_OPENING} {middle} {_CONCLUSION}"


class BoundedAbstractTests(TestCase):

    def test_text_within_the_cap_is_unchanged(self):
        for text in ("Short abstract.", "x" * _ABSTRACT_MAX_CHARS):
            with self.subTest(length=len(text)):
                self.assertEqual(_bounded_abstract(text), text)

    def test_long_abstract_keeps_opening_and_conclusion(self):
        text = _long_abstract()
        self.assertGreater(len(text), _ABSTRACT_MAX_CHARS)
        bounded = _bounded_abstract(text)
        self.assertLessEqual(len(bounded), _ABSTRACT_MAX_CHARS)
        self.assertTrue(bounded.startswith(_OPENING))
        self.assertTrue(bounded.endswith(_CONCLUSION))
        self.assertIn(_ELISION, bounded)

    def test_old_prefix_cut_lost_the_conclusion(self):
        """The regression this replaces, stated directly."""
        text = _long_abstract()
        self.assertNotIn(_CONCLUSION, text[:_ABSTRACT_MAX_CHARS])
        self.assertIn(_CONCLUSION, _bounded_abstract(text))

    def test_both_parts_are_whole_sentences_and_do_not_overlap(self):
        text = _long_abstract()
        head, tail = _bounded_abstract(text).split(_ELISION)
        self.assertTrue(head.endswith("."))
        self.assertTrue(text.startswith(head))
        self.assertTrue(text.endswith(tail))
        self.assertLess(len(head), text.index(tail))
        self.assertLessEqual(len(tail), _ABSTRACT_TAIL_CHARS)

    def test_cjk_abstract_splits_on_cjk_sentence_ends(self):
        opening = "本文提出一种卤化物固态电解质。"
        conclusion = "电池在八百次循环后容量保持率为百分之九十一。"
        text = opening + "实验细节描述了中间加工步骤。" * 120 + conclusion
        bounded = _bounded_abstract(text)
        self.assertLessEqual(len(bounded), _ABSTRACT_MAX_CHARS)
        self.assertTrue(bounded.startswith(opening))
        self.assertTrue(bounded.endswith(conclusion))

    def test_decimal_points_are_not_sentence_ends(self):
        text = _OPENING + " " + "A value of 3.5 eV was measured. " * 60 + _CONCLUSION
        head, _tail = _bounded_abstract(text).split(_ELISION)
        self.assertFalse(head.endswith("3."))

    def test_unpunctuated_text_is_cut_at_a_word_with_an_ellipsis(self):
        text = "word " * 600
        bounded = _bounded_abstract(text.strip())
        self.assertLessEqual(len(bounded), _ABSTRACT_MAX_CHARS)
        self.assertTrue(bounded.endswith("…"))
        self.assertNotIn(_ELISION, bounded)
        self.assertTrue(bounded[:-1].endswith("word"))

    def test_overlong_final_sentence_falls_back_to_the_opening(self):
        """No tail fits, so keep the opening rather than cut the conclusion."""
        text = _long_abstract() + " " + "conclusion " * 100 + "ends."
        bounded = _bounded_abstract(text)
        self.assertLessEqual(len(bounded), _ABSTRACT_MAX_CHARS)
        self.assertTrue(bounded.startswith(_OPENING))
        self.assertTrue(bounded.endswith("…"))

    def test_bounded_text_satisfies_the_evidence_summary_floor(self):
        bounded = _bounded_abstract(_long_abstract())
        source = EvidenceSource(
            source_id="A1", title="Solid electrolytes", publisher="Test Publisher",
            doi="10.1234/solid-electrolyte",
            accessed_date=date(2026, 1, 1), source_type="academic_paper",
            evidence_summary=bounded,
        )
        self.assertEqual(source.evidence_summary, bounded)


class CrossrefPathTests(TestCase):
    """End to end through a real academic constructor."""

    def test_crossref_abstract_keeps_its_conclusion(self):
        item = {
            "DOI": "10.1234/solid-electrolyte",
            "title": ["Solid Electrolytes for Lithium Metal Batteries"],
            "publisher": "Test Publisher",
            "abstract": f"<jats:p>{_long_abstract()}</jats:p>",
            "published": {"date-parts": [[2025, 1, 1]]},
        }

        class StaticCrossref:
            def lookup_doi(self, doi: str) -> dict | None:
                return item

            def search_title(self, title: str) -> list[dict]:
                return [item]

        source, reason = _academic_source(
            {
                "title": "Solid Electrolytes for Lithium Metal Batteries",
                "link": "https://doi.org/10.1234/solid-electrolyte",
                "snippet": "A search snippet.",
            },
            "A1", StaticCrossref(), date(2026, 7, 2),
            "solid electrolytes for lithium metal batteries",
        )
        self.assertEqual(reason, "")
        self.assertIsNotNone(source)
        self.assertLessEqual(len(source.evidence_summary), _ABSTRACT_MAX_CHARS)
        self.assertIn(_CONCLUSION, source.evidence_summary)
