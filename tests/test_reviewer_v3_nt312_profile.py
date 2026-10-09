"""H6 synthetic profile boundaries, separate from the frozen 529-node invocation.

No real prepare, vendor import, subprocess or process-global audit hook is used.
Runtime selectors are caller-owned facts in these pure controls; they do not
establish a successful native H6 diagnostic or full CP312 run.
"""

import ast
import builtins
import hashlib
import json
import ntpath
import os
from pathlib import Path
import subprocess
import sys
from types import FunctionType, ModuleType, SimpleNamespace

import pytest

from evals.reviewer_comparison_v3 import test_invoker as invoker


NT312 = ("nt", "cpython", (3, 12))
NT311 = ("nt", "cpython", (3, 11))
NORMAL_KEYS = ("_PYTHON_PROJECT_BASE", "UNIXCONFDIR", "UNIXUSRLIBDIR")


def synthetic_runtime(monkeypatch, *, platform=NT312, environment=None):
    """Replace only invoker-owned references, not the interpreter's os/sys modules."""
    system, implementation, version = platform
    shadow_os = SimpleNamespace(**vars(os))
    shadow_os.name = system
    shadow_os.environ = {} if environment is None else environment
    shadow_sys = SimpleNamespace(**vars(sys))
    shadow_sys.version_info = (*version, 9)
    shadow_sys.platform = "win32" if system == "nt" else "linux"
    shadow_sys.implementation = SimpleNamespace(name=implementation, cache_tag=f"{implementation}-{version[0]}{version[1]}")
    monkeypatch.setattr(invoker, "os", shadow_os)
    monkeypatch.setattr(invoker, "sys", shadow_sys)
    return shadow_os, shadow_sys


def h6_values(profile):
    selected = [case for case, candidate in invoker._H6_CASES.items() if candidate == profile]
    assert len(selected) == 1, "h6_case_profile_mapping_drift"
    return dict(zip(invoker._H6_INPUTS, (selected[0], "a" * 64), strict=True))


@pytest.mark.parametrize("platform,expected", [
    (NT312, True), (NT311, False), (("posix", "cpython", (3, 12)), False),
    (("nt", "pypy", (3, 12)), False), (("nt", "cpython", (3, 13)), False),
], ids=["nt312", "nt311", "posix312", "pypy312", "nt313"])
def test_nt312_target_is_separate_from_legacy_platforms(platform, expected):
    """The new eligibility predicate must not redefine old diagnostic ownership."""
    assert invoker._nt312_profile_target(platform=platform) is expected


def test_exact_h6_runtime_identity_admits_only_the_bound_native_abi():
    """A series-wide default must not broaden an exact-patch diagnostic identity."""
    assert invoker._nt312_profile_runtime(
        (3, 12, 9), "cpython-312", 8, [".cp312-win_amd64.pyd", ".pyd"], platform=NT312) == "cp312"


@pytest.mark.parametrize("defect", [
    "patch", "version-length", "cache-tag", "pointer", "suffix-abi", "suffix-order",
    "suffix-missing", "platform", "implementation",
], ids=["patch", "version-length", "cache", "pointer", "suffix-abi", "suffix-order",
        "suffix-missing", "platform", "implementation"])
def test_wrong_h6_runtime_identity_cannot_become_a_profile(defect):
    """Wrong ABI or source-runtime identity must refuse before any profile observation."""
    values = [(3, 12, 9), "cpython-312", 8, [".cp312-win_amd64.pyd", ".pyd"]]
    platform = NT312
    if defect == "patch":
        values[0] = (3, 12, 8)
    elif defect == "version-length":
        values[0] = (3, 12, 9, 0)
    elif defect == "cache-tag":
        values[1] = "cpython-311"
    elif defect == "pointer":
        values[2] = 4
    elif defect == "suffix-abi":
        values[3] = [".cp311-win_amd64.pyd", ".pyd"]
    elif defect == "suffix-order":
        values[3] = [".pyd", ".cp312-win_amd64.pyd"]
    elif defect == "suffix-missing":
        values[3] = [".cp312-win_amd64.pyd"]
    elif defect == "platform":
        platform = ("posix", "cpython", (3, 12))
    else:
        platform = ("nt", "pypy", (3, 12))
    with pytest.raises(RuntimeError, match="nt312_profile_runtime_identity_drift"):
        invoker._nt312_profile_runtime(*values, platform=platform)


