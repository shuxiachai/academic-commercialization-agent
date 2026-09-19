"""Direct saved bytes and filesystem boundaries; synthetic data only."""

from copy import deepcopy
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import pytest

from academic_agent import saved_source_loader as loader
from academic_agent.report_evidence_snapshot import SnapshotSource

RUN_ID = "20260919T123456Z-0123456789abcdef0123456789abcdef"


def registry(text="Saved 测🙂e\u0301\r\n<script>text</script>\t "):
    return {
        "topic": "Not part of the projection", "academic_sources": [{
            "source_id": "A1", "title": "  <script>untrusted</script>  ",
            "publisher": " Publisher ", "source_type": "academic_paper",
            "url": "javascript:still-inert", "doi": " doi:unchanged ",
            "published_date": "2099-12-31", "accessed_date": "not-normalized",
            "evidence_summary": text, "summary_source": "abstract",
        }], "patent_sources": [], "market_sources": [],
    }


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def saved_file(root, value=None):
    directory = root / RUN_ID
    directory.mkdir(parents=True)
    path = directory / "validated_sources.json"
    path.write_bytes(encoded(registry() if value is None else value))
    return path


@pytest.mark.parametrize("text", [None, "", " \t\r\n", "精确🙂e\u0301\r\n\t "])
def test_projection_preserves_every_saved_field_and_text_state(text):
    """Date repair, trimming or None-to-empty conversion changes saved identity."""
    value = registry(text)
    before = deepcopy(value)
    snapshot = loader.snapshot_from_saved_bytes(encoded(value), "server-owned arbitrary reference")
    row = value["academic_sources"][0]
    expected = {key: row[key] for key in (
        "source_id", "title", "publisher", "source_type", "url", "doi", "published_date", "accessed_date")}
    expected.update(group="academic", summary=text, origin="abstract")
    assert snapshot.sources[0].model_dump() == expected
    assert set(expected) == set(SnapshotSource.model_fields)
    assert snapshot.report_ref == "server-owned arbitrary reference"
    assert value == before
    with pytest.raises(ValueError, match="frozen"):
        snapshot.sources[0].title = "mutated"


def test_optional_legacy_fields_and_empty_groups_are_not_fabricated():
    """Absent saved summaries/provenance stay absent/unknown, not fresh evidence."""
    value = registry()
    row = value["academic_sources"][0]
    for key in ("evidence_summary", "summary_source", "url", "doi", "published_date"):
        row.pop(key)
    result = loader.snapshot_from_saved_bytes(encoded(value), "one").sources[0]
    assert result.summary is None and result.origin == "unknown"
    assert result.url is None and result.doi is None and result.published_date is None
    value["academic_sources"] = []
    assert loader.snapshot_from_saved_bytes(encoded(value), "one").sources == ()


@pytest.mark.parametrize("field,value", [
    ("source_id", "A0"), ("source_id", "A1\n"), ("source_id", "P1"), ("source_id", 1),
    ("title", ""), ("title", "x" * 1025), ("publisher", "x" * 513),
    ("source_type", "x" * 65), ("url", "x" * 4097), ("doi", "x" * 513),
    ("published_date", "x" * 33), ("accessed_date", ""), ("accessed_date", 123),
    ("evidence_summary", False),
    pytest.param("evidence_summary", "x" * 100001, id="oversized-saved-summary"),
    ("summary_source", "full_text"), ("summary_source", ""),
])
def test_snapshot_field_bounds_fail_whole_registry(field, value):
    """A malformed second row must not leave a shortened apparently valid set."""
    data = registry()
    bad = {**data["academic_sources"][0], "source_id": "A2", field: value}
    data["academic_sources"].append(bad)
    with pytest.raises(loader.SavedSourceUnavailable, match="^Saved sources unavailable\\.$"):
        loader.snapshot_from_saved_bytes(encoded(data), "one")


@pytest.mark.parametrize("group", ["academic_sources", "patent_sources", "market_sources"])
@pytest.mark.parametrize("bad", [None, {}, "private malformed group", 2, [None]])
def test_malformed_groups_cannot_be_silently_ignored(group, bad):
    data = registry()
    data[group] = bad
    with pytest.raises(loader.SavedSourceUnavailable):
        loader.snapshot_from_saved_bytes(encoded(data), "one")


@pytest.mark.parametrize("group", ["academic_sources", "patent_sources", "market_sources"])
def test_missing_group_is_not_evidence_of_an_empty_group(group):
    data = registry()
    data.pop(group)
    with pytest.raises(loader.SavedSourceUnavailable):
        loader.snapshot_from_saved_bytes(encoded(data), "one")


