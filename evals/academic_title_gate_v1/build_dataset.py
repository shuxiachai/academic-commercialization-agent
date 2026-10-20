"""Build the academic title-gate dataset from saved held-out benchmark runs.

Rows are title-gate decisions: every accepted academic source, and every
candidate rejected *because its title was judged off-topic* (other rejection
reasons are other gates and are excluded). Deduplicated by (topic, title).

Split fixed before any rule is designed: heldout-trl-v2 topics = development
(the hypothesis came from V06/V07), heldout-trl-v1* topics = test.

    python build_dataset.py <repo> <out.jsonl>
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1])
OUT = Path(sys.argv[2])
TITLE_REJECT = re.compile(
    r"^(arXiv title not relevant to topic|PubMed title not relevant to topic|OpenAlex title not relevant to topic"
    r"|OpenAlex topic matched broadly but title is off-topic|Crossref title is not relevant to research topic"
    r"[^:]*): '(.*)'$"
)


def norm(title):
    return re.sub(r"\W+", " ", title.lower()).strip()


rows = {}
for path in sorted(ROOT.glob("outputs/benchmark-runs/heldout-trl-v*/*/validated_sources.json")):
    run = path.parent
    batch = run.parent.name
    vs = json.loads(path.read_text(encoding="utf-8"))
    display = (vs.get("display_topic") or vs.get("topic") or "").strip()
    split = "dev" if batch == "heldout-trl-v2" else "test"
    base = {"split": split, "display_topic": display, "research_topic": vs.get("topic"),
            "aliases": vs.get("search_aliases") or []}
    by_id = {s["source_id"]: s for s in vs.get("academic_sources", [])}
    for q in vs.get("audit", []):
        if q.get("domain") != "academic":
            continue
        path_name = q["query"].split("]")[0].lstrip("[") if q["query"].startswith("[") else "web"
        for sid in q.get("accepted_source_ids", []):
            s = by_id.get(sid)
            if not s:
                continue
            key = (display.lower(), norm(s["title"]))
            row = rows.setdefault(key, {**base, "title": s["title"], "accepted": 0, "rejected": 0, "paths": set(),
                                        "summary": (s.get("evidence_summary") or "")[:280]})
            row["accepted"] += 1
            row["paths"].add(path_name)
        for reason in q.get("rejected_reasons", []):
            m = TITLE_REJECT.match(str(reason))
            if not m:
                continue
            key = (display.lower(), norm(m.group(2)))
            row = rows.setdefault(key, {**base, "title": m.group(2), "accepted": 0, "rejected": 0, "paths": set(),
                                        "summary": ""})
            row["rejected"] += 1
            row["paths"].add(path_name)

with OUT.open("w", encoding="utf-8") as f:
    for i, (_key, row) in enumerate(sorted(rows.items(), key=lambda kv: (kv[1]["split"], kv[0]))):
        row["id"] = f"{row['split']}-{i:04d}"
        row["paths"] = sorted(row["paths"])
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

c = Counter((r["split"], "accepted" if r["accepted"] else "rejected-only") for r in rows.values())
print("rows:", len(rows), dict(sorted(c.items())))
print("topics:", Counter(r["split"] for r in {r["display_topic"]: r for r in rows.values()}.values()))
