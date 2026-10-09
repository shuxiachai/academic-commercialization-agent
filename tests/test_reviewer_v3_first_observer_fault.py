"""Pure first-fault seams, outside the frozen 529-node invocation.

Synthetic observer failures and private function globals exercise the actual
catch/main code. No guard, audit hook, native source, provider, subprocess,
genuine runner preparation, nested pytest session or atexit callback is run.
"""

import ast
import builtins
from contextlib import contextmanager
import copy
from pathlib import Path
import sys
from types import FunctionType, MethodType, ModuleType, SimpleNamespace

import pytest

from evals.reviewer_comparison_v3 import test_invoker as invoker


NT312 = ("nt", "cpython", (3, 12))
CASE = "e0591d8f-bb7d-4ba6-a41a-fd62d30c87e3"
FIELD = "ff_first_observer_fault"


def configuration_values():
    return {"REVIEWER_V3_FF_CASE": CASE, "REVIEWER_V3_FF_CONTROL_SHA256": "a" * 64}


def private_function(function, **replacements):
    """Keep actual code while confining synthetic dependencies to private globals."""
    result = FunctionType(function.__code__, {**function.__globals__, **replacements},
                          function.__name__, function.__defaults__, function.__closure__)
    result.__kwdefaults__ = function.__kwdefaults__
    return result


def mutated_function(function, change):
    """Compile one altered function; never rewrite the source or execute a module."""
    tree = ast.parse(Path(invoker.__file__).read_bytes())
    matches = [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
               and node.name == function.__name__ and node.lineno == function.__code__.co_firstlineno]
    assert len(matches) == 1, "mutation_function_site_drift"
    target = copy.deepcopy(matches[0])
    change(target)
    code = compile(ast.fix_missing_locations(ast.Module(body=[target], type_ignores=[])),
                   invoker.__file__, "exec")
    namespace = dict(function.__globals__)
    exec(code, namespace)
    return namespace[function.__name__]


def test_ff_case_is_separate_and_requires_its_own_complete_binding():
    """The new diagnostic must neither alias a consumed case nor become a default."""
    assert invoker._FF_CASE == CASE
    assert CASE not in invoker._H6_CASES
    assert invoker._ff_configuration({}, platform=NT312) is None
    actual = invoker._ff_configuration(configuration_values(), platform=NT312)
    assert actual["diagnostic_binding"] == "explicit_ff"
    assert actual["mode"] == "missing-control"
    assert actual["case_id"] == CASE and actual["control_sha256"] == "a" * 64
    assert actual["policy_applicable"] is True
    assert actual["platform_validation"] == "not_evaluated"
    assert len(actual["policy_sha256"]) == 64
    assert Path(__file__).name not in {Path(path).name for path in invoker.CHECK_FILES}


@pytest.mark.parametrize("defect", [
    "missing-case", "missing-control", "case-key-lower", "control-key-lower",
    "case-upper", "old-h6", "old-h2", "digest-upper", "digest-short", "digest-type",
    "mix-h1", "mix-h2", "mix-h3", "mix-h6", "nt311", "posix312", "pypy312",
], ids=["no-case", "no-control", "case-key", "hash-key", "case-upper", "old-h6", "old-h2",
        "hash-upper", "hash-short", "hash-type", "mix-h1", "mix-h2", "mix-h3", "mix-h6",
        "nt311", "posix", "pypy"])
def test_ff_selector_rejects_partial_mixed_historical_and_wrong_runtime_inputs(defect):
    """Explicit malformed FF inputs must refuse rather than select a default or old case."""
    values, platform = configuration_values(), NT312
    case_key, control_key = invoker._FF_INPUTS
    if defect.startswith("missing-"):
        del values[case_key if defect == "missing-case" else control_key]
    elif defect.endswith("key-lower"):
        key = case_key if defect == "case-key-lower" else control_key
        values[key.lower()] = values.pop(key)
    elif defect == "case-upper":
        values[case_key] = CASE.upper()
    elif defect == "old-h6":
        values[case_key] = "8788c0ac-3e50-4e99-8a0e-3e6767ad97d0"
    elif defect == "old-h2":
        values[case_key] = "79dbf145-52ff-40ea-9988-cbd651993aea"
    elif defect.startswith("digest-"):
        values[control_key] = {"digest-upper": "A" * 64, "digest-short": "a" * 63,
                               "digest-type": 64}[defect]
    elif defect.startswith("mix-"):
        values[{"mix-h1": "REVIEWER_V3_SYSCONFIG_MODE", "mix-h2": "REVIEWER_V3_H2_CASE",
                "mix-h3": "REVIEWER_V3_H3_CASE", "mix-h6": "REVIEWER_V3_H6_CASE"}[defect]] = "untrusted"
    else:
        platform = {"nt311": ("nt", "cpython", (3, 11)), "posix312": ("posix", "cpython", (3, 12)),
                    "pypy312": ("nt", "pypy", (3, 12))}[defect]
    with pytest.raises(RuntimeError, match="ff_configuration_binding_invalid"):
        invoker._ff_configuration(values, platform=platform)