def test_h6_isfile_identity_uses_actual_installer_or_explicit_no_install(monkeypatch):
    """A code-shaped callable cannot substitute for the current installed H5 wrapper."""
    shadow_os, _shadow_sys = synthetic_runtime(monkeypatch,
        platform=(os.name, sys.implementation.name, sys.version_info[:2]))
    target = ModuleType("ntpath")
    target.__dict__.update(vars(ntpath))
    shadow_os.path = target
    monkeypatch.setattr(invoker, "ntpath", target)
    before = (target.isfile, target.exists)
    wrappers = invoker._install_nt312_path_guard(lambda *args: None)
    if (os.name, sys.implementation.name, sys.version_info[:2]) != NT312:
        assert wrappers is None and (target.isfile, target.exists) == before
        with pytest.raises(RuntimeError, match="nt312_profile_isfile_identity_drift"):
            invoker._nt312_isfile_identity(target.isfile)
        return
    real_isfile = wrappers[0]
    assert target.isfile is real_isfile
    assert invoker._nt312_isfile_identity(real_isfile) is real_isfile.__code__
    for candidate in (
        lambda path: False,
        FunctionType(real_isfile.__code__, {}, closure=real_isfile.__closure__),
        SimpleNamespace(__code__=real_isfile.__code__, __globals__=invoker.__dict__),
    ):
        target.isfile = candidate
        with pytest.raises(RuntimeError, match="nt312_profile_isfile_identity_drift"):
            invoker._nt312_isfile_identity(candidate)
    target.isfile = lambda path: False
    with pytest.raises(RuntimeError, match="nt312_profile_isfile_identity_drift"):
        invoker._nt312_isfile_identity(real_isfile)
    target.isfile = real_isfile
    assert invoker._nt312_isfile_identity(real_isfile) is real_isfile.__code__


@pytest.mark.parametrize("platform,expected", [
    (NT312, True), (NT311, True), (("posix", "cpython", (3, 12)), False),
    (("nt", "pypy", (3, 12)), False), (("nt", "cpython", (3, 13)), False),
], ids=["nt312-default", "nt311-default", "posix312", "pypy312", "nt313"])
def test_default_configuration_needs_no_diagnostic_selector(platform, expected):
    """Default NT312 isolation must be independent of any consumed diagnostic case."""
    actual = invoker._sysconfig_configuration({}, platform=platform)
    assert actual["mode"] == "isolated"
    assert actual["diagnostic_binding"] == "not_requested"
    assert actual["case_id"] is None and actual["control_sha256"] is None
    assert actual["policy_applicable"] is expected
    assert actual["platform_validation"] == "not_evaluated"


@pytest.mark.parametrize("legacy", ["h1", "h2", "h3"], ids=["h1", "h2", "h3"])
def test_nt312_default_does_not_admit_legacy_selectors(legacy):
    """Broadening default eligibility must not reopen a CP311-only historical selector."""
    if legacy == "h1":
        values = dict(zip(invoker._SYSCONFIG_INPUTS,
                          ("isolated", invoker._SYSCONFIG_CASES["isolated"], "a" * 64), strict=True))
        function = invoker._sysconfig_configuration
    elif legacy == "h2":
        values = dict(zip(invoker._H2_INPUTS, (invoker._H2_CASE, "a" * 64), strict=True))
        function = invoker._h2_configuration
    else:
        values = dict(zip(invoker._H3_INPUTS, (next(iter(invoker._H3_CASES)), "a" * 64), strict=True))
        function = invoker._h3_configuration
    with pytest.raises(RuntimeError):
        function(values, platform=NT312)


