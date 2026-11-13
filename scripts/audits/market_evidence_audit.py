"""Measure the market sources of saved runs, and replay the selection rules on them.

Reads only ``validated_sources.json`` and ``commercialization_scores.json``
under a directory of finished runs; it never searches, fetches a page or
calls a model. Two things come out:

1. **As saved.** Per window: how many runs list one story twice, how many
   let one site hold three or more market slots, how the sources divide by
   site and kind, how many carry no date and why, and what the market cap
   did to the scorecards.
2. **Replayed.** ``market_selection``'s rules, imported from the pipeline and
   applied to each run's saved market sources in their saved order: which
   sources the run would no longer list (a second copy of a story, an
   encyclopedia entry) and which would wait for a slot (a third source from
   one site).

The replay is exact about what leaves and silent about what arrives. A run's
audit keeps a rejected candidate's title and nothing else, and results past a
query's source limit were never read, so the sources that would take the
freed slots are not on disk. Site concentration after the change is therefore
reported as a range: every waiting source replaced by another site's result,
or none of them (each then returns to its slot, as the pipeline does when
nothing else fills it).

A registry copied into several directories is counted once (identical
bytes), and a registry with no market source is not a run for this purpose;
both counts are printed.

``--page-date-probes`` adds a check of the page-date rule against saved page
probes (``evals/market_dates_v1/*_probe.json``): for each probed page on a
press wire or syndicating host, whether the date its metadata states agrees
with the dateline the release itself prints in the saved excerpt
("Dublin, Oct. 20, 2026 (GLOBE NEWSWIRE) --"). The dateline is read only to
check the metadata; the pipeline never dates a source from prose.

    uv run python -m scripts.audits.market_evidence_audit outputs --since 2026-10-01 --since 2026-11-01
    uv run python -m scripts.audits.market_evidence_audit outputs --since 2026-10-01 --pairs
    uv run python -m scripts.audits.market_evidence_audit outputs --since 2026-10-01 --json out.json
    uv run python -m scripts.audits.market_evidence_audit outputs --since 2026-01-01 \
        --page-date-probes evals/market_dates_v1/dev_probe.json evals/market_dates_v1/test_probe.json
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from academic_agent.market_selection import (
    MARKET_SOURCES_PER_SITE,
    MarketItem,
    prefer,
    provenance_rank,
    same_story,
    site_of,
)
from academic_agent.page_dates import should_date
from academic_agent.source_pipeline import _ENCYCLOPEDIA_DOMAINS, _host_matches

REGISTRY = "validated_sources.json"
SCORECARD = "commercialization_scores.json"
# The score at which the market cap holds market_accessibility.
MARKET_CAP = 3.5
# Titles at least this alike are what a title-only rule would have merged.
SIMILAR_TITLE = 0.75
_WORD = re.compile(r"[a-z0-9]+")
_MONTHS = ("Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
           "|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?")
# A press release's dateline: a full date directly before the wire's mark.
_DATELINE = re.compile(
    rf"\b({_MONTHS})\.?\s+(\d{{1,2}}),\s+((?:19|20)\d{{2}})\s*"
    r"(?:\(GLOBE NEWSWIRE\)|/PRNewswire/|(?:--)?\(BUSINESS WIRE\)|/CNW/|\(ACCESSWIRE\)|\(Newsfile Corp\.)",
    re.IGNORECASE,
)


@dataclass
class Run:
    """One saved run's market sources, audit rows and scorecard."""

    path: str
    collected_at: str
    market: list[dict[str, Any]]
    audit: list[dict[str, Any]] = field(default_factory=list)
    scorecard: dict[str, Any] | None = None


@dataclass
class Replay:
    """What the selection rules do to one run's saved market sources."""

    kept: list[dict[str, Any]] = field(default_factory=list)
    # (the copy no longer listed, the copy listed, why they are one story)
    duplicates: list[tuple[dict[str, Any], dict[str, Any], str]] = field(default_factory=list)
    encyclopedia: list[dict[str, Any]] = field(default_factory=list)
    # Sources past their site's share: listed only if nothing else fills the slot.
    waiting: list[dict[str, Any]] = field(default_factory=list)


