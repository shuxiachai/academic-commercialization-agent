"""The audit behind docs/results-2026-11-19-report-headings.md counts what it says it counts.

The fixed heading table takes the wording saved reports use most, and the
decision to leave English phrases inside Chinese prose alone rests on how
rarely they occur. Both figures come from this script, so its counting is
held on a small directory of reports whose answers are known.
"""

from __future__ import annotations

from pathlib import Path

from academic_agent.report_applicability import add_applicability_block
from academic_agent.report_display import _LEGENDS, HEADING_TRANSLATIONS, REPORT_HEADINGS
from academic_agent.run_spec import DecisionContext
from scripts.audits import report_heading_audit as audit

_ZH_LEGEND = _LEGENDS["Simplified Chinese"]
_ENTRY = ("[A1] A GO/NO-GO framework. Some Journal. Published: 2021-05-01. Accessed: 2026-10-21. "
          "Type: academic_paper. Credibility: high. Rationale: OpenAlex record. https://doi.org/10.1/x")


def _report(headings, lines, *, legend=_ZH_LEGEND, notes=""):
    parts = [f"{headings[0]}主题", ""]
    for heading, line in zip(headings[1:-1], lines, strict=True):
        parts += [heading, "", line, ""]
    parts += ["## References", "", legend, "", _ENTRY, ""]
    if notes:
        parts += ["## Reviewer Notes", "", notes, ""]
    return "\n".join(parts)


def _save(root: Path, name: str, text: str) -> None:
    directory = root / "batch" / name
    directory.mkdir(parents=True)
    (directory / "commercialization_report.md").write_text(text, encoding="utf-8")


def test_the_audit_counts_languages_headings_spellings_and_english_runs(tmp_path, capsys):
    table = HEADING_TRANSLATIONS["Simplified Chinese"]
    other = list(table)
    other[0], other[6] = "# 学术商业化评估：", "## 5. 商业化机会与建议"
    plain = ["正文一 [A1]。"] * 7
    leaking = [
        "评估模式：orientation（方向性简报），未进行GO/NO_GO评估；actor-specific GO/NO_GO is not assessed。",
        "该成果发表于 Journal of Power Sources and Energy Storage Materials [A1]。",   # a name, five words
        "本节不构成 freedom-to-operate 意见。",
        "结论为 NO_GO。",
        "正文 [A1]。", "正文 [A1]。", "正文 [A1]。",
    ]
    gate = DecisionContext().gate_snapshot()
    # 1. Table wording, delivered by the application, with English from the contract in its prose.
    _save(tmp_path, "a-table", add_applicability_block(
        _report(table, leaking, notes="- Checked the GO/NO_GO sentence."), decision_gate=gate,
        output_language="Simplified Chinese"))
    # 2. The model's other wording, from the command line: known by its legend.
    _save(tmp_path, "b-other", _report(other, plain))
    # 3. Saved under the English headings: what a failed translation leaves.
    _save(tmp_path, "c-english-headings", _report(REPORT_HEADINGS, plain))
    # 4. An English report with the lower-case phrase.
    _save(tmp_path, "d-english", _report(REPORT_HEADINGS, ["A go/no-go decision follows [A1]."] + ["Text [A1]."] * 6,
                                         legend="*Reference codes: **A** = Academic paper*"))
    # 5. Chinese with no paragraph and no legend: known by its characters only.
    _save(tmp_path, "e-characters", "# 报告\n\n## 摘要\n\n" + "这是一段足够长的中文正文，用来按字符判断语言。" * 4 + "\n")

    found = audit.audit(tmp_path)
    assert found["reports"] == 5
    assert found["languages"] == {"Simplified Chinese": 3, "English": 1, "Simplified Chinese (by its characters)": 1}
    assert found["chinese"] == 4
    # Three reports keep none of the eight, one keeps all eight.
    assert found["english_headings_kept"] == {0: 3, 8: 1}
    wording = found["wording"]
    assert sorted(wording["# Academic Commercialization Assessment:"]) == [
        ("# Academic Commercialization Assessment", 1), ("# 学术商业化评估", 1), ("# 学术成果商业化评估", 1)]
    assert wording["## Executive Summary"][0] == ("## 执行摘要", 2)
    assert sorted(wording["## 5. Commercialization Opportunities & Recommendations"]) == [
        ("## 5. Commercialization Opportunities & Recommendations", 1), ("## 5. 商业化机会与建议", 1),
        ("## 5. 商业化机遇与建议", 1)]
    # Spellings, wherever they stand: the paragraph's own is in code marks.
    # The four reports with a reference list each cite one "GO/NO-GO" title.
    assert dict(found["spelling"]) == {"GO/NO_GO": 3, "`GO/NO_GO`": 1, "GO/NO-GO": 4, "go/no-go": 1}
    assert found["places"] == {"applicability paragraph": 1, "prose": 3, "reference list": 4, "proofreading record": 1}
    assert found["lone_no_go"] == {"occurrences": 1, "reports": 1}
    inside = found["chinese_reports_with"]
    assert inside["GO/NO_GO"] == [1, 2] and inside["orientation"] == [1, 1]
    assert inside["actor-specific"] == [1, 1] and inside["not assessed"] == [1, 1]
    assert inside["freedom-to-operate"] == [1, 1]
    assert "decision_support" not in inside
    runs = dict(found["english_runs"]["runs"])
    assert found["english_runs"]["reports"] == 1
    assert runs == {"actor-specific go/no_go is not assessed": 1,
                    "journal of power sources and energy storage materials": 1}

    assert audit.main([str(tmp_path)]) == 0
    printed = capsys.readouterr().out
    assert "reports: 5" in printed and "学术成果商业化评估" in printed
    assert "NO_GO alone in prose: {'occurrences': 1, 'reports': 1}" in printed
    assert audit.main([str(tmp_path / "missing")]) == 2
