"""Tests for ui/html_scorecard.py and ui/html_sources.py rendering helpers."""

from __future__ import annotations

import json
import tempfile
from datetime import date
from pathlib import Path
from unittest import TestCase

from ui.html_scorecard import (
    _bar_row,
    _bullet_item,
    _kpi_tile,
    _metric_color,
    _radar_svg,
    _score_color,
    _source_id_chips,
)
from ui.html_sources import _date_is_before, _build_sources_index, _src_detail_panel_html
from ui.history import _history_empty, _cleanup_old_runs


# ---------------------------------------------------------------------------
# _score_color
# ---------------------------------------------------------------------------

class ScoreColorTests(TestCase):
    def test_excellent_threshold(self) -> None:
        color, label = _score_color(80)
        self.assertEqual(label, "EXCELLENT")
        self.assertEqual(color, "#16a34a")

    def test_good_threshold(self) -> None:
        _, label = _score_color(60)
        self.assertEqual(label, "GOOD")

    def test_moderate_threshold(self) -> None:
        _, label = _score_color(40)
        self.assertEqual(label, "MODERATE")

    def test_weak_threshold(self) -> None:
        _, label = _score_color(39)
        self.assertEqual(label, "WEAK")
        self.assertEqual(_score_color(39)[0], "#dc2626")

    def test_boundary_79_is_good_not_excellent(self) -> None:
        _, label = _score_color(79)
        self.assertEqual(label, "GOOD")

    def test_boundary_80_is_excellent(self) -> None:
        _, label = _score_color(80)
        self.assertEqual(label, "EXCELLENT")


# ---------------------------------------------------------------------------
# _metric_color
# ---------------------------------------------------------------------------

class MetricColorTests(TestCase):
    def test_green_at_75(self) -> None:
        self.assertEqual(_metric_color(75), "#16a34a")

    def test_blue_at_50(self) -> None:
        self.assertEqual(_metric_color(50), "#2563eb")

    def test_amber_at_30(self) -> None:
        self.assertEqual(_metric_color(30), "#d97706")

    def test_red_at_29(self) -> None:
        self.assertEqual(_metric_color(29), "#dc2626")

    def test_returns_string(self) -> None:
        for pct in (0, 25, 50, 75, 100):
            with self.subTest(pct=pct):
                self.assertIsInstance(_metric_color(pct), str)
                self.assertTrue(_metric_color(pct).startswith("#"))


# ---------------------------------------------------------------------------
# _source_id_chips
# ---------------------------------------------------------------------------

class SourceIdChipsTests(TestCase):
    def test_empty_list_returns_empty_string(self) -> None:
        self.assertEqual(_source_id_chips([]), "")

    def test_single_id_renders_chip(self) -> None:
        result = _source_id_chips(["A1"])
        self.assertIn("A1", result)

    def test_multiple_ids_all_present(self) -> None:
        result = _source_id_chips(["A1", "P2", "M3"])
        self.assertIn("A1", result)
        self.assertIn("P2", result)
        self.assertIn("M3", result)

    def test_output_is_valid_html_fragment(self) -> None:
        result = _source_id_chips(["A1"])
        self.assertIn("<", result)
        self.assertIn(">", result)


# ---------------------------------------------------------------------------
# _kpi_tile
# ---------------------------------------------------------------------------

class KpiTileTests(TestCase):
    def test_basic_render_contains_value(self) -> None:
        result = _kpi_tile("TRL", 7, 9, "Technology Readiness", 78)
        self.assertIn("7", result)
        self.assertIn("TRL", result)

    def test_with_source_ids_includes_chips(self) -> None:
        result = _kpi_tile("TRL", 7, 9, "Technology Readiness", 78, source_ids=["A1"])
        self.assertIn("A1", result)

    def test_without_source_ids_no_chip_div(self) -> None:
        result = _kpi_tile("MRL", 5, 10, "Market Readiness", 50, source_ids=None)
        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# _bar_row
# ---------------------------------------------------------------------------

class BarRowTests(TestCase):
    def test_contains_label_and_value(self) -> None:
        result = _bar_row("Patent Strength", 4, 5, 80)
        self.assertIn("Patent Strength", result)
        self.assertIn("4", result)

    def test_zero_value(self) -> None:
        result = _bar_row("Evidence", 0, 5, 0)
        self.assertIn("0", result)

    def test_max_value(self) -> None:
        result = _bar_row("TRL", 9, 9, 100)
        self.assertIn("9", result)


# ---------------------------------------------------------------------------
# _bullet_item
# ---------------------------------------------------------------------------

class BulletItemTests(TestCase):
    def test_contains_text_and_color(self) -> None:
        result = _bullet_item("Excellent market fit", "#16a34a")
        self.assertIn("Excellent market fit", result)
        self.assertIn("#16a34a", result)

    def test_html_escapes_special_chars(self) -> None:
        result = _bullet_item("<script>alert(1)</script>", "#dc2626")
        self.assertNotIn("<script>", result)


# ---------------------------------------------------------------------------
# _radar_svg
# ---------------------------------------------------------------------------

class RadarSvgTests(TestCase):
    def test_returns_svg_string(self) -> None:
        result = _radar_svg(7, 6, 4, 3, 4)
        self.assertIn("<svg", result)
        self.assertIn("</svg>", result)

    def test_accepts_zero_values(self) -> None:
        result = _radar_svg(0, 0, 0, 0, 0)
        self.assertIn("<svg", result)

    def test_custom_color_appears_in_output(self) -> None:
        result = _radar_svg(5, 5, 5, 5, 5, color="#ff0000")
        self.assertIn("#ff0000", result)


