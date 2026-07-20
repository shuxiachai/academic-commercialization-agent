"""html_scorecard — Score card HTML rendering helpers."""

import html
import json
import math
import re

from ui.i18n import _scorecard_strings


def _score_color(overall: int) -> tuple[str, str]:
    if overall >= 80:
        return "#16a34a", "EXCELLENT"
    elif overall >= 60:
        return "#2563eb", "GOOD"
    elif overall >= 40:
        return "#d97706", "MODERATE"
    else:
        return "#dc2626", "WEAK"


def _metric_color(pct: int) -> str:
    if pct >= 75:
        return "#16a34a"
    elif pct >= 50:
        return "#2563eb"
    elif pct >= 30:
        return "#d97706"
    else:
        return "#dc2626"


_CHIP_ONCLICK = (
    "(function(id){"
    "var d=document.getElementById('_acadSrcData');"
    "if(!d)return;"
    "var idx;try{idx=JSON.parse(d.textContent);}catch(e){return;}"
    "var s=idx[id]||{};"
    "var panel=document.getElementById('_acadSrcPanel');"
    "var content=document.getElementById('_acadSrcContent');"
    "if(!panel||!content)return;"
    "function esc(x){return String(x||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}"
    "var h='<div style=\"font-size:12px;color:#e5e5e5;font-weight:600;margin-bottom:8px;\">'+esc(s.title||'—')+'</div>';"
    "h+='<div style=\"display:flex;gap:12px;flex-wrap:wrap;font-size:11px;color:#777777;margin-bottom:8px;\">';"
    "h+='<span style=\"font-weight:700;color:#9a9a9a;\">'+id+'</span>';"
    "if(s.source_type)h+='<span>'+esc(s.source_type)+'</span>';"
    "if(s.published_date)h+='<span>'+esc(String(s.published_date||'').slice(0,10))+'</span>';"
    "if(s.credibility_tier)h+='<span>✓ '+esc(s.credibility_tier)+'</span>';"
    "if(s.citation_count!=null)h+='<span>'+s.citation_count+' citations</span>';"
    "h+='</div>';"
    "if(s.url)h+='<div style=\"margin-bottom:8px;\"><a href=\"'+esc(s.url)+'\" target=\"_blank\" style=\"font-size:11px;color:#60a5fa;word-break:break-all;\">'+esc(s.url)+'</a></div>';"
    "if(s.evidence_summary)h+='<div style=\"font-size:11px;color:#9a9a9a;line-height:1.6;padding:8px;background:#0a0a0a;border-radius:6px;\">'+esc(String(s.evidence_summary||'').slice(0,350))+'</div>';"
    "content.innerHTML=h;"
    "panel.style.display='block';"
    "})('{ID}')"
)


