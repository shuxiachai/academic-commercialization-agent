"""Replay title-gate rules over the labelled dataset.

    python evaluate.py <repo> <dataset.jsonl> <labels.json> [--split dev] [--rule current] [--show]

A row is decided once per path it was seen on: database paths (arXiv, S2,
PubMed, OpenAlex) gate on the planned research topic; web/Crossref results
gate on the topic and its aliases, as in source_pipeline.
"""
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path[:0] = [str(ROOT / "src")]
from academic_agent import source_pipeline as sp  # noqa: E402

rows = [json.loads(line) for line in open(sys.argv[2], encoding="utf-8")]
labels = json.loads(Path(sys.argv[3]).read_text(encoding="utf-8"))
split = sys.argv[sys.argv.index("--split") + 1] if "--split" in sys.argv else "dev"
rule_name = sys.argv[sys.argv.index("--rule") + 1] if "--rule" in sys.argv else "current"
show = "--show" in sys.argv

rules = {"current": sp._title_matches_topic}
candidates = Path(__file__).with_name("rules.py")
if candidates.exists():
    spec = importlib.util.spec_from_file_location("rules", candidates)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rules.update(mod.RULES)
rule = rules[rule_name]


def decide(row, gate):
    topics = [row["research_topic"]]
    if row["paths"] == ["web"] or ("web" in row["paths"] and len(row["paths"]) == 1):
        topics += list(row["aliases"])
    return any(gate(row["title"], t, row) if gate is not sp._title_matches_topic else gate(row["title"], t)
               for t in topics if t)


# Fidelity: does the current rule reproduce the recorded decision?
fid = Counter()
for r in rows:
    if r["split"] != split:
        continue
    recorded = "accepted" if r["accepted"] and not r["rejected"] else "rejected" if r["rejected"] and not r["accepted"] else "mixed"
    replay = "accepted" if decide(r, sp._title_matches_topic) else "rejected"
    fid[(recorded, replay)] += 1

cm = Counter()
details = []
for r in rows:
    if r["split"] != split or r["id"] not in labels:
        continue
    y = labels[r["id"]]
    accept = decide(r, rule)
    cm[(y, accept)] += 1
    if show and ((y == 1) != accept):
        details.append(("FN" if y else "FP", r["display_topic"], r["title"][:100]))

tp, fp, fn, tn = cm[(1, True)], cm[(0, True)], cm[(1, False)], cm[(0, False)]
print(f"split={split} rule={rule_name}  replay fidelity (recorded, replayed): {dict(fid)}")
print(f"  accepted: {tp + fp:3d}  relevant among accepted (precision): {tp / max(1, tp + fp):.1%}  "
      f"irrelevant accepted (FP): {fp}")
print(f"  relevant total: {tp + fn:3d}  relevant kept (recall): {tp / max(1, tp + fn):.1%}  "
      f"relevant rejected (FN): {fn}")
for kind, topic, title in sorted(details):
    print(f"  {kind} | {topic[:28]:28s} | {title}")
