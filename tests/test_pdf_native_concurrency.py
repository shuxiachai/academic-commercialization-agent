"""Exercise real paid admission with instrumented native handles, not unsafe PDFium races."""

import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event, Lock, get_ident
from types import SimpleNamespace

import pytest

from academic_agent import pdf_extractor as extractor
from api import main, runs


class ObservedLock:
    """Signal competing lock entry before acquiring, avoiding timing-based tests."""

    def __init__(self):
        self.lock = Lock()
        self.counter_lock = Lock()
        self.attempts = 0
        self.competing = Event()
        self.owner = None

    def __enter__(self):
        with self.counter_lock:
            self.attempts += 1
            if self.attempts >= 2:
                self.competing.set()
        self.lock.acquire()
        self.owner = get_ident()

    def __exit__(self, *_):
        self.owner = None
        self.lock.release()

    def assert_owned(self):
        assert self.owner == get_ident(), "Native PDFium call escaped the process-wide lock"


def install_native_probe(monkeypatch, lock, *, concurrent=False, fail=False):
    closed = []

    class Text:
        def get_text_range(self):
            lock.assert_owned()
            if fail:
                raise ValueError("malformed native page")
            return "Public fixture abstract"

        def close(self):
            lock.assert_owned()
            closed.append("text")

    class Page:
        def get_textpage(self):
            lock.assert_owned()
            return Text()

        def close(self):
            lock.assert_owned()
            closed.append("page")

    class Document:
        def __init__(self, _):
            lock.assert_owned()
            if concurrent:
                assert lock.competing.wait(3), "Second admitted extraction never attempted parsing"

        def __enter__(self):
            return self

        def __exit__(self, *_):
            lock.assert_owned()
            closed.append("document")

        def __len__(self):
            return 1

        def __getitem__(self, _):
            lock.assert_owned()
            return Page()

    monkeypatch.setattr(extractor, "_PDFIUM_LOCK", lock)
    monkeypatch.setitem(sys.modules, "pypdfium2", SimpleNamespace(PdfDocument=Document))
    return closed


def test_two_admitted_uploads_serialize_native_handles_not_model_work(monkeypatch):
    """Two legitimate API slots previously entered PDFium together and could crash the process."""
    lock = ObservedLock()
    closed = install_native_probe(monkeypatch, lock, concurrent=True)
    model_boundary = Barrier(2)
    monkeypatch.setattr(runs, "_registry", {})
    monkeypatch.setattr(runs, "_inline_paid_operations", {})
    monkeypatch.setattr(runs, "MAX_CONCURRENT", 5)
    monkeypatch.setattr(runs, "BYOK_MAX_CONCURRENT", 2)

    def contribution(path, **_):
        text = extractor.extract_pdf_text(path)
        # No actual LLM is called. Both threads must reach this seam together;
        # serializing the whole extraction would hold the first here forever.
        model_boundary.wait(timeout=3)
        return text

    monkeypatch.setattr(main, "extract_paper_contribution", contribution)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(main._extract_paper_with_paid_reservation, "fixture.pdf",
                               owner=None, byok=True, llm_provider="qwen", llm_api_key="fixture")
                   for _ in range(2)]
        assert all("Public fixture" in f.result(timeout=5) for f in futures)
    assert closed == ["text", "page", "document"] * 2
    assert runs.capacity_counts() == (0, 0)


def test_native_failure_closes_children_and_unlocks_next_upload(monkeypatch):
    lock = ObservedLock()
    closed = install_native_probe(monkeypatch, lock, fail=True)
    with pytest.raises(ValueError, match="malformed native"):
        extractor.extract_pdf_text("bad.pdf")
    assert closed == ["text", "page", "document"]
    assert not lock.lock.locked()
    install_native_probe(monkeypatch, lock)
    assert "Public fixture" in extractor.extract_pdf_text("good.pdf")