def test_first_fault_starts_unobserved_with_an_exact_builtin_claim():
    """An unused capture slot must not be confused with a failed or successful observation."""
    data = {}
    slot = invoker._FirstObserverFault(data)
    assert type(slot._claim) is dict
    assert data[FIELD] == {"status": "not_observed", "first": None}


@pytest.mark.parametrize("binding", ["explicit_ff", "explicit_h6", "explicit_h3"], ids=["ff", "h6", "h3"])
def test_real_constructors_keep_ff_fields_and_schema_out_of_legacy_payloads(tmp_path, binding):
    """Only the new case may add fault/outcome fields; legacy sidecar schemas stay distinct."""
    def synthetic_code():
        raise AssertionError("synthetic_reference_must_not_execute")

    configuration = {"diagnostic_binding": binding, "case_id": {
        "explicit_ff": CASE, "explicit_h6": "8788c0ac-3e50-4e99-8a0e-3e6767ad97d0",
        "explicit_h3": "10c852e8-dcf8-4f9e-b162-79460ab6e48f"}[binding], "mode": "missing-control"}
    nt312 = binding != "explicit_h3"
    references = {"sysconfig": {("is_python_build", 1): synthetic_code.__code__},
        "subprocess": {("_execute_child", 1438 if nt312 else 1436): synthetic_code.__code__},
        "distro": {"module": {("<module>", 1): synthetic_code.__code__,
                               ("__init__", 667): synthetic_code.__code__}}}
    hooks = []
    shadow_sys = SimpleNamespace(**{name: str(tmp_path) for name in (
        "prefix", "base_prefix", "exec_prefix", "base_exec_prefix", "executable")},
        modules={}, addaudithook=hooks.append)
    guard = invoker.Guard(tmp_path, [], [])
    observer = object.__new__(invoker._SysconfigObservation)
    private_function(invoker._SysconfigObservation.__init__, sys=shadow_sys,
        subprocess=SimpleNamespace(Popen=SimpleNamespace(_execute_child=synthetic_code),
            __file__=str(tmp_path / "Lib/subprocess.py")),
        os=SimpleNamespace(path=SimpleNamespace(isfile=synthetic_code)),
        _nt312_isfile_identity=lambda wrapper: synthetic_code.__code__,
        _sysconfig_reference_codes=lambda path, *args: references[path.stem])(
            observer, guard, tmp_path, "synthetic-script", configuration,
            profile_sources=references if nt312 else None, guarded_isfile=synthetic_code)
    assert len(hooks) == 1 and hooks[0].__self__ is observer
    assert observer.data["schema"] == ("reviewer-v3-first-observer-fault-observation-v1"
        if binding == "explicit_ff" else "reviewer-v3-sysconfig-observation-v1")
    assert observer.nt312 is nt312
    assert observer.h6 is (binding == "explicit_h6")
    if binding == "explicit_ff":
        assert observer.data["ff_prepare_outcome"] == "not_reached"
        assert observer.data[FIELD] == {"status": "not_observed", "first": None}
    else:
        assert FIELD not in observer.data and "ff_prepare_outcome" not in observer.data
        assert observer.first_fault is None

    directories = {"UNIXCONFDIR": tmp_path / "etc", "UNIXUSRLIBDIR": tmp_path / "usr-lib"}
    for directory in directories.values():
        directory.mkdir()
    profile = object.__new__(invoker._DistroProfileObservation)
    private_function(invoker._DistroProfileObservation.__init__, sys=shadow_sys,
        os=SimpleNamespace(path=SimpleNamespace(isfile=synthetic_code),
            environ={} if binding == "explicit_h3" else {key: str(path) for key, path in directories.items()}),
        _distro_profile_dirs=lambda paths: directories,
        _nt312_isfile_identity=lambda wrapper: synthetic_code.__code__,
        _no_owned_links=lambda *args: None, _no_discovery_links=lambda *args, **kwargs: None,
        _i18n_physical_path=lambda *args, **kwargs: None,
        _sysconfig_reference_codes=lambda *args: references["distro"]["module"])(
            profile, guard, tmp_path, {}, tmp_path / "site", configuration,
            profile_sources=references if nt312 else None, guarded_isfile=synthetic_code,
            first_fault=observer.first_fault)
    assert profile.data["schema"] == {"explicit_ff": "ff-distro-profile-v1",
        "explicit_h6": "h6-distro-profile-v1", "explicit_h3": "h3-distro-profile-v1"}[binding]
    assert FIELD not in profile.data and "ff_prepare_outcome" not in profile.data
    assert profile.first_fault is observer.first_fault


