"""Decide whether production retrieval health needs an alert, and write its text.

    python scripts/retrieval_health_alert.py <health.json> <body.md>

<health.json> is the reply of GET /api/health/retrieval. Prints "alert" when a
lane is failing (failed in at least half of three or more recent runs) and
"ok" otherwise, and writes the Markdown for the alert issue or its recovery
comment to <body.md>. Mostly-empty lanes are listed but never alert on their
own: some lanes run only when others leave slots open.

The Retrieval health workflow runs this once a day. A lane that refuses
requests otherwise goes unnoticed: in October 2026 an exhausted OpenAlex
budget emptied every OpenAlex lane of seven runs for three days before
anyone saw it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# What to check first when a lane fails, keyed by the lane label or its prefix.
_HINTS = (
    ("OA-", "OpenAlex: OPENALEX_API_KEY and its daily budget"),
    ("OpenAlex", "OpenAlex: OPENALEX_API_KEY and its daily budget"),
    ("S2", "Semantic Scholar: SEMANTIC_SCHOLAR_API_KEY (anonymous requests are rate limited)"),
    ("PubMed", "PubMed: NCBI_API_KEY and its rate limit"),
    ("arXiv", "arXiv: its request rate limit"),
    ("Lens", "Lens.org: LENS_API_KEY"),
    ("academic web search", "web search: the Tavily or Serper key and its quota"),
    ("patent web search", "web search: the Tavily or Serper key and its quota"),
    ("market web search", "web search: the Tavily or Serper key and its quota"),
)


def hint(lane: str) -> str:
    return next((text for prefix, text in _HINTS if lane == prefix or lane.startswith(prefix)), "the lane's client")


def decide(health: dict) -> tuple[str, str]:
    """("alert" | "ok", Markdown body)."""
    failing = list(health.get("failing") or [])
    lanes = {row["lane"]: row for row in health.get("lanes") or []}
    lines = [f"Production retrieval health over the last {health.get('runs_examined', 0)} runs "
             f"that saved an audit (window {health.get('window')}).", ""]
    if lanes:
        lines += ["| Lane | Runs observed | Failed | Empty |", "|---|---:|---:|---:|"]
        lines += [f"| {lane} | {row['observed_runs']} | {row['failed_runs']} | {row['empty_runs']} |"
                  for lane, row in lanes.items()]
        lines.append("")
    if failing:
        lines.append("**Failing lanes** (a refusal or failed request in at least half of three or more runs):")
        lines += [f"- **{lane}**: check {hint(lane)}." for lane in failing]
        lines += ["", "Reports from these runs may carry less evidence than they should. Each report's "
                  "reliability panel names the domains whose retrieval failed."]
    else:
        lines.append("No lane is failing.")
    if health.get("mostly_empty"):
        lines += ["", "Mostly empty, not alerted: " + ", ".join(health["mostly_empty"]) + "."]
    return ("alert" if failing else "ok"), "\n".join(lines) + "\n"


def main() -> None:
    health = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    decision, body = decide(health)
    Path(sys.argv[2]).write_text(body, encoding="utf-8")
    print(decision)


if __name__ == "__main__":
    main()