def _source_id_chips(ids: list) -> str:
    if not ids:
        return ""
    _kd = "if(event.key==='Enter'||event.key===' '){event.preventDefault();this.click();}"
    chips = "".join(
        f'<span role="button" tabindex="0" '
        f'style="display:inline-block;background:#222222;border:1px solid #333333;'
        f'color:#9a9a9a;font-size:9px;font-family:ui-monospace,monospace;font-weight:600;'
        f'padding:1px 5px;border-radius:4px;margin:1px 1px 0;cursor:pointer;" '
        f'onclick="{html.escape(_CHIP_ONCLICK.replace("{ID}", str(sid)))}" '
        f'onkeydown="{html.escape(_kd)}" '
        f'aria-label="View source {html.escape(str(sid))}" '
        f'title="Click to view source details">'
        f'{html.escape(str(sid))}</span>'
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


def _radar_svg(trl: float, mrl: float, pat: float, mkt: float, evi: float, color: str = "#6366f1") -> str:
    """Generate an inline SVG pentagon radar chart for the five scoring dimensions."""
    cx, cy, r = 100, 100, 68
    vals   = [trl / 9, mrl / 10, pat / 5, mkt / 5, evi / 5]
    labels = ["TRL", "MRL", "Patent", "Market", "Evidence"]
    raws   = [f"{trl:.1f}/9", f"{mrl:.1f}/10", f"{pat:.1f}/5", f"{mkt:.1f}/5", f"{evi:.1f}/5"]
    angles = [-math.pi / 2 + i * 2 * math.pi / 5 for i in range(5)]

    def pt(a: float, radius: float) -> tuple[float, float]:
        return cx + radius * math.cos(a), cy + radius * math.sin(a)

    parts: list[str] = []

    # Grid rings (25 / 50 / 75 / 100 %)
    for frac in (0.25, 0.5, 0.75, 1.0):
        pts = " ".join(f"{pt(a, r * frac)[0]:.1f},{pt(a, r * frac)[1]:.1f}" for a in angles)
        lw = "1" if frac == 1.0 else "0.6"
        parts.append(f'<polygon points="{pts}" fill="none" stroke="#3a3a3a" stroke-width="{lw}"/>')

    # Spokes
    for a in angles:
        x, y = pt(a, r)
        parts.append(f'<line x1="{cx}" y1="{cy}" x2="{x:.1f}" y2="{y:.1f}" stroke="#3a3a3a" stroke-width="0.6"/>')

    # Data polygon
    dpts = " ".join(
        f"{pt(angles[i], r * max(v, 0.02))[0]:.1f},{pt(angles[i], r * max(v, 0.02))[1]:.1f}"
        for i, v in enumerate(vals)
    )
    parts.append(f'<polygon points="{dpts}" fill="{color}" fill-opacity="0.18" stroke="{color}" stroke-width="1.5"/>')

    # Dots + labels + raw values (merged to share title tooltip on dots)
    for i, (v, lbl, raw, a) in enumerate(zip(vals, labels, raws, angles)):
        x, y = pt(a, r * max(v, 0.02))
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}" style="cursor:pointer;">'
            f'<title>{lbl}: {raw}</title>'
            f'</circle>'
        )
        lx, ly = pt(a, r + 18)
        anchor = "middle"
        if lx < cx - 8:
            anchor = "end"
        elif lx > cx + 8:
            anchor = "start"
        parts.append(
            f'<text x="{lx:.1f}" y="{ly:.1f}" text-anchor="{anchor}" '
            f'fill="#888888" font-size="9" font-family="system-ui,sans-serif">{lbl}</text>'
        )
        parts.append(
            f'<text x="{lx:.1f}" y="{ly + 11:.1f}" text-anchor="{anchor}" '
            f'fill="{color}" font-size="8" font-family="ui-monospace,monospace">{raw}</text>'
        )

    _svg_title = "Commercialization radar chart"
    _svg_desc = (
        f"TRL {trl:.1f}/9, MRL {mrl:.1f}/10, Patent {pat:.1f}/5, "
        f"Market {mkt:.1f}/5, Evidence {evi:.1f}/5"
    )
    return (
        '<svg viewBox="0 0 200 200" width="190" height="190" '
        'xmlns="http://www.w3.org/2000/svg" role="img" '
        f'aria-label="{_svg_title}" '
        'style="overflow:visible;display:block;">'
        f'<title>{_svg_title}</title>'
        f'<desc>{_svg_desc}</desc>'
        + "".join(parts)
        + "</svg>"
    )


_PROFILE_LABELS: dict[str, str] = {
    "industrial":      "Industrial",
    "biomedical":      "Biomedical",
    "material_science": "Material Science",
    "clean_tech":      "Clean Tech",
    "software_ai":     "Software / AI",
}


