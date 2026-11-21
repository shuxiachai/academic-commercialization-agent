"""What the PDF says beside the report: its first-page summary, page header and
footer, document information and file name.

A technology-transfer office or an investor passes the PDF on, not the page.
Until 2026-11-21 the PDF was the report's text alone: no score, no
dimensions, no source counts, no date, model or link back, no page numbers;
its document title read "(anonymous)" and its file name was the run's ID.
The page had all of these. They are put in the PDF from the same files the
page reads them from: the scorecard (/api/runs/{id}/scores), the source
registry (/sources), the run's record (/api/runs/{id}) and its saved request.
Nothing here judges anything, and no model is called.

The words are the page's where the page has them (i18n.js: the dimension
names, the grade words, the brief's labels, the comparison's decision-context
lines, the draft notices; tests/test_report_summary.py holds them equal) and
new only for what the page never says: the "no score" line, the header and
footer, the document information. English and Chinese, chosen by the
report's language as the decision card's are (decision_verdict._CARD_COPY);
any other language gets English.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from urllib.parse import quote

from academic_agent.decision_verdict import _CARD_COPY
from academic_agent.report_brief import band, brief_lines

#: The five dimensions, as result.js DIMENSIONS has them, in its order.
DIMENSIONS: tuple[tuple[str, float, str], ...] = (
    ("trl_score", 9, "dim_trl"),
    ("mrl_score", 10, "dim_mrl"),
    ("patent_strength", 5, "dim_patent"),
    ("market_accessibility", 5, "dim_market"),
    ("evidence_confidence", 5, "dim_evidence"),
)

# Keyed as in i18n.js where the page has the words (the test compares them);
# the rest are the PDF's own.
COPY: dict[str, dict[str, str]] = {
    "English": {
        # i18n.js
        "dim_trl": "Technology readiness",
        "dim_mrl": "Manufacturing readiness",
        "dim_patent": "Patent position",
        "dim_market": "Market accessibility",
        "dim_evidence": "Evidence confidence",
        "band_strong": "Strong",
        "band_moderate": "Moderate",
        "band_early": "Early",
        "band_nascent": "Nascent",
        "readiness": "commercialization readiness",
        "group_academic": "Academic",
        "group_patents": "Patents",
        "group_market": "Market",
        "brief_report_says": "The report's own summary:",
        "brief_risk": "Biggest risk",
        "brief_risk_none": "The scorecard lists no risk.",
        "brief_next": "First recommended step",
        "brief_next_none": "The report gives no numbered recommendation.",
        "compare_context": "Decision context",
        "compare_context_orientation": "None given: an orientation brief",
        "compare_context_incomplete": "Incomplete: not all four required fields were given",
        "compare_context_given": "Given: decision support",
        "compare_context_unknown": "Not recorded",
        "draft_note": "This is an unreviewed, unscored draft. The run stopped before its report was finished: "
                      "this is what the report writer wrote, before the review that checks its citations and "
                      "claims, and with no score. Do not treat it as the assessment.",
        "draft_reviewed_note": "This is a reviewed draft with no score. The run stopped before its report was "
                               "finished: this is the report after the review that checks its citations and "
                               "claims, before the scoring. Do not treat it as the assessment.",
        # The PDF's own
        "summary_title": "At a glance",
        "score_unit": "/ 100",
        "sources": "Sources",
        "sources_line": "{total} in all · {academic} academic · {patent} patents · {market} market",
        "no_score": "This run stopped before scoring, so it has no score.",
        "score_unreadable": "This run's scorecard could not be read, so no score is shown.",
        "header": "ACA · {topic}",
        "page": "Page {page} of {pages}",
        "generated": "Generated {date} UTC",
        "model": "Model: {model}",
        "run": "Run {run_id}",
        "title": "ACA assessment: {topic}",
        "title_draft": "ACA assessment (draft): {topic}",
        "subject": "A commercialization assessment of “{topic}” made by ACA (Academic Commercialization "
                   "Assessment) on {date} UTC: scores, evidence and recommendations with their sources.",
        "subject_draft": "A draft of a commercialization assessment of “{topic}” by ACA (Academic "
                         "Commercialization Assessment), from a run that stopped on {date} UTC before it "
                         "was finished; it has no score.",
        "author": "Academic Commercialization Assessment",
    },
    "Simplified Chinese": {
        "dim_trl": "技术就绪度",
        "dim_mrl": "制造就绪度",
        "dim_patent": "专利地位",
        "dim_market": "市场可及性",
        "dim_evidence": "证据置信度",
        "band_strong": "较强",
        "band_moderate": "中等",
        "band_early": "早期",
        "band_nascent": "萌芽",
        "readiness": "商业化就绪度",
        "group_academic": "学术",
        "group_patents": "专利",
        "group_market": "市场",
        "brief_report_says": "报告自己的摘要：",
        "brief_risk": "最大风险",
        "brief_risk_none": "评分卡没有列出风险。",
        "brief_next": "建议的第一步",
        "brief_next_none": "报告没有给出编号的建议。",
        "compare_context": "决策场景",
        "compare_context_orientation": "未提供：方向性简报",
        "compare_context_incomplete": "不完整：四个必填项没有填全",
        "compare_context_given": "已提供：决策支持",
        "compare_context_unknown": "未记录",
        "draft_note": "这是一份未经审稿和打分的草稿。这次运行在报告完成前停下了：下面是报告撰写这一步写出的文字，"
                      "还没有经过核对引用和论断的审查，也没有评分。请不要把它当作评估结论。",
        "draft_reviewed_note": "这是一份已核查、未评分的草稿。这次运行在报告完成前停下了：下面是经过核对引用和论断的审查"
                               "之后的报告，还没有评分。请不要把它当作评估结论。",
        "summary_title": "评估概要",
        "score_unit": "/ 100",
        "sources": "来源",
        "sources_line": "共 {total} 个 · 学术 {academic} · 专利 {patent} · 市场 {market}",
        "no_score": "这次运行在评分前停止，没有分数。",
        "score_unreadable": "这次运行的评分无法读取，因此不显示分数。",
        "header": "ACA · {topic}",
        "page": "第 {page} 页，共 {pages} 页",
        "generated": "生成于 {date}（UTC）",
        "model": "模型：{model}",
        "run": "运行 {run_id}",
        "title": "ACA 评估：{topic}",
        "title_draft": "ACA 评估（草稿）：{topic}",
        "subject": "ACA（学术成果商业化评估）于 {date}（UTC）对“{topic}”所作的商业化评估：评分、证据和建议，均注明来源。",
        "subject_draft": "ACA（学术成果商业化评估）对“{topic}”的商业化评估草稿：这次运行于 {date}（UTC）在完成前停下，没有评分。",
        "author": "学术成果商业化评估",
    },
}

# The Chinese sentence for each readiness level, as i18n.js trl_level_N has
# it: the scorecard writes its label in English ("TRL 7 (system prototype in
# operational environment)", evidence.py), and a Chinese reader is shown the
# same level in Chinese, as result.js trlText does.
TRL_LEVELS_ZH: dict[str, str] = {
    "1": "TRL 1（发现并报告基本原理）",
    "2": "TRL 2（形成技术概念或应用设想）",
    "3": "TRL 3（通过实验完成概念验证）",
    "4": "TRL 4（部件在实验室环境中得到验证）",
    "5": "TRL 5（部件在相关环境中得到验证）",
    "6": "TRL 6（系统原型在相关环境中完成演示）",
    "7": "TRL 7（系统原型在实际运行环境中完成演示）",
    "8": "TRL 8（系统完成研制并通过鉴定）",
    "9": "TRL 9（实际系统已在运行环境中得到验证）",
}
_TRL_LABEL = re.compile(r"^TRL ([1-9]) \(.+\)$", re.DOTALL)
_SOURCE_LISTS = (("academic", "academic_sources"), ("patent", "patent_sources"), ("market", "market_sources"))
_STOPPED = frozenset({"failed", "cancelled", "timeout"})


def copy_for(language: str | None) -> dict[str, str]:
    return COPY.get(language or "", COPY["English"])


def _score(value: Any, highest: float) -> bool:
    """result.js scoreNumber: a finite number in 0..highest (not a bool)."""
    return (not isinstance(value, bool) and isinstance(value, int | float)
            and value == value and 0 <= value <= highest)  # value == value refuses NaN


def js_number(value: float) -> str:
    """A number as JavaScript's String(number) writes it ("4" for 4.0, "6.5")."""
    if float(value).is_integer():
        return str(int(value))
    return repr(float(value))


