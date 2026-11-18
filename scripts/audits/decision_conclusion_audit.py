"""How saved reports use the words of a decision conclusion, and what the rule finds.

Reads only ``commercialization_report.md`` and ``status.json`` under a
directory of runs; it calls no model and fetches nothing. Three counts:

1. **Modes.** How many reports were written in each assessment mode, from the
   gate in the run's status or, failing that, the code in the delivered
   applicability paragraph. A report with neither predates the gate or came
   from the command line, which sets none.
2. **Lines.** Every line that uses GO, NO_GO or DEFER as the writer's
   contract spells them, sorted into: says that none is assessed; "GO" as a
   name (graphene oxide, a product); and the rest, printed with ``--lines``
   for reading.
3. **The rule.** ``decision_verdict.find_verdict``, the function the page and
   the PDF use, applied to every report. In a report that is not in
   decision-support mode anything it finds is a candidate false positive, and
   each is printed.

    uv run python -m scripts.audits.decision_conclusion_audit outputs
    uv run python -m scripts.audits.decision_conclusion_audit outputs --lines
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from academic_agent.decision_verdict import find_verdict

_WORD = re.compile(r"\bGO\b|\bNO[-_ ]?GO\b|\bDEFER\b")
_MODE_CODE = re.compile(r"Mode `([a-z_]+)`")
# Said of the report's mode: no conclusion is given. English and Chinese, as
# the saved reports word it.
_NONE_ASSESSED = re.compile(
    r"not (?:been )?(?:assessed|provided|issued|given|rendered|made|offered|applicable|established|performed)"
    r"|no actor-specific|does not|do not|is not|cannot|without|no GO\s*/\s*NO|disclaimer|lack of GO"
    r"|未评估|不评估|未进行|不进行|不给出|未给出|无法给出|不提供|不构成|均未评估|未作|不作",
    re.IGNORECASE,
)
# "GO" that is not the verdict word: graphene oxide, reduced graphene oxide, a product's name.
_A_NAME = re.compile(
    r"graphene oxide|\(GO\)|\brGO\b|\bGO(?:'s|-based| photoreduction| sheets| films| inks| flakes)"
    r"|\b[A-Z][a-z]+ GO\b",
)


def _mode(run: Path, report: str) -> str:
    status = run / "status.json"
    if status.is_file():
        try:
            gate = json.loads(status.read_text(encoding="utf-8")).get("decision_gate")
        except (OSError, ValueError):
            gate = None
        if isinstance(gate, dict) and isinstance(gate.get("mode"), str):
            return gate["mode"]
    code = _MODE_CODE.search(report[:3000])
    return code.group(1) if code else "not recorded"


def audit(root: Path) -> dict[str, Any]:
    modes: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    found: Counter[str] = Counter()
    rest: list[tuple[str, str]] = []
    statements: list[dict[str, str]] = []
    reports = 0
    for path in sorted(root.rglob("commercialization_report.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        reports += 1
        run = str(path.parent.relative_to(root))
        mode = _mode(path.parent, text)
        modes[mode] += 1
        for line in text.splitlines():
            if not _WORD.search(line):
                continue
            # A line that names both the verdict vocabulary and graphene oxide is read as the former.
            if _A_NAME.search(line) and not re.search(r"NO[-_ ]?GO|DEFER", line):
                kinds["a name"] += 1
            elif _NONE_ASSESSED.search(line):
                kinds["none assessed"] += 1
            else:
                kinds["other"] += 1
                rest.append((run, line.strip()))
        result = find_verdict(text)
        found[result["status"]] += 1
        for item in result["statements"]:
            statements.append({"run": run, "mode": mode, "verdict": item["verdict"],
                               "section": item["section"], "statement": item["statement"]})
    return {"reports": reports, "modes": dict(modes), "lines": sum(kinds.values()), "kinds": dict(kinds),
            "rest": rest, "rule": dict(found), "statements": statements}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path, help="a directory of saved runs, searched at any depth")
    parser.add_argument("--lines", action="store_true", help="print the lines that are neither a negation nor a name")
    args = parser.parse_args(argv)
    result = audit(args.root)
    out = sys.stdout
    print(f"{result['reports']} reports", file=out)
    print("  by mode: " + ", ".join(f"{mode} {count}" for mode, count in sorted(result["modes"].items())), file=out)
    print(f"{result['lines']} lines use GO, NO_GO or DEFER", file=out)
    for kind in ("none assessed", "a name", "other"):
        print(f"  {kind}: {result['kinds'].get(kind, 0)}", file=out)
    if args.lines:
        for run, line in result["rest"]:
            print(f"    {run[-60:]} | {line[:240]}", file=out)
    print("the rule: " + ", ".join(f"{status} {count}" for status, count in sorted(result["rule"].items())), file=out)
    for item in result["statements"]:
        print(f"  FOUND in a {item['mode']} report ({item['run'][-60:]}), {item['section']!r}: "
              f"{item['verdict']} | {item['statement'][:240]}", file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
