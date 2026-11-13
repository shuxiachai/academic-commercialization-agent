"""Part R: read the two arms' registries side by side.

    uv run python evals/market_selection_v1/compare.py --out <dir> [--json compare.json]

Run from this branch, so the measures use the rules under test. For each
case collected under both arms it reports the market sources each arm lists,
what the new arm's audit says it did (copies, replacements, sources held for
their site's share, encyclopedia entries), which addresses only one arm
lists, and whether the academic and patent sources are the same in both. It
makes no request of any kind.

The list it prints under "To read" is the labelling work the protocol asks
for: every pair the new arm called one story, and every market source only
the new arm lists.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date
from pathlib import Path

from academic_agent.market_selection import MARKET_SOURCES_PER_SITE, MarketItem, provenance_rank, same_story, site_of

NOTE_KINDS = ("duplicate story", "deferred (site share", "encyclopedia entry is not market evidence")


def _item(row: dict) -> MarketItem:
    published = row.get("published_date")
    return MarketItem(str(row.get("title") or ""), str(row.get("url") or ""), str(row.get("evidence_summary") or ""),
                      date.fromisoformat(published[:10]) if published else None)


def measure(registry: dict) -> dict:
    market = registry.get("market_sources") or []
    items = [_item(row) for row in market]
    sites = Counter(site_of(item.url) for item in items)
    return {
        "market_sources": len(market),
        "stories_listed_twice": sum(
            1 for i, a in enumerate(items) for b in items[i + 1:] if same_story(a, b)),
        "largest_site": max(sites.values(), default=0),
        "sites": len(sites),
        "over_site_share": max(sites.values(), default=0) > MARKET_SOURCES_PER_SITE,
        "encyclopedia": sum(1 for item in items if site_of(item.url) == "wikipedia.org"),
        "undated": sum(1 for item in items if item.published is None),
        "on_wire_or_syndicating_hosts": sum(1 for item in items if provenance_rank(item.url) > 0),
        "market_domain_failed": "market" in (registry.get("failed_domains") or {}),
    }


def _keys(rows: list[dict]) -> list[str]:
    return sorted(str(row.get("doi") or row.get("url") or row.get("title")) for row in rows)


def compare_case(out: Path, case: str) -> dict | None:
    loaded = {}
    for arm in ("old", "new"):
        path = out / arm / case / "validated_sources.json"
        if not path.exists():
            meta = out / arm / case / "meta.json"
            error = json.loads(meta.read_text(encoding="utf-8")).get("error") if meta.exists() else "not collected"
            return {"case": case, "missing": {arm: error}}
        loaded[arm] = json.loads(path.read_text(encoding="utf-8"))
    old, new = loaded["old"], loaded["new"]
    old_urls = {row["url"]: row for row in old["market_sources"]}
    new_urls = {row["url"]: row for row in new["market_sources"]}
    notes = [reason for audit in new.get("audit") or [] if audit.get("domain") == "market"
             for reason in audit.get("rejected_reasons") or [] if reason.startswith(NOTE_KINDS)]
    calls = {arm: json.loads((out / arm / case / "calls.json").read_text(encoding="utf-8")) for arm in loaded}
    return {
        "case": case,
        "old": measure(old),
        "new": measure(new),
        "only_old": [{"url": url, "title": row["title"]} for url, row in old_urls.items() if url not in new_urls],
        "only_new": [{"url": url, "title": row["title"], "published_date": row.get("published_date")}
                     for url, row in new_urls.items() if url not in old_urls],
        "newly_dated": [{"url": url, "published_date": row["published_date"]} for url, row in new_urls.items()
                        if row.get("published_date") and url in old_urls and not old_urls[url].get("published_date")],
        "new_arm_notes": notes,
        "academic_identical": _keys(old["academic_sources"]) == _keys(new["academic_sources"]),
        "patent_identical": _keys(old["patent_sources"]) == _keys(new["patent_sources"]),
        "live_requests": {arm: {name: count for name, count in calls[arm].items() if name.endswith(": live")}
                          for arm in calls},
    }


def render(rows: list[dict]) -> str:
    lines = ["| Case | Market sources | Stories twice | Largest site | Encyclopedia | Undated | Same academic / patent |",
             "|---|---:|---:|---:|---:|---:|---|"]
    for row in rows:
        if "missing" in row:
            lines.append(f"| {row['case']} | not comparable: {row['missing']} | | | | | |")
            continue
        cells = " | ".join(
            f"{row['old'][key]} -> {row['new'][key]}"
            for key in ("market_sources", "stories_listed_twice", "largest_site", "encyclopedia", "undated"))
        lines.append(
            f"| {row['case']} | {cells} | "
            f"{'yes' if row['academic_identical'] else 'NO'} / {'yes' if row['patent_identical'] else 'NO'} |")
    done = [row for row in rows if "missing" not in row]
    lines += ["", f"Cases compared: {len(done)} of {len(rows)}."]
    for arm in ("old", "new"):
        lines.append(
            f"- {arm}: {sum(r[arm]['market_sources'] for r in done)} market sources; "
            f"{sum(1 for r in done if r[arm]['stories_listed_twice'])} cases list a story twice; "
            f"{sum(1 for r in done if r[arm]['over_site_share'])} cases have a site over its share; "
            f"{sum(r[arm]['encyclopedia'] for r in done)} encyclopedia entries; "
            f"{sum(r[arm]['undated'] for r in done)} undated; "
            f"{sum(1 for r in done if r[arm]['market_domain_failed'])} cases lost the market domain.")
    lines += ["", "## To read", ""]
    for row in done:
        if not (row["new_arm_notes"] or row["only_new"] or row["only_old"]):
            continue
        lines.append(f"### {row['case']}")
        lines += [f"- note: {note}" for note in row["new_arm_notes"]]
        lines += [f"- only the old arm lists: {entry['url']}" for entry in row["only_old"]]
        lines += [f"- only the new arm lists: {entry['url']}" for entry in row["only_new"]]
        lines += [f"- dated only by the new arm: {entry['published_date']} {entry['url']}" for entry in row["newly_dated"]]
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    cases = json.loads(Path(__file__).with_name("cases.json").read_text(encoding="utf-8"))["cases"]
    rows = [compare_case(args.out, case["id"]) for case in cases]
    print(render(rows))
    if args.json:
        args.json.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
