"""Offline-only diagnostic for the legacy, untyped market variance cap.

This module is deliberately not imported by the Crew or delivery path. A regex
can expose obviously mixed quantities, but cannot establish that two commercial
estimates use the same methodology. Unknown dimensions abstain, and absence of
comparable pairs is not agreement. Changing the calibrated cap needs a separate
decision; this audit neither repairs scores nor authorizes paid reruns.
"""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from decimal import Decimal
import hashlib
from itertools import combinations
import json
import math
from pathlib import Path
import re


VERSION = "market-metric-audit-v1"
# Match the historical grammar, including its lack of currency/unit checking.
# Keeping every occurrence lets a replay explain why the old cap fired. This
# is not a new Chinese/compact-amount parser or a currency conversion service.
_AMOUNT = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(bn|billion|mn|million)", re.I)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_CURRENCY = r"USD|US\s*\$|EUR|€|GBP|£|CNY|RMB|JPY|CAD|C\$|AUD|A\$|\$|¥"
_PREFIX = re.compile(rf"(?<![\w$])({_CURRENCY})\s*$", re.I)
_SUFFIX = re.compile(rf"^\s*({_CURRENCY})(?!\w)", re.I)
_CURRENCIES = {
    "USD": "USD", "US$": "USD", "EUR": "EUR", "€": "EUR",
    "GBP": "GBP", "£": "GBP", "CNY": "CNY", "RMB": "CNY",
    "JPY": "JPY", "CAD": "CAD", "C$": "CAD", "AUD": "AUD", "A$": "AUD",
}
_PHYSICAL = re.compile(
    r"^\s+(?:metric\s+)?(?:tonnes?|tons?|molecules?|cells?|users?|units?|vehicles?|people)\b", re.I,
)
_SIGNALS = {
    "funding": re.compile(r"\b(?:funding|funded|raised|investments?|invested|capital|financing)\b", re.I),
    "acquisition": re.compile(r"\b(?:acquisitions?|acquired|buyout)\b", re.I),
    "revenue": re.compile(r"\brevenues?\b", re.I),
    "cost": re.compile(r"\b(?:costs?|prices?|capex|expenditure)\b", re.I),
    "valuation": re.compile(r"\bvaluation\b", re.I),
    "market_size": re.compile(r"\bmarket\b", re.I),
}
_GEO = r"global|worldwide|U\.S\.|United States|North America|Asia Pacific|Europe|China"
_GEO_ALIASES = {"worldwide": "global", "u.s.": "united states"}
_GEOGRAPHY = re.compile(rf"(?<!\w)({_GEO})(?!\w)", re.I)
# Exact lexical scope, never the report topic: the latter would merge a niche
# into its parent market. Multiple phrases, mixed metrics or multi-year prose
# abstain instead of guessing which qualifier belongs to the nearest number.
_SCOPE = re.compile(rf"(?<!\w)(?:{_GEO})\s+([\w()/-]+(?:\s+[\w()/-]+){{0,15}}?)\s+market\b", re.I)
_SUBYEAR = re.compile(
    r"\bQ[1-4]\b|\bFY\b|\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b"
    r"|\b(?:19|20)\d{2}\s*[-–/]\s*\d{2}\b", re.I,
)
_BOUND = re.compile(rf"\b(?:over|under|at least|at most|up to|more than|less than)\s*(?:{_CURRENCY})?\s*$", re.I)
_MAX_BYTES = 4 * 1024 * 1024


def _currency(text: str, match: re.Match) -> str | None:
    labels = []
    for found in (_PREFIX.search(text[:match.start()]), _SUFFIX.search(text[match.end():])):
        if found:
            labels.append(_CURRENCIES.get(re.sub(r"\s", "", found[1]).upper()))
    # A bare $ or yen symbol is intentionally ambiguous, even in a US report.
    return labels[0] if labels and labels[0] and len(set(labels)) == 1 else None


