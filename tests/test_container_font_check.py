"""Tests for the build-time CJK font check.

The check exists because the failure it guards against is silent:
_resolve_font() degrades to a CID font and then to Helvetica, so an image built
without fonts-noto-cjk produces reports that look fine to the pipeline and
render as blank boxes for the reader.

A verifier that cannot fail is worth nothing, so the important test here is the
negative one.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import ui.pdf_export as pdf_export  # noqa: E402
from verify_container_fonts import main  # noqa: E402


class ContainerFontCheckTests(unittest.TestCase):

    def test_passes_when_an_embedded_font_resolves(self):
        with patch.object(pdf_export, "_resolve_font",
                          return_value=pdf_export._EMBEDDED_FONT_NAME):
            self.assertEqual(main(), 0)

    def test_fails_when_no_font_file_exists(self):
        """A slim image with no font package installed."""
        missing = {k: ["/nonexistent/none.ttc"] for k in pdf_export._CJK_TTF_CANDIDATES}
        with patch.dict(pdf_export._CJK_TTF_CANDIDATES, missing, clear=False):
            self.assertEqual(main(), 1)

    def test_cid_fallback_is_still_a_failure(self):
        """CID fonts need the typeface on the reader's machine.

        That assumption does not hold for a PDF generated in a container and
        downloaded by someone else, so resolving to one must not pass.
        """
        with patch.object(pdf_export, "_resolve_font", return_value="STSong-Light"):
            self.assertEqual(main(), 1)

    def test_helvetica_fallback_is_a_failure(self):
        with patch.object(pdf_export, "_resolve_font",
                          return_value=pdf_export._FALLBACK_FONT):
            self.assertEqual(main(), 1)

    def test_resolver_exception_does_not_escape(self):
        """A raising resolver must be reported, not crash the build opaquely."""
        with patch.object(pdf_export, "_resolve_font", side_effect=OSError("boom")):
            self.assertEqual(main(), 1)


if __name__ == "__main__":
    unittest.main()