@pytest.mark.parametrize("exception,label", [
    (AttributeError, "attribute_error"), (TypeError, "type_error"), (KeyError, "key_error"),
    (IndexError, "index_error"), (ValueError, "value_error"), (RuntimeError, "runtime_error"),
    (RecursionError, "recursion_error"), (PermissionError, "permission_error"), (OSError, "os_error"),
    (MemoryError, "memory_error"), (ImportError, "import_error"), (NameError, "name_error"),
    (SystemExit, "system_exit"), (KeyboardInterrupt, "keyboard_interrupt"), (Exception, "other"),
], ids=["attribute", "type", "key", "index", "value", "runtime", "recursion", "permission",
        "os", "memory", "import", "name", "exit", "interrupt", "other"])
def test_exact_builtin_exception_classes_deliver_only_the_fixed_enum(exception, label):
    """Subclass relationships must not collapse distinct built-in fault classifications."""
    data = {}
    invoker._FirstObserverFault(data).capture("sysconfig_path", "prepare", exception("private-detail"))
    assert data[FIELD] == {"status": "captured", "first": {
        "component": "sysconfig_path", "phase": "prepare", "exception": label}}


@pytest.mark.parametrize("phase", ["guard_registration", "dependency_startup", "prepare", "prepare_scope_exit", "pytest_import",
    "distro_import", "pytest_main", "receipt_finalization", "shutdown"],
    ids=["guard", "dependency", "prepare", "scope-exit", "pytest-import", "distro", "pytest-main", "receipt", "shutdown"])
def test_capture_admits_only_known_phase_labels_without_normalization(phase):
    """Known observation phases must survive delivery exactly as observed."""
    data = {}
    invoker._FirstObserverFault(data).capture("distro_probe", phase, ValueError("private"))
    assert data[FIELD] == {"status": "captured", "first": {
        "component": "distro_probe", "phase": phase, "exception": "value_error"}}


def test_record_owner_must_be_an_exact_builtin_dictionary():
    """A caller mapping with user code must not enter the first-fault publication path."""
    class DictionarySubclass(dict):
        def __setitem__(self, key, value):
            raise AssertionError("custom_mapping_must_not_execute")

    with pytest.raises(TypeError, match="ff_builtin_record_owner_required"):
        invoker._FirstObserverFault(DictionarySubclass())


class OpaqueFailureType(type):
    def __getattribute__(cls, name):
        if name in {"__name__", "__qualname__", "__module__"}:
            raise AssertionError("private_exception_type_metadata_read")
        return super().__getattribute__(name)


class OpaqueFailure(ValueError, metaclass=OpaqueFailureType):
    def __getattribute__(self, name):
        if name in {"args", "__traceback__", "__class__", "__dict__"}:
            raise AssertionError("private_exception_attribute_read")
        return super().__getattribute__(name)

    def __str__(self):
        raise AssertionError("private_exception_string_read")

    def __repr__(self):
        raise AssertionError("private_exception_repr_read")


