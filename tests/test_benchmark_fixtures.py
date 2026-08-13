"""Tests for frozen benchmark evidence.

A fixture is the input every number in a benchmark summary is attributed to,
so the assertions that matter are not "does it save and load". They are the
three ways a fixture could quietly stop meaning what it claims:

  * a result measured over frozen evidence presented as a result about the
    whole system, when it only measures the reasoning half
  * a missing fixture falling back to live retrieval, producing exactly that
    confusion one run at a time
  * a fixture edited or truncated after the fact, so the recorded provenance
    describes a file that no longer exists
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import TestCase, mock

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

import benchmark_fixtures  # noqa: E402


def _collection_json(collected_at: str | None = None, academic: int = 2) -> str:
    """A minimal SourceCollection dump. Only the fields the manifest reads."""
    return json.dumps({
        "topic": "test topic",
        "collected_at": collected_at or datetime.now(UTC).isoformat(),
        "academic_sources": [{"id": f"A{i}"} for i in range(academic)],
        "patent_sources": [{"id": "P1"}],
        "market_sources": [],
    }, indent=2)


class _TempFixtureRoot:
    """Redirect the fixture directory so tests never touch the real one."""

    def __init__(self, tmp: Path):
        self._patches = [
            mock.patch.object(benchmark_fixtures, "FIXTURE_ROOT", tmp),
            mock.patch.object(benchmark_fixtures, "MANIFEST_PATH", tmp / "manifest.json"),
        ]

    def __enter__(self):
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *exc):
        for p in self._patches:
            p.stop()


class FreezeAndLoadTests(TestCase):

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_frozen_bytes_are_preserved_exactly(self):
        """Re-serialising would produce a file that differs from what the run
        actually used — even a key reordering makes the fixture stop being a
        record of that run."""
        raw = _collection_json()
        with _TempFixtureRoot(self.root):
            benchmark_fixtures.freeze("01", "slug", "topic", raw)
            stored = benchmark_fixtures.fixture_path("01", "slug").read_text(encoding="utf-8")
        self.assertEqual(stored, raw)

    def test_manifest_records_counts_and_provenance(self):
        with _TempFixtureRoot(self.root):
            entry = benchmark_fixtures.freeze("01", "slug", "topic", _collection_json(academic=5))
        self.assertEqual(entry["counts"]["academic"], 5)
        self.assertEqual(entry["topic"], "topic")
        self.assertTrue(entry["sha256_16"])

    def test_missing_fixture_returns_none_rather_than_raising(self):
        """The caller distinguishes absent from corrupt, and only the second
        is an error — absent just means it was never captured."""
        with _TempFixtureRoot(self.root):
            self.assertIsNone(benchmark_fixtures.load("99", "nope"))

    def test_edited_fixture_is_refused(self):
        """The one input a benchmark must never silently accept: every number
        downstream is attributed to this file."""
        with _TempFixtureRoot(self.root):
            benchmark_fixtures.freeze("01", "slug", "topic", _collection_json())
            path = benchmark_fixtures.fixture_path("01", "slug")
            path.write_text(_collection_json(academic=99), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                benchmark_fixtures.load("01", "slug")
        self.assertIn("manifest digest", str(ctx.exception))

    def test_truncated_fixture_is_refused(self):
        """A half-written file parses as invalid JSON on a good day and as a
        smaller valid collection on a bad one. The digest catches both."""
        with _TempFixtureRoot(self.root):
            raw = _collection_json()
            benchmark_fixtures.freeze("01", "slug", "topic", raw)
            path = benchmark_fixtures.fixture_path("01", "slug")
            path.write_text(raw[: len(raw) // 2], encoding="utf-8")
            with self.assertRaises(ValueError):
                benchmark_fixtures.load("01", "slug")

    def test_digest_ignores_line_endings(self):
        """Git checks the same fixture out as CRLF on Windows and LF on a
        Linux runner, so a byte-for-byte hash would call one of them tampered.

        This passes today for a reason that is not in _digest: Python's text
        mode folds the newlines before it is called. Pinning the property here
        means a later switch to read_bytes(), or an open(newline=""), fails
        this test instead of failing the integrity guard on everyone else's
        machine while still passing on the one that captured the fixture."""
        raw = _collection_json()
        self.assertEqual(
            benchmark_fixtures._digest(raw),
            benchmark_fixtures._digest(raw.replace("\n", "\r\n")),
        )
        # And the guard built on it does not fire on a CRLF checkout.
        with _TempFixtureRoot(self.root):
            benchmark_fixtures.freeze("01", "slug", "topic", raw)
            path = benchmark_fixtures.fixture_path("01", "slug")
            with path.open("w", encoding="utf-8", newline="") as fh:
                fh.write(raw.replace("\n", "\r\n"))
            recorded = benchmark_fixtures.load_manifest()["fixtures"]["01"]["sha256_16"]
            self.assertEqual(
                benchmark_fixtures._digest(path.read_text(encoding="utf-8")), recorded)

    def test_freeze_writes_lf_so_the_working_copy_matches_the_repo(self):
        """Keeps `git status` meaningful: a CRLF rewrite marks all ten
        fixtures modified, hiding the one that actually changed."""
        raw = _collection_json()
        with _TempFixtureRoot(self.root):
            benchmark_fixtures.freeze("01", "slug", "topic", raw)
            written = benchmark_fixtures.fixture_path("01", "slug").read_bytes()
        self.assertNotIn(b"\r\n", written)

    def test_refreezing_updates_the_digest(self):
        """Otherwise the guard above would reject every legitimate refresh."""
        with _TempFixtureRoot(self.root):
            benchmark_fixtures.freeze("01", "slug", "topic", _collection_json())
            benchmark_fixtures.freeze("01", "slug", "topic", _collection_json(academic=9))
            entry = benchmark_fixtures.load_manifest()["fixtures"]["01"]
            self.assertEqual(entry["counts"]["academic"], 9)
            path = benchmark_fixtures.fixture_path("01", "slug")
            self.assertEqual(
                benchmark_fixtures._digest(path.read_text(encoding="utf-8")),
                entry["sha256_16"],
            )


class AgeReportingTests(TestCase):
    """Age is taken from when the web was read, not from when the file was
    copied. Seeding a fixture from an old run would otherwise look brand new."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_age_follows_collected_at_not_the_write_time(self):
        old = (datetime.now(UTC) - timedelta(days=400)).isoformat()
        with _TempFixtureRoot(self.root):
            benchmark_fixtures.freeze("01", "slug", "topic", _collection_json(collected_at=old))
            age = benchmark_fixtures.age_days("01")
        self.assertGreater(age, 399, "age was measured from the copy, not the retrieval")

    def test_naive_timestamp_does_not_crash_the_age_calculation(self):
        """Older dumps were written without a timezone; a TypeError here would
        take down the whole harness at startup."""
        naive = datetime.now(UTC).replace(tzinfo=None).isoformat()
        with _TempFixtureRoot(self.root):
            benchmark_fixtures.freeze("01", "slug", "topic", _collection_json(collected_at=naive))
            self.assertLess(benchmark_fixtures.age_days("01"), 1)

    def test_stale_fixtures_are_called_out_in_the_listing(self):
        """A stale fixture produces a result that looks exactly like a fresh
        one, so the staleness has to be stated rather than merely stored."""
        old = (datetime.now(UTC)
               - timedelta(days=benchmark_fixtures.STALE_AFTER_DAYS + 10)).isoformat()
        with _TempFixtureRoot(self.root):
            benchmark_fixtures.freeze("01", "slug", "topic", _collection_json(collected_at=old))
            lines = benchmark_fixtures.describe()
        self.assertTrue(any("STALE" in line for line in lines), lines)

    def test_fresh_fixtures_are_not_called_stale(self):
        with _TempFixtureRoot(self.root):
            benchmark_fixtures.freeze("01", "slug", "topic", _collection_json())
            lines = benchmark_fixtures.describe()
        self.assertFalse(any("STALE" in line for line in lines), lines)

    def test_empty_fixture_dir_says_so_instead_of_returning_nothing(self):
        with _TempFixtureRoot(self.root):
            lines = benchmark_fixtures.describe()
        self.assertTrue(any("--freeze" in line for line in lines), lines)


