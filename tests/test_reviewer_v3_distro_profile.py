"""Normal-profile boundaries, with genuine distro imports isolated in fresh children.

These additive checks are outside the original 529-node invocation. Deliberate
configuration/filter defects exercise the same delivery assertions as positives.
The two cold-import controls install the original Guard only inside their child;
they do not invoke a runner, provider, or historical H3 case.
"""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch as mock_patch

import pytest

from evals.reviewer_comparison_v3 import test_invoker as invoker


KEYS = ("UNIXCONFDIR", "UNIXUSRLIBDIR")


def runtime_fields(monkeypatch, *, name, platform, version, implementation="cpython"):
    # Replace only the invoker's module references, not process-global os/sys.
    monkeypatch.setattr(invoker, "os", SimpleNamespace(**(vars(os) | {"name": name})))
    monkeypatch.setattr(invoker, "sys", SimpleNamespace(
        platform=platform, implementation=SimpleNamespace(name=implementation), version_info=version))


@pytest.mark.parametrize("name,platform,implementation,version,expected", [
    ("nt", "win32", "cpython", (3, 11), True),
    ("nt", "win32", "cpython", (3, 12), True),
    ("posix", "linux", "cpython", (3, 11), True),
    ("posix", "linux", "cpython", (3, 12), True),
    ("posix", "darwin", "cpython", (3, 11), False),
    ("posix", "freebsd14", "cpython", (3, 12), False),
    ("posix", "linux", "pypy", (3, 11), False),
    ("nt", "win32", "pypy", (3, 12), False),
    ("posix", "linux", "cpython", (3, 10), False),
    ("posix", "linux", "cpython", (3, 13), False),
    ("nt", "win32", "cpython", (3, 10), False),
    ("nt", "win32", "cpython", (3, 13), False),
])
def test_distro_profile_runtime_matrix(monkeypatch, name, platform, implementation, version, expected):
    """A Windows-only classifier left both supported Linux ABIs probing host os-release."""
    runtime_fields(monkeypatch, name=name, platform=platform, implementation=implementation, version=version)
    assert invoker._distro_profile_target() is expected


def paths_for(base):
    return {name: base / name for name in (
        "home", "local", "roaming", "tmp", "work", "xdg-config", "xdg-data", "xdg-cache")}


def assert_profile_delivery(selected, paths):
    actual = {name: value for name, value in selected.items() if name.upper() in KEYS}
    expected = dict(zip(KEYS, (str(paths["work"].parent / leaf) for leaf in ("distro-etc", "distro-usr-lib")), strict=True))
    assert actual == expected, "both_owned_distro_directories_required"


@pytest.mark.parametrize("name,platform", [("nt", "win32"), ("posix", "linux")])
@pytest.mark.parametrize("version", [(3, 11), (3, 12)])
def test_target_profile_preserves_eight_keys_and_creates_empty_physical_dirs(
        tmp_path, monkeypatch, name, platform, version):
    """The repair must create actual owned directories without changing callers' path API."""
    (tmp_path / "outputs").mkdir()
    monkeypatch.setattr(invoker, "ROOT", tmp_path)
    monkeypatch.setattr(invoker, "PROFILE_BASE", tmp_path / "outputs" / "profiles")
    runtime_fields(monkeypatch, name=name, platform=platform, version=version)
    owned, paths = invoker._owned_profile()
    assert paths == paths_for(owned)
    selected = invoker._environment_values({"unixconfdir": "untrusted", "UnixUsrLibDir": "untrusted"}, paths)
    assert_profile_delivery(selected, paths)
    for name in KEYS:
        directory = Path(selected[name])
        assert directory.parent == owned and directory.is_dir() and directory.resolve() == directory
        assert list(directory.iterdir()) == []
    damaged = dict(selected)
    del damaged["UNIXUSRLIBDIR"]
    with pytest.raises(AssertionError, match="both_owned_distro_directories_required"):
        assert_profile_delivery(damaged, paths)


def test_other_platform_does_not_add_distro_configuration(tmp_path, monkeypatch):
    """Normal-profile admission must not silently add an unsupported platform."""
    runtime_fields(monkeypatch, name="posix", platform="darwin", version=(3, 12))
    selected = invoker._environment_values({"UNIXCONFDIR": "ambient"}, paths_for(tmp_path))
    assert not {name.upper() for name in selected}.intersection(KEYS)


