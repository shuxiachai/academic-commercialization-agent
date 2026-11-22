"""The run page's decision brief, as far as a PDF can carry it.

The page's brief (web/static/js/result.js `decisionBrief`) puts three lines
above the report: the report's own summary sentence, the biggest risk and the
first recommended step. The risk is the scorecard's first `key_risks` entry.
The other two are sentences the page finds in the displayed report by a set of
rules written against the saved reports (each rule's comment in result.js says
what it was measured on). A PDF is made on the server, so those rules are
ported here, rule for rule; nothing is summarised, rewritten or judged, and
no model is called.

The two must agree, or a reader of the PDF and a reader of the page are told
different things about the same report. tests/test_report_brief.py runs
result.js's own functions in Node on every public sample and on the reports
saved on the maintainer's machine, and requires the same sentences here.

A port of JavaScript regular expressions needs care in four places, kept
exact on purpose rather than approximately:

- `\\s`, `\\b` and `\\w`. JavaScript's `\\b` and `\\w` are ASCII; Python's are
  Unicode ("report" followed by a Chinese character has a word boundary in
  JavaScript and none in Python). Every pattern here is compiled with
  re.ASCII, and `\\s` is spelt out as JavaScript's set (_WS), which re.ASCII
  would otherwise narrow to six characters.
- `.`, which in JavaScript stops at U+2028 and U+2029 as well (_DOT).
- `\\p{Ll}`, which Python's re lacks: tested with unicodedata instead.
- Lengths. JavaScript counts UTF-16 code units; the limits (240 characters
  for a quoted sentence, 80 for a label) are applied in those units.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# JavaScript's \s (as the inside of a class, and as a class), and its `.`.
_WS_IN = "\\t\\n\\v\\f\\r \\u00a0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000\\ufeff"
_WS = "[" + _WS_IN + "]"
_WS_CHARS = "\t\n\v\f\r              " \
            "    　﻿"
_DOT = "[^\\n\\r\\u2028\\u2029]"
_A = re.ASCII
_AI = re.ASCII | re.IGNORECASE


def _js(pattern: str) -> str:
    """A JavaScript pattern's \\s as JavaScript means it, in a class or out of one."""
    out: list[str] = []
    in_class = False
    at = 0
    while at < len(pattern):
        char = pattern[at]
        if char == "\\" and at + 1 < len(pattern):
            pair = pattern[at:at + 2]
            out.append((_WS_IN if in_class else _WS) if pair == "\\s" else pair)
            at += 2
            continue
        if char == "[" and not in_class:
            in_class = True
        elif char == "]" and in_class:
            in_class = False
        out.append(char)
        at += 1
    return "".join(out)


def _trim(text: str) -> str:
    return text.strip(_WS_CHARS)


def _trim_end(text: str) -> str:
    return text.rstrip(_WS_CHARS)


def _units(text: str) -> bytes:
    return text.encode("utf-16-le", "surrogatepass")


def _length(text: str) -> int:
    """String.prototype.length: UTF-16 code units."""
    return len(_units(text)) // 2


def _head(text: str, units: int) -> str:
    """String.prototype.slice(0, units)."""
    return _units(text)[:2 * units].decode("utf-16-le", "surrogatepass")


# ── result.js, in its order ──────────────────────────────────────────────

BAND_THRESHOLDS: tuple[tuple[float, str], ...] = ((70, "strong"), (55, "moderate"), (40, "early"))


def band(score: float) -> str:
    """result.js band(): the grade word's key (band_strong ...) for an overall score."""
    for floor, name in BAND_THRESHOLDS:
        if score >= floor:
            return name
    return "nascent"


_CITATION_RUN = re.compile(_js(r"[\[(]\s*([APM]\d+(?:\s*[,;]\s*[APM]\d+)*)\s*[\])]"), _A)
_SUMMARY_HEADINGS = re.compile(r"executive summary|执行摘要", _AI)
_RECOMMENDATION_HEADINGS = re.compile(r"commercialization opportunities|商业化机遇|商业化机会", _AI)
BRIEF_SENTENCE_LIMIT = 240

