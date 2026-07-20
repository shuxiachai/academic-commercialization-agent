"""html_progress — Progress step HTML rendering + stage constants."""

import html
import json
from pathlib import Path

from ui.i18n import _scorecard_strings, _ui
from academic_agent.run_output import DEFAULT_OUTPUT_ROOT

# ---------------------------------------------------------------------------
# Stage / spinner constants (re-exported for runner.py)
# ---------------------------------------------------------------------------

TASK_STAGE_LABELS = [
    "Phase 1 — Evidence Collection (Academic · Patent · Market)",
    "Agent 4 — Report Writing",
    "Agent 5 — Quality Review & Citation Check",
    "Agent 6 — Commercialization Scoring",
]
_STAGE_INITIAL = "Source Collection & Validation"
SPINNER = ["|", "/", "-", "\\"]

# These were defined at the top of app.py but never called externally; kept here for completeness.
_AGENT_SHORT_NAMES = ["Academic", "Patent", "Market", "Writer", "Reviewer", "Scorer"]  # unused
_AGENT_COLORS      = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ec4899", "#06b6d4"]  # unused

# ---------------------------------------------------------------------------
# Phase 1 agent definitions
# ---------------------------------------------------------------------------

_PHASE1_AGENTS = (
    ("Agent 1 — Academic Literature Analysis", "#3b82f6", "#1e3a5f"),
    ("Agent 2 — Patent Landscape Analysis",    "#8b5cf6", "#2e1065"),
    ("Agent 3 — Market Intelligence Analysis", "#10b981", "#052e16"),
)


def _progress_dot(state: str, spin: str) -> str:
    """Return a styled indicator dot for a progress step."""
    if state == "done":
        # Green filled circle with SVG checkmark; pop-in animation on first render
        return (
            '<div style="width:18px;height:18px;border-radius:50%;background:#16a34a;'
            'display:flex;align-items:center;justify-content:center;flex-shrink:0;'
            'animation:_dotPop 0.22s ease-out both;">'
            '<svg width="10" height="10" viewBox="0 0 10 10">'
            '<polyline points="1.5,5 4,7.5 8.5,2.5" stroke="#fff" stroke-width="1.8" '
            'fill="none" stroke-linecap="round" stroke-linejoin="round"/></svg></div>'
        )
    if state == "active":
        # Blue ring with rotating ASCII spinner inside
        return (
            '<div style="width:18px;height:18px;border-radius:50%;background:#1e3a5f;'
            'border:2px solid #3b82f6;display:flex;align-items:center;justify-content:center;'
            'flex-shrink:0;font-size:9px;color:#60a5fa;font-family:monospace;'
            'font-weight:700;line-height:1;">'
            f'{spin}</div>'
        )
    # Future: hollow gray ring
    return (
        '<div style="width:18px;height:18px;border-radius:50%;'
        'border:2px solid #374151;flex-shrink:0;"></div>'
    )


