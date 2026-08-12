"""Tests for pure/near-pure functions in pdf_extractor.py.

Covers: _find_doi, _find_arxiv_url, _detect_paper_language,
        paper_to_evidence_source.
extract_pdf_text and extract_paper_contribution are excluded because they
require pypdfium2 and a live LLM respectively.
"""

from __future__ import annotations

import unittest

from academic_agent.pdf_extractor import (
    PaperContribution,
    _detect_paper_language,
    _find_arxiv_url,
    _find_doi,
    paper_to_evidence_source,
)


# ---------------------------------------------------------------------------
# _find_doi
# ---------------------------------------------------------------------------

class FindDoiTests(unittest.TestCase):

    def test_bare_doi_in_text(self):
        self.assertEqual(_find_doi("DOI: 10.1038/nature12345"), "10.1038/nature12345")

    def test_doi_in_doi_org_url(self):
        text = "Available at https://doi.org/10.1016/j.cell.2023.01.001"
        self.assertEqual(_find_doi(text), "10.1016/j.cell.2023.01.001")

    def test_doi_trailing_punctuation_stripped(self):
        # Trailing period, comma, or closing bracket should be stripped
        result = _find_doi("See ref [10.1234/abc.xyz].")
        self.assertIsNotNone(result)
        self.assertFalse(result.endswith("]") or result.endswith("."))

    def test_returns_first_doi_when_multiple_present(self):
        text = "Paper A (10.1111/aaa) cites paper B (10.2222/bbb)"
        self.assertEqual(_find_doi(text), "10.1111/aaa")

    def test_returns_none_when_no_doi(self):
        self.assertIsNone(_find_doi("No identifier in this abstract text."))

    def test_doi_with_long_suffix(self):
        doi = "10.1007/s00521-023-08435-7"
        self.assertEqual(_find_doi(f"published at {doi}"), doi)

    def test_case_insensitive(self):
        result = _find_doi("Doi: 10.1234/UPPER.CASE")
        self.assertIsNotNone(result)
        self.assertIn("10.1234/", result)


# ---------------------------------------------------------------------------
# _find_arxiv_url
# ---------------------------------------------------------------------------

class FindArxivUrlTests(unittest.TestCase):

    def test_arxiv_colon_format(self):
        self.assertEqual(
            _find_arxiv_url("See arXiv:1706.03762 for details."),
            "https://arxiv.org/abs/1706.03762",
        )

    def test_arxiv_version_stripped(self):
        result = _find_arxiv_url("arXiv:2301.00234v3")
        self.assertEqual(result, "https://arxiv.org/abs/2301.00234")

    def test_arxiv_org_abs_url(self):
        self.assertEqual(
            _find_arxiv_url("https://arxiv.org/abs/1706.03762"),
            "https://arxiv.org/abs/1706.03762",
        )

    def test_arxiv_org_pdf_url(self):
        self.assertEqual(
            _find_arxiv_url("https://arxiv.org/pdf/2310.12345"),
            "https://arxiv.org/abs/2310.12345",
        )

    def test_case_insensitive(self):
        result = _find_arxiv_url("ARXIV: 1234.56789")
        self.assertEqual(result, "https://arxiv.org/abs/1234.56789")

    def test_five_digit_id(self):
        result = _find_arxiv_url("arXiv:2401.12345")
        self.assertEqual(result, "https://arxiv.org/abs/2401.12345")

    def test_returns_none_when_absent(self):
        self.assertIsNone(_find_arxiv_url("No preprint identifier here."))


# ---------------------------------------------------------------------------
# _detect_paper_language
# ---------------------------------------------------------------------------