def _legacy_value(row: dict) -> float:
    # Replay the historical float division too: 78.6 million became
    # 0.07859999999999999 billion there, not Decimal('0.0786'). Typed comparisons
    # use Decimal separately; calling the decimal result a bit-exact legacy
    # replay would misdescribe a real difference at threshold boundaries.
    match = _AMOUNT.fullmatch(row["raw"])
    value = float(match[1].replace(",", ""))
    if match[2].lower() in {"mn", "million"}:
        value /= 1000
    if not math.isfinite(value):
        raise ValueError("non-finite legacy quantity")
    return value


def _observations(text: str, path: str, source_ids: list[str], known: set[str], *, finding: bool) -> list[dict]:
    matches = list(_AMOUNT.finditer(text))
    years = set(_YEAR.findall(text))
    year = next(iter(years)) if len(years) == 1 and not _SUBYEAR.search(text) else None
    geos = {_GEO_ALIASES.get(m[0].lower(), m[0].lower()) for m in _GEOGRAPHY.finditer(text)}
    geo = next(iter(geos)) if len(geos) == 1 else None
    scopes = {" ".join(m[1].lower().split()) for m in _SCOPE.finditer(text)}
    scope = next(iter(scopes)) if len(scopes) == 1 else None
    signals = [name for name, pattern in _SIGNALS.items() if pattern.search(text)]
    rows = []
    for match in matches:
        amount = Decimal(match[1].replace(",", ""))
        if match[2].lower() in {"mn", "million"}:
            amount /= 1000
        physical = bool(_PHYSICAL.match(text[match.end():]))
        metric = "non_monetary" if physical else signals[0] if len(signals) == 1 else "unknown"
        currency = _currency(text, match)
        reasons = []
        # Multiple amounts may be a range or different subjects even within a
        # single year. Do not invent attribution, or compare bounds as points.
        if len(matches) != 1:
            reasons.append("multiple_amounts_unattributed")
        if _BOUND.search(text[:match.start()]):
            reasons.append("bound_not_point_estimate")
        if not finding:
            reasons.append("context_only_not_independent_estimate")
        if metric != "market_size":
            reasons.append("metric_not_market_size" if metric != "unknown" else "metric_unknown_or_mixed")
        if currency is None:
            reasons.append("currency_unknown_or_conflicting")
        if year is None:
            reasons.append("period_unknown_or_multiple")
        if geo is None:
            reasons.append("geography_unknown_or_multiple")
        if scope is None:
            reasons.append("market_scope_unknown_or_multiple")
        if len(source_ids) != 1 or source_ids[0] not in known:
            reasons.append("single_registered_source_required")
        # The legacy grammar drops signs. Preserve its magnitude for parity,
        # but do not turn a negative amount/range endpoint into an estimate.
        if amount <= 0 or re.search(r"[-−–+]\s*$", text[:match.start()]):
            reasons.append("nonpositive_or_range_or_signed_amount")
        rows.append({
            "path": path, "start": match.start(), "end": match.end(), "raw": match[0],
            "amount_billions": str(amount), "metric": metric, "currency": currency,
            "year": year, "geography": geo, "market_scope": scope,
            "source_ids": source_ids, "eligible": not reasons, "reasons": reasons,
        })
    return rows