@pytest.mark.parametrize("raw", [
    b"[]", b"null", b"{}", b"{broken", b"\xff", b"\xef\xbb\xbf{}",
    b'{"academic_sources":[],"academic_sources":[],"patent_sources":[],"market_sources":[]}',
    b'{"private":NaN}', b'{"private":Infinity}', b'{"private":-Infinity}',
    b'{"private":"\\ud800"}', b"[" * 1100 + b"]" * 1100,
])
def test_strict_json_and_safe_failures(raw):
    """Malformed JSON, duplicate keys and non-UTF8 scalar data never project."""
    with pytest.raises(loader.SavedSourceUnavailable) as failure:
        loader.snapshot_from_saved_bytes(raw, "private-ref")
    assert str(failure.value) == "Saved sources unavailable."
    assert "private" not in repr(failure.value)


def test_nested_duplicate_keys_and_duplicate_source_ids_are_rejected():
    raw = encoded(registry()).replace(b'"source_id": "A1"', b'"source_id":"A1","source_id":"A2"')
    with pytest.raises(loader.SavedSourceUnavailable):
        loader.snapshot_from_saved_bytes(raw, "one")
    data = registry()
    data["academic_sources"].append(deepcopy(data["academic_sources"][0]))
    with pytest.raises(loader.SavedSourceUnavailable):
        loader.snapshot_from_saved_bytes(encoded(data), "one")


def test_snapshot_source_count_bound_and_required_field():
    """All rows count, and a missing required metadata field cannot be invented."""
    data = registry()
    row = data["academic_sources"][0]
    data["academic_sources"] = [{**row, "source_id": f"A{i}"} for i in range(1, 258)]
    with pytest.raises(loader.SavedSourceUnavailable):
        loader.snapshot_from_saved_bytes(encoded(data), "one")
    data = registry()
    data["academic_sources"][0].pop("title")
    with pytest.raises(loader.SavedSourceUnavailable):
        loader.snapshot_from_saved_bytes(encoded(data), "one")


@pytest.mark.parametrize("reference", ["", "x" * 257, None, 5])
def test_invalid_server_reference_is_safe(reference):
    with pytest.raises(loader.SavedSourceUnavailable):
        loader.snapshot_from_saved_bytes(encoded(registry()), reference)


def test_actual_byte_limit_accepts_exact_limit_and_rejects_extra(tmp_path, monkeypatch):
    """Actual read length, not a stale stat size, owns the one-MiB bound."""
    path = saved_file(tmp_path)
    raw = path.read_bytes()
    exact = raw + b" " * (loader.MAX_SAVED_BYTES - len(raw))
    path.write_bytes(exact)
    assert loader.SavedSourceLoader(tmp_path)(RUN_ID).sources[0].source_id == "A1"
    path.write_bytes(exact + b"private-overflow")
    calls = []
    original = os.fdopen

    class Observed:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def fileno(self):
            return self.stream.fileno()

        def read(self, size):
            calls.append(size)
            return self.stream.read(size)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "fdopen", lambda *args, **kwargs: Observed(original(*args, **kwargs)))
        with pytest.raises(loader.SavedSourceUnavailable):
            loader.SavedSourceLoader(tmp_path)(RUN_ID)
    assert calls == [loader.MAX_SAVED_BYTES + 1]
    with pytest.raises(loader.SavedSourceUnavailable):
        loader.snapshot_from_saved_bytes(exact + b" ", "one")


@pytest.mark.parametrize("run_id", [
    "../private", "..", "", "abc", "/absolute", "C:\\private", RUN_ID + "/child",
    RUN_ID + "\\child", RUN_ID + "\n", RUN_ID + ":stream", RUN_ID.upper(),
    "２０２６0919T123456Z-ab", "20260919T123456Z-" + "a" * 129, None,
    "20260919T123456Z-", "20260919T123456Z-" + "a" * 31, "20260919T123456Z-" + "a" * 33,
])
def test_invalid_run_ids_never_touch_filesystem(tmp_path, monkeypatch, run_id):
    def forbidden(*_args, **_kwargs):
        pytest.fail("invalid ID reached filesystem")
    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "lstat", forbidden)
        with pytest.raises(loader.SavedSourceUnavailable):
            loader.SavedSourceLoader(tmp_path)(run_id)


