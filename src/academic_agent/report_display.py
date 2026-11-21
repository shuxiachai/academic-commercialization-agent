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
- The proofreading record ("## Reviewer Notes") is written by code under an
  English heading. A Chinese report shows that heading in Chinese; the notes
  stay as saved.

- The section headings are a fixed set (evidence._REQUIRED_REPORT_HEADINGS).
  A report in another language is written under translations of them, and
  until 2026-11-19 a model call made that translation at the start of every
  such run. When the call failed, the writer was given the English headings
  and the report was saved with them: a Chinese report read "Executive
  Summary", "1. Technology Overview & Maturity" and so on over Chinese text,
  and nothing said why. HEADING_TRANSLATIONS is that translation as a table.
  A run now takes its headings from it (language.translate_headings), and a
  report saved with the English ones is shown under the table's.
- The writer's contract spells the verdict vocabulary "GO/NO_GO" and reports
  repeat it; the page writes "GO / NO-GO" everywhere else. Shown, the report
  writes it the page's way.
- The writer is also told the gate's mode by its code, and a report can say
  "Assessment mode: decision_support." Shown, the code is a word: "decision
  support", "orientation" (决策支持, 方向性简报 in a Chinese report).
- Each reference entry states its source's type as evidence.py's code
  ("Type: company_disclosure"), and a patent's title as Google Patents served
  it, with " - Google Patents" on the end. Shown, the type is a phrase in the
  report's language, and the site's name is off the title (as result.js does
  for the Sources tab and the brief).

Which language a report is in comes from its applicability paragraph where
it has one. A report made from the command line has none, and was taken for
English whatever it was written in; it is now known by the legend evidence.py
writes as the first line of every reference list.

Nothing here changes what the gate allowed: the sentences are chosen from the
codes in the saved paragraph, and an unknown code keeps the saved wording.
"""

from __future__ import annotations

import re
from typing import Any

from academic_agent.report_applicability import (
    _COPY,
    _OPENING_TITLE,
    _OWNED_BLOCK,
)

# The verdict vocabulary as the writer's contract and the gate's own
# paragraph spell it, in or out of code marks. Upper case only: "a go/no-go
# decision" is English prose, and seven saved reports use it that way. The
# edges are Latin letters and not \b: Chinese text runs straight into the
# word ("未进行GO/NO_GO决策评估"), and to Python a Chinese character is a
# word character.
_GO_NO_GO = re.compile(r"`GO\s*/\s*NO[_-]GO`|(?<![A-Za-z0-9_])GO\s*/\s*NO[_-]GO(?![A-Za-z0-9_])")
GO_NO_GO = "GO / NO-GO"

_SCOPE: dict[str, dict[str, str]] = {
    "English": {
        "label": "Scope of this assessment",
        "orientation": "An orientation brief: no decision context was given, so it gives no "
                       f"{GO_NO_GO} for a particular decision-maker.",
        "decision_context_incomplete": f"The decision context is incomplete, so no {GO_NO_GO} is "
                                       "given for a particular decision-maker.",
        "decision_support": f"Decision support: the context given allows a {GO_NO_GO} for this "
                            "decision-maker; the cited evidence still governs it.",
        "not_allowed": f"No {GO_NO_GO} is given for a particular decision-maker.",
        "not_established": "No success criteria were given, so any thresholds in the report are "
                           "the analyst's proposals.",
        "user_supplied_unapproved": "Success criteria were supplied but not confirmed by the "
                                    "decision-maker.",
        "owner_approved": "The decision-maker approved the success criteria.",
    },
    "Simplified Chinese": {
        "label": "评估范围",
        "orientation": f"方向性简报：没有提供具体决策场景，因此不针对任何决策者给出 {GO_NO_GO}。",
        "decision_context_incomplete": f"决策场景信息不完整，因此不针对具体决策者给出 {GO_NO_GO}。",
        "decision_support": f"决策支持：已提供的决策场景允许针对该决策者给出 {GO_NO_GO}，结论仍以引用证据为准。",
        "not_allowed": f"不针对具体决策者给出 {GO_NO_GO}。",
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
# evidence.SourceType, as a reader is told it. The page's Sources tab names no
# type (it groups sources as academic, patent and market), so this is the one
# table; tests/test_report_display.py holds its keys to the Literal.
SOURCE_TYPES: dict[str, dict[str, str]] = {
    "English": {
        "academic_paper": "Academic paper", "patent": "Patent", "company_disclosure": "Company disclosure",
        "government": "Government source", "standards_body": "Standards body",
        "research_institute": "Research institute", "market_report": "Market report",
        "reputable_news": "News report", "other": "Other",
    },
    "Simplified Chinese": {
        "academic_paper": "学术论文", "patent": "专利", "company_disclosure": "公司披露",
        "government": "政府来源", "standards_body": "标准机构", "research_institute": "研究机构",
        "market_report": "市场报告", "reputable_news": "新闻报道", "other": "其他",
    },
}
_TIERS_ZH = {"high": "高", "medium": "中", "low": "低"}

# Google Patents ends the page title it serves with " - Google Patents", and
# evidence.py writes the title as served, then the publisher after a full
# stop. The same pattern as result.js PATENT_SITE_SUFFIX (the test compares
# the two), so the reference list and the Sources tab name a patent alike:
# the exact suffix only, before a full stop or at the end.
PATENT_SITE_SUFFIX = re.compile(r"\s+-\s+Google Patents(?=\.\s|\.?$)")


def without_site_name(title: str) -> str:
    """A title without the patent site's name; the title itself when nothing else is left."""
    shown = PATENT_SITE_SUFFIX.sub("", title)
    return shown if shown.strip() else title