def test_unknown_subclass_is_other_without_reading_exception_details():
    """Even a ValueError subclass must not disclose text, arguments, traceback or class names."""
    data = {}
    invoker._FirstObserverFault(data).capture("sysconfig_path", "prepare", OpaqueFailure("private"))
    assert data[FIELD] == {"status": "captured", "first": {
        "component": "sysconfig_path", "phase": "prepare", "exception": "other"}}


@pytest.mark.parametrize("component,phase", [
    ("unknown", "prepare"), (None, "prepare"), ("sysconfig_path", "unknown"), ("sysconfig_path", None),
], ids=["bad-component", "component-type", "bad-phase", "phase-type"])
def test_first_invalid_capture_stays_unavailable_after_a_valid_later_fault(component, phase):
    """Failed first metadata admission must consume ownership, not allow later repair."""
    data = {}
    slot = invoker._FirstObserverFault(data)
    slot.capture(component, phase, ValueError("private-first"))
    assert data[FIELD] == {"status": "unavailable", "first": None}
    slot.capture("distro_probe", "prepare", RuntimeError("private-later"))
    assert data[FIELD] == {"status": "unavailable", "first": None}


def synthetic_observers(tmp_path, *, phase="prepare", enabled=True):
    """Bare state isolates the actual two catches from constructor/global I/O setup."""
    guard = invoker.Guard(tmp_path, [], [])
    observer = object.__new__(invoker._SysconfigObservation)
    observer.guard, observer.phase, observer.watch_markers = guard, phase, False
    observer.invoker_filename = invoker.__file__
    observer.h6 = observer.nt312 = False
    observer.build_code, observer.isfile_code = object(), object()
    observer.data = {"observer_fault": False, "refusal_witnesses": [], "saturated": False}
    profile = object.__new__(invoker._DistroProfileObservation)
    profile.guard, profile.data = guard, {"observer_fault": False}
    if enabled:
        slot = invoker._FirstObserverFault(observer.data)
        observer.first_fault = profile.first_fault = slot
    observer.h3_profile = profile
    return observer, profile


def exercise_catch(tmp_path, component, *, refused=False, phase="prepare", enabled=True,
                   omitted_capture=False, failed_record=False):
    observer, profile = synthetic_observers(tmp_path, phase=phase, enabled=enabled)
    original_error, admitted = [], object()
    fault = OpaqueFailure("private-observer-detail")

    def broken(*args, **kwargs):
        raise fault

    if failed_record:
        observer.first_fault.capture = MethodType(private_function(
            invoker._FirstObserverFault.capture, _ff_fault_record=broken), observer.first_fault)

    if component == "sysconfig_path":
        observer._path_observation = broken
        if omitted_capture:
            observer._observe_path_safely = MethodType(
                mutated_function(invoker._SysconfigObservation._observe_path_safely, remove_capture), observer)
    else:
        module = ModuleType("synthetic_distro")
        function = invoker._DistroProfileObservation.record_probe
        if omitted_capture:
            function = mutated_function(function, remove_capture)
        profile.record_probe = MethodType(private_function(function,
            sys=SimpleNamespace(modules={"distro.distro": module}, _getframe=broken)), profile)

    def original(*args, **kwargs):
        if refused:
            try:
                observer.guard.deny("read_outside_admitted_sources")
            except PermissionError as error:
                original_error.append(error)
                raise
        return admitted

    if refused:
        with pytest.raises(PermissionError) as caught:
            observer._wrap_path(original)("synthetic-path", "probe")
        assert caught.value is original_error[0], "original_permission_identity_preserved"
    else:
        assert observer._wrap_path(original)("synthetic-path", "probe") is admitted, "admitted_object_preserved"
    assert observer.guard.violations == (["read_outside_admitted_sources"] if refused else [])
    assert observer.guard.finish_status(0) == int(refused)
    assert observer.data["observer_fault"] is True, "original_sticky_fault_preserved"
    if component == "distro_probe":
        assert profile.data["observer_fault"] is True
    return observer, profile


def assert_capture_delivery(observer, component, phase="prepare"):
    assert observer.data[FIELD] == {"status": "captured", "first": {
        "component": component, "phase": phase, "exception": "other"}}, "first_catch_metadata_delivered"


