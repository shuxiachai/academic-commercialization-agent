"""Descriptive tables for the test-split result, written after the registered evaluation.

    python report.py <repo> [--sample <out.json>]

The primary numbers come from evaluate.py. This prints what the result note
reports beside them: the rows on which R5 and the production gate disagree,
a per-topic table, leave-one-topic-out deltas, a sign test on the deciding
rows (not registered), the maintainer-check sample (registered procedure)
and an exploratory stemmer diagnostic found after the evaluation.
"""
import importlib.util
import json
import random
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

ROOT = Path(sys.argv[1])
E = ROOT / "evals/academic_title_gate_v1"
sys.path[:0] = [str(ROOT / "src")]
from academic_agent import source_pipeline as sp  # noqa: E402

spec = importlib.util.spec_from_file_location("rules", E / "rules.py")
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)
rows = [json.loads(line) for line in open(E / "dataset.jsonl", encoding="utf-8")]
test = [r for r in rows if r["split"] == "test"]
labels = json.loads((E / "labels_test.json").read_text(encoding="utf-8"))


def decide(row, gate):  # identical to evaluate.py
    topics = [row["research_topic"]]
    if row["paths"] == ["web"] or ("web" in row["paths"] and len(row["paths"]) == 1):
        topics += list(row["aliases"])
    return any(gate(row["title"], t, row) if gate is not sp._title_matches_topic else gate(row["title"], t)
               for t in topics if t)


def scores(ids, decisions, gold):
    tp = sum(1 for i in ids if decisions[i] and gold[i])
    accepted = sum(1 for i in ids if decisions[i])
    relevant = sum(gold[i] for i in ids)
    return tp / max(1, accepted), tp / max(1, relevant)


prod = {r["id"]: decide(r, sp._title_matches_topic) for r in test}
r5 = {r["id"]: decide(r, rules.r5_one_matcher) for r in test}
ids = [r["id"] for r in test]
disagree = [i for i in ids if prod[i] != r5[i]]
agree = [i for i in ids if prod[i] == r5[i]]
by_id = {r["id"]: r for r in test}

print("## Rows on which R5 and production disagree")
for i in disagree:
    print(f"- {i} accepted by {'production' if prod[i] else 'R5'} only, label {labels[i]}: "
          f"{by_id[i]['display_topic']} | {by_id[i]['title']}")
favour_r5 = sum(1 for i in disagree if r5[i] == bool(labels[i]))
n = len(disagree)
tail = sum(comb(n, k) for k in range(min(favour_r5, n - favour_r5) + 1)) / 2**n
print(f"R5 right on {favour_r5} of {n}; exact two-sided sign test p = {min(1.0, 2 * tail):.3f} (not registered)")

print("\n## Per topic: rows | relevant | production accepted (off-topic) | R5 accepted (off-topic) | relevant kept")
per = defaultdict(list)
for r in test:
    per[r["display_topic"]].append(r["id"])
for topic, members in sorted(per.items(), key=lambda kv: -len(kv[1])):
    cells = []
    for d in (prod, r5):
        acc = [i for i in members if d[i]]
        cells.append((len(acc), sum(1 for i in acc if not labels[i]), sum(1 for i in acc if labels[i])))
    print(f"| {topic} | {len(members)} | {sum(labels[i] for i in members)} | {cells[0][0]} ({cells[0][1]}) "
          f"| {cells[1][0]} ({cells[1][1]}) | {cells[0][2]} → {cells[1][2]} |")

print("\n## Leave one topic out: precision and recall change, R5 minus production (points)")
for topic in sorted(per):
    rest = [i for i in ids if by_id[i]["display_topic"] != topic]
    (pp, pr), (rp, rr) = scores(rest, prod, labels), scores(rest, r5, labels)
    print(f"without {topic}: precision {100 * (rp - pp):+.1f}, recall {100 * (rr - pr):+.1f}")

if "--sample" in sys.argv:
    rng = random.Random(20261020)
    sample = (rng.sample(disagree, 30) if len(disagree) > 30 else list(disagree)) + rng.sample(agree, 10)
    rng.shuffle(sample)
    sample.sort(key=lambda i: by_id[i]["display_topic"])  # stable: the shuffled order is kept within a topic
    out = Path(sys.argv[sys.argv.index("--sample") + 1])
    out.write_text(json.dumps(
        {"_how": "Test rows where R5 and the production gate disagree (all if <= 30), plus 10 agreeing rows drawn "
                 "with random.Random(20261020); shuffled with the same generator, then grouped by topic. Shown to "
                 "the maintainer as topic + title only.",
         "rows": [{"n": k + 1, "id": i, "topic": by_id[i]["display_topic"], "title": by_id[i]["title"]}
                  for k, i in enumerate(sample)]},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"\nmaintainer sample: {len(sample)} rows -> {out}")


def plural_stem(token):
    """Exploratory: '-ies' to '-y', '-es' only after s/x/z/ch/sh, else '-s' (so 'drones' stays 'drone')."""
    if token.endswith("ies") and len(token) >= 6:
        return token[:-3] + "y"
    if token.endswith(("sses", "xes", "zes", "ches", "shes")) and len(token) - 2 >= 4:
        return token[:-2]
    if token.endswith("ing") and len(token) - 3 >= 4:
        return token[:-3]
    if token.endswith("s") and not token.endswith("ss") and len(token) - 1 >= 4:
        return token[:-1]
    return token


print("\n## Exploratory (found after the evaluation): R5 with plural_stem")
frozen_stem = rules._stem
for split in ("dev", "test"):
    split_labels = json.loads((E / f"labels_{split}.json").read_text(encoding="utf-8"))
    members = [r for r in rows if r["split"] == split]
    rules._stem = frozen_stem
    before = {r["id"]: decide(r, rules.r5_one_matcher) for r in members}
    rules._stem = plural_stem
    after = {r["id"]: decide(r, rules.r5_one_matcher) for r in members}
    rules._stem = frozen_stem
    p, rc = scores([r["id"] for r in members], after, split_labels)
    changed = [r for r in members if before[r["id"]] != after[r["id"]]]
    print(f"{split}: precision {p:.1%}, recall {rc:.1%}; {len(changed)} decisions change")
    for r in changed:
        print(f"  {r['id']} -> {'accepted' if after[r['id']] else 'rejected'}, label {split_labels[r['id']]}: "
              f"{r['title']}")

# Errata: labels written from titles cut at 120 characters, where the hidden part
# names the topic. Recorded beside the unchanged primary result, not applied to it.
ERRATA = {"dev-0106": 1, "dev-0145": 1, "test-0303": 1, "test-0361": 1, "test-0454": 1}

print("\n## Sensitivity: frozen labels vs labels with errata applied")
for split in ("dev", "test"):
    frozen = {k: v for k, v in json.loads((E / f"labels_{split}.json").read_text(encoding="utf-8")).items()
              if not k.startswith("_")}
    corrected = {**frozen, **{k: v for k, v in ERRATA.items() if k in frozen}}
    members = [r for r in rows if r["split"] == split]
    member_ids = [r["id"] for r in members]
    for name, gate in (("production", sp._title_matches_topic), ("R4", rules.r4_user_phrase_adjacent3),
                       ("R5", rules.r5_one_matcher)):
        d = {r["id"]: decide(r, gate) for r in members}
        (p0, r0), (p1, r1) = scores(member_ids, d, frozen), scores(member_ids, d, corrected)
        print(f"{split} {name:10s} frozen: precision {p0:.1%} recall {r0:.1%} | errata: precision {p1:.1%} recall {r1:.1%}")
