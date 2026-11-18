"""The conclusion a decision-support report states, read back from its own text.

A reader who fills in the decision context asks one question: should this
decision-maker go ahead. The writer is told to answer it with exactly one of
GO, NO_GO or DEFER (config/tasks.yaml), and it does, somewhere in thirty-eight
thousand characters: the run that prompted this module said "the
actor-specific conclusion is DEFER because ..." in the last paragraph of its
executive summary, and the page, the comparison and the PDF never showed it.

This module finds that sentence. It reads; it does not judge:

- Nothing is inferred. A report that argues its way to "wait" without one of
  the words is reported as stating no conclusion, and the page says so.
- Precision over recall. A conclusion is taken only from a sentence that ties
  a verdict word to the conclusion itself: a label ("Decision: DEFER"), a
  statement ("the conclusion is DEFER", "we recommend a NO_GO"), or DEFER or
  NO_GO standing alone at the head of a paragraph. A verdict word anywhere
  else is not one. Measured on the 1,797 reports saved on the maintainer's
  machine (2026-11-18, none of them in decision-support mode): 400 lines
  use GO, NO_GO or DEFER and none states a conclusion. They say, in English
  or Chinese, that no GO/NO_GO is assessed; or they name graphene oxide
  ("GO") or a product ("Carbyon GO"). The rule finds a conclusion in none.
- Statements that disagree are reported as disagreeing, with each of them;
  the module does not pick one.

It changes no score and no saved byte, and it is not the applicability
paragraph (report_applicability.py), which says whether a conclusion is
permitted. That paragraph is removed before reading, so the permission is
never read as the conclusion.

No model is called. The same answer serves the page, the comparison and the
PDF, so the three cannot disagree.
"""

from __future__ import annotations

import re
from typing import Any

from academic_agent.report_applicability import _OWNED_BLOCK

#: The four conclusions a card can show, in the order a reader ranks them.
VERDICTS = ("go", "conditional_go", "defer", "no_go")

STATED = "stated"
NOT_STATED = "not_stated"
CONFLICTING = "conflicting"

_CITATION = re.compile(r"\s*[\[(]\s*[APM]\d+(?:\s*[-,;]\s*[APM]\d+)*\s*[\])]")

# The vocabulary named as a vocabulary: "GO/NO_GO", "GO, NO_GO, or DEFER",
# "GO or NO-GO". It says what may be concluded, never what was.
_NO_GO = r"NO[ _-]?GO"
_ENUMERATION = re.compile(
    rf"\bGO\s*/\s*{_NO_GO}(?:\s*/\s*DEFER)?\b"
    rf"|\bGO\s*,\s*{_NO_GO}\s*,?\s*(?:or|and|或|和)\s*DEFER\b"
    rf"|\bGO\s+(?:or|versus|vs\.?|或)\s+{_NO_GO}(?:\s+(?:or|或)\s+DEFER)?\b"
    rf"|\b{_NO_GO}\s*(?:,|/|or|或)\s*(?:or\s+)?DEFER\b",
    re.IGNORECASE,
)

# A verdict word as the writer's contract spells it. Upper case in prose:
# "we defer to the registry" and "go to market" are not conclusions.
_CONDITIONAL_BEFORE = r"(?:CONDITIONAL|Conditional|conditional|QUALIFIED|Qualified|qualified|有条件(?:的)?)[ _-]?"
_CONDITIONAL_AFTER = (
    r"\s*[,(（—–-]?\s*(?:with conditions?|conditional(?:ly)?\b|subject to\b|contingent (?:up)?on\b"
    r"|provided that\b|附条件|有条件)"
)
_TOKEN = re.compile(
    rf"(?P<conditional>{_CONDITIONAL_BEFORE}GO\b|\bGO\b(?={_CONDITIONAL_AFTER}))"
    rf"|(?P<no_go>\b{_NO_GO}\b(?![-'’\w]))"
    r"|(?P<defer>\bDEFER\b(?![-'’\w]))"
    r"|(?P<go>\bGO\b(?![-'’\w]))"
)
# After a label the word is the whole answer, so its case is free:
# "**Decision:** Defer." A word that goes on is prose ("Go to market via...",
# "defer to the registry record") unless what follows is its reason or its
# condition ("Defer until module data exist", "No-go because...").
_LABELLED_TOKEN = re.compile(
    rf"(?P<conditional>{_CONDITIONAL_BEFORE}go\b|\bgo\b(?={_CONDITIONAL_AFTER}))"
    r"|(?P<no_go>\bno[ _-]?go\b)"
    r"|(?P<defer>\bdefer(?:red|ral)?\b)"
    r"|(?P<go>\bgo\b)",
    re.IGNORECASE,
)
_CHINESE_TOKEN = re.compile(
    r"(?P<conditional>有条件(?:的)?(?:通过|推进|许可|批准|同意))"
    r"|(?P<no_go>不通过|否决|不予(?:推进|许可|批准|投资))"
    r"|(?P<defer>暂缓(?:决策|决定|推进|许可|投资)?|推迟决策|延后决策)"
)
_AFTER_A_LABELLED_WORD = re.compile(
    r"\s*(?:$|[.。;；,，:：—–(（\[]|\*\*|`|-\s"
    r"|(?:because|since|given|until|pending|unless|while|for now|at this stage|subject to)\b)",
    re.IGNORECASE,
)
# "GO" is also graphene oxide and part of product names ("we recommend GO
# inks", "the Carbyon GO machine"). As a conclusion it ends its clause or is
# followed by its reason or its bound, never by the thing it names.
_AFTER_GO = re.compile(
    r"\s*(?:$|[.。;；,，:：—–)(（\[]|-\s"
    r"|(?:because|since|given|as|for|on|with|but|and|only|provided|subject|bounded|conditional|contingent)\b)",
    re.IGNORECASE,
)

