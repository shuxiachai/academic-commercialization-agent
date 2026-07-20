"""Tests for ui/run_reader.py — all pure or filesystem-only functions."""

from __future__ import annotations

import json
import os
import time
from datetime import timezone
from pathlib import Path
from unittest import TestCase
import tempfile

from ui.run_reader import (
    _extract_topic_from_report,
    _parse_run_timestamp,
    _read_output_language,
    _read_run_topic,
    _read_weight_profile,
    _run_duration,
)


class ParseRunTimestampTests(TestCase):
    def test_valid_utc_id(self) -> None:
        result = _parse_run_timestamp("20260119T143000Z-abc123")
        # Should return a formatted local time string, not the raw run_id
        self.assertRegex(result, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}")

    def test_invalid_id_returns_prefix(self) -> None:
        bad_id = "not-a-timestamp-abc"
        result = _parse_run_timestamp(bad_id)
        # Falls back to first 16 chars
        self.assertEqual(result, bad_id[:16])

    def test_empty_id_does_not_raise(self) -> None:
        result = _parse_run_timestamp("")
        self.assertIsInstance(result, str)


class RunDurationTests(TestCase):
    def _make_run_dir(self, tmp: Path, run_id: str, status_delay_secs: int = 5) -> Path:
        run_dir = tmp / run_id
        run_dir.mkdir()
        status_path = run_dir / "status.json"
        status_path.write_text("{}", encoding="utf-8")
        # Set mtime to run_id start time + delay so _run_duration sees the right duration
        from datetime import datetime, timezone as _tz
        ts_str = run_id.split("-")[0]
        start_ts = datetime.strptime(ts_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=_tz.utc).timestamp()
        mtime = start_ts + status_delay_secs
        os.utime(status_path, (mtime, mtime))
        return run_dir

    def test_returns_dash_for_missing_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "20260119T140000Z-abc"
            run_dir.mkdir()
            self.assertEqual(_run_duration(run_dir), "—")

    def test_seconds_format_for_short_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(Path(tmp), "20260119T140000Z-abc", status_delay_secs=30)
            result = _run_duration(run_dir)
            self.assertRegex(result, r"^\d+s$")

    def test_minutes_format_for_long_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = self._make_run_dir(Path(tmp), "20260119T140000Z-abc", status_delay_secs=130)
            result = _run_duration(run_dir)
            self.assertRegex(result, r"^\d+m \d{2}s$")

    def test_invalid_run_id_returns_dash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "not-a-valid-id"
            run_dir.mkdir()
            (run_dir / "status.json").write_text("{}", encoding="utf-8")
            self.assertEqual(_run_duration(run_dir), "—")


class ExtractTopicFromReportTests(TestCase):
    def _write_report(self, tmp: Path, content: str) -> Path:
        p = tmp / "report.md"
        p.write_text(content, encoding="utf-8")
        return p

    def test_strips_english_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_report(
                Path(tmp),
                "# Academic Commercialization Assessment: perovskite solar cells\n\nBody.",
            )
            self.assertEqual(_extract_topic_from_report(p), "perovskite solar cells")

    def test_strips_chinese_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_report(Path(tmp), "# 学术商业化评估：钙钛矿太阳能电池\n\nBody.")
            topic = _extract_topic_from_report(p)
            self.assertEqual(topic, "钙钛矿太阳能电池")

    def test_no_prefix_returns_full_heading(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_report(Path(tmp), "# Some Custom Title\n\nBody.")
            self.assertEqual(_extract_topic_from_report(p), "Some Custom Title")

    def test_missing_file_returns_dash(self) -> None:
        result = _extract_topic_from_report(Path("/nonexistent/path/report.md"))
        self.assertEqual(result, "—")

    def test_truncates_very_long_title(self) -> None:
        long_title = "A" * 200
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_report(Path(tmp), f"# {long_title}\n\nBody.")
            result = _extract_topic_from_report(p)
            self.assertLessEqual(len(result), 90)

    def test_empty_file_returns_dash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write_report(Path(tmp), "")
            self.assertEqual(_extract_topic_from_report(p), "—")


class ReadRunTopicTests(TestCase):
    def test_reads_topic_from_status_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "status.json").write_text(
                json.dumps({"topic": "solid-state batteries"}), encoding="utf-8"
            )
            self.assertEqual(_read_run_topic(run_dir), "solid-state batteries")

    def test_falls_back_to_report_when_no_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "commercialization_report.md").write_text(
                "# Academic Commercialization Assessment: CAR-T therapy\n\nBody.",
                encoding="utf-8",
            )
            self.assertEqual(_read_run_topic(run_dir), "CAR-T therapy")

    def test_returns_dash_when_nothing_available(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_read_run_topic(Path(tmp)), "—")

    def test_truncates_long_topic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "status.json").write_text(
                json.dumps({"topic": "X" * 200}), encoding="utf-8"
            )
            result = _read_run_topic(run_dir)
            self.assertLessEqual(len(result), 90)


class ReadOutputLanguageTests(TestCase):
    def test_reads_language_from_validated_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "validated_sources.json").write_text(
                json.dumps({"output_language": "Simplified Chinese"}), encoding="utf-8"
            )
            self.assertEqual(_read_output_language(run_dir), "Simplified Chinese")

    def test_defaults_to_english_when_file_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_read_output_language(Path(tmp)), "English")

    def test_defaults_to_english_when_key_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "validated_sources.json").write_text(
                json.dumps({}), encoding="utf-8"
            )
            self.assertEqual(_read_output_language(run_dir), "English")

    def test_defaults_to_english_on_corrupt_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "validated_sources.json").write_text("NOT JSON", encoding="utf-8")
            self.assertEqual(_read_output_language(run_dir), "English")


class ReadWeightProfileTests(TestCase):
    def test_reads_profile_from_validated_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "validated_sources.json").write_text(
                json.dumps({"weight_profile": "biomedical"}), encoding="utf-8"
            )
            self.assertEqual(_read_weight_profile(run_dir), "biomedical")

    def test_defaults_to_industrial_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(_read_weight_profile(Path(tmp)), "industrial")
