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

Reads English and Simplified Chinese. A report in another language is
reported as unchecked, never as consistent: the result page shows "not run"
for an absent verdict, and an empty phrase table would otherwise turn every
such report into "the recommendation matches the score".
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from academic_agent.evidence import _REQUIRED_REPORT_HEADINGS

#: The report's own voice, by language. Every report this pipeline produces
#: carries these two headings; sections 1-4 are evidence description and are
#: not read here. Chinese reports carry the translated headings, which the
#: heading translator has rendered more than one way in the runs on disk
#: ("商业化机遇与建议" 33 times, "商业化机会与建议" 6 times), so stems are
#: matched rather than whole headings, and a run's own translated headings
#: are read as well when the caller has them.
_CONCLUSION_SECTIONS: dict[str, tuple[str, ...]] = {
    "en": ("Executive Summary", "Commercialization Opportunities"),
    "zh": ("执行摘要", "商业化机遇", "商业化机会"),
}
#: Where the two conclusion headings sit in the required heading list, which
#: is also the order the heading translator keeps.
_CONCLUSION_POSITIONS = tuple(
    i for i, heading in enumerate(_REQUIRED_REPORT_HEADINGS)
    if any(stem in heading for stem in _CONCLUSION_SECTIONS["en"]))

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

#: The same advice in Chinese, with the same thresholds. Calibrated on the 39
#: Chinese runs on disk (overall scores 38-84, 2026-07 to 2026-08) before any
#: phrase was admitted: there, "立即" always urged a patent filing or a research
#: start, "低风险" named a use case, "进入市场" described a path and "值得投资" an
#: adjacent technology. So each phrase is bound to commercialisation, market
#: entry or investment itself, as the English phrases are, and the corpus
#: reads clean (0 findings in 39) with every synthetic positive still caught.
_STRONG_RECOMMENDATIONS_ZH: tuple[tuple[str, float], ...] = (
    (r"建议立即(?:启动|开展|推进|进行|实施)?(?:商业化|产业化|市场化|量产|进入市场|推向市场)", 60),
    (r"立即(?:启动|开展|推进|进行|实施)?(?:商业化|产业化|市场化)", 60),
    (r"(?:已|已经)(?:具备|做好|达到)(?:了)?(?:商业化|产业化|量产)(?:的)?(?:条件|准备|要求|水平)", 60),
    (r"商业化(?:条件)?(?:已|已经)(?:成熟|就绪)", 60),
    (r"(?:应|应当|应该|可以|可|建议)(?:尽快|立即|直接|马上)?(?:进入市场|推向市场|投放市场)", 60),
    (r"强烈(?:建议|推荐)|高度推荐", 55),
    (r"极具投资价值|极具吸引力的投资|非常有吸引力的投资|绝佳的投资", 60),
    (r"低风险(?:的)?投资", 60),
)

#: Chinese denials and conditions. No word boundaries: the script has none.
#: Broad on purpose, like the English list; a conditional ("若", "一旦") turns
#: "can commercialise at once" into a plan, and a plan is not a verdict.
_NEGATIONS_ZH = re.compile(
    r"(?:尚未|并未|未|不宜|不应|不能|不建议|不推荐|不足|不可|不具备|无法|并非|缺乏|难以|"
    r"仍需|还需|需要|须|之前|直到|一旦|除非|才|没有|尚不|还不|远未|有待|若|如果|假如|只有)")

_CJK = re.compile(r"[\u4e00-\u9fff]")


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


def conclusion_text(report_markdown: str, headings: Sequence[str] = ()) -> str:
    """The parts of the report that speak in the report's own voice.

    `headings` adds a run's own translated conclusion headings to the built-in
    English and Chinese stems.
    """
    stems = tuple(stem.lower() for stems in _CONCLUSION_SECTIONS.values() for stem in stems)
    stems += tuple(heading.lower() for heading in headings if heading)
    lines = report_markdown.splitlines()
    kept: list[str] = []
    keeping = False
    for line in lines:
        if line.startswith("## "):
            keeping = any(stem in line.lower() for stem in stems)
            continue
        if keeping:
            kept.append(line)
    return "\n".join(kept)


def _conclusion_headings(localized_headings: Sequence[str]) -> tuple[str, ...]:
    """The run's own translations of the two conclusion headings.

    Only a complete translated list is trusted: the translator returns the
    originals when its line count is off, and a partial list would put some
    other section's heading at the conclusions' positions.
    """
    if len(localized_headings) != len(_REQUIRED_REPORT_HEADINGS):
        return ()
    headings = tuple(str(localized_headings[i]).lstrip("#").strip() for i in _CONCLUSION_POSITIONS)
    return tuple(heading for heading in headings if len(heading) >= 2)


def _readable(output_language: str | None) -> bool:
    """Whether a phrase table exists for the report's language.

    None is a run that did not record one; its headings decide. Traditional
    Chinese is excluded on purpose: the stems and phrases are simplified, and
    reading a traditional report with them would find the headings through
    the run's own translations and then nothing in the text.
    """
    if output_language is None:
        return True
    name = output_language.casefold()
    return "english" in name or ("chinese" in name and "traditional" not in name)


def _negated(text: str, start: int, negations: re.Pattern[str]) -> bool:
    return bool(negations.search(text[max(0, start - _NEGATION_WINDOW):start]))


def _assertions(text: str, table: tuple[tuple[str, float], ...],
                negations: re.Pattern[str] = _NEGATIONS) -> list[tuple[str, float, str]]:
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
            if _negated(text, match.start(), negations):
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


def check(
    report_markdown: str,
    scores: dict[str, Any],
    *,
    output_language: str | None = None,
    localized_headings: Sequence[str] = (),
) -> ConsistencyReport:
    """Compare a finished report against its scorecard. Never raises.

    output_language and localized_headings are the run's own, when the caller
    has them; without them the built-in English and Chinese headings decide
    what is read. A language without a phrase table is unchecked, not clean.
    """
    try:
        return _check(report_markdown, scores, output_language, localized_headings)
    except Exception as exc:  # noqa: BLE001 - an audit must not fail a run
        return ConsistencyReport(checked=False,
                                 error=f"{type(exc).__name__}: {exc}"[:200])


def _check(
    report_markdown: str,
    scores: dict[str, Any],
    output_language: str | None,
    localized_headings: Sequence[str],
) -> ConsistencyReport:
    if not report_markdown or not scores or not _readable(output_language):
        return ConsistencyReport(checked=False)

    text = conclusion_text(report_markdown, _conclusion_headings(localized_headings))
    if not text.strip():
        return ConsistencyReport(checked=False)

    overall = scores.get("overall_score")
    findings: list[Inconsistency] = []

    tables = [(_STRONG_RECOMMENDATIONS, _NEGATIONS)]
    if _CJK.search(text):
        tables.append((_STRONG_RECOMMENDATIONS_ZH, _NEGATIONS_ZH))
    assertions = [hit for table, negations in tables
                  for hit in _assertions(text, table, negations)]

    if overall is not None:
        for phrase, floor, excerpt in assertions:
            if float(overall) < floor:
                findings.append(Inconsistency(
                    severity="blocker",
                    kind="recommendation_exceeds_score",
                    detail=(f"The conclusions say {phrase!r} while the overall "
                            f"score is {float(overall):g}, below the {floor:g} "
                            "this phrasing implies."),
                    excerpt=excerpt))

    return ConsistencyReport(findings=tuple(findings))