_REPORT_QUALIFIER = _js(r"(?:(?:orientation(?:-mode)?|evidence-linked|commerciali[sz]ation|present|current)\s+)")
_ABOUT_THE_REPORT = re.compile(_js(
    "^(?:"
    + r"(?:this|the)\s+" + _REPORT_QUALIFIER + r"{0,2}(?:assessment|report|analysis|document|evaluation)\b"
    + r"|this\s+" + _REPORT_QUALIFIER + r"{0,2}brief\b"
    + r"|(?:this|it) is an?\s+(?:[\w-]+\s+){0,3}(?:assessment|report|analysis|evaluation|brief)\b"
    + r"|it is written in (?:orientation|decision[- ]support)\b"
    + r"|assessment mode\b|no actor-specific\b|actor-specific go\s*\/\s*no[_-]go\b"
    + r"|(?:all )?(?:conclusions|findings) (?:are|remain) (?:provisional|preliminary|tentative)\b"
    + r"|本(?:报告|评估|分析|文)|需要(?:明确|说明|指出)的是|评估模式"
    + ")"), _AI)
_TITLE_LIMIT = 60

_NEVER_ENDS = re.compile(_js(
    r"(?:^|[\s(\[“\"'‘/—-])(?:e\.g|i\.e|vs|cf|et al|approx|ca|Dr|Inc|Ltd|Corp|Co|Nos?|Figs?|U\.S|U\.K)\Z"), _A)
_LEADING_ENUMERATOR = re.compile(r"^\(?(?:\d{1,2}|[A-Za-z])\Z", _A)
_SENTENCE_CLOSERS = re.compile(r"^[)\]\"'”’」』）]+", _A)
_STOPS = re.compile(r"[.!?。！？]+", _A)
_SPACE_BEFORE_MARK = re.compile(_js(r"\s+([,.;:!?，。；：！？、])"), _A)
_EMPTY_BRACKETS = re.compile(_js(r"\(\s*\)"), _A)
_RUN_OF_SPACE = re.compile(_js(r"\s+"), _A)


def _lowercase_word(after: str) -> bool:
    """/^\\p{Ll}[\\p{Ll}'’-]*[,;:]?(?:\\s|$)/u: a word wholly in lower case."""
    if not after or unicodedata.category(after[0]) != "Ll":
        return False
    at = 1
    while at < len(after) and (unicodedata.category(after[at]) == "Ll" or after[at] in "'’-"):
        at += 1
    if at < len(after) and after[at] in ",;:":
        at += 1
    return at == len(after) or after[at] in _WS_CHARS


def _full_stop_ends(before: str, after: str) -> bool:
    if _LEADING_ENUMERATOR.search(_trim(before)):
        return False
    if not after or after[0] not in _WS_CHARS:
        return False
    return not _lowercase_word(after.lstrip(_WS_CHARS)) and not _NEVER_ENDS.search(before)


def sentences_of(text: str) -> list[str]:
    """result.js sentencesOf."""
    clean = _CITATION_RUN.sub("", text).replace("**", "")
    clean = _RUN_OF_SPACE.sub(" ", clean)
    clean = _SPACE_BEFORE_MARK.sub(r"\1", clean)
    clean = _trim(_EMPTY_BRACKETS.sub("", clean))
    sentences: list[str] = []
    start = 0
    for match in _STOPS.finditer(clean):
        end = match.end()
        closers = _SENTENCE_CLOSERS.match(clean[end:])
        end += len(closers.group()) if closers else 0
        if match.group() == "." and not _full_stop_ends(clean[start:match.start()], clean[end:]):
            continue
        sentences.append(_trim(clean[start:end]))
        start = end
    sentences.append(_trim(clean[start:]))
    return [s for s in sentences if s]


def _quoted(sentence: str) -> str | None:
    """result.js quoted(): whole, or cut at a word with an ellipsis."""
    if _length(sentence) > BRIEF_SENTENCE_LIMIT:
        cut = _head(sentence, BRIEF_SENTENCE_LIMIT - 1)
        space = cut.rfind(" ")
        kept = cut[:space] if space != -1 and _length(cut[:space]) > BRIEF_SENTENCE_LIMIT - 40 else cut
        sentence = re.sub(_js(r"[\s,;:]+\Z"), "", kept, flags=_A) + "…"
    return sentence or None


_CLAUSE_END = re.compile(_js(r"[,;:]\s|[，；：、]|\s[—–]\s"), _A)
_CLAUSE_MIN = 80


