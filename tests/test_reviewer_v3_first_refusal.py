"""Pure H2 boundary regressions; no real pytest session or provider is launched.

The generator lifecycle checks establish plugin requests and ordering only.
Actual pytest teardown/drain remains a separate, explicitly bounded validation.
"""

from pathlib import Path
import stat
from types import FunctionType, SimpleNamespace

import pytest

from evals.reviewer_comparison_v3 import test_invoker as invoker


def locator(tmp_path):
    """Exercise legacy NT311 observer logic with a synthetic reference, not native observation."""
    guard = invoker.Guard(tmp_path, [], [])
    configuration = invoker._h2_configuration({invoker._H2_INPUTS[0]: invoker._H2_CASE,
                                               invoker._H2_INPUTS[1]: "a" * 64},
                                              platform=("nt", "cpython", (3, 11)))
    def synthetic_isfile_reference(_path):
        raise AssertionError("synthetic_isfile_reference_must_not_execute")

    # Keep the complete original constructor and payload. Only its private
    # globals receive this explicit Python code reference: no host os.path or
    # production observer is replaced, and no native predicate is observed.
    constructor = invoker._FirstRefusalLocator.__init__
    namespace = {**constructor.__globals__, "os": SimpleNamespace(
        path=SimpleNamespace(isfile=synthetic_isfile_reference))}
    initialize = FunctionType(constructor.__code__, namespace, constructor.__name__,
                              constructor.__defaults__, constructor.__closure__)
    current = object.__new__(invoker._FirstRefusalLocator)
    initialize(current, guard, tmp_path, tmp_path / "site", configuration)
    return current


def test_h2_is_default_off_and_cannot_reuse_partial_or_h1_configuration():
    """A fresh H2 diagnosis cannot silently inherit a consumed H1 selector."""
    assert invoker._h2_configuration({}) is None
    inputs = {invoker._H2_INPUTS[0]: invoker._H2_CASE, invoker._H2_INPUTS[1]: "a" * 64}
    assert invoker._h2_configuration(inputs, platform=("nt", "cpython", (3, 11)))["diagnostic_binding"] == "explicit_h2"
    for invalid in ({invoker._H2_INPUTS[0]: invoker._H2_CASE}, {**inputs, invoker._SYSCONFIG_INPUTS[0]: "isolated"}):
        with pytest.raises(RuntimeError, match="h2_configuration_binding_invalid"):
            invoker._h2_configuration(invalid, platform=("nt", "cpython", (3, 11)))
    with pytest.raises(RuntimeError, match="h2_configuration_binding_invalid"):
        invoker._h2_configuration(inputs, platform=("nt", "cpython", (3, 12)))


def test_h2_observer_fault_preserves_original_permission_error_and_ledger(tmp_path, monkeypatch):
    """Frame-observation failure must not mask the Guard denial it diagnoses."""
    current = locator(tmp_path)
    observer = object.__new__(invoker._SysconfigObservation)
    observer.data = {"observer_fault": False}
    seen = []

    def broken(*args):
        raise ValueError("synthetic_private_exception_must_not_be_saved")

    monkeypatch.setattr(current, "frame_record", broken)
    monkeypatch.setattr(observer, "_path_observation", lambda raw, operation, refused: current.record_refusal(operation))

    def original(*args, **kwargs):
        try:
            current.guard.deny("read_outside_admitted_sources")
        except PermissionError as error:
            seen.append(error)
            raise

    with pytest.raises(PermissionError) as failure:
        observer._wrap_path(original)(tmp_path, "probe")
    assert failure.value is seen[0]
    assert current.guard.violations == ["read_outside_admitted_sources"]
    assert current.data["observer_fault"] is True
    assert current.data["stop_requested"] is True
    with pytest.raises(RuntimeError, match="h2_observer_fault"):
        current.require_healthy()
    assert "synthetic_private_exception" not in repr(current.data)


class DiagnosticExit(Exception):
    pass


class HookFixture:
    def __init__(self):
        self.exits = 0

    def hookimpl(self, **kwargs):
        return lambda function: function

    def exit(self, reason, returncode):
        self.exits += 1
        raise DiagnosticExit(reason)


def finish(generator):
    with pytest.raises(StopIteration):
        next(generator)


def test_collection_refusal_requests_exit_before_any_test_protocol(tmp_path):
    """Collection stop must exit at the hook boundary, before a first test."""
    current, hooks = locator(tmp_path), HookFixture()
    plugin = invoker._h2_pytest_plugin(current, hooks)
    plugin.pytest_sessionstart(SimpleNamespace(shouldstop=False))
    collection = plugin.pytest_collection(current.session)
    next(collection)
    assert current.phase == "collection"
    with pytest.raises(PermissionError):
        current.guard.deny("read_outside_admitted_sources")
    current.record_refusal("probe")
    with pytest.raises(DiagnosticExit):
        plugin.pytest_collection_finish()
    collection.close()
    assert hooks.exits == 1
    assert current.data["test_protocols_started"] == 0
    assert current.data["stop_boundary"] == "collection_finish_exit"
    assert current.data["session_finished"] is False


