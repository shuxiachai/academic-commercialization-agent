"""Immutable execution identity for NEW benchmark batches, never the archive.

The old success/mode predicate is useful for reading historical results, but
not permission to skip a new model evaluation. A batch binds source contents,
dependency lock, explicit non-secret settings, exact model and frozen inputs.
This is local reproducibility, not deterministic provider responses or billing
exactly-once. An occupied failed/unfinished unit is deliberately not retried.
"""

from __future__ import annotations

import hashlib
from importlib import metadata
import json
import os
import platform
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parent
BATCH_ROOT = ROOT / "outputs" / "benchmark-runs"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}")
_SETTINGS = ("MAX_RPM", "LLM_PRICE_PER_MTOK", "ACADEMIC_AGENT_WORKER_LLM_TIMEOUT_SECONDS",
             "EVIDENCE_GAP_SHADOW_ENABLED")
_OPTIONAL_ACCESS = ("TAVILY_API_KEY", "SERPER_API_KEY", "SEMANTIC_SCHOLAR_API_KEY",
                    "NCBI_API_KEY", "LENS_API_KEY", "OPENALEX_MAILTO", "CROSSREF_MAILTO")


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_digest(value: object) -> str:
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode())


def execution_identity(selected: list[tuple], use_fixture: bool) -> dict:
    """Read only; credentials are consumed by resolution, never serialized.

    Import resolution first: CrewAI's one-time dotenv import must precede the
    snapshot, just as it precedes actual crew construction. Content hashes also
    bind uncommitted edits; HEAD alone would miss the common local-edit case.
    """
    from academic_agent.llm_config import resolve_provider_config
    import benchmark_fixtures
    from benchmark import _slug

    config = resolve_provider_config()
    files = sorted({
        *ROOT.joinpath("src").rglob("*.py"),
        *ROOT.joinpath("src").rglob("*.yaml"),
        *(ROOT / name for name in ("benchmark.py", "benchmark_identity.py",
                                  "benchmark_fixtures.py", "pyproject.toml", "uv.lock")),
    })
    # Paths are relative and raw bytes intentionally bind the actual checkout.
    # Cross-platform/line-ending changes start a new batch, not an assumed reuse.
    sources = {p.relative_to(ROOT).as_posix(): digest(p.read_bytes()) for p in files}
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
                            capture_output=True, text=True).stdout.strip()
    fixtures = {}
    if use_fixture:
        for num, topic, *_ in selected:
            if benchmark_fixtures.load(num, _slug(topic)) is None:
                raise ValueError(f"Missing fixture for case {num}; no paid unit started")
            path = benchmark_fixtures.fixture_path(num, _slug(topic))
            fixtures[num] = digest(path.read_bytes())
    return {
        "schema_version": 1, "code_commit": commit, "source_hashes": sources,
        "python": platform.python_version(), "platform": platform.system(),
        # A lock file is intent, not proof of what an unsynced environment has
        # installed. Bind both; no network/package installation happens here.
        "installed_versions": dict(sorted((dist.metadata["Name"].lower(), dist.version)
                                           for dist in metadata.distributions() if dist.metadata["Name"])),
        "provider": config.provider, "model": config.model,
        "endpoint_sha256": digest(config.base_url.encode()),
        # Only whitelisted controls are recorded. Do not dump os.environ or
        # hash low-entropy access codes as a supposed anonymization scheme.
        "settings": {name: os.getenv(name, "") for name in _SETTINGS},
        "optional_access_configured": {name: bool(os.getenv(name)) for name in _OPTIONAL_ACCESS},
        "evidence_mode": "fixture" if use_fixture else "live",
        "fixture_sha256": fixtures,
        "cases": json.loads(json.dumps(selected)),
    }


def prepare_batch(selected: list[tuple], use_fixture: bool, *,
                  experiment_id: str | None = None, resume: bool = False) -> dict:
    identifier = experiment_id or (datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:12])
    if not _ID.fullmatch(identifier):
        raise ValueError("Experiment ID must be a bounded alphanumeric slug")
    root = BATCH_ROOT / identifier
    if root.is_symlink() or root.resolve().parent != BATCH_ROOT.resolve():
        raise ValueError("Experiment path must remain inside benchmark-runs")
    identity = execution_identity(selected, use_fixture)
    manifest = {"identity": identity, "identity_sha256": json_digest(identity)}
    if resume:
        saved = json.loads((root / "batch.json").read_text(encoding="utf-8"))
        if saved != manifest:
            raise ValueError("Batch identity changed; use a new experiment ID")
    else:
        # mkdir is the exclusive acceptance point. A stale/partial directory
        # is never overwritten, even if --force was used by an older script.
        root.mkdir(parents=True, exist_ok=False)
        (root / "batch.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {"root": str(root), **manifest}


def verify_batch(batch: dict, selected: list[tuple], use_fixture: bool) -> None:
    """Check again inside spawned workers before any retrieval/model request."""
    saved = json.loads((Path(batch["root"]) / "batch.json").read_text(encoding="utf-8"))
    current = execution_identity(selected, use_fixture)
    if (saved != {"identity": batch["identity"], "identity_sha256": batch["identity_sha256"]}
            or current != batch["identity"] or json_digest(current) != batch["identity_sha256"]):
        raise ValueError("Execution/fixture identity changed after batch acceptance")


def result_hashes(run_dir: Path) -> dict[str, str]:
    """Bind inspection outputs too; a damaged report is not a reusable success."""
    return {p.name: digest(p.read_bytes()) for p in sorted(run_dir.iterdir())
            if p.is_file() and p.name != "meta.json"}


def reusable_result(run_dir: Path, identity: dict) -> bool:
    try:
        meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
        hashes = meta.get("artifact_sha256")
        required = {"validated_sources.json", "commercialization_report.md",
                    "commercialization_scores.json"}
        return (meta.get("status") == "success" and meta.get("execution_identity") == identity
                and isinstance(hashes, dict) and required <= hashes.keys()
                and hashes == result_hashes(run_dir))
    except (OSError, ValueError, TypeError, AttributeError):
        # Absence, corruption and old successes are not permission to spend.
        # The caller rejects an occupied unit instead of launching it again.
        return False