# The gate's mode codes as a report's prose may repeat them. The writer is
# given the code; measured over the 1,820 reports saved on the maintainer's
# machine (2026-11-21), two lines outside the code's own paragraph use one:
# "**Assessment mode: decision_support.**" and "not a decision_support
# verdict". The snake-case codes are not English words and are replaced
# wherever they stand; "orientation" is a word, so only in code marks. Not
# bare in a Chinese report either: there all 15 uses are the model's own
# gloss after a Chinese term ("定位性（orientation）简报", "导向模式
# （orientation mode）"), which the Chinese word would only repeat. The edges
# are Latin letters, digits and "_", as for GO/NO_GO.
_MODE_WORDS: dict[str, dict[str, str]] = {
    "English": {"decision_support": "decision support",
                "decision_context_incomplete": "decision context incomplete",
                "orientation": "orientation"},
    "Simplified Chinese": {"decision_support": "决策支持",
                           "decision_context_incomplete": "决策背景不完整",
                           "orientation": "方向性简报"},
}
_MODE_CODE = re.compile(
    r"`(decision_support|decision_context_incomplete|orientation)`"
    r"|(?<![A-Za-z0-9_])(decision_support|decision_context_incomplete)(?![A-Za-z0-9_])"
)
# A Chinese character or full-width mark; a space between one and the word
# that replaces a code was there to set the code off, and goes with it.
_CJK = re.compile(r"[　-〿㐀-鿿＀-￯]")


def _mode_words(text: str, language: str | None) -> str:
    chinese = language == "Simplified Chinese"
    words = _MODE_WORDS["Simplified Chinese" if chinese else "English"]
    if not chinese:
        return _MODE_CODE.sub(lambda m: words[m.group(1) or m.group(2)], text)
    out, last = [], 0
    for match in _MODE_CODE.finditer(text):
        start, end = match.start(), match.end()
        if start - 1 >= last and text[start - 1] == " " and start >= 2 and _CJK.match(text[start - 2]):
            start -= 1
        out.append(text[last:start] + words[match.group(1) or match.group(2)])
        last = end
        if text[end:end + 1] == " " and _CJK.match(text[end + 1:end + 2] or "x"):
            last = end + 1
    out.append(text[last:])
    return "".join(out)

