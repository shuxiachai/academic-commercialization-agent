"""H5 synthetic predicate boundaries; no invoker startup or framework import.

Only explicitly named stdlib-only definitions are loaded from the real invoker.
The Windows CP312 native comparison is reported separately in suite properties;
every other runtime executes no-install assertions instead of skipping the test.
"""

import ast
import copy
import inspect
import ntpath
import operator
import os
from pathlib import Path
import stat
import sys
import types
from types import SimpleNamespace

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "evals/reviewer_comparison_v3/test_invoker.py"
CORE_NAMES = {
    "Guard", "_key", "_inside", "_no_discovery_links", "_no_owned_links",
    "_io_callbacks", "_install_io_guard",
}
ADAPTER_NAMES = {
    "_nt312_path_argument", "_nt312_path_predicate", "_install_nt312_path_guard",
}


def load_definitions(defect=None):
    """Load selected real definitions, never the source module's startup body."""
    with SOURCE.open("rb") as handle:
        raw = handle.read(131073)
    assert len(raw) <= 131072, "invoker_source_cap"
    tree = ast.parse(raw, filename=str(SOURCE))
    names = CORE_NAMES | ADAPTER_NAMES
    selected = [copy.deepcopy(node) for node in tree.body
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    assert {node.name for node in selected} == names, "selected_definition_set_drift"
    assert len(selected) == len(names), "duplicate_selected_definition"
    if defect == "mro_membership":
        argument = next(node for node in selected if node.name == "_nt312_path_argument")

        class MembershipDefect(ast.NodeTransformer):
            replacements = 0

            def visit_Call(self, node):
                self.generic_visit(node)
                if not (isinstance(node.func, ast.Name) and node.func.id == "any"
                        and len(node.args) == 1 and not node.keywords
                        and isinstance(node.args[0], ast.GeneratorExp)):
                    return node
                generator = node.args[0]
                comparison = generator.elt
                if not (isinstance(comparison, ast.Compare) and len(comparison.ops) == 1
                        and isinstance(comparison.ops[0], ast.Is)
                        and isinstance(comparison.left, ast.Name) and comparison.left.id == "base"
                        and len(comparison.comparators) == 1
                        and isinstance(comparison.comparators[0], ast.Name)
                        and comparison.comparators[0].id in ("str", "bytes")
                        and len(generator.generators) == 1):
                    return node
                clause = generator.generators[0]
                assert isinstance(clause.target, ast.Name) and clause.target.id == "base"
                assert isinstance(clause.iter, ast.Name) and clause.iter.id == "real_mro"
                assert clause.ifs == [] and clause.is_async == 0
                self.replacements += 1
                return ast.copy_location(ast.Compare(
                    left=copy.deepcopy(comparison.comparators[0]), ops=[ast.In()],
                    comparators=[ast.Name(id="real_mro", ctx=ast.Load())]), node)

        mutator = MembershipDefect()
        mutator.visit(argument)
        assert mutator.replacements == 3, "mutation_mro_identity_sites_drift"
    elif defect is not None:
        predicate = next(node for node in selected if node.name == "_nt312_path_predicate")
        checks = [node for node in predicate.body if isinstance(node, ast.Expr)
                  and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                  and node.value.func.id == "check"]
        assert len(checks) == 1, "mutation_check_site_drift"
        check = checks[0]
        index = predicate.body.index(check)
        if defect == "missing_guard":
            predicate.body.pop(index)
        elif defect == "swallowed_refusal":
            predicate.body[index] = ast.Try(
                body=[check], handlers=[ast.ExceptHandler(
                    type=ast.Name(id="PermissionError", ctx=ast.Load()), name=None,
                    body=[ast.Return(value=ast.Constant(value=False))])], orelse=[], finalbody=[])
        elif defect == "repeated_pathlike":
            returns = [node for node in predicate.body if isinstance(node, ast.Return)
                       and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name)
                       and node.value.func.id == "original"]
            assert len(returns) == 1 and len(returns[0].value.args) == 1, "mutation_native_site_drift"
            assert isinstance(returns[0].value.args[0], ast.Name)
            assert returns[0].value.args[0].id == "native", "mutation_native_argument_drift"
            returns[0].value.args[0] = ast.Name(id="path", ctx=ast.Load())
        else:
            raise AssertionError("unknown_synthetic_mutation")
    module = ast.fix_missing_locations(ast.Module(body=selected, type_ignores=[]))
    namespace = {"os": os, "sys": sys, "ntpath": ntpath, "Path": Path,
                 "stat": stat, "operator": operator, "types": types,
                 "_REAL_LSTAT": os.lstat}
    exec(compile(module, str(SOURCE), "exec", dont_inherit=True, optimize=0), namespace)
    return namespace