def _quoted_at_clause(sentence: str) -> str | None:
    """result.js quotedAtClause(): cut where a clause ends, if one ends in the room."""
    if _length(sentence) <= BRIEF_SENTENCE_LIMIT:
        return sentence or None
    room = _head(sentence, BRIEF_SENTENCE_LIMIT - 1)
    at = -1
    for match in _CLAUSE_END.finditer(room):
        before = room[:match.start()]
        opened = max(before.rfind("["), before.rfind("("), before.rfind("（"))
        closed = max(before.rfind("]"), before.rfind(")"), before.rfind("）"))
        if _length(before) >= _CLAUSE_MIN and opened <= closed:
            at = match.start()
    return _quoted(sentence) if at == -1 else _trim_end(room[:at]) + "…"


_RECOMMENDATION_PREAMBLE = re.compile(
    r"^(?:assessment mode|(?:responsible )?decision (?:owner|context)|评估模式|决策(?:主体|所有者|负责人|背景))", _AI)
_BARE_LABEL = re.compile(
    r"[:：]\Z|^(?:primary|preferred)(?: commercialization)? route\Z|^(?:首选|主要)商业化(?:路线|路径)\Z", _AI)
_LABEL_LIMIT = 80
_SECTION_NOTE = re.compile(_js(
    r"^(?:mode|go\s*\/\s*no[_-]go status|note|evidence bas(?:is|es|e)|rationale|cost, capital and time"
    r"|provenance legend|责任决策者|证据基础|推荐理由)\s*[:：.。]"), _AI)
_ROUTE_LABEL = r"(?:primary|preferred)(?: commerciali[sz]ation)? route|(?:首选|首要|主要|主导)商业化(?:路线|路径)"
_LABEL_REMARK = _js(r"(?:\s*[（(][^（()）]*[）)])?")
_LEADING_LABEL = re.compile(_js(
    "^(?:" + _ROUTE_LABEL + "|route|recommendations?|analyst inference|建议)" + _LABEL_REMARK + r"\s*[:：.。]\s*"), _AI)
_ROUTE_LEAD = re.compile(_js("^(?:" + _ROUTE_LABEL + ")" + _LABEL_REMARK + r"\s*[:：.。]"), _AI)
_ROUTE_HEADING = re.compile(_js(
    r"^#{3,}\s+(?:\d+(?:\.\d+)*[.)]?\s+)?(?:" + _ROUTE_LABEL + ")" + _LABEL_REMARK
    + r"\s*(?:[:：]\s*(" + _DOT + r"*))?\Z"), _AI)
_BOLD_ONLY = re.compile(r"^\*\*[^*]+\*\*\Z", _A)
_LIST_ENTRY = re.compile(_js(r"^(?:[-*]\s|\d+[.)]\s|\*[^*\s])"), _A)
_NUMBERED_OPPORTUNITY = re.compile(_js(r"^(?:opportunity|机遇|机会|路径)\s*[\d一二三四五六七八九十]+\s*[:：.]"), _AI)
_H2 = re.compile(_js(r"^##\s"), _A)
_H1 = re.compile(_js(r"^#\s"), _A)
_SUMMARY_ITEM = re.compile(_js(r"^(?:[-*]|\d+[.)])\s+(" + _DOT + r"+)\Z"), _A)
_STEP_ITEM = re.compile(_js(r"^\s*(?:[-*]|\d+[.)])\s+(" + _DOT + r"+)\Z"), _A)
_BOLD_LEAD = re.compile(_js(r"^\s*(\*\*" + _DOT + r"+)\Z"), _A)
_LEADING_BOLD = re.compile(r"^\*\*[^*]+\*\*", _A)
_LINES = re.compile(r"\r?\n")


def _lines(markdown: str) -> list[str]:
    return _LINES.split(markdown)


def _executive_summary_lead(markdown: str) -> str | None:
    """result.js executiveSummaryLead."""
    inside = False
    first: str | None = None
    for line in _lines(markdown):
        if _H2.search(line):
            inside = bool(_SUMMARY_HEADINGS.search(line))
            continue
        if _H1.search(line) or not inside:
            continue
        text = _trim(line)
        if not text or text.startswith("###") or text[0] in ">|":
            continue
        item = _SUMMARY_ITEM.search(text)
        block = item.group(1) if item else text
        if _RECOMMENDATION_PREAMBLE.search(_trim(re.sub(r"\*+", "", block))):
            continue
        sentences = sentences_of(block)
        if not item and first is None:
            first = sentences[0] if sentences else None
        at = next((i for i, s in enumerate(sentences)
                   if not _ABOUT_THE_REPORT.search(s)
                   and not (_length(s) <= _LABEL_LIMIT and re.search(r"[:：]\Z", s))), -1)
        if at < 0:
            continue
        title = _LEADING_BOLD.search(block) if at == 0 else None
        heads = (title is not None and len(sentences) > 1 and _length(sentences[0]) <= _TITLE_LIMIT
                 and (sentences_of(title.group()) or [None])[0] == sentences[0])
        gap = "" if re.search(r"[。！？]\Z", sentences[0]) else " "
        return sentences[0] + gap + sentences[1] if heads else sentences[at]
    return first