def test_test_refusal_sets_shouldstop_without_interrupting_current_teardown(tmp_path):
    """The stop request must allow the existing runner's teardown boundary."""
    current, hooks = locator(tmp_path), HookFixture()
    plugin = invoker._h2_pytest_plugin(current, hooks)
    session = SimpleNamespace(shouldstop=False)
    item = SimpleNamespace(nodeid="private-parameter-must-only-be-hashed", session=session)
    plugin.pytest_sessionstart(session)
    plugin.pytest_collection_modifyitems([item])
    protocol = plugin.pytest_runtest_protocol(item, None)
    next(protocol)
    call = plugin.pytest_runtest_call(item)
    next(call)
    with pytest.raises(PermissionError):
        current.guard.deny("read_outside_admitted_sources")
    current.record_refusal("probe")
    assert session.shouldstop == "h2_first_refusal_diagnostic_stop"
    assert hooks.exits == 0
    finish(call)
    teardown = plugin.pytest_runtest_teardown(item, None)
    next(teardown)
    assert current.phase == "teardown"
    finish(teardown)
    plugin.pytest_runtest_logreport(SimpleNamespace(when="teardown"))
    finish(protocol)
    assert current.data["test_protocols_started"] == current.data["test_protocols_finished"] == 1
    assert current.data["teardown_reports"] == 1
    assert current.data["stop_node_ordinal"] == 1
    assert current.data["stop_node_sha256"] == invoker._h2_text_digest(item.nodeid)
    assert item.nodeid not in repr(current.data)


def test_fake_public_filename_stays_declared_and_private_filename_stays_hashed(tmp_path):
    """A forged co_filename is never proof that a public source executed."""
    current = locator(tmp_path)
    fake = SimpleNamespace(f_code=compile("pass", str(Path(__file__)), "exec"), f_lineno=1)
    public = current.frame_record(fake, 0)
    assert public["source_status"] == "declared_public_unverified"
    assert public["source_kind"] == "project_tests"
    private = "unrelated-private-filename.py"
    fake.f_code = compile("pass", private, "exec")
    unknown = current.frame_record(fake, 1)
    assert unknown["source_status"] == "unknown"
    assert unknown["relative_source"] is None
    assert unknown["filename_sha256"] == invoker._h2_text_digest(private)
    assert private not in repr(unknown)
    assert all(key not in unknown for key in ("locals", "function", "filename", "exception"))


def test_public_position_rejects_parent_components_and_reparse_points(tmp_path, monkeypatch):
    """No public-root spelling may turn a traversal or reparse point into source identity."""
    current = locator(tmp_path)
    current.roots = (("project_tests", tmp_path),)
    assert current.public_position(str(tmp_path / ".." / "private.py")) == ("unknown", None)
    leaf = tmp_path / "public.py"

    def reparse(path):
        return SimpleNamespace(st_mode=stat.S_IFREG if path == leaf else stat.S_IFDIR,
                               st_file_attributes=0x400 if path == leaf else 0)

    monkeypatch.setattr(invoker, "_REAL_LSTAT", reparse)
    assert current.public_position(str(leaf)) == ("unknown", None)


def test_real_hook_dispatch_covers_late_cleanup_and_reinjects_old_phase_bug(tmp_path):
    """A later plugin must not run before the unconfigure observation boundary.

    This uses the real pytest Pluggy manager, without starting a pytest session.
    A fresh plugin class then reinjects the former ordinary hook and demonstrates
    the original misclassification at the actual later-registered cleanup hook.
    """
    from _pytest.config import PytestPluginManager

    def dispatch(legacy):
        current = locator(tmp_path)
        current.phase = "pytest_startup"  # The phase restored after sessionfinish.
        plugin = invoker._h2_pytest_plugin(current, pytest)
        if legacy:
            def ordinary_unconfigure(self):
                current.phase = "unconfigure"
                current.data["unconfigure_seen"] = True

            # The factory creates a fresh class per invocation; production and
            # the positive plugin are never changed by this negative control.
            type(plugin).pytest_unconfigure = ordinary_unconfigure
        observed = []

        class LaterCleanup:
            def pytest_unconfigure(self, config):
                observed.append((current.phase, current.data["unconfigure_seen"],
                                 current.data["unconfigure_dispatch_completed"]))
                with pytest.raises(PermissionError):
                    current.guard.deny("read_outside_admitted_sources")
                current.record_refusal("probe")

        manager = PytestPluginManager()
        manager.register(plugin, "h2_observer")
        manager.register(LaterCleanup(), "late_cleanup")
        manager.hook.pytest_unconfigure(config=SimpleNamespace())
        assert current.phase == "unconfigure"
        # Config's subsequent cleanup stack is outside this dispatch. Retaining
        # the phase covers it without claiming that the stack has completed.
        after_dispatch_phase = current.phase
        assert current.guard.violations == ["read_outside_admitted_sources"]
        return current, observed, after_dispatch_phase

    def assert_correct_boundary(current, order, later_phase):
        assert order == [("unconfigure", True, False)], "h2_unconfigure_dispatch_order"
        assert current.data["refusals"][0]["phase"] == "unconfigure", "h2_unconfigure_refusal_phase"
        assert current.data["unconfigure_dispatch_completed"] is True
        assert later_phase == "unconfigure"

    positive, positive_order, later_phase = dispatch(False)
    assert_correct_boundary(positive, positive_order, later_phase)
    negative, negative_order, negative_later_phase = dispatch(True)
    with pytest.raises(AssertionError, match="h2_unconfigure_dispatch_order") as reinjected:
        assert_correct_boundary(negative, negative_order, negative_later_phase)
    assert reinjected.traceback[-1].name == "assert_correct_boundary"
    assert negative_order == [("pytest_startup", False, False)]
    assert negative.data["refusals"][0]["phase"] == "pytest_startup"
    assert negative.data["unconfigure_dispatch_completed"] is False