@pytest.mark.parametrize("profile,mode", [
    ("missing-project", "missing-control"), ("missing-usr-lib", "isolated"),
    ("isolated-distro", "isolated"),
], ids=["missing-project", "missing-usr-lib", "positive"])
def test_h6_configuration_binds_its_own_case_and_control(profile, mode):
    """Each fresh H6 case must select its declared control without reusing H1-H3."""
    values = h6_values(profile)
    actual = invoker._h6_configuration(values, platform=NT312)
    assert actual["diagnostic_binding"] == "explicit_h6" and actual["mode"] == mode
    assert actual["case_id"] == values[invoker._H6_INPUTS[0]]
    assert actual["control_sha256"] == "a" * 64
    assert actual["policy_applicable"] is True
    assert actual["platform_validation"] == "not_evaluated"
    assert len(actual["policy_sha256"]) == 64
    assert invoker._h6_configuration({}, platform=NT312) is None


@pytest.mark.parametrize("defect", ["missing-case", "missing-control", "bad-case", "bad-digest", "legacy", "wrong-platform"],
                         ids=["missing-case", "missing-control", "bad-case", "bad-digest", "legacy", "wrong-platform"])
def test_h6_selector_faults_never_fall_back_to_default(defect):
    """Incomplete, mixed or wrong-platform selectors must stop before normal execution."""
    values = h6_values("isolated-distro")
    platform = NT312
    if defect == "missing-case":
        del values[invoker._H6_INPUTS[0]]
    elif defect == "missing-control":
        del values[invoker._H6_INPUTS[1]]
    elif defect == "bad-case":
        values[invoker._H6_INPUTS[0]] = invoker._H2_CASE
    elif defect == "bad-digest":
        values[invoker._H6_INPUTS[1]] = "A" * 64
    elif defect == "legacy":
        values[invoker._H3_INPUTS[0]] = next(iter(invoker._H3_CASES))
    else:
        platform = NT311
    with pytest.raises(RuntimeError):
        invoker._h6_configuration(values, platform=platform)


@pytest.mark.parametrize("exit_kind", ["return", "exception", "base-exception"],
                         ids=["return", "exception", "base-exception"])
def test_nt312_prepare_override_restores_all_case_variants(monkeypatch, tmp_path, exit_kind):
    """Failure must not deliver the temporary project base to a later cold child."""
    synthetic_runtime(monkeypatch)
    environment = {"PRESERVED_SYNTHETIC": "value"}
    before = dict(environment)
    failure = {"return": None, "exception": RuntimeError, "base-exception": KeyboardInterrupt}[exit_kind]
    caught = None
    try:
        with invoker._sysconfig_prepare_scope(tmp_path, "isolated", environ=environment, modules={}):
            assert environment["_PYTHON_PROJECT_BASE"] == str(tmp_path)
            environment["_pYtHoN_pRoJeCt_BaSe"] = "synthetic-added-during-prepare"
            if failure is not None:
                raise failure("synthetic-prepare-stop")
    except (RuntimeError, KeyboardInterrupt) as error:
        caught = type(error)
    assert caught is failure and environment == before
    assert invoker._sysconfig_environment_absent(environment)


def test_nt312_owned_distro_directories_and_environment(monkeypatch, tmp_path):
    """New default configuration must point at two fresh physical empty owned directories."""
    synthetic_runtime(monkeypatch)
    (tmp_path / "outputs").mkdir()
    monkeypatch.setattr(invoker, "ROOT", tmp_path)
    monkeypatch.setattr(invoker, "PROFILE_BASE", tmp_path / "outputs/profiles")
    owned, paths = invoker._owned_profile()
    assert set(paths) == {"home", "local", "roaming", "tmp", "work", "xdg-config", "xdg-data", "xdg-cache"}
    directories = invoker._distro_profile_dirs(paths)
    assert set(directories) == {"UNIXCONFDIR", "UNIXUSRLIBDIR"}
    for directory in directories.values():
        assert directory.parent == owned and directory.resolve() == directory
        assert directory.is_dir() and list(directory.iterdir()) == []
    actual = invoker._environment_values({"UnixConfDir": "synthetic-ambient", "UnixUsrLibDir": "synthetic-ambient"}, paths)
    assert {key: value for key, value in actual.items() if key.upper() in directories} == {
        key: str(value) for key, value in directories.items()}
    project = invoker._sysconfig_project(owned)
    assert project.parent == owned and project.is_dir() and list(project.iterdir()) == []
    with pytest.raises(FileExistsError):
        invoker._sysconfig_project(owned)