def _render_progress_html(
    stage: str,
    elapsed: int,
    run_id: str,
    spin: str,
    output_language: str = "English",
    source_counts: dict | None = None,
) -> str:
    t = _scorecard_strings(output_language)
    u = _ui(output_language)
    all_stages = [_STAGE_INITIAL] + TASK_STAGE_LABELS
    _stage_en_keys = ["stage_init", "stage_evidence", "stage_writing", "stage_review", "stage_scoring"]
    _stage_display = {en: u.get(key, en) for en, key in zip(all_stages, _stage_en_keys)}
    _phase1_labels = [
        u.get("agent_academic", _PHASE1_AGENTS[0][0]),
        u.get("agent_patent",   _PHASE1_AGENTS[1][0]),
        u.get("agent_market",   _PHASE1_AGENTS[2][0]),
    ]
    try:
        current_idx = all_stages.index(stage)
    except ValueError:
        current_idx = 0

    # Progress bar percentage: 0% at start, 100% when last stage is active
    n = len(all_stages) - 1
    pct = round(current_idx / n * 100) if n > 0 else 0

    is_phase1 = TASK_STAGE_LABELS[0] if TASK_STAGE_LABELS else ""

    items = []
    for i, label in enumerate(all_stages):
        if i < current_idx:
            state, text_style = "done", "font-size:13px;color:#4b5563;"
        elif i == current_idx:
            state, text_style = "active", "font-size:13px;color:#f5f5f5;font-weight:600;"
        else:
            state, text_style = "future", "font-size:13px;color:#374151;"

        # Phase 1: expand into 3 individual agent rows when active or done
        if label == is_phase1 and state in ("active", "done"):
            # Detect which parallel agents have already sent a "finish" event
            phase1_done: set[int] = set()
            if state == "active":
                try:
                    _raw = (DEFAULT_OUTPUT_ROOT / run_id / "steps.jsonl").read_text(encoding="utf-8")
                    for _ln in _raw.splitlines():
                        try:
                            _e = json.loads(_ln)
                            if _e.get("type") == "finish":
                                _idx = int(_e.get("agent_idx", -1))
                                if 0 <= _idx <= 2:
                                    phase1_done.add(_idx)
                        except Exception:
                            pass
                except Exception:
                    pass

            # Source counts summary line (shown once Phase 1 starts)
            if source_counts:
                ac = source_counts.get("academic", 0)
                pa = source_counts.get("patent", 0)
                mk = source_counts.get("market", 0)
                ac_c = "#f59e0b" if ac < 3 else "#6b7280"
                pa_c = "#f59e0b" if pa < 2 else "#6b7280"
                mk_c = "#f59e0b" if mk < 2 else "#6b7280"
                items.append(
                    f'<div style="margin-bottom:10px;padding-left:28px;'
                    f'animation:_agFade 0.2s ease-out both;">'
                    f'<span style="font-size:11px;color:#4b5563;">{html.escape(u.get("sources_prefix", "Sources: "))}</span>'
                    f'<span style="font-size:11px;color:{ac_c};">{ac} academic</span>'
                    f'<span style="font-size:11px;color:#374151;"> · </span>'
                    f'<span style="font-size:11px;color:{pa_c};">{pa} patent</span>'
                    f'<span style="font-size:11px;color:#374151;"> · </span>'
                    f'<span style="font-size:11px;color:{mk_c};">{mk} market</span>'
                    f'</div>'
                )

            for j, (agent_name, color, bg) in enumerate(_PHASE1_AGENTS):
                agent_done = state == "done" or j in phase1_done
                if agent_done:
                    dot = _progress_dot("done", spin)
                    row_style = "font-size:12px;color:#4b5563;"
                else:
                    dot = (
                        f'<div style="width:18px;height:18px;border-radius:50%;background:{bg};'
                        f'border:2px solid {color};display:flex;align-items:center;'
                        f'justify-content:center;flex-shrink:0;font-size:9px;color:{color};'
                        f'font-family:monospace;font-weight:700;line-height:1;">{spin}</div>'
                    )
                    row_style = f"font-size:12px;color:{color};font-weight:600;"
                items.append(
                    f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;'
                    f'animation:_agFade 0.22s ease-out both;animation-delay:{j * 65}ms;">'
                    f'{dot}'
                    f'<div style="{row_style}">{html.escape(_phase1_labels[j])}</div>'
                    f'</div>'
                )
            continue

        dot = _progress_dot(state, spin)
        items.append(
            f'<div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:12px;">'
            f'{dot}'
            f'<div style="padding-top:1px;">'
            f'<div style="{text_style}">{html.escape(_stage_display.get(label, label))}</div>'
            f'</div>'
            f'</div>'
        )

    # Connector lines between steps (thin vertical line on left column)
    # Achieved by wrapping steps in a relative container with a left border
    steps_html = (
        f'<div style="padding-left:9px;border-left:2px solid #27272a;margin-left:0;">'
        + "".join(items)
        + "</div>"
    )

    mins, secs = divmod(elapsed, 60)
    elapsed_str = f"{mins}m {secs:02d}s" if mins else f"{secs}s"

    remaining_str = ""
    if 0 < pct < 100 and elapsed >= 5:
        total_est = elapsed / pct * 100
        remaining = int(total_est - elapsed)
        if remaining > 0:
            r_mins, r_secs = divmod(remaining, 60)
            remaining_str = f" · ~{r_mins}m {r_secs:02d}s left" if r_mins else f" · ~{r_secs}s left"

    return (
        # Keyframe definitions (scoped by unique names; browser dedupes across redraws)
        '<style>'
        '@keyframes _agFade{from{opacity:.55;transform:translateX(-5px)}to{opacity:1;transform:translateX(0)}}'
        '@keyframes _dotPop{0%{transform:scale(.55);opacity:0}65%{transform:scale(1.18)}100%{transform:scale(1);opacity:1}}'
        '@keyframes _logSlide{from{opacity:.4;transform:translateY(7px)}to{opacity:1;transform:translateY(0)}}'
        '@keyframes _bluePulse{0%,100%{box-shadow:0 0 0 3px #1e3a5f}50%{box-shadow:0 0 0 6px #1e3a5f66}}'
        '</style>'

        f'<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;'
        f'background:#1a1a1a;border:1px solid #2d2d2d;border-left:4px solid #3b82f6;'
        f'border-radius:10px;padding:20px 24px;">'

        # Header row
        f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">'
        f'<div style="width:8px;height:8px;border-radius:50%;background:#3b82f6;'
        f'box-shadow:0 0 0 3px #1e3a5f;flex-shrink:0;animation:_bluePulse 2s ease infinite;"></div>'
        f'<span style="font-size:13px;font-weight:600;color:#f5f5f5;">{t["progress"]}</span>'
        f'<span style="margin-left:auto;font-size:12px;color:#6b7280;'
        f'font-variant-numeric:tabular-nums;">{elapsed_str}'
        f'<span style="color:#4b5563;">{html.escape(remaining_str)}</span></span>'
        f'</div>'

        # Progress bar (width transition already present)
        f'<div style="background:#27272a;border-radius:4px;height:4px;margin-bottom:20px;overflow:hidden;">'
        f'<div style="height:100%;width:{pct}%;'
        f'background:linear-gradient(90deg,#3b82f6 0%,#6366f1 100%);'
        f'border-radius:4px;transition:width 0.5s ease;min-width:{4 if pct > 0 else 0}px;"></div>'
        f'</div>'

        # Step list
        f'{steps_html}'

        # Footer
        f'<div style="margin-top:8px;padding-top:12px;border-top:1px solid #202020;">'
        f'<span style="font-size:11px;color:#3f3f46;font-family:ui-monospace,monospace;">'
        f'Run ID: {html.escape(run_id)}</span>'
        f'</div>'
        f'</div>'
    )
