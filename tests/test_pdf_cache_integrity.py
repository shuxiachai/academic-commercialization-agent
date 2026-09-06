"""Failed/competing downloads must never publish partial PDF cache bytes."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from reportlab.platypus import SimpleDocTemplate

from api import main
from ui import pdf_export


@pytest.fixture
def report(monkeypatch, tmp_path):
    path = tmp_path / "commercialization_report.md"
    path.write_text("# Preserved report\n\nPublic fixture text.", encoding="utf-8")
    monkeypatch.setattr(main.runs, "get_state", lambda _: {"state": "completed"})
    monkeypatch.setattr(main.runs, "artifact_path", lambda *_: path)
    return path


def test_partial_render_is_not_published_or_served_on_retry(report):
    """The first request formerly failed, then the second returned its partial bytes as 200."""
    client = TestClient(main.app)
    cache = report.with_suffix(".pdf")
    original = report.read_bytes()

    def torn_build(doc, *_):
        Path(doc.filename).write_bytes(b"%PDF-1.4 torn-render")
        raise OSError("fixture disk full")

    with patch.object(SimpleDocTemplate, "build", torn_build):
        assert client.get("/api/runs/fixture/report.pdf").status_code == 500
    assert not cache.exists(), "Failed build must not publish the final cache path"
    assert not list(report.parent.glob(".report-*.pdf.tmp"))
    response = client.get("/api/runs/fixture/report.pdf")
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")
    assert response.content.rstrip().endswith(b"%%EOF")
    assert b"torn-render" not in response.content
    assert report.read_bytes() == original


def test_failed_replacement_preserves_previous_complete_pdf(report):
    """Atomic build also protects callers regenerating an existing valid export."""
    previous = pdf_export._generate_pdf(report.read_text(), report.parent).read_bytes()

    def broken(doc, *_):
        Path(doc.filename).write_bytes(b"partial replacement")
        raise ValueError("bad flowable")

    with patch.object(SimpleDocTemplate, "build", broken), pytest.raises(ValueError):
        pdf_export._generate_pdf("replacement", report.parent)
    assert report.with_suffix(".pdf").read_bytes() == previous


def test_simultaneous_first_downloads_share_one_completed_build(report):
    """Both threads reach cache locking together; one build reaches both HTTP clients."""
    gate = Barrier(2)
    real_lock = pdf_export.pdf_cache_lock

    def simultaneous_lock(directory):
        gate.wait(timeout=5)
        return real_lock(directory)

    def download():
        return TestClient(main.app).get("/api/runs/fixture/report.pdf")

    with (
        patch.object(pdf_export, "pdf_cache_lock", simultaneous_lock),
        patch.object(pdf_export, "_generate_pdf", wraps=pdf_export._generate_pdf) as render,
        ThreadPoolExecutor(max_workers=2) as pool,
    ):
        first, second = [f.result(timeout=10) for f in [pool.submit(download), pool.submit(download)]]
    assert render.call_count == 1, "Concurrent first downloads must share one build"
    assert first.status_code == second.status_code == 200
    assert first.content == second.content == report.with_suffix(".pdf").read_bytes()


def test_legacy_torn_cache_is_regenerated(report):
    report.with_suffix(".pdf").write_bytes(b"%PDF-1.4 legacy partial")
    with patch.object(pdf_export, "_generate_pdf", wraps=pdf_export._generate_pdf) as render:
        response = TestClient(main.app).get("/api/runs/fixture/report.pdf")
    assert response.status_code == 200
    assert response.content.rstrip().endswith(b"%%EOF")
    render.assert_called_once()