@pytest.mark.parametrize("component", ["sysconfig_path", "distro_probe"], ids=["sysconfig", "distro"])
@pytest.mark.parametrize("refused", [False, True], ids=["return", "refusal"])
@pytest.mark.parametrize("phase", ["prepare", "unknown"], ids=["captured", "unavailable"])
def test_actual_catches_preserve_original_result_ledger_and_sticky_fault(tmp_path, component, refused, phase):
    """Neither a successful nor a failed metadata capture may replace the original Guard result."""
    observer, _profile = exercise_catch(tmp_path, component, refused=refused, phase=phase)
    if phase == "prepare":
        assert_capture_delivery(observer, component)
    else:
        assert observer.data[FIELD] == {"status": "unavailable", "first": None}
        observer.first_fault.capture("sysconfig_path", "prepare", RuntimeError("later"))
        assert observer.data[FIELD] == {"status": "unavailable", "first": None}


@pytest.mark.parametrize("component", ["sysconfig_path", "distro_probe"], ids=["sysconfig", "distro"])
def test_legacy_catches_never_add_first_fault_fields(tmp_path, component):
    """Additive FF capture must leave non-FF observer payloads without new keys."""
    observer, profile = exercise_catch(tmp_path, component, refused=True, enabled=False)
    assert FIELD not in observer.data and FIELD not in profile.data
    assert "ff_prepare_outcome" not in observer.data


@pytest.mark.parametrize("component", ["sysconfig_path", "distro_probe"], ids=["sysconfig", "distro"])
@pytest.mark.parametrize("refused", [False, True], ids=["return", "refusal"])
def test_metadata_builder_failure_preserves_result_and_cannot_be_repaired(tmp_path, component, refused):
    """A record-builder exception must leave the first slot unavailable while preserving Guard truth."""
    observer, _profile = exercise_catch(tmp_path, component, refused=refused, failed_record=True)
    assert observer.data[FIELD] == {"status": "unavailable", "first": None}
    # Restoring the genuine builder cannot give a later event another claim.
    observer.first_fault.capture = MethodType(invoker._FirstObserverFault.capture, observer.first_fault)
    observer.first_fault.capture("sysconfig_path", "prepare", RuntimeError("later"))
    assert observer.data[FIELD] == {"status": "unavailable", "first": None}


def test_reentrant_capture_cannot_claim_during_first_record_construction():
    """First ownership must be consumed before record construction can admit another arrival."""
    data, calls = {}, []
    slot = invoker._FirstObserverFault(data)

    def nested_record(component, phase, error):
        calls.append(component)
        assert data[FIELD] == {"status": "unavailable", "first": None}
        slot.capture("distro_probe", "shutdown", ValueError("nested-private"))
        return invoker._ff_fault_record(component, phase, error)

    slot.capture = MethodType(private_function(invoker._FirstObserverFault.capture,
        _ff_fault_record=nested_record), slot)
    slot.capture("sysconfig_path", "prepare", RuntimeError("original-private"))
    assert calls == ["sysconfig_path"], "single_record_construction"
    assert data[FIELD] == {"status": "captured", "first": {
        "component": "sysconfig_path", "phase": "prepare", "exception": "runtime_error"}}


@pytest.mark.parametrize("first", ["sysconfig_path", "distro_probe"], ids=["sysconfig-first", "distro-first"])
def test_shared_slot_keeps_first_capture_across_both_actual_catches(tmp_path, first):
    """A propagated or later component failure cannot replace the first recorded component."""
    observer, profile = exercise_catch(tmp_path, first)
    assert observer.first_fault is profile.first_fault
    second = "distro_probe" if first == "sysconfig_path" else "sysconfig_path"
    def later_failure(*args, **kwargs):
        raise RuntimeError("later-private")

    observer.phase = "shutdown"
    if second == "sysconfig_path":
        observer._path_observation = later_failure
    else:
        observer._path_observation = MethodType(invoker._SysconfigObservation._path_observation, observer)
        profile.record_probe = MethodType(private_function(invoker._DistroProfileObservation.record_probe,
            sys=SimpleNamespace(modules={"distro.distro": ModuleType("synthetic_distro")},
                                _getframe=later_failure)), profile)
    admitted = object()
    assert observer._wrap_path(lambda *args, **kwargs: admitted)("synthetic-path", "probe") is admitted
    assert_capture_delivery(observer, first)