_REFERENCES = "\n## References\n"
# evidence._REF_LEGEND, the first line under the heading, in the report's
# language. A copy: evidence.py imports CrewAI, and this module is read for
# every report a page shows. tests/test_report_display.py holds it to the
# original.
_LEGENDS: dict[str, str] = {
    "Simplified Chinese":  "*文献编码说明：**A** = 学术论文 · **P** = 专利 · **M** = 市场/行业来源*",
    "Traditional Chinese": "*文獻編碼說明：**A** = 學術論文 · **P** = 專利 · **M** = 市場/產業來源*",
    "Japanese":            "*引用コード：**A** = 学術論文 · **P** = 特許 · **M** = 市場/業界情報*",
    "Korean":              "*참고문헌 코드：**A** = 학술 논문 · **P** = 특허 · **M** = 시장/업계 자료*",
}
_NOTES = "\n## Reviewer Notes\n"
_NOTES_ZH = "\n## 自动校对记录\n"       # result.js NOTES_HEADING finds the fold by either

# evidence._REQUIRED_REPORT_HEADINGS, in the order the writer is given them.
# A copy, for the reason _LEGENDS is one; tests/test_report_headings.py holds
# it to the original.
REPORT_HEADINGS: tuple[str, ...] = (
    "# Academic Commercialization Assessment:",
    "## Executive Summary",
    "## 1. Technology Overview & Maturity",
    "## 2. Patent Landscape & White Spaces",
    "## 3. Target Industries & Use Cases",
    "## 4. Competitive Landscape",
    "## 5. Commercialization Opportunities & Recommendations",
    "## Evidence Limitations",
    "## References",
)
# The nine in each language a report can be asked for: the eleven the topic's
# language is detected among (language.LANGUAGE_REGISTRY) and Hindi, which the
# page's menu offers. The title is the product's name in that language.
#
# Simplified Chinese is the wording the model itself chose most often in the
# 57 Chinese reports saved on the maintainer's machine (2026-11-19): 执行摘要,
# 竞争格局 and 证据局限性 in all 57, 技术概述与成熟度 in 53, 目标行业与应用场景
# in 55, 商业化机遇与建议 in 39 (the other 18 wrote 机会), 专利布局与空白领域
# in 25 (24 wrote 格局). consistency.py, decision_verdict.py and the page's
# brief read these words, so a different choice here must be made there too.
# Japanese and Korean follow the three saved reports in those languages. The
# others were written for this table and no native reader has reviewed them;
# before it, each run's own model translation was reviewed by nobody either.
HEADING_TRANSLATIONS: dict[str, tuple[str, ...]] = {
    "Simplified Chinese": (
        "# 学术成果商业化评估：", "## 执行摘要", "## 1. 技术概述与成熟度",
        "## 2. 专利布局与空白领域", "## 3. 目标行业与应用场景", "## 4. 竞争格局",
        "## 5. 商业化机遇与建议", "## 证据局限性", "## 参考文献",
    ),
    "Traditional Chinese": (
        "# 學術成果商業化評估：", "## 執行摘要", "## 1. 技術概述與成熟度",
        "## 2. 專利布局與空白領域", "## 3. 目標產業與應用場景", "## 4. 競爭格局",
        "## 5. 商業化機會與建議", "## 證據侷限性", "## 參考文獻",
    ),
    "Japanese": (
        "# 学術成果の商業化評価：", "## エグゼクティブサマリー", "## 1. 技術概要と成熟度",
        "## 2. 特許状況と空白領域", "## 3. 対象産業とユースケース", "## 4. 競合状況",
        "## 5. 商業化の機会と推奨事項", "## エビデンスの限界", "## 参考文献",
    ),
    "Korean": (
        "# 학술 성과 상업화 평가:", "## 요약", "## 1. 기술 개요 및 성숙도",
        "## 2. 특허 환경 및 공백 영역", "## 3. 대상 산업 및 사용 사례", "## 4. 경쟁 환경",
        "## 5. 상업화 기회 및 권장 사항", "## 증거의 한계", "## 참고문헌",
    ),
    "German": (
        "# Bewertung der Kommerzialisierung akademischer Forschung:", "## Zusammenfassung",
        "## 1. Technologieüberblick und Reifegrad", "## 2. Patentlandschaft und Freiräume",
        "## 3. Zielbranchen und Anwendungsfälle", "## 4. Wettbewerbsumfeld",
        "## 5. Kommerzialisierungschancen und Empfehlungen", "## Grenzen der Evidenz",
        "## Quellenverzeichnis",
    ),
    "French": (
        "# Évaluation de la commercialisation de la recherche académique :", "## Résumé exécutif",
        "## 1. Aperçu de la technologie et maturité", "## 2. Paysage des brevets et espaces libres",
        "## 3. Secteurs cibles et cas d'usage", "## 4. Paysage concurrentiel",
        "## 5. Opportunités de commercialisation et recommandations",
        "## Limites des éléments probants", "## Références",
    ),
    "Spanish": (
        "# Evaluación de la comercialización de la investigación académica:", "## Resumen ejecutivo",
        "## 1. Panorama tecnológico y madurez", "## 2. Panorama de patentes y espacios en blanco",
        "## 3. Sectores objetivo y casos de uso", "## 4. Panorama competitivo",
        "## 5. Oportunidades de comercialización y recomendaciones",
        "## Limitaciones de la evidencia", "## Referencias",
    ),
    "Italian": (
        "# Valutazione della commercializzazione della ricerca accademica:", "## Sintesi esecutiva",
        "## 1. Panoramica tecnologica e maturità", "## 2. Panorama brevettuale e spazi liberi",
        "## 3. Settori target e casi d'uso", "## 4. Panorama competitivo",
        "## 5. Opportunità di commercializzazione e raccomandazioni",
        "## Limiti delle evidenze", "## Riferimenti",
    ),
    "Portuguese": (
        "# Avaliação da comercialização da pesquisa acadêmica:", "## Resumo executivo",
        "## 1. Visão geral da tecnologia e maturidade", "## 2. Panorama de patentes e espaços em branco",
        "## 3. Setores-alvo e casos de uso", "## 4. Panorama competitivo",
        "## 5. Oportunidades de comercialização e recomendações",
        "## Limitações das evidências", "## Referências",
    ),
    "Russian": (
        "# Оценка коммерциализации научных разработок:", "## Краткое резюме",
        "## 1. Обзор технологии и уровень зрелости", "## 2. Патентный ландшафт и свободные ниши",
        "## 3. Целевые отрасли и сценарии применения", "## 4. Конкурентная среда",
        "## 5. Возможности коммерциализации и рекомендации",
        "## Ограничения доказательной базы", "## Список источников",
    ),
    "Arabic": (
        "# تقييم التسويق التجاري للبحث الأكاديمي:", "## الملخص التنفيذي",
        "## 1. نظرة عامة على التقنية ومستوى النضج", "## 2. مشهد براءات الاختراع والمساحات غير المغطاة",
        "## 3. القطاعات المستهدفة وحالات الاستخدام", "## 4. المشهد التنافسي",
        "## 5. فرص التسويق التجاري والتوصيات", "## حدود الأدلة", "## المراجع",
    ),
    "Hindi": (
        "# शैक्षणिक शोध के व्यावसायीकरण का आकलन:", "## कार्यकारी सारांश",
        "## 1. प्रौद्योगिकी का अवलोकन और परिपक्वता", "## 2. पेटेंट परिदृश्य और रिक्त क्षेत्र",
        "## 3. लक्षित उद्योग और उपयोग के मामले", "## 4. प्रतिस्पर्धी परिदृश्य",
        "## 5. व्यावसायीकरण के अवसर और सिफ़ारिशें", "## साक्ष्य की सीमाएँ", "## संदर्भ",
    ),
}