def analyze_report(report: dict) -> dict:
    """Return a typed diagnostic, not an alternative score or a semantic label.

    Findings are the comparison surface; limitations/summaries still explain
    legacy extrema but cannot count as additional, independent estimates.
    A finding citing multiple sources cannot identify which supplied a number.
    """
    if not isinstance(report, dict) or not isinstance(report.get("topic"), str):
        raise ValueError("invalid report")
    findings, sources = report.get("findings"), report.get("sources")
    if not isinstance(findings, list) or not isinstance(sources, list) or len(findings) + len(sources) > 500:
        raise ValueError("invalid report collections")
    known = set()
    for source in sources:
        if not isinstance(source, dict) or not isinstance(source.get("source_id"), str):
            raise ValueError("invalid source")
        sid = source["source_id"]
        if not re.fullmatch(r"M[1-9]\d*", sid) or sid in known:
            raise ValueError("invalid or duplicate market source")
        known.add(sid)
    rows = []
    for index, item in enumerate(findings):
        if not isinstance(item, dict):
            raise ValueError("invalid finding")
        ids = item.get("source_ids")
        if not isinstance(ids, list) or not all(isinstance(sid, str) for sid in ids):
            raise ValueError("invalid finding sources")
        for field in ("claim", "limitations"):
            text = item.get(field)
            if field == "limitations" and text is None:
                continue
            if not isinstance(text, str):
                raise ValueError("invalid finding text")
            rows.extend(_observations(text, f"findings[{index}].{field}", ids, known, finding=field == "claim"))
    for index, item in enumerate(sources):
        if not isinstance(item.get("evidence_summary"), str):
            raise ValueError("invalid source summary")
        rows.extend(_observations(item["evidence_summary"], f"sources[{index}].evidence_summary",
                                  [item["source_id"]], known, finding=False))
    if len(rows) > 1000:
        raise ValueError("too many amount observations")
    for index, row in enumerate(rows):
        row["id"] = index
    values = [value for row in rows if (value := _legacy_value(row)) > 0]
    legacy_ratio = max(values) / min(values) if len(values) >= 2 else None
    # Repeated quotations from one registered source are not independent votes.
    # Group by the complete observation identity, then require different IDs;
    # distinct IDs still do not prove independent publishers/methodologies.
    unique = {}
    for row in rows:
        if row["eligible"]:
            key = (*[row[k] for k in ("currency", "year", "geography", "market_scope")], Decimal(row["amount_billions"]))
            unique.setdefault((*key, row["source_ids"][0]), row)
    pairs, skipped = [], Counter()
    for left, right in combinations(unique.values(), 2):
        reasons = [key for key in ("currency", "year", "geography", "market_scope") if left[key] != right[key]]
        if left["source_ids"] == right["source_ids"]:
            reasons.append("same_source")
        if reasons:
            skipped.update(reasons)
            continue
        a, b = Decimal(left["amount_billions"]), Decimal(right["amount_billions"])
        ratio = max(a, b) / min(a, b)
        pairs.append({"left": left["id"], "right": right["id"], "ratio": str(ratio), "above_five": ratio > 5})
    verdict = "not_assessed" if not pairs else "spread_candidate" if any(p["above_five"] for p in pairs) else "no_spread_in_checked_pairs"
    return {
        "version": VERSION, "status": "available", "production_effect": "none",
        "legacy_untyped": {"positive_occurrences": len(values), "ratio": str(legacy_ratio) if legacy_ratio is not None else None,
                           "above_five": legacy_ratio is not None and legacy_ratio > 5},
        "metric_counts": dict(sorted(Counter(row["metric"] for row in rows).items())),
        "comparison": {"verdict": verdict, "eligible_occurrences": sum(row["eligible"] for row in rows),
                       "excluded_occurrences": sum(not row["eligible"] for row in rows),
                       "pairs": pairs, "skipped_pair_reasons": dict(sorted(skipped.items()))},
        "observations": rows,
    }


def _read(path: Path, inputs: dict) -> dict:
    with path.open("rb") as handle:
        data = handle.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        raise ValueError("input too large")
    inputs[path.name] = hashlib.sha256(data).hexdigest()
    value = json.loads(data)
    if not isinstance(value, dict):
        raise ValueError("invalid input object")
    return value