def assert_cold_delivery(monkeypatch, owned, leaked_key=None):
    environment = {"UnixConfDir": "synthetic-etc",
                   "uNiXuSrLiBdIr": "synthetic-lib", "LANG": "C"}
    synthetic_runtime(monkeypatch, environment=environment)
    with invoker._sysconfig_prepare_scope(owned / "sysconfig-project", "isolated", environ=environment, modules={}):
        assert environment["_PYTHON_PROJECT_BASE"] == str(owned / "sysconfig-project")
        environment["_pYtHoN_pRoJeCt_BaSe"] = "synthetic-added-during-prepare"
    assert invoker._sysconfig_environment_absent(environment), "prepare_finally_must_remove_project_base"
    monkeypatch.setattr(invoker, "ROOT", owned)
    script = "synthetic_cold_program_not_executed"
    command = [invoker.sys.executable, "-B", "-c", script, "identity", str(owned / "runtime"), "none"]
    guard = invoker.Guard(owned, [], [])
    _path, audit = invoker._io_callbacks(guard, owned, script)
    delivered = []

    class RecordingPopen:
        def __init__(self, actual, *args, **kwargs):
            assert actual == command and args == () and kwargs["cwd"] == owned
            audit("subprocess.Popen", (invoker.sys.executable, actual, kwargs["cwd"], kwargs["env"]))
            delivered.append(dict(kwargs["env"]))

    shadow_process = SimpleNamespace(Popen=RecordingPopen, list2cmdline=subprocess.list2cmdline)
    monkeypatch.setattr(invoker, "subprocess", shadow_process)
    original_filter = invoker._cold_environment
    if leaked_key is not None:
        def broken_filter(original):
            result = original_filter(original)
            result[leaked_key] = "synthetic-leak"
            return result
        monkeypatch.setattr(invoker, "_cold_environment", broken_filter)
    invoker._install_cold_envelope(script, guard)
    caught = None
    try:
        shadow_process.Popen(command, cwd=owned)
    except PermissionError as error:
        caught = error
    assert caught is None and guard.violations == [], "normal_flag_must_not_reach_cold_audit"
    assert len(delivered) == 1 and delivered[0]["LANG"] == "C"
    assert not {key.upper() for key in delivered[0]}.intersection(NORMAL_KEYS)
    assert guard.finish_status(0) == 0


@pytest.mark.parametrize("leaked_key", ["UnixConfDir", "uNiXuSrLiBdIr"],
                         ids=["distro-etc", "distro-usr-lib"])
def test_actual_cold_envelope_and_guard_detect_mixed_case_filter_defect(monkeypatch, tmp_path, leaked_key):
    """After real prepare-finally cleanup, the same delivery assertion rejects either leaked distro flag."""
    with monkeypatch.context() as positive:
        assert_cold_delivery(positive, tmp_path)
    with monkeypatch.context() as negative:
        with pytest.raises(AssertionError, match="normal_flag_must_not_reach_cold_audit"):
            assert_cold_delivery(negative, tmp_path, leaked_key)


