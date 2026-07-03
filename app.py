import html
import json
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

import gradio as gr

from academic_agent.crew import AcademicAgent
from academic_agent.run_output import (
    DEFAULT_OUTPUT_ROOT,
    create_run_id,
    save_error,
    save_report,
    save_scores,
    save_source_collection,
)
from academic_agent.source_pipeline import collect_source_collection


TASK_STAGE_LABELS = [
    "Agent 1 — Academic Literature Analysis",
    "Agent 2 — Patent Landscape Analysis",
    "Agent 3 — Market Intelligence Analysis",
    "Agent 4 — Report Writing",
    "Agent 5 — Quality Review & Citation Check",
    "Agent 6 — Commercialization Scoring",
]
_STAGE_INITIAL = "Source Collection & Validation"
SPINNER = ["|", "/", "-", "\\"]

# ---------------------------------------------------------------------------
# Score card helpers
# ---------------------------------------------------------------------------

def _score_color(overall: int) -> tuple[str, str]:
    if overall >= 80:
        return "#0ca30c", "Strong"
    elif overall >= 60:
        return "#2a78d6", "Good"
    elif overall >= 40:
        return "#eda100", "Moderate"
    else:
        return "#d03b3b", "Early Stage"


def _kpi_tile(label: str, value, max_val: int, subtitle: str) -> str:
    return (
        f'<div style="background:#f9f9f7;border:1px solid #e1e0d9;border-radius:6px;'
        f'padding:14px 10px;text-align:center;">'
        f'<div style="font-size:30px;font-weight:700;color:#0b0b0b;line-height:1.1;">{value}</div>'
        f'<div style="font-size:11px;color:#898781;margin-bottom:4px;">/ {max_val}</div>'
        f'<div style="font-size:12px;color:#0b0b0b;font-weight:600;">{label}</div>'
        f'<div style="font-size:11px;color:#898781;margin-top:2px;">{subtitle}</div>'
        f'</div>'
    )


def _bar_row(label: str, value, max_val: int, pct: int) -> str:
    return (
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">'
        f'<div style="width:170px;font-size:13px;color:#52514e;text-align:right;'
        f'white-space:nowrap;flex-shrink:0;">{label}</div>'
        f'<div style="flex:1;background:#e1e0d9;border-radius:4px;height:8px;overflow:hidden;">'
        f'<div style="width:{pct}%;background:#2a78d6;height:100%;border-radius:4px;"></div>'
        f'</div>'
        f'<div style="width:44px;font-size:13px;color:#0b0b0b;font-weight:600;'
        f'font-variant-numeric:tabular-nums;flex-shrink:0;">{value}/{max_val}</div>'
        f'</div>'
    )