def audit_directory(root: Path) -> dict:
    """Read each unit, including incomplete/corrupt units, without rewriting it."""
    if not root.is_dir():
        raise ValueError("input directory unavailable")
    units = []
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        row = {"unit": directory.name, "input_sha256": {}}
        try:
            report = _read(directory / "market_evidence.json", row["input_sha256"])
            row["audit"] = analyze_report(report)
        except (OSError, UnicodeError, ValueError, ArithmeticError) as exc:
            # A broken artifact stays in the denominator. Do not expose file
            # contents through JSON decoder errors or replace it with []/pass.
            row["audit"] = {"status": "unavailable", "error_type": type(exc).__name__}
        for filename, field in (("meta.json", "meta"), ("commercialization_scores.json", "score")):
            try:
                data = _read(directory / filename, row["input_sha256"])
                if field == "meta":
                    mode = data.get("evidence_mode")
                    num, rep = data.get("num"), data.get("rep")
                    row[field] = {
                        "status": "available", "evidence_mode": mode if mode in {"live", "fixture"} else "unknown",
                        "case_num": num if isinstance(num, str) and re.fullmatch(r"\d{2}", num) else None,
                        "rep": rep if type(rep) is int and rep > 0 else None,
                    }
                else:
                    saved = data.get("market_accessibility")
                    valid = type(saved) in {float, int} and 1 <= saved <= 5
                    row[field] = {"status": "available" if valid else "unavailable",
                                  "market_accessibility": saved if valid else None,
                                  "cap_effect": "not_reconstructable_without_pre_cap_score"}
            except (OSError, UnicodeError, ValueError) as exc:
                row[field] = {"status": "unavailable", "error_type": type(exc).__name__}
        units.append(row)
    available = [row for row in units if row["audit"]["status"] == "available"]
    observations = [item for row in available for item in row["audit"]["observations"]]
    result = {
        "version": VERSION, "execution": "offline_only", "production_effect": "none",
        "implementation_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "summary": {
            "units": len(units), "available": len(available), "unavailable": len(units) - len(available),
            "legacy_above_five": sum(row["audit"]["legacy_untyped"]["above_five"] for row in available),
            "verdicts": dict(Counter(row["audit"]["comparison"]["verdict"] for row in available)),
            "meta_modes": dict(Counter(row["meta"].get("evidence_mode", "unavailable") for row in units)),
            "score_states": dict(Counter(row["score"]["status"] for row in units)),
            "metric_occurrences": dict(sorted(Counter(item["metric"] for item in observations).items())),
            "exclusion_reasons": dict(sorted(Counter(reason for item in observations for reason in item["reasons"]).items())),
        },
        "units": units,
    }
    csv_path = root / "benchmark_summary.csv"
    if csv_path.is_file():
        # The CSV is a separate historical artifact, not proof that the local
        # unit files are still its original inputs. Bind both, never overwrite.
        data = csv_path.read_bytes()
        result["archived_csv_sha256"] = hashlib.sha256(data).hexdigest()
        rows = list(csv.DictReader(data.decode("utf-8-sig").splitlines()))
        result["archived_csv_modes"] = dict(Counter(row.get("evidence_mode", "unknown") for row in rows))
        mismatches = []
        for unit in units:
            meta = unit["meta"]
            matches = [row for row in rows if meta.get("case_num") is not None
                       and row.get("case_num") == meta["case_num"] and row.get("rep") == str(meta.get("rep"))]
            if len(matches) == 1 and matches[0].get("evidence_mode") != meta.get("evidence_mode"):
                mismatches.append(unit["unit"])
        result["archived_csv_mode_mismatches"] = mismatches
        result["historical_identity"] = "not_established_by_matching_csv_labels"
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New directory; existing paths are refused")
    args = parser.parse_args(argv)
    try:
        root, output = args.input.resolve(), args.output.resolve()
        if output == root or output.is_relative_to(root):
            raise ValueError("output cannot be inside input")
        result = audit_directory(root)
        output.mkdir(parents=True, exist_ok=False)
        with (output / "audit.json").open("x", encoding="utf-8") as handle:
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "unavailable", "error_type": type(exc).__name__}))
        return 2
    print(json.dumps(result["summary"], sort_keys=True))
    return 0 if result["summary"]["units"] and not result["summary"]["unavailable"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