_CODES = {"conditional": "conditional_go", "no_go": "no_go", "defer": "defer", "go": "go"}

# What ties a verdict word to the conclusion. Each is tried on one sentence.
_CONCLUSION_NOUN = (
    r"(?:conclusion|recommendation|verdict|decision|determination|outcome|ruling"
    r"|GO\s*/\s*NO[ _-]?GO(?:\s*/\s*DEFER)?(?:\s+(?:status|conclusion|decision|determination|recommendation|outcome))?)"
)
_LABEL = re.compile(
    rf"^(?:(?:the|our|this)\s+)?(?:[\w'’-]+\s+){{0,3}}{_CONCLUSION_NOUN}"
    r"(?:\s+(?:for|on|to)\s+[^:：]{1,80})?\s*[:：]\s*(?P<rest>.+)$",
    re.IGNORECASE,
)
_CHINESE_LABEL = re.compile(
    r"^(?:[一-鿿]{0,8})?(?:结论|决策结论|决策建议|最终建议|建议结论|判定|裁定)(?:为|是)?\s*[:：]\s*(?P<rest>.+)$"
)
_STATEMENT = re.compile(
    rf"\b{_CONCLUSION_NOUN}\b(?P<between>[^.;:!?。；：]{{0,80}}?)"
    r"\b(?:is|was|remains|stands at|is therefore|is thus|is to|is a|is an)\s+(?P<rest>.+)$",
    re.IGNORECASE,
)
_TIE_NOUN = re.compile(rf"\b{_CONCLUSION_NOUN}\b", re.IGNORECASE)
# The two below match the tie alone; what follows it is read by the caller.
_VERB = re.compile(r"\b(?:conclud(?:e|es|ed)|recommend(?:s|ed)?|advis(?:e|es|ed))\b", re.IGNORECASE)
_CHINESE_STATEMENT = re.compile(r"(?:结论|建议|判定|裁定|决策)(?:[一-鿿]{0,6})?(?:为|是)")
# How far past the tie the word may stand: "is a clear, evidence-conditioned DEFER".
_REACH = 48
# Between the tie and the word, any of these means the sentence says something else.
_UNSAID = re.compile(
    r"\b(?:not|no|never|neither|nor|cannot|can't|without|whether|if|unless|either|would|could|might|may|should a)\b"
    r"|未|不(?!通过|予)|无法|是否|若|如果|除非",
    re.IGNORECASE,
)
# A verdict word followed by its trigger is a criterion, not a conclusion. The
# writer's contract asks every report for a gated action plan with pass
# thresholds and stop criteria, so "Gate 2 decision: NO_GO if outdoor loss
# exceeds 3% a year" is a line to expect beside the real conclusion, and read
# as one it would turn a DEFER into a disagreement. "Until", "unless" and
# "because" are not here: "DEFER until module data exist" concludes now.
_CRITERION_AFTER = re.compile(
    r"\s*[,;(（]?\s*(?:(?:only\s+)?(?:if|when|whenever|where|should|in case|in the event|otherwise)\b|如果|若|当)",
    re.IGNORECASE,
)
# Said of the report's mode or of a criterion, wherever the word stands.
_NOT_A_CONCLUSION = re.compile(
    r"\bnot (?:been )?(?:assessed|issued|given|provided|rendered|made|offered|permitted|applicable)\b"
    r"|\bis (?:permitted|allowed)\b|\bmay be (?:given|issued)\b"
    r"|未评估|不评估|不给出|未给出|不提供|不适用|允许(?:针对|给出)",
    re.IGNORECASE,
)

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_SKIPPED_SECTIONS = re.compile(r"^(?:references|参考文献|reviewer notes|自动校对记录|evidence limitations|证据局限)", re.IGNORECASE)
_LIST_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])\s+")

