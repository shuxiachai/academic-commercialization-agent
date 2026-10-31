"""Development probe: does market retrieval surface the topic's known operators?

Market domain only, on the consumed held-out v1 topics. Each topic reuses its
saved v1 search plan (search topic and components), so no LLM is called.
Every Tavily response is cached per (mode, query) in a file the caller names,
so variants that share a query, and any rerun, cost nothing. Keep the cache
outside the repository: it holds third-party search snippets.

The label is a mention, in a market source's title or summary, of an
operator, product or deployment named in that topic's cohort anchor. A
mention is not support, and these topics are consumed: this is a development
measurement, never held-out validation.

    uv run python market_retrieval_probe.py --cache <file> --out <file> --variants A,B [--cases H01,H10]
    uv run python market_retrieval_probe.py --saved-coverage    # the v1 runs, no search

Variants: A = production market queries; B = operator wording in place of the
topic-level templates; C and D = A and B with Tavily's news search for the
topic-level queries. See docs/results-2026-10-19-market-retrieval-development-probe.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

from academic_agent.evidence import check_public_url
from academic_agent.source_clients import CrossrefClient
from academic_agent.source_pipeline import (
    _COMPONENT_MARKET_SOURCES_PER_QUERY,
    _MARKET_SOURCES_PER_QUERY,
    _collect_domain,
    _component_market_query,
    _component_terms,
    _queries,
    _recent_years,
)

BATCH = Path("outputs/benchmark-runs/heldout-trl-v1-c")
VARIANTS = ("A", "B", "C", "D")
_SITE = re.compile(r"\bsite:(\S+)")
_PARENS = re.compile(r"\s*\([^)]*\)")

# Operators, products and named deployments from evals/heldout_trl_v1/cohort.json
# anchors, and nothing else, so the label is not chosen after seeing results.
ANCHOR_ENTITIES = {
    "H01": ["Akademik Lomonosov", "KLT-40", "HTR-PM", "Shidaowan", "Linglong One", "ACP100",
            "NuScale", "BWRX-300"],
    "H02": ["National Ignition Facility", "NIF", "SPARC", "ARC"],
    "H03": ["Synchron", "Neuralink", "Paradromics", "Precision Neuroscience"],
    "H04": ["Compass Pathways", "COMP360", "COMP005", "COMP006"],
    "H05": ["Climeworks", "Mammoth", "1PointFive", "Stratos", "Occidental"],
    "H06": ["Hywind", "Kincardine", "WindFloat", "Sanxia Yinling", "三峡引领"],
    "H07": ["INPEX", "University of Tokyo"],
    "H08": ["Perfect Day", "Graeter", "Bored Cow", "Vivici"],
    "H09": ["Atlas Data Storage", "Atlas Eon", "Twist Bioscience"],
    "H10": ["Zipline"],
}
# Entities not written verbatim in their anchor: the expansion or translation
# of an anchor term.
ANCHOR_ALIASES = {"National Ignition Facility": "NIF", "三峡引领": "Sanxia Yinling"}

Search =Callable[[str, str], dict[str, Any]]


def mentions(text: str, entities: list[str]) -> set[str]:
    """Entities named in text. Acronyms match case-sensitively, all as whole tokens."""
    found = set()
    for entity in entities:
        flags = 0 if entity.isupper() else re.IGNORECASE
        if re.search(rf"(?<![A-Za-z0-9]){re.escape(entity)}(?![A-Za-z0-9])", text, flags):
            found.add(entity)
    return found


def _operator_templates(topic: str) -> list[str]:
    short = " ".join(_PARENS.sub("", topic).split()[:6])
    years = _recent_years()
    return [
        f"{topic} operator deployments in service",
        f"{topic} company announces first commercial operation",
        f"{topic} customers contract delivered units",
        f"{topic} approved product launch",
        f"{topic} pilot project operating results",
        f"{short} market size revenue commercial manufacturer {years}",
        f"{short} market report investment startup {years}",
    ]


def plan_variant(variant: str, saved: dict[str, Any]) -> list[tuple[str, str, int]]:
    """(query, search mode, source limit) for one variant of one saved plan."""
    topic, components = saved["topic"], saved.get("search_components") or []
    production = _queries(topic, weight_profile=saved["weight_profile"],
                          components=components)["market"]
    component_queries = [_component_market_query(c) for c in _component_terms(components)]
    authority = [q for q in production if "site:" in q]
    reserved = [q for q in production if q in component_queries]
    if variant in ("A", "C"):
        topical = [q for q in production if q not in authority and q not in reserved]
    else:
        # As in _queries, components and topic templates share eight slots.
        topical = _operator_templates(topic)[:max(0, 8 - len(reserved))]
    mode = "news" if variant in ("C", "D") else "general"
    return ([(q, "general", _MARKET_SOURCES_PER_QUERY) for q in authority]
            + [(q, "general", _COMPONENT_MARKET_SOURCES_PER_QUERY) for q in reserved]
            + [(q, mode, _MARKET_SOURCES_PER_QUERY) for q in topical])


def run_case(case: str, variant: str, saved: dict[str, Any], search: Search, *,
             url_checker=check_public_url, accessed: date | None = None) -> dict[str, Any]:
    planned = plan_variant(variant, saved)
    modes = {q: mode for q, mode, _ in planned}
    sources, audits = _collect_domain(
        "market", [q for q, _, _ in planned], lambda q: search(q, modes[q]), CrossrefClient(),
        url_checker, accessed or date.today(), saved["topic"],
        minimum_sources=0, maximum_sources=8,
        query_limits={q: limit for q, _, limit in planned})
    entities = ANCHOR_ENTITIES[case]
    named = [mentions(f"{s.title} {s.evidence_summary}", entities) for s in sources]
    in_results: set[str] = set()
    for audit in audits:
        if audit.query in modes:
            for item in search(audit.query, modes[audit.query])["organic"]:
                in_results |= mentions(f"{item['title']} {item['snippet']}", entities)
    return {
        "case": case, "variant": variant,
        "queries_run": sum(audit.query in modes for audit in audits),
        "market_sources": len(sources),
        "entity_sources": sum(bool(n) for n in named),
        "entities_admitted": sorted(set().union(*named)),
        "entities_in_results": sorted(in_results),
    }


def saved_coverage(case: str, batch: Path = BATCH) -> list[tuple[int, int]]:
    """(entity sources, market sources) for each saved run of a case; no search."""
    rows = []
    for run_dir in sorted(batch.glob(f"{case}-*")):
        saved = json.loads((run_dir / "validated_sources.json").read_text(encoding="utf-8"))
        sources = saved["market_sources"]
        rows.append((sum(bool(mentions(f"{s['title']} {s['evidence_summary']}",
                                        ANCHOR_ENTITIES[case])) for s in sources), len(sources)))
    return rows


class CachedTavily:
    """Tavily search with a JSON cache; general or news mode."""

    def __init__(self, cache: Path, api_key: str) -> None:
        self.path = cache
        self.api_key = api_key
        self.data = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
        self.calls = 0

    def __call__(self, query: str, mode: str) -> dict[str, Any]:
        key = f"{mode}\t{query}"
        if key not in self.data:
            body: dict[str, Any] = {"query": _SITE.sub("", query).strip(), "max_results": 10}
            if domains := _SITE.findall(query):
                body["include_domains"] = domains
            if mode == "news":
                body.update(topic="news", days=730)
            request = Request("https://api.tavily.com/search", data=json.dumps(body).encode(),
                              headers={"Authorization": f"Bearer {self.api_key}",
                                       "Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.calls += 1
            self.data[key] = {"organic": [
                {"title": r.get("title", ""), "link": r.get("url", ""), "snippet": r.get("content", "")}
                for r in payload.get("results", [])]}
            self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
            time.sleep(0.3)
        return self.data[key]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--saved-coverage", action="store_true",
                        help="report coverage of the saved v1 runs and exit; no search")
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--variants", default="A")
    parser.add_argument("--cases", default=",".join(ANCHOR_ENTITIES))
    args = parser.parse_args(argv)
    if args.saved_coverage:
        for case in args.cases.split(","):
            print(case, " ".join(f"{hit}/{total}" for hit, total in saved_coverage(case)))
        return
    if args.cache is None or args.out is None:
        parser.error("--cache and --out are required for a probe run")
    variants = args.variants.split(",")
    if not set(variants) <= set(VARIANTS):
        parser.error(f"variants must be among {VARIANTS}")
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        parser.error("TAVILY_API_KEY is required")
    search = CachedTavily(args.cache, api_key)
    results = json.loads(args.out.read_text(encoding="utf-8")) if args.out.exists() else []
    done = {(r["case"], r["variant"]) for r in results}
    for case in args.cases.split(","):
        run_dir = sorted(p for p in BATCH.glob(f"{case}-*") if "__r" not in p.name)[0]
        saved = json.loads((run_dir / "validated_sources.json").read_text(encoding="utf-8"))
        for variant in variants:
            if (case, variant) not in done:
                results.append(run_case(case, variant, saved, search))
                args.out.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
                print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    print(f"tavily calls: {search.calls}")


if __name__ == "__main__":
    main()
