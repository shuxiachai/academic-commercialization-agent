"""Replay each saved patent registry under a family rule and score it against Google Patents families.

    python evaluate.py <repo> <families.json>

A rule rejects a patent row that it takes for the same invention as a row kept
earlier in the same registry; the registry order is the acceptance order, so
the first member found is kept. A rejection is correct when the two rows share
a DOCDB family member: Google Patents lists a page's family under "Also
Published As" and the same application's other publications under "Other
versions". A true duplicate is any row sharing a family with an earlier row,
whatever the rule does. Rows without a readable family are unknown.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(sys.argv[1]).resolve()
sys.path[:0] = [str(ROOT / "src")]
from academic_agent.patent_family import same_invention  # noqa: E402

DATA = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
_KIND = re.compile(r"^([A-Z]{2}\d+?)([A-Z]\d?)?$")
_WORD = re.compile(r"[a-z0-9]+")


def bare(number: str) -> str:
    match = _KIND.match(number)
    return match[1] if match else number


FAMILY = {p["number"]: {bare(n) for n in [p["own"], p["number"], *p["docdb"], *p["direct"]]}
          for p in DATA["patents"] if p["own"]}


def same_family(a: str | None, b: str | None) -> bool | None:
    if a is None or b is None:
        return None
    if bare(a) == bare(b):
        return True
    if a not in FAMILY or b not in FAMILY:
        return None
    return bool(FAMILY[a] & FAMILY[b])


def current_rule(row, kept):
    """Production today: every word of the title, publication number and site name included."""
    def key(title):
        return " ".join(_WORD.findall(title.lower()))
    return key(row["title"]) == key(kept["title"])


def candidate_rule(row, kept):
    return same_invention(row["title"], row["url"], kept["title"], kept["url"])


def true_duplicates():
    counts = Counter()
    for registry in DATA["registries"]:
        rows = registry["patents"]
        for i, row in enumerate(rows):
            verdicts = [same_family(row["number"], earlier["number"]) for earlier in rows[:i]]
            counts["duplicate" if True in verdicts else "unknown" if None in verdicts else "distinct"] += 1
    return counts


def replay(rule):
    rejections = []
    for registry in DATA["registries"]:
        kept = []
        for row in registry["patents"]:
            match = next((k for k in kept if rule(row, k)), None)
            if match is None:
                kept.append(row)
                continue
            earlier = registry["patents"][:registry["patents"].index(row)]
            rejections.append({
                "run": registry["run"], "kept": match["number"], "rejected": row["number"],
                "verdict": same_family(row["number"], match["number"]),
                "true_duplicate": True in (same_family(row["number"], e["number"]) for e in earlier),
            })
    return rejections


rows = sum(len(r["patents"]) for r in DATA["registries"])
truth = true_duplicates()
print(f"registries {len(DATA['registries'])} | patent rows {rows} | true family duplicates {truth['duplicate']} "
      f"| distinct {truth['distinct']} | unknown {truth['unknown']}")
for name, rule in (("current rule (whole title)", current_rule), ("candidate rule (same_invention)", candidate_rule)):
    rejected = replay(rule)
    verdicts = Counter({True: "correct", False: "wrong", None: "unknown"}[r["verdict"]] for r in rejected)
    known = verdicts["correct"] + verdicts["wrong"]
    pairs = {tuple(sorted((r["kept"] or "", r["rejected"] or ""))): r["verdict"] for r in rejected}
    caught = sum(r["true_duplicate"] for r in rejected)
    precision = f"{verdicts['correct'] / known:.2f}" if known else "n/a"
    print(f"\n{name}: {len(rejected)} rejected ({verdicts['correct']} correct, {verdicts['wrong']} wrong, "
          f"{verdicts['unknown']} unknown) | precision {precision} | recall {caught}/{truth['duplicate']} "
          f"| unique pairs {len(pairs)} ({sum(v is False for v in pairs.values())} wrong)")
    for r in rejected:
        if r["verdict"] is not True:
            print(f"   {r['verdict']!s:5} {r['run'][:40]:40} kept {r['kept']} rejected {r['rejected']}")
