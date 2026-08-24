"""Tests for uploaded-paper handling.

This module accepts an arbitrary file from an HTTP client, writes it to disk,
and resolves an id supplied by that client into a path which is then passed to
a subprocess as --paper-json. A traversal here is not just a file read: it
selects what the worker executes against.

It was written with 30% coverage and no tests of its own, which is why these
concentrate on the id validation rather than the happy path.
"""

from __future__ import annotations

import time
import unittest
from datetime import datetime, timedelta, UTC
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from api import papers, runs


class _PapersTestBase(unittest.TestCase):

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "_papers"
        patcher = patch.object(papers, "PAPERS_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)


class PaperIdValidationTests(_PapersTestBase):
    """paper_id reaches a subprocess argument; it must never escape PAPERS_ROOT."""

    TRAVERSALS = [
        "../secrets",
        "..\\secrets",
        "../../etc/passwd",
        "a/b",
        "a\\b",
        "..",
        "",
        "./x",
        "paper-0123456789ab",
        "paper-not-a-capability",
    ]

    def test_load_extraction_rejects_traversal(self):
        for bad in self.TRAVERSALS:
            with self.subTest(paper_id=bad):
                with self.assertRaises(papers.PaperNotFound):
                    papers.load_extraction(bad)

    def test_extraction_path_rejects_traversal(self):
        """The path this returns becomes --paper-json for the worker."""
        for bad in self.TRAVERSALS:
            with self.subTest(paper_id=bad):
                with self.assertRaises(papers.PaperNotFound):
                    papers.extraction_path_for_run(bad)

    def test_traversal_is_rejected_even_when_the_target_exists(self):
        """Rejection must not depend on the file happening to be absent.

        A check that only fails because nothing is there would pass silently
        until someone put a file where it could be reached.
        """
        outside = Path(self._tmp.name) / "outside"
        outside.mkdir(parents=True, exist_ok=True)
        (outside / "extraction.json").write_text("{}", encoding="utf-8")

        with self.assertRaises(papers.PaperNotFound):
            papers.extraction_path_for_run("../outside")

    def test_generated_ids_are_accepted(self):
        paper_id = papers.create_paper_id()
        self.assertRegex(paper_id, r"^paper-[0-9a-f]{32}$")
        papers.save_extraction(paper_id, {"title": "t"})
        self.assertTrue(papers.extraction_path_for_run(paper_id).exists())


class UploadTests(_PapersTestBase):

    def test_upload_is_stored_under_a_generated_id(self):
        paper_id, pdf_path = papers.save_upload(b"%PDF-1.4 body")
        self.assertTrue(pdf_path.exists())
        self.assertEqual(pdf_path.read_bytes(), b"%PDF-1.4 body")
        self.assertEqual(pdf_path.parent.name, paper_id)

    def test_only_the_fixed_pdf_name_is_persisted(self):
        """Client filenames are not needed after multipart parsing."""
        _paper_id, pdf_path = papers.save_upload(b"%PDF-1.4")
        self.assertEqual(pdf_path.name, "paper.pdf")
        self.assertEqual(pdf_path.parent.parent, self.root)
        self.assertEqual(
            {path.name for path in pdf_path.parent.iterdir()},
            {"paper.pdf"},
        )

    def test_oversized_upload_rejected(self):
        oversized = b"%PDF-1.4" + b"x" * (papers.MAX_UPLOAD_BYTES + 1)
        with self.assertRaises(papers.PaperTooLarge):
            papers.save_upload(oversized)

    def test_upload_at_the_limit_is_accepted(self):
        """Exactly at the ceiling is allowed; the check is > not >=."""
        at_limit = b"%PDF-1.4" + b"x" * (papers.MAX_UPLOAD_BYTES - 8)
        paper_id, _ = papers.save_upload(at_limit)
        self.assertTrue(papers.paper_dir(paper_id).is_dir())

    def test_rejected_upload_leaves_nothing_behind(self):
        with self.assertRaises(papers.PaperTooLarge):
            papers.save_upload(b"%PDF-1.4" + b"x" * papers.MAX_UPLOAD_BYTES)
        self.assertFalse(self.root.exists() and any(self.root.iterdir()))

    def test_two_uploads_do_not_collide(self):
        a, _ = papers.save_upload(b"%PDF-1.4 a")
        b, _ = papers.save_upload(b"%PDF-1.4 b")
        self.assertNotEqual(a, b)


class DiscardTests(_PapersTestBase):
    """An upload whose extraction failed is unreachable and still on disk.

    save_upload writes the PDF before the extractor is called, so a PDF that
    cannot be parsed leaves a copy behind — and no paper_id ever reaches the
    client, so no run can name it and nothing will ever read it again. It sat
    there until the day-long pruner came round: a day of holding someone's
    unpublished paper in exchange for an error message.
    """

    def test_a_discarded_upload_is_gone(self):
        paper_id, pdf_path = papers.save_upload(b"%PDF-1.4 body")
        papers.discard(paper_id)
        self.assertFalse(pdf_path.exists())
        self.assertFalse(papers.paper_dir(paper_id).exists())

    def test_discarding_an_unknown_id_is_not_an_error(self):
        """It is called from an error path. Raising there would replace a
        useful 422 about the PDF with a confusing one about cleanup."""
        papers.discard("paper-does-not-exist")

    def test_discard_rejects_traversal(self):
        """The id reaching this comes from save_upload, not from a client —
        but the check costs nothing and this function deletes a tree."""
        outside = Path(self._tmp.name) / "keepme"
        outside.mkdir()
        papers.discard("../keepme")
        self.assertTrue(outside.exists())

    def test_a_failed_extraction_deletes_the_upload(self):
        """End to end through the endpoint, because that is where the two
        halves meet: papers.py writes the file and main.py decides its fate."""
        from fastapi.testclient import TestClient

        from api.main import app

        with patch("api.main.extract_paper_contribution",
                   side_effect=ValueError(r"not a paper C:\private\top-secret")):
            with TestClient(app) as client:
                response = client.post(
                    "/api/papers",
                    files={"file": ("p.pdf", b"%PDF-1.4 body", "application/pdf")},
                )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(
            response.json()["detail"],
            "The paper could not be converted into a structured contribution. Retry or use another PDF.",
        )
        self.assertNotIn("top-secret", response.text)
        remaining = list(self.root.iterdir()) if self.root.exists() else []
        self.assertEqual(remaining, [], "the upload outlived the request that made it")

    def test_ledger_failure_returns_safe_503_and_deletes_the_upload(self):
        """Accounting errors happen before provider work and are not bad PDFs."""
        from fastapi.testclient import TestClient

        from api.main import app

        private = runs.PaidLedgerUnavailable(
            r"corrupt C:\private\wallet.json token=top-secret"
        )
        with patch(
            "api.main._extract_paper_with_paid_reservation",
            side_effect=private,
        ):
            with TestClient(app) as client:
                response = client.post(
                    "/api/papers",
                    files={"file": ("p.pdf", b"%PDF-1.4 body", "application/pdf")},
                )

        self.assertEqual(response.status_code, 503)
        self.assertIn(
            "accounting is temporarily unavailable", response.json()["detail"]
        )
        self.assertNotIn("wallet.json", response.text)
        remaining = list(self.root.iterdir()) if self.root.exists() else []
        self.assertEqual(remaining, [])

    def test_a_successful_extraction_deletes_only_the_raw_upload(self):
        """Runs consume extraction.json, so retaining paper.pdf after this
        boundary has no runtime purpose and violates the privacy disclosure."""
        from fastapi.testclient import TestClient

        from academic_agent.pdf_extractor import PaperContribution
        from api.main import app

        contribution = PaperContribution(
            title="A paper", core_contribution="x" * 25, application_domain="evs",
            delta_from_prior="y" * 15, commercialization_topic="z" * 15,
            search_keywords=["a", "b", "c"],
        )
        with patch("api.main.extract_paper_contribution", return_value=contribution):
            with TestClient(app) as client:
                response = client.post(
                    "/api/papers",
                    files={"file": ("p.pdf", b"%PDF-1.4 body", "application/pdf")},
                )

        self.assertEqual(response.status_code, 200)
        paper_id = response.json()["paper_id"]
        self.assertFalse((papers.paper_dir(paper_id) / "paper.pdf").exists())
        self.assertFalse((papers.paper_dir(paper_id) / "original_name.txt").exists())
        self.assertTrue((papers.paper_dir(paper_id) / "extraction.json").exists())


class ExtractionRoundTripTests(_PapersTestBase):

    def test_saved_extraction_reads_back_intact(self):
        paper_id = papers.create_paper_id()
        payload = {
            "title": "基于异构图神经网络的抗体设计",
            "key_metrics": ["76% accuracy", "72 citations"],
            "commercialization_topic": "antibody design SaaS",
        }
        papers.save_extraction(paper_id, payload)
        self.assertEqual(papers.load_extraction(paper_id), payload)

    def test_unknown_id_raises_rather_than_returning_empty(self):
        with self.assertRaises(papers.PaperNotFound):
            papers.load_extraction(papers.create_paper_id())

    def test_corrupt_extraction_raises_paper_not_found(self):
        """Half-written JSON must not surface as a JSONDecodeError to the API."""
        paper_id = papers.create_paper_id()
        directory = papers.paper_dir(paper_id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "extraction.json").write_text('{"title": ', encoding="utf-8")

        with self.assertRaises(papers.PaperNotFound):
            papers.load_extraction(paper_id)


class PaperOwnershipTests(_PapersTestBase):
    """The capability crosses upload and run requests; ownership must too."""

    def _saved(self, owner: str | None) -> str:
        paper_id, _ = papers.save_upload(b"%PDF-1.4 body", owner=owner)
        papers.save_extraction(paper_id, {"title": "Bound paper"})
        return paper_id

    def test_matching_owner_can_consume_the_extraction(self):
        paper_id = self._saved("alice-hash")
        self.assertTrue(
            papers.extraction_path_for_run(paper_id, owner="alice-hash").is_file()
        )

    def test_a_different_owner_and_no_owner_are_both_denied(self):
        paper_id = self._saved("alice-hash")
        for owner in ("bob-hash", None):
            with self.subTest(owner=owner), self.assertRaises(papers.PaperNotFound):
                papers.extraction_path_for_run(paper_id, owner=owner)

    def test_an_ownerless_capability_is_not_available_to_a_code(self):
        paper_id = self._saved(None)
        self.assertTrue(papers.extraction_path_for_run(paper_id).is_file())
        with self.assertRaises(papers.PaperNotFound):
            papers.extraction_path_for_run(paper_id, owner="alice-hash")

    def test_http_submission_carries_the_code_owner_across_the_seam(self):
        """A unit test on extraction_path_for_run would miss main.py passing
        owner=None, the same computed-but-never-delivered failure seen before."""
        from fastapi.testclient import TestClient

        from api import access
        from api.main import app

        paper_id = self._saved(access.owner_id("alice-code"))
        fake_run_id = "20260824T000000Z-0123456789"
        with patch.object(access, "ACCESS_CODE", None), \
             patch.object(access, "ACCESS_CODES", "alice-code,bob-code"), \
             patch.object(access, "ADMIN_CODE", None), \
             patch.object(runs, "start_run", return_value=(fake_run_id, self.root)) as start:
            with TestClient(app) as client:
                denied = client.post(
                    "/api/runs",
                    headers={"X-Access-Code": "bob-code"},
                    json={"topic": "a valid research topic", "paper_id": paper_id},
                )
                accepted = client.post(
                    "/api/runs",
                    headers={"X-Access-Code": "alice-code"},
                    json={"topic": "a valid research topic", "paper_id": paper_id},
                )

        self.assertEqual(denied.status_code, 404)
        self.assertEqual(accepted.status_code, 202)
        self.assertEqual(start.call_count, 1)
        self.assertEqual(start.call_args.kwargs["owner"], access.owner_id("alice-code"))
        self.assertEqual(
            Path(start.call_args.kwargs["paper_json_path"]),
            papers.paper_dir(paper_id) / "extraction.json",
        )


class PruneTests(_PapersTestBase):

    def _aged(self, paper_id: str, age_seconds: float) -> Path:
        directory = papers.paper_dir(paper_id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "extraction.json").write_text("{}", encoding="utf-8")
        old = time.time() - age_seconds
        import os
        os.utime(directory, (old, old))
        return directory

    def test_expired_uploads_are_removed(self):
        stale = self._aged("paper-stale", 48 * 3600)
        fresh = self._aged("paper-fresh", 60)

        removed = papers.prune_old()

        self.assertEqual(removed, 1)
        self.assertFalse(stale.exists())
        self.assertTrue(fresh.exists())

    def test_prune_on_a_missing_root_is_not_an_error(self):
        """The reaper runs on a timer from application start."""
        self.assertEqual(papers.prune_old(), 0)

    def test_prune_survives_an_undeletable_directory(self):
        """Windows refuses to remove a directory with an open handle.

        Pruning runs on a timer and must not take the reaper down with it.
        """
        self._aged("paper-locked", 48 * 3600)
        with patch("api.papers.shutil.rmtree", side_effect=OSError("in use")):
            self.assertEqual(papers.prune_old(), 0)   # skipped, not raised


if __name__ == "__main__":
    unittest.main()


class RunRetentionTests(unittest.TestCase):
    """Runs are deleted after RUN_RETENTION_DAYS.

    Pending paper records already expire after a day; runs did not, and a run
    retains the contribution extracted from a paper plus the assessment
    written about it. Reading a run needs only its id, so a shared link stays
    live for as long as the run does; retention is what bounds that.
    """

    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        patcher = patch.object(runs, "DEFAULT_OUTPUT_ROOT", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        runs._registry.clear()
        self.addCleanup(runs._registry.clear)

    def _run_dir(self, days_old: float) -> str:
        stamp = datetime.now(UTC) - timedelta(days=days_old)
        run_id = f"{stamp.strftime('%Y%m%dT%H%M%SZ')}-{'a' * 10}"
        d = self.root / run_id
        d.mkdir(parents=True)
        (d / "commercialization_report.md").write_text("# R", encoding="utf-8")
        return run_id

    def test_disabled_by_default_keeps_everything(self):
        """Local development's outputs directory is the developer's own."""
        old = self._run_dir(days_old=400)
        self.assertEqual(runs.prune_expired_runs(0), [])
        self.assertTrue((self.root / old).exists())

    def test_runs_past_the_window_are_deleted(self):
        old = self._run_dir(days_old=31)
        self.assertEqual(runs.prune_expired_runs(30), [old])
        self.assertFalse((self.root / old).exists())

    def test_runs_inside_the_window_are_kept(self):
        recent = self._run_dir(days_old=3)
        self.assertEqual(runs.prune_expired_runs(30), [])
        self.assertTrue((self.root / recent).exists())

    def test_a_live_run_is_never_deleted(self):
        """A worker is still writing there, and a long run can outlive the
        window while executing."""
        old = self._run_dir(days_old=99)
        proc = MagicMock()
        proc.poll.return_value = None                 # still running
        runs._registry[old] = runs._Handle(run_id=old, topic="t", proc=proc)

        self.assertEqual(runs.prune_expired_runs(30), [])
        self.assertTrue((self.root / old).exists())

    def test_age_comes_from_the_run_id_not_the_mtime(self):
        """Rendering a PDF on first download rewrites the directory, which
        would otherwise extend the life of exactly the runs being opened."""
        old = self._run_dir(days_old=90)
        (self.root / old / "commercialization_report.pdf").write_bytes(b"%PDF-1.4")
        self.assertEqual(runs.prune_expired_runs(30), [old])

    def test_unrelated_directories_are_left_alone(self):
        """_papers and benchmark live under outputs too."""
        (self.root / "_papers").mkdir()
        (self.root / "benchmark").mkdir()
        runs.prune_expired_runs(1)
        self.assertTrue((self.root / "_papers").exists())
        self.assertTrue((self.root / "benchmark").exists())


class UploadShapeTests(unittest.TestCase):
    """The upload is the one place a stranger hands this system a file, and it
    goes on to a native PDF parser. Both checks here run before that."""

    def test_a_non_pdf_is_refused_before_it_is_stored(self):
        """Filename and content type both come from the client. A renamed
        archive should be refused here rather than several layers in, by
        pypdfium2, on a path with no HTTP status to return."""
        with self.assertRaises(papers.PaperNotAPdf):
            papers.save_upload(b"PK this is a zip")

    def test_an_empty_body_is_refused(self):
        with self.assertRaises(papers.PaperNotAPdf):
            papers.save_upload(b"")

    def test_a_real_pdf_header_passes(self):
        paper_id, path = papers.save_upload(b"%PDF-1.7 content")
        self.assertTrue(path.exists())
        self.assertTrue(paper_id)


class CappedReadTests(unittest.IsolatedAsyncioTestCase):
    """The size limit used to run after `await file.read()`, so a 2 GB body was
    allocated in full and only then rejected. The check ran; it just ran after
    the damage it existed to prevent."""

    class _Body:
        """An upload that would be enormous if fully read."""

        def __init__(self, total: int, chunk: int = 1024 * 1024):
            self.remaining = total
            self.chunk = chunk
            self.delivered = 0

        async def read(self, size: int = -1) -> bytes:
            if self.remaining <= 0:
                return b""
            n = min(size if size > 0 else self.chunk, self.remaining, self.chunk)
            self.remaining -= n
            self.delivered += n
            return b"x" * n

    async def test_it_stops_reading_once_the_cap_is_passed(self):
        from api.main import _read_capped

        body = self._Body(papers.MAX_UPLOAD_BYTES * 20)
        with self.assertRaises(papers.PaperTooLarge):
            await _read_capped(body, papers.MAX_UPLOAD_BYTES)
        # The point: it gave up near the limit instead of consuming the lot.
        self.assertLess(body.delivered, papers.MAX_UPLOAD_BYTES * 2)

    async def test_a_body_within_the_cap_is_returned_whole(self):
        from api.main import _read_capped

        body = self._Body(3 * 1024 * 1024)
        data = await _read_capped(body, papers.MAX_UPLOAD_BYTES)
        self.assertEqual(len(data), 3 * 1024 * 1024)


class PaperOwnerCorruptionTests(_PapersTestBase):
    """A damaged owner marker must never become an ownerless capability."""

    def test_blank_existing_owner_marker_fails_closed(self):
        paper_id, _ = papers.save_upload(b"%PDF-1.4 body", owner="alice-hash")
        papers.save_extraction(paper_id, {"title": "Bound paper"})
        marker = papers.paper_dir(paper_id) / papers._OWNER_FILE
        marker.write_text("", encoding="utf-8")

        for owner in (None, "alice-hash"):
            with self.subTest(owner=owner), self.assertRaises(papers.PaperNotFound):
                papers.extraction_path_for_run(paper_id, owner=owner)
