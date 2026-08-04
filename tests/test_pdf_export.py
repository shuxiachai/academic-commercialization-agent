"""Tests for PDF export.

This module has a history worth guarding: CJK reports once rendered as blank
boxes because the original engine referenced fonts instead of embedding them.
The failure was silent — a perfectly valid PDF came out, just unreadable — so
the tests below assert on the things that made it wrong: which font gets
registered, which characters get normalised, and whether CJK output actually
carries an embedded face (its file size).
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from reportlab.platypus import HRFlowable, Paragraph, Spacer, Table

from ui.pdf_export import (
    _CID_FONT_MAP,
    _CJK_TTF_CANDIDATES,
    _EMBEDDED_FONT_NAME,
    _FALLBACK_FONT,
    _UNICODE_FIX,
    _build_styles,
    _generate_pdf,
    _make_story_parser,
    _resolve_font,
    markdown_to_story,
)


def _story(md: str) -> list:
    """Render markdown to flowables using a font that is always available."""
    return markdown_to_story(md, _build_styles(_FALLBACK_FONT))


def _texts(story: list) -> list[str]:
    return [f.text for f in story if isinstance(f, Paragraph)]


# ---------------------------------------------------------------------------
# _UNICODE_FIX — the glyphs CJK faces lack
# ---------------------------------------------------------------------------

class UnicodeFixTests(unittest.TestCase):

    def test_subscript_digits_become_plain(self):
        self.assertEqual("CO₂".translate(_UNICODE_FIX), "CO2")

    def test_superscript_digits_become_plain(self):
        self.assertEqual("m³".translate(_UNICODE_FIX), "m3")

    def test_full_subscript_range_mapped(self):
        self.assertEqual("₀₁₂₃₄₅₆₇₈₉".translate(_UNICODE_FIX), "0123456789")

    def test_full_superscript_range_mapped(self):
        self.assertEqual("⁰¹²³⁴⁵⁶⁷⁸⁹".translate(_UNICODE_FIX), "0123456789")

    def test_en_and_em_dashes_become_hyphen(self):
        self.assertEqual("5–10".translate(_UNICODE_FIX), "5-10")
        self.assertEqual("a—b".translate(_UNICODE_FIX), "a-b")

    def test_minus_sign_becomes_hyphen(self):
        self.assertEqual("−40".translate(_UNICODE_FIX), "-40")

    def test_every_mapped_dash_variant(self):
        for ch in "‐‑‒―−–—":
            with self.subTest(char=ch):
                self.assertEqual(ch.translate(_UNICODE_FIX), "-")

    def test_ordinary_text_untouched(self):
        text = "TRL 6/9 — 固态电解质 (25 mS/cm)"
        out = text.translate(_UNICODE_FIX)
        self.assertIn("固态电解质", out)
        self.assertIn("25 mS/cm", out)

    def test_ascii_hyphen_unchanged(self):
        self.assertEqual("well-known".translate(_UNICODE_FIX), "well-known")


# ---------------------------------------------------------------------------
# _resolve_font — the embedded → CID → Helvetica fallback chain
# ---------------------------------------------------------------------------

class ResolveFontTests(unittest.TestCase):

    def test_english_gets_helvetica(self):
        self.assertEqual(_resolve_font("English"), _FALLBACK_FONT)

    def test_unknown_language_gets_helvetica(self):
        self.assertEqual(_resolve_font("Klingon"), _FALLBACK_FONT)

    @patch("ui.pdf_export.Path.is_file", return_value=True)
    @patch("reportlab.pdfbase.pdfmetrics.registerFont")
    def test_embedded_font_preferred_when_file_exists(self, mock_reg, _mock_isfile):
        self.assertEqual(_resolve_font("Simplified Chinese"), _EMBEDDED_FONT_NAME)
        self.assertTrue(mock_reg.called)

    @patch("ui.pdf_export.Path.is_file", return_value=True)
    @patch("reportlab.pdfbase.pdfmetrics.registerFont")
    def test_first_existing_candidate_wins(self, _mock_reg, _mock_isfile):
        """Registration must stop at the first hit, not walk the whole list."""
        with patch("reportlab.pdfbase.ttfonts.TTFont") as mock_ttf:
            _resolve_font("Japanese")
            self.assertEqual(mock_ttf.call_count, 1)
            used_path = mock_ttf.call_args[0][1]
            self.assertEqual(used_path, _CJK_TTF_CANDIDATES["Japanese"][0])

    @patch("ui.pdf_export.Path.is_file", return_value=False)
    def test_falls_back_to_cid_when_no_ttf_present(self, _mock_isfile):
        """No TrueType on disk → the CID face for that language."""
        self.assertEqual(
            _resolve_font("Simplified Chinese"),
            _CID_FONT_MAP["Simplified Chinese"],
        )

    @patch("ui.pdf_export.Path.is_file", return_value=False)
    @patch("reportlab.pdfbase.cidfonts.UnicodeCIDFont", side_effect=Exception("no cid"))
    def test_falls_back_to_helvetica_when_cid_also_fails(self, _mock_cid, _mock_isfile):
        self.assertEqual(_resolve_font("Korean"), _FALLBACK_FONT)

    @patch("ui.pdf_export.Path.is_file", return_value=True)
    def test_corrupt_ttf_skipped_not_fatal(self, _mock_isfile):
        """A broken font file must not abort the chain."""
        with patch("reportlab.pdfbase.ttfonts.TTFont", side_effect=Exception("corrupt")):
            # Every TTF candidate raises, so it must land on the CID font.
            self.assertEqual(
                _resolve_font("Traditional Chinese"),
                _CID_FONT_MAP["Traditional Chinese"],
            )

    def test_every_cjk_language_has_candidates(self):
        for lang in _CID_FONT_MAP:
            with self.subTest(language=lang):
                self.assertTrue(_CJK_TTF_CANDIDATES.get(lang))


# ---------------------------------------------------------------------------
# _build_styles
# ---------------------------------------------------------------------------

class BuildStylesTests(unittest.TestCase):

    def test_returns_all_keys_used_by_the_parser(self):
        styles = _build_styles("Helvetica")
        for key in ("font", "H1", "H2", "H3", "Body", "LI", "TH", "TD",
                    "Mono", "BLUE", "GRID", "TH_BG"):
            with self.subTest(key=key):
                self.assertIn(key, styles)

    def test_font_name_propagates_to_paragraph_styles(self):
        styles = _build_styles("EmbeddedCJK")
        self.assertEqual(styles["font"], "EmbeddedCJK")
        self.assertEqual(styles["Body"].fontName, "EmbeddedCJK")
        self.assertEqual(styles["TH"].fontName, "EmbeddedCJK")


# ---------------------------------------------------------------------------
# markdown_to_story — markdown/HTML → flowables
# ---------------------------------------------------------------------------

class StoryStructureTests(unittest.TestCase):

    def test_h1_emits_paragraph_and_rule(self):
        story = _story("# Title")
        self.assertIn("Title", _texts(story))
        self.assertTrue(any(isinstance(f, HRFlowable) for f in story))

    def test_h2_emits_paragraph_and_rule(self):
        story = _story("## Section")
        self.assertIn("Section", _texts(story))
        self.assertTrue(any(isinstance(f, HRFlowable) for f in story))

    def test_h3_has_no_rule(self):
        story = _story("### Sub")
        self.assertIn("Sub", _texts(story))
        self.assertFalse(any(isinstance(f, HRFlowable) for f in story))

    def test_paragraph_text_preserved(self):
        self.assertIn("Plain body text.", _texts(_story("Plain body text.")))

    def test_list_items_get_bullet_prefix(self):
        texts = _texts(_story("- first\n- second\n"))
        self.assertTrue(any(t.startswith("•") and "first" in t for t in texts))
        self.assertTrue(any(t.startswith("•") and "second" in t for t in texts))

    def test_empty_markdown_yields_empty_story(self):
        self.assertEqual(_story(""), [])

    def test_bold_becomes_reportlab_markup(self):
        self.assertTrue(any("<b>" in t for t in _texts(_story("A **bold** word."))))

    def test_italic_becomes_reportlab_markup(self):
        self.assertTrue(any("<i>" in t for t in _texts(_story("An *italic* word."))))

    def test_inline_code_uses_courier(self):
        self.assertTrue(any("Courier" in t for t in _texts(_story("Use `run()` here."))))


class StoryEscapingTests(unittest.TestCase):
    """Bare &, < and > must be escaped or reportlab's XML parser rejects them."""

    def test_ampersand_escaped(self):
        self.assertTrue(any("&amp;" in t for t in _texts(_story("R&D spending"))))

    def test_angle_brackets_escaped(self):
        texts = _texts(_story("values 5 < 10 and 20 > 3"))
        joined = " ".join(texts)
        self.assertIn("&lt;", joined)
        self.assertIn("&gt;", joined)

    def test_escaped_text_still_renders_to_pdf(self):
        """The escaping has to survive an actual doc.build(), not just look right."""
        with tempfile.TemporaryDirectory() as tmp:
            path = _generate_pdf("# T\n\nA & B, 5 < 10, x > y\n", Path(tmp))
            self.assertIsNotNone(path)
            self.assertGreater(path.stat().st_size, 0)

    def test_bold_markup_not_double_escaped(self):
        """Inline tags are generated, not user data — they must stay literal."""
        texts = _texts(_story("**strong**"))
        joined = " ".join(texts)
        self.assertIn("<b>", joined)
        self.assertNotIn("&lt;b&gt;", joined)