# Sentences. The page's own rule (result.js fullStopEnds), for the same reason:
# a line cut inside "e.g." or "52.8%" reads as a claim the report never made.
_NEVER_ENDS = re.compile(r"(?:^|[\s(\[“\"'‘/—-])(?:e\.g|i\.e|vs|cf|et al|approx|ca|Dr|Inc|Ltd|Corp|Co|Nos?|Figs?|U\.S|U\.K)$")
_STOP = re.compile(r"[.!?。！？]+")
_CLOSERS = re.compile(r"^[)\]\"'”’」』）*`]+")
_LOWERCASE_WORD = re.compile(r"^[a-z][a-z'’-]*[,;:]?(?:\s|$)")

_STATEMENT_LIMIT = 600
_FOLLOWS = 2
_NEEDLE_LIMIT = 80


def _sentences(text: str) -> list[str]:
    out: list[str] = []
    start = 0
    for stop in _STOP.finditer(text):
        end = stop.end()
        closer = _CLOSERS.match(text[end:])
        if closer:
            end += closer.end()
        if stop.group() == ".":
            after = text[end:]
            before = text[start:stop.start()]
            # A citation after the stop belongs to the sentence it closes.
            cited = _CITATION.match(after)
            if cited and not after[cited.end():].strip():
                continue
            if not after[:1].isspace() and after:
                continue
            if _LOWERCASE_WORD.match(after.lstrip()) or _NEVER_ENDS.search(before):
                continue
        sentence = text[start:end].strip()
        if sentence:
            out.append(sentence)
        start = end
    tail = text[start:].strip()
    if tail:
        # "...insufficient. [A1]" leaves the citation behind its sentence.
        if out and not _CITATION.sub("", tail).strip():
            out[-1] = f"{out[-1]} {tail}"
        else:
            out.append(tail)
    return out


def _plain(text: str) -> str:
    """The words as a page shows them: emphasis and code marks gone, spaces single."""
    return re.sub(r"\s+", " ", re.sub(r"\*\*|__|`", "", text)).strip()


def _first_token(text: str, pattern: re.Pattern[str]) -> tuple[str, re.Match[str]] | None:
    masked = _ENUMERATION.sub(lambda m: " " * len(m.group()), text)
    match = pattern.search(masked)
    if match is None:
        return None
    return _CODES[match.lastgroup or ""], match


def _bound_verdict(rest: str, *, labelled: bool) -> str | None:
    """The verdict word the tie reaches in `rest`, or None."""
    found = _first_token(rest, _LABELLED_TOKEN if labelled else _TOKEN)
    chinese = _CHINESE_TOKEN.search(rest)
    if chinese and (found is None or chinese.start() < found[1].start()):
        found = (_CODES[chinese.lastgroup or ""], chinese)
    if found is None:
        return None
    code, match = found
    if match.start() > _REACH or _UNSAID.search(rest[:match.start()]):
        return None
    if _CRITERION_AFTER.match(rest[match.end():]):
        return None
    if labelled and match.re is _LABELLED_TOKEN and not match.group().isupper():
        if not _AFTER_A_LABELLED_WORD.match(rest[match.end():]) and code != "conditional_go":
            return None
    if code == "go" and not _AFTER_GO.match(rest[match.end():]):
        return None
    return code