@pytest.fixture
def definitions():
    return load_definitions()


class CountingPath:
    """A second coercion can point at another entirely synthetic file."""

    def __init__(self, *values):
        self.values = values
        self.calls = 0

    def __fspath__(self):
        selected = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        return selected


class RaisingPath:
    """Conversion exceptions must be distinguished from policy refusals."""

    def __init__(self, exception_type):
        self.exception_type = exception_type
        self.calls = 0

    def __fspath__(self):
        self.calls += 1
        raise self.exception_type("synthetic_conversion_failure")


class CountingIndex:
    """Only a new synthetic file supplies valid descriptors to real comparisons."""

    def __init__(self, value):
        self.value = value
        self.calls = 0

    def __index__(self):
        self.calls += 1
        return self.value


class DualProtocol(CountingIndex):
    """The native integer protocol precedes fspath for non-string objects."""

    def __init__(self, value, path):
        super().__init__(value)
        self.path = path
        self.path_calls = 0

    def __fspath__(self):
        self.path_calls += 1
        return self.path


class RaisingIndex:
    """A failed integer protocol must never fall through to a path protocol."""

    def __init__(self, exception_type):
        self.exception_type = exception_type
        self.calls = 0
        self.path_calls = 0

    def __index__(self):
        self.calls += 1
        raise self.exception_type("synthetic_index_failure")

    def __fspath__(self):
        self.path_calls += 1
        raise AssertionError("index_failure_fell_through_to_fspath")


class SpoofedPath(CountingPath):
    """The C converter observes real type, not a forged instance __class__."""

    @property
    def __class__(self):
        return int


class SpoofedIndex(DualProtocol):
    """A forged string identity must not replace the real integer protocol."""

    @property
    def __class__(self):
        return str


def metaclass_path(target, value):
    """Rich equality can impersonate a builtin during tuple membership checks."""
    comparisons = []

    class EqualityTrap(type):
        def __eq__(cls, other):
            comparisons.append("str" if other is str else "bytes" if other is bytes else "other")
            return other is target

        __hash__ = type.__hash__

    class MetaclassPath(metaclass=EqualityTrap):
        def __init__(self):
            self.calls = 0
            self.equality_calls = comparisons

        def __fspath__(self):
            self.calls += 1
            return value

    return MetaclassPath()


class HostileString(str):
    """A string's contents, rather than overridden Python methods, are checked."""

    def __str__(self):
        raise AssertionError("string_override_used")

    def replace(self, *args, **kwargs):
        raise AssertionError("string_override_used")

    def encode(self, *args, **kwargs):
        raise AssertionError("string_override_used")

    def __fspath__(self):
        raise AssertionError("string_fspath_used")

    def __index__(self):
        raise AssertionError("string_index_used")


class HostileBytes(bytes):
    """Bytes conversion must not execute a subclass's alternative content hook."""

    def __bytes__(self):
        raise AssertionError("bytes_override_used")

    def decode(self, *args, **kwargs):
        raise AssertionError("bytes_override_used")

    def __fspath__(self):
        raise AssertionError("bytes_fspath_used")

    def __index__(self):
        raise AssertionError("bytes_index_used")