def _render_score_html(scores_json: str, topic: str) -> str:
    """Build an HTML score card from the JSON scorecard."""
    try:
        s = json.loads(scores_json)
    except (json.JSONDecodeError, TypeError):
        return ""

    trl = s.get("trl_score") or 0
    pat = s.get("patent_strength") or 0
    mkt = s.get("market_accessibility") or 0
    evi = s.get("evidence_confidence") or 0
    overall = s.get("overall_score") or 0
    scoring_rationale = s.get("scoring_rationale", "")
    risks = s.get("key_risks", [])
    opps = s.get("key_opportunities", [])

    color, badge = _score_color(overall)
    trl_pct = round(trl / 9 * 100)
    pat_pct = round(pat / 5 * 100)
    mkt_pct = round(mkt / 5 * 100)
    evi_pct = round(evi / 5 * 100)

    risks_html = "".join(
        f'<li style="margin-bottom:4px;">{html.escape(str(r))}</li>'
        for r in risks
    )
    opps_html = "".join(
        f'<li style="margin-bottom:4px;">{html.escape(str(o))}</li>'
        for o in opps
    )

    risks_section = (
        f'<div style="flex:1;">'
        f'<div style="font-size:12px;font-weight:600;color:#52514e;margin-bottom:6px;">Key Risks</div>'
        f'<ul style="margin:0;padding-left:18px;font-size:12px;color:#52514e;">{risks_html}</ul>'
        f'</div>'
        if risks else ""
    )
    opps_section = (
        f'<div style="flex:1;">'
        f'<div style="font-size:12px;font-weight:600;color:#52514e;margin-bottom:6px;">Key Opportunities</div>'
        f'<ul style="margin:0;padding-left:18px;font-size:12px;color:#52514e;">{opps_html}</ul>'
        f'</div>'
        if opps else ""
    )
    risks_opps_row = (
        f'<div style="display:flex;gap:24px;margin-top:16px;padding-top:16px;'
        f'border-top:1px solid #e1e0d9;">'
        f'{risks_section}{opps_section}'
        f'</div>'
        if (risks or opps) else ""
    )

    return (
        f'<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;'
        f'background:#fcfcfb;border:1px solid #e1e0d9;border-radius:8px;'
        f'padding:24px;margin-bottom:16px;">'

        # Hero score
        f'<div style="display:flex;align-items:center;gap:20px;margin-bottom:20px;">'
        f'<div style="font-size:60px;font-weight:700;color:{color};line-height:1;">'
        f'{overall}</div>'
        f'<div>'
        f'<div style="font-size:13px;color:#898781;">Overall Score / 100</div>'
        f'<div style="display:inline-block;margin-top:6px;padding:3px 12px;'
        f'border-radius:12px;background:{color};color:#fff;font-size:12px;font-weight:600;">'
        f'{badge}</div>'
        f'</div>'
        f'<div style="flex:1;font-size:12px;color:#52514e;line-height:1.5;">'
        f'{html.escape(scoring_rationale)}</div>'
        f'</div>'

        # KPI tiles
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px;">'
        f'{_kpi_tile("TRL", trl, 9, "Tech Readiness")}'
        f'{_kpi_tile("IP", pat, 5, "Patent Landscape")}'
        f'{_kpi_tile("Market", mkt, 5, "Accessibility")}'
        f'{_kpi_tile("Evidence", evi, 5, "Confidence")}'
        f'</div>'

        # Horizontal bars
        f'<div style="padding-top:16px;border-top:1px solid #e1e0d9;">'
        f'{_bar_row("Technology Readiness", trl, 9, trl_pct)}'
        f'{_bar_row("IP Landscape", pat, 5, pat_pct)}'
        f'{_bar_row("Market Accessibility", mkt, 5, mkt_pct)}'
        f'{_bar_row("Evidence Confidence", evi, 5, evi_pct)}'
        f'</div>'

        f'{risks_opps_row}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Progress display
# ---------------------------------------------------------------------------

def _render_progress_html(stage: str, elapsed: int, run_id: str, spin: str) -> str:
    """Build an HTML progress panel showing agent pipeline status."""
    all_stages = [_STAGE_INITIAL] + TASK_STAGE_LABELS
    try:
        current_idx = all_stages.index(stage)
    except ValueError:
        current_idx = 0

    items = []
    for i, label in enumerate(all_stages):
        if i < current_idx:
            icon, color, weight = "✓", "#0ca30c", "600"
            opacity = "0.7"
        elif i == current_idx:
            icon, color, weight = spin, "#2a78d6", "700"
            opacity = "1"
        else:
            icon, color, weight = "○", "#c3c2b7", "400"
            opacity = "0.5"
        items.append(
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:7px;opacity:{opacity};">'
            f'<span style="width:18px;text-align:center;color:{color};font-weight:{weight};'
            f'font-size:13px;">{icon}</span>'
            f'<span style="font-size:13px;color:#0b0b0b;">{html.escape(label)}</span>'
            f'</div>'
        )

    return (
        f'<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;'
        f'background:#f9f9f7;border:1px solid #e1e0d9;border-radius:8px;padding:18px 22px;">'
        f'<div style="margin-bottom:14px;font-size:14px;color:#52514e;">'
        f'⏳&nbsp; Running &nbsp;·&nbsp; '
        f'<span style="font-variant-numeric:tabular-nums;">{elapsed}s</span> elapsed'
        f'&nbsp;&nbsp;<span style="color:#c3c2b7;">|</span>&nbsp;&nbsp;'
        f'<code style="font-size:12px;color:#898781;">{html.escape(run_id)}</code>'
        f'</div>'
        f'{"".join(items)}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# History tab
# ---------------------------------------------------------------------------

def _parse_run_timestamp(run_id: str) -> str:
    """Convert run_id like '20241215T123456Z-abc' to a readable date."""
    try:
        ts = run_id.split("-")[0]  # '20241215T123456Z'
        dt = datetime.strptime(ts, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return run_id[:16]


def _extract_topic_from_report(report_path: Path) -> str:
    try:
        text = report_path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") and len(stripped) > 2:
                return stripped.lstrip("#").strip()[:90]
    except Exception:
        pass
    return "—"


def _load_run(run_id: str) -> tuple[str, str]:
    """Load score card + report for a past run by its run ID."""
    run_id = run_id.strip()
    if not run_id:
        return "", ""

    run_dir = DEFAULT_OUTPUT_ROOT / run_id
    if not run_dir.is_dir():
        return "", f"> Run `{html.escape(run_id)}` not found in outputs/."

    score_html = ""
    scores_path = run_dir / "commercialization_scores.json"
    if scores_path.exists():
        try:
            topic = "—"
            report_path = run_dir / "commercialization_report.md"
            if report_path.exists():
                topic = _extract_topic_from_report(report_path)
            score_html = _render_score_html(
                scores_path.read_text(encoding="utf-8"), topic
            )
        except Exception:
            pass

    report_md = ""
    report_path = run_dir / "commercialization_report.md"
    if report_path.exists():
        try:
            report_md = report_path.read_text(encoding="utf-8")
        except Exception:
            report_md = "Error reading report file."

    if not score_html and not report_md:
        return "", f"> No report found for run `{html.escape(run_id)}`."

    return score_html, report_md


def _render_history_html() -> str:
    """Build an HTML table of past analysis runs."""
    output_root = DEFAULT_OUTPUT_ROOT
    if not output_root.exists():
        return _history_empty("No output directory found.")

    run_dirs = sorted(
        (d for d in output_root.iterdir() if d.is_dir() and d.name != "benchmark"),
        reverse=True,
    )
    if not run_dirs:
        return _history_empty("No previous runs found. Run an analysis first.")

    rows_html = ""
    for run_dir in run_dirs:
        run_id = run_dir.name
        timestamp = _parse_run_timestamp(run_id)

        topic = "—"
        report_path = run_dir / "commercialization_report.md"
        if report_path.exists():
            topic = _extract_topic_from_report(report_path)

        overall = trl = pat = mkt = evi = "—"
        overall_color = "#0b0b0b"
        scores_path = run_dir / "commercialization_scores.json"
        if scores_path.exists():
            try:
                sc = json.loads(scores_path.read_text(encoding="utf-8"))
                overall = sc.get("overall_score", "—")
                trl = sc.get("trl_score", "—")
                pat = sc.get("patent_strength", "—")
                mkt = sc.get("market_accessibility", "—")
                evi = sc.get("evidence_confidence", "—")
                if isinstance(overall, int):
                    overall_color, _ = _score_color(overall)
            except Exception:
                pass

        has_error = (run_dir / "error.log").exists() and not scores_path.exists()
        status_icon = "✗" if has_error else ("✓" if scores_path.exists() else "?")
        status_color = "#d03b3b" if has_error else ("#0ca30c" if scores_path.exists() else "#898781")

        rows_html += (
            f'<tr style="border-bottom:1px solid #e1e0d9;">'
            f'<td style="padding:8px 12px;color:#898781;font-size:12px;'
            f'font-variant-numeric:tabular-nums;white-space:nowrap;">{html.escape(timestamp)}</td>'
            f'<td style="padding:8px 12px;max-width:320px;overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap;font-size:13px;">{html.escape(topic)}</td>'
            f'<td style="padding:8px 12px;text-align:center;font-size:16px;'
            f'font-weight:700;color:{overall_color};">{overall}</td>'
            f'<td style="padding:8px 12px;text-align:center;font-size:13px;">{trl}/9</td>'
            f'<td style="padding:8px 12px;text-align:center;font-size:13px;">{pat}/5</td>'
            f'<td style="padding:8px 12px;text-align:center;font-size:13px;">{mkt}/5</td>'
            f'<td style="padding:8px 12px;text-align:center;font-size:13px;">{evi}/5</td>'
            f'<td style="padding:8px 12px;text-align:center;color:{status_color};font-size:13px;'
            f'font-weight:600;">{status_icon}</td>'
            f'</tr>'
        )

    return (
        f'<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;'
        f'overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        f'<thead>'
        f'<tr style="border-bottom:2px solid #c3c2b7;">'
        f'<th style="text-align:left;padding:10px 12px;color:#52514e;font-weight:600;'
        f'white-space:nowrap;">Time (UTC)</th>'
        f'<th style="text-align:left;padding:10px 12px;color:#52514e;font-weight:600;">Topic</th>'
        f'<th style="text-align:center;padding:10px 12px;color:#52514e;font-weight:600;">Score</th>'
        f'<th style="text-align:center;padding:10px 12px;color:#52514e;font-weight:600;">TRL</th>'
        f'<th style="text-align:center;padding:10px 12px;color:#52514e;font-weight:600;">Patent</th>'
        f'<th style="text-align:center;padding:10px 12px;color:#52514e;font-weight:600;">Market</th>'
        f'<th style="text-align:center;padding:10px 12px;color:#52514e;font-weight:600;">Evidence</th>'
        f'<th style="text-align:center;padding:10px 12px;color:#52514e;font-weight:600;">Status</th>'
        f'</tr>'
        f'</thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>'
        f'</div>'
    )


def _history_empty(msg: str) -> str:
    return (
        f'<p style="font-family:system-ui;font-size:13px;color:#898781;padding:12px;">'
        f'{html.escape(msg)}</p>'
    )


# ---------------------------------------------------------------------------
# Main analysis runner
# ---------------------------------------------------------------------------

def run_analysis(research_topic: str):
    """Generator that yields (progress_html, score_html, report_md, file_path)."""
    if not research_topic.strip():
        yield "", "", "Please enter a research topic.", None
        return

    run_id = create_run_id()
    result_holder: dict = {
        "result": None,
        "path": None,
        "scores": None,
        "done": False,
        "error": None,
        "error_path": None,
        "current_stage": _STAGE_INITIAL,
    }
    completed_tasks = [0]

    def on_task_complete(_task_output) -> None:
        completed_tasks[0] += 1
        idx = completed_tasks[0]
        if idx < len(TASK_STAGE_LABELS):
            result_holder["current_stage"] = TASK_STAGE_LABELS[idx]

    def _run() -> None:
        try:
            result_holder["current_stage"] = _STAGE_INITIAL
            source_collection = collect_source_collection(research_topic.strip())
            save_source_collection(source_collection.model_dump_json(indent=2), run_id=run_id)
            result_holder["current_stage"] = TASK_STAGE_LABELS[0]

            result = AcademicAgent(
                source_collection,
                task_callback=on_task_complete,
            ).crew().kickoff(inputs=source_collection.crew_inputs())

            tasks_output = getattr(result, "tasks_output", None) or []
            if len(tasks_output) >= 2:
                report_raw = tasks_output[-2].raw
                scores_raw = tasks_output[-1].raw
            else:
                report_raw = result.raw
                scores_raw = None

            _, report_path = save_report(report_raw, run_id=run_id)
            result_holder["result"] = report_raw
            result_holder["path"] = report_path

            if scores_raw:
                save_scores(scores_raw, run_id=run_id)
                result_holder["scores"] = scores_raw

        except Exception as exc:
            error_details = traceback.format_exc()
            error_path = save_error(error_details, run_id=run_id)
            print(error_details, file=sys.stderr, flush=True)
            result_holder["error"] = str(exc)
            result_holder["error_path"] = error_path
        finally:
            result_holder["done"] = True

    threading.Thread(target=_run, daemon=True).start()

    start = time.time()
    tick = 0
    while not result_holder["done"]:
        elapsed = int(time.time() - start)
        stage = result_holder["current_stage"]
        spin = SPINNER[tick % len(SPINNER)]
        yield (
            _render_progress_html(stage, elapsed, run_id, spin),
            "",
            "",
            None,
        )
        time.sleep(0.8)
        tick += 1

    if result_holder["error"]:
        err = result_holder["error"]
        first_line = next((ln.strip() for ln in err.splitlines() if ln.strip()), err)
        error_html = (
            f'<div style="font-family:system-ui;background:#fff5f5;border:1px solid #fcc;'
            f'border-radius:8px;padding:16px 20px;">'
            f'<div style="font-size:14px;font-weight:600;color:#d03b3b;margin-bottom:8px;">'
            f'✗ Analysis Failed</div>'
            f'<div style="font-size:13px;color:#52514e;">{html.escape(first_line)}</div>'
            f'<div style="font-size:12px;color:#898781;margin-top:8px;">'
            f'Run ID: <code>{html.escape(run_id)}</code></div>'
            f'</div>'
        )
        yield error_html, "", "", None
    else:
        report = result_holder["result"] or "Report generation failed. Please retry."
        path = result_holder["path"]
        scores_json = result_holder["scores"]
        score_html = _render_score_html(scores_json, research_topic.strip()) if scores_json else ""
        footer = f"\n\n---\n\nRun ID: `{run_id}`  \nSaved to: `{path}`"
        yield "", score_html, report + footer, str(path) if path else None


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------

_CSS = """
.gr-markdown h2 { margin-top: 1.2em; }
footer { display: none !important; }
"""

with gr.Blocks(title="Academic Commercialization Assessment Agent") as demo:
    gr.Markdown(
        "# Academic Commercialization Assessment Agent\n"
        "Enter a research topic to launch 6 specialized AI agents that assess "
        "commercialization readiness — producing a scored report with traceable citations. "
        "Expected run time: **5–8 minutes**."
    )

    with gr.Tabs():
        # ── Analysis tab ──────────────────────────────────────────────────
        with gr.Tab("Analysis"):
            topic_input = gr.Textbox(
                label="Research Topic",
                placeholder="e.g., perovskite solar cells for building-integrated photovoltaics",
                lines=2,
            )
            with gr.Row():
                submit_btn = gr.Button("Run Analysis", variant="primary", scale=2)
                clear_btn = gr.Button("Clear", scale=1)

            progress_output = gr.HTML(label="Progress")
            score_output = gr.HTML(label="Scorecard")
            report_output = gr.Markdown(label="Full Report")
            download_output = gr.File(label="Download Report (.md)")

            submit_btn.click(
                fn=run_analysis,
                inputs=topic_input,
                outputs=[progress_output, score_output, report_output, download_output],
            )
            clear_btn.click(
                fn=lambda: ("", "", "", "", None),
                outputs=[topic_input, progress_output, score_output, report_output, download_output],
            )

        # ── History tab ───────────────────────────────────────────────────
        with gr.Tab("History"):
            refresh_btn = gr.Button("Refresh", variant="secondary")
            history_output = gr.HTML(value=_render_history_html())
            refresh_btn.click(fn=_render_history_html, outputs=history_output)

            gr.Markdown("---\n**Load a past run** — paste a Run ID from the table above:")
            with gr.Row():
                run_id_input = gr.Textbox(
                    label="Run ID",
                    placeholder="20260703T032111Z-98b72a7f17",
                    scale=4,
                )
                load_btn = gr.Button("Load", variant="primary", scale=1)
            loaded_score = gr.HTML()
            loaded_report = gr.Markdown()
            load_btn.click(
                fn=_load_run,
                inputs=run_id_input,
                outputs=[loaded_score, loaded_report],
            )


if __name__ == "__main__":
    demo.launch(css=_CSS)