def remove_capture(function):
    statements = [node for node in ast.walk(function) if isinstance(node, ast.Expr)
                  and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                  and node.value.func.id == "_capture_first_observer_fault"]
    assert len(statements) == 1, "capture_mutation_site_drift"
    target = statements[0]
    for node in ast.walk(function):
        for _name, value in ast.iter_fields(node):
            if isinstance(value, list) and target in value:
                value[value.index(target)] = ast.copy_location(ast.Pass(), target)
                return
    raise AssertionError("capture_mutation_parent_missing")


@pytest.mark.parametrize("component", ["sysconfig_path", "distro_probe"], ids=["sysconfig", "distro"])
def test_reinjected_missing_catch_capture_fails_same_delivery_assertion(tmp_path, component):
    """Removing either catch's recording must fail metadata delivery, not just a mock call count."""
    positive, _profile = exercise_catch(tmp_path, component)
    assert_capture_delivery(positive, component)
    damaged, _profile = exercise_catch(tmp_path, component, omitted_capture=True)
    with pytest.raises(AssertionError, match="first_catch_metadata_delivered"):
        assert_capture_delivery(damaged, component)


def assert_first_record_kept(*, overwrite=False):
    data = {}
    slot = invoker._FirstObserverFault(data)
    if overwrite:
        def change(function):
            calls = [node for node in ast.walk(function) if isinstance(node, ast.Call)
                     and isinstance(node.func, ast.Attribute) and node.func.attr == "pop"]
            assert len(calls) == 1, "first_claim_mutation_site_drift"
            calls[0].func.attr = "get"

        slot.capture = MethodType(mutated_function(invoker._FirstObserverFault.capture, change), slot)
    slot.capture("sysconfig_path", "prepare", OpaqueFailure("first"))
    slot.capture("distro_probe", "shutdown", RuntimeError("later"))
    assert data[FIELD] == {"status": "captured", "first": {
        "component": "sysconfig_path", "phase": "prepare", "exception": "other"}}, "first_record_not_overwritten"


def test_reinjected_reusable_claim_fails_same_first_record_assertion():
    """Changing the one-use pop into get must expose the later overwrite to the original oracle."""
    assert_first_record_kept()
    with pytest.raises(AssertionError, match="first_record_not_overwritten"):
        assert_first_record_kept(overwrite=True)


class ForbiddenBoundary(Exception):
    pass


