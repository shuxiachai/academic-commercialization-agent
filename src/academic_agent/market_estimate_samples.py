"""Prepare attributable market samples without inventing real-world labels.

Synthetic controls exercise a declared comparison contract. Snapshot candidates
retain literal saved source summaries, not externally verified primary text.
The two denominators never mix; neither is a replacement scoring guardrail.
"""

from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re


VERSION = "market-estimate-samples-v1"
DIMENSIONS = ("metric", "currency", "year", "geography", "market_scope",
              "time_basis", "price_basis", "measurement_basis")
_MAX_BYTES = 4 * 1024 * 1024
_AMOUNT = re.compile(r"\b(?:USD|EUR|GBP|CNY|JPY|CAD|AUD)\s+\d[\d,]*(?:\.\d+)?\s+(?:billion|million)\b", re.I)
_MONEY = re.compile(r"(USD|EUR|GBP|CNY|JPY|CAD|AUD) ([0-9]+(?:\.[0-9]+)?) (billion|million)")


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _read(path: Path) -> tuple[dict, str]:
    with path.open("rb") as handle:
        raw = handle.read(_MAX_BYTES + 1)
    if len(raw) > _MAX_BYTES:
        raise ValueError("oversized sample input")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("sample input must be an object")
    return value, _digest(raw)


