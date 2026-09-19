"""Bounded saved-JSON projection, not retrieval, authentication or attestation."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat

from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource

MAX_SAVED_BYTES = 1024 * 1024
_RUN_ID = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{32}")


class SavedSourceMissing(Exception):
    """The direct saved registry does not exist; never include its path."""

    def __init__(self):
        super().__init__("Saved sources not found.")


class SavedSourceUnavailable(Exception):
    """Saved bytes cannot safely form a complete snapshot."""

    def __init__(self):
        super().__init__("Saved sources unavailable.")


def valid_run_id(value: object) -> bool:
    """Admit only bounded ASCII timestamp/hex names, never a path or alias."""
    return type(value) is str and _RUN_ID.fullmatch(value) is not None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise ValueError("invalid_constant")


def _unicode_scalars(value):
    # Escaped lone surrogates are accepted by json.loads but cannot be exact
    # UTF-8 text at the later HTTP/read boundary. Fail the whole registry now.
    if isinstance(value, str):
        value.encode("utf-8")
    elif isinstance(value, dict):
        for key, item in value.items():
            _unicode_scalars(key)
            _unicode_scalars(item)
    elif isinstance(value, list):
        for item in value:
            _unicode_scalars(item)


def snapshot_from_saved_bytes(raw: bytes, report_ref: str) -> ReportEvidenceSnapshot:
    """Preserve saved fields without today's EvidenceSource/date validators.

    All three group lists must be present, even when empty. Other historical
    collection/source metadata is not evidence in this projection. A bad row
    invalidates the registry; it is never silently skipped or repaired.
    """
    try:
        if type(raw) is not bytes or len(raw) > MAX_SAVED_BYTES:
            raise ValueError("invalid_saved_bytes")
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant)
        _unicode_scalars(value)
        if type(value) is not dict:
            raise ValueError("invalid_registry")
        sources = []
        for group in ("academic", "patent", "market"):
            rows = value[f"{group}_sources"]
            if type(rows) is not list:
                raise ValueError("invalid_group")
            for row in rows:
                if type(row) is not dict:
                    raise ValueError("invalid_source")
                source = {key: row[key] for key in (
                    "source_id", "title", "publisher", "source_type", "accessed_date")}
                source.update({key: row.get(key) for key in ("url", "doi", "published_date")})
                sources.append(SnapshotSource(
                    **source, group=group, summary=row.get("evidence_summary"),
                    origin="unknown" if row.get("summary_source") is None else row["summary_source"],
                ))
        return ReportEvidenceSnapshot(report_ref=report_ref, sources=tuple(sources))
    except (ValueError, TypeError, KeyError, RecursionError):
        raise SavedSourceUnavailable() from None


def _direct_stat(path: Path, *, directory: bool):
    info = path.lstat()
    if (stat.S_ISLNK(info.st_mode)
            or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT
            or (not stat.S_ISDIR(info.st_mode) if directory else not stat.S_ISREG(info.st_mode))
            or (not directory and info.st_nlink != 1)):
        raise SavedSourceUnavailable()
    return info


def _identity(info):
    return info.st_dev, info.st_ino


class SavedSourceLoader:
    """Read exactly one direct registry below a server-selected local root.

    Validate every ancestor without resolving away symlinks/junctions. Compare
    the opened descriptor to the pre-open regular file before reading; path
    replacement must not turn a successful check into a read of another file.
    This is not a transactional snapshot of a concurrently edited registry.
    """

    def __init__(self, root):
        self.root = Path(os.path.abspath(root))

    def __call__(self, run_id: str) -> ReportEvidenceSnapshot:
        if not valid_run_id(run_id):
            raise SavedSourceUnavailable()
        target = self.root / run_id / "validated_sources.json"
        parents = tuple(reversed(target.parents))
        observed = False
        try:
            before = tuple(_identity(_direct_stat(path, directory=True)) for path in parents)
            expected = _direct_stat(target, directory=False)
            observed = True
            # O_NONBLOCK prevents a replacement FIFO from hanging open on POSIX.
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            flags |= getattr(os, "O_NONBLOCK", 0)
            fd = os.open(target, flags)
            with os.fdopen(fd, "rb", buffering=0) as stream:
                opened = os.fstat(stream.fileno())
                if not stat.S_ISREG(opened.st_mode) or _identity(opened) != _identity(expected):
                    raise SavedSourceUnavailable()
                self._check_paths(parents, before, target, expected)
                # Stat size is advisory only: a growing file cannot bypass this
                # actual read cap. The extra byte distinguishes exact-limit EOF.
                raw = stream.read(MAX_SAVED_BYTES + 1)
                self._check_paths(parents, before, target, expected)
            return snapshot_from_saved_bytes(raw, run_id)
        except FileNotFoundError:
            if observed:
                raise SavedSourceUnavailable() from None
            raise SavedSourceMissing() from None
        except (OSError, ValueError):
            raise SavedSourceUnavailable() from None

    @staticmethod
    def _check_paths(parents, before, target, expected):
        after = tuple(_identity(_direct_stat(path, directory=True)) for path in parents)
        if after != before or _identity(_direct_stat(target, directory=False)) != _identity(expected):
            raise SavedSourceUnavailable()