def main_observation(tmp_path, outcome, *, remove_stop=False, reject_source=False, isolate_normal_profile=True):
    """Use actual main sequencing with every setup/global/provider seam isolated."""
    calls, observers, profiles, imports = [], [], [], []
    environment = configuration_values()
    control = invoker._ff_configuration(environment, platform=NT312)
    original_exception = PermissionError("synthetic-denial") if outcome == "permission_error" else ValueError("synthetic-prepare-failure")
    shadow_sys = SimpleNamespace(**vars(sys))
    shadow_sys.path = list(sys.path)
    shadow_os = SimpleNamespace(**vars(invoker.os))
    shadow_os.environ = environment

    def forbidden(name):
        def boundary(*args, **kwargs):
            calls.append(name)
            raise ForbiddenBoundary(name)
        return boundary

    def make_observation(guard, owned, script, configuration, **kwargs):
        observer = SimpleNamespace(guard=guard, data={"observer_fault": False,
            "prepare_returned": False, "ff_prepare_outcome": "not_reached", "pytest_started": False,
            "receipt_written": False, "marker_intents": {
                "Setup": {"admitted": 0, "refused": 0}, "Setup.local": {"admitted": 0, "refused": 0}}})
        observer.first_fault = invoker._FirstObserverFault(observer.data)
        observer.finish = forbidden("finish")
        observer.prepared = forbidden("prepared")
        observer.require_prepare_ledger = lambda stage: calls.append("ledger-" + stage)
        observer.window = lambda stage: calls.append("window-" + stage)
        observers.append(observer)
        return observer

    def make_profile(guard, owned, paths, site, configuration, **kwargs):
        profile = SimpleNamespace(data={"observer_fault": False}, profile="missing-project",
            first_fault=kwargs.get("first_fault"), require_cold=lambda stage: calls.append("cold-" + stage),
            finish=forbidden("profile-finish"), verify_import=forbidden("verify-import"))
        profiles.append(profile)
        return profile

    @contextmanager
    def scope(*args):
        calls.append("scope-enter")
        try:
            if outcome == "not_reached":
                raise original_exception
            yield
        finally:
            calls.append("scope-exit")

    def prepare():
        calls.append("prepare")
        if outcome != "returned":
            if outcome == "permission_error":
                observers[0].guard.violations.append("read_outside_admitted_sources")
            raise original_exception
        return {"synthetic": "returned-without-validation"}

    def sources(*args):
        calls.append("source-binding")
        if reject_source:
            raise original_exception
        return {"synthetic": "no-source-executed"}

    @contextmanager
    def normal_profile(owned, stdlib_paths):
        # This fixture selects NT312 and replaces every process-wide setup
        # seam. Importing the real helper here would select the pytest HOST
        # platform instead, where sysconfig is already warm on Linux.
        assert owned == tmp_path and stdlib_paths == invoker._STDLIB_PATHS
        assert control["diagnostic_binding"] == "explicit_ff" and control["policy_applicable"]
        calls.append("normal-profile-enter")
        try:
            yield {"applicable": False}
        finally:
            calls.append("normal-profile-exit")

    def dependencies(*args):
        calls.append("normal-dependencies")
        return {}, None

    def import_only(name, globals=None, locals=None, fromlist=(), level=0):
        if (isolate_normal_profile and name == "evals.reviewer_comparison_v3.linux_sysconfig_profile"
                and fromlist == ("install",) and level == 0):
            calls.append("normal-profile-import")
            return SimpleNamespace(install=normal_profile)
        if name == "evals.reviewer_comparison_v3" and fromlist == ("runner",):
            return SimpleNamespace(runner=SimpleNamespace(prepare=prepare))
        if name == "pytest":
            imports.append(name)
            raise ForbiddenBoundary("pytest-import")
        return builtins.__import__(name, globals, locals, fromlist, level)

    main = invoker.main
    if remove_stop:
        def change(function):
            targets = [node for node in ast.walk(function) if isinstance(node, ast.Raise)
                       and isinstance(node.exc, ast.Call) and node.exc.args
                       and isinstance(node.exc.args[0], ast.Constant)
                       and node.exc.args[0].value == "ff_diagnostic_stop_before_pytest"]
            assert len(targets) == 1, "ff_stop_mutation_site_drift"
            for node in ast.walk(function):
                for _name, value in ast.iter_fields(node):
                    if isinstance(value, list) and targets[0] in value:
                        value[value.index(targets[0])] = ast.copy_location(ast.Pass(), targets[0])
                        return
            raise AssertionError("ff_stop_mutation_parent_missing")
        main = mutated_function(main, change)
    isolated = private_function(main, os=shadow_os, sys=shadow_sys,
        __builtins__={**vars(builtins), "__import__": import_only},
        _fixed_invocation=lambda *args: True,
        _ff_configuration=lambda original: invoker._ff_configuration(original, platform=NT312),
        _h6_configuration=lambda *args: None, _h2_configuration=lambda *args: None,
        _h3_configuration=lambda *args: None,
        _verified_environment=lambda: (tmp_path, tmp_path, "0" * 64),
        _owned_profile=lambda: (tmp_path, {"work": tmp_path, "tmp": tmp_path}),
        _test_environment=lambda *args: None, _preload_canonical=lambda: {},
        _cold_script_and_names=lambda: ("synthetic-not-executed", set()),
        _install_io_guard=lambda *args: (object(), object()), _install_cold_envelope=lambda *args: None,
        atexit=SimpleNamespace(register=lambda *args: None),
        _nt312_profile_sources=sources,
        _SysconfigObservation=make_observation, _DistroProfileObservation=make_profile,
        _normal_dependency_startup=dependencies, _normal_model_shims=lambda *args: {},
        _sysconfig_project=lambda owned: owned / "synthetic-project", _normal_sysconfig_scope=scope,
        _sysconfig_environment_absent=lambda *args: True)
    caught = None
    try:
        isolated()
    except BaseException as error:  # Keep exact synthetic result for the common oracle below.
        caught = error
    return SimpleNamespace(calls=calls, observers=observers, profiles=profiles, imports=imports,
        caught=caught, original=original_exception, configuration=control, environment=environment)


