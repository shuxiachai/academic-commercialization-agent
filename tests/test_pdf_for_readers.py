"""The PDF a reader is handed: built through GET /api/runs/{id}/report.pdf and read back.

Technology-transfer offices and investors forward the PDF, not the page. The
review of production 166130d (2026-11-20) found a PDF that was the report's
text alone: no score, no page numbers, header or footer, no date, model or
link back; "(anonymous)" as its title; a cache mark as its subject; codes and
" - Google Patents" in its references, none of them clickable; and the run's
ID as its file name. These tests build real PDFs of an English decision-
support sample, the Chinese sample and a stopped run's draft, and read what a
reader would see: the text of every page, the document information, the
link annotations and the download's name.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import unquote

import pypdfium2 as pdfium
import pytest
from fastapi.testclient import TestClient

from academic_agent.checkpoints import CheckpointIdentity, CheckpointStore, hash_text
from academic_agent.report_brief import brief_lines
from academic_agent.report_display import report_for_display
from academic_agent.run_spec import DecisionContext, RunSpec
from academic_agent.run_terminal import TerminalRecord, UsageAccounting, commit_terminal_record
from api import crawlers, runs, samples
from api.main import app
from ui.pdf_export import _UNICODE_FIX, DECISION_CARD_MARK, DISPLAY_MARK, wrap_url

_ROOT = Path(__file__).resolve().parents[1]
_ORIGIN = crawlers.origin_of((_ROOT / "web" / "index.html").read_text(encoding="utf-8"))
_SOURCES = {"academic_sources": [{}] * 8, "patent_sources": [{}] * 8, "market_sources": [{}] * 8}
_EN_RUN = "20261120T021505Z-34d116728d999590c648a94439f101a2"
_ZH_RUN = "20261108T090000Z-a1b2c3d4e5f60718293a4b5c6d7e8f90"
_DRAFT_RUN = "20261118T083403Z-e434f298d40b911342d46653c7c88b74"


@pytest.fixture
def root(tmp_path, monkeypatch):
    runs._registry.clear()
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    yield tmp_path
    runs._registry.clear()


def _status(run_dir: Path, **fields) -> None:
    status = {"stage": "Done", "done": True, "error": None, **fields}
    (run_dir / "status.json").write_text(json.dumps(status, ensure_ascii=False), encoding="utf-8")


def _sample_run(root: Path, run_id: str, slug: str, **status) -> Path:
    run_dir = root / run_id
    run_dir.mkdir()
    (run_dir / "commercialization_report.md").write_text(samples.read_sample(slug), encoding="utf-8")
    (run_dir / "commercialization_scores.json").write_text(json.dumps(samples.read_sample_scores(slug)),
                                                           encoding="utf-8")
    (run_dir / "validated_sources.json").write_text(json.dumps(_SOURCES), encoding="utf-8")
    _status(run_dir, **status)
    return run_dir


def _english(root: Path) -> Path:
    """The decision-support sample, as its run left it: request, gate, report, scorecard."""
    decision = samples._BY_SLUG["perovskite-silicon-tandem"].decision
    context = DecisionContext(asset_description=decision.asset_description,
                              target_application=decision.target_application,
                              decision_owner=decision.decision_owner, decision_type=decision.decision_type)
    run_dir = _sample_run(root, _EN_RUN, "perovskite-silicon-tandem", topic="perovskite-silicon tandem solar cells",
                          output_language="English", decision_gate=context.gate_snapshot(),
                          llm_model="claude-opus-5-5")
    RunSpec(topic="perovskite-silicon tandem solar cells", decision_context=context).save(run_dir)
    return run_dir


def _chinese(root: Path) -> Path:
    return _sample_run(root, _ZH_RUN, "uhvdc-transmission-zh", topic="特高压直流输电",
                       output_language="Simplified Chinese", decision_gate=DecisionContext().gate_snapshot(),
                       llm_model="deepseek-v4-pro")


def _get(run_id: str):
    reply = TestClient(app).get(f"/api/runs/{run_id}/report.pdf")
    assert reply.status_code == 200, reply.text[:300]
    return reply


def _read(pdf: bytes) -> tuple[list[str], dict[str, str]]:
    document = pdfium.PdfDocument(pdf)
    try:
        pages = [document[i].get_textpage().get_text_range() for i in range(len(document))]
        return pages, document.get_metadata_dict()
    finally:
        document.close()


def _flat(text: str) -> str:
    """Text as one line: a PDF breaks lines where the page ran out. The PDF
    writes "cm²" as "cm2" and every dash as "-" (pdf_export._UNICODE_FIX:
    the CJK faces have no glyph for them), so an expected sentence is
    flattened the same way."""
    return re.sub(r"\s+", " ", text.translate(_UNICODE_FIX)).strip()


def _links(pdf: bytes) -> set[str]:
    return {match.decode("latin-1") for match in re.findall(rb"/URI \(([^)]*)\)", pdf)}


def test_the_english_pdf_carries_what_the_page_shows(root):
    _english(root)
    reply = _get(_EN_RUN)
    pages, info = _read(reply.content)
    first, everything = _flat(pages[0]), _flat(" ".join(pages))

    # The score, its grade and the five dimensions, on the first page.
    assert "69.3 / 100 Moderate" in first
    for row in ("Technology readiness 7.3 / 9 TRL 7 (system prototype in operational environment)",
                "Manufacturing readiness 6.5 / 10", "Patent position 2.5 / 5", "Market accessibility 3.5 / 5",
                "Evidence confidence 4 / 5"):
        assert row in first, row
    assert "Sources: 24 in all · 8 academic · 8 patents · 8 market" in first
    assert "Decision context: Given: decision support · Decision owner: Technology transfer office" in first
    # The brief's three lines, in the words the page finds (report_brief.py).
    lines = brief_lines(samples.read_sample_scores("perovskite-silicon-tandem"),
                        report_for_display(samples.read_sample("perovskite-silicon-tandem")))
    for line in ("summary", "risk", "next"):
        whole = lines[f"{line}_whole"] if line != "risk" else None
        assert _flat(whole or lines[line]) in first, line
    # After the decision card and before the report's own first section.
    assert first.index("Decision conclusion") < first.index("At a glance") < first.index("Executive Summary")

    # Every page: the header, the page number, the link back, the date and the model.
    for number, page in enumerate(pages, start=1):
        flat = _flat(page)
        assert "ACA · perovskite-silicon tandem solar cells" in flat, number
        assert f"Page {number} of {len(pages)}" in flat, number
        assert f"{_ORIGIN}/run/{_EN_RUN}" in flat, number
        assert "Generated 2026-11-20 UTC · Model: claude-opus-5-5" in flat, number
    assert f"{_ORIGIN}/run/{_EN_RUN}" in _links(reply.content)

    # The references in words, without the site's name, their addresses clickable.
    assert "Type: Patent." in everything and "Type: Academic paper." in everything
    assert not re.search(r"Type: [a-z]", everything)
    assert " - Google Patents" not in everything
    saved = samples.read_sample("perovskite-silicon-tandem")
    addresses = re.findall(r"^\[[APM]\d+\] .* (https?://\S+)$", saved, re.MULTILINE)
    assert len(addresses) == 24
    assert set(addresses) <= _links(reply.content)

    # The document information a reader's viewer shows.
    assert info["Title"] == "ACA assessment: perovskite-silicon tandem solar cells"
    assert info["Author"] == "Academic Commercialization Assessment"
    assert "perovskite-silicon tandem solar cells" in info["Subject"] and "report-display" not in info["Subject"]
    assert set(info["Keywords"].split()) == {DISPLAY_MARK, DECISION_CARD_MARK}

    # A name that says what the file is.
    assert reply.headers["content-disposition"] == (
        'attachment; filename="ACA-perovskite-silicon-tandem-solar-cells-2026-11-20.pdf"; '
        "filename*=UTF-8''ACA-perovskite-silicon-tandem-solar-cells-2026-11-20.pdf")


def test_the_chinese_pdf_is_in_chinese(root):
    _chinese(root)
    reply = _get(_ZH_RUN)
    pages, info = _read(reply.content)
    first, everything = _flat(pages[0]), _flat(" ".join(pages))
    scores = samples.read_sample_scores("uhvdc-transmission-zh")
    assert f"{scores['overall_score']:.1f} / 100" in first and "评估概要" in first
    assert "技术就绪度" in first and "TRL" in first
    assert "决策场景：未提供：方向性简报" in first.replace(" ", "")
    for number, page in enumerate(pages, start=1):
        flat = _flat(page)
        assert "ACA · 特高压直流输电" in flat, number
        assert f"第 {number} 页，共 {len(pages)} 页" in flat, number
        assert f"{_ORIGIN}/run/{_ZH_RUN}" in flat, number
        assert "生成于 2026-11-08（UTC）" in flat, number
    assert "类型：专利" in everything and "类型：学术论文" in everything
    assert "Type:" not in everything and " - Google Patents" not in everything
    assert info["Title"] == "ACA 评估：特高压直流输电"
    assert info["Author"] == "学术成果商业化评估"
    disposition = reply.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="ACA-report-2026-11-08.pdf"; filename*=UTF-8\'\'')
    assert unquote(disposition.split("UTF-8''", 1)[1]) == "ACA-特高压直流输电-2026-11-08.pdf"


def _draft(root: Path) -> Path:
    """A run that failed in scoring with its writer and reviewer done, as on 2026-11-18."""
    run_dir = root / _DRAFT_RUN
    run_dir.mkdir()
    _status(run_dir, stage="Error", error="RuntimeError: provider unreachable", topic="solid-state batteries",
            output_language="English", decision_gate=DecisionContext().gate_snapshot(), llm_model="qwen3.8")
    written = ("# Academic Commercialization Assessment: solid-state batteries\n\n## Executive Summary\n\n"
               "The writer's sentence [P1].\n\n## References\n\n"
               "[P1] US1 - A cell - Google Patents. Google Patents. Published: 2024-01-02. Accessed: 2026-11-18. "
               "Type: patent. Credibility: medium. Rationale: A record. https://patents.google.com/patent/US1/en\n")
    reviewed = written.replace("The writer's sentence", "The reviewed sentence") + (
        "\n## Reviewer Notes\n\n- Applied: Said it plainly.\n")
    for node, text in (("writer", written), ("reviewer", reviewed)):
        CheckpointStore(run_dir).commit(
            CheckpointIdentity(node_id=node, input_sha256=hash_text("i"), evidence_sha256=hash_text("e"),
                               config_sha256=hash_text("c"), upstream_sha256={}, pipeline_revision="test",
                               as_of_date=date(2026, 11, 18), model=None),
            text, output_format="markdown",
        )
    started = datetime(2026, 11, 18, 8, 34, 3, tzinfo=UTC)
    ended = started + timedelta(seconds=1531)
    commit_terminal_record(run_dir, TerminalRecord(
        state="failed", reason_code="worker_exception", termination_method="worker_exit",
        started_at=started, ended_at=ended, elapsed_seconds=1531, last_stage="Error", timeout_seconds=1800,
        usage={"total_tokens": 141_193, "cost_usd": None, "cost_complete": False, "agents": []},
        usage_accounting=UsageAccounting(state="lower_bound", snapshot_at=ended, through_stage="Error",
                                         run_complete=False, in_flight_request_may_have_spent=True),
        checkpointing={"state": "partial", "committed_nodes": ["writer", "reviewer"], "errors": []},
    ))
    return run_dir


def test_a_stopped_run_s_draft_is_exported_as_the_page_shows_it(root):
    run_dir = _draft(root)
    reply = _get(_DRAFT_RUN)
    pages, info = _read(reply.content)
    first = _flat(pages[0])
    # The reviewed draft (PR #438), its notice first, then why there is no score.
    assert first.index("This is a reviewed draft with no score.") < first.index(
        "This run stopped before scoring, so it has no score.") < first.index("The reviewed sentence")
    assert "The writer's sentence" not in first and "/ 100" not in first and "At a glance" not in first
    assert "Resuming" not in first
    assert " - Google Patents" not in first and "Type: Patent." in first
    assert "Page 1 of" in first and f"{_ORIGIN}/run/{_DRAFT_RUN}" in first
    assert info["Title"] == "ACA assessment (draft): solid-state batteries"
    assert reply.headers["content-disposition"].startswith(
        'attachment; filename="ACA-solid-state-batteries-2026-11-18-draft.pdf"')
    # Cached under its own name; the report's name stays free.
    assert (run_dir / "commercialization_draft.pdf").exists()
    assert not (run_dir / "commercialization_report.pdf").exists()


def test_a_run_with_neither_report_nor_draft_is_still_409(root):
    run_dir = root / _DRAFT_RUN
    run_dir.mkdir()
    _status(run_dir, stage="Error", error="RuntimeError: x", topic="t")
    assert TestClient(app).get(f"/api/runs/{_DRAFT_RUN}/report.pdf").status_code == 409


def test_without_a_public_address_the_footer_names_the_run(root):
    """A copy whose pages name no address links nowhere rather than to a guess."""
    _chinese(root)
    with patch.object(crawlers, "origin_of", lambda _page: None):
        reply = _get(_ZH_RUN)
    pages, _info = _read(reply.content)
    assert f"运行 {_ZH_RUN}" in _flat(pages[0])
    assert not any("/run/" in link for link in _links(reply.content))


def test_a_cached_export_from_before_the_summary_is_drawn_again(root):
    run_dir = _chinese(root)
    stale = b"%PDF-1.4 /Subject (report-display:v2) old pages\n%%EOF"
    (run_dir / "commercialization_report.pdf").write_bytes(stale)
    reply = _get(_ZH_RUN)
    assert reply.content != stale and b"report-display:v3" in reply.content
    again = _get(_ZH_RUN)
    assert again.content == reply.content, "once drawn, the export is served as cached"


@pytest.mark.parametrize("url", [
    "https://patents.google.com/patent/US20250248296A1/en?oq=18%2F833670",
    "https://www.example.com/energy/articles/perovskite-solar-cell-market-reach-181100005-and-a-long-tail.html",
    "https://doi.org/10.1038/s41586-025-09312-x",
    # Full stops inside pieces that fit: never a place to break.
    "https://example.test/alpha.beta.gamma.delta/epsilon.zeta.eta.theta/iota",
])
def test_an_address_is_broken_only_after_a_slash_a_hyphen_or_a_question_mark(url):
    lines = wrap_url(url, "Helvetica", 10, 160)
    assert "".join(lines) == url
    assert len(lines) > 1
    for line in lines[:-1]:
        assert line[-1] in "/-?", lines


def test_a_reference_s_address_starts_its_own_line_and_is_a_link():
    from ui.pdf_export import _build_styles, markdown_to_story

    url = "https://patents.google.com/patent/US20250248296A1/en?oq=perovskite-silicon-tandem-solar-cells-made-at-scale"
    story = markdown_to_story(f"[P1] A title. A publisher. Published: 2024-01-02. {url}\n\n"
                              "Read https://example.test/a, then go on.\n", _build_styles("Helvetica"))
    entry, prose = (paragraph.text for paragraph in story)
    before, link = entry.split("<br/>", 1)
    assert before == "[P1] A title. A publisher. Published: 2024-01-02."
    assert link.startswith(f'<a href="{url}"') and link.endswith("</a>")
    shown = re.sub(r"<[^>]+>", "\n", link).split()
    assert "".join(shown) == url and len(shown) > 1 and all(line[-1] in "/-?" for line in shown[:-1])
    # Inside a sentence an address is a link where it stands, its comma outside it.
    assert prose == 'Read <a href="https://example.test/a" color="#1d4ed8">https://example.test/a</a>, then go on.'


def test_chinese_lines_run_to_the_margin():
    """Chinese is set without spaces; broken only at spaces, a line stopped
    at the last one and left the rest of the width empty."""
    from ui.pdf_export import _build_styles, _resolve_font, markdown_to_story

    text = ("特高压直流（UHVDC）输电技术在中国已达到系统级部署的成熟阶段。截至2018年的综述显示，中国已建成11项直流特高压工程，"
            "另有3项在建，并正在发展±1100 kV技术 [A8]。技术前沿正在向三个方向演进：一是混合换相换流器（Hybrid Commutated "
            "Converter），其在120 kV/360 MW原型上完成实验验证 [A4]；二是单端故障诊断方法。")
    from reportlab.pdfbase.pdfmetrics import stringWidth

    font = _resolve_font("Simplified Chinese")
    width = 470

    def widths(cjk_wrap: bool) -> list[float]:
        paragraph = markdown_to_story(text, _build_styles(font, cjk_wrap=cjk_wrap))[0]
        paragraph.wrap(width, 1000)
        shown = []
        for line in paragraph.blPara.lines[:-1]:
            words = line.words if hasattr(line, "words") else None
            text_of = "".join(getattr(f, "text", "") for f in words) if words is not None else " ".join(line[1])
            shown.append(stringWidth(text_of, font, 10))
        return shown

    # The premise: broken at spaces, one line stops well short of the margin.
    assert min(widths(False)) < 0.8 * width
    assert len(widths(True)) >= 2 and min(widths(True)) > 0.9 * width


def test_a_chinese_pdf_is_set_with_chinese_line_breaking(root):
    from ui import pdf_export

    _chinese(root)
    seen = []
    real = pdf_export._build_styles

    def spy(font_name, cjk_wrap=False):
        seen.append(cjk_wrap)
        return real(font_name, cjk_wrap)

    with patch.object(pdf_export, "_build_styles", spy):
        _get(_ZH_RUN)
    assert seen == [True]


def test_a_long_topic_is_cut_to_the_header_line():
    from reportlab.pdfbase.pdfmetrics import stringWidth

    from ui.pdf_export import _fit

    header = _fit("ACA · " + "perovskite silicon tandem " * 20, "Helvetica", 8, 300)
    assert header.endswith("…") and header.startswith("ACA · perovskite")
    assert stringWidth(header, "Helvetica", 8) <= 300
    assert _fit("ACA · short", "Helvetica", 8, 300) == "ACA · short"


def test_the_pdf_carries_a_long_brief_line_whole(root):
    """The page cuts a long line at 240 characters and offers the rest on a
    press; a PDF has no button, so it carries the sentence whole."""
    run_dir = _english(root)
    long = ("Perovskite-silicon tandem cells have moved from laboratory records to pilot lines on three "
            "continents, with certified efficiencies above thirty-three percent, stability tests in the thousands "
            "of hours, and two manufacturers reporting first commercial deliveries to utility customers [A1].")
    report = (run_dir / "commercialization_report.md").read_text(encoding="utf-8")
    (run_dir / "commercialization_report.md").write_text(
        report.replace("## Executive Summary\n\n", f"## Executive Summary\n\n{long}\n\n", 1), encoding="utf-8")
    pages, _info = _read(_get(_EN_RUN).content)
    assert len(long) > 240
    assert f"The report's own summary: “{_flat(long.removesuffix(' [A1].'))}.”" in _flat(pages[0])


def test_a_piece_with_no_such_place_is_cut_only_where_nothing_else_fits():
    url = "https://example.test/" + "x" * 120
    lines = wrap_url(url, "Helvetica", 10, 160)
    assert "".join(lines) == url and lines[0] == "https://example.test/"
