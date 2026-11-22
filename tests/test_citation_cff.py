from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class CitationMetadataTests(unittest.TestCase):
    def test_citation_file_describes_the_current_release(self) -> None:
        citation_path = ROOT / "CITATION.cff"
        self.assertTrue(citation_path.is_file(), "CITATION.cff must enable GitHub's citation UI")
        citation = citation_path.read_text(encoding="utf-8")
        self.assertIn('title: "Academic Commercialization Assessment Agent"', citation)
        self.assertIn('family-names: "Chai"', citation)
        self.assertIn('given-names: "Jason"', citation)
        self.assertIn('url: "https://github.com/shuxiachai/academic-commercialization-agent"', citation)
        self.assertIn("license: MIT", citation)
        self.assertRegex(citation, r"(?m)^version: [^\s]+$")
        self.assertRegex(citation, r"(?m)^date-released: \d{4}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()