class StoryTableTests(unittest.TestCase):

    _MD = (
        "| Metric | Value |\n"
        "|---|---|\n"
        "| TRL | 6 |\n"
        "| MRL | 4 |\n"
    )

    def test_table_flowable_emitted(self):
        self.assertTrue(any(isinstance(f, Table) for f in _story(self._MD)))

    def test_table_has_header_plus_data_rows(self):
        table = next(f for f in _story(self._MD) if isinstance(f, Table))
        self.assertEqual(len(table._cellvalues), 3)      # header + 2 rows

    def test_table_cell_content_preserved(self):
        table = next(f for f in _story(self._MD) if isinstance(f, Table))
        flat = [c.text for row in table._cellvalues for c in row]
        self.assertIn("Metric", flat)
        self.assertIn("TRL", flat)
        self.assertIn("6", flat)

    def test_ragged_table_renders_without_error(self):
        """A row with fewer cells than the header must still render.

        Note on what this does and does not prove: reportlab's Table pads
        short rows itself, so the explicit padding in _build_table is
        defensive rather than load-bearing — removing it does not change
        observable behaviour. This test therefore asserts the contract that
        actually matters (jagged input produces a usable PDF) instead of
        asserting an internal detail that the library would satisfy anyway.
        """
        from reportlab.lib.pagesizes import A4
        from reportlab.platypus import SimpleDocTemplate

        html = (
            "<table><tr><th>A</th><th>B</th><th>C</th></tr>"
            "<tr><td>only one</td></tr></table>"
        )
        parser = _make_story_parser(_build_styles(_FALLBACK_FONT))
        parser.feed(html)

        table = next(f for f in parser.story if isinstance(f, Table))
        self.assertEqual(len(table._cellvalues), 2)

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "t.pdf"
            SimpleDocTemplate(str(out), pagesize=A4).build(parser.story)
            self.assertGreater(out.stat().st_size, 0)

    def test_table_followed_by_spacer(self):
        story = _story(self._MD)
        idx = next(i for i, f in enumerate(story) if isinstance(f, Table))
        self.assertTrue(any(isinstance(f, Spacer) for f in story[idx:]))