@pytest.mark.parametrize("environment,expected,rejected", [
    ({"LANG": "C"}, (1, 1, 1), False),
    ({"LANG": "C", "_pYtHoN_pRoJeCt_BaSe": "synthetic-leak"}, (1, 0, 1), True),
    (None, (0, 0, 0), True),
    ({"LANG": "C", "UnixConfDir": "synthetic-leak"}, (1, 1, 0), True),
], ids=["clean", "project-base", "implicit-env", "normal-flag"])
def test_synthetic_execute_child_observer_enforces_explicit_clean_environment(
        monkeypatch, tmp_path, environment, expected, rejected):
    """The existing observer owns project-base leakage detection after a synthetic execute-child event.

    The real _audit method and command admission run, but the caller frame is
    explicitly synthetic. No real Popen, audit hook or native child is used;
    the observer's counter field names are asserted, not reported as native evidence.
    """
    synthetic_runtime(monkeypatch)
    monkeypatch.setattr(invoker, "ROOT", tmp_path)
    observer = object.__new__(invoker._SysconfigObservation)
    observer.guard = invoker.Guard(tmp_path, [], [])
    observer.cold_script = "synthetic_cold_program_not_executed"
    command = [invoker.sys.executable, "-B", "-c", observer.cold_script,
               "identity", str(tmp_path / "runtime"), "none"]
    arguments = (invoker.sys.executable, command, tmp_path, environment)
    facts = {"actual_audit_events": 0, "explicit_environment": 0, "project_base_absent": 0,
             "normal_flags_absent": 0, "child_self_reported_absent": None}
    observer.data = {"cold_launches": facts}

    def synthetic_execute_child(event):
        observer._audit(event, arguments)

    observer.execute_child = synthetic_execute_child.__code__
    # A matching event from another caller and an unrelated event from the
    # synthetic caller must not be counted as this observer's launch.
    observer._audit("subprocess.Popen", arguments)
    synthetic_execute_child("synthetic.unrelated_event")
    assert facts == {"actual_audit_events": 0, "explicit_environment": 0, "project_base_absent": 0,
                     "normal_flags_absent": 0, "child_self_reported_absent": None}
    if rejected:
        with pytest.raises(RuntimeError, match="sysconfig_observer_cold_environment_leak"):
            synthetic_execute_child("subprocess.Popen")
    else:
        synthetic_execute_child("subprocess.Popen")
    assert facts == {"actual_audit_events": 1, "explicit_environment": expected[0],
                     "project_base_absent": expected[1], "normal_flags_absent": expected[2],
                     "child_self_reported_absent": None}
    assert observer.guard.violations == [] and observer.guard.finish_status(0) == 0


def test_public_source_digest_mismatch_stops_before_source_execution(tmp_path):
    """A matching-looking public path cannot replace the source bytes used by an observer."""
    source = tmp_path / "synthetic_public_profile.py"
    raw = b'raise AssertionError("compiled_source_must_not_run")\n'
    source.write_bytes(raw)
    assert ("<module>", 1) in invoker._sysconfig_reference_codes(source, len(raw), hashlib.sha256(raw).hexdigest())
    with pytest.raises(RuntimeError, match="source_identity_drift"):
        invoker._sysconfig_reference_codes(source, len(raw), "0" * 64)


@pytest.mark.parametrize("changed", [None, "sysconfig", "subprocess", "package", "module"],
                         ids=["all-bound", "sysconfig", "subprocess", "package", "module"])