_DISTRO_IMPORT_SCRIPT = r'''
import importlib.util
import json
from pathlib import Path
import sys

assert sys.flags.no_site and sys.flags.dont_write_bytecode and sys.flags.ignore_environment
source, site, base = map(Path, sys.argv[1:4])
missing = sys.argv[4] == "missing"
assert sys.argv[4] in {"owned", "missing"}
stdlib = [entry for entry in sys.path if entry and Path(entry).is_absolute()]
spec = importlib.util.spec_from_file_location("profile_under_test", source)
invoker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(invoker)
assert invoker._distro_profile_target()
for filename, size, digest in invoker._DISTRO_SOURCES.values():
    raw = (site / "distro" / filename).read_bytes()
    assert len(raw) == size and invoker.hashlib.sha256(raw).hexdigest() == digest
invoker._distro_require_cold(sys.modules)
invoker.ROOT = base
invoker.PROFILE_BASE = base / "outputs" / "profiles"
(base / "outputs").mkdir()
owned, paths = invoker._owned_profile()
invoker._test_environment(paths)
configured = {name: str(path) for name, path in invoker._distro_profile_dirs(paths).items()}
assert all(invoker.os.environ.get(name) == value for name, value in configured.items())
assert all(Path(value).is_dir() and not list(Path(value).iterdir()) for value in configured.values())
if missing:
    for name in configured:
        del invoker.os.environ[name]
guard = invoker.Guard(owned, [*stdlib, site], [], windows=sys.platform == "win32")
invoker._install_io_guard(guard, owned, "no_subprocess_is_admitted")
sys.path[:] = [*stdlib, str(site)]
import_returned = False
try:
    import distro
    import_returned = True
except PermissionError as error:
    assert str(error) == "read_outside_admitted_sources"
module = sys.modules.get("distro.distro")
actual = None if module is None else {
    "UNIXCONFDIR": module._distro.etc_dir,
    "UNIXUSRLIBDIR": module._distro.usr_lib_dir,
}
print(json.dumps({"platform": sys.platform, "version": list(sys.version_info[:2]),
                  "configured": configured, "actual": actual,
                  "import_returned": import_returned, "violations": guard.violations,
                  "status": guard.finish_status(0)}), flush=True)
raise SystemExit(guard.finish_status(0))
'''


@pytest.mark.parametrize("configuration", ["owned", "missing"])
def test_fresh_distro_import_under_original_guard(tmp_path, configuration):
    """Removing both real env keys must leave the original Guard's host-probe denials cumulative."""
    spec = importlib.util.find_spec("distro")
    assert spec is not None and spec.origin is not None
    site = Path(spec.origin).parent.parent
    result = subprocess.run(
        [sys.executable, "-B", "-E", "-S", "-c", _DISTRO_IMPORT_SCRIPT,
         str(invoker.ROOT / invoker.ENTRY), str(site), str(tmp_path), configuration],
        cwd=tmp_path, env={"LANG": "C", "LC_ALL": "C"},
        capture_output=True, text=True, encoding="utf-8", timeout=30, check=False)
    assert result.stdout, result.stderr
    observed = json.loads(result.stdout)
    assert observed["platform"] == sys.platform and observed["version"] == list(sys.version_info[:2])
    if configuration == "owned":
        assert result.returncode == observed["status"] == 0, result.stderr
        assert observed["import_returned"] and observed["actual"] == observed["configured"]
        assert observed["violations"] == []
    else:
        # CP312's Windows wrapper propagates the first refusal. The Python
        # predicates on Linux/NT311 catch it and probe both default locations.
        propagates = sys.platform == "win32" and sys.version_info[:2] == (3, 12)
        assert result.returncode == observed["status"] == 1, result.stderr
        assert observed["import_returned"] is not propagates
        assert observed["violations"] == ["read_outside_admitted_sources"] * (1 if propagates else 2)
        assert observed["actual"] == (None if propagates else {"UNIXCONFDIR": "/etc", "UNIXUSRLIBDIR": "/usr/lib"})