def load_runs(root: Path, since: str) -> tuple[list[Run], dict[str, int]]:
    """Every distinct registry under ``root`` collected on or after ``since``.

    Returns the runs that list at least one market source, oldest first, and
    the counts of what was set aside.
    """
    seen: set[str] = set()
    runs: list[Run] = []
    skipped = Counter()
    for path in sorted(root.rglob(REGISTRY)):
        raw = path.read_bytes()
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            skipped["unreadable"] += 1
            continue
        if not isinstance(data, dict) or str(data.get("collected_at") or "") < since:
            continue
        digest = hashlib.sha256(raw).hexdigest()
        if digest in seen:
            skipped["copies of a registry already counted"] += 1
            continue
        seen.add(digest)
        market = [row for row in data.get("market_sources") or [] if isinstance(row, dict)]
        if not market:
            skipped["registries with no market source"] += 1
            continue
        scorecard = None
        score_path = path.with_name(SCORECARD)
        if score_path.exists():
            try:
                loaded = json.loads(score_path.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                loaded = None
            if isinstance(loaded, dict) and "market_accessibility" in loaded:
                scorecard = loaded
        runs.append(Run(
            path=path.parent.relative_to(root).as_posix(),
            collected_at=str(data["collected_at"]),
            market=market,
            audit=[row for row in data.get("audit") or []
                   if isinstance(row, dict) and row.get("domain") == "market"],
            scorecard=scorecard,
        ))
    runs.sort(key=lambda run: (run.collected_at, run.path))
    return runs, dict(skipped)


def _item(row: dict[str, Any]) -> MarketItem:
    published = row.get("published_date")
    return MarketItem(
        title=str(row.get("title") or ""),
        url=str(row.get("url") or ""),
        summary=str(row.get("evidence_summary") or ""),
        published=date.fromisoformat(published[:10]) if isinstance(published, str) and published else None,
    )


def _host(row: dict[str, Any]) -> str:
    return (urlsplit(str(row.get("url") or "")).hostname or "").lower()


def replay(run: Run) -> Replay:
    """Apply the pipeline's rules to a run's saved market sources, in saved order.

    The kind caps (institutional, market report) are not replayed: the saved
    list is what they already produced. A waiting source is not put back
    here, because whether a slot stays empty depends on results not on disk.
    """
    result = Replay()
    for row in run.market:
        if _host_matches(_host(row), _ENCYCLOPEDIA_DOMAINS):
            result.encyclopedia.append(row)
            continue
        candidate = _item(row)
        # A waiting source is compared too: the pipeline drops a held copy
        # when it comes to promote it.
        copy = next(
            ((listed, index, kept, why)
             for listed in (result.kept, result.waiting)
             for index, kept in enumerate(listed)
             if (why := same_story(candidate, _item(kept)))),
            None,
        )
        if copy is not None:
            listed, index, kept, why = copy
            if prefer(candidate, _item(kept)):
                listed[index] = row
                result.duplicates.append((kept, row, why))
            else:
                result.duplicates.append((row, kept, why))
            continue
        site = site_of(candidate.url)
        if site and sum(site_of(str(kept.get("url") or "")) == site for kept in result.kept) >= MARKET_SOURCES_PER_SITE:
            result.waiting.append(row)
            continue
        result.kept.append(row)
    return result


def _undated_reason(run: Run, row: dict[str, Any]) -> str:
    """Why a saved market source carries no date, from the run's own audit.

    The run's "[Page-Dates]" note for the source comes first: it records what
    happened. Without one the page was not read, and the reason is the rule
    of the day. Until 2026-11-13 that rule read no market report's page; it
    now reads those on a wire or syndicating host, which is why the two kinds
    of report page are counted apart here.
    """
    page_rows = [a for a in run.audit if str(a.get("query") or "").startswith("[Page-Dates]")]
    for audit in page_rows:
        for reason in audit.get("rejected_reasons") or []:
            source_id, _, text = str(reason).partition(": ")
            if source_id == row.get("source_id"):
                return "page not read in time" if text.startswith("page not read within") else text
    if row.get("source_type") == "market_report":
        carrier = provenance_rank(str(row.get("url") or "")) > 0
        return ("not read: market report on a wire or syndicating host" if carrier
                else "not read: market report on its publisher's page")
    if not should_date(row.get("source_type"), row.get("url")):
        if _host_matches(_host(row), _ENCYCLOPEDIA_DOMAINS):
            return "not read: encyclopedia entry"
        return "not read: home page"
    if not page_rows:
        return "run predates page dating"
    return "no note in the audit"


def _similar_title_pairs(run: Run) -> tuple[int, int]:
    """(pairs of a run's sources with alike titles, how many of them are one story)."""
    alike = same = 0
    rows = run.market
    for index, first in enumerate(rows):
        for second in rows[index + 1:]:
            a = " ".join(_WORD.findall(str(first.get("title") or "").lower()))
            b = " ".join(_WORD.findall(str(second.get("title") or "").lower()))
            if a and b and difflib.SequenceMatcher(None, a, b).ratio() >= SIMILAR_TITLE:
                alike += 1
                same += bool(same_story(_item(first), _item(second)))
    return alike, same


def dateline(text: str) -> date | None:
    """The date a press release prints before its wire's mark, if the text has one."""
    match = _DATELINE.search(text or "")
    if not match:
        return None
    try:
        return datetime.strptime(
            f"{match.group(1)[:3].title()} {match.group(2)} {match.group(3)}", "%b %d %Y").date()
    except ValueError:
        return None


def page_date_agreement(runs: list[Run], probe_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare probed page-metadata dates with the datelines in saved excerpts.

    Only pages on a press wire or syndicating host are counted: those are the
    pages the page-date rule admits for market reports.
    """
    excerpts: dict[str, str] = {}
    for run in runs:
        for row in run.market:
            if row.get("url"):
                excerpts.setdefault(str(row["url"]), str(row.get("evidence_summary") or ""))
    probed = Counter()
    agreement = Counter()
    differing: list[dict[str, str]] = []
    for row in probe_rows:
        url = str(row.get("url") or "")
        if provenance_rank(url) == 0:
            continue
        kind = str(row.get("source_type"))
        probed[(kind, "dated" if row.get("date") else "undated")] += 1
        stated = dateline(excerpts.get(url, ""))
        if not row.get("date") or stated is None:
            continue
        apart = abs((stated - date.fromisoformat(row["date"])).days)
        agreement[(kind, "within a day" if apart <= 1 else "further apart")] += 1
        if apart > 1:
            differing.append({"url": url, "metadata": row["date"], "dateline": stated.isoformat()})
    return {
        "probed_pages_on_wire_or_syndicating_hosts": {f"{kind}: {state}": n for (kind, state), n in sorted(probed.items())},
        "with_a_dateline_in_the_saved_excerpt": {f"{kind}: {state}": n for (kind, state), n in sorted(agreement.items())},
        "differing": differing,
    }


def _max_site_count(rows: list[dict[str, Any]]) -> int:
    counts = Counter(site_of(str(row.get("url") or "")) for row in rows)
    counts.pop("", None)
    return max(counts.values(), default=0)


def measure(runs: list[Run]) -> dict[str, Any]:
    """The window's figures, as saved and under the replayed rules."""
    sources = [row for run in runs for row in run.market]
    replays = [replay(run) for run in runs]
    sites = Counter(site_of(str(row.get("url") or "")) for row in sources)
    undated = [(run, row) for run in runs for row in run.market if not row.get("published_date")]

    scored = [run.scorecard for run in runs if run.scorecard is not None]
    caps = [card.get("market_cap_audit") for card in scored if isinstance(card.get("market_cap_audit"), dict)]

    over_share_runs = [run for run in runs if _max_site_count(run.market) > MARKET_SOURCES_PER_SITE]
    title_pairs = [_similar_title_pairs(run) for run in runs]
    return {
        "runs": len(runs),
        "market_sources": len(sources),
        "as_saved": {
            "pairs_with_alike_titles": sum(alike for alike, _ in title_pairs),
            "pairs_with_alike_titles_that_are_one_story": sum(same for _, same in title_pairs),
            "runs_listing_a_story_twice": sum(1 for r in replays if r.duplicates),
            "slots_holding_a_second_copy": sum(len(r.duplicates) for r in replays),
            "duplicate_signs": dict(Counter(why for r in replays for _, _, why in r.duplicates)),
            "runs_with_a_site_over_its_share": len(over_share_runs),
            "runs_with_an_encyclopedia_entry": sum(1 for r in replays if r.encyclopedia),
            "encyclopedia_sources": sum(len(r.encyclopedia) for r in replays),
            "sources_on_wire_or_syndicating_hosts": sum(
                1 for row in sources if provenance_rank(str(row.get("url") or "")) > 0),
            "top_sites": sites.most_common(8),
            "source_types": dict(Counter(str(row.get("source_type")) for row in sources)),
            "undated_sources": len(undated),
            "undated_reasons": dict(Counter(_undated_reason(run, row) for run, row in undated).most_common()),
        },
        "replayed": {
            "sources_no_longer_listed": sum(len(r.duplicates) + len(r.encyclopedia) for r in replays),
            "sources_waiting_for_a_slot": sum(len(r.waiting) for r in replays),
            "runs_with_a_waiting_source": sum(1 for r in replays if r.waiting),
            "runs_changed": sum(1 for r in replays if r.duplicates or r.encyclopedia or r.waiting),
            "runs_listing_a_story_twice": sum(
                1 for r in replays
                if any(same_story(_item(a), _item(b))
                       for i, a in enumerate(r.kept + r.waiting) for b in (r.kept + r.waiting)[i + 1:])),
            # Every waiting source replaced by another site's result, or none.
            "runs_with_a_site_over_its_share": {
                "if_every_waiting_source_is_replaced": sum(
                    1 for r in replays if _max_site_count(r.kept) > MARKET_SOURCES_PER_SITE),
                "if_none_is_replaced": sum(
                    1 for r in replays if _max_site_count(r.kept + r.waiting) > MARKET_SOURCES_PER_SITE),
            },
            "runs_left_with_fewer_than_two_sources_before_refill": sum(
                1 for r in replays if len(r.kept) + len(r.waiting) < 2),
            "preferred_copy_replaces_listed_copy": sum(
                1 for run, r in zip(runs, replays, strict=True)
                for dropped, kept, _ in r.duplicates
                if run.market.index(dropped) < run.market.index(kept)),
        },
        "scorecards": {
            "scorecards": len(scored),
            "with_a_cap_record": len(caps),
            "cap_triggered": sum(1 for cap in caps if cap.get("triggered")),
            "cap_lowered_the_score": sum(1 for cap in caps if cap.get("applied")),
            "market_accessibility_at_the_cap": sum(
                1 for card in scored if card.get("market_accessibility") == MARKET_CAP),
        },
    }


def _pct(part: int, whole: int) -> str:
    return f"{part} ({part / whole:.0%})" if whole else f"{part} (n/a)"


def render(since: str, figures: dict[str, Any], skipped: dict[str, int]) -> str:
    runs, total = figures["runs"], figures["market_sources"]
    saved, after, cards = figures["as_saved"], figures["replayed"], figures["scorecards"]
    over = after["runs_with_a_site_over_its_share"]
    lines = [
        f"## Runs collected since {since}",
        "",
        f"{runs} runs listing {total} market sources. Set aside: "
        + (", ".join(f"{count} {what}" for what, count in sorted(skipped.items())) or "nothing") + ".",
        "",
        "| Measure | As saved | Rules replayed |",
        "|---|---:|---:|",
        f"| Runs listing one story twice | {_pct(saved['runs_listing_a_story_twice'], runs)} | "
        f"{_pct(after['runs_listing_a_story_twice'], runs)} |",
        f"| Slots holding a second copy | {saved['slots_holding_a_second_copy']} | 0 |",
        f"| Runs with an encyclopedia entry | {_pct(saved['runs_with_an_encyclopedia_entry'], runs)} | 0 |",
        f"| Runs where one site holds more than {MARKET_SOURCES_PER_SITE} slots | "
        f"{_pct(saved['runs_with_a_site_over_its_share'], runs)} | "
        f"{_pct(over['if_every_waiting_source_is_replaced'], runs)} to {_pct(over['if_none_is_replaced'], runs)} |",
        f"| Sources no longer listed (copies and encyclopedia entries) | | "
        f"{_pct(after['sources_no_longer_listed'], total)} |",
        f"| Sources waiting for a slot nothing else fills | | "
        f"{_pct(after['sources_waiting_for_a_slot'], total)} in {after['runs_with_a_waiting_source']} runs |",
        f"| Runs the rules change | | {_pct(after['runs_changed'], runs)} |",
        "",
        f"Pairs of sources in one run with alike titles (similarity at least {SIMILAR_TITLE}): "
        f"{saved['pairs_with_alike_titles']}, of which {saved['pairs_with_alike_titles_that_are_one_story']} "
        "are one story; the rest are different sources a title-only rule would have merged.",
        "",
        f"Signs behind the copies: {saved['duplicate_signs'] or 'none'}. A copy nearer the issuer "
        f"replaced the listed one {after['preferred_copy_replaces_listed_copy']} time(s). "
        f"Runs left with fewer than two market sources before any refill: "
        f"{after['runs_left_with_fewer_than_two_sources_before_refill']}.",
        "",
        f"Sources on a press wire or a syndicating host: "
        f"{_pct(saved['sources_on_wire_or_syndicating_hosts'], total)}. Largest sites: "
        + ", ".join(f"{site} {_pct(count, total)}" for site, count in saved["top_sites"][:5]) + ".",
        "",
        f"Undated sources: {_pct(saved['undated_sources'], total)}.",
        "",
        "| Why undated | Sources |",
        "|---|---:|",
        *(f"| {reason} | {count} |" for reason, count in saved["undated_reasons"].items()),
        "",
        f"Scorecards: {cards['scorecards']}, of which {cards['with_a_cap_record']} record the market cap. "
        f"The cap triggered in {cards['cap_triggered']} and lowered the score in "
        f"{cards['cap_lowered_the_score']}; market accessibility is exactly {MARKET_CAP} in "
        f"{cards['market_accessibility_at_the_cap']}.",
        "",
    ]
    return "\n".join(lines)


def render_pairs(runs: list[Run]) -> str:
    """Every change the replay makes, for reading by eye."""
    lines: list[str] = []
    for run in runs:
        result = replay(run)
        if not (result.duplicates or result.encyclopedia or result.waiting):
            continue
        lines.append(f"### {run.path}")
        for dropped, kept, why in result.duplicates:
            lines.append(f"- copy ({why}): {dropped.get('url')}")
            lines.append(f"  - listed instead: {kept.get('url')}")
        for row in result.encyclopedia:
            lines.append(f"- encyclopedia: {row.get('url')}")
        for row in result.waiting:
            lines.append(f"- waits (site share, {site_of(str(row.get('url') or ''))}): {row.get('url')}")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("root", type=Path, help="directory of saved runs, searched recursively")
    parser.add_argument("--since", action="append", required=True, metavar="YYYY-MM-DD",
                        help="count runs collected on or after this date (UTC); repeat for several windows")
    parser.add_argument("--pairs", action="store_true", help="also list every source the replay changes")
    parser.add_argument("--json", type=Path, help="write the figures of every window to this file")
    parser.add_argument("--page-date-probes", type=Path, nargs="+", metavar="PROBE.json",
                        help="saved page-date probes to check against the datelines in saved excerpts")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    everything: dict[str, Any] = {}
    for since in args.since:
        date.fromisoformat(since)
        runs, skipped = load_runs(args.root, since)
        figures = measure(runs)
        everything[since] = {"skipped": skipped, **figures}
        print(render(since, figures, skipped))
        if args.pairs:
            print(render_pairs(runs))
        if args.page_date_probes:
            probe_rows = [row for path in args.page_date_probes
                          for row in json.loads(path.read_text(encoding="utf-8"))]
            check = page_date_agreement(runs, probe_rows)
            everything[since]["page_date_agreement"] = check
            print("Page-metadata dates against release datelines, pages on wire or syndicating hosts:")
            print(json.dumps(check, indent=2, ensure_ascii=False))
            print()
    if args.json:
        args.json.write_text(json.dumps(everything, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