class DetectPaperLanguageTests(unittest.TestCase):

    def test_english_text_returns_en(self):
        text = "This paper presents a novel approach to sequence modeling using transformers."
        self.assertEqual(_detect_paper_language(text), "en")

    def test_chinese_text_returns_zh(self):
        # Dense Chinese characters (>12% threshold)
        text = "本文提出了一种基于深度学习的新型序列建模方法，" * 20
        self.assertEqual(_detect_paper_language(text), "zh")

    def test_japanese_text_returns_ja(self):
        # Katakana/Hiragana characters
        text = "このモデルはトランスフォーマーアーキテクチャを使用しています。" * 20
        self.assertEqual(_detect_paper_language(text), "ja")

    def test_korean_text_returns_ko(self):
        text = "이 논문은 새로운 딥러닝 방법을 제안합니다." * 30
        self.assertEqual(_detect_paper_language(text), "ko")

    def test_empty_string_returns_en(self):
        self.assertEqual(_detect_paper_language(""), "en")

    def test_mostly_english_with_few_cjk_returns_en(self):
        # A handful of CJK characters in otherwise English text shouldn't flip to zh
        text = "Abstract: " + "word " * 100 + "（注）"
        self.assertEqual(_detect_paper_language(text), "en")

    def test_arabic_text_returns_ar(self):
        text = "هذا البحث يقترح نهجاً جديداً للتعلم الآلي." * 20
        self.assertEqual(_detect_paper_language(text), "ar")

    def test_russian_text_returns_ru(self):
        text = "Данная работа предлагает новый подход к моделированию." * 20
        self.assertEqual(_detect_paper_language(text), "ru")


# ---------------------------------------------------------------------------
# paper_to_evidence_source
# ---------------------------------------------------------------------------

def _make_pc(**kwargs) -> PaperContribution:
    defaults = dict(
        title="Solid Electrolyte Interface Study",
        authors="Kim et al.",
        core_contribution="We demonstrate a novel solid electrolyte with 25 mS/cm conductivity.",
        application_domain="Battery technology",
        key_metrics=["25 mS/cm ionic conductivity", "stable up to 5V"],
        delta_from_prior="Exceeds prior sulfide electrolytes by 3x at room temperature.",
        commercialization_topic="sulfide solid electrolyte for lithium-metal EV batteries",
        search_keywords=["solid electrolyte", "lithium metal", "ionic conductivity"],
        abstract_excerpt="We report a new solid-state electrolyte...",
    )
    defaults.update(kwargs)
    return PaperContribution(**defaults)


def _reachable(_url: str) -> tuple[bool, str]:
    """Stand-in for check_public_url that accepts every locator.

    Injected explicitly rather than left to the default: the real checker
    issues an HTTP request, and a test that quietly reaches doi.org is the
    exact failure mode this suite already got bitten by twice.
    """
    return True, ""


def _unreachable(_url: str) -> tuple[bool, str]:
    return False, "HTTP status 404"


class PaperToEvidenceSourceTests(unittest.TestCase):

    def test_source_id_is_always_A1(self):
        src = paper_to_evidence_source(_make_pc(doi="10.1234/test"), _reachable)
        self.assertEqual(src.source_id, "A1")

    def test_source_type_is_academic_paper(self):
        src = paper_to_evidence_source(_make_pc(doi="10.1234/test"), _reachable)
        self.assertEqual(src.source_type, "academic_paper")

    def test_credibility_tier_is_high(self):
        src = paper_to_evidence_source(_make_pc(doi="10.1234/test"), _reachable)
        self.assertEqual(src.credibility_tier, "high")

    def test_real_doi_sets_doi_and_doi_org_url(self):
        src = paper_to_evidence_source(_make_pc(doi="10.1038/s41586-023-001"), _reachable)
        self.assertEqual(src.doi, "10.1038/s41586-023-001")
        self.assertIn("doi.org", str(src.url))

    def test_placeholder_doi_stored_but_no_url(self):
        placeholder = "10.0000/uploaded-abc123"
        src = paper_to_evidence_source(_make_pc(doi=placeholder), _reachable)
        self.assertEqual(src.doi, placeholder)
        self.assertTrue(src.url is None or not src.url.startswith("https://doi.org/10.0000"))

    def test_arxiv_url_used_when_no_real_doi(self):
        src = paper_to_evidence_source(
            _make_pc(doi=None, url="https://arxiv.org/abs/1706.03762"), _reachable
        )
        self.assertIn("1706.03762", str(src.url))
        self.assertIsNone(src.doi)

    def test_doi_org_url_in_url_field_extracts_real_doi(self):
        src = paper_to_evidence_source(
            _make_pc(doi=None, url="https://doi.org/10.1016/j.cell.2024.01.001"), _reachable
        )
        self.assertEqual(src.doi, "10.1016/j.cell.2024.01.001")

    def test_evidence_summary_combines_contribution_and_delta(self):
        pc = _make_pc(doi="10.1234/test")
        src = paper_to_evidence_source(pc, _reachable)
        self.assertIn("novel solid electrolyte", src.evidence_summary)
        self.assertIn("prior sulfide", src.evidence_summary)

    def test_evidence_summary_capped_at_500_chars(self):
        long_contrib = "A" * 400
        long_delta = "B" * 400
        pc = _make_pc(doi="10.1234/test", core_contribution=long_contrib, delta_from_prior=long_delta)
        src = paper_to_evidence_source(pc, _reachable)
        self.assertLessEqual(len(src.evidence_summary), 500)

    def test_title_used_in_source(self):
        src = paper_to_evidence_source(_make_pc(doi="10.1234/test"), _reachable)
        self.assertEqual(src.title, "Solid Electrolyte Interface Study")