def test_h6_four_source_bundle_rejects_each_changed_public_source(tmp_path, changed):
    """Synthetic source bytes test all four binder reads without executing their module bodies."""
    library, site = tmp_path / "python/Lib", tmp_path / "site"
    library.mkdir(parents=True)
    (site / "distro").mkdir(parents=True)
    paths = {"sysconfig": library / "sysconfig.py", "subprocess": library / "subprocess.py",
             "package": site / "distro/__init__.py", "module": site / "distro/distro.py"}
    bindings = {}
    for name, path in paths.items():
        raw = f'raise AssertionError("synthetic_{name}_source_must_not_execute")\n'.encode()
        path.write_bytes(raw)
        bindings[name] = (len(raw), hashlib.sha256(raw).hexdigest())
    if changed is not None:
        paths[changed].write_bytes(paths[changed].read_bytes().replace(b"AssertionError", b"AttributeError"))
    gates, physical_paths = [], []
    wrapper = object()  # Identity was tested separately; this binder control stubs that gate explicitly.

    def runtime_gate(*args):
        gates.append("runtime")
        return invoker._nt312_profile_runtime(*args, platform=NT312)

    def isfile_gate(actual):
        assert actual is wrapper
        gates.append("isfile")

    def public_path(path, *, windows):
        assert windows is True
        physical_paths.append(path)

    def synthetic_import(name, *args, **kwargs):
        if name == "struct":
            return SimpleNamespace(calcsize=lambda format: 8 if format == "P" else pytest.fail("unexpected_format"))
        if name == "importlib.machinery":
            return SimpleNamespace(EXTENSION_SUFFIXES=[".cp312-win_amd64.pyd", ".pyd"])
        raise AssertionError("unexpected_source_binder_import")

    namespace = {**vars(invoker), "__builtins__": {**vars(builtins), "__import__": synthetic_import},
                 "sys": SimpleNamespace(version_info=(3, 12, 9), implementation=SimpleNamespace(cache_tag="cpython-312"),
                                        platform="win32", flags=SimpleNamespace(optimize=0), base_prefix=str(library.parent)),
                 "_nt312_profile_runtime": runtime_gate, "_nt312_isfile_identity": isfile_gate,
                 "_i18n_physical_path": public_path,
                 "_NT312_SYSCONFIG_SOURCES": {name + ".py": bindings[name] for name in ("sysconfig", "subprocess")},
                 "_NT312_DISTRO_SOURCES": {name: (paths[name].name, *bindings[name]) for name in ("package", "module")}}
    bind = FunctionType(invoker._nt312_profile_sources.__code__, namespace)
    if changed is None:
        result = bind(site, wrapper)
        assert result["abi"] == "cp312" and set(result) == {"abi", "sysconfig", "subprocess", "distro"}
        assert set(result["distro"]) == {"package", "module"}
        for codes in (result["sysconfig"], result["subprocess"], *result["distro"].values()):
            assert ("<module>", 1) in codes
        assert physical_paths == [str(path) for path in paths.values()]
    else:
        with pytest.raises(RuntimeError, match="sysconfig_observer_source_identity_drift"):
            bind(site, wrapper)
        index = list(paths).index(changed)
        assert physical_paths == [str(path) for path in list(paths.values())[:index + 1]]
    assert gates == ["runtime", "isfile"]


