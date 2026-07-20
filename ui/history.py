"""history — History table HTML, cleanup, and load_run."""

import html
import json
from pathlib import Path

from ui.i18n import _ui
from ui.html_scorecard import _score_color, _render_score_html
from ui.html_sources import _build_sources_index, _render_source_warning_html, _src_detail_panel_html
from ui.html_misc import _render_reviewer_notes_html
from ui.run_reader import (
    _parse_run_timestamp,
    _run_duration,
    _read_run_topic,
    _read_output_language,
    _read_weight_profile,
)
from academic_agent.run_output import DEFAULT_OUTPUT_ROOT


def _load_run(run_id: str) -> tuple[str, str]:
    """Load score card + report for a past run by its run ID."""
    run_id = run_id.strip()
    if not run_id:
        return "", ""

    run_dir = (DEFAULT_OUTPUT_ROOT / run_id).resolve()
    if not run_dir.is_relative_to(DEFAULT_OUTPUT_ROOT.resolve()):
        return "", "> Invalid Run ID."
    if not run_dir.is_dir():
        return "", f"> Run `{html.escape(run_id)}` not found in outputs/."

    sources_index = _build_sources_index(run_dir)
    score_html = ""
    scores_path = run_dir / "commercialization_scores.json"
    output_lang = "English"
    if scores_path.exists():
        try:
            topic = _read_run_topic(run_dir)
            output_lang = _read_output_language(run_dir)
            wp = _read_weight_profile(run_dir)
            score_html = (
                _render_source_warning_html(run_dir, output_lang)
                + _render_score_html(
                    scores_path.read_text(encoding="utf-8"), topic, output_lang, wp,
                    sources_index=sources_index,
                )
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

    score_html += _render_reviewer_notes_html(run_dir, output_lang)
    score_html += _src_detail_panel_html(sources_index)
    return score_html, report_md


def _render_history_html(ui_lang: str = "English") -> str:
    """Build an HTML table of past analysis runs."""
    u = _ui(ui_lang)
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

        topic = _read_run_topic(run_dir)
        duration = _run_duration(run_dir)

        overall = trl = mrl = pat = mkt = evi = "—"
        overall_color = "#0b0b0b"
        scores_path = run_dir / "commercialization_scores.json"
        if scores_path.exists():
            try:
                sc = json.loads(scores_path.read_text(encoding="utf-8"))
                overall = sc.get("overall_score", "—")
                trl = sc.get("trl_score", "—")
                mrl = sc.get("mrl_score", "—")
                pat = sc.get("patent_strength", "—")
                mkt = sc.get("market_accessibility", "—")
                evi = sc.get("evidence_confidence", "—")
                if isinstance(overall, (int, float)):
                    overall_color, _ = _score_color(overall)
            except Exception:
                pass

        has_error = (run_dir / "error.log").exists() and not scores_path.exists()
        if has_error:
            status_cell = '<span style="color:#dc2626;font-weight:700;font-size:13px;">✗ Error</span>'
        elif scores_path.exists():
            status_cell = '<span style="color:#16a34a;font-weight:700;font-size:13px;">✓ Done</span>'
        else:
            status_cell = '<span style="color:#9a9a9a;font-size:13px;">—</span>'

        if isinstance(overall, (int, float)):
            _, badge_label = _score_color(overall)
            overall_display = f"{overall:.1f}"
            score_cell = (
                f'<div style="display:flex;flex-direction:column;align-items:center;gap:3px;">'
                f'<span style="font-size:16px;font-weight:800;color:{overall_color};'
                f'font-variant-numeric:tabular-nums;">{overall_display}</span>'
                f'<span style="font-size:10px;font-weight:700;color:{overall_color};'
                f'background:{overall_color}18;border-radius:10px;padding:1px 7px;'
                f'letter-spacing:0.04em;text-transform:uppercase;">{badge_label}</span>'
                f'</div>'
            )
        else:
            score_cell = f'<span style="color:#9a9a9a;">—</span>'

        run_id_short = run_id[:26]
        rows_html += (
            f'<tr style="border-bottom:1px solid #1a1a1a;cursor:pointer;" '
            f'data-topic="{html.escape(topic)}" '
            f'title="Click to copy Run ID" '
            f'onclick="(function(){{var el=document.querySelector(\'textarea[data-testid=\\"run_id_input\\"]\');'
            f'if(!el)el=document.querySelector(\'input[placeholder*=\\"20\\"]\');'
            f'if(el){{el.value=\'{html.escape(run_id)}\';'
            f'el.dispatchEvent(new Event(\'input\',{{bubbles:true}}));}}}})();" '
            f'onmouseover="this.style.background=\'#222222\'" '
            f'onmouseout="this.style.background=\'\'">'
            f'<td style="padding:10px 14px;color:#777777;font-size:12px;'
            f'font-variant-numeric:tabular-nums;white-space:nowrap;">{html.escape(timestamp)}</td>'
            f'<td style="padding:10px 14px;max-width:300px;overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap;font-size:13px;color:#e5e5e5;'
            f'font-weight:500;" title="{html.escape(topic)}">{html.escape(topic)}</td>'
            f'<td style="padding:10px 14px;text-align:center;font-size:12px;'
            f'color:#777777;font-variant-numeric:tabular-nums;white-space:nowrap;">{html.escape(duration)}</td>'
            f'<td style="padding:10px 14px;text-align:center;">{score_cell}</td>'
            f'<td style="padding:10px 14px;text-align:center;font-size:13px;'
            f'color:#9a9a9a;font-variant-numeric:tabular-nums;">{f"{trl}/9" if isinstance(trl, (int, float)) else "—"}</td>'
            f'<td style="padding:10px 14px;text-align:center;font-size:13px;'
            f'color:#9a9a9a;font-variant-numeric:tabular-nums;">{f"{mrl}/10" if isinstance(mrl, (int, float)) else "—"}</td>'
            f'<td style="padding:10px 14px;text-align:center;font-size:13px;'
            f'color:#9a9a9a;font-variant-numeric:tabular-nums;">{f"{pat}/5" if isinstance(pat, (int, float)) else "—"}</td>'
            f'<td style="padding:10px 14px;text-align:center;font-size:13px;'
            f'color:#9a9a9a;font-variant-numeric:tabular-nums;">{f"{mkt}/5" if isinstance(mkt, (int, float)) else "—"}</td>'
            f'<td style="padding:10px 14px;text-align:center;font-size:13px;'
            f'color:#9a9a9a;font-variant-numeric:tabular-nums;">{f"{evi}/5" if isinstance(evi, (int, float)) else "—"}</td>'
            f'<td style="padding:10px 14px;text-align:center;">{status_cell}</td>'
            f'<td style="padding:10px 14px;font-family:ui-monospace,monospace;font-size:10px;'
            f'color:#3f3f46;white-space:nowrap;">{html.escape(run_id_short)}</td>'
            f'</tr>'
        )

    _hist_filter_js = (
        "(function(inp){var q=inp.value.toLowerCase();"
        "document.querySelectorAll('#hist-tbody tr').forEach(function(r){"
        "var t=r.getAttribute('data-topic')||'';"
        "r.style.display=t.toLowerCase().includes(q)?'':'none';"
        "});}).call(this)"
    )
    return (
        f'<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;'
        f'border:1px solid #2d2d2d;border-radius:10px;overflow:hidden;">'
        f'<div style="padding:8px 14px 6px;background:#0f0f0f;border-bottom:1px solid #1a1a1a;'
        f'display:flex;align-items:center;gap:12px;">'
        f'<input type="text" placeholder="{html.escape(u["hist_filter"])}" '
        f'oninput="{_hist_filter_js}" '
        f'style="flex:1;max-width:340px;background:#1a1a1a;border:1px solid #3d3d3d;'
        f'border-radius:6px;padding:4px 10px;font-size:12px;color:#e5e5e5;'
        f'font-family:system-ui;outline:none;" />'
        f'<span style="font-size:11px;color:#4b5563;white-space:nowrap;">'
        f'{html.escape(u["hist_hint"])}</span>'
        f'</div>'
        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        f'<thead>'
        f'<tr style="background:#141414;border-bottom:1px solid #2d2d2d;">'
        f'<th style="text-align:left;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;white-space:nowrap;">{html.escape(u["hist_col_time"])}</th>'
        f'<th style="text-align:left;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">{html.escape(u["hist_col_topic"])}</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;white-space:nowrap;">{html.escape(u["hist_col_duration"])}</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">{html.escape(u["hist_col_score"])}</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">TRL</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">MRL</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">{html.escape(u["src_patent"])}</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">{html.escape(u["src_market"])}</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">{html.escape(u.get("src_evidence", "Evidence"))}</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">{html.escape(u["hist_col_status"])}</th>'
        f'<th style="text-align:left;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">{html.escape(u["hist_col_runid"])}</th>'
        f'</tr>'
        f'</thead>'
        f'<tbody id="hist-tbody">{rows_html}</tbody>'
        f'</table>'
        f'</div>'
        f'</div>'
    )


def _cleanup_old_runs(keep_n: int = 20) -> str:
    """Delete all but the latest keep_n run directories, leaving benchmark/ untouched."""
    output_root = DEFAULT_OUTPUT_ROOT
    if not output_root.exists():
        return "No output directory found."
    run_dirs = sorted(
        (d for d in output_root.iterdir() if d.is_dir() and d.name != "benchmark"),
        reverse=True,
    )
    to_delete = run_dirs[keep_n:]
    if not to_delete:
        return f"Nothing to clean — {len(run_dirs)} run(s) present, limit is {keep_n}."
    import shutil
    deleted = 0
    for d in to_delete:
        try:
            shutil.rmtree(d)
            deleted += 1
        except Exception:
            pass
    return f"Deleted {deleted} old run(s). {min(len(run_dirs), keep_n)} remain."


def _history_empty(msg: str) -> str:
    return (
        f'<p style="font-family:system-ui;font-size:13px;color:#777777;padding:12px;">'
        f'{html.escape(msg)}</p>'
    )
