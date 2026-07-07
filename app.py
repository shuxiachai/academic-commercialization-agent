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
        return "#16a34a", "Strong"
    elif overall >= 60:
        return "#2563eb", "Good"
    elif overall >= 40:
        return "#d97706", "Moderate"
    else:
        return "#dc2626", "Early Stage"


def _metric_color(pct: int) -> str:
    if pct >= 75:
        return "#16a34a"
    elif pct >= 50:
        return "#2563eb"
    elif pct >= 30:
        return "#d97706"
    else:
        return "#dc2626"


def _source_id_chips(ids: list) -> str:
    if not ids:
        return ""
    chips = "".join(
        f'<span style="display:inline-block;background:#222222;border:1px solid #333333;'
        f'color:#9a9a9a;font-size:9px;font-family:ui-monospace,monospace;font-weight:600;'
        f'padding:1px 5px;border-radius:4px;margin:1px 1px 0;">{html.escape(str(sid))}</span>'
        for sid in ids
    )
    return f'<div style="margin-top:6px;line-height:1.8;">{chips}</div>'


def _kpi_tile(label: str, value, max_val: int, subtitle: str, pct: int, source_ids: list | None = None) -> str:
    accent = _metric_color(pct)
    chips = _source_id_chips(source_ids or [])
    return (
        f'<div style="background:#1a1a1a;border:1px solid #2d2d2d;'
        f'border-top:3px solid {accent};border-radius:8px;'
        f'padding:16px 12px;text-align:center;">'
        f'<div style="font-size:32px;font-weight:800;color:#f5f5f5;line-height:1.1;">{value}</div>'
        f'<div style="font-size:11px;color:#777777;margin-bottom:6px;">/ {max_val}</div>'
        f'<div style="font-size:12px;color:#d4d4d4;font-weight:700;letter-spacing:0.02em;">{label}</div>'
        f'<div style="font-size:11px;color:#777777;margin-top:2px;">{subtitle}</div>'
        f'{chips}'
        f'</div>'
    )


def _bar_row(label: str, value, max_val: int, pct: int) -> str:
    bar_color = _metric_color(pct)
    return (
        f'<div style="display:flex;align-items:center;gap:14px;margin-bottom:12px;">'
        f'<div style="width:180px;font-size:13px;color:#9a9a9a;text-align:right;'
        f'white-space:nowrap;flex-shrink:0;font-weight:500;">{label}</div>'
        f'<div style="flex:1;background:#111111;border-radius:6px;height:10px;overflow:hidden;">'
        f'<div style="width:{pct}%;background:{bar_color};height:100%;border-radius:6px;"></div>'
        f'</div>'
        f'<div style="width:44px;font-size:13px;color:#e5e5e5;font-weight:700;'
        f'font-variant-numeric:tabular-nums;flex-shrink:0;">{value}/{max_val}</div>'
        f'</div>'
    )


def _bullet_item(text: str, color: str) -> str:
    return (
        f'<div style="display:flex;gap:8px;margin-bottom:8px;align-items:flex-start;">'
        f'<span style="color:{color};font-size:14px;line-height:1.4;flex-shrink:0;">▸</span>'
        f'<span style="font-size:12px;color:#d4d4d4;line-height:1.5;">{html.escape(text)}</span>'
        f'</div>'
    )