def synthetic_prepared_observer(tmp_path, cache_state, *, defect=False):
    """Exercise real completed-observer code with declared synthetic module facts.

    No real sysconfig module is replaced, and no vendor source is executed.
    Private function globals supply only the synthetic interpreter ABI needed
    to exercise the common assertion on either host Python version.
    """
    events = []
    read_fault = RuntimeError("synthetic_cache_flag_read_fault")

    class SyntheticConfig(ModuleType):
        def __getattribute__(self, name):
            if name == "_CONFIG_VARS_INITIALIZED":
                events.append("flag-read")
                if cache_state == "fault":
                    raise read_fault
            return super().__getattribute__(name)

        def __setattr__(self, name, value):
            assert name != "_CONFIG_VARS_INITIALIZED", "observer_must_not_fabricate_initialized_flag"
            return super().__setattr__(name, value)

    module = SyntheticConfig("synthetic_sysconfig")
    source = tmp_path / "synthetic_sysconfig.py"
    module.__file__ = str(source)
    module.__spec__ = SimpleNamespace(origin=str(source), loader=SimpleNamespace())
    module.__dict__.update({
        "_CONFIG_VARS_INITIALIZED": False, "_PROJECT_BASE": str(tmp_path), "_PYTHON_BUILD": False,
        "_CONFIG_VARS": {"projectbase": str(tmp_path), "srcdir": str(tmp_path),
                         "EXT_SUFFIX": ".cp312-win_amd64.pyd"},
        "events": events, "cache_state": cache_state,
        "expected_paths": {
            "stdlib": "D:\\python\\Lib", "platstdlib": "C:\\venv\\Lib",
            "purelib": "C:\\venv\\Lib\\site-packages", "platlib": "C:\\venv\\Lib\\site-packages",
            "include": "D:\\python\\Include", "platinclude": "D:\\python\\Include",
            "scripts": "C:\\venv\\Scripts", "data": "C:\\venv",
        },
    })
    fixture = '''
def get_paths(scheme):
    assert scheme == "nt"
    events.append("get-paths")
    if cache_state == "missing":
        globals().pop("_CONFIG_VARS_INITIALIZED", None)
    else:
        globals()["_CONFIG_VARS_INITIALIZED"] = {
            "true": True, "false": False, "integer": 1, "fault": False}[cache_state]
    return dict(expected_paths)
def is_python_build():
    raise AssertionError("unused_synthetic_function")
def get_config_vars():
    raise AssertionError("unused_synthetic_function")
def _expand_vars():
    raise AssertionError("unused_synthetic_function")
def _init_non_posix():
    raise AssertionError("unused_synthetic_function")
'''
    exec(compile(fixture, str(source), "exec"), module.__dict__)
    observer = object.__new__(invoker._SysconfigObservation)
    observer.h6, observer.source, observer.loader_type = True, source, SimpleNamespace
    observer.guard = invoker.Guard(tmp_path, [], [])
    observer.prefixes = {"prefix": "C:/venv", "base_prefix": "D:/python"}
    observer.codes = {(function.__code__.co_name, function.__code__.co_firstlineno): function.__code__
                      for function in vars(module).values() if type(function) is FunctionType}
    observer.source_bindings = {"sysconfig.py": (0, "a" * 64)}
    observer.data = {"configuration": {"mode": "isolated"}, "prepare_returned": False,
                     "marker_intents": {name: {"admitted": 1, "refused": 0} for name in ("Setup", "Setup.local")}}
    shadow_sys = SimpleNamespace(modules={"sysconfig": module}, implementation=SimpleNamespace(
        name="cpython", cache_tag="cpython-312"), version_info=(3, 12, 9), **observer.prefixes)
    private_builtins = dict(vars(builtins))

    def synthetic_import(name, *args, **kwargs):
        if name == "struct":
            return SimpleNamespace(calcsize=lambda format: 8 if format == "P" else pytest.fail("unexpected_format"))
        if name == "importlib.machinery":
            return SimpleNamespace(EXTENSION_SUFFIXES=[".cp312-win_amd64.pyd", ".pyd"])
        raise AssertionError("unexpected_completed_observer_import")

    private_builtins["__import__"] = synthetic_import
    namespace = {**vars(invoker), "sys": shadow_sys, "os": SimpleNamespace(environ={}),
                 "__builtins__": private_builtins}
    code = invoker._SysconfigObservation.prepared.__code__
    if defect:
        tree = ast.parse(Path(invoker.__file__).read_bytes())
        cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                   and node.name == "_SysconfigObservation")
        function = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "prepared")
        matches = [node for node in ast.walk(function) if isinstance(node, ast.Assign)
                   and len(node.targets) == 1 and isinstance(node.targets[0], ast.Subscript)
                   and isinstance(node.targets[0].slice, ast.Constant)
                   and node.targets[0].slice.value == "config_vars_initialized"]
        assert len(matches) == 1, "cache_observation_mutation_site_drift"
        matches[0].value = ast.copy_location(ast.Constant(value=True), matches[0].value)
        compiled = compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])),
                           invoker.__file__, "exec")
        code = next(value for value in compiled.co_consts if type(value) is type(code) and value.co_name == "prepared")
    completed = FunctionType(code, namespace)
    runner = SimpleNamespace(sha=lambda raw: hashlib.sha256(raw).hexdigest(),
        wire=lambda value: json.dumps(value, sort_keys=True, separators=(",", ":")).encode())
    facts = {"manifest_sha256": "b" * 64, "sources": {invoker.ENTRY: "c" * 64}}
    prepared = {"identity": runner.sha(runner.wire(facts)), "facts": facts, "cases": [], "requests": []}
    startup = {"manifest_sha256": "b" * 64, "invoker_sha256": "c" * 64}
    return observer, module, events, read_fault, lambda: completed(observer, prepared, runner, tmp_path, startup)