def outcome(function, *args, **kwargs):
    """Record only result or exception class for controlled synthetic arguments."""
    try:
        return "return", function(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - compare controlled exception classes, never their text.
        return "raise", type(exc)


def counts(value):
    return getattr(value, "calls", 0), getattr(value, "path_calls", 0)


def local_policy(namespace, owned, private=()):
    guard = namespace["Guard"](owned, [], private)
    check, _audit = namespace["_io_callbacks"](guard, owned, "unused_synthetic_script")
    return guard, check


def assert_denial_boundary(namespace, owned):
    selected = owned / "synthetic-private.bin"
    guard, check = local_policy(namespace, owned, [selected])
    calls = []

    def original(value):
        calls.append(value)
        return True

    result = outcome(namespace["_nt312_path_predicate"], str(selected), original, check)
    assert result == ("raise", PermissionError), "guard_refusal_must_propagate"
    assert calls == [], "denied_path_reached_native"
    assert guard.violations == ["real_private_path"], "refusal_ledger_must_survive"
    assert guard.finish_status(0) != 0, "refusal_cannot_finish_green"


def assert_single_pathlike_boundary(namespace, owned):
    allowed = str(owned / "synthetic-allowed.bin")
    alternate = str(owned / "synthetic-alternate.bin")
    guard, check = local_policy(namespace, owned)
    selected = CountingPath(allowed, alternate)
    calls = []

    def original(value):
        concrete = os.fspath(value)
        calls.append(concrete)
        return concrete == allowed

    result = namespace["_nt312_path_predicate"](selected, original, check)
    assert selected.calls == 1, "pathlike_must_be_evaluated_once"
    assert result is True and calls == [allowed], "checked_value_must_reach_native"
    assert guard.violations == [] and guard.finish_status(0) == 0


@pytest.mark.parametrize("kind", ["str", "bytes", "path_str", "path_bytes", "str_subclass", "bytes_subclass"])
def test_checked_concrete_value_reaches_original(definitions, tmp_path, kind):
    """The checked pathname and forwarded native value must describe identical contents."""
    text = str(tmp_path / "synthetic-present.bin")
    encoded = os.fsencode(text)
    factories = {"str": lambda: text, "bytes": lambda: encoded,
                 "path_str": lambda: CountingPath(text), "path_bytes": lambda: CountingPath(encoded),
                 "str_subclass": lambda: HostileString(text), "bytes_subclass": lambda: HostileBytes(encoded)}
    supplied = factories[kind]()
    guard, check = local_policy(definitions, tmp_path)
    delivered = []

    def original(value):
        delivered.append(value)
        assert type(value) in (str, bytes)
        return True

    assert definitions["_nt312_path_predicate"](supplied, original, check) is True
    expected = encoded if "bytes" in kind else text
    assert len(delivered) == 1 and type(delivered[0]) is type(expected) and delivered[0] == expected
    assert counts(supplied) == ((1, 0) if kind.startswith("path_") else (0, 0))
    assert guard.violations == []


def test_private_synthetic_target_is_refused_before_native(definitions, tmp_path):
    """A successful native predicate must never hide a Guard refusal."""
    assert_denial_boundary(definitions, tmp_path)


def test_pathlike_is_materialized_once(definitions, tmp_path):
    """Repeated coercion must not replace an admitted pathname after the check."""
    assert_single_pathlike_boundary(definitions, tmp_path)


@pytest.mark.parametrize("defect", ["missing_guard", "swallowed_refusal", "repeated_pathlike"])
def test_same_boundary_assertion_rejects_reinjected_defect(tmp_path, defect):
    """Each actual-source mutant must fail the same substantive assertion as the positive."""
    assertion = assert_single_pathlike_boundary if defect == "repeated_pathlike" else assert_denial_boundary
    assertion(load_definitions(), tmp_path)
    expected = "pathlike_must_be_evaluated_once" if defect == "repeated_pathlike" else "guard_refusal_must_propagate"
    with pytest.raises(AssertionError, match=expected):
        assertion(load_definitions(defect), tmp_path)


@pytest.mark.parametrize("protocol", ["path", "index"])
@pytest.mark.parametrize("exception_type", [ValueError, UnicodeError, TypeError, OverflowError,
                                          OSError, PermissionError, RuntimeError, MemoryError])
def test_conversion_exception_boundary(definitions, protocol, exception_type):
    """Only ValueError conversion failures become False; policy checks stay outside that catch."""
    selected = RaisingPath(exception_type) if protocol == "path" else RaisingIndex(exception_type)
    reached = []
    result = outcome(definitions["_nt312_path_predicate"], selected,
                     lambda value: reached.append("native"), lambda *args: reached.append("check"))
    expected = ("return", False) if issubclass(exception_type, ValueError) else ("raise", exception_type)
    assert result == expected and reached == []
    assert counts(selected) == (1, 0)


@pytest.mark.parametrize("kind", ["none", "float", "bytearray", "object", "path_int", "path_none", "index_str"])
def test_invalid_types_are_typeerror_without_check_or_native(definitions, kind):
    """An integer returned by fspath is invalid, not a newly admitted descriptor."""
    factories = {"none": lambda: None, "float": lambda: 1.5, "bytearray": lambda: bytearray(b"synthetic"),
                 "object": object, "path_int": lambda: CountingPath(0),
                 "path_none": lambda: CountingPath(None), "index_str": lambda: CountingIndex("0")}
    reached = []
    selected = factories[kind]()
    result = outcome(definitions["_nt312_path_predicate"], selected,
                     lambda value: reached.append("native"), lambda *args: reached.append("check"))
    assert result == ("raise", TypeError) and reached == []
    assert counts(selected) == ((1, 0) if kind.startswith(("path_", "index_")) else (0, 0))


@pytest.mark.parametrize("value", [-(2 ** 31), -1, 0, 1, 2 ** 31 - 1, False, True])
def test_integer_materialization_retains_existing_fd_branch(definitions, value):
    """Canonical integer descriptors retain the existing Guard bypass, without touching a real fd."""
    native, decoded = definitions["_nt312_path_argument"](value)
    assert type(native) is int and type(decoded) is int
    assert native == decoded == value


@pytest.mark.parametrize("value", [-(2 ** 31) - 1, 2 ** 31, -(2 ** 100), 2 ** 100])
def test_fd_overflow_is_not_suppressed(definitions, value):
    """Out-of-range C descriptors must remain OverflowError rather than False or path input."""
    assert outcome(definitions["_nt312_path_argument"], value) == ("raise", OverflowError)


def test_integer_protocol_precedes_fspath_without_changing_guard(definitions, tmp_path):
    """A dual-protocol object is normalized once to the established integer policy branch."""
    supplied = DualProtocol(-1, str(tmp_path / "unused-synthetic.bin"))
    guard, check = local_policy(definitions, tmp_path)
    delivered = []

    def original(value):
        delivered.append(value)
        return False

    assert definitions["_nt312_path_predicate"](supplied, original, check) is False
    assert delivered == [-1] and type(delivered[0]) is int
    assert counts(supplied) == (1, 0) and guard.violations == []
    assert outcome(guard.path, CountingIndex(-1), "probe") == ("raise", TypeError)


def test_spoofed_class_does_not_replace_actual_conversion_protocol(definitions, tmp_path):
    """The real type must determine both native argument content and the one-call protocol."""
    text = str(tmp_path / "synthetic-class-spoof.bin")
    path = SpoofedPath(text)
    index = SpoofedIndex(-1, text)
    assert isinstance(path, int) and isinstance(index, str)
    assert definitions["_nt312_path_argument"](path) == (text, text)
    assert counts(path) == (1, 0)
    native, decoded = definitions["_nt312_path_argument"](index)
    assert type(native) is int and type(decoded) is int and native == decoded == -1
    assert counts(index) == (1, 0)


def assert_metaclass_identity_boundary(namespace, owned, target):
    text = str(owned / "synthetic-metaclass.bin")
    expected = text if target is str else os.fsencode(text)
    supplied = metaclass_path(target, expected)
    guard, real_check = local_policy(namespace, owned)
    checked, delivered = [], []

    def check(value, operation):
        real_check(value, operation)
        checked.append((value, operation))

    def original(value):
        delivered.append(value)
        return True

    result = outcome(namespace["_nt312_path_predicate"], supplied, original, check)
    assert supplied.equality_calls == [], "metaclass_equality_must_not_run"
    assert supplied.calls == 1, "metaclass_path_must_be_evaluated_once"
    assert result == ("return", True), "metaclass_path_must_reach_native"
    assert checked == [(text, "probe")] and type(checked[0][0]) is str
    assert delivered == [expected] and type(delivered[0]) is target
    assert guard.violations == [] and guard.finish_status(0) == 0


@pytest.mark.parametrize("target", [str, bytes])
def test_metaclass_equality_is_ignored_and_old_membership_is_detected(definitions, tmp_path, target):
    """The same conversion/delivery assertion must reject the reviewed rich-comparison defect."""
    assert_metaclass_identity_boundary(definitions, tmp_path, target)
    with pytest.raises(AssertionError, match="metaclass_equality_must_not_run"):
        assert_metaclass_identity_boundary(load_definitions("mro_membership"), tmp_path, target)


@pytest.mark.parametrize("kind", ["str_nul", "bytes_nul", "bmp_long", "nonbmp_long"])
def test_invalid_windows_path_never_reaches_check_or_native(definitions, kind):
    """NUL and UTF-16 length rejection precede policy and native filesystem queries."""
    values = {"str_nul": "synthetic\0tail", "bytes_nul": b"synthetic\0tail",
              "bmp_long": "a" * 32768, "nonbmp_long": "\U0001f600" * 16384}
    reached = []
    assert definitions["_nt312_path_predicate"](
        values[kind], lambda value: reached.append("native"), lambda *args: reached.append("check")) is False
    assert reached == []


@pytest.mark.parametrize(
    "value", ["a" * 32767, "\U0001f600" * 16383 + "a", "synthetic\ud800"],
    ids=("bmp-32767", "nonbmp-32767", "unpaired-surrogate"),
)
def test_windows_length_uses_utf16_units_and_allows_surrogates(definitions, value):
    """The conversion boundary counts Windows wchar units, without adding an encoding prohibition."""
    native, decoded = definitions["_nt312_path_argument"](value)
    assert type(native) is str and type(decoded) is str and native == decoded == value


def test_bytes_decode_valueerror_is_false_before_policy(definitions):
    """Filesystem decoding failure has the same conversion-only False boundary on every host."""
    class ControlledCodec:
        fspath = staticmethod(os.fspath)

        @staticmethod
        def fsdecode(value):
            assert value == b"synthetic-invalid-encoding"
            raise UnicodeDecodeError("utf-8", b"\xff", 0, 1, "synthetic")

    definitions["os"] = ControlledCodec
    reached = []
    assert definitions["_nt312_path_predicate"](
        b"synthetic-invalid-encoding", lambda value: reached.append("native"),
        lambda *args: reached.append("check")) is False
    assert reached == []


@pytest.mark.parametrize("system,implementation,version", [
    ("nt", "cpython", (3, 11, 9)), ("posix", "cpython", (3, 12, 9)),
    ("nt", "pypy", (3, 12, 9)), ("nt", "cpython", (3, 13, 0)),
])
def test_other_runtime_does_not_install(definitions, system, implementation, version):
    """Non-target platforms must execute a no-mutation assertion, never silently skip it."""
    first, second = object(), object()
    target = SimpleNamespace(isfile=first, exists=second)
    definitions["ntpath"] = target
    definitions["os"] = SimpleNamespace(name=system, path=target)
    definitions["sys"] = SimpleNamespace(version_info=version, platform="win32" if system == "nt" else "linux",
                                         implementation=SimpleNamespace(name=implementation))
    assert definitions["_install_nt312_path_guard"](lambda *args: None) is None
    assert target.isfile is first and target.exists is second


def test_original_installer_calls_adapter_once_after_existing_hooks(definitions, tmp_path):
    """The new wrappers must actually be installed by the original Guard setup seam."""
    tree = ast.parse(SOURCE.read_bytes())
    install = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "_install_io_guard")
    calls = [node for node in ast.walk(install) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Name) and node.func.id == "_install_nt312_path_guard"]
    assert len(calls) == 1 and ast.unparse(calls[0].args[0]) == "path"
    old_loop = next(node for node in install.body if isinstance(node, ast.For))
    assert ast.literal_eval(old_loop.iter) == ("stat", "lstat", "access")
    assert calls[0].lineno > old_loop.end_lineno
    events = []
    shadow_os = SimpleNamespace(**vars(os))
    originals = {name: getattr(shadow_os, name) for name in ("stat", "lstat", "access")}
    definitions["os"] = shadow_os
    definitions["sys"] = SimpleNamespace(addaudithook=lambda callback: events.append("audit"))
    guard = definitions["Guard"](tmp_path, [], [tmp_path / "synthetic-install-private.bin"])

    def adapter(check):
        assert all(getattr(shadow_os, name) is not original for name, original in originals.items())
        assert outcome(check, str(tmp_path / "synthetic-install-private.bin"), "probe") == ("raise", PermissionError)
        events.append("adapter")

    definitions["_install_nt312_path_guard"] = adapter
    definitions["_install_io_guard"](guard, tmp_path, "unused_synthetic_script")
    assert events == ["audit", "adapter"]
    assert guard.violations == ["real_private_path"] and guard.finish_status(0) != 0


