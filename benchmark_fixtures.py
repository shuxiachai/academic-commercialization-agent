"""Frozen evidence for benchmark runs.

A benchmark run currently retrieves its own evidence, which means every
measurement mixes two sources of variance: what the pipeline *found* that day
and what the agents *concluded* from it. When a calibration number moves, the
two are not separable after the fact — and re-measuring costs a full retrieval
pass plus a full crew run for every topic.

Freezing the evidence separates them. A fixture is the exact SourceCollection
a real retrieval produced, saved verbatim; replaying it holds the input
constant so that any remaining spread is the agents' reasoning, which is the
thing a prompt change is actually trying to move.

Two rules this module exists to enforce.

**A fixture result is not a live result.** Fixture mode measures reasoning
over fixed evidence; live mode measures the whole system. Reporting either as
"the benchmark score" without saying which one produced it would compare two
different quantities — so the mode is recorded in each run's meta.json and the
loader refuses to reuse a run captured under the other mode.

**A fixture goes stale invisibly.** The evidence is a snapshot of what the
web held on one day; a year later it is a historical artifact, and nothing
about replaying it would say so. The manifest records when each fixture was
captured and from which run, and the age is printed every time fixtures are
used, so "the baseline" stays falsifiable.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

FIXTURE_ROOT = Path(__file__).parent / "benchmark_fixtures"
MANIFEST_PATH = FIXTURE_ROOT / "manifest.json"

#: Fixtures older than this are still usable -- they are a valid historical
#: input -- but replaying them is no longer evidence about today's web, so the
#: harness says so out loud rather than letting the number speak for itself.
STALE_AFTER_DAYS = 180


def fixture_path(num: str, slug: str) -> Path:
    return FIXTURE_ROOT / f"{num}-{slug}.json"


def _digest(text: str) -> str:
    """Content hash, blind to line endings.

    Git translates newlines on checkout, so the same committed fixture is CRLF
    in a Windows working copy and LF on a Linux CI runner. Hashing the bytes as
    they sit on disk made the guard fire on every machine that was not the one
    that captured the file — a platform artifact reported as tampering, which
    would have trained everyone to ignore the check.
    """
    return hashlib.sha256(text.replace("\r\n", "\n").encode("utf-8")).hexdigest()[:16]


def load_manifest() -> dict:
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"fixtures": {}}


def _save_manifest(manifest: dict) -> None:
    FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    # newline="" for the same reason as the fixtures themselves: otherwise
    # every capture on Windows rewrites the whole file as CRLF and git shows
    # it as changed even when no fixture moved.
    with MANIFEST_PATH.open("w", encoding="utf-8", newline="") as fh:
        fh.write(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def freeze(num: str, slug: str, topic: str, sources_json: str) -> dict:
    """Save one SourceCollection dump as a fixture and record its provenance.

    Returns the manifest entry. `sources_json` is stored byte-for-byte rather
    than re-serialised: a fixture that differs from what the run actually used,
    even in key order, is no longer the thing it claims to be a record of.
    """
    FIXTURE_ROOT.mkdir(parents=True, exist_ok=True)
    path = fixture_path(num, slug)
    # newline="" so Windows does not expand \n to \r\n on the way out: the
    # file then matches what git stores, and a fixture captured on one
    # platform is byte-identical to the same fixture captured on another.
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(sources_json)

    parsed = json.loads(sources_json)
    entry = {
        "topic": topic,
        "file": path.name,
        "captured_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "collected_at": parsed.get("collected_at", ""),
        "sha256_16": _digest(sources_json),
        "counts": {
            "academic": len(parsed.get("academic_sources") or []),
            "patent": len(parsed.get("patent_sources") or []),
            "market": len(parsed.get("market_sources") or []),
        },
    }
    manifest = load_manifest()
    manifest.setdefault("fixtures", {})[num] = entry
    _save_manifest(manifest)
    return entry


def load(num: str, slug: str):
    """Return the frozen SourceCollection for a topic, or None if absent.

    Raises ValueError when the file no longer matches the digest the manifest
    recorded: a fixture edited by hand is the one input a benchmark must never
    silently accept, since every number downstream is attributed to it.
    """
    path = fixture_path(num, slug)
    if not path.exists():
        return None

    raw = path.read_text(encoding="utf-8")
    recorded = load_manifest().get("fixtures", {}).get(num, {}).get("sha256_16")
    if recorded and _digest(raw) != recorded:
        raise ValueError(
            f"fixture {path.name} does not match the manifest digest "
            f"({_digest(raw)} != {recorded}). Re-freeze it, or restore the file."
        )

    from academic_agent.source_pipeline import SourceCollection

    return SourceCollection.model_validate_json(raw)


def age_days(num: str) -> float | None:
    """How old the *evidence* is — not how long ago the file was written.

    `collected_at` is when the pipeline actually read the web; `captured_at`
    is only when that dump was copied into the fixture directory. Seeding a
    fixture from a run recorded months ago would look brand new under the
    second, which is exactly the false freshness this age is meant to expose.
    """
    entry = load_manifest().get("fixtures", {}).get(num)
    if not entry:
        return None
    stamp = entry.get("collected_at") or entry.get("captured_at")
    if not stamp:
        return None
    try:
        collected = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if collected.tzinfo is None:
        collected = collected.replace(tzinfo=UTC)
    return (datetime.now(UTC) - collected).total_seconds() / 86400


def describe() -> list[str]:
    """One line per fixture, for the harness to print before it runs.

    Age is stated rather than only stored, because a stale fixture produces a
    result that looks exactly like a fresh one.
    """
    manifest = load_manifest().get("fixtures", {})
    if not manifest:
        return ["no fixtures captured yet — run: python benchmark.py --freeze"]

    lines = []
    for num in sorted(manifest):
        entry = manifest[num]
        counts = entry.get("counts", {})
        age = age_days(num)
        stamp = "age unknown" if age is None else f"{age:.0f}d old"
        if age is not None and age > STALE_AFTER_DAYS:
            stamp += " — STALE, no longer evidence about today's web"
        lines.append(
            f"  {num} {entry.get('topic', '?')[:44]:<44} "
            f"{counts.get('academic', 0)}A/{counts.get('patent', 0)}P/"
            f"{counts.get('market', 0)}M  {stamp}"
        )
    return lines
