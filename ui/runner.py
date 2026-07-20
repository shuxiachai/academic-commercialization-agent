"""runner — extract_paper_from_pdf / run_analysis_from_paper / run_analysis."""

import html
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import gradio as gr

from ui.i18n import _ui, _scorecard_strings
from ui.html_scorecard import _render_score_html
from ui.html_sources import (
    _render_source_preview_html,
    _render_source_warning_html,
    _build_sources_index,
    _src_detail_panel_html,
)
from ui.html_progress import _render_progress_html, _STAGE_INITIAL, SPINNER
from ui.html_misc import _render_reviewer_notes_html, _paper_divider_html
from ui.run_reader import _read_output_language, _read_weight_profile
from ui.pdf_export import _generate_pdf
from academic_agent.run_output import DEFAULT_OUTPUT_ROOT, create_run_id
from academic_agent.pdf_extractor import extract_paper_contribution


def _read_failure_reason(run_dir: Path) -> str:
    """Return a human-readable failure reason for a run that did not complete.

    Checks, in order: error.log (written on timeout or by the worker on crash),
    the last 800 chars of process.log (subprocess stderr).
    Returns a generic message when neither file has content.
    """
    try:
        msg = (run_dir / "error.log").read_text(encoding="utf-8", errors="replace").strip()
        if msg:
            return msg[:800]
    except OSError:
        pass
    try:
        proc = (run_dir / "process.log").read_text(encoding="utf-8", errors="replace").strip()
        if proc:
            return "Worker stderr:\n" + proc[-800:]
    except OSError:
        pass
    return "The worker process exited without completing. Check API keys and network, then retry."


def _is_cjk_text(text: str) -> bool:
    """Return True if >25% of characters are CJK (simplified/traditional Chinese)."""
    if not text:
        return False
    cjk = sum(1 for c in text if "一" <= c <= "鿿")
    return cjk / len(text) > 0.25


def extract_paper_from_pdf(pdf_file, ui_lang: str = "English") -> tuple:
    """Extract PaperContribution from uploaded PDF.
    Returns 13 values: title, contribution, domain, metrics_str, topic, doi_url,
    paper_json, card_visible, status_msg, submit_btn_update,
    clear_paper_btn_update, paper_run_btn_update, paper_divider_html_update.
    """
    _PDF_MAX_BYTES = 50 * 1024 * 1024  # 50 MB
    _no_change = gr.update()
    _fail_trail = (_no_change, _no_change, _no_change)
    if pdf_file is None:
        return ("", "", "", "", "", "", "", gr.update(visible=False),
                '<p style="color:#f59e0b;font-size:13px;margin:6px 0">⚠ Please upload a PDF file first.</p>',
                _no_change, *_fail_trail)

    try:
        _pdf_size = Path(pdf_file).stat().st_size
    except Exception:
        _pdf_size = 0
    if _pdf_size > _PDF_MAX_BYTES:
        _mb = _pdf_size / (1024 * 1024)
        return ("", "", "", "", "", "", "", gr.update(visible=False),
                f'<p style="color:#f87171;font-size:13px;margin:6px 0">✗ File too large ({_mb:.1f} MB). Maximum allowed size is 50 MB.</p>',
                _no_change, *_fail_trail)

    try:
        pc = extract_paper_contribution(pdf_file)
    except Exception as exc:
        return ("", "", "", "", "", "", "", gr.update(visible=False),
                f'<p style="color:#f87171;font-size:13px;margin:6px 0">✗ Extraction failed: {html.escape(str(exc))}</p>',
                _no_change, *_fail_trail)

    metrics_str = "\n".join(pc.key_metrics)
    doi_url = pc.url or (f"https://doi.org/{pc.doi}" if pc.doi and not pc.doi.startswith("10.0000/uploaded-") else "")
    paper_json = pc.model_dump_json()

    # Determine label language: explicit UI choice wins; "Auto" falls back to content detection
    if ui_lang in ("Auto (detect from topic)", "English"):
        effective_lang = "Chinese" if _is_cjk_text(pc.title + " " + pc.core_contribution) else "English"
    else:
        effective_lang = ui_lang
    t = _ui(effective_lang)

    return (
        gr.update(value=pc.title,                    label=t["paper_title_label"]),
        gr.update(value=pc.core_contribution,        label=t["paper_contribution_label"]),
        gr.update(value=pc.application_domain,       label=t["paper_domain_label"]),
        gr.update(value=metrics_str,                 label=t["paper_metrics_label"]),
        gr.update(value=pc.commercialization_topic,  label=t["paper_topic_label"]),
        gr.update(value=doi_url,                     label=t["paper_doi_label"]),
        paper_json,
        gr.update(visible=True),
        "",                                          # clear status bar
        gr.update(visible=False),                    # hide submit_btn
        gr.update(value=t["clear_paper_btn"]),       # clear_paper_btn text
        gr.update(value=t["paper_run_btn"]),         # paper_run_btn text
        gr.update(value=_paper_divider_html(t["paper_divider"])),
    )