@pytest.mark.parametrize("defect", [False, True])
def test_real_cold_envelope_and_original_audit_reject_distro_flag_leak(tmp_path, monkeypatch, defect):
    """An omitted filter key must be denied at the original delegated-Popen audit boundary."""
    script = "synthetic_cold_script_not_executed"
    runtime = tmp_path / "runtime"
    command = [sys.executable, "-B", "-c", script, "identity", str(runtime), "none"]
    guard = invoker.Guard(tmp_path, [], [])
    _path, audit = invoker._io_callbacks(guard, tmp_path, script)
    captured = []

    class RecordingPopen:
        def __init__(self, actual, *args, **kwargs):
            assert actual == command and args == () and kwargs["cwd"] == invoker.ROOT
            supplied = kwargs["env"]
            captured.append(dict(supplied))
            audit("subprocess.Popen", (sys.executable, actual, str(kwargs["cwd"]), supplied))
            assert not {name.upper() for name in supplied}.intersection(KEYS), "distro_flag_reached_cold_child"

    original_filter = invoker._cold_environment

    def leaking_filter(original):
        selected = original_filter(original)
        selected["UnixUsrLibDir"] = original["UnixUsrLibDir"]
        return selected

    environment = {"UNIXCONFDIR": "synthetic-etc", "UnixUsrLibDir": "synthetic-lib", "LANG": "C"}
    with mock_patch.dict(os.environ, environment, clear=True), monkeypatch.context() as local:
        local.setattr(subprocess, "Popen", RecordingPopen)
        if defect:
            local.setattr(invoker, "_cold_environment", leaking_filter)
        invoker._install_cold_envelope(script, guard)
        if defect:
            with pytest.raises(PermissionError, match="normal_model_flag_in_cold_child"):
                subprocess.Popen(command, cwd=invoker.ROOT)
        else:
            subprocess.Popen(command, cwd=invoker.ROOT)
    assert len(captured) == 1
    assert guard.violations == (["normal_model_flag_in_cold_child"] if defect else [])
    assert guard.finish_status(0) == int(defect)


def test_explicit_h3_negative_keeps_sysconfig_isolated_and_refuses_selector_mixing(monkeypatch):
    """The missing-distro control must never disable the already established sysconfig isolation."""
    monkeypatch.setattr(invoker, "_distro_profile_target", lambda: True)
    assert invoker._h3_configuration({}, platform=("nt", "cpython", (3, 11))) is None
    values = dict(zip(invoker._H3_INPUTS, ("10c852e8-dcf8-4f9e-b162-79460ab6e48f", "a" * 64), strict=True))
    configuration = invoker._h3_configuration(values, platform=("nt", "cpython", (3, 11)))
    assert configuration["mode"] == "isolated" and configuration["diagnostic_binding"] == "explicit_h3"
    for invalid in ({invoker._H3_INPUTS[0]: values[invoker._H3_INPUTS[0]]},
                    {**values, invoker._SYSCONFIG_INPUTS[0]: "missing-control"},
                    {**values, invoker._H2_INPUTS[0]: invoker._H2_CASE}):
        with pytest.raises(RuntimeError, match="h3_configuration_binding_invalid"):
            invoker._h3_configuration(invalid, platform=("nt", "cpython", (3, 11)))


@pytest.mark.parametrize("name", ["distro", "distro.distro", "distro.synthetic_child"])
def test_cold_check_includes_every_distro_submodule(name):
    """Checking only the package name would admit a prewarmed implementation module."""
    invoker._distro_require_cold({"unrelated": object()})
    with pytest.raises(RuntimeError, match="requires_cold_package_and_submodules"):
        invoker._distro_require_cold({name: object()})


def test_source_reference_rejects_changed_bytes_without_executing_body(tmp_path):
    """The reference binder must reject source drift and compile without running top-level code."""
    source = tmp_path / "public-synthetic.py"
    raw = b'raise AssertionError("reference_must_not_execute")\n'
    source.write_bytes(raw)
    codes = invoker._sysconfig_reference_codes(source, len(raw), hashlib.sha256(raw).hexdigest())
    assert ("<module>", 1) in codes
    with pytest.raises(RuntimeError, match="source_identity_drift"):
        invoker._sysconfig_reference_codes(source, len(raw), "0" * 64)


def test_profile_observer_fault_preserves_original_denial_and_cumulative_ledger(tmp_path):
    """The additive distro observer cannot replace a real PermissionError or clear its ledger."""
    guard = invoker.Guard(tmp_path, [], [])
    observer = object.__new__(invoker._SysconfigObservation)
    observer.data = {"observer_fault": False}
    seen = []

    def broken(*args, **kwargs):
        raise ValueError("private_observer_error_not_reported")

    observer.h3_profile = SimpleNamespace(record_probe=broken, data={"observer_fault": False})

    def denied(*args, **kwargs):
        try:
            guard.deny("read_outside_admitted_sources")
        except PermissionError as error:
            seen.append(error)
            raise

    with pytest.raises(PermissionError) as failure:
        observer._wrap_path(denied)(tmp_path, "probe")
    assert failure.value is seen[0]
    assert observer.data["observer_fault"] is True
    assert guard.violations == ["read_outside_admitted_sources"] and guard.finish_status(0) == 1
    assert "private_observer_error" not in repr(observer.data)
