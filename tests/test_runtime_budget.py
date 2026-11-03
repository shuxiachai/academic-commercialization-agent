"""Tests for the API watchdog to worker/provider deadline contract.

The production failure behind this module reached Reviewer and was then killed
by the 30-minute parent watchdog. A transport timeout equal to that watchdog is
not a bound: it leaves no time for the existing validated-draft fallback,
independent Scorer, usage snapshot, or terminal persistence. These tests pin
the reserves at the monotonic conversion seam without sleeping or networking.
"""

from __future__ import annotations

import pytest

from academic_agent.runtime_budget import RuntimeBudget


def test_wall_deadline_is_converted_once_to_monotonic_time() -> None:
    budget = RuntimeBudget.from_wall_deadline(
        1_900.0,
        1_800,
        wall_now=100.0,
        monotonic_now=500.0,
    )

    assert budget.hard_deadline_monotonic == 2_300.0
    assert budget.reviewer_deadline == 2_060.0
    assert budget.paid_work_deadline == 2_240.0


def test_reviewer_has_a_larger_finalization_reserve_than_other_nodes() -> None:
    budget = RuntimeBudget.from_wall_deadline(
        1_900.0,
        1_800,
        wall_now=100.0,
        monotonic_now=500.0,
    )

    assert budget.deadline_for_agent(4) == budget.reviewer_deadline
    for index in (0, 1, 2, 3, 5):
        assert budget.deadline_for_agent(index) == budget.paid_work_deadline
    assert budget.reviewer_deadline < budget.paid_work_deadline


def test_public_snapshot_exposes_policy_without_process_local_clock() -> None:
    budget = RuntimeBudget.from_wall_deadline(
        1_900.0,
        1_800,
        wall_now=100.0,
        monotonic_now=500.0,
    )

    snapshot = budget.public_snapshot()

    assert snapshot["state"] == "active"
    assert snapshot["hard_timeout_seconds"] == 1_800
    assert snapshot["hard_deadline_at"].endswith("+00:00")
    assert "monotonic" not in " ".join(snapshot)


def test_direct_cli_run_remains_explicitly_unbounded() -> None:
    budget = RuntimeBudget.from_wall_deadline(None, None)

    assert not budget.active
    assert budget.deadline_for_agent(4) is None
    assert budget.public_snapshot()["state"] == "unbounded_cli"


@pytest.mark.parametrize("deadline", [0.0, -1.0])
def test_invalid_wall_deadline_is_rejected(deadline: float) -> None:
    with pytest.raises(ValueError, match="deadline"):
        RuntimeBudget.from_wall_deadline(deadline, 1_800)


def test_a_wall_deadline_already_passed_yields_elapsed_deadlines_not_an_error() -> None:
    budget = RuntimeBudget.from_wall_deadline(1_000.0, 30, wall_now=2_000.0, monotonic_now=50.0)
    assert budget.active
    assert budget.hard_deadline_monotonic == 50.0
    assert budget.paid_work_deadline == 50.0 - budget.finalization_reserve_seconds
    assert budget.reviewer_deadline == 50.0 - budget.reviewer_reserve_seconds


@pytest.mark.parametrize("index", [0, 1, 2, 3, 5, -1, 99])
def test_only_the_reviewer_index_gets_the_reviewer_reserve(index: int) -> None:
    budget = RuntimeBudget.from_wall_deadline(1_000.0, 30, wall_now=100.0, monotonic_now=0.0)
    assert budget.deadline_for_agent(index) == budget.paid_work_deadline
    assert budget.deadline_for_agent(4) == budget.reviewer_deadline


@pytest.mark.parametrize("timeout", [0, -5])
def test_a_non_positive_timeout_is_rejected_whenever_a_deadline_is_set(timeout: int) -> None:
    with pytest.raises(ValueError):
        RuntimeBudget.from_wall_deadline(100.0, timeout, wall_now=1.0, monotonic_now=1.0)


def test_an_unbounded_budget_has_no_deadlines_at_all() -> None:
    budget = RuntimeBudget.from_wall_deadline(None, None)
    assert not budget.active
    assert budget.reviewer_deadline is None
    assert budget.paid_work_deadline is None
    assert budget.deadline_for_agent(4) is None
    assert budget.public_snapshot()["hard_deadline_at"] is None