def fixed_headings(language: str | None) -> tuple[str, ...] | None:
    """The nine required headings in `language`, or None where no table has it."""
    return HEADING_TRANSLATIONS.get(language or "")


def text_for_display(text: str, language: str | None = None) -> str:
    """Report prose with the verdict vocabulary written the page's way, and
    the gate's mode codes as words of the report's `language` (English
    otherwise)."""
    return _mode_words(_GO_NO_GO.sub(GO_NO_GO, text), language)


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


def _legend_language(report: str) -> str | None:
    """The language named by the line under the reference heading, if it is a legend."""
    _, heading, references = report.partition(_REFERENCES)
    if not heading:
        return None
    first = references.lstrip("\n").split("\n", 1)[0].strip()
    for language, legend in _LEGENDS.items():
        if first == legend:
            return language
    return None


def _report_language(report: str) -> str:
    block = _delivered_block(report)
    if block is not None:
        # Delivered by the application: its paragraph decides, as before.
        return _block_language(block.group()) or "English"
    return _legend_language(report) or "English"




def _heading_language(report: str, language: str | None = None) -> str:
    """The language whose headings the report should be shown under.

    What the report itself says comes first, and its paragraph still decides
    where there is one (_report_language). But the paragraph has copy in six
    languages and the legend in four: a delivered Korean report has an
    English paragraph over a Korean legend, and a Portuguese one names its
    language nowhere. So an English paragraph leaves room only for a language
    it has no copy in, named by the legend or, failing that, by `language`,
    the run's recorded output language. A sample and a file have no record.
    """
    block = _delivered_block(report)
    legend = _legend_language(report)
    if block is None:
        if legend is not None:
            return legend
        return str(language) if language in HEADING_TRANSLATIONS else "English"
    own = _block_language(block.group()) or "English"
    if own != "English":
        return own
    for named in (legend, language):
        if named in HEADING_TRANSLATIONS and named not in _COPY:
            return str(named)
    return "English"


