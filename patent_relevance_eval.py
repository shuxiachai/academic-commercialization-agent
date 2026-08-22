"""Build and summarize a human-labelled patent-relevance audit.

The retrieval pipeline treats every validated patent as relevant enough to
reach the report, but URL validation says nothing about topical relevance.
This tool measures that separate question over evidence already on disk.  It
never searches the web, never asks a model to label a case, and never reports
recall from a positive-only sample.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections.abc import Iterable
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


LABELS = {"RELEVANT", "WEAK", "IRRELEVANT", "UNCERTAIN"}
LABEL_FIELDS = ("case_id", "label", "confidence", "rationale")
INDEX_FIELDS = ("case_id", "topic", "source_id", "title", "url", "case_file")


class PatentAuditError(ValueError):
    """Raised when an audit artifact would misstate its evidence or denominator."""


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PatentCase:
    """One accepted patent judged against the topic that retrieved it."""

    case_id: str
    corpus: str
    topic: str
    source_id: str
    title: str
    url: str
    evidence_summary: str
    provenance: str

    @property
    def case_file(self) -> str:
        return f"cases/{self.case_id}.md"

    @property
    def content_sha256(self) -> str:
        return _sha256(_case_markdown(self))


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PatentAuditError(f"could not read JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PatentAuditError(f"{path} must contain a JSON object")
    return value


def _case_id(topic: str, url: str) -> str:
    """Keep IDs stable when another fixture or corpus is added later."""

    digest = hashlib.sha256(f"{topic}\0{url}".encode()).hexdigest()[:12]
    return f"PR-{digest.upper()}"


def _cases_from_payload(
    payload: dict[str, Any],
    *,
    corpus: str,
    provenance: str,
) -> list[PatentCase]:
    topic = str(payload.get("topic", "")).strip()
    if not topic:
        raise PatentAuditError(f"{provenance} has no topic")
    patents = payload.get("patent_sources")
    if not isinstance(patents, list) or not patents:
        raise PatentAuditError(f"{provenance} has no patent_sources")

    cases: list[PatentCase] = []
    for index, patent in enumerate(patents, start=1):
        if not isinstance(patent, dict):
            raise PatentAuditError(f"{provenance} patent {index} is not an object")
        source_id = str(patent.get("source_id", "")).strip()
        title = str(patent.get("title", "")).strip()
        url = str(patent.get("url", "")).strip()
        summary = str(patent.get("evidence_summary", "")).strip()
        missing = [
            name
            for name, value in (
                ("source_id", source_id),
                ("title", title),
                ("url", url),
                ("evidence_summary", summary),
            )
            if not value
        ]
        if missing:
            raise PatentAuditError(
                f"{provenance} patent {index} is missing {', '.join(missing)}"
            )
        cases.append(
            PatentCase(
                case_id=_case_id(topic, url),
                corpus=corpus,
                topic=topic,
                source_id=source_id,
                title=title,
                url=url,
                evidence_summary=summary,
                provenance=provenance,
            )
        )
    return cases


def discover_cases(
    fixture_dir: Path,
    challenge_paths: Iterable[Path] = (),
) -> list[PatentCase]:
    """Read the complete frozen benchmark plus explicitly declared challenges."""

    fixtures = sorted(path for path in fixture_dir.glob("*.json") if path.name != "manifest.json")
    if not fixtures:
        raise PatentAuditError(f"no benchmark fixtures found in {fixture_dir}")

    cases: list[PatentCase] = []
    for path in fixtures:
        cases.extend(
            _cases_from_payload(
                _read_json(path),
                corpus="benchmark_core",
                provenance=path.as_posix(),
            )
        )
    for path in sorted(challenge_paths):
        payload = _read_json(path)
        corpus = str(payload.get("corpus", "")).strip()
        if not corpus or corpus == "benchmark_core":
            raise PatentAuditError(f"{path} must declare a non-core corpus")
        cases.extend(
            _cases_from_payload(payload, corpus=corpus, provenance=path.as_posix())
        )

    # A repeated URL for the same topic is one judgment, even if two historical
    # runs happened to retrieve it. Counting both would inflate the denominator
    # and make a stable upstream result look like independent evidence.
    seen: dict[tuple[str, str], PatentCase] = {}
    for case in cases:
        key = (case.topic.casefold(), case.url.casefold())
        previous = seen.get(key)
        if previous is not None:
            raise PatentAuditError(
                f"duplicate topic/URL across {previous.provenance} and {case.provenance}: "
                f"{case.topic} | {case.url}"
            )
        seen[key] = case
    return sorted(cases, key=lambda case: (case.corpus, case.topic.casefold(), case.source_id))


def freeze_challenge(
    source_path: Path,
    output_path: Path,
    *,
    corpus: str,
    selection_note: str,
) -> dict[str, Any]:
    """Copy only public patent evidence from one real run into a tracked fixture."""

    if output_path.exists():
        raise PatentAuditError(f"refusing to overwrite existing challenge fixture: {output_path}")
    source = _read_json(source_path)
    # Validate before writing. A malformed challenge file should fail at freeze
    # time, not months later when somebody tries to reproduce the measurement.
    _cases_from_payload(source, corpus=corpus, provenance=source_path.as_posix())
    frozen = {
        "schema_version": 1,
        "corpus": corpus,
        "source_run_id": source_path.parent.name,
        "topic": source["topic"],
        "collected_at": source.get("collected_at"),
        "selection_note": selection_note,
        "patent_sources": source["patent_sources"],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(frozen, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return frozen


def _case_markdown(case: PatentCase) -> str:
    return f"""# Patent relevance case {case.case_id}