def assert_main_stopped(result, outcome, tmp_path):
    assert not set(result.calls).intersection({"prepared", "finish", "profile-finish", "verify-import"}), \
        "ff_stop_before_completed_observation"
    assert result.imports == [], "ff_stop_before_pytest_import"
    assert [call for call in result.calls if call.startswith("normal-")] == [
        "normal-profile-import", "normal-profile-enter", "normal-dependencies", "normal-profile-exit"], \
        "synthetic_nt_profile_scope_must_surround_startup"
    assert result.calls.count("prepare") == int(outcome != "not_reached")
    assert result.calls.count("scope-exit") == 1
    assert result.calls[0] == "source-binding", "source_binding_before_prepare"
    assert result.calls.index("normal-profile-enter") < result.calls.index("scope-enter")
    assert result.calls.index("window-prepare_scope_exit") < result.calls.index("normal-profile-exit"), \
        "normal_profile_must_exit_after_prepare_scope"
    observer = result.observers[0]
    assert observer.first_fault is result.profiles[0].first_fault
    assert observer.data["ff_prepare_outcome"] == outcome, "honest_prepare_outcome"
    assert observer.data["prepare_returned"] is (outcome == "returned"), "actual_return_not_validation"
    assert observer.data["prepare_scope_exited"] is True
    assert observer.data["env_absent_after_prepare_exit"] is True
    assert observer.phase == "prepare_scope_exit", "late_fault_cannot_impersonate_prepare"
    assert observer.data["pytest_started"] is False and observer.data["receipt_written"] is False
    assert not (tmp_path / "receipt.json").exists()
    assert result.environment == configuration_values()
    if outcome == "returned":
        assert type(result.caught) is RuntimeError
        assert str(result.caught) == "ff_diagnostic_stop_before_pytest"
    else:
        assert result.caught is result.original, "original_prepare_exception_preserved"
    assert observer.guard.violations == (["read_outside_admitted_sources"] if outcome == "permission_error" else [])


@pytest.mark.parametrize("outcome", ["returned", "permission_error", "other_failure", "not_reached"],
                         ids=["return", "refusal", "other", "not-reached"])
def test_actual_main_stops_all_prepare_outcomes_before_completed_observation_or_pytest(tmp_path, outcome):
    """Real main must report what prepare did and stop before completed validation or pytest import."""
    assert_main_stopped(main_observation(tmp_path, outcome), outcome, tmp_path)


def test_actual_ff_main_requires_nt312_source_binding_before_observers_or_prepare(tmp_path):
    """Selecting FF must not bypass the existing exact source/ABI binding gate."""
    result = main_observation(tmp_path, "returned", reject_source=True)
    assert result.caught is result.original
    assert result.calls == ["source-binding"]
    assert result.observers == result.profiles == result.imports == []
    assert not (tmp_path / "bootstrap.json").exists()


def test_reinjected_missing_main_stop_fails_same_pre_pytest_boundary_assertion(tmp_path):
    """Deleting the actual stop must fail the original sequencing oracle without running pytest."""
    positive = tmp_path / "positive"
    positive.mkdir()
    assert_main_stopped(main_observation(positive, "returned"), "returned", positive)
    negative = tmp_path / "negative"
    negative.mkdir()
    with pytest.raises(AssertionError, match="ff_stop_before_completed_observation"):
        assert_main_stopped(main_observation(negative, "returned", remove_stop=True), "returned", negative)


def test_reinjected_unisolated_profile_fails_the_same_synthetic_scope_oracle(tmp_path):
    """Removing the new import boundary must fail even on a non-Linux pytest host."""
    # A warmed Linux host refuses the leaked real helper; Windows yields its
    # real nonapplicable profile. Neither supplies the declared fixture scope.
    # Cache warmth is not assumed: the same oracle detects the missing mock
    # even when the host has not imported sysconfig yet.
    result = main_observation(tmp_path, "returned", isolate_normal_profile=False)
    with pytest.raises(AssertionError, match="synthetic_nt_profile_scope_must_surround_startup"):
        assert_main_stopped(result, "returned", tmp_path)
