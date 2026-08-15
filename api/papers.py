"""Uploaded-paper handling for the HTTP API.

The Gradio path keeps an extracted paper in a `gr.State` for the length of a
session. An HTTP client has no equivalent, so an extraction is written to disk
under a generated id and referenced by that id when a run is started.

Extractions are disposable: they exist only between the upload and the run
that consumes them, and are pruned by age rather than tracked.
"""

from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

from academic_agent.run_output import DEFAULT_OUTPUT_ROOT

# Uploads and their extractions live outside the per-run directories: a paper
# may be uploaded and never run, and a run directory should describe a run.
PAPERS_ROOT = DEFAULT_OUTPUT_ROOT / "_papers"

# The Gradio path applies the same ceiling. Larger PDFs are almost always
# scanned images, which the text extractor cannot use anyway.
MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# An extraction is only useful until the run that consumes it starts. A day is
# generous for that and keeps a stale upload from lingering indefinitely.
_MAX_AGE_SECONDS = 24 * 60 * 60


class PaperNotFound(Exception):
    """Raised for an unknown or expired paper_id."""


class PaperTooLarge(Exception):
    """Raised when an upload exceeds MAX_UPLOAD_BYTES."""


class PaperNotAPdf(Exception):
    """Raised when an upload does not begin with the PDF signature."""


def _is_valid_paper_id(paper_id: str) -> bool:
    """Reject anything that could escape PAPERS_ROOT."""
    return (
        bool(paper_id)
        and "/" not in paper_id
        and "\\" not in paper_id
        and ".." not in paper_id
        and paper_id == Path(paper_id).name
    )


def paper_dir(paper_id: str) -> Path:
    return PAPERS_ROOT / paper_id


def create_paper_id() -> str:
    return f"paper-{uuid.uuid4().hex[:12]}"


#: Every PDF starts with this. Checked because the filename and the declared
#: content type both come from the client, and the file is handed to a native
#: parser afterwards — a renamed archive or image should be refused here
#: rather than by pypdfium2 several layers in.
_PDF_SIGNATURE = b"%PDF-"


def save_upload(filename: str, data: bytes) -> tuple[str, Path]:
    """Persist an uploaded PDF. Returns (paper_id, pdf_path)."""
    if not data.startswith(_PDF_SIGNATURE):
        raise PaperNotAPdf(
            "The uploaded file does not look like a PDF (missing %PDF- header)."
        )
    if len(data) > MAX_UPLOAD_BYTES:
        raise PaperTooLarge(
            f"{len(data) / 1024 / 1024:.1f} MB exceeds the "
            f"{MAX_UPLOAD_BYTES // 1024 // 1024} MB limit"
        )

    paper_id = create_paper_id()
    directory = paper_dir(paper_id)
    directory.mkdir(parents=True, exist_ok=True)

    # The client's filename is never used as a path component; only its
    # extension matters and even that is fixed.
    pdf_path = directory / "paper.pdf"
    pdf_path.write_bytes(data)
    (directory / "original_name.txt").write_text(filename or "", encoding="utf-8")
    return paper_id, pdf_path


def discard(paper_id: str) -> None:
    """Remove an upload and anything stored beside it. Never raises.

    For the extraction that failed: the PDF has already been written by then,
    and nothing downstream can ever use it — no paper_id was returned, so no
    run can reference it. Left in place it sat on the server for a full day
    waiting for the pruner, which is a day of holding someone's unpublished
    paper in exchange for an error message.

    Best-effort because the caller is already on an error path and is about to
    report a more useful failure than this one.
    """
    if not _is_valid_paper_id(paper_id):
        return
    shutil.rmtree(paper_dir(paper_id), ignore_errors=True)


def save_extraction(paper_id: str, extraction: dict) -> Path:
    """Store the structured extraction alongside its PDF."""
    directory = paper_dir(paper_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "extraction.json"
    path.write_text(json.dumps(extraction, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_extraction(paper_id: str) -> dict:
    """Read a stored extraction, raising PaperNotFound when absent."""
    if not _is_valid_paper_id(paper_id):
        raise PaperNotFound(f"Invalid paper id: {paper_id!r}")
    path = paper_dir(paper_id) / "extraction.json"
    if not path.exists():
        raise PaperNotFound(f"No extraction for paper id {paper_id}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaperNotFound(f"Extraction for {paper_id} is unreadable") from exc


def extraction_path_for_run(paper_id: str) -> Path:
    """Path passed to the worker as --paper-json.

    Validates first: this value reaches a subprocess argument, so an unchecked
    id would be a path traversal with an execution step attached.
    """
    if not _is_valid_paper_id(paper_id):
        raise PaperNotFound(f"Invalid paper id: {paper_id!r}")
    path = paper_dir(paper_id) / "extraction.json"
    if not path.exists():
        raise PaperNotFound(f"No extraction for paper id {paper_id}")
    return path


def prune_old(max_age_seconds: int = _MAX_AGE_SECONDS) -> int:
    """Delete upload directories older than max_age_seconds.

    Best-effort: a directory that cannot be removed (open handle on Windows,
    permissions) is skipped rather than raising, since pruning runs on a timer
    and must not take down the caller.
    """
    if not PAPERS_ROOT.is_dir():
        return 0

    cutoff = time.time() - max_age_seconds
    removed = 0
    for directory in PAPERS_ROOT.iterdir():
        if not directory.is_dir():
            continue
        try:
            if directory.stat().st_mtime >= cutoff:
                continue
            shutil.rmtree(directory)
            removed += 1
        except OSError:
            continue
    return removed