def run_analysis_from_paper(
    paper_title: str,
    paper_contribution: str,
    paper_domain: str,
    paper_metrics_str: str,
    paper_topic: str,
    paper_doi_url: str,
    paper_json_state: str,
    language: str,
    weight_profile: str,
):
    """Run the full pipeline seeded with the uploaded paper as source A1."""
    if not paper_topic.strip():
        yield "", "", "Please enter a commercialization topic.", None, None, gr.update(), gr.update(), ""
        return

    # Reconstruct PaperContribution from UI fields (user may have edited them)
    pc_data: dict = {}
    if paper_json_state:
        try:
            pc_data = json.loads(paper_json_state)
        except Exception:
            pass

    metrics = [m.strip() for m in paper_metrics_str.splitlines() if m.strip()]
    pc_data.update({
        "title": paper_title.strip() or pc_data.get("title", "Uploaded Paper"),
        "core_contribution": paper_contribution.strip() or pc_data.get("core_contribution", ""),
        "application_domain": paper_domain.strip() or pc_data.get("application_domain", ""),
        "key_metrics": metrics or pc_data.get("key_metrics", []),
        "commercialization_topic": paper_topic.strip(),
        "delta_from_prior": pc_data.get("delta_from_prior", paper_contribution.strip()),
        "search_keywords": pc_data.get("search_keywords", paper_topic.strip().split()[:5]),
        "abstract_excerpt": pc_data.get("abstract_excerpt", ""),
        "authors": pc_data.get("authors", ""),
    })

    # Handle DOI / URL field
    doi_url = paper_doi_url.strip()
    if doi_url.startswith("http"):
        pc_data["url"] = doi_url
        pc_data["doi"] = None
    elif doi_url:
        pc_data["doi"] = doi_url
        pc_data["url"] = None
    else:
        # Keep whatever the extractor found; add placeholder if nothing
        if not pc_data.get("doi") and not pc_data.get("url"):
            import hashlib
            h = hashlib.md5(pc_data["title"].encode()).hexdigest()[:10]
            pc_data["doi"] = f"10.0000/uploaded-{h}"

    # Write to a session-scoped temp file; cleaned up after the generator exits
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(pc_data, f, ensure_ascii=False)

        yield from run_analysis(paper_topic.strip(), language, weight_profile, tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def run_analysis(
    research_topic: str,
    language: str = "Auto (detect from topic)",
    weight_profile: str = "Auto (detect from topic)",
    paper_json_path: str = "",
):
    """Generator that yields (progress_html, score_html, report_md, md_path, pdf_path, submit_btn, cancel_btn).

    The pipeline runs in a subprocess so that clicking Cancel immediately
    terminates it via proc.terminate() in the try/finally block — even if
    CrewAI is mid-task. GeneratorExit (thrown by Gradio on cancel) triggers
    the finally clause before the generator exits.
    """
    if not research_topic.strip():
        yield "", "", "Please enter a research topic.", None, None, gr.update(), gr.update(), ""
        return

    run_id = create_run_id()
    run_dir = DEFAULT_OUTPUT_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    status_path = run_dir / "status.json"

    cmd = [sys.executable, "-m", "academic_agent.pipeline_worker", run_id, research_topic.strip()]
    if language and language != "Auto (detect from topic)":
        cmd += ["--language", language]
    if weight_profile and weight_profile != "Auto (detect from topic)":
        cmd += ["--weight-profile", weight_profile]
    if paper_json_path and Path(paper_json_path).exists():
        cmd += ["--paper-json", paper_json_path]
    _TIMEOUT_SECS = 1800  # 30-minute hard limit
    stderr_log = open(run_dir / "process.log", "w", encoding="utf-8")
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=stderr_log)
    except Exception:
        stderr_log.close()
        raise

    start = time.time()
    tick = 0
    try:
        while proc.poll() is None:
            elapsed = int(time.time() - start)
            if elapsed > _TIMEOUT_SECS:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                (run_dir / "error.log").write_text(
                    f"Analysis timed out after {_TIMEOUT_SECS // 60} minutes.", encoding="utf-8"
                )
                break
            stage = _STAGE_INITIAL
            output_language = "English"
            source_counts: dict | None = None
            try:
                _status = json.loads(status_path.read_text(encoding="utf-8"))
                stage = _status.get("stage", _STAGE_INITIAL)
                output_language = _status.get("output_language") or "English"
                source_counts = _status.get("source_counts")
            except Exception:
                pass
            spin = SPINNER[tick % len(SPINNER)]
            yield (
                _render_progress_html(stage, elapsed, run_id, spin, output_language, source_counts),
                "",
                "",
                gr.update(visible=False),
                gr.update(visible=False),
                gr.update(interactive=False),
                gr.update(visible=True),
                _render_source_preview_html(run_dir, ui_lang=language),
            )
            time.sleep(0.8)
            tick += 1
    finally:
        # Runs on normal completion AND on GeneratorExit (Gradio cancel).
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        stderr_log.close()

    # Read final status written by the worker.
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        status = {"done": False, "error": None, "output_language": "English"}

    # If the process was cancelled (GeneratorExit path doesn't reach here),
    # or exited unexpectedly, surface whatever diagnostic is available.
    if not status.get("done"):
        _err_msg = status.get("error") or _read_failure_reason(run_dir)
        _out_lang = status.get("output_language") or "English"
        _et = _scorecard_strings(_out_lang)
        _err_html = (
            '<div style="font-family:system-ui;background:#2d1515;border:1px solid #7f1d1d;'
            'border-radius:8px;padding:16px 20px;">'
            '<div style="font-size:14px;font-weight:600;color:#f87171;margin-bottom:8px;">'
            f'{html.escape(_et.get("err_failed", "✗ Analysis Failed"))}</div>'
            '<div style="font-size:13px;color:#9a9a9a;white-space:pre-wrap">'
            f'{html.escape(_err_msg)}</div>'
            '<div style="font-size:12px;color:#777777;margin-top:8px;">'
            f'{html.escape(_et.get("err_run", "Run ID"))}: <code>{html.escape(run_id)}</code></div>'
            '</div>'
        )
        yield _err_html, "", "", gr.update(visible=False), gr.update(visible=False), gr.update(interactive=True), gr.update(visible=False), ""
        return

    output_language = status.get("output_language") or "English"

    if status.get("error"):
        _et = _scorecard_strings(output_language)
        error_html = (
            f'<div style="font-family:system-ui;background:#2d1515;border:1px solid #7f1d1d;'
            f'border-radius:8px;padding:16px 20px;">'
            f'<div style="font-size:14px;font-weight:600;color:#f87171;margin-bottom:8px;">'
            f'{html.escape(_et.get("err_failed", "✗ Analysis Failed"))}</div>'
            f'<div style="font-size:13px;color:#9a9a9a;">{html.escape(status["error"])}</div>'
            f'<div style="font-size:12px;color:#777777;margin-top:8px;">'
            f'{html.escape(_et.get("err_run", "Run ID"))}: <code>{html.escape(run_id)}</code></div>'
            f'</div>'
        )
        yield error_html, "", "", gr.update(visible=False), gr.update(visible=False), gr.update(interactive=True), gr.update(visible=False), ""
        return

    report_path = run_dir / "commercialization_report.md"
    scores_path = run_dir / "commercialization_scores.json"
    report = report_path.read_text(encoding="utf-8") if report_path.exists() else "Report generation failed. Please retry."
    scores_json = scores_path.read_text(encoding="utf-8") if scores_path.exists() else None

    _lang_badge_prefix = _ui(output_language).get("lang_badge_prefix", "Report language: ")
    lang_badge = (
        f'<div style="font-family:system-ui;margin-bottom:10px;">'
        f'<span style="background:#1a1a1a;border:1px solid #2d2d2d;color:#9a9a9a;'
        f'font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;">'
        f'🌐 {html.escape(_lang_badge_prefix)}{html.escape(output_language)}</span></div>'
    ) if output_language != "English" else ""
    wp = _read_weight_profile(run_dir)
    sources_index = _build_sources_index(run_dir)
    score_html = (lang_badge + _render_source_warning_html(run_dir, output_language) + _render_score_html(scores_json, research_topic.strip(), output_language, wp, sources_index=sources_index)) if scores_json else lang_badge
    score_html += _render_reviewer_notes_html(run_dir, output_language)
    score_html += _src_detail_panel_html(sources_index)
    t = _scorecard_strings(output_language)
    md_update = gr.update(value=str(report_path), visible=True, label=t["dl_md"]) if report_path.exists() else gr.update(visible=False)

    # Yield results and re-enable Run button immediately; PDF generation runs concurrently.
    yield "", score_html, report, md_update, gr.update(visible=False), gr.update(interactive=True), gr.update(visible=False), ""

    _pdf_result: list[Path | None] = [None]
    def _bg_pdf() -> None:
        _pdf_result[0] = _generate_pdf(report, run_dir, output_language)
    _pdf_thread = threading.Thread(target=_bg_pdf, daemon=True)
    _pdf_thread.start()
    _pdf_thread.join(timeout=45)

    pdf_path_obj = _pdf_result[0]
    pdf_update = gr.update(value=str(pdf_path_obj), visible=True, label=t["dl_pdf"]) if pdf_path_obj else gr.update(visible=False)
    yield "", score_html, report, md_update, pdf_update, gr.update(interactive=True), gr.update(visible=False), ""
