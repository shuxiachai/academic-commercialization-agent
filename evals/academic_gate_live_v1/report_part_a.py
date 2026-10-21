"""Part A measures from part_a_results.json and labels_part_a.json.

    python report_part_a.py <repo>

Written after collection and labelling; it applies the protocol's readings.
"""
import json
import re
import sys
from pathlib import Path

E = Path(sys.argv[1]) / "evals/academic_gate_live_v1"
results = json.loads((E / "part_a_results.json").read_text(encoding="utf-8"))
labels = json.loads((E / "labels_part_a.json").read_text(encoding="utf-8"))["labels"]


def norm(title):
    return re.sub(r"\W+", " ", title.lower()).strip()


totals = {arm: {"delivered": 0, "off": 0, "relevant": 0, "short": 0} for arm in ("new", "old")}
print("| Topic | New: delivered (off-topic) | Old: delivered (off-topic) | Shared |")
print("|---|---|---|---|")
for topic in results:
    cells = {}
    titles = {}
    for arm in ("new", "old"):
        arm_result = topic["arms"][arm]
        marks = [labels[topic["display_topic"]][norm(s["title"])] for s in arm_result["sources"]]
        titles[arm] = {norm(s["title"]) for s in arm_result["sources"]}
        t = totals[arm]
        t["delivered"] += len(marks)
        t["off"] += marks.count(0)
        t["relevant"] += marks.count(1)
        t["short"] += arm_result["fallback_triggered"]
        cells[arm] = f"{len(marks)} ({marks.count(0)})"
    print(f"| {topic['display_topic']} | {cells['new']} | {cells['old']} | {len(titles['new'] & titles['old'])} |")

new, old = totals["new"], totals["old"]
print(f"\nA1 off-topic delivered: new {new['off']} / old {old['off']} -> "
      f"{'cleaner delivered evidence' if new['off'] <= 0.75 * old['off'] else 'slot refill absorbs the gain'}")
print(f"A2 topics below 3 sources: new {new['short']} / old {old['short']} -> "
      f"{'shortage risk confirmed' if new['short'] - old['short'] >= 2 else 'no shortage increase detected'}")
print(f"A3 relevant delivered: new {new['relevant']} / old {old['relevant']} -> "
      f"{'relevance loss flagged' if new['relevant'] < 0.9 * old['relevant'] else 'no relevance loss flagged'}")
print(f"delivered: new {new['delivered']} / old {old['delivered']}")
