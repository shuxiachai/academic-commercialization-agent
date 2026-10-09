"""Synthetic unit contracts; the separate frozen script is NOT run by pytest.

Windows has no admitted Linux stdlib here. Synthetic source/loader checks below
test the adapter mechanics, not Linux import success. Native evidence requires
the three separately reviewed fresh Linux processes at the bottom of this file.
"""

import ast
from importlib.machinery import SourceFileLoader
import importlib.util
import os
import sys
from threading import get_ident
from types import SimpleNamespace

import pytest

from evals.reviewer_comparison_v3 import linux_sysconfig_profile as profile
from evals.reviewer_comparison_v3 import test_invoker as invoker


def synthetic_binding(tmp_path, *, variant="ordinary", tail=""):
    """Bypass only source admission for a clearly synthetic unit fixture."""
    source = tmp_path / "sysconfig.py"
    prelude = ""
    call = "_safe_realpath(sys.executable)"
    if variant == "foreign_globals":
        prelude = "selected = types.FunctionType(_safe_realpath.__code__, dict(globals()))\n"
        call = "selected(sys.executable)"
    elif variant == "equal_not_identical_code":
        prelude = "selected = types.FunctionType(_safe_realpath.__code__.replace(), globals())\n"
        call = "selected(sys.executable)"
    elif variant == "wrong_argument":
        call = "_safe_realpath(sys.executable + '-not-the-executable')"
    raw = (
        "import os, sys, types\nfrom os.path import realpath\n"
        "def _safe_realpath(path):\n"
        "    try:\n        return realpath(path)\n"
        "    except OSError:\n        return path\n"
        "before_initial()\n" + prelude
        + ("for repeat in range(2):\n    " if variant == "repeat" else "")
        + "_PROJECT_BASE = os.path.dirname(" + call + ")\n"
        "before_override()\n"
        "if '_PYTHON_PROJECT_BASE' in os.environ:\n"
        "    _PROJECT_BASE = _safe_realpath(os.environ['_PYTHON_PROJECT_BASE'])\n"
        "_PYTHON_BUILD = False\n" + tail
    )
    source.write_text(raw, encoding="utf-8")
    candidate = object.__new__(profile._Profile)
    candidate.source = source
    candidate.reference = compile(raw, str(source), "exec", dont_inherit=True)
    candidate.call_line = next(i for i, line in enumerate(raw.splitlines(), 1)
                               if "_PROJECT_BASE = os.path.dirname(" in line)
    candidate.project = tmp_path / "owned-project"
    candidate.project.mkdir()
    candidate.runtime, candidate.thread = profile._runtime(), get_ident()
    candidate.facts = {"test_scope": "synthetic_unit_only", "declined_optional_resolution": 0,
                       "loader_code_verified": False, "completed": False, "fault": False}
    candidate.selected = True
    candidate.active = False
    candidate.module = candidate.module_code = candidate.safe_code = None
    delegate = SourceFileLoader("sysconfig", str(source))
    candidate.spec = importlib.util.spec_from_file_location("sysconfig", source, loader=delegate)
    candidate.spec._initializing = True
    module = importlib.util.module_from_spec(candidate.spec)
    module.before_initial = lambda: None
    module.before_override = lambda: None
    return candidate, delegate, module


def execute_synthetic(monkeypatch, candidate, delegate, module):
    monkeypatch.setitem(sys.modules, "sysconfig", module)
    monkeypatch.delenv("_PYTHON_PROJECT_BASE", raising=False)
    scope = profile._ImportScope(candidate, delegate)
    scope.exec_module(module)


def test_synthetic_real_loader_uses_actual_code_and_restores_at_import_return(tmp_path, monkeypatch):
    """The optional call must use genuine fallback, with no executable realpath IO."""
    candidate, delegate, module = synthetic_binding(tmp_path)
    original, calls = os.path.realpath, []

    def recording(raw, *args, **kwargs):
        calls.append(raw)
        return original(raw, *args, **kwargs)

    monkeypatch.setattr(os.path, "realpath", recording)
    before = profile._runtime()
    execute_synthetic(monkeypatch, candidate, delegate, module)
    assert candidate.facts == {"test_scope": "synthetic_unit_only", "declined_optional_resolution": 1,
        "loader_code_verified": True, "completed": True, "fault": False,
        "bindings_restored": True, "finder_restored": True}
    assert sys.executable not in calls and str(candidate.project) in calls
    assert profile._runtime() == before
    assert module._safe_realpath.__code__ is candidate.safe_code
    assert candidate.module_code == candidate.reference and candidate.module_code is not candidate.reference
    assert type(module.__loader__) is SourceFileLoader and module.__spec__.loader is delegate
    assert os.path.realpath is module.realpath is recording
    assert "get_code" not in vars(delegate) and profile._environment_absent()


