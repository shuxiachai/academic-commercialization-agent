"""The real thread owns publication/privacy cleanup when its waiter disappears."""

import asyncio
import threading
from unittest.mock import MagicMock

import pytest

from api import papers, runs
from api import main


@pytest.mark.parametrize("outcome", ["success", "provider_error", "storage_error"])
@pytest.mark.parametrize("cancel_queued", [False, True])
def test_abandoned_thread_finalizes_storage(monkeypatch, tmp_path, outcome, cancel_queued):
    """Cancelling before start or during extraction previously orphaned raw PDFs."""
    monkeypatch.setattr(papers, "PAPERS_ROOT", tmp_path / "papers")
    paper_id, pdf_path = papers.save_upload(b"%PDF-offline")
    started, release = threading.Event(), threading.Event()
    contribution = main.PaperContribution(
        title="Offline paper", core_contribution="x" * 25,
        application_domain="energy storage", delta_from_prior="y" * 15,
        commercialization_topic="z" * 15, search_keywords=["a", "b", "c"],
    )

    def extractor(*_args, **_kwargs):
        started.set()
        assert release.wait(3), "Test must release the fake provider"
        if outcome == "provider_error":
            raise ValueError("offline provider error")
        return contribution

    monkeypatch.setattr(main, "_extract_paper_with_paid_reservation", extractor)
    if outcome == "storage_error":
        monkeypatch.setattr(papers, "save_extraction", MagicMock(side_effect=OSError("offline disk failure")))

    async def exercise():
        queued = asyncio.Event()
        original = asyncio.to_thread

        async def gated_thread(fn, *args, **kwargs):
            if cancel_queued:
                await queued.wait()
            return await original(fn, *args, **kwargs)

        monkeypatch.setattr(main.asyncio, "to_thread", gated_thread)
        request = asyncio.create_task(main._process_uploaded_paper(paper_id, str(pdf_path)))
        try:
            if cancel_queued:
                while not main._paper_jobs:
                    await asyncio.sleep(0)
            else:
                assert await original(started.wait, 2)
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
        finally:
            release.set()
            queued.set()
        # Shielded work must actually finish, not merely report a free slot or
        # leave an unobserved exception after the test's event loop closes.
        for _ in range(200):
            if not main._paper_jobs:
                break
            await asyncio.sleep(0.01)
        assert not main._paper_jobs
        assert runs.active_paid_operation_count() == 0
        assert started.is_set() is not cancel_queued, "Queued cancellation must clean up without provider work"
        assert not papers.paper_dir(paper_id).exists()

    asyncio.run(exercise())


def test_cleanup_failure_is_observable(monkeypatch, tmp_path, caplog):
    """Best effort must not silently represent failed privacy cleanup as done."""
    monkeypatch.setattr(papers, "PAPERS_ROOT", tmp_path)
    paper_id, _ = papers.save_upload(b"%PDF-offline")
    with monkeypatch.context() as faults:
        faults.setattr(papers.shutil, "rmtree", MagicMock(side_effect=PermissionError("private path")))
        papers.discard(paper_id)
    assert "Paper cleanup incomplete: PermissionError" in caplog.text
    assert "private path" not in caplog.text
    assert paper_id not in caplog.text
