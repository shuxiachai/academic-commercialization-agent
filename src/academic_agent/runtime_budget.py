"""Code-owned time budget shared by the API worker and LLM adapter.

The API's 30-minute watchdog is an availability boundary, not a useful model
timeout.  If every provider call is allowed to consume that whole window, a
Reviewer request can be killed after the validated Writer draft exists but
before the existing Reviewer fallback, independent Scorer, usage snapshot and
terminal files run.  This module derives earlier monotonic deadlines while
leaving the public watchdog unchanged.

The constants are deliberately conservative operational policy, not an SLO.
A measured successful Writer/Reviewer/Scorer recovery suffix took 102 seconds;
240 seconds is reserved before the hard stop so the Reviewer can fail closed,
the independent Scorer can run, and final artifacts still have 60 seconds to
commit.  Provider traces should be used before changing these numbers.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime


WORKER_LLM_TIMEOUT_ENV = "ACADEMIC_AGENT_WORKER_LLM_TIMEOUT_SECONDS"
REQUEST_TIMEOUT_SECONDS = 150
REVIEWER_RESERVE_SECONDS = 240
FINALIZATION_RESERVE_SECONDS = 60


@dataclass(frozen=True)
class RuntimeBudget:
    """Monotonic worker deadlines derived once from the API's wall deadline."""

    hard_deadline_monotonic: float | None
    hard_deadline_epoch: float | None
    hard_timeout_seconds: int | None
    request_timeout_seconds: int = REQUEST_TIMEOUT_SECONDS
    reviewer_reserve_seconds: int = REVIEWER_RESERVE_SECONDS
    finalization_reserve_seconds: int = FINALIZATION_RESERVE_SECONDS

    @classmethod
    def from_wall_deadline(
        cls,
        deadline_epoch: float | None,
        timeout_seconds: int | None,
        *,
        wall_now: float | None = None,
        monotonic_now: float | None = None,
    ) -> "RuntimeBudget":
        """Convert once so later system-clock changes cannot extend a run."""

        if deadline_epoch is None:
            return cls(None, None, timeout_seconds)
        if deadline_epoch <= 0:
            raise ValueError("hard deadline epoch must be positive")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("hard timeout seconds must be positive")
        observed_wall = time.time() if wall_now is None else wall_now
        observed_monotonic = (
            time.monotonic() if monotonic_now is None else monotonic_now
        )
        remaining = max(0.0, deadline_epoch - observed_wall)
        return cls(
            observed_monotonic + remaining,
            deadline_epoch,
            timeout_seconds,
        )

    @property
    def active(self) -> bool:
        return self.hard_deadline_monotonic is not None

    @property
    def reviewer_deadline(self) -> float | None:
        if self.hard_deadline_monotonic is None:
            return None
        return self.hard_deadline_monotonic - self.reviewer_reserve_seconds

    @property
    def paid_work_deadline(self) -> float | None:
        if self.hard_deadline_monotonic is None:
            return None
        return self.hard_deadline_monotonic - self.finalization_reserve_seconds

    def deadline_for_agent(self, index: int) -> float | None:
        """Reviewer stops early; every other node shares the finalization edge."""

        return self.reviewer_deadline if index == 4 else self.paid_work_deadline

    def public_snapshot(self) -> dict[str, object]:
        """Serializable policy metadata; monotonic process-local values stay private."""

        deadline_at = None
        if self.hard_deadline_epoch is not None:
            deadline_at = datetime.fromtimestamp(
                self.hard_deadline_epoch, tz=UTC
            ).isoformat()
        return {
            "state": "active" if self.active else "unbounded_cli",
            "hard_timeout_seconds": self.hard_timeout_seconds,
            "hard_deadline_at": deadline_at,
            "request_timeout_seconds": self.request_timeout_seconds,
            "reviewer_reserve_seconds": self.reviewer_reserve_seconds,
            "finalization_reserve_seconds": self.finalization_reserve_seconds,
        }