@pytest.mark.parametrize("variant", ["foreign_globals", "equal_not_identical_code", "wrong_argument",
                                     "wrong_origin", "wrong_line", "wrong_thread"])
def test_illegal_source_context_gets_original_guard_denial(tmp_path, monkeypatch, variant):
    """Equal code, borrowed globals or a lookalike origin must not obtain the capability decline."""
    candidate, delegate, module = synthetic_binding(tmp_path, variant=variant)
    guard = invoker.Guard(tmp_path, [], [], windows=sys.platform == "win32")

    def guarded_realpath(raw, *args, **kwargs):
        guard.path(raw, "probe")
        return raw

    if variant == "wrong_origin":
        candidate.spec.origin = str(tmp_path / "other.py")
    elif variant == "wrong_line":
        candidate.call_line += 1
    elif variant == "wrong_thread":
        module.before_initial = lambda: setattr(candidate, "thread", -1)
    monkeypatch.setattr(os.path, "realpath", guarded_realpath)
    with pytest.raises(RuntimeError, match="completed_profile_mismatch"):
        execute_synthetic(monkeypatch, candidate, delegate, module)
    assert candidate.facts["declined_optional_resolution"] == 0
    assert guard.violations == ["read_outside_admitted_sources"] and guard.finish_status(0) == 1
    assert candidate.facts["bindings_restored"] and candidate.facts["fault"]


def test_repeat_at_the_same_actual_callsite_keeps_cumulative_refusal(tmp_path, monkeypatch):
    """A second call on the same code/line must delegate even when stdlib catches the refusal."""
    candidate, delegate, module = synthetic_binding(tmp_path, variant="repeat")
    guard = invoker.Guard(tmp_path, [], [], windows=sys.platform == "win32")

    def guarded_realpath(raw, *args, **kwargs):
        guard.path(raw, "probe")
        return raw

    monkeypatch.setattr(os.path, "realpath", guarded_realpath)
    execute_synthetic(monkeypatch, candidate, delegate, module)
    assert candidate.facts["declined_optional_resolution"] == 1
    assert guard.violations == ["read_outside_admitted_sources"] and guard.finish_status(0) == 1
    assert candidate.facts["bindings_restored"]


@pytest.mark.parametrize("exception", [RuntimeError("synthetic"), KeyboardInterrupt("synthetic")])
def test_original_import_failure_survives_immediate_restoration(tmp_path, monkeypatch, exception):
    """A failed genuine loader call must restore before its exact original exception escapes."""
    candidate, delegate, module = synthetic_binding(tmp_path, tail="raise original_exception\n")
    module.original_exception = exception
    original = os.path.realpath
    with pytest.raises(type(exception)) as caught:
        execute_synthetic(monkeypatch, candidate, delegate, module)
    assert caught.value is exception
    assert os.path.realpath is module.realpath is original
    assert candidate.facts["fault"] and candidate.facts["bindings_restored"]
    assert "get_code" not in vars(delegate) and profile._environment_absent()


def test_changed_loader_bytes_fail_before_executing_module_body(tmp_path, monkeypatch):
    """Source-file-loader execution cannot substitute cached or changed code for the compiled binding."""
    candidate, delegate, module = synthetic_binding(tmp_path)
    candidate.source.write_text("raise AssertionError('changed body executed')\n", encoding="utf-8")
    original = os.path.realpath
    with pytest.raises(RuntimeError, match="loaded_code_mismatch"):
        execute_synthetic(monkeypatch, candidate, delegate, module)
    assert not candidate.facts["loader_code_verified"]
    assert candidate.facts["fault"] and candidate.facts["bindings_restored"]
    assert os.path.realpath is original and profile._environment_absent()


def test_missing_owned_override_fails_the_delivery_contract(tmp_path, monkeypatch):
    """Omitting the later owned override cannot silently leave the executable directory cached."""
    candidate, delegate, module = synthetic_binding(tmp_path)
    module.before_override = lambda: os.environ.pop("_PYTHON_PROJECT_BASE")
    with pytest.raises(RuntimeError, match="completed_profile_mismatch"):
        execute_synthetic(monkeypatch, candidate, delegate, module)
    assert candidate.facts["declined_optional_resolution"] == 1
    assert candidate.facts["fault"] and candidate.facts["bindings_restored"]


