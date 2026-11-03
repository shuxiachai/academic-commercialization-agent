"""Rows each candidate rule removes, with their labels.

    python report.py <labels.json> [--test]

Without --test only the dev split is read. Read the test split only after a
pre-registration naming the chosen rule has been pushed.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rules import RULES, anchor_words_present  # noqa: E402

data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
splits = ("dev", "test") if "--test" in sys.argv[2:] else ("dev",)

for split in splits:
    rows = [r for r in data["rows"] if r["split"] == split]
    print(f"== {split}: {len(rows)} selected rows, {sum(r['label'] == 0 for r in rows)} off-topic")
    for name, keep in RULES.items():
        removed = [r for r in rows if not keep(r)]
        off = sum(r["label"] == 0 for r in removed)
        on = len(removed) - off
        by_path = defaultdict(lambda: [0, 0])
        for r in removed:
            by_path[anchor_words_present(r)][r["label"]] += 1
        ratio = f"{off / on:.1f}:1" if on else "all off-topic"
        print(f"  {name:5} removed {len(removed):3} (off {off}, on {on}, {ratio}); "
              f"by anchor words in title {dict((k, {'off': v[0], 'on': v[1]}) for k, v in sorted(by_path.items()))}")
    by_topic = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for r in rows:
        for name, keep in RULES.items():
            if not keep(r):
                by_topic[r["topic"]][name][r["label"]] += 1
    for topic in sorted(by_topic):
        print(f"    {topic:18}", "  ".join(f"{name} off {v[0]}/on {v[1]}" for name, v in by_topic[topic].items()))