def _title(line: str, language: str) -> str:
    """The opening title under the table's name for the product; any other line as it is."""
    fixed = HEADING_TRANSLATIONS.get(language)
    english = REPORT_HEADINGS[0]
    if fixed is None or not line.startswith(english):
        return line
    topic = line[len(english):].lstrip(" \t")
    # A Latin colon is followed by a space, a full-width one is not.
    gap = " " if topic.strip() and fixed[0].endswith(":") else ""
    return fixed[0] + gap + topic


def _sections(body: str, language: str) -> str:
    """The seven section headings between the title and the reference list.

    Only a line that is exactly one of them changes. A report whose headings
    were translated has none, and a heading the writer made up is not ours.
    """
    fixed = HEADING_TRANSLATIONS.get(language)
    if fixed is None:
        return body
    known = dict(zip(REPORT_HEADINGS[1:-1], fixed[1:-1], strict=True))
    lines = body.split("\n")
    for index, line in enumerate(lines):
        bare = line.rstrip()
        if bare in known:
            lines[index] = known[bare] + line[len(bare):]
    return "\n".join(lines)


def _notes_heading(report: str, language: str) -> str:
    """The last such heading is the pipeline's (evidence.py reads it with rpartition)."""
    if language != "Simplified Chinese":
        return report
    body, marker, notes = report.rpartition(_NOTES)
    return body + _NOTES_ZH + notes if marker else report


def _references(report: str, language: str) -> str:
    marker = _REFERENCES
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
        head = without_site_name(re.sub(r"\.{2,}", ".", entry["head"]).rstrip(". "))
        why = entry["why"].rstrip(". ")
        published = entry["published"]
        # An unknown code (a type evidence.py did not have when this was
        # written) is shown as saved rather than guessed at.
        kind = SOURCE_TYPES.get(language, SOURCE_TYPES["English"]).get(entry["type"], entry["type"])
        if language == "Simplified Chinese":
            lines.append(
                f"[{entry['id']}] {head}. 发布：{'未注明' if published == 'n.d.' else published} · "
                f"访问：{entry['accessed']} · 类型：{kind} · "
                f"可信度：{_TIERS_ZH[entry['credibility']]} · 依据：{why}. {entry['url']}"
            )
        else:
            lines.append(
                f"[{entry['id']}] {head}. Published: {published.rstrip('.')}. Accessed: {entry['accessed']}. "
                f"Type: {kind}. Credibility: {entry['credibility']}. Rationale: {why}. {entry['url']}"
            )
    refs = "\n".join(lines)
    if language == "Simplified Chinese":
        refs = refs.replace(marker, "\n## 参考文献\n", 1)
    return body + refs


def _after_the_scope(rest: str, language: str, heading_language: str) -> str:
    """Everything after the scope paragraph (or the title), as shown.

    The verdict vocabulary and the mode codes are respelt in the report's
    prose and in the proofreading record, which quotes that prose. The
    reference list between them is not: a source's title is the source's,
    apart from the patent site's name on it. Its heading and labels are
    translated for a Chinese report, its source types are words in English
    or Chinese, and otherwise the list is shown as evidence.py wrote it.
    """
    at = rest.find(_REFERENCES)
    body, tail = (rest, "") if at == -1 else (rest[:at], rest[at:])
    notes_at = tail.rfind(_NOTES)
    refs, notes = (tail, "") if notes_at == -1 else (tail[:notes_at], tail[notes_at:])
    shown = (text_for_display(_sections(body, heading_language), language) + refs
             + text_for_display(notes, language))
    return _notes_heading(_references(shown, language), language)