def assert_completed_cache_delivery(tmp_path, cache_state, *, defect=False):
    observer, module, events, read_fault, complete = synthetic_prepared_observer(tmp_path, cache_state, defect=defect)
    caught = None
    try:
        complete()
    except RuntimeError as error:
        caught = error
    if cache_state == "true":
        assert caught is None and observer.data["prepare_returned"] is True
        assert observer.data["sysconfig_facts"]["config_vars_initialized"] is True
    elif cache_state == "fault":
        assert caught is read_fault and observer.data["prepare_returned"] is False
        assert "sysconfig_facts" not in observer.data
    else:
        assert isinstance(caught, RuntimeError) and str(caught) == "sysconfig_prepared_configuration_mismatch", \
            "cache_state_must_be_observed_not_fabricated"
        assert observer.data["prepare_returned"] is False
        assert observer.data["sysconfig_facts"]["config_vars_initialized"] is False
    assert events == ["get-paths", "flag-read"], "flag_must_be_observed_once_after_get_paths"
    if cache_state == "missing":
        assert "_CONFIG_VARS_INITIALIZED" not in vars(module)
    else:
        assert vars(module)["_CONFIG_VARS_INITIALIZED"] is {
            "true": True, "false": False, "integer": 1, "fault": False}[cache_state]
    assert observer.guard.violations == []


@pytest.mark.parametrize("cache_state", ["true", "false", "missing", "integer", "fault"],
                         ids=["observed-true", "false", "missing", "integer", "read-fault"])
def test_completed_observer_reads_actual_initialized_flag_after_get_paths(tmp_path, cache_state):
    """A populated cache, a missing flag or failed observation cannot be reported as initialized."""
    assert_completed_cache_delivery(tmp_path, cache_state)


def test_reinjected_fabricated_initialized_fact_fails_same_delivery_assertion(tmp_path):
    """Replacing the observed cache flag with True must fail the original cache-state oracle."""
    assert_completed_cache_delivery(tmp_path, "false")
    with pytest.raises(AssertionError, match="cache_state_must_be_observed_not_fabricated"):
        assert_completed_cache_delivery(tmp_path, "false", defect=True)


@pytest.mark.parametrize("observation_fault", [False, True], ids=["observed", "observer-fault"])
def test_h6_path_observation_keeps_original_refusal_and_ledger(tmp_path, observation_fault):
    """An additive H6 observer cannot clear a denial or replace its exact exception object."""
    guard = invoker.Guard(tmp_path, [], [])
    observer = object.__new__(invoker._SysconfigObservation)
    observer.h6, observer.guard = True, guard
    observer.data = {"observer_fault": False}
    observed, errors = [], []

    def observation(raw, operation, *, refused):
        observed.append((raw, operation, refused, tuple(guard.violations)))
        if observation_fault:
            raise RuntimeError("synthetic_observer_failure_not_disclosed")

    observer._path_observation = observation

    def original(raw, operation, *, resource_open):
        assert resource_open is False
        try:
            guard.deny("read_outside_admitted_sources")
        except PermissionError as error:
            errors.append(error)
            raise

    with pytest.raises(PermissionError) as caught:
        observer._wrap_path(original)(tmp_path, "probe")
    assert caught.value is errors[0]
    assert observed == [(tmp_path, "probe", True, ("read_outside_admitted_sources",))]
    assert guard.violations == ["read_outside_admitted_sources"] and guard.finish_status(0) == 1
    assert observer.data["observer_fault"] is observation_fault
    assert "synthetic_observer_failure" not in repr(observer.data)
