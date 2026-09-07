"""Per-attempt cleanup observations, separate from legacy removal return values."""

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from stat import S_ISDIR
from typing import Literal

from api.models import CleanupSummary


@dataclass
class CleanupAudit:
    """Owned by one offloaded call; only its final immutable snapshot is public."""

    scanned: int = 0
    deleted: int = 0
    skipped: int = 0
    failed: int = 0
    skip_reasons: dict[str, int] = field(default_factory=dict)
    failure_reasons: dict[str, int] = field(default_factory=dict)
    started: bool = False
    scan_complete: bool = False
    state: Literal["complete", "partial", "disabled", "absent", "unavailable"] = "unavailable"

    def entries(self, root: Path) -> Iterator[Path]:
        # is_dir can collapse absence and a failed stat on some Python versions.
        # Only definite absence is a no-scan result; a denied/file root remains
        # unavailable and reaches the existing per-stage exception boundary.
        try:
            mode = root.stat().st_mode
        except FileNotFoundError:
            self.state = "absent"
            return
        if not S_ISDIR(mode):
            raise NotADirectoryError("Cleanup root is not a directory")
        self.started = True
        for directory in root.iterdir():
            self.scanned += 1
            yield directory
        self.scan_complete = True
        self.state = "partial" if self.failed else "complete"

    def skip(self, reason: Literal["fresh", "live", "unrelated"]) -> None:
        self.skipped += 1
        self.skip_reasons[reason] = self.skip_reasons.get(reason, 0) + 1

    def fail(self, reason: Literal["metadata", "delete"]) -> None:
        self.failed += 1
        self.failure_reasons[reason] = self.failure_reasons.get(reason, 0) + 1

    def snapshot(self, *, interrupted: bool = False) -> CleanupSummary:
        # No scan is not an empty successful scan. A mid-iteration failure keeps
        # the observed prefix, explicitly incomplete, rather than zeroing facts
        # or presenting partial counts as the root's complete inventory.
        state = "unavailable" if interrupted else self.state
        if not self.started:
            return CleanupSummary(state=state)
        return CleanupSummary(
            state=state, scan_complete=self.scan_complete and not interrupted,
            scanned=self.scanned, deleted=self.deleted, skipped=self.skipped, failed=self.failed,
            skip_reasons=dict(self.skip_reasons), failure_reasons=dict(self.failure_reasons),
        )
