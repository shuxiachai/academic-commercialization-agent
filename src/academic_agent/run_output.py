"""Per-run output management for generated commercialization reports."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "outputs"


def create_run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{uuid4().hex[:10]}"


def save_report(
    report: str,
    run_id: str | None = None,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
) -> tuple[str, Path]:
    resolved_run_id = run_id or create_run_id()
    run_directory = output_root / resolved_run_id
    run_directory.mkdir(parents=True, exist_ok=False)
    report_path = run_directory / "commercialization_report.md"
    report_path.write_text(report, encoding="utf-8")
    return resolved_run_id, report_path