def native_namespace(definitions):
    """Use real builtin objects but isolate installation from process-wide os.path."""
    target = types.ModuleType("ntpath")
    target.__dict__.update(vars(ntpath))
    shadow_os = SimpleNamespace(**vars(os))
    shadow_os.path = target
    definitions["ntpath"] = target
    definitions["os"] = shadow_os
    return target


def native_comparison_cases(present, absent, descriptor):
    """Factories give both sides fresh protocol objects and only owned valid fds."""
    text, missing = str(present), str(absent)
    encoded, missing_bytes = os.fsencode(text), os.fsencode(missing)
    return [
        ("str_present", lambda: text), ("str_absent", lambda: missing),
        ("owned_directory", lambda: str(present.parent)),
        ("bytes_present", lambda: encoded), ("bytes_absent", lambda: missing_bytes),
        ("path_str", lambda: CountingPath(text)), ("path_bytes", lambda: CountingPath(encoded)),
        ("str_subclass", lambda: HostileString(text)), ("bytes_subclass", lambda: HostileBytes(encoded)),
        ("owned_fd", lambda: descriptor), ("index_fd", lambda: CountingIndex(descriptor)),
        ("dual_fd", lambda: DualProtocol(descriptor, missing)), ("invalid_fd", lambda: -1),
        ("none", lambda: None), ("float", lambda: 1.5),
        ("bytearray", lambda: bytearray(b"synthetic")), ("object", object),
        ("path_int", lambda: CountingPath(descriptor)), ("path_none", lambda: CountingPath(None)),
        ("index_str", lambda: CountingIndex("0")),
        ("path_valueerror", lambda: RaisingPath(ValueError)),
        ("index_valueerror", lambda: RaisingIndex(ValueError)),
        ("path_permission", lambda: RaisingPath(PermissionError)),
        ("index_permission", lambda: RaisingIndex(PermissionError)),
        ("path_typeerror", lambda: RaisingPath(TypeError)),
        ("index_typeerror", lambda: RaisingIndex(TypeError)),
        ("path_oserror", lambda: RaisingPath(OSError)),
        ("index_oserror", lambda: RaisingIndex(OSError)),
        ("fd_positive_overflow", lambda: 2 ** 31), ("fd_negative_overflow", lambda: -(2 ** 31) - 1),
        ("str_nul", lambda: text + "\0tail"), ("bytes_nul", lambda: encoded + b"\0tail"),
        ("bmp_long", lambda: "a" * 32768), ("nonbmp_long", lambda: "\U0001f600" * 16384),
        ("invalid_bytes", lambda: b"\xff"),
        ("path_long", lambda: CountingPath("\U0001f600" * 16384)),
        ("spoofed_path", lambda: SpoofedPath(text)),
        ("spoofed_index", lambda: SpoofedIndex(descriptor, missing)),
        ("metaclass_str", lambda: metaclass_path(str, text)),
        ("metaclass_bytes", lambda: metaclass_path(bytes, encoded)),
    ]