- **Research topic:** {case.topic}
- **Retrieved source ID:** `{case.source_id}`
- **Patent title:** {case.title}
- **Patent URL:** {case.url}

## Retrieved evidence summary

{case.evidence_summary}

## Labeling question

Does this patent directly help assess the patent landscape or commercialization
position of the research topic above? Record the answer in `labels.csv`; judge
topical relevance, not whether the patent is legally valid or commercially good.
"""


def _packet_readme(case_count: int, corpus_counts: Counter[str]) -> str:
    counts = ", ".join(f"{name}={count}" for name, count in sorted(corpus_counts.items()))
    return f"""# Patent-relevance audit packet

This packet contains {case_count} patent records ({counts}) retrieved and accepted
by the existing pipeline. It uses frozen evidence only and makes no API calls.

Open each file under `cases/` and complete the matching row in `labels.csv`:

- `RELEVANT`: the claimed invention directly concerns the topic's core technology
  or the named commercialization application.
- `WEAK`: adjacent or contextually useful, but not direct evidence of the core
  patent landscape.
- `IRRELEVANT`: keyword overlap without a material connection to the topic.
- `UNCERTAIN`: the title and retrieved summary are insufficient for a reliable
  judgment; do not guess.
- `confidence`: integer 1-5.
- `rationale`: concise evidence for the label; name the mismatch for weak,
  irrelevant, or uncertain cases.

After all labels are complete, also fill in `reviewer_declaration.md`; metrics
without a documented review method are not an independent human audit.

Every row must be completed before headline rates are calculated. Empty is
"not evaluated", never relevant. This accepted-source sample can measure
precision-like relevance rates, but it cannot measure global retrieval recall.
Do not change production filtering rules until this baseline is complete and a
candidate rule has been compared against the same labels.
"""


def _reviewer_declaration() -> str:
    return """# Reviewer declaration

Complete this after labeling all cases. This declaration distinguishes a human
audit from an AI-generated opinion and records how the evidence was inspected.

1. Did you personally review every case card? **[YES / NO]**
2. Did generative AI create any substantive label or rationale?
   **[NONE / LANGUAGE-ONLY / SOME-SUBSTANTIVE / MOST-OR-ALL]**
3. Did you open any external patent URLs? **[NONE / SOME / ALL]**
4. Were any labels discussed with another person before submission?
   **[YES / NO]**
5. Actual elapsed review time: **[minutes]**
6. Relevant expertise or role (optional): **[text]**
7. Additional limitations or conflicts (optional): **[text]**

