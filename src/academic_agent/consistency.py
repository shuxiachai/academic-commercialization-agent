"""Does the report agree with the scorecard it ships next to?

The reviewer agent checks the report against the evidence, and the scoring
agent runs after it reading the same evidence. Neither ever sees the other's
output, so nothing in the pipeline compares them. A report can recommend
moving quickly to market beside a scorecard reading 40, and both are
internally consistent.

Done in code rather than by adding a seventh agent. The checks an external
review asked for are deterministic ones, and a judge model to answer them
would cost a call per run, add a second opinion whose errors correlate with
the first, and produce a verdict no test could pin.

One axis survives measurement, one did not — see the note below the section
list. What is left reads the report's own advice and compares it to the
score, which is the case where the subject of the sentence is unambiguous.

Scoped to the conclusions rather than the whole report. Sections 1-4 describe
what the evidence says, including what competitors claim, and a strong phrase
there is usually a fact about somebody else.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

#: The report's own voice. Every report this pipeline produces carries these
#: two headings; sections 1-4 are evidence description and are not read here.
_CONCLUSION_SECTIONS = ("Executive Summary", "Commercialization Opportunities")

#: MATURITY LANGUAGE WAS TRIED AND DROPPED.
#:
#: The obvious second check is "the report calls it commercially available
#: while the scorecard says TRL 3". Implemented and measured against all 30
#: baseline reports, it produced two flags and both were wrong:
#:
#:   "Given that MEA-based capture is commercially available but
#:    energy-intensive, technologies that…"     -> about the incumbent
#:   "whether such a space is commercially available [P7]"
#:                                              -> about patent white space
#:
#: A paragraph attributes properties to several subjects, and matching the
#: phrase cannot tell which one carries it. Requiring the topic's words
#: nearby does not help either: the incumbent in a carbon-capture report is
#: also called "capture". Deciding the subject needs parsing this does not
#: do, so the axis is left out rather than shipped at 0% precision.
#:
#: The recommendation check below survives because it reads the report's own
#: advice, which has only one subject: what the reader should do.

#: Phrases urging action now, paired with the lowest overall score at which
#: they stop contradicting the scorecard. The scale is 0-100.
_STRONG_RECOMMENDATIONS: tuple[tuple[str, float], ...] = (
    (r"recommend(?:ed|s)? immediate", 60),
    (r"ready for commercriali[sz]ation", 60),
    (r"ready for commerciali[sz]ation", 60),
    (r"should enter the market", 60),
    (r"immediate commerciali[sz]ation", 60),
    (r"strong(?:ly)? recommend", 55),
    (r"compelling investment", 60),
    (r"low[- ]risk investment", 60),
)

#: A phrase inside this distance before a match flips its meaning. "not
#: commercially available" is the single most common way these words appear
#: in an honest report about an immature technology, and reading it as a
#: maturity claim would flag exactly the reports that are being careful.
_NEGATIONS = re.compile(
    r"(?:\bnot\b|\bno\b|\bnever\b|\bnor\b|\bwithout\b|\blacks?\b|\byet to\b|"
    r"\bfar from\b|\bunlikely\b|\bcannot\b|\bnone\b|\bbefore\b|\brequires?\b|"
    r"\bwould need\b|\bnot yet\b|\bprior to\b|\bonce\b|\buntil\b)",
    re.IGNORECASE)
_NEGATION_WINDOW = 60


@dataclass(frozen=True)
class Inconsistency:
    """One disagreement between the report's words and the scorecard."""

    severity: str          # "blocker" | "warning"
    kind: str
    detail: str
    excerpt: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "kind": self.kind,
                "detail": self.detail, "excerpt": self.excerpt[:200]}


@dataclass(frozen=True)
class ConsistencyReport:
    findings: tuple[Inconsistency, ...] = ()
    checked: bool = True
    error: str | None = field(default=None)

    @property
    def blockers(self) -> int:
        return sum(1 for f in self.findings if f.severity == "blocker")

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "checked": self.checked,
            "blockers": self.blockers,
            "warnings": len(self.findings) - self.blockers,
            "findings": [f.as_dict() for f in self.findings],
        }
        if self.error:
            data["error"] = self.error
        return data


def conclusion_text(report_markdown: str) -> str:
    """The parts of the report that speak in the report's own voice."""
    lines = report_markdown.splitlines()
    kept: list[str] = []
    keeping = False
    for line in lines:
        if line.startswith("## "):
            keeping = any(s.lower() in line.lower() for s in _CONCLUSION_SECTIONS)
            continue
        if keeping:
            kept.append(line)
    return "\n".join(kept)


def _negated(text: str, start: int) -> bool:
    return bool(_NEGATIONS.search(text[max(0, start - _NEGATION_WINDOW):start]))


def _assertions(text: str, table: tuple[tuple[str, float], ...]
                ) -> list[tuple[str, float, str]]:
    """Every phrase from `table` asserted, not denied, in `text`.

    One sentence per finding. "We recommend immediate commercialization"
    matches three entries at once, and reporting it three times makes one
    disagreement look like three — the kind of inflation that gets a check
    ignored. Overlapping matches collapse to the strictest threshold, since
    that is the one the sentence has to clear.
    """
    hits: dict[tuple[int, int], tuple[str, float, str]] = {}
    for pattern, threshold in table:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            if _negated(text, match.start()):
                continue
            # Sentence-ish bucket: matches within one window are the same
            # assertion phrased in overlapping ways.
            bucket = (match.start() // 160, 0)
            excerpt = " ".join(
                text[max(0, match.start() - 90):match.end() + 90].split())
            previous = hits.get(bucket)
            if previous is None or threshold > previous[1]:
                hits[bucket] = (match.group(0), threshold, excerpt)
            break
    return list(hits.values())


def check(report_markdown: str, scores: dict[str, Any]) -> ConsistencyReport:
    """Compare a finished report against its scorecard. Never raises."""
    try:
        return _check(report_markdown, scores)
    except Exception as exc:  # noqa: BLE001 - an audit must not fail a run
        return ConsistencyReport(checked=False,
                                 error=f"{type(exc).__name__}: {exc}"[:200])


def _check(report_markdown: str, scores: dict[str, Any]) -> ConsistencyReport:
    if not report_markdown or not scores:
        return ConsistencyReport(checked=False)

    text = conclusion_text(report_markdown)
    if not text.strip():
        return ConsistencyReport(checked=False)

    overall = scores.get("overall_score")
    findings: list[Inconsistency] = []

    if overall is not None:
        for phrase, floor, excerpt in _assertions(text, _STRONG_RECOMMENDATIONS):
            if float(overall) < floor:
                findings.append(Inconsistency(
                    severity="blocker",
                    kind="recommendation_exceeds_score",
                    detail=(f"The conclusions say {phrase!r} while the overall "
                            f"score is {float(overall):g}, below the {floor:g} "
                            "this phrasing implies."),
                    excerpt=excerpt))

    return ConsistencyReport(findings=tuple(findings))
