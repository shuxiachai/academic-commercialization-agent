"""Part R: read the two arms' registries side by side, issuer by issuer.

    uv run python -m evals.market_issuer_share_v1.compare --out <dir> [--json compare.json]

Run from this branch, so the measures use the rule under test. For each case
collected under both arms it reports the market sources each arm lists, the
largest group of sources one issuer holds in each arm, what the new arm's
audit says it held for an issuer's share, which addresses only one arm
lists, and whether the academic and patent sources are the same in both. It
makes no request of any kind.

The list it prints under "To read" is the labelling work the protocol asks
for: every source the new arm held for its issuer's share, with the listed
sources it was tied to, and every market source only one arm lists.

An issuer still over its share in the new arm is expected only where a held
release returned to a slot nothing else filled. ``unexplained`` counts the
cases where that is not what the audit shows: a defect in the wiring.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from academic_agent.market_selection import MARKET_SOURCES_PER_ISSUER
from evals.market_selection_v1 import compare as base
from scripts.audits.market_evidence_audit import issuer_groups

CASES = Path(__file__).with_name("cases.json")
ISSUER_NOTE = "deferred (issuer share"
# The other notes of the market stage, listed so a reader sees what else moved a source.
NOTE_KINDS = (ISSUER_NOTE, "duplicate story", "deferred (site share")
PROMOTION = "[Deferred-Promotion]"


def issuer_measure(registry: dict) -> dict:
    """The issuers that state themselves more than once among a registry's market sources."""
    market = registry.get("market_sources") or []
    groups = issuer_groups(market)
    promoted = {source_id for audit in registry.get("audit") or []
                if audit.get("domain") == "market" and audit.get("query") == PROMOTION
                for source_id in audit.get("accepted_source_ids") or []}
    over = [group for group in groups if len(group) > MARKET_SOURCES_PER_ISSUER]
    return {
        "largest_issuer_group": max((len(group) for group in groups), default=1 if market else 0),
        "issuers_over_their_share": len(over),
        # Over its share with no member that waited and returned to an empty slot.
        "unexplained": sum(1 for group in over if not any(row.get("source_id") in promoted for row in group)),
        "groups": [[str(row.get("url")) for row in group] for group in groups],
    }


def compare_case(out: Path, case: str) -> dict:
    row = base.compare_case(out, case)
    if row is None or "missing" in row:
        return row
    registries = {arm: json.loads((out / arm / case / "validated_sources.json").read_text(encoding="utf-8"))
                  for arm in ("old", "new")}
    for arm, registry in registries.items():
        row[arm].update(issuer_measure(registry))
    row["new_arm_notes"] = [
        reason for audit in registries["new"].get("audit") or [] if audit.get("domain") == "market"
        for reason in audit.get("rejected_reasons") or [] if reason.startswith(NOTE_KINDS)]
    row["held_for_an_issuer"] = sum(1 for note in row["new_arm_notes"] if note.startswith(ISSUER_NOTE))
    return row


def render(rows: list[dict]) -> str:
    lines = ["| Case | Market sources | Largest issuer group | Issuers over their share | Held for an issuer | "
             "Largest site | Undated | Same academic / patent |",
             "|---|---:|---:|---:|---:|---:|---:|---|"]
    for row in rows:
        if "missing" in row:
            lines.append(f"| {row['case']} | not comparable: {row['missing']} | | | | | | |")
            continue
        cells = {key: f"{row['old'][key]} -> {row['new'][key]}"
                 for key in ("market_sources", "largest_issuer_group", "issuers_over_their_share", "largest_site", "undated")}
        lines.append(
            f"| {row['case']} | {cells['market_sources']} | {cells['largest_issuer_group']} | "
            f"{cells['issuers_over_their_share']} | {row['held_for_an_issuer']} | {cells['largest_site']} | "
            f"{cells['undated']} | "
            f"{'yes' if row['academic_identical'] else 'NO'} / {'yes' if row['patent_identical'] else 'NO'} |")
    done = [row for row in rows if "missing" not in row]
    lines += ["", f"Cases compared: {len(done)} of {len(rows)}."]
    for arm in ("old", "new"):
        lines.append(
            f"- {arm}: {sum(r[arm]['market_sources'] for r in done)} market sources; "
            f"{sum(1 for r in done if r[arm]['issuers_over_their_share'])} cases have an issuer over its share; "
            f"{sum(1 for r in done if r[arm]['over_site_share'])} cases have a site over its share; "
            f"{sum(r[arm]['undated'] for r in done)} undated; "
            f"{sum(1 for r in done if r[arm]['market_domain_failed'])} cases lost the market domain.")
    lines.append(
        f"- new arm: {sum(r['held_for_an_issuer'] for r in done)} sources held for an issuer's share in "
        f"{sum(1 for r in done if r['held_for_an_issuer'])} cases; issuers over their share with no returned "
        f"release to explain it: {sum(r['new']['unexplained'] for r in done)}.")
    lines += ["", "## To read", ""]
    for row in done:
        if not (row["new_arm_notes"] or row["only_new"] or row["only_old"]):
            continue
        lines.append(f"### {row['case']}")
        lines += [f"- note: {note}" for note in row["new_arm_notes"]]
        for group in row["new"]["groups"]:
            lines.append("- one issuer in the new arm:")
            lines += [f"  - {url}" for url in group]
        lines += [f"- only the old arm lists: {entry['url']}" for entry in row["only_old"]]
        lines += [f"- only the new arm lists: {entry['url']}" for entry in row["only_new"]]
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    rows = [compare_case(args.out, case["id"]) for case in cases]
    print(render(rows))
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