def test_unknown_source_is_never_self_authenticated(tmp_path):
    """Computing a new runtime hash is not admission to the finite source table."""
    source = tmp_path / "sysconfig.py"
    source.write_bytes(b"raise AssertionError('not executable authority')\n")
    for version in ((3, 11, 17), (3, 12, 3)):
        with pytest.raises(RuntimeError, match="source_not_approved"):
            profile._source_binding(source, version)
    assert {(item[0], item[1]) for item in profile.CANDIDATES.values()} == {
        (32768, (3, 12, 3)), (30315, (3, 11, 17)), (30999, (3, 12, 3))}


@pytest.mark.parametrize("body_fails", [False, True])
def test_outer_scope_removes_only_its_finder_when_import_never_completes(monkeypatch, body_fails):
    """An import failure before exec_module must not leave a finder registered or become success."""
    unrelated = object()
    fake_sys = SimpleNamespace(platform="linux", meta_path=[unrelated])
    candidate = SimpleNamespace(facts={"fault": False, "completed": False})
    monkeypatch.setattr(profile, "sys", fake_sys)
    monkeypatch.setattr(profile, "_Profile", lambda *args: candidate)
    error = ValueError("synthetic body failure")
    with pytest.raises(ValueError if body_fails else RuntimeError) as caught:
        with profile.install(None, ()):
            assert fake_sys.meta_path == [candidate, unrelated]
            if body_fails:
                raise error
    if body_fails:
        assert caught.value is error
    assert fake_sys.meta_path == [unrelated] and candidate.facts["finder_restored"]


def test_non_linux_path_is_explicit_and_does_not_bind_a_linux_source(monkeypatch):
    """Non-Linux normal startup remains explicit without pretending it exercised a Linux stdlib."""
    monkeypatch.setattr(profile, "sys", SimpleNamespace(platform="win32"))
    with profile.install(None, ()) as facts:
        assert facts == {"applicable": False}


def test_native_control_is_syntax_only_in_the_ordinary_suite():
    """The ordinary suite validates preparation without quietly running a fresh Linux experiment."""
    tree = ast.parse(LINUX_PROFILE_CONTROL)
    assert any(isinstance(node, ast.With) for node in ast.walk(tree))
    assert "pytest.main" not in LINUX_PROFILE_CONTROL and "runner.prepare" not in LINUX_PROFILE_CONTROL


