"""run_reader — Functions to read run-directory metadata (pure IO, no ui dependencies)."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _read_output_language(run_dir) -> str:
    """Read output_language from the saved validated_sources.json for a run."""
    try:
        sources_path = run_dir / "validated_sources.json"
        if sources_path.exists():
            data = json.loads(sources_path.read_text(encoding="utf-8"))
            return data.get("output_language") or "English"
    except Exception:
        pass
    return "English"


def _read_weight_profile(run_dir) -> str:
    """Read weight_profile from validated_sources.json for a run."""
    try:
        sources_path = run_dir / "validated_sources.json"
        if sources_path.exists():
            data = json.loads(sources_path.read_text(encoding="utf-8"))
            return data.get("weight_profile") or "industrial"
    except Exception:
        pass
    return "industrial"


def _parse_run_timestamp(run_id: str) -> str:
    """Convert run_id like '20241215T123456Z-abc' to local time."""
    try:
        ts = run_id.split("-")[0]  # '20241215T123456Z'
        dt = datetime.strptime(ts, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return run_id[:16]


def _run_duration(run_dir: Path) -> str:
    """Return human-readable run duration (e.g. '2m 34s') from run_id start to status.json mtime."""
    try:
        run_id = run_dir.name
        ts = run_id.split("-")[0]
        start_dt = datetime.strptime(ts, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        status_path = run_dir / "status.json"
        if not status_path.exists():
            return "—"
        end_ts = os.path.getmtime(status_path)
        from datetime import timezone as _tz
        end_dt = datetime.fromtimestamp(end_ts, tz=_tz.utc)
        secs = int((end_dt - start_dt).total_seconds())
        if secs < 0:
            return "—"
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m {secs % 60:02d}s"
    except Exception:
        return "—"


_REPORT_TITLE_PREFIXES = (
    "academic commercialization assessment:",
    # Common localized prefixes — strip the heading label, keep the topic
    "学术商业化评估：", "学术商业化评估:", "学术商业化评估",
    "commercialization assessment:",
)


def _extract_topic_from_report(report_path: Path) -> str:
    try:
        text = report_path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") and len(stripped) > 2:
                title = stripped.lstrip("#").strip()
                for prefix in _REPORT_TITLE_PREFIXES:
                    if title.lower().startswith(prefix.lower()):
                        title = title[len(prefix):].strip()
                        break
                return title[:90] if title else "—"
    except Exception:
        pass
    return "—"


def _read_run_topic(run_dir: Path) -> str:
    """Read topic from status.json (supports all languages); fall back to report parsing."""
    try:
        data = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        if t := data.get("topic"):
            return str(t)[:90]
    except Exception:
        pass
    report_path = run_dir / "commercialization_report.md"
    if report_path.exists():
        return _extract_topic_from_report(report_path)
    return "—"