Reviewer name or pseudonym: **[text]**
Date completed: **[YYYY-MM-DD]**
"""


def prepare_packet(
    fixture_dir: Path,
    packet_dir: Path,
    *,
    challenge_paths: Iterable[Path] = (),
) -> dict[str, Any]:
    """Create a deterministic human-label packet from existing evidence."""

    if packet_dir.exists():
        raise PatentAuditError(f"refusing to overwrite existing packet: {packet_dir}")
    cases = discover_cases(fixture_dir, challenge_paths)
    packet_dir.mkdir(parents=True)
    case_dir = packet_dir / "cases"
    case_dir.mkdir()

    manifest_cases: list[dict[str, Any]] = []
    with (packet_dir / "case_index.csv").open("w", encoding="utf-8", newline="") as handle:
        index_writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDS)
        index_writer.writeheader()
        for case in cases:
            body = _case_markdown(case)
            (packet_dir / case.case_file).write_text(body, encoding="utf-8")
            index_writer.writerow(
                {
                    "case_id": case.case_id,
                    "topic": case.topic,
                    "source_id": case.source_id,
                    "title": case.title,
                    "url": case.url,
                    "case_file": case.case_file,
                }
            )
            manifest_cases.append(
                {
                    "case_id": case.case_id,
                    "corpus": case.corpus,
                    "topic": case.topic,
                    "source_id": case.source_id,
                    "url": case.url,
                    "content_sha256": case.content_sha256,
                    "provenance": case.provenance,
                }
            )

    with (packet_dir / "labels.csv").open("w", encoding="utf-8", newline="") as handle:
        label_writer = csv.DictWriter(handle, fieldnames=LABEL_FIELDS)
        label_writer.writeheader()
        for case in cases:
            label_writer.writerow({"case_id": case.case_id})

    corpus_counts = Counter(case.corpus for case in cases)
    topic_counts = Counter(case.topic for case in cases)
    manifest = {
        "schema_version": 1,
        "audit_unit": "accepted_patent_topic_pair",
        "source_mode": "frozen evidence; zero network",
        "prepared_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "case_count": len(cases),
        "corpus_counts": dict(sorted(corpus_counts.items())),
        "topic_counts": dict(sorted(topic_counts.items())),
        "cases": manifest_cases,
        "measurement_limit": (
            "Accepted sources support relevance-rate measurement, not global retrieval recall."
        ),
    }
    (packet_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (packet_dir / "README.md").write_text(
        _packet_readme(len(cases), corpus_counts),
        encoding="utf-8",
    )
    (packet_dir / "reviewer_declaration.md").write_text(
        _reviewer_declaration(),
        encoding="utf-8",
    )
    return manifest


def _read_label_rows(path: Path) -> list[dict[str, str]]:
    try:
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if tuple(reader.fieldnames or ()) != LABEL_FIELDS:
                raise PatentAuditError(
                    f"{path} columns must be exactly: {', '.join(LABEL_FIELDS)}"
                )
            return list(reader)
    except OSError as exc:
        raise PatentAuditError(f"could not read labels from {path}: {exc}") from exc


def _validated_label(row: dict[str, str]) -> dict[str, Any] | None:
    values = [row.get(field, "").strip() for field in LABEL_FIELDS[1:]]
    if not any(values):
        return None
    if not all(values):
        raise PatentAuditError(f"{row['case_id']} is partially completed")
    label = values[0].upper()
    if label not in LABELS:
        raise PatentAuditError(f"{row['case_id']} has invalid label: {values[0]}")
    try:
        confidence = int(values[1])
    except ValueError as exc:
        raise PatentAuditError(f"{row['case_id']} confidence must be an integer") from exc
    if confidence not in range(1, 6):
        raise PatentAuditError(f"{row['case_id']} confidence must be between 1 and 5")
    return {
        "case_id": row["case_id"],
        "label": label,
        "confidence": confidence,
        "rationale": values[2],
    }


def _metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    counts = Counter(row["label"] for row in rows)
    # Uncertain stays in every denominator. Dropping it would let a difficult
    # corpus improve its own headline rate merely by declining to judge cases.
    return {
        "case_count": total,
        "label_counts": {label: counts[label] for label in sorted(LABELS)},
        "direct_relevance_rate": counts["RELEVANT"] / total,
        "usable_relevance_rate": (counts["RELEVANT"] + counts["WEAK"]) / total,
        "weak_rate": counts["WEAK"] / total,
        "irrelevant_rate": counts["IRRELEVANT"] / total,
        "uncertain_rate": counts["UNCERTAIN"] / total,
        "mean_confidence": sum(row["confidence"] for row in rows) / total,
    }


def summarize_labels(
    labels_path: Path,
    manifest_path: Path,
) -> dict[str, Any]:
    """Validate a complete label contract before calculating headline rates."""

    manifest = _read_json(manifest_path)
    cases = manifest.get("cases")
    if not isinstance(cases, list) or not cases:
        raise PatentAuditError(f"{manifest_path} has no cases")
    expected = [str(case.get("case_id", "")) for case in cases]
    if any(not case_id for case_id in expected) or len(expected) != len(set(expected)):
        raise PatentAuditError("manifest case IDs must be non-empty and unique")

    rows = _read_label_rows(labels_path)
    observed = [row.get("case_id", "").strip() for row in rows]
    if len(observed) != len(set(observed)):
        raise PatentAuditError("labels contain duplicate case IDs")
    if set(observed) != set(expected):
        missing = sorted(set(expected) - set(observed))
        extra = sorted(set(observed) - set(expected))
        raise PatentAuditError(f"label case IDs do not match manifest; missing={missing}, extra={extra}")

    validated_by_id: dict[str, dict[str, Any]] = {}
    incomplete: list[str] = []
    for row in rows:
        validated = _validated_label(row)
        if validated is None:
            incomplete.append(row["case_id"])
        else:
            validated_by_id[row["case_id"]] = validated

    summary: dict[str, Any] = {
        "schema_version": 1,
        "protocol_status": "incomplete" if incomplete else "complete",
        "case_count": len(expected),
        "completed_case_count": len(validated_by_id),
        "incomplete_case_ids": incomplete,
        "metrics": None,
        "by_corpus": None,
        "by_topic": None,
        "measurement_limit": manifest.get("measurement_limit"),
    }
    if incomplete:
        return summary

    ordered = [validated_by_id[case_id] for case_id in expected]
    case_by_id = {str(case["case_id"]): case for case in cases}
    summary["metrics"] = _metrics(ordered)
    for dimension, output_key in (("corpus", "by_corpus"), ("topic", "by_topic")):
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in ordered:
            group = str(case_by_id[row["case_id"]][dimension])
            grouped.setdefault(group, []).append(row)
        summary[output_key] = {
            name: _metrics(group_rows) for name, group_rows in sorted(grouped.items())
        }
    return summary


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    freeze = commands.add_parser(
        "freeze-challenge",
        help="copy only patent evidence from one existing run into a public challenge fixture",
    )
    freeze.add_argument("source", type=Path)
    freeze.add_argument("output", type=Path)
    freeze.add_argument("--corpus", required=True)
    freeze.add_argument("--selection-note", required=True)

    prepare = commands.add_parser("prepare", help="create a blank human-label packet")
    prepare.add_argument("fixtures", type=Path)
    prepare.add_argument("packet", type=Path)
    prepare.add_argument("--challenge", action="append", default=[], type=Path)

    summarize = commands.add_parser("summarize", help="validate labels and write metrics")
    summarize.add_argument("labels", type=Path)
    summarize.add_argument("manifest", type=Path)
    summarize.add_argument("output", type=Path)
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    if args.command == "freeze-challenge":
        result = freeze_challenge(
            args.source,
            args.output,
            corpus=args.corpus,
            selection_note=args.selection_note,
        )
    elif args.command == "prepare":
        result = prepare_packet(
            args.fixtures,
            args.packet,
            challenge_paths=args.challenge,
        )
    else:
        result = summarize_labels(args.labels, args.manifest)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
