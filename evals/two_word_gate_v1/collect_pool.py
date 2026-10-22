"""Fetch the academic candidate pool for each frozen plan, titles and abstracts.

    python collect_pool.py <repo> <plans.json> <cache_dir> <out.jsonl>

Calls the production clients the primary academic lanes use, with the same
row counts: OpenAlex recent and cited searches on the planned phrase, one
OpenAlex search per alias, and Semantic Scholar, PubMed and arXiv searches on
the planned phrase. Each lane's raw response is cached in <cache_dir>, so a
rerun fetches nothing it already has. Cluster and snowball lanes depend on
what a gate accepted, so they are left out.

One row per (topic, normalised title), with every lane that returned it and the
phrase that lane gates on (the alias for an alias search, as in production).
No model or web-search request is made.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path[:0] = [str(ROOT / "src")]
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env", override=False)  # OPENALEX_API_KEY, if set locally
from academic_agent import source_pipeline as sp  # noqa: E402

PLANS = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
CACHE = Path(sys.argv[3])
OUT = Path(sys.argv[4])
CACHE.mkdir(parents=True, exist_ok=True)
FETCH_ROWS = 32  # _collect_academic_primary: max(20, maximum_sources * 4) with maximum_sources=8


def norm(title):
    return re.sub(r"\W+", " ", title.lower()).strip()


def cached(key, fetch):
    path = CACHE / f"{re.sub(r'[^a-z0-9]+', '_', key.lower())[:120]}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    result = fetch()
    if result:  # an empty answer may be a refusal; fetch it again next time
        path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return result


openalex, s2 = sp.OpenAlexClient(), sp.SemanticScholarClient()
pubmed, arxiv = sp.PubMedClient(), sp.ArxivClient()
rows = {}
for plan in PLANS:
    topic = plan["research_topic"]
    lanes = [
        ("OA-Recent", topic, lambda t=topic: openalex.search_recent(t, since_year=date.today().year - 3, rows=FETCH_ROWS)),
        ("OA-Cited", topic, lambda t=topic: openalex.search(t, rows=FETCH_ROWS)),
        *((f"OA-Syn:{alias}", alias, lambda a=alias: openalex.search(a, rows=FETCH_ROWS // 2)) for alias in plan["aliases"]),
        ("S2", topic, lambda t=topic: s2.search(t, rows=FETCH_ROWS)),
        ("PubMed", topic, lambda t=topic: pubmed.search(t, rows=FETCH_ROWS)),
        ("arXiv", topic, lambda t=topic: arxiv.search(t, rows=FETCH_ROWS)),
    ]
    for lane, gate_topic, fetch in lanes:
        items = cached(f"{plan['display_topic']}__{lane}", fetch)
        if lane.startswith("OA-") and getattr(openalex, "last_error", None):
            print(f"  {plan['display_topic']} {lane}: {openalex.last_error}", flush=True)
            openalex.last_error = None
        print(f"{plan['split']} {plan['display_topic']!r} {lane}: {len(items)}", flush=True)
        for item in items:
            title = sp._clean_text(str(item.get("title") or ""))
            if not title:
                continue
            abstract = sp._openalex_abstract(item) if lane.startswith("OA-") else sp._clean_text(str(item.get("abstract") or ""))
            key = (plan["display_topic"], norm(title))
            row = rows.setdefault(key, {
                "split": plan["split"], "display_topic": plan["display_topic"], "research_topic": topic,
                "anchor": plan["anchor"], "title": title, "abstract": abstract, "lanes": [],
            })
            if len(abstract) > len(row["abstract"]):
                row["abstract"] = abstract
            row["lanes"].append({"lane": lane, "gate_topic": gate_topic})

with OUT.open("w", encoding="utf-8", newline="\n") as handle:
    for index, (_key, row) in enumerate(sorted(rows.items(), key=lambda kv: (kv[1]["split"], kv[0]))):
        row["id"] = f"{row['split']}-{index:04d}"
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
print("rows:", len(rows))