def fixed1(value: float) -> str:
    """Number.prototype.toFixed(1): the nearer tenth, the larger on a tie."""
    return str(Decimal(float(value)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


def _trl_text(label: str, language: str | None) -> str:
    level = _TRL_LABEL.match(label)
    if language == "Simplified Chinese" and level:
        return TRL_LEVELS_ZH[level.group(1)]
    return label


def source_counts(sources: Any) -> dict[str, int] | None:
    """How many sources the registry holds, per domain; None when it cannot be read as one."""
    if not isinstance(sources, dict):
        return None
    counts = {}
    for domain, key in _SOURCE_LISTS:
        rows = sources.get(key)
        if not isinstance(rows, list):
            return None
        counts[domain] = len(rows)
    return counts


def _context_line(mode: Any, copy: dict[str, str]) -> str:
    return copy[{
        "decision_support": "compare_context_given",
        "orientation": "compare_context_orientation",
        "decision_context_incomplete": "compare_context_incomplete",
    }.get(mode, "compare_context_unknown")]


def summary(*, state: str, scores: Any, sources: Any, mode: Any, question: dict[str, Any] | None,
            markdown: str, language: str | None) -> dict[str, Any]:
    """The first page's summary block, as lines of text.

    `scores` and `sources` are the run's scorecard and source registry as
    parsed JSON, or None where the file is missing or unreadable; `mode` is
    the gate's mode from the run's record; `question` the decision owner
    and the decision from its saved request; `markdown` the report as
    displayed. Without a readable overall score there is no block, only a
    sentence saying why (`note`): a run that stopped before scoring, or a
    scorecard that cannot be read.
    """
    copy = copy_for(language)
    overall = scores.get("overall_score") if isinstance(scores, dict) else None
    if not _score(overall, 100):
        return {"note": copy["no_score" if state in _STOPPED else "score_unreadable"]}
    rows = []
    for key, highest, label in DIMENSIONS:
        value = scores.get(key)
        valid = _score(value, highest) and value >= 1
        note = ""
        if key == "trl_score" and isinstance(scores.get("trl_label"), str) and scores["trl_label"].strip():
            note = _trl_text(scores["trl_label"].strip(), language)
        rows.append((copy[label], f"{js_number(value)} / {js_number(highest)}" if valid else "—", note))
    counts = source_counts(sources)
    chinese = language == "Simplified Chinese"
    card = _CARD_COPY["Simplified Chinese" if chinese else "English"]
    asked = []
    for key, field in (("owner", "decision_owner"), ("decision", "decision_type")):
        value = (question or {}).get(field)
        if isinstance(value, str) and value.strip():
            asked.append(f"{card[key]}{'：' if chinese else ': '}{value.strip()}")
    context = (copy["compare_context"], _context_line(mode, copy), asked)
    lines = brief_lines(scores, markdown)
    # As the page's brief: the summary line only where the report yields
    # one, the risk and the step always, saying so when there is none.
    # Uncut: a PDF has no "Show the whole sentence" button.
    # Each line is (label, text, whether the text is a quotation of the report).
    brief = [(copy["brief_report_says"], lines["summary_whole"] or lines["summary"], True)] if lines["summary"] else []
    brief.append((copy["brief_risk"], lines["risk"] or copy["brief_risk_none"], False))
    brief.append((copy["brief_next"], lines["next_whole"] or lines["next"] or copy["brief_next_none"], False))
    return {
        "title": copy["summary_title"],
        "score": fixed1(overall),
        "unit": copy["score_unit"],
        "band": copy["band_" + band(overall)],
        "band_key": band(overall),
        "readiness": copy["readiness"],
        "rows": rows,
        "sources": None if counts is None else (
            copy["sources"], copy["sources_line"].format(total=sum(counts.values()), **counts),
        ),
        "context": context,
        "brief": brief,
    }


def report_date(run_id: str, ended_at: Any = None) -> str:
    """The day (UTC) the report was made: when the run ended, else when it started."""
    if isinstance(ended_at, str):
        try:
            ended = datetime.fromisoformat(ended_at)
        except ValueError:
            ended = None
        if ended is not None and ended.tzinfo is not None:
            return ended.astimezone(UTC).date().isoformat()
    try:
        return datetime.strptime(run_id.split("-")[0], "%Y%m%dT%H%M%SZ").date().isoformat()
    except ValueError:
        return ""


def page_text(*, topic: str, run_id: str, run_link: str | None, date: str, model: str | None,
              language: str | None, draft: bool = False) -> dict[str, Any]:
    """The words around every page, and the document information."""
    copy = copy_for(language)
    topic = " ".join(str(topic or "").split()) or run_id
    footer = [copy["generated"].format(date=date)] if date else []
    if model:
        footer.append(copy["model"].format(model=model))
    return {
        "header": copy["header"].format(topic=topic),
        "page": copy["page"],
        "link": run_link,
        "link_text": run_link if run_link else copy["run"].format(run_id=run_id),
        "footer": " · ".join(footer),
        "title": copy["title_draft" if draft else "title"].format(topic=topic),
        "subject": copy["subject_draft" if draft else "subject"].format(topic=topic, date=date),
        "author": copy["author"],
    }


def draft_note(stage: str, language: str | None) -> str:
    """What the page says above a draft (result.js draftWording), to a reader who cannot resume it."""
    copy = copy_for(language)
    return copy["draft_reviewed_note" if stage == "reviewer" else "draft_note"]


# Characters a file name cannot carry on Windows, and control characters.
_UNSAFE = re.compile(r'[/\\:*?"<>|\x00-\x1f\x7f]')
_NAME_LIMIT = 60


def _cut(name: str) -> str:
    """At most _NAME_LIMIT characters, at a hyphen where one is near the end."""
    if len(name) <= _NAME_LIMIT:
        return name
    head = name[:_NAME_LIMIT]
    at = head.rfind("-")
    return (head[:at] if at >= _NAME_LIMIT // 2 else head).strip("-.")


def download_names(topic: str, date: str, *, draft: bool = False) -> tuple[str, str]:
    """(ASCII name, UTF-8 name) for the PDF download.

    "ACA-perovskite-silicon-tandem-solar-cells-2026-11-18.pdf". The UTF-8
    name keeps the topic's own letters ("ACA-特高压直流输电-2026-11-08.pdf")
    and goes in filename*; the ASCII one is the fallback for a client that
    reads only filename, and is the same name for an English topic.
    """
    ascii_topic = unicodedata.normalize("NFKD", str(topic or "")).encode("ascii", "ignore").decode("ascii")
    slug = _cut(re.sub(r"[^a-z0-9]+", "-", ascii_topic.lower()).strip("-"))
    words = _cut(re.sub(r"\s+", "-", _UNSAFE.sub("", str(topic or "")).strip()).strip("-."))
    tail = "-".join(part for part in (date, "draft" if draft else "") if part)

    def named(middle: str) -> str:
        return "-".join(part for part in ("ACA", middle, tail) if part) + ".pdf"

    fallback = named(slug or "report")
    return fallback, (named(words) if words and not words.isascii() else fallback)


def content_disposition(topic: str, date: str, *, draft: bool = False) -> str:
    """The header for the download: an ASCII filename and an RFC 5987 filename*."""
    fallback, name = download_names(topic, date, draft=draft)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(name, safe='')}"