# ---------------------------------------------------------------------------
# _date_is_before
# ---------------------------------------------------------------------------

class DateIsBeforeTests(TestCase):
    def test_older_date_returns_true(self) -> None:
        self.assertTrue(_date_is_before("2020-01-01", date(2023, 1, 1)))

    def test_same_date_returns_false(self) -> None:
        self.assertFalse(_date_is_before("2023-01-01", date(2023, 1, 1)))

    def test_newer_date_returns_false(self) -> None:
        self.assertFalse(_date_is_before("2024-06-15", date(2023, 1, 1)))

    def test_invalid_string_returns_false(self) -> None:
        self.assertFalse(_date_is_before("not-a-date", date(2023, 1, 1)))

    def test_empty_string_returns_false(self) -> None:
        self.assertFalse(_date_is_before("", date(2023, 1, 1)))

    def test_none_returns_false(self) -> None:
        self.assertFalse(_date_is_before(None, date(2023, 1, 1)))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _build_sources_index
# ---------------------------------------------------------------------------

class BuildSourcesIndexTests(TestCase):
    def _make_run_dir(self, tmp: Path, sources: list[dict]) -> Path:
        run_dir = tmp / "run"
        run_dir.mkdir()
        (run_dir / "validated_sources.json").write_text(
            json.dumps({
                "academic_sources": sources,
                "patent_sources": [],
                "market_sources": [],
            }),
            encoding="utf-8",
        )
        return run_dir

    def test_indexes_sources_by_source_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(
                Path(tmp),
                [{"source_id": "A1", "title": "Paper One", "url": "https://doi.org/10.1/a1"}],
            )
            index = _build_sources_index(run_dir)
            self.assertIn("A1", index)
            self.assertEqual(index["A1"]["title"], "Paper One")

    def test_empty_sources_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(Path(tmp), [])
            self.assertEqual(_build_sources_index(run_dir), {})

    def test_missing_file_returns_empty_dict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_build_sources_index(Path(tmp)), {})


# ---------------------------------------------------------------------------
# _src_detail_panel_html
# ---------------------------------------------------------------------------

class SrcDetailPanelHtmlTests(TestCase):
    def test_empty_index_returns_empty_string(self) -> None:
        result = _src_detail_panel_html({})
        self.assertEqual(result, "")

    def test_sources_embedded_as_json(self) -> None:
        index = {"A1": {"title": "Test Paper", "url": "https://example.com"}}
        result = _src_detail_panel_html(index)
        self.assertIn("Test Paper", result)
        self.assertIn("_acadSrcData", result)


# ---------------------------------------------------------------------------
# _history_empty
# ---------------------------------------------------------------------------

class HistoryEmptyTests(TestCase):
    def test_contains_message(self) -> None:
        result = _history_empty("No runs found.")
        self.assertIn("No runs found.", result)

    def test_escapes_html(self) -> None:
        result = _history_empty("<b>danger</b>")
        self.assertNotIn("<b>", result)

    def test_returns_html_string(self) -> None:
        result = _history_empty("msg")
        self.assertIn("<p", result)


# ---------------------------------------------------------------------------
# _cleanup_old_runs
# ---------------------------------------------------------------------------

class CleanupOldRunsTests(TestCase):
    def _populate_output_dir(self, tmp: Path, count: int) -> list[Path]:
        out = tmp / "outputs"
        out.mkdir()
        dirs = []
        for i in range(count):
            d = out / f"202601{i:02d}T000000Z-run{i:02d}"
            d.mkdir()
            dirs.append(d)
        return dirs

    def test_no_output_dir_returns_message(self) -> None:
        from unittest.mock import patch
        from academic_agent.run_output import DEFAULT_OUTPUT_ROOT
        with patch("ui.history.DEFAULT_OUTPUT_ROOT", Path("/nonexistent/outputs")):
            result = _cleanup_old_runs(20)
        self.assertIn("No output directory", result)

    def test_nothing_to_clean_when_under_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dirs = self._populate_output_dir(Path(tmp), 3)
            from unittest.mock import patch
            with patch("ui.history.DEFAULT_OUTPUT_ROOT", Path(tmp) / "outputs"):
                result = _cleanup_old_runs(keep_n=5)
        self.assertIn("Nothing to clean", result)

    def test_deletes_oldest_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self._populate_output_dir(Path(tmp), 5)
            out = Path(tmp) / "outputs"
            from unittest.mock import patch
            with patch("ui.history.DEFAULT_OUTPUT_ROOT", out):
                result = _cleanup_old_runs(keep_n=3)
            remaining = [d for d in out.iterdir() if d.is_dir()]
            self.assertEqual(len(remaining), 3)
            self.assertIn("Deleted 2", result)

    def test_benchmark_dir_never_deleted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "outputs"
            out.mkdir()
            (out / "benchmark").mkdir()
            for i in range(5):
                (out / f"202601{i:02d}T000000Z-run{i:02d}").mkdir()
            from unittest.mock import patch
            with patch("ui.history.DEFAULT_OUTPUT_ROOT", out):
                _cleanup_old_runs(keep_n=2)
            self.assertTrue((out / "benchmark").exists())