# A fresh process per mode, reviewed separately before execution. This is not a
# pytest test or a platform skip. It never replays the sealed prefix baseline.
LINUX_PROFILE_CONTROL = r'''
import os
import sys
os.environ.clear()
os.environ.update({"LANG": "C", "LC_ALL": "C"})
import hashlib
import importlib.util
import json
from pathlib import Path
import signal

class Deadline(BaseException):
    pass
def stop(signum, frame):
    raise Deadline()
signal.signal(signal.SIGALRM, stop)
signal.alarm(45)
assert sys.platform == "linux" and sys.flags.no_site and sys.flags.ignore_environment and sys.flags.dont_write_bytecode
assert sys.version_info[:3] == (3, 12, 3) and sys.executable == "/usr/bin/python3"
assert sys.prefix == sys.base_prefix == "/usr" and getattr(sys, "_home", None) is None
root, owned, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
assert len(sys.argv) == 4 and mode in {"fixed", "without_capability", "without_owned"}
assert root.is_absolute() and owned.is_absolute() and owned.is_relative_to(root / "outputs")
assert root.resolve() == root and owned.parent.resolve() == owned.parent
assert not os.path.lexists(owned)
modules = {}
bindings = {"invoker": "ad138af039b3b333942b48f7f030efd8fb368f747a55457bd521ede9bed6a26f",
            "profile": "1d64587acc03b17c5248e06567fe01d8d9638dab42bc3656d18c1242841e77ed"}
for label, relative in (("invoker", "test_invoker.py"), ("profile", "linux_sysconfig_profile.py")):
    path = root / "evals/reviewer_comparison_v3" / relative
    with path.open("rb") as handle:
        raw = handle.read(131073)
    assert len(raw) <= 131072 and hashlib.sha256(raw).hexdigest() == bindings[label]
    spec = importlib.util.spec_from_file_location("linux_control_" + label, path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), "exec", dont_inherit=True), module.__dict__)
    modules[label] = module
invoker, profile = modules["invoker"], modules["profile"]
owned.mkdir()
paths = {name: owned / name for name in ("home", "local", "roaming", "tmp", "work", "xdg-config", "xdg-data", "xdg-cache")}
for path in (*paths.values(), *invoker._distro_profile_dirs(paths).values()):
    path.mkdir()
invoker._test_environment(paths)
stdlib = [str(Path(sys.base_prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"),
          str(Path(sys.base_exec_prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "lib-dynload"),
          str(Path(sys.base_prefix) / "lib" / f"python{sys.version_info.major}{sys.version_info.minor}.zip")]
sys.path[:] = stdlib
assert "sysconfig" not in sys.modules
before = profile._runtime()
original_realpath = os.path.realpath
if mode == "without_capability":
    profile._Profile._realpath = lambda self, raw, *args, **kwargs: self.original_realpath(raw, *args, **kwargs)
elif mode == "without_owned":
    # Injection occurs after the authentic caller check, without adding a
    # frame between _safe_realpath and the adapter or replacing stdlib code.
    def remove_owned(message):
        assert message == profile.UNAVAILABLE
        del os.environ["_PYTHON_PROJECT_BASE"]
        return OSError(message)
    profile.OSError = remove_owned
guard = invoker.Guard(owned, stdlib, [], windows=False)
original_path, markers, refusals = guard.path, [], []
observer_fault = False
def remember(raw, operation, denied):
    global observer_fault
    try:
        if type(raw) is str and operation == "probe" and raw.endswith(("/Modules/Setup", "/Modules/Setup.local")):
            assert len(markers) < 4
            markers.append({"leaf": raw.rsplit("/", 1)[-1], "owned": raw.startswith(str(owned) + "/")})
        if denied:
            kinds = {"/usr/bin": "executable_ancestor", "/usr/bin/python3": "executable_entry",
                     "/usr/bin/Modules/Setup": "host_setup", "/usr/bin/Modules/Setup.local": "host_setup_local"}
            source, frame = None, sys._getframe(1)
            active = sys.modules.get("sysconfig")
            for _ in range(8):
                if frame is None:
                    break
                for name in ("_safe_realpath", "is_python_build"):
                    function = getattr(active, name, None)
                    if function is not None and frame.f_code is function.__code__ and frame.f_globals is vars(active):
                        source = name
                frame = frame.f_back
            assert len(refusals) < 4
            refusals.append({"kind": kinds.get(raw, "unexpected"), "operation": operation, "source": source})
    except BaseException:
        observer_fault = True
def observed_path(raw, operation="read", *, resource_open=False):
    try:
        result = original_path(raw, operation, resource_open=resource_open)
    except PermissionError:
        remember(raw, operation, True)
        raise
    remember(raw, operation, False)
    return result
guard.path = observed_path
invoker._install_io_guard(guard, owned, "no_child_process_is_admitted")
facts, error_type = None, None
try:
    with profile.install(owned, stdlib) as facts:
        import sysconfig
        sysconfig.get_config_vars()
        sysconfig.get_paths()
except RuntimeError as error:
    error_type = type(error).__name__
assert profile._runtime() == before and os.path.realpath is original_realpath
assert profile._environment_absent() and not any(isinstance(item, profile._Profile) for item in sys.meta_path)
assert facts is not None and facts["loader_code_verified"] and facts["bindings_restored"]
assert facts["source_sha256"] == "e21755a918f488db1bd21d23120ee36ad09382c553b79735a121ee1fbdbcc08d"
assert not observer_fault
assert [item["leaf"] for item in markers] == ["Setup", "Setup.local"]
if mode == "fixed":
    assert error_type is None and facts["completed"] and not facts["fault"]
    assert facts["declined_optional_resolution"] == 1 and all(item["owned"] for item in markers)
    assert guard.violations == [] and refusals == []
else:
    assert error_type == "RuntimeError" and facts["fault"] and not facts["completed"]
    assert guard.violations == ["read_outside_admitted_sources"] * 2
    assert all(item["owned"] for item in markers) == (mode == "without_capability")
    kinds = ["executable_ancestor", "executable_entry"] if mode == "without_capability" else ["host_setup", "host_setup_local"]
    function = "_safe_realpath" if mode == "without_capability" else "is_python_build"
    assert refusals == [{"kind": kind, "operation": "probe", "source": function} for kind in kinds]
assert not any(name == prefix or name.startswith(prefix + ".") for name in sys.modules
               for prefix in ("pytest", "crewai", "openai", "pydantic", "distro"))
record = {"mode": mode, "facts": facts, "markers": markers, "violations": guard.violations, "refusals": refusals,
          "error_type": error_type, "status": guard.finish_status(0)}
payload = json.dumps(record, sort_keys=True).encode()
assert len(payload) <= 16384
with (owned / "observation.json").open("xb") as handle:
    handle.write(payload)
sys.stdout.buffer.write(payload + b"\n")
sys.stdout.buffer.flush()
raise SystemExit(guard.finish_status(0))
'''