def test_only_direct_registry_is_read_and_missing_differs_from_corrupt(tmp_path):
    """No recursive search, alternate artifact, or private path in diagnostics."""
    saved_file(tmp_path / "nested")
    direct = loader.SavedSourceLoader(tmp_path)
    with pytest.raises(loader.SavedSourceMissing, match="^Saved sources not found\\.$"):
        direct(RUN_ID)
    path = saved_file(tmp_path)
    assert direct(RUN_ID).report_ref == RUN_ID
    path.write_bytes(b"corrupt private material")
    with pytest.raises(loader.SavedSourceUnavailable, match="^Saved sources unavailable\\.$"):
        direct(RUN_ID)


def test_real_directory_indirection_is_denied(tmp_path):
    """Both Windows junctions and POSIX directory symlinks must fail closed."""
    real = tmp_path / "real"
    saved_file(real)
    indirect = tmp_path / "indirect"
    if os.name == "nt":
        import _winapi
        _winapi.CreateJunction(str(real), str(indirect))
    else:
        indirect.symlink_to(real, target_is_directory=True)
    with pytest.raises(loader.SavedSourceUnavailable):
        loader.SavedSourceLoader(indirect)(RUN_ID)
    root = tmp_path / "root"
    root.mkdir()
    indirect_run = root / RUN_ID
    if os.name == "nt":
        _winapi.CreateJunction(str(real / RUN_ID), str(indirect_run))
    else:
        indirect_run.symlink_to(real / RUN_ID, target_is_directory=True)
    with pytest.raises(loader.SavedSourceUnavailable):
        loader.SavedSourceLoader(root)(RUN_ID)


def test_hardlinked_registry_is_denied(tmp_path):
    path = saved_file(tmp_path)
    os.link(path, tmp_path / "other-private-name.json")
    with pytest.raises(loader.SavedSourceUnavailable):
        loader.SavedSourceLoader(tmp_path)(RUN_ID)


@pytest.mark.parametrize("kind", ["symlink", "reparse", "directory"])
def test_file_indirection_is_denied_before_open(tmp_path, monkeypatch, kind):
    """A reparse bit matters even when st_mode reports an ordinary file."""
    path = saved_file(tmp_path)
    original = Path.lstat

    def altered(self, *args, **kwargs):
        info = original(self, *args, **kwargs)
        if self != path:
            return info
        return SimpleNamespace(st_mode=stat.S_IFLNK if kind == "symlink" else (
            stat.S_IFDIR if kind == "directory" else info.st_mode), st_nlink=1,
            st_file_attributes=stat.FILE_ATTRIBUTE_REPARSE_POINT if kind == "reparse" else 0)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "lstat", altered)
        scoped.setattr(os, "open", lambda *_a, **_k: pytest.fail("indirect file opened"))
        with pytest.raises(loader.SavedSourceUnavailable):
            loader.SavedSourceLoader(tmp_path)(RUN_ID)


def test_replaced_file_is_not_read_after_path_check(tmp_path, monkeypatch):
    """Descriptor identity catches a replacement between lstat and open."""
    path = saved_file(tmp_path)
    replacement = tmp_path / "replacement"
    replacement.write_bytes(encoded(registry("other data")))
    original = os.open

    def replaced(*args, **kwargs):
        os.replace(replacement, path)
        return original(*args, **kwargs)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "open", replaced)
        with pytest.raises(loader.SavedSourceUnavailable):
            loader.SavedSourceLoader(tmp_path)(RUN_ID)


def test_permission_failure_does_not_leak_path(tmp_path, monkeypatch):
    saved_file(tmp_path)
    def denied(*_args, **_kwargs):
        raise PermissionError("private path and credential")
    with monkeypatch.context() as scoped:
        scoped.setattr(os, "open", denied)
        with pytest.raises(loader.SavedSourceUnavailable) as failure:
            loader.SavedSourceLoader(tmp_path)(RUN_ID)
    assert str(failure.value) == "Saved sources unavailable."


def test_registry_disappearing_after_stat_is_unavailable_not_initially_missing(tmp_path, monkeypatch):
    """A path replacement/loss race cannot be presented as an absent registry."""
    path = saved_file(tmp_path)
    original = os.open
    def disappeared(*args, **kwargs):
        path.unlink()
        return original(*args, **kwargs)
    with monkeypatch.context() as scoped:
        scoped.setattr(os, "open", disappeared)
        with pytest.raises(loader.SavedSourceUnavailable):
            loader.SavedSourceLoader(tmp_path)(RUN_ID)