def _heads_a_list(lines: list[str], index: int) -> bool:
    for line in lines[index + 1:]:
        text = _trim(line)
        if text:
            return bool(_LIST_ENTRY.search(text))
    return False


def _recommendation_in(lines: list[str], route_only: bool) -> str | None:
    """result.js recommendationIn."""
    inside = False
    labelled = False
    for index, line in enumerate(lines):
        if _H2.search(line):
            inside = bool(_RECOMMENDATION_HEADINGS.search(line))
            labelled = False
            continue
        text = _trim(line)
        if not inside or not text or text[0] in ">|":
            continue
        if text.startswith("#"):
            route = _ROUTE_HEADING.search(re.sub(r"\*+", "", text))
            if route:
                name = _trim(route.group(1) or "")
                if name:
                    return (sentences_of(name) or [None])[0] or None
                labelled = True
            continue
        item = _STEP_ITEM.search(line) or _BOLD_LEAD.search(line)
        candidate = item.group(1) if item else text if labelled else None
        if not candidate:
            continue
        whole = _trim(re.sub(r"\*+", "", candidate))
        names_route = bool(_ROUTE_LEAD.search(whole))
        if route_only and not labelled and not names_route:
            continue
        if _RECOMMENDATION_PREAMBLE.search(whole) or _SECTION_NOTE.search(whole):
            labelled = False
            continue
        plain = _LEADING_LABEL.sub("", whole, count=1)
        if not plain or (_length(plain) <= _LABEL_LIMIT and _BARE_LABEL.search(plain)):
            labelled = True
            continue
        if (_BOLD_ONLY.search(text) and not names_route and not _NUMBERED_OPPORTUNITY.search(plain)
                and _heads_a_list(lines, index)):
            labelled = True
            continue
        return (sentences_of(plain) or [None])[0] or None
    return None


def _capitalized(sentence: str | None) -> str | None:
    r"""result.js capitalized(): a first word wholly in lower case gets a capital.

    /^\p{Ll}[\p{Ll}'’-]*(?![\p{L}'’-])/u, then the first code point upper-cased.
    """
    if not sentence or unicodedata.category(sentence[0]) != "Ll":
        return sentence
    at = 1
    while at < len(sentence) and (unicodedata.category(sentence[at]) == "Ll" or sentence[at] in "'’-"):
        at += 1
    if at < len(sentence) and unicodedata.category(sentence[at]).startswith("L"):
        return sentence
    return sentence[0].upper() + sentence[1:]


def _first_recommendation(markdown: str) -> str | None:
    lines = _lines(markdown)
    return _capitalized(_recommendation_in(lines, True) or _recommendation_in(lines, False))


def _strings(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def brief_lines(scores: dict[str, Any], markdown: str) -> dict[str, str | None]:
    """The three lines of the page's brief, as result.js decisionBrief has them.

    `markdown` is the report as displayed (report_display.report_for_display),
    which is what the page reads. Each line is given twice: `summary`, `next`
    as the brief shows them (cut to 240 characters where longer), and
    `summary_whole`, `next_whole` uncut, which the page shows when "Show the
    whole sentence" is pressed and None where nothing was cut. `risk` is
    never cut. A line the report does not yield is None; the page then says
    "none stated", and so must whoever shows these.
    """
    text = markdown if isinstance(markdown, str) else ""
    lead = _executive_summary_lead(text)
    risks, opportunities = scores.get("key_risks"), scores.get("key_opportunities")
    risk = _trim(risks[0]) if _strings(risks) and risks and _trim(risks[0]) else None
    opportunity = (_trim(opportunities[0])
                   if _strings(opportunities) and opportunities and _trim(opportunities[0]) else None)
    step = _first_recommendation(text)
    return {
        "summary": _quoted_at_clause(lead) if lead else None,
        "summary_whole": lead if lead and _length(lead) > BRIEF_SENTENCE_LIMIT else None,
        "risk": risk,
        "next": _quoted(step) if step else opportunity,
        "next_whole": step if step and _length(step) > BRIEF_SENTENCE_LIMIT else None,
    }