def _render_score_html(
    scores_json: str,
    topic: str,
    output_language: str = "English",
    weight_profile: str = "industrial",
    sources_index: dict | None = None,
) -> str:
    try:
        s = json.loads(scores_json)
    except (json.JSONDecodeError, TypeError):
        return ""

    trl = s.get("trl_score") or 0
    mrl = s.get("mrl_score") or 0
    pat = s.get("patent_strength") or 0
    mkt = s.get("market_accessibility") or 0
    evi = s.get("evidence_confidence") or 0
    overall = s.get("overall_score") or 0
    scoring_rationale_raw = s.get("scoring_rationale", "")

    # auto_corrected: new runs have dedicated boolean; old runs have legacy prefix.
    if s.get("auto_corrected") is True:
        autocorrect_note = True
        scoring_rationale = scoring_rationale_raw
    else:
        _autocorrect_match = re.match(r"^\[Auto-corrected:[^\]]+\]\s*", scoring_rationale_raw)
        autocorrect_note = bool(_autocorrect_match)
        scoring_rationale = scoring_rationale_raw[_autocorrect_match.end():] if _autocorrect_match else scoring_rationale_raw

    # score_formula: new runs have dedicated field; old runs embedded it as "[Verified ...]".
    score_formula = s.get("score_formula", "")
    if not score_formula:
        _vf = re.search(r"\s*\[Verified \([^)]+\):[^\]]+\]", scoring_rationale)
        if _vf:
            score_formula = _vf.group(0).strip()[1:-1]  # strip outer [ ]
            scoring_rationale = scoring_rationale[: _vf.start()].rstrip()
    risks = s.get("key_risks", [])
    opps = s.get("key_opportunities", [])
    trl_ids  = s.get("trl_source_ids", [])
    mrl_ids  = s.get("mrl_source_ids", [])
    pat_ids  = s.get("patent_source_ids", [])
    mkt_ids  = s.get("market_source_ids", [])
    evi_ids  = s.get("evidence_source_ids", [])

    color, badge_en = _score_color(overall)
    t = _scorecard_strings(output_language)
    badge = t.get(badge_en, badge_en)
    trl_pct = round(trl / 9 * 100)
    mrl_pct = round(mrl / 10 * 100)
    pat_pct = round(pat / 5 * 100)
    mkt_pct = round(mkt / 5 * 100)
    evi_pct = round(evi / 5 * 100)

    profile_label = _PROFILE_LABELS.get(weight_profile, weight_profile.replace("_", " ").title())
    radar_svg = _radar_svg(trl, mrl, pat, mkt, evi, color)

    risks_block = "".join(_bullet_item(str(r), "#dc2626") for r in risks)
    opps_block  = "".join(_bullet_item(str(o), "#16a34a") for o in opps)

    risks_col = (
        f'<div style="flex:1;background:#2d1515;border:1px solid #7f1d1d;'
        f'border-radius:8px;padding:16px;">'
        f'<div style="font-size:12px;font-weight:700;color:#fca5a5;'
        f'letter-spacing:0.05em;text-transform:uppercase;margin-bottom:10px;">'
        f'&#x26A0; {html.escape(t["risks"])}</div>'
        f'{risks_block}'
        f'</div>'
    ) if risks else ""

    opps_col = (
        f'<div style="flex:1;background:#0f2d1a;border:1px solid #14532d;'
        f'border-radius:8px;padding:16px;">'
        f'<div style="font-size:12px;font-weight:700;color:#86efac;'
        f'letter-spacing:0.05em;text-transform:uppercase;margin-bottom:10px;">'
        f'&#x2726; {html.escape(t["opps"])}</div>'
        f'{opps_block}'
        f'</div>'
    ) if opps else ""

    risks_opps_row = (
        f'<div style="display:flex;gap:16px;margin-top:20px;">'
        f'{risks_col}{opps_col}'
        f'</div>'
    ) if (risks or opps) else ""

    _rtl_attrs = ' dir="rtl" lang="ar"' if output_language == "Arabic" else ""
    return (
        f'<div{_rtl_attrs} style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;'
        f'background:#1a1a1a;border:1px solid #2d2d2d;'
        f'border-left:4px solid {color};border-radius:10px;'
        f'padding:24px;margin-bottom:16px;">'

        # Hero row: score + badges | radar chart | rationale
        f'<div style="display:flex;align-items:stretch;gap:24px;margin-bottom:24px;">'

        # Left: score number + readiness badge + profile badge
        f'<div style="text-align:center;min-width:108px;">'
        f'<div style="font-size:72px;font-weight:800;color:{color};line-height:0.9;">{overall:.1f}</div>'
        f'<div style="font-size:11px;color:#777777;margin-top:6px;">{html.escape(t["out_of"])}</div>'
        f'<div style="display:inline-block;margin-top:10px;padding:4px 14px;'
        f'border-radius:20px;background:{color};color:#ffffff;'
        f'font-size:12px;font-weight:700;letter-spacing:0.04em;">{badge}</div>'
        f'<div style="display:inline-block;margin-top:8px;padding:3px 10px;'
        f'border-radius:20px;border:1px solid #3d3d3d;background:#242424;color:#aaaaaa;'
        f'font-size:10px;font-weight:600;letter-spacing:0.05em;white-space:nowrap;">'
        f'{html.escape(profile_label)}</div>'
        f'</div>'

        # Middle: radar chart
        f'<div style="display:flex;align-items:center;justify-content:center;'
        f'padding:0 4px;">'
        f'{radar_svg}'
        f'</div>'

        # Right: scoring rationale
        f'<div style="flex:1;border-left:1px solid #2d2d2d;padding-left:20px;'
        f'display:flex;flex-direction:column;justify-content:center;">'
        f'<div style="font-size:10px;font-weight:700;color:#777777;'
        f'text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px;">'
        f'{html.escape(t["formula"])}'
        + (f'<span style="margin-left:8px;font-size:9px;font-weight:600;'
           f'background:#292912;border:1px solid #52520a;color:#a3a30a;'
           f'padding:1px 6px;border-radius:4px;text-transform:none;letter-spacing:0;">'
           f'auto-corrected</span>' if autocorrect_note else "") +
        f'</div>'
        + (f'<div style="font-size:10px;color:#555555;font-family:ui-monospace,monospace;'
           f'margin-bottom:6px;padding:3px 8px;background:#111111;border-radius:4px;'
           f'overflow-x:auto;white-space:nowrap;">'
           f'{html.escape(score_formula)}</div>' if score_formula else "") +
        f'<div style="font-size:12px;color:#d4d4d4;background:#141414;'
        f'border:1px solid #2d2d2d;border-radius:6px;padding:10px 14px;'
        f'font-family:ui-monospace,monospace;line-height:1.6;">'
        f'{html.escape(scoring_rationale)}</div>'
        f'</div>'
        f'</div>'

        # KPI tiles
        f'<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:10px;margin-bottom:20px;">'
        f'{_kpi_tile("TRL", trl, 9, t["trl_sub"], trl_pct, trl_ids)}'
        f'{_kpi_tile("MRL", mrl, 10, t["mrl_sub"], mrl_pct, mrl_ids)}'
        f'{_kpi_tile("IP", pat, 5, t["ip_sub"], pat_pct, pat_ids)}'
        f'{_kpi_tile(t["kpi_market"], mkt, 5, t["mkt_sub"], mkt_pct, mkt_ids)}'
        f'{_kpi_tile(t["kpi_evidence"], evi, 5, t["evi_sub"], evi_pct, evi_ids)}'
        f'</div>'

        # Bars
        f'<div style="background:#141414;border:1px solid #2d2d2d;border-radius:8px;padding:18px 20px;">'
        f'{_bar_row(t["bar_trl"], trl, 9, trl_pct)}'
        f'{_bar_row(t["bar_mrl"], mrl, 10, mrl_pct)}'
        f'{_bar_row(t["bar_ip"], pat, 5, pat_pct)}'
        f'{_bar_row(t["bar_mkt"], mkt, 5, mkt_pct)}'
        f'<div style="margin-bottom:0;">'
        f'{_bar_row(t["bar_evi"], evi, 5, evi_pct)}'
        f'</div>'
        f'</div>'

        f'{risks_opps_row}'
        f'</div>'
    )
