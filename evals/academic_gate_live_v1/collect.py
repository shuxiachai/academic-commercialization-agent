"""Part A: live academic retrieval under the old and the new title gate.

    python collect.py <repo> <plans.json> <out.json>

For each frozen plan the academic lanes (OpenAlex, Semantic Scholar, PubMed,
arXiv) run through source_pipeline._collect_academic_primary twice, once per
gate, as production fills its academic slots. Client responses (and errors)
are cached on first use, so both arms fill from the same responses; a request
only one arm makes (a snowball from its own accepted papers) is fetched live
for that arm alone. The arm run first alternates by topic.

No model or web-search request is made. The Crossref/web fallback is not run;
an arm delivering fewer than three sources is recorded as triggering it.
"""
import copy
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path[:0] = [str(ROOT / "src")]
from academic_agent import source_pipeline as sp  # noqa: E402

MINIMUM, MAXIMUM = 3, 8  # collect_source_collection's defaults, which benchmark.py uses


class Cached:
    """A client whose calls are memoised, results and exceptions alike."""

    def __init__(self, client, log):
        self._client, self._cache, self._log = client, {}, log

    def __getattr__(self, name):
        target = getattr(self._client, name)
        if not callable(target):
            return target

        def call(*args, **kwargs):
            key = (name, repr(args), repr(sorted(kwargs.items())))
            if key not in self._cache:
                self._log.append(name)
                try:
                    self._cache[key] = ("ok", target(*args, **kwargs))
                except Exception as exc:  # replayed to the other arm unchanged
                    self._cache[key] = ("error", exc)
            kind, value = self._cache[key]
            if kind == "error":
                raise value
            return copy.deepcopy(value)

        return call


def old_gate(title, topic, user_topic=""):
    """The gate before #245: the planned phrase only, with the original matcher."""
    return sp._title_matches_topic(title, topic)


NEW_GATE = sp._academic_title_matches
ARMS = {"new": NEW_GATE, "old": old_gate}


def run_arm(plan, gate, clients, anchor):
    sp._academic_title_matches = gate  # the lanes look it up at call time
    try:
        sources, audits = sp._collect_academic_primary(
            plan["research_topic"], clients["openalex"], clients["s2"], date.today(),
            maximum_sources=MAXIMUM, weight_profile=plan["weight_profile"], synonyms=plan["aliases"],
            pubmed=clients["pubmed"], arxiv=clients["arxiv"], user_topic=anchor,
        )
    finally:
        sp._academic_title_matches = NEW_GATE
    lane = {sid: audit.query.split("]")[0].lstrip("[") for audit in audits for sid in audit.accepted_source_ids}
    return {
        "count": len(sources),
        "fallback_triggered": len(sources) < MINIMUM,
        "sources": [{"title": s.title, "doi": s.doi, "lane": lane.get(s.source_id, "?")} for s in sources],
        "fetch_errors": [r for a in audits if a.result_count == 0 for r in a.rejected_reasons],
    }


plans = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
results = []
for index, plan in enumerate(plans):
    live_calls = []
    clients = {
        "openalex": Cached(sp.OpenAlexClient(), live_calls),
        "s2": Cached(sp.SemanticScholarClient(), live_calls),
        "pubmed": Cached(sp.PubMedClient(), live_calls),
        "arxiv": Cached(sp.ArxivClient(), live_calls),
    }
    anchor = sp._academic_anchor_topic(plan["display_topic"], plan["research_topic"], plan["aliases"])
    order = ["new", "old"] if index % 2 == 0 else ["old", "new"]
    arms = {}
    for arm in order:
        before = len(live_calls)
        arms[arm] = run_arm(plan, ARMS[arm], clients, anchor)
        arms[arm]["live_calls"] = len(live_calls) - before
    results.append({**plan, "anchor": anchor, "first_arm": order[0], "arms": arms})
    print(f"{plan['id']}: new {arms['new']['count']} / old {arms['old']['count']} sources, "
          f"{len(live_calls)} live calls", flush=True)

Path(sys.argv[3]).write_text(json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