def _verdict_in(sentence: str, *, heads_block: bool) -> tuple[str, bool] | None:
    """The conclusion this one sentence states and whether the sentence is the
    report's own conclusion line (a label, or the word alone), or None."""
    plain = _plain(_CITATION.sub("", sentence))
    plain = _LIST_ITEM.sub("", plain)
    if _NOT_A_CONCLUSION.search(plain):
        return None
    for label in (_LABEL, _CHINESE_LABEL):
        match = label.match(plain)
        if match:
            code = _bound_verdict(match["rest"], labelled=True)
            if code:
                return code, True
    # Every tie in the sentence is tried, not only the first. "In
    # decision-support mode the preferred route is a licence; however, the
    # conclusion is DEFER because..." has two such nouns before an "is", and
    # the first leads nowhere. The production report that shaped this wrote
    # "decision_support", which is one word, and so hid the miss.
    for noun in _TIE_NOUN.finditer(plain):
        statement = _STATEMENT.match(plain, noun.start())
        # "The conclusion is that GO inks are closer to market" goes on to a clause.
        if (statement and not _UNSAID.search(statement["between"])
                and not re.match(r"that\b", statement["rest"], re.IGNORECASE)):
            code = _bound_verdict(statement["rest"], labelled=False)
            if code:
                return code, False
    for tie in (_VERB, _CHINESE_STATEMENT):
        for match in tie.finditer(plain):
            code = _bound_verdict(plain[match.end():], labelled=False)
            if code:
                return code, False
    if heads_block:
        # "**DEFER.** Module-scale validation is not yet..." at the head of a
        # paragraph or a list item: the word alone, then its punctuation.
        # Not a bare GO: "GO: graphene oxide" heads a glossary line.
        found = _first_token(plain, _TOKEN)
        if (found and found[0] != "go" and found[1].start() == 0
                and re.match(r"\s*(?:[.。:：—–]|-\s|$)", plain[found[1].end():])):
            return found[0], True
    return None


def _needle(statement: str) -> str:
    """The longest stretch of the statement with no citation in it, as the page prints it."""
    runs = [_plain(run) for run in _CITATION.split(statement)]
    longest = max(runs, key=len, default="")
    return longest[:_NEEDLE_LIMIT].strip()


def _blocks(report: str):
    """(section heading, block text) for every paragraph and list item read."""
    section = ""
    skipped = False
    block: list[str] = []
    fenced = False

    def flush():
        if block:
            text = " ".join(block)
            block.clear()
            return text
        return None

    for raw in report.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            fenced = not fenced
            text = flush()
            if text and not skipped:
                yield section, text
            continue
        if fenced:
            continue
        heading = _HEADING.match(line)
        if heading:
            text = flush()
            if text and not skipped:
                yield section, text
            if len(heading[1]) <= 2:
                section = _plain(heading[2])
                skipped = bool(_SKIPPED_SECTIONS.match(section))
            elif not skipped:
                # "### Decision: DEFER" states it as well as a paragraph does.
                yield section, heading[2]
            continue
        if not line or line.startswith(("|", ">")) or _LIST_ITEM.match(line):
            text = flush()
            if text and not skipped:
                yield section, text
            if line.startswith(">"):
                line = line.lstrip("> ").strip()
            if not line or line.startswith("|"):
                continue
        block.append(line)
    text = flush()
    if text and not skipped:
        yield section, text


#: The card's words where no interface language applies: the PDF, which is in
#: the report's language. The page words the same card from i18n.js;
#: tests/test_decision_verdict.py holds the two to the same statements.
_CARD_COPY: dict[str, dict[str, str]] = {
    "English": {
        "title": "Decision conclusion",
        "owner": "Decision owner",
        "decision": "Decision to make",
        "go": "GO",
        "conditional_go": "Conditional GO",
        "defer": "DEFER",
        "no_go": "NO-GO",
        "says": "The report says:",
        "where": "Stated in the report's section “{section}”.",
        "not_stated": "The report states no clear conclusion",
        "not_stated_detail": (
            "No sentence of the report gives GO, NO-GO or DEFER as its conclusion for this "
            "decision. This card only quotes the report and infers nothing; read its "
            "recommendations section."
        ),
        "conflicting": "The report states conclusions that disagree",
        "conflicting_detail": "Each is quoted below as written; this card does not choose between them.",
        "in_section": "{verdict}, in “{section}”:",
        "note": "Read from the report's own text. The scores are not changed by it.",
    },
    "Simplified Chinese": {
        "title": "决策结论",
        "owner": "决策负责人",
        "decision": "待作决策",
        "go": "GO",
        "conditional_go": "有条件 GO",
        "defer": "暂缓",
        "no_go": "NO-GO",
        "says": "报告原文：",
        "where": "出自报告“{section}”一节。",
        "not_stated": "报告没有给出明确结论",
        "not_stated_detail": (
            "报告中没有一句话把 GO、NO-GO 或暂缓作为这项决策的结论写出来。"
            "这张卡只引用报告原文，不作推断；请阅读报告的建议部分。"
        ),
        "conflicting": "报告在不同位置给出了不一致的结论",
        "conflicting_detail": "下面按原文逐条引用，这张卡不替报告取舍。",
        "in_section": "{verdict}，出自“{section}”：",
        "note": "摘自报告原文，不改变评分。",
    },
}