class EvidenceModeTests(TestCase):
    """A run over frozen evidence and a run over live retrieval measure
    different things, so the harness must never blend them."""

    def setUp(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _write_meta(self, **fields):
        (self.dir / "meta.json").write_text(json.dumps({
            "status": "success", **fields
        }), encoding="utf-8")

    def test_live_run_is_not_reused_for_a_fixture_request(self):
        import benchmark

        self._write_meta(evidence_mode="live")
        self.assertFalse(benchmark._already_succeeded(self.dir, "fixture"))
        self.assertTrue(benchmark._already_succeeded(self.dir, "live"))

    def test_fixture_run_is_not_reused_for_a_live_request(self):
        import benchmark

        self._write_meta(evidence_mode="fixture")
        self.assertFalse(benchmark._already_succeeded(self.dir, "live"))
        self.assertTrue(benchmark._already_succeeded(self.dir, "fixture"))

    def test_runs_predating_the_field_count_as_live(self):
        """Which is what they were. Treating them as neither would silently
        re-run a completed baseline; as fixture would misattribute it."""
        import benchmark

        self._write_meta()
        self.assertTrue(benchmark._already_succeeded(self.dir, "live"))
        self.assertFalse(benchmark._already_succeeded(self.dir, "fixture"))

    def test_failed_run_is_never_reused_in_either_mode(self):
        import benchmark

        (self.dir / "meta.json").write_text(
            json.dumps({"status": "failed", "evidence_mode": "fixture"}), encoding="utf-8")
        self.assertFalse(benchmark._already_succeeded(self.dir, "fixture"))
        self.assertFalse(benchmark._already_succeeded(self.dir, "live"))


class ShippedFixtureTests(TestCase):
    """The fixtures actually committed to the repo, checked as data."""

    def test_every_shipped_fixture_matches_its_manifest_digest(self):
        manifest = benchmark_fixtures.load_manifest().get("fixtures", {})
        if not manifest:
            self.skipTest("no fixtures committed")
        for num, entry in manifest.items():
            with self.subTest(num=num):
                path = benchmark_fixtures.FIXTURE_ROOT / entry["file"]
                self.assertTrue(path.exists(), f"{entry['file']} is in the manifest but missing")
                self.assertEqual(
                    benchmark_fixtures._digest(path.read_text(encoding="utf-8")),
                    entry["sha256_16"],
                )

    def test_shipped_fixtures_cover_every_benchmark_topic(self):
        """A topic without a fixture makes --fixtures fail mid-batch rather
        than at startup, after the earlier topics have already been run."""
        import benchmark

        manifest = benchmark_fixtures.load_manifest().get("fixtures", {})
        if not manifest:
            self.skipTest("no fixtures committed")
        missing = [num for num, *_ in benchmark.TOPICS if num not in manifest]
        self.assertFalse(missing, f"topics without a fixture: {missing}")

    def test_shipped_fixtures_parse_as_source_collections(self):
        """They are replayed straight into the crew, so a schema drift here
        would surface as a crash in a paid run."""
        from academic_agent.source_pipeline import SourceCollection

        manifest = benchmark_fixtures.load_manifest().get("fixtures", {})
        if not manifest:
            self.skipTest("no fixtures committed")
        for num, entry in manifest.items():
            with self.subTest(num=num):
                path = benchmark_fixtures.FIXTURE_ROOT / entry["file"]
                collection = SourceCollection.model_validate_json(
                    path.read_text(encoding="utf-8"))
                # crew_inputs is what the agents actually receive; building it
                # is where a missing field would show up.
                self.assertIn("academic_sources_json", collection.crew_inputs())