def _render_score_html(scores_json: str, topic: str) -> str:
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
    trl_ids  = s.get("trl_source_ids", [])
    pat_ids  = s.get("patent_source_ids", [])
    mkt_ids  = s.get("market_source_ids", [])
    evi_ids  = s.get("evidence_source_ids", [])

    color, badge = _score_color(overall)
    trl_pct = round(trl / 9 * 100)
    pat_pct = round(pat / 5 * 100)
    mkt_pct = round(mkt / 5 * 100)
    evi_pct = round(evi / 5 * 100)

    risks_block = "".join(_bullet_item(str(r), "#dc2626") for r in risks)
    opps_block  = "".join(_bullet_item(str(o), "#16a34a") for o in opps)

    risks_col = (
        f'<div style="flex:1;background:#2d1515;border:1px solid #7f1d1d;'
        f'border-radius:8px;padding:16px;">'
        f'<div style="font-size:12px;font-weight:700;color:#fca5a5;'
        f'letter-spacing:0.05em;text-transform:uppercase;margin-bottom:10px;">'
        f'&#x26A0; Key Risks</div>'
        f'{risks_block}'
        f'</div>'
    ) if risks else ""

    opps_col = (
        f'<div style="flex:1;background:#0f2d1a;border:1px solid #14532d;'
        f'border-radius:8px;padding:16px;">'
        f'<div style="font-size:12px;font-weight:700;color:#86efac;'
        f'letter-spacing:0.05em;text-transform:uppercase;margin-bottom:10px;">'
        f'&#x2726; Key Opportunities</div>'
        f'{opps_block}'
        f'</div>'
    ) if opps else ""

    risks_opps_row = (
        f'<div style="display:flex;gap:16px;margin-top:20px;">'
        f'{risks_col}{opps_col}'
        f'</div>'
    ) if (risks or opps) else ""

    return (
        f'<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;'
        f'background:#1a1a1a;border:1px solid #2d2d2d;'
        f'border-left:4px solid {color};border-radius:10px;'
        f'padding:24px;margin-bottom:16px;">'

        # Hero row
        f'<div style="display:flex;align-items:stretch;gap:24px;margin-bottom:24px;">'
        f'<div style="text-align:center;min-width:100px;">'
        f'<div style="font-size:72px;font-weight:800;color:{color};line-height:0.9;">{overall}</div>'
        f'<div style="font-size:11px;color:#777777;margin-top:6px;">out of 100</div>'
        f'<div style="display:inline-block;margin-top:10px;padding:4px 14px;'
        f'border-radius:20px;background:{color};color:#ffffff;'
        f'font-size:12px;font-weight:700;letter-spacing:0.04em;">{badge}</div>'
        f'</div>'
        f'<div style="flex:1;border-left:1px solid #2d2d2d;padding-left:20px;'
        f'display:flex;flex-direction:column;justify-content:center;">'
        f'<div style="font-size:10px;font-weight:700;color:#777777;'
        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">Scoring Formula</div>'
        f'<div style="font-size:12px;color:#d4d4d4;background:#141414;'
        f'border:1px solid #2d2d2d;border-radius:6px;padding:10px 14px;'
        f'font-family:ui-monospace,monospace;line-height:1.6;">'
        f'{html.escape(scoring_rationale)}</div>'
        f'</div>'
        f'</div>'

        # KPI tiles
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:20px;">'
        f'{_kpi_tile("TRL", trl, 9, "Tech Readiness", trl_pct, trl_ids)}'
        f'{_kpi_tile("IP", pat, 5, "Patent Landscape", pat_pct, pat_ids)}'
        f'{_kpi_tile("Market", mkt, 5, "Accessibility", mkt_pct, mkt_ids)}'
        f'{_kpi_tile("Evidence", evi, 5, "Confidence", evi_pct, evi_ids)}'
        f'</div>'

        # Bars
        f'<div style="background:#141414;border:1px solid #2d2d2d;border-radius:8px;padding:18px 20px;">'
        f'{_bar_row("Technology Readiness", trl, 9, trl_pct)}'
        f'{_bar_row("IP Landscape", pat, 5, pat_pct)}'
        f'{_bar_row("Market Accessibility", mkt, 5, mkt_pct)}'
        f'<div style="margin-bottom:0;">'
        f'{_bar_row("Evidence Confidence", evi, 5, evi_pct)}'
        f'</div>'
        f'</div>'

        f'{risks_opps_row}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Progress display
# ---------------------------------------------------------------------------

def _render_progress_html(stage: str, elapsed: int, run_id: str, spin: str) -> str:
    all_stages = [_STAGE_INITIAL] + TASK_STAGE_LABELS
    try:
        current_idx = all_stages.index(stage)
    except ValueError:
        current_idx = 0

    items = []
    for i, label in enumerate(all_stages):
        if i < current_idx:
            icon, fg, weight, opacity = "✓", "#16a34a", "700", "0.75"
        elif i == current_idx:
            icon, fg, weight, opacity = spin, "#2563eb", "700", "1"
        else:
            icon, fg, weight, opacity = "○", "#9ca3af", "400", "0.4"
        items.append(
            f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:8px;opacity:{opacity};">'
            f'<span style="width:20px;text-align:center;color:{fg};font-weight:{weight};'
            f'font-size:13px;flex-shrink:0;">{icon}</span>'
            f'<span style="font-size:13px;color:#e5e5e5;font-weight:{"600" if i == current_idx else "400"};">'
            f'{html.escape(label)}</span>'
            f'</div>'
        )

    mins, secs = divmod(elapsed, 60)
    elapsed_str = f"{mins}m {secs:02d}s" if mins else f"{secs}s"
    return (
        f'<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;'
        f'background:#1a1a1a;border:1px solid #2d2d2d;border-left:4px solid #3b82f6;'
        f'border-radius:10px;padding:20px 24px;">'
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:16px;">'
        f'<div style="width:8px;height:8px;border-radius:50%;background:#3b82f6;'
        f'box-shadow:0 0 0 3px #1e3a5f;flex-shrink:0;"></div>'
        f'<span style="font-size:13px;font-weight:600;color:#f5f5f5;">Analysis in progress</span>'
        f'<span style="margin-left:auto;font-size:12px;color:#777777;'
        f'font-variant-numeric:tabular-nums;">{elapsed_str}</span>'
        f'</div>'
        f'{"".join(items)}'
        f'<div style="margin-top:14px;padding-top:12px;border-top:1px solid #2d2d2d;">'
        f'<span style="font-size:11px;color:#555555;font-family:ui-monospace,monospace;">'
        f'Run ID: {html.escape(run_id)}</span>'
        f'</div>'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# History tab
# ---------------------------------------------------------------------------

def _parse_run_timestamp(run_id: str) -> str:
    """Convert run_id like '20241215T123456Z-abc' to local time."""
    try:
        ts = run_id.split("-")[0]  # '20241215T123456Z'
        dt = datetime.strptime(ts, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return run_id[:16]


_REPORT_TITLE_PREFIXES = (
    "academic commercialization assessment:",
    # Common localized prefixes — strip the heading label, keep the topic
    "学术商业化评估：", "学术商业化评估:", "学术商业化评估",
    "commercialization assessment:",
)

def _extract_topic_from_report(report_path: Path) -> str:
    try:
        text = report_path.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") and len(stripped) > 2:
                title = stripped.lstrip("#").strip()
                for prefix in _REPORT_TITLE_PREFIXES:
                    if title.lower().startswith(prefix.lower()):
                        title = title[len(prefix):].strip()
                        break
                return title[:90] if title else "—"
    except Exception:
        pass
    return "—"


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
        if has_error:
            status_cell = '<span style="color:#dc2626;font-weight:700;font-size:13px;">✗ Error</span>'
        elif scores_path.exists():
            status_cell = '<span style="color:#16a34a;font-weight:700;font-size:13px;">✓ Done</span>'
        else:
            status_cell = '<span style="color:#9a9a9a;font-size:13px;">—</span>'

        if isinstance(overall, int):
            _, badge_label = _score_color(overall)
            score_cell = (
                f'<div style="display:flex;flex-direction:column;align-items:center;gap:3px;">'
                f'<span style="font-size:16px;font-weight:800;color:{overall_color};'
                f'font-variant-numeric:tabular-nums;">{overall}</span>'
                f'<span style="font-size:10px;font-weight:700;color:{overall_color};'
                f'background:{overall_color}18;border-radius:10px;padding:1px 7px;'
                f'letter-spacing:0.04em;text-transform:uppercase;">{badge_label}</span>'
                f'</div>'
            )
        else:
            score_cell = f'<span style="color:#9a9a9a;">—</span>'

        rows_html += (
            f'<tr style="border-bottom:1px solid #1a1a1a;" '
            f'onmouseover="this.style.background=\'#222222\'" '
            f'onmouseout="this.style.background=\'\'">'
            f'<td style="padding:10px 14px;color:#777777;font-size:12px;'
            f'font-variant-numeric:tabular-nums;white-space:nowrap;">{html.escape(timestamp)}</td>'
            f'<td style="padding:10px 14px;max-width:320px;overflow:hidden;'
            f'text-overflow:ellipsis;white-space:nowrap;font-size:13px;color:#e5e5e5;'
            f'font-weight:500;">{html.escape(topic)}</td>'
            f'<td style="padding:10px 14px;text-align:center;">{score_cell}</td>'
            f'<td style="padding:10px 14px;text-align:center;font-size:13px;'
            f'color:#9a9a9a;font-variant-numeric:tabular-nums;">{f"{trl}/9" if isinstance(trl, int) else "—"}</td>'
            f'<td style="padding:10px 14px;text-align:center;font-size:13px;'
            f'color:#9a9a9a;font-variant-numeric:tabular-nums;">{f"{pat}/5" if isinstance(pat, int) else "—"}</td>'
            f'<td style="padding:10px 14px;text-align:center;font-size:13px;'
            f'color:#9a9a9a;font-variant-numeric:tabular-nums;">{f"{mkt}/5" if isinstance(mkt, int) else "—"}</td>'
            f'<td style="padding:10px 14px;text-align:center;font-size:13px;'
            f'color:#9a9a9a;font-variant-numeric:tabular-nums;">{f"{evi}/5" if isinstance(evi, int) else "—"}</td>'
            f'<td style="padding:10px 14px;text-align:center;">{status_cell}</td>'
            f'</tr>'
        )

    return (
        f'<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;'
        f'overflow-x:auto;border:1px solid #2d2d2d;border-radius:10px;overflow:hidden;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        f'<thead>'
        f'<tr style="background:#141414;border-bottom:1px solid #2d2d2d;">'
        f'<th style="text-align:left;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;white-space:nowrap;">Time (Local)</th>'
        f'<th style="text-align:left;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">Topic</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">Score</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">TRL</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">Patent</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">Market</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">Evidence</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">Status</th>'
        f'</tr>'
        f'</thead>'
        f'<tbody>{rows_html}</tbody>'
        f'</table>'
        f'</div>'
    )


def _history_empty(msg: str) -> str:
    return (
        f'<p style="font-family:system-ui;font-size:13px;color:#777777;padding:12px;">'
        f'{html.escape(msg)}</p>'
    )


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

# (path, reportlab-name, is_ttc)
_CJK_FONT_CANDIDATES = [
    (r"C:\Windows\Fonts\simhei.ttf", "SimHei",         False),
    (r"C:\Windows\Fonts\msyh.ttc",   "MicrosoftYaHei", True),
    (r"C:\Windows\Fonts\simsun.ttc", "SimSun",         True),
]


def _register_cjk_font() -> str:
    """Register the first available CJK font directly with reportlab.

    Bypasses xhtml2pdf's @font-face / URL loading (which fails on Windows
    paths) by using reportlab's native TTFont API. Returns the registered
    font name, or '' when no CJK font is found.
    """
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        for path_str, name, is_ttc in _CJK_FONT_CANDIDATES:
            p = Path(path_str)
            if not p.exists():
                continue
            try:
                kwargs = {"subfontIndex": 0} if is_ttc else {}
                pdfmetrics.registerFont(TTFont(name, str(p), **kwargs))
                return name
            except Exception:
                continue
    except ImportError:
        pass
    return ""


def _generate_pdf(report_md: str, run_dir: Path) -> Path | None:
    """Convert markdown report to PDF alongside the .md file. Returns path or None."""
    try:
        import markdown as md_lib
        from xhtml2pdf import pisa

        cjk_font = _register_cjk_font()
        font_family = f"'{cjk_font}', Helvetica, Arial, sans-serif" if cjk_font else "Helvetica, Arial, sans-serif"
        html_body = md_lib.markdown(report_md, extensions=["tables", "fenced_code"])
        styled = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
@page {{ margin: 2cm; }}
body {{ font-family: {font_family}; font-size: 10pt;
        line-height: 1.55; color: #1a1a1a; }}
h1 {{ font-size: 15pt; color: #111827; border-bottom: 1.5pt solid #2563eb;
      padding-bottom: 4pt; margin-top: 0; }}
h2 {{ font-size: 12pt; color: #1e293b; border-bottom: 0.5pt solid #d1d5db;
      margin-top: 14pt; padding-bottom: 2pt; }}
h3 {{ font-size: 10.5pt; color: #374151; margin-top: 10pt; }}
p  {{ margin: 5pt 0; }}
table {{ width: 100%; border-collapse: collapse; font-size: 8.5pt; margin: 6pt 0; }}
th {{ background: #f8fafc; font-weight: bold; padding: 4pt 6pt;
      border: 0.5pt solid #d1d5db; text-align: left; }}
td {{ padding: 3pt 6pt; border: 0.5pt solid #d1d5db; vertical-align: top; }}
code {{ background: #f3f4f6; padding: 1pt 3pt; font-size: 8pt; }}
pre  {{ background: #f3f4f6; padding: 7pt; font-size: 8pt;
        border-left: 3pt solid #2563eb; margin: 6pt 0; }}
ul, ol {{ margin: 4pt 0; padding-left: 14pt; }}
li {{ margin-bottom: 2pt; }}
strong {{ font-weight: bold; }}
em {{ font-style: italic; }}
</style></head><body>{html_body}</body></html>"""

        pdf_path = run_dir / "commercialization_report.pdf"
        with open(pdf_path, "wb") as f:
            result = pisa.CreatePDF(styled, dest=f, encoding="utf-8")
        return None if result.err else pdf_path
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main analysis runner
# ---------------------------------------------------------------------------

def run_analysis(research_topic: str):
    """Generator that yields (progress_html, score_html, report_md, md_path, pdf_path)."""
    if not research_topic.strip():
        yield "", "", "Please enter a research topic.", None, None
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
        "output_language": None,
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
            result_holder["output_language"] = source_collection.output_language
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
            gr.update(visible=False),
            gr.update(visible=False),
        )
        time.sleep(0.8)
        tick += 1

    if result_holder["error"]:
        err = result_holder["error"]
        first_line = next((ln.strip() for ln in err.splitlines() if ln.strip()), err)
        error_html = (
            f'<div style="font-family:system-ui;background:#2d1515;border:1px solid #7f1d1d;'
            f'border-radius:8px;padding:16px 20px;">'
            f'<div style="font-size:14px;font-weight:600;color:#f87171;margin-bottom:8px;">'
            f'✗ Analysis Failed</div>'
            f'<div style="font-size:13px;color:#9a9a9a;">{html.escape(first_line)}</div>'
            f'<div style="font-size:12px;color:#777777;margin-top:8px;">'
            f'Run ID: <code>{html.escape(run_id)}</code></div>'
            f'</div>'
        )
        yield error_html, "", "", gr.update(visible=False), gr.update(visible=False)
    else:
        report = result_holder["result"] or "Report generation failed. Please retry."
        path = result_holder["path"]
        scores_json = result_holder["scores"]
        output_language = result_holder.get("output_language") or "English"
        lang_badge = (
            f'<div style="font-family:system-ui;margin-bottom:10px;">'
            f'<span style="background:#1a1a1a;border:1px solid #2d2d2d;color:#9a9a9a;'
            f'font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;">'
            f'🌐 Report language: {html.escape(output_language)}</span></div>'
        ) if output_language != "English" else ""
        score_html = (lang_badge + _render_score_html(scores_json, research_topic.strip())) if scores_json else lang_badge
        footer = f"\n\n---\n\nRun ID: `{run_id}`  \nSaved to: `{path}`"
        md_update = gr.update(value=str(path), visible=True) if path else gr.update(visible=False)
        pdf_path = _generate_pdf(report, path.parent) if path else None
        pdf_update = gr.update(value=str(pdf_path), visible=True) if pdf_path else gr.update(visible=False)
        yield "", score_html, report + footer, md_update, pdf_update


# ---------------------------------------------------------------------------
# Gradio UI
# ---------------------------------------------------------------------------


_CSS = """
footer { display: none !important; }

/* ── Dark theme ── */
html, html.dark, .dark, :root {
  color-scheme: dark !important;
  --body-background-fill:            #111111 !important;
  --background-fill-primary:         #1a1a1a !important;
  --background-fill-secondary:       #141414 !important;
  --panel-background-fill:           #111111 !important;
  --block-background-fill:           #111111 !important;
  --body-text-color:                 #f5f5f5 !important;
  --body-text-color-subdued:         #9a9a9a !important;
  --block-title-text-color:          #e5e5e5 !important;
  --block-label-text-color:          #9a9a9a !important;
  --block-info-text-color:           #777777 !important;
  --border-color-primary:            #2d2d2d !important;
  --border-color-accent:             #3b82f6 !important;
  --input-background-fill:           #1a1a1a !important;
  --input-background-fill-focus:     #222222 !important;
  --input-text-color:                #f5f5f5 !important;
  --input-placeholder-color:         #555555 !important;
  --input-border-color:              #2d2d2d !important;
  --input-border-color-focus:        #3b82f6 !important;
  --button-secondary-background-fill:        #1a1a1a !important;
  --button-secondary-background-fill-hover:  #222222 !important;
  --button-secondary-text-color:             #d4d4d4 !important;
  --button-secondary-border-color:           #2d2d2d !important;
  --button-secondary-border-color-hover:     #555555 !important;
  --checkbox-background-color:       #1a1a1a !important;
  --checkbox-border-color:           #2d2d2d !important;
  --tab-text-color:                  #9a9a9a !important;
  --tab-text-color-selected:         #f5f5f5 !important;
  --table-even-background-fill:      #1a1a1a !important;
  --table-odd-background-fill:       #141414 !important;
  --code-background-fill:            #111111 !important;
  --link-text-color:                 #60a5fa !important;
  --link-text-color-hover:           #93c5fd !important;
  --neutral-50:  #111111 !important;
  --neutral-100: #1a1a1a !important;
  --neutral-200: #222222 !important;
  --neutral-300: #2d2d2d !important;
  --neutral-400: #555555 !important;
  --neutral-500: #777777 !important;
  --neutral-600: #9a9a9a !important;
  --neutral-700: #d4d4d4 !important;
  --neutral-800: #e5e5e5 !important;
  --neutral-900: #f5f5f5 !important;
  --neutral-950: #f8fafc !important;
}

/* ── Inline clear button ── */
.clear-icon-btn {
    align-self: flex-end !important;
    flex-shrink: 0 !important;
}
.clear-icon-btn button {
    width: 44px !important;
    height: 44px !important;
    min-width: 44px !important;
    min-height: 44px !important;
    border: 1px solid #2d2d2d !important;
    background: transparent !important;
    color: #555555 !important;
    font-size: 20px !important;
    border-radius: 8px !important;
    padding: 0 !important;
    line-height: 1 !important;
    margin-bottom: 2px !important;
    box-shadow: none !important;
}
.clear-icon-btn button:hover {
    background: #2d1515 !important;
    color: #f87171 !important;
    border-color: #7f1d1d !important;
}

/* ── Report markdown ── */
.report-md h2 { margin-top: 1.6em; padding-bottom: 0.3em; border-bottom: 1px solid #2d2d2d; }
.report-md h3 { margin-top: 1.2em; }
.report-md p, .report-md li { line-height: 1.7; }
.report-md table { width: 100%; border-collapse: collapse; font-size: 0.88em; }
.report-md th { background: #141414; font-weight: 700; padding: 8px 12px; border: 1px solid #2d2d2d; text-align: left; }
.report-md td { padding: 7px 12px; border: 1px solid #2d2d2d; }
"""

_HEADER_HTML = """
<div style="font-family:system-ui,-apple-system,'Segoe UI',sans-serif;
  padding:24px 0 18px; border-bottom:1px solid #2d2d2d; margin-bottom:8px;">
  <div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
    <h1 style="font-size:21px;font-weight:800;color:#f5f5f5;letter-spacing:-0.3px;margin:0;">
      Academic Commercialization Assessment
    </h1>
    <span style="background:#1e3a5f;color:#60a5fa;font-size:10px;font-weight:800;
      padding:3px 9px;border-radius:10px;letter-spacing:0.06em;text-transform:uppercase;">BETA</span>
  </div>
  <p style="font-size:13px;color:#9a9a9a;line-height:1.6;max-width:660px;margin:0 0 12px;">
    Enter a research topic to launch <strong style="color:#e5e5e5;">6 specialized AI agents</strong>
    that assess commercialization readiness — producing a scored report with verified citations.
    Expected run time: <strong style="color:#e5e5e5;">5–8 minutes</strong>.
    Input any language — the report is generated in the same language.
  </p>
  <div style="display:flex;gap:6px;flex-wrap:wrap;">
    <span style="background:#1a1a1a;border:1px solid #2d2d2d;color:#9a9a9a;font-size:11px;
      font-weight:600;padding:3px 10px;border-radius:20px;">📚 OpenAlex · Semantic Scholar</span>
    <span style="background:#1a1a1a;border:1px solid #2d2d2d;color:#9a9a9a;font-size:11px;
      font-weight:600;padding:3px 10px;border-radius:20px;">🔬 6 AI Agents</span>
    <span style="background:#1a1a1a;border:1px solid #2d2d2d;color:#9a9a9a;font-size:11px;
      font-weight:600;padding:3px 10px;border-radius:20px;">📊 TRL · IP · Market · Evidence</span>
    <span style="background:#1a1a1a;border:1px solid #2d2d2d;color:#9a9a9a;font-size:11px;
      font-weight:600;padding:3px 10px;border-radius:20px;">✓ Verified Citations</span>
  </div>
</div>
"""

_theme = gr.themes.Default(
    primary_hue=gr.themes.colors.blue,
    neutral_hue=gr.themes.colors.slate,
).set(
    button_primary_background_fill="#2563eb",
    button_primary_background_fill_hover="#1d4ed8",
    button_primary_text_color="#ffffff",
)

with gr.Blocks(title="Academic Commercialization Assessment") as demo:
    gr.HTML(_HEADER_HTML)

    with gr.Tabs():
        # ── Analysis tab ──────────────────────────────────────────────────
        with gr.Tab("Analysis"):
            with gr.Row(equal_height=False):
                topic_input = gr.Textbox(
                    label="Research Topic",
                    placeholder="e.g., perovskite solar cells for building-integrated photovoltaics  |  例如：钠离子电池在电网储能中的商业化",
                    lines=2,
                    scale=10,
                )
                clear_btn = gr.Button(
                    "✕", variant="secondary", scale=0, min_width=48,
                    elem_classes=["clear-icon-btn"],
                )

            submit_btn = gr.Button("▶  Run Analysis", variant="primary")

            progress_output = gr.HTML()
            score_output    = gr.HTML()
            report_output   = gr.Markdown(elem_classes=["report-md"])
            with gr.Row():
                download_md  = gr.File(label="Download Report (.md)", visible=False, scale=1)
                download_pdf = gr.File(label="Download Report (.pdf)", visible=False, scale=1)

            submit_btn.click(
                fn=run_analysis,
                inputs=topic_input,
                outputs=[progress_output, score_output, report_output, download_md, download_pdf],
            )
            clear_btn.click(
                fn=lambda: ("", "", "", "",
                            gr.update(value=None, visible=False),
                            gr.update(value=None, visible=False)),
                outputs=[topic_input, progress_output, score_output, report_output,
                         download_md, download_pdf],
            )

        # ── History tab ───────────────────────────────────────────────────
        with gr.Tab("History"):
            with gr.Row():
                gr.HTML('<p style="font-size:13px;color:#9a9a9a;margin:6px 0;">Past runs — paste a Run ID below to reload any report</p>')
                refresh_btn = gr.Button("↻  Refresh", variant="secondary", scale=0, min_width=110)

            history_output = gr.HTML(value=_render_history_html())
            refresh_btn.click(fn=_render_history_html, outputs=history_output)

            with gr.Row():
                run_id_input = gr.Textbox(
                    label="Run ID",
                    placeholder="20260703T045159Z-6288f6252a",
                    scale=5,
                )
                load_btn = gr.Button("Load", variant="primary", scale=1)
            loaded_score  = gr.HTML()
            loaded_report = gr.Markdown(elem_classes=["report-md"])
            load_btn.click(fn=_load_run, inputs=run_id_input, outputs=[loaded_score, loaded_report])


if __name__ == "__main__":
    demo.launch(css=_CSS, theme=_theme)