def joined(sentences: list[str]) -> str:
    """Sentences as one passage: a space between them, none after a Chinese full stop."""
    passage = ""
    for sentence in sentences:
        passage += ("" if not passage or passage[-1] in "。！？" else " ") + sentence
    return passage


def card_text(question: dict[str, Any] | None, conclusion: dict[str, Any], language: str) -> dict[str, Any]:
    """The card as lines of text, in the report's language (English otherwise).

    `tone` is the verdict code, or the status when there is no single verdict.
    """
    copy = _CARD_COPY.get(language, _CARD_COPY["English"])
    asked = []
    for key in ("owner", "decision"):
        value = (question or {}).get("decision_owner" if key == "owner" else "decision_type")
        if isinstance(value, str) and value.strip():
            asked.append(f"{copy[key]}: {value.strip()}" if language != "Simplified Chinese"
                         else f"{copy[key]}：{value.strip()}")
    status = conclusion.get("status")
    card: dict[str, Any] = {"title": copy["title"], "asked": asked, "note": copy["note"], "quotes": [], "where": None}
    if status == STATED:
        card.update(tone=conclusion["verdict"], headline=copy[conclusion["verdict"]], detail=None)
        card["quotes"] = [(copy["says"], joined([conclusion["statement"], *conclusion.get("follows", [])]))]
        if conclusion.get("section"):
            card["where"] = copy["where"].format(section=conclusion["section"])
    elif status == CONFLICTING:
        card.update(tone=CONFLICTING, headline=copy["conflicting"], detail=copy["conflicting_detail"])
        card["quotes"] = [
            (copy["in_section"].format(verdict=copy[item["verdict"]], section=item["section"]), item["statement"])
            for item in conclusion.get("statements", [])
        ]
    else:
        card.update(tone=NOT_STATED, headline=copy["not_stated"], detail=copy["not_stated_detail"])
    return card


def find_verdict(report: str) -> dict[str, Any]:
    """What the report itself concludes for the decision it was asked about.

    `status` is "stated" (one conclusion, wherever it is repeated),
    "conflicting" (statements that name different conclusions) or
    "not_stated". For a stated one: `verdict`, the `statement` as written
    (the report's own conclusion line where it has one, else the first place
    it is said), the `section` it stands in, up to two sentences that follow it in the same
    paragraph (`follows`: the reasons and conditions the writer put next to
    it), and a `needle`, text a page can find the paragraph by. `statements`
    lists every one found, so a disagreement can be shown rather than hidden.
    """
    text = _OWNED_BLOCK.sub("", report or "")
    statements: list[dict[str, Any]] = []
    own_lines: list[int] = []
    for section, block in _blocks(text):
        sentences = _sentences(block)
        for index, sentence in enumerate(sentences):
            stated = _verdict_in(sentence, heads_block=index == 0)
            if stated is None:
                continue
            code, own_line = stated
            if own_line:
                own_lines.append(len(statements))
            shown = _plain(_LIST_ITEM.sub("", sentence))
            statements.append({
                "verdict": code,
                "statement": shown[:_STATEMENT_LIMIT],
                "section": section,
                "follows": [_plain(s)[:_STATEMENT_LIMIT] for s in sentences[index + 1:index + 1 + _FOLLOWS]],
                "needle": _needle(_LIST_ITEM.sub("", sentence)),
            })
    codes = sorted({item["verdict"] for item in statements}, key=VERDICTS.index)
    if not statements:
        return {"status": NOT_STATED, "verdict": None, "statement": None, "section": None,
                "follows": [], "needle": None, "statements": []}
    if len(codes) > 1:
        return {"status": CONFLICTING, "verdict": None, "statement": None, "section": None,
                "follows": [], "needle": None, "statements": statements}
    # Which of several agreeing statements to quote. The report's own
    # conclusion line where it has one ("Conclusion: DEFER."), else the first.
    # The one production report read for this (2026-11-18) says DEFER twice:
    # in passing, at the end of a long sentence about the preferred route in
    # its summary, and as a labelled line in its recommendations, followed by
    # the reasons and by what would reopen the decision. The second is what a
    # reader of the card is after, and the contract puts the conclusion there.
    shown = statements[own_lines[0]] if own_lines else statements[0]
    return {"status": STATED, **shown, "statements": statements}