class StoryUnicodeTests(unittest.TestCase):
    """The normalisation has to happen on the way into the story, not later."""

    def test_subscript_normalised_in_body(self):
        self.assertTrue(any("CO2" in t for t in _texts(_story("Captures CO₂ well."))))

    def test_dash_normalised_in_body(self):
        self.assertTrue(any("5-10" in t for t in _texts(_story("Range 5–10 units."))))

    def test_normalisation_applies_inside_table_cells(self):
        md = "| Gas | Range |\n|---|---|\n| CO₂ | 5–10 |\n"
        table = next(f for f in _story(md) if isinstance(f, Table))
        flat = [c.text for row in table._cellvalues for c in row]
        self.assertIn("CO2", flat)
        self.assertIn("5-10", flat)

    def test_normalisation_applies_inside_list_items(self):
        texts = _texts(_story("- CO₂ at 5–10 bar\n"))
        self.assertTrue(any("CO2" in t and "5-10" in t for t in texts))


# ---------------------------------------------------------------------------
# _generate_pdf — end to end
# ---------------------------------------------------------------------------

_REPORT = """# Commercialization Assessment: Solid Electrolyte

## Executive Summary

Conductivity reached 25 mS/cm [A1], a 3x gain over prior work [A2].

## 1. Technology Overview

- Ionic conductivity: 25 mS/cm
- Stable to 5 V

| Dimension | Score |
|---|---|
| TRL | 6 |
| MRL | 4 |

## References

- [A1] Kim et al. https://doi.org/10.1234/test
"""


class GeneratePdfTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_creates_pdf_file(self):
        path = _generate_pdf(_REPORT, self.run_dir)
        self.assertIsNotNone(path)
        self.assertTrue(path.exists())

    def test_named_commercialization_report_pdf(self):
        path = _generate_pdf(_REPORT, self.run_dir)
        self.assertEqual(path.name, "commercialization_report.pdf")

    def test_output_is_a_real_pdf(self):
        path = _generate_pdf(_REPORT, self.run_dir)
        self.assertEqual(path.read_bytes()[:5], b"%PDF-")

    def test_empty_report_still_produces_a_pdf(self):
        path = _generate_pdf("", self.run_dir)
        self.assertIsNotNone(path)
        self.assertGreater(path.stat().st_size, 0)

    def test_returns_none_when_build_fails(self):
        """A PDF failure must not propagate — the report itself is already saved."""
        with patch("ui.pdf_export.markdown_to_story", side_effect=RuntimeError("boom")):
            self.assertIsNone(_generate_pdf(_REPORT, self.run_dir))

    def test_returns_none_for_unwritable_directory(self):
        missing = self.run_dir / "does" / "not" / "exist"
        self.assertIsNone(_generate_pdf(_REPORT, missing))

    def test_cjk_pdf_is_substantially_larger_than_latin(self):
        """Size is the observable proof that a CJK face was embedded.

        This is the regression guard for the blank-box bug: a PDF that merely
        references a font is small, and its CJK glyphs render as empty squares
        outside Acrobat. An embedded face costs tens of kilobytes.
        """
        cjk_report = _REPORT.replace("Solid Electrolyte", "固态电解质") + "\n\n中文正文内容测试。\n"
        en_dir = self.run_dir / "en"
        zh_dir = self.run_dir / "zh"
        en_dir.mkdir()
        zh_dir.mkdir()

        en_pdf = _generate_pdf(_REPORT, en_dir, "English")
        zh_pdf = _generate_pdf(cjk_report, zh_dir, "Simplified Chinese")
        self.assertIsNotNone(en_pdf)
        self.assertIsNotNone(zh_pdf)
        self.assertGreater(zh_pdf.stat().st_size, en_pdf.stat().st_size * 3)

    def test_all_cjk_languages_produce_output(self):
        for lang in _CID_FONT_MAP:
            with self.subTest(language=lang):
                d = self.run_dir / lang.replace(" ", "_")
                d.mkdir()
                path = _generate_pdf(f"# 报告\n\n{lang} test 内容\n", d, lang)
                self.assertIsNotNone(path)
                self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
