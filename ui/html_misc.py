"""html_misc — Header, PDF description, paper divider, and reviewer notes HTML."""

import html
import re

from ui.i18n import _scorecard_strings


def _header_html(t: dict) -> str:
    return (
        '<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;'
        'padding:24px 0 18px; border-bottom:1px solid #2d2d2d; margin-bottom:8px;">'
        '<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">'
        f'<h1 style="font-size:21px;font-weight:800;color:#f5f5f5;letter-spacing:-0.3px;margin:0;">'
        f'{html.escape(t["header_title"])}'
        '</h1>'
        '<span style="background:#1e3a5f;color:#60a5fa;font-size:10px;font-weight:800;'
        'padding:3px 9px;border-radius:10px;letter-spacing:0.06em;text-transform:uppercase;">BETA</span>'
        '</div>'
        f'<p style="font-size:13px;color:#9a9a9a;line-height:1.6;max-width:660px;margin:0 0 12px;">'
        f'{t["header_desc"]}'
        '</p>'
        '<div style="display:flex;gap:6px;flex-wrap:wrap;">'
        f'<span style="background:#1a1a1a;border:1px solid #2d2d2d;color:#9a9a9a;font-size:11px;'
        f'font-weight:600;padding:3px 10px;border-radius:20px;">{html.escape(t["chip_sources"])}</span>'
        f'<span style="background:#1a1a1a;border:1px solid #2d2d2d;color:#9a9a9a;font-size:11px;'
        f'font-weight:600;padding:3px 10px;border-radius:20px;">{html.escape(t["chip_agents"])}</span>'
        f'<span style="background:#1a1a1a;border:1px solid #2d2d2d;color:#9a9a9a;font-size:11px;'
        f'font-weight:600;padding:3px 10px;border-radius:20px;">{html.escape(t["chip_metrics"])}</span>'
        f'<span style="background:#1a1a1a;border:1px solid #2d2d2d;color:#9a9a9a;font-size:11px;'
        f'font-weight:600;padding:3px 10px;border-radius:20px;">{html.escape(t["chip_citations"])}</span>'
        '</div>'
        '</div>'
    )


def _pdf_desc_html(t: dict) -> str:
    return (
        f'<p style="font-size:12px;color:#6b7280;margin:2px 0 12px;">'
        f'{t["pdf_desc"]}'
        '</p>'
    )


def _render_reviewer_notes_html(run_dir, output_language: str = "English") -> str:
    """Return a collapsible HTML block with Agent 5's reviewer notes, or '' if absent."""
    notes_path = run_dir / "reviewer_notes.md"
    if not notes_path.exists():
        return ""
    try:
        raw = notes_path.read_text(encoding="utf-8").strip()
        if not raw:
            return ""
        notes_label = _scorecard_strings(output_language).get("reviewer_notes", "Reviewer Notes")
        # Strip the heading line if present
        raw = re.sub(r"(?im)^##\s+Reviewer Notes\s*\n?", "", raw).strip()
        # Minimal markdown → HTML: bold, numbered list items, paragraphs
        lines_html: list[str] = []
        for line in raw.splitlines():
            line = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", line)
            if re.match(r"^\d+\.", line):
                lines_html.append(
                    f'<div style="margin-bottom:8px;padding-left:4px;">{line}</div>'
                )
            elif line.strip() == "":
                lines_html.append('<div style="margin-bottom:6px;"></div>')
            else:
                lines_html.append(
                    f'<div style="margin-bottom:4px;color:#a3a3a3;">{line}</div>'
                )
        return (
            '<details style="margin-top:16px;border:1px solid #2d2d2d;border-radius:8px;'
            'background:#141414;padding:14px 18px;font-family:system-ui,sans-serif;">'
            '<summary style="cursor:pointer;font-size:11px;font-weight:700;color:#6b7280;'
            'text-transform:uppercase;letter-spacing:0.07em;user-select:none;">'
            f'&#x270E; Agent 5 — {html.escape(notes_label)}</summary>'
            '<div style="margin-top:12px;font-size:12px;color:#d4d4d4;line-height:1.7;">'
            + "".join(lines_html)
            + "</div></details>"
        )
    except Exception:
        return ""


def _paper_divider_html(label: str) -> str:
    return f'<div class="paper-divider"><span>{label}</span></div>'
