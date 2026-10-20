"""Freeze one saved retrieval plan per consumed held-out topic (rep 1 of each).

    python build_plans.py <repo> <out.json>

The plans come from heldout-trl-v1-c (H01-H10) and heldout-trl-v2 (V01-V10),
so both gates search exactly what the planner produced then, with no model call.
"""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
OUT = Path(sys.argv[2])

plans = []
for batch in ("heldout-trl-v1-c", "heldout-trl-v2"):
    for run in sorted((ROOT / "outputs/benchmark-runs" / batch).iterdir()):
        if not run.is_dir() or "__r" in run.name:
            continue
        vs = json.loads((run / "validated_sources.json").read_text(encoding="utf-8"))
        plans.append({
            "id": run.name.split("-", 1)[0],
            "display_topic": vs.get("display_topic") or vs["topic"],
            "research_topic": vs["topic"],
            "aliases": vs.get("search_aliases") or [],
            "weight_profile": vs.get("weight_profile") or "industrial",
            "from_run": f"{batch}/{run.name}",
        })

OUT.write_text(json.dumps(plans, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
print(len(plans), "plans")