def display_parts(report: str, language: str | None = None) -> tuple[str, str]:
    """The displayed report in two parts: through its scope paragraph, and the rest.

    The PDF puts the decision-conclusion card between them, where the page
    has it: under the sentence saying a conclusion is permitted, above the
    report. Joined, the two are report_for_display(report), byte for byte. A
    report with no delivered scope paragraph is cut after its opening title,
    or has an empty first part.

    Each part is rewritten by itself, so the cut is where it is in the
    displayed text whatever a rewrite does to the length of a line before it.

    `language` is the run's recorded output language (see _heading_language).
    """
    own = _report_language(report)
    heading_language = _heading_language(report, language)
    block = _delivered_block(report)
    if block is None:
        title = _OPENING_TITLE.match(report)
        cut = title.end() if title is not None else 0
        head, paragraph, rest = report[:cut], "", report[cut:]
    else:
        paragraph = _scope_paragraph(block.group(), own)
        if paragraph is None:
            # The saved words, as report_applicability.applicability_for_display
            # gives them: the marker line dropped, each line without its "> ".
            # Its codes stay codes ("Mode `orientation`", "`not_established`"):
            # only the verdict vocabulary is respelt, as before the mode words.
            lines = block.group().splitlines()[1:]
            paragraph = _GO_NO_GO.sub(
                GO_NO_GO, "\n".join(re.sub(r"^>[ \t]?", "", line) for line in lines if line.strip())
            )
        head, rest = report[:block.start()], report[block.end():]
    opening = _OPENING_TITLE.match(head)
    if opening is not None:
        line = opening.group()
        bare = line.rstrip("\r\n")
        head = head[:opening.start()] + text_for_display(_title(bare, heading_language), own) + line[len(bare):] \
            + head[opening.end():]
    return head + paragraph, _after_the_scope(rest, own, heading_language)


def report_for_display(report: str, language: str | None = None) -> str:
    """The report as the page and the PDF show it. The saved bytes stay as they are."""
    head, rest = display_parts(report, language)
    return head + rest


def _plain_heading(heading: str) -> str:
    """A heading as decision_verdict names a section: without its "#" marks."""
    return heading.lstrip("#").strip()


def conclusion_for_display(conclusion: dict[str, Any], report: str,
                           language: str | None = None) -> dict[str, Any]:
    """decision_verdict.find_verdict's answer, in the words the displayed report uses.

    The verdict is read from the saved report, and the page then looks for
    the quoted sentence, or failing that its section's heading, in the report
    it drew. Both are the displayed text, so a section named "Executive
    Summary" would not be found under "执行摘要", nor a sentence saying
    "GO/NO_GO" where the page shows "GO / NO-GO". The same rewrites are made
    here; nothing about the verdict changes.
    """
    heading_language = _heading_language(report, language)
    # The language display_parts respells the prose in, so that a quoted
    # sentence is found in the report the page drew.
    own = _report_language(report)
    fixed = HEADING_TRANSLATIONS.get(heading_language)
    names = {} if fixed is None else {
        _plain_heading(english): _plain_heading(shown)
        for english, shown in zip(REPORT_HEADINGS[1:-1], fixed[1:-1], strict=True)
    }

    def said(item: dict[str, Any]) -> dict[str, Any]:
        out = dict(item)
        for key in ("statement", "needle"):
            if isinstance(out.get(key), str):
                out[key] = text_for_display(out[key], own)
        if isinstance(out.get("follows"), list):
            out["follows"] = [text_for_display(s, own) if isinstance(s, str) else s for s in out["follows"]]
        section = out.get("section")
        if isinstance(section, str):
            title = _plain_heading(_title(f"# {section}", heading_language))
            out["section"] = names.get(section, text_for_display(title, own))
        return out

    shown = said(conclusion)
    if isinstance(conclusion.get("statements"), list):
        shown["statements"] = [said(s) if isinstance(s, dict) else s for s in conclusion["statements"]]
    return shown