class PaperLocatorVerificationTests(unittest.TestCase):
    """The DOI/URL come from an LLM reading PDF text, so they are checked
    before this source is offered to the report as a citable reference."""

    def test_unresolvable_doi_is_dropped_rather_than_cited(self):
        """The bad identifier must not survive into the report. It degrades
        to the synthetic upload id, which EvidenceSource requires (a source
        with neither URL nor DOI fails model validation) and which nothing
        mistakes for a registered DOI."""
        src = paper_to_evidence_source(_make_pc(doi="10.1234/hallucinated"), _unreachable)
        self.assertIsNone(src.url)
        self.assertNotEqual(src.doi, "10.1234/hallucinated")
        self.assertTrue(src.doi.startswith("10.0000/uploaded-"))

    def test_unresolvable_locator_downgrades_credibility(self):
        """"high" asserts a reader can go and check it — without a working
        locator that claim is not the pipeline's to make."""
        src = paper_to_evidence_source(_make_pc(doi="10.1234/hallucinated"), _unreachable)
        self.assertEqual(src.credibility_tier, "medium")
        self.assertIn("no independently resolvable", src.credibility_reason)

    def test_unreachable_url_falls_back_to_the_doi_resolver(self):
        """A dead publisher link does not condemn a DOI extracted separately."""
        checks = []

        def only_doi_org_resolves(url: str) -> tuple[bool, str]:
            checks.append(url)
            return (True, "") if url.startswith("https://doi.org/") else (False, "HTTP status 404")

        src = paper_to_evidence_source(
            _make_pc(doi="10.1038/s41586-023-001", url="https://publisher.example/dead"),
            only_doi_org_resolves,
        )
        self.assertEqual(src.doi, "10.1038/s41586-023-001")
        self.assertEqual(str(src.url), "https://doi.org/10.1038/s41586-023-001")
        self.assertEqual(src.credibility_tier, "high")
        self.assertIn("https://publisher.example/dead", checks)

    def test_unreachable_arxiv_url_leaves_no_real_locator(self):
        src = paper_to_evidence_source(
            _make_pc(doi=None, url="https://arxiv.org/abs/9999.99999"), _unreachable
        )
        self.assertIsNone(src.url)
        self.assertTrue(src.doi.startswith("10.0000/uploaded-"))
        self.assertEqual(src.credibility_tier, "medium")

    def test_placeholder_fallback_is_stable_for_the_same_paper(self):
        """Dedup and citation tracking key off this id, so two uploads of
        the same paper must not become two different sources."""
        first = paper_to_evidence_source(_make_pc(doi="10.1234/nope"), _unreachable)
        second = paper_to_evidence_source(_make_pc(doi="10.1234/nope"), _unreachable)
        self.assertEqual(first.doi, second.doi)

    def test_placeholder_doi_never_triggers_a_network_check(self):
        """Nothing to resolve, so nothing should be looked up — and the
        paper still keeps its placeholder id for dedup/citation tracking."""
        checks = []

        def recording(url: str) -> tuple[bool, str]:
            checks.append(url)
            return True, ""

        src = paper_to_evidence_source(_make_pc(doi="10.0000/uploaded-abc123"), recording)
        self.assertEqual(checks, [])
        self.assertEqual(src.doi, "10.0000/uploaded-abc123")
        self.assertEqual(src.credibility_tier, "medium")

    def test_paper_is_kept_even_when_no_locator_verifies(self):
        """The upload is still the researcher's own primary source — it is
        the citation claim that degrades, not the evidence itself."""
        src = paper_to_evidence_source(_make_pc(doi="10.1234/nope"), _unreachable)
        self.assertEqual(src.source_id, "A1")
        self.assertEqual(src.title, "Solid Electrolyte Interface Study")
        self.assertIn("novel solid electrolyte", src.evidence_summary)


if __name__ == "__main__":
    unittest.main()
