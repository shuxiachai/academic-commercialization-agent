"""How a saved report reads on screen and in its PDF; the saved file is not touched.

The saved Markdown is the audit record, and its download keeps every byte.
Two code-written parts of it read badly as delivered:

- The applicability paragraph states the gate as codes ("Mode `orientation`
  ... `not_established`"). Shown, it becomes the same facts as sentences, in
  English or Chinese; other languages keep the paragraph as saved, without its
  marker (applicability_for_display).
- The reference list is written by the pinned evidence.py: a title or reason
  that already ends in a full stop gets a second one, and a Chinese report
  carries English labels and codes. Shown, the doubled stops go, and a Chinese
  report gets Chinese labels. The reasons themselves stay as written.

Nothing here changes what the gate allowed: the sentences are chosen from the
codes in the saved paragraph, and an unknown code keeps the saved wording.
"""

from __future__ import annotations

import re

from academic_agent.report_applicability import (
    _COPY,
    _OPENING_TITLE,
    _OWNED_BLOCK,
    applicability_for_display,
)

_SCOPE: dict[str, dict[str, str]] = {
    "English": {
        "label": "Scope of this assessment",
        "orientation": "An orientation brief: no decision context was given, so it gives no "
                       "GO/NO_GO for a particular decision-maker.",
        "decision_context_incomplete": "The decision context is incomplete, so no GO/NO_GO is "
                                       "given for a particular decision-maker.",
        "decision_support": "Decision support: the context given allows a GO/NO_GO for this "
                            "decision-maker; the cited evidence still governs it.",
        "not_allowed": "No GO/NO_GO is given for a particular decision-maker.",
        "not_established": "No success criteria were given, so any thresholds in the report are "
                           "the analyst's proposals.",
        "user_supplied_unapproved": "Success criteria were supplied but not confirmed by the "
                                    "decision-maker.",
        "owner_approved": "The decision-maker approved the success criteria.",
    },
    "Simplified Chinese": {
        "label": "评估范围",
        "orientation": "方向性简报：没有提供具体决策场景，因此不针对任何决策者给出 GO/NO_GO。",
        "decision_context_incomplete": "决策场景信息不完整，因此不针对具体决策者给出 GO/NO_GO。",
        "decision_support": "决策支持：已提供的决策场景允许针对该决策者给出 GO/NO_GO，结论仍以引用证据为准。",
        "not_allowed": "不针对具体决策者给出 GO/NO_GO。",
        "not_established": "未提供成功标准，报告中的决策门槛均为分析者建议。",
        "user_supplied_unapproved": "已提供成功标准，但未经决策者确认。",
        "owner_approved": "成功标准已获决策者批准。",
    },
}
_MODES = ("orientation", "decision_context_incomplete", "decision_support")
_PROVENANCE = ("not_established", "user_supplied_unapproved", "owner_approved")
_CODE = re.compile(r"`([a-z_]+)`")

# evidence._canonical_reference_section, entry by entry.
_ENTRY = re.compile(
    r"^\[(?P<id>[APM]\d+)\] (?P<head>.*?) Published: (?P<published>.*?)\. "
    r"Accessed: (?P<accessed>.*?)\. Type: (?P<type>[a-z_]+)\. "
    r"Credibility: (?P<credibility>high|medium|low)\. Rationale: (?P<why>.*?)\.+ (?P<url>\S+)\s*$"
)
_TYPES_ZH = {
    "academic_paper": "学术论文", "patent": "专利", "company_disclosure": "公司披露",
    "government": "政府来源", "standards_body": "标准机构", "research_institute": "研究机构",
    "market_report": "市场报告", "reputable_news": "新闻报道", "other": "其他",
}
_TIERS_ZH = {"high": "高", "medium": "中", "low": "低"}


def _delivered_block(report: str) -> re.Match[str] | None:
    """The owned paragraph, only where delivery puts it (first, or after an opening H1)."""
    match = _OWNED_BLOCK.search(report)
    if match is None:
        return None
    prefix = report[:match.start()]
    title = _OPENING_TITLE.match(prefix)
    if prefix.strip() and (title is None or prefix[title.end():].strip()):
        return None
    return match


def _block_language(block: str) -> str | None:
    for language, copy in _COPY.items():
        if f"**{copy['label']}:**" in block:
            return language
    return None


def _scope_paragraph(block: str, language: str) -> str | None:
    scope = _SCOPE.get(language)
    codes = _CODE.findall(block)
    if scope is None or len(codes) != 2 or codes[0] not in _MODES or codes[1] not in _PROVENANCE:
        return None
    mode, provenance = codes
    allowed = _COPY[language]["allowed"] in block
    if allowed and mode != "decision_support":
        return None  # a permission the mode does not carry: keep the saved words
    # A support label without the permission is described by the permission.
    sentences = [scope[mode] if mode != "decision_support" or allowed else scope["not_allowed"]]
    sentences.append(scope[provenance])
    if provenance != "not_established":
        sentences.append(_COPY[language]["caveat"])
    if language == "Simplified Chinese":
        return f"**{scope['label']}：**" + "".join(sentences)
    return f"**{scope['label']}:** " + " ".join(sentences)


def _report_language(report: str) -> str:
    block = _delivered_block(report)
    return (block and _block_language(block.group())) or "English"


def _references(report: str, language: str) -> str:
    marker = "\n## References\n"
    at = report.find(marker)
    if at == -1:
        return report
    body, refs = report[:at], report[at:]
    lines = []
    for line in refs.split("\n"):
        entry = _ENTRY.match(line)
        if entry is None:
            lines.append(line)
            continue
        head = re.sub(r"\.{2,}", ".", entry["head"]).rstrip(". ")
        why = entry["why"].rstrip(". ")
        published = entry["published"]
        if language == "Simplified Chinese":
            lines.append(
                f"[{entry['id']}] {head}. 发布：{'未注明' if published == 'n.d.' else published} · "
                f"访问：{entry['accessed']} · 类型：{_TYPES_ZH.get(entry['type'], entry['type'])} · "
                f"可信度：{_TIERS_ZH[entry['credibility']]} · 依据：{why}. {entry['url']}"
            )
        else:
            lines.append(
                f"[{entry['id']}] {head}. Published: {published.rstrip('.')}. Accessed: {entry['accessed']}. "
                f"Type: {entry['type']}. Credibility: {entry['credibility']}. Rationale: {why}. {entry['url']}"
            )
    refs = "\n".join(lines)
    if language == "Simplified Chinese":
        refs = refs.replace(marker, "\n## 参考文献\n", 1)
    return body + refs


def report_for_display(report: str) -> str:
    """The report as the page and the PDF show it. The saved bytes stay as they are."""
    language = _report_language(report)
    block = _delivered_block(report)
    shown = applicability_for_display(report)
    if block is not None:
        paragraph = _scope_paragraph(block.group(), language)
        if paragraph is not None:
            shown = report[:block.start()] + paragraph + report[block.end():]
    return _references(shown, language)