def test_actual_runtime_native_comparison_or_no_install(
        definitions, tmp_path, record_testsuite_property):
    """JUnit distinguishes actual NT312 native comparisons from an asserted no-install branch."""
    record_testsuite_property("h5_runtime_version", ".".join(map(str, sys.version_info[:3])))
    record_testsuite_property("h5_runtime_platform", sys.platform)
    record_testsuite_property("h5_runtime_implementation", sys.implementation.name)
    target = native_namespace(definitions)
    before = target.isfile, target.exists
    guard, check = local_policy(definitions, tmp_path)
    applicable = os.name == "nt" and sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 12)
    if not applicable:
        assert definitions["_install_nt312_path_guard"](check) is None
        assert (target.isfile, target.exists) == before
        assert guard.violations == []
        record_testsuite_property("h5_native_comparison_executed", "false")
        record_testsuite_property("h5_native_comparison_count", 0)
        record_testsuite_property("h5_unsupported_no_install_asserted", "true")
        return

    import nt  # Only the true Windows CP312 branch imports the builtin module.

    assert before == (nt._path_isfile, nt._path_exists)
    wrappers = definitions["_install_nt312_path_guard"](check)
    assert wrappers == (target.isfile, target.exists)
    assert all(isinstance(function, types.FunctionType) for function in wrappers)
    assert wrappers[0].__code__ is not wrappers[1].__code__, "predicate_frames_must_be_distinct"
    assert all(str(inspect.signature(function)) == "(path)" for function in wrappers)
    present = tmp_path / "synthetic-native-present.bin"
    present.write_bytes(b"synthetic")
    absent = tmp_path / "synthetic-native-absent.bin"
    compared = 0
    with present.open("rb") as owned_handle:
        cases = native_comparison_cases(present, absent, owned_handle.fileno())
        assert len(cases) == 40, "native_comparison_case_set_drift"
        for original, wrapped in zip(before, wrappers, strict=True):
            for label, factory in cases:
                baseline, protected = factory(), factory()
                expected = outcome(original, baseline)
                actual = outcome(wrapped, protected)
                if label in ("metaclass_str", "metaclass_bytes"):
                    assert baseline.equality_calls == protected.equality_calls == [], "native_metaclass_equality_must_not_run"
                    assert baseline.calls == protected.calls == 1, "native_metaclass_path_must_be_evaluated_once"
                if label == "owned_directory":
                    assert expected == ("return", original is before[1]), "directory_must_distinguish_predicates"
                assert actual == expected, label
                assert counts(protected) == counts(baseline), label
                compared += 1
            assert outcome(wrapped, path=str(present)) == outcome(original, path=str(present))
            compared += 1
            for args, kwargs in [((), {}), ((str(present), str(absent)), {}),
                                 ((str(present),), {"path": str(present)}),
                                 ((), {"unknown": str(present)})]:
                assert outcome(wrapped, *args, **kwargs) == outcome(original, *args, **kwargs) == ("raise", TypeError)
                compared += 1
    assert compared == 90 and guard.violations == [], "native_comparison_delivery_drift"

    private = tmp_path / "synthetic-native-private.bin"
    denied_guard, denied_check = local_policy(definitions, tmp_path, [private])
    # Use a fresh namespace so an already wrapped entry cannot be mistaken for a builtin.
    denied_definitions = load_definitions()
    native_namespace(denied_definitions)
    denied_wrappers = denied_definitions["_install_nt312_path_guard"](denied_check)
    for wrapped in denied_wrappers:
        assert outcome(wrapped, str(private)) == ("raise", PermissionError)
    assert denied_guard.violations == ["real_private_path", "real_private_path"]
    assert denied_guard.finish_status(0) != 0
    record_testsuite_property("h5_native_comparison_executed", "true")
    record_testsuite_property("h5_native_comparison_count", compared)
    record_testsuite_property("h5_unsupported_no_install_asserted", "false")


def test_target_identity_drift_fails_before_install(definitions):
    """A target-runtime identity mismatch must refuse both mutations, never partly install."""
    target = native_namespace(definitions)
    applicable = os.name == "nt" and sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 12)
    if not applicable:
        before = target.isfile, target.exists
        assert definitions["_install_nt312_path_guard"](lambda *args: None) is None
        assert (target.isfile, target.exists) == before
        return
    for drift in ("isfile", "exists", "os_path", "check"):
        selected = load_definitions()
        target = native_namespace(selected)
        if drift in ("isfile", "exists"):
            setattr(target, drift, object())
        elif drift == "os_path":
            selected["os"].path = object()
        before = target.isfile, target.exists
        with pytest.raises(RuntimeError):
            selected["_install_nt312_path_guard"](None if drift == "check" else lambda *args: None)
        assert (target.isfile, target.exists) == before
    selected = load_definitions()
    target = native_namespace(selected)
    installed = selected["_install_nt312_path_guard"](lambda *args: None)
    with pytest.raises(RuntimeError, match="nt312_path_guard_already_installed"):
        selected["_install_nt312_path_guard"](lambda *args: None)
    assert (target.isfile, target.exists) == installed
