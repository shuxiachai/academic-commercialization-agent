"""The per-run daily-charge marker: what it says, and what damage must not say.

api/runs.py writes `.daily_charge` at launch and rewrites it when a never-launched
run is refunded; get_state reads it back for the result page's quota line. The
reader has five answers, and the two that mean "nothing reliable is recorded"
must never collapse into "not charged", which would tell a code holder a run
was free when nothing says so.
"""

from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from api import runs


class DailyChargeMarkerTests(unittest.TestCase):

    def setUp(self):
        self.run_dir = Path(tempfile.mkdtemp())

    def _write(self, text: str) -> None:
        (self.run_dir / runs._CHARGE_FILE).write_text(text, encoding="utf-8")

    def test_each_written_state_reads_back(self):
        runs._write_daily_charge(self.run_dir, date(2026, 10, 25))
        self.assertEqual(runs._read_daily_charge(self.run_dir), "charged")
        runs._write_daily_charge(self.run_dir, date(2026, 10, 25), refunded=True)
        self.assertEqual(runs._read_daily_charge(self.run_dir), "refunded")
        runs._write_daily_charge(self.run_dir, None)
        self.assertEqual(runs._read_daily_charge(self.run_dir), "not_charged")

    def test_an_absent_marker_is_not_recorded(self):
        self.assertEqual(runs._read_daily_charge(self.run_dir), "not_recorded")

    def test_damage_is_unreadable_never_not_charged(self):
        for text in ("", "null", "[]", "{}", '{"charged": "yes", "refunded": false}',
                     '{"charged": true}', '{"charged": 1, "refunded": false}',
                     '\ufeff{"charged": true, "refunded": false}'):
            with self.subTest(text=text):
                self._write(text)
                self.assertEqual(runs._read_daily_charge(self.run_dir), "unreadable")

    def test_a_directory_in_the_markers_place_is_unreadable(self):
        (self.run_dir / runs._CHARGE_FILE).mkdir()
        self.assertEqual(runs._read_daily_charge(self.run_dir), "unreadable")

    def test_a_refund_flag_on_an_uncharged_run_is_still_not_charged(self):
        self._write('{"charged": false, "refunded": true}')
        self.assertEqual(runs._read_daily_charge(self.run_dir), "not_charged")

    def test_unknown_extra_keys_are_tolerated(self):
        self._write('{"charged": true, "refunded": false, "schema_version": 99, "extra": 1}')
        self.assertEqual(runs._read_daily_charge(self.run_dir), "charged")


if __name__ == "__main__":
    unittest.main()