def _control_observation(value: dict) -> tuple[dict, Decimal]:
    """Validate literal anchors, not the truth of a purported expert judgment.

Control prose is deliberately rigid and synthetic. This parser is not used to
extract facts from market websites, model-written findings or human reviews.
Unknown annotations remain null, including when both sides omit the same key.
"""
    if not isinstance(value, dict) or value.get("origin") != "synthetic":
        raise ValueError("only synthetic observations can carry control labels")
    text, annotations = value.get("text"), value.get("annotations")
    if not isinstance(text, str) or not text or len(text) > 8000:
        raise ValueError("invalid control text")
    if not isinstance(annotations, dict) or set(annotations) != set(DIMENSIONS):
        raise ValueError("control dimensions are incomplete")
    clauses = text.split(";")
    if clauses[-1] != "":
        raise ValueError("unterminated control clause")
    bindings = {}
    for clause in clauses[:-1]:
        key, separator, literal = clause.strip().partition("=")
        if not separator or key in bindings or key not in {*DIMENSIONS, "amount"}:
            raise ValueError("ambiguous control clause")
        bindings[key] = literal
    for key, annotation in annotations.items():
        if annotation is not None and (not isinstance(annotation, str) or not annotation.strip()
                                       or len(annotation) > 120):
            raise ValueError("invalid control annotation")
        # Exact labelled clauses prevent an amount/year elsewhere in the text
        # from supplying an unrelated slot. They do not prove semantic entailment.
        if annotation is not None and bindings.get(key) != annotation:
            raise ValueError("annotation is not bound to its literal clause")
        if annotation is not None and annotation.casefold() in {"unknown", "n/a", "none", "not stated"}:
            raise ValueError("unknown dimensions must be null")
    for key, allowed in (("time_basis", {"observed", "estimate", "forecast"}),
                         ("measurement_basis", {"annual_revenue", "annual_shipments_value"})):
        if annotations[key] is not None and annotations[key] not in allowed:
            raise ValueError("unsupported control basis")
    pricing = annotations["price_basis"]
    if pricing is not None and pricing != "nominal" and not re.fullmatch(r"constant_(?:19|20)\d{2}", pricing):
        raise ValueError("unsupported control price basis")
    money = value.get("amount")
    match = _MONEY.fullmatch(money) if isinstance(money, str) else None
    if not match or bindings.get("amount") != money:
        raise ValueError("amount is not a supported literal point")
    number = Decimal(match[2]) / (1000 if match[3] == "million" else 1)
    if number <= 0 or not number.is_finite():
        raise ValueError("nonpositive control amount")
    if annotations["currency"] is not None and annotations["currency"] != match[1]:
        raise ValueError("currency and amount disagree")
    if annotations["year"] is not None and not re.fullmatch(r"(?:19|20)\d{2}", annotations["year"]):
        raise ValueError("unsupported control period")
    for key in ("source_family", "source_id"):
        if not isinstance(value.get(key), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", value[key]):
            raise ValueError("invalid control source identity")
    return annotations, number


def compare_control(left: dict, right: dict) -> dict:
    """Compare fully declared synthetic dimensions; never infer missing ones."""
    a, x = _control_observation(left)
    b, y = _control_observation(right)
    missing = [key for key in DIMENSIONS if a[key] is None or b[key] is None]
    mismatched = [key for key in DIMENSIONS if a[key] is not None and b[key] is not None and a[key] != b[key]]
    if a["metric"] not in {None, "market_size"} or b["metric"] not in {None, "market_size"}:
        mismatched.append("not_market_size")
    if left["source_family"] == right["source_family"]:
        mismatched.append("same_source_family")
    if left["source_id"] == right["source_id"]:
        mismatched.append("same_source_id")
    # Missing and explicitly different are distinct outcomes, not two varieties
    # of agreement. No ratio (and no score) is emitted for either condition.
    if missing:
        verdict, ratio = "insufficient_information", None
    elif mismatched:
        verdict, ratio = "incomparable", None
    else:
        ratio = str(max(x, y) / min(x, y))
        verdict = "comparable_spread" if max(x, y) > 5 * min(x, y) else "comparable_no_spread"
    return {"verdict": verdict, "ratio": ratio, "missing": missing, "mismatched": mismatched}


def evaluate_controls(bundle: dict) -> dict:
    if bundle.get("version") != VERSION or bundle.get("origin") != "synthetic_engineering_controls":
        raise ValueError("unsupported control provenance")
    cases = bundle.get("cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 64:
        raise ValueError("empty or oversized control cohort")
    rows, seen = [], set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or case["id"] in seen:
            raise ValueError("invalid or duplicate control identity")
        seen.add(case["id"])
        try:
            actual = compare_control(case.get("left"), case.get("right"))
            expected = case.get("expected")
            if not isinstance(expected, dict) or set(expected) != set(actual):
                raise ValueError("missing full control expectation")
            rows.append({"id": case["id"], "status": "checked", "actual": actual,
                         "expected": expected, "contract_matches": actual == expected})
        except (ValueError, ArithmeticError) as exc:
            # Malformed cases remain in the denominator. Parser errors must not
            # print private input text, even if a local operator uses this CLI.
            rows.append({"id": case["id"], "status": "unavailable", "error_type": type(exc).__name__})
    checked = [row for row in rows if row["status"] == "checked"]
    return {"version": VERSION, "origin": bundle["origin"], "production_effect": "none",
            "independent_accuracy": "not_measured", "cases": rows,
            "summary": {"cases": len(rows), "checked": len(checked), "unavailable": len(rows) - len(checked),
                        "contract_matches": sum(row["contract_matches"] for row in checked),
                        "verdicts": dict(Counter(row["actual"]["verdict"] for row in checked))}}


def prepare_snapshot(root: Path) -> dict:
    """Choose at most two literal source summaries per topic, keeping failures.

    Selection is sorted, deterministic convenience sampling, not random/held-out
    evaluation. Exact repeated topic/URL pairs do not add samples; different
    URLs can still repeat or syndicate the same original evidence.
No value from the model-written claim or its category is promoted to a label.
"""
    if not root.is_dir():
        raise ValueError("snapshot unavailable")
    root = root.resolve()
    units, candidates, seen = [], [], set()
    topic_counts = Counter()
    directories = sorted(p for p in root.iterdir() if p.is_dir())
    if len(directories) > 200:
        raise ValueError("snapshot too large")
    for directory in directories:
        row = {"unit": directory.name, "status": "unavailable", "sha256": {}}
        try:
            # Fixed filenames, bounded reads, and resolution checks keep this
            # inspection inside the chosen corpus even with symlinked inputs.
            paths = [directory / name for name in ("market_evidence.json", "meta.json")]
            if any(not path.resolve().is_relative_to(root) for path in paths):
                raise ValueError("snapshot path escapes selected root")
            report, report_hash = _read(paths[0])
            meta, meta_hash = _read(paths[1])
            row["sha256"] = {"market_evidence.json": report_hash, "meta.json": meta_hash}
            topic, sources = report.get("topic"), report.get("sources")
            mode = meta.get("evidence_mode")
            if not isinstance(topic, str) or not topic.strip() or not isinstance(sources, list) or len(sources) > 100:
                raise ValueError("invalid source collection")
            if not isinstance(mode, str) or mode not in {"live", "fixture"}:
                raise ValueError("unknown snapshot mode")
            ids = set()
            validated = []
            for index, source in enumerate(sources):
                if not isinstance(source, dict) or not isinstance(source.get("source_id"), str):
                    raise ValueError("invalid snapshot source")
                sid, text, url = source["source_id"], source.get("evidence_summary"), source.get("url")
                if not re.fullmatch(r"M[1-9]\d*", sid) or sid in ids or not isinstance(text, str) or not isinstance(url, str) or not url:
                    raise ValueError("invalid or duplicate snapshot source")
                ids.add(sid)
                validated.append((index, sid, text, url))
            row.update(status="available", mode=mode)
            # Validate the entire unit before selecting anything; partial bad
            # units must not quietly contribute rows to a successful cohort.
            for index, sid, text, url in validated:
                if topic_counts[topic] >= 2 or (topic, url) in seen or not _AMOUNT.search(text):
                    continue
                seen.add((topic, url))
                topic_counts[topic] += 1
                candidates.append({
                    "id": f"S{len(candidates) + 1:02}", "origin": "saved_source_summary",
                    "unit": directory.name, "topic": topic, "mode": mode,
                    "source_id": sid, "source_url": url, "source_url_verified": False,
                    "file_sha256": report_hash, "meta_sha256": meta_hash,
                    "json_pointer": f"/sources/{index}/evidence_summary",
                    "text": text, "text_sha256": _digest(text.encode("utf-8")),
                    "amount_candidates": [{"start": m.start(), "end": m.end(), "literal": m[0]} for m in _AMOUNT.finditer(text)],
                    "annotations": dict.fromkeys(DIMENSIONS), "expected": None,
                    "external_verification": "not_performed", "judgment": "unreviewed",
                })
        except (OSError, UnicodeError, ValueError) as exc:
            row["error_type"] = type(exc).__name__
        units.append(row)
    # The source text remains local. This output must not be auto-published or
    # fed into production; hashes bind saved bytes, not publisher identity.
    return {"version": VERSION, "origin": "snapshot_preparation", "production_effect": "none",
            "historical_identity": "not_established", "units": units, "candidates": candidates,
            "summary": {"units": len(units), "available": sum(u["status"] == "available" for u in units),
                        "unavailable": sum(u["status"] != "available" for u in units),
                        "modes": dict(Counter(u.get("mode", "unavailable") for u in units)),
                        "candidates": len(candidates), "topics": len(topic_counts),
                        "reviewed": 0, "externally_verified": 0, "scored_comparisons": 0}}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--controls", type=Path)
    choice.add_argument("--snapshot", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        source = (args.controls or args.snapshot).resolve()
        output = args.output.resolve()
        # Refuse outputs in the input tree and any occupied result directory.
        # A repeat invocation gets a new directory, never revised evidence.
        boundary = source.parent if args.controls else source
        if output == boundary or output.is_relative_to(boundary):
            raise ValueError("output overlaps input")
        if args.controls:
            bundle, digest = _read(source)
            result = evaluate_controls(bundle)
            result["input_sha256"] = digest
        else:
            result = prepare_snapshot(source)
        result["implementation_sha256"] = _digest(Path(__file__).read_bytes())
        output.mkdir(parents=True, exist_ok=False)
        with (output / "samples.json").open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
    except (OSError, UnicodeError, ValueError, ArithmeticError) as exc:
        print(json.dumps({"status": "unavailable", "error_type": type(exc).__name__}))
        return 2
    summary = result["summary"]
    print(json.dumps(summary, sort_keys=True))
    if args.controls:
        return 0 if summary["cases"] == summary["contract_matches"] else 2
    return 0 if summary["units"] and summary["candidates"] and not summary["unavailable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
