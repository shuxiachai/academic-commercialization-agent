"""Select the rows a two-word adjacency rule could change, for blind labelling.

    python label_set.py <repo> <pool.jsonl> <out.jsonl>

A row is selected when the production gate (R5, _academic_title_matches)
accepts its title on at least one lane that returned it, and the anchor's two
content words do not appear next to each other, in order, among the title's
stemmed words. Every candidate rule (adjacency, one intervening word, an
abstract rescue) agrees with production on all other rows, so only these
need labels. The output carries topic, title and abstract only: no lane,
gate or rule decision, so labelling stays blind to them.
"""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
sys.path[:0] = [str(ROOT / "src")]
from academic_agent import source_pipeline as sp  # noqa: E402

rows = [json.loads(line) for line in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines()]
selected = []
for row in rows:
    core = sp._academic_content_words(row["anchor"])
    if len(core) != 2:
        raise SystemExit(f"{row['display_topic']!r}: anchor has {len(core)} content words, not 2")
    title_words = [sp._academic_stem(w) for w in sp._WORD_PATTERN.findall(row["title"].lower())]
    adjacent = any(pair == tuple(core) for pair in zip(title_words, title_words[1:], strict=False))
    accepted = any(sp._academic_title_matches(row["title"], lane["gate_topic"], row["anchor"]) for lane in row["lanes"])
    if accepted and not adjacent:
        selected.append({key: row[key] for key in ("id", "split", "display_topic", "title", "abstract")})

with Path(sys.argv[3]).open("w", encoding="utf-8", newline="\n") as handle:
    for row in selected:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
by_topic = {}
for row in selected:
    by_topic[(row["split"], row["display_topic"])] = by_topic.get((row["split"], row["display_topic"]), 0) + 1
for key in sorted(by_topic):
    print(*key, by_topic[key])
print("selected:", len(selected), "of", len(rows))
