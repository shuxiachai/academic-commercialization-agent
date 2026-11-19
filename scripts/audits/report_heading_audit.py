"""What saved reports write as their headings, and the English a Chinese report carries.

Reads only ``commercialization_report.md`` under a directory of runs; it
calls no model and fetches nothing. Four counts:

1. **Languages.** How many reports are in each language, as the display
   layer reads it (the applicability paragraph, else the reference legend),
   plus reports that name no language and are mostly Chinese characters (a
   command-line report written before the legend existed).
2. **Headings.** For every Chinese report: how many of the eight required
   English headings it was saved under (a failed heading translation leaves
   all eight), and, where it has exactly eight headings before its reference
   list, what each position was written as. The fixed table in
   ``report_display.HEADING_TRANSLATIONS`` takes the most frequent wording.
3. **Spelling.** Every "GO/NO_GO" in every report, by spelling and by where
   it stands (the applicability paragraph, the report's prose, the reference
   list, the proofreading record), and the verdict word ``NO_GO`` alone.
4. **English in Chinese reports.** Code words of the gate, phrases of the
   writer's contract, and every run of five or more English words inside a
   line that also has Chinese, with citations removed.

    uv run python -m scripts.audits.report_heading_audit outputs
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from academic_agent.report_applicability import _OWNED_BLOCK
from academic_agent.report_display import REPORT_HEADINGS, _report_language

_CJK = re.compile(r"[一-鿿]")
_HEADING = re.compile(r"#{1,2} ")
# Any spelling and any case: the display rule itself is narrower (upper case only).
_COMPOUND = re.compile(r"`?(?<![A-Za-z0-9_])GO\s*/\s*NO[ _-]?GO(?![A-Za-z0-9_])`?", re.IGNORECASE)
_LONE = re.compile(r"(?<![/\w])NO_GO\b")
_CODES = ("orientation", "decision_support", "decision_context_incomplete", "not_established",
          "user_supplied_unapproved", "owner_approved")
_PHRASES = {
    "actor-specific": re.compile(r"actor-specific", re.IGNORECASE),
    "not assessed": re.compile(r"not assessed", re.IGNORECASE),
    "analyst proposal": re.compile(r"analyst[- ]propos", re.IGNORECASE),
    "success criteria": re.compile(r"success criteri", re.IGNORECASE),
    # Kept in Latin on purpose (evidence.py): the patent disclaimer is found by it.
    "freedom-to-operate": re.compile(r"freedom-to-operate", re.IGNORECASE),
}
_ENGLISH_RUN = re.compile(r"(?:\b[A-Za-z][A-Za-z'’_-]*\b[ ,;:/]*){5,}")
_CITATION = re.compile(r"\[[APM]\d+[^\]]*\]")


def _parts(text: str) -> dict[str, str]:
    body, _, tail = text.partition("\n## References\n")
    notes = tail.partition("\n## Reviewer Notes\n")[2]
    block = _OWNED_BLOCK.search(body)
    owned = block.group() if block else ""
    return {
        "applicability paragraph": owned,
        "prose": body.replace(owned, "") if owned else body,
        "reference list": tail[: len(tail) - len(notes)],
        "proofreading record": notes,
    }


def audit(root: Path) -> dict[str, Any]:
    languages: Counter[str] = Counter()
    kept: Counter[int] = Counter()
    wording: dict[int, Counter[str]] = {index: Counter() for index in range(8)}
    spelling: Counter[str] = Counter()
    places: Counter[str] = Counter()
    lone = [0, 0]
    chinese_with: Counter[str] = Counter()
    chinese_hits: Counter[str] = Counter()
    runs: Counter[str] = Counter()
    with_run = 0
    reports = 0
    for path in sorted(root.rglob("commercialization_report.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        reports += 1
        parts = _parts(text)
        for place, part in parts.items():
            for match in _COMPOUND.finditer(part):
                spelling[match.group()] += 1
                places[place] += 1
        alone = len(_LONE.findall(parts["prose"]))
        lone[0] += alone
        lone[1] += bool(alone)

        language = _report_language(text)
        body = text.partition("\n## References\n")[0]
        if language == "English" and len(_CJK.findall(body)) > 0.2 * max(1, len(body)):
            language = "Simplified Chinese"
            languages["Simplified Chinese (by its characters)"] += 1
        else:
            languages[language] += 1
        if language != "Simplified Chinese":
            continue

        headings = [line.rstrip() for line in body.splitlines() if _HEADING.match(line)]
        kept[sum(any(line.startswith(english) for line in headings) for english in REPORT_HEADINGS[:-1])] += 1
        if len(headings) == 8:
            for index, heading in enumerate(headings):
                wording[index][re.split(r"[：:]", heading, maxsplit=1)[0] if index == 0 else heading] += 1

        prose = parts["prose"]
        for name, pattern in ((code, re.compile(rf"(?<!\w){code}(?!\w)")) for code in _CODES):
            hits = len(pattern.findall(prose))
            chinese_with[name] += bool(hits)
            chinese_hits[name] += hits
        for name, pattern in _PHRASES.items():
            hits = len(pattern.findall(prose))
            chinese_with[name] += bool(hits)
            chinese_hits[name] += hits
        hits = len(_COMPOUND.findall(prose))
        chinese_with["GO/NO_GO"] += bool(hits)
        chinese_hits["GO/NO_GO"] += hits
        seen = False
        for line in prose.splitlines():
            if line.startswith("#") or not _CJK.search(line):
                continue
            for match in _ENGLISH_RUN.finditer(_CITATION.sub("", line)):
                phrase = " ".join(match.group().split()).strip(" ,;:/")
                if len(phrase.split()) >= 5:
                    runs[phrase.lower()[:90]] += 1
                    seen = True
        with_run += seen
    chinese = sum(count for name, count in languages.items() if name.startswith("Simplified Chinese"))
    return {
        "reports": reports, "languages": dict(languages), "chinese": chinese,
        "english_headings_kept": dict(sorted(kept.items())),
        "wording": {REPORT_HEADINGS[index]: counts.most_common() for index, counts in wording.items()},
        "spelling": spelling.most_common(), "places": dict(places),
        "lone_no_go": {"occurrences": lone[0], "reports": lone[1]},
        "chinese_reports_with": {name: [chinese_with[name], chinese_hits[name]]
                                 for name in sorted(chinese_with, key=lambda key: -chinese_with[key]) if chinese_with[name]},
        "english_runs": {"reports": with_run, "runs": runs.most_common()},
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("root", type=Path, help="a directory of runs, searched recursively")
    args = parser.parse_args(argv)
    if not args.root.is_dir():
        print(f"not a directory: {args.root}", file=sys.stderr)
        return 2
    result = audit(args.root)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(f"reports: {result['reports']}")
    print(f"languages: {result['languages']}")
    print(f"Chinese reports by how many required English headings they kept: {result['english_headings_kept']}")
    for english, counts in result["wording"].items():
        print(f"  {english}")
        for heading, count in counts:
            print(f"    {count:4d}  {heading}")
    print(f"GO/NO_GO by spelling: {result['spelling']}")
    print(f"GO/NO_GO by place: {result['places']}")
    print(f"NO_GO alone in prose: {result['lone_no_go']}")
    print("Chinese reports containing / occurrences:")
    for name, (with_it, hits) in result["chinese_reports_with"].items():
        print(f"  {with_it:3d} / {hits:4d}  {name}")
    english = result["english_runs"]
    print(f"Chinese reports with a run of five or more English words in a Chinese line: {english['reports']}")
    for phrase, count in english["runs"]:
        print(f"  {count:3d}  {phrase}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
