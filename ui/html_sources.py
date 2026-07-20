"""html_sources — Source list, warning banner, and detail panel HTML."""

import html
import json
from datetime import date
from pathlib import Path

from ui.i18n import _ui, _warning_strings


def _render_source_preview_html(run_dir: Path, ui_lang: str = "English") -> str:
    """Show collected source titles once validated_sources.json is available."""
    src_path = run_dir / "validated_sources.json"
    if not src_path.exists():
        return ""
    try:
        data = json.loads(src_path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    u = _ui(ui_lang)
    sections = [
        ("academic_sources",  "A", "#3b82f6", u["src_academic"]),
        ("patent_sources",    "P", "#8b5cf6", u["src_patent"]),
        ("market_sources",    "M", "#10b981", u["src_market"]),
    ]

    rows_html = ""
    for key, prefix, color, label in sections:
        sources = data.get(key, [])
        if not sources:
            continue
        rows_html += (
            f'<div style="font-size:10px;font-weight:700;color:{color};letter-spacing:0.06em;'
            f'text-transform:uppercase;margin:10px 0 4px;">{html.escape(label)} ({len(sources)})</div>'
        )
        for i, src in enumerate(sources, 1):
            sid = f"{prefix}{i}"
            title = str(src.get("title") or "—")[:100]
            rows_html += (
                f'<div style="display:flex;gap:8px;align-items:baseline;margin-bottom:3px;">'
                f'<span style="font-size:10px;font-weight:700;color:{color}88;'
                f'font-family:ui-monospace,monospace;flex-shrink:0;width:22px;">{sid}</span>'
                f'<span style="font-size:11px;color:#9a9a9a;line-height:1.4;">'
                f'{html.escape(title)}{"…" if len(str(src.get("title") or "")) > 100 else ""}</span>'
                f'</div>'
            )

    if not rows_html:
        return ""

    return (
        f'<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;'
        f'background:#0a0a0a;border:1px solid #1a1a1a;border-radius:8px;'
        f'padding:12px 14px;max-height:280px;overflow-y:auto;margin-top:10px;">'
        f'<div style="font-size:10px;font-weight:700;color:#444444;letter-spacing:0.08em;'
        f'text-transform:uppercase;margin-bottom:6px;">{html.escape(u["src_header"])}</div>'
        f'{rows_html}'
        f'</div>'
    )


def _date_is_before(date_str: str, cutoff: date) -> bool:
    """Return True if date_str (ISO 8601) parses to a date before cutoff."""
    try:
        return date.fromisoformat(str(date_str)[:10]) < cutoff
    except (ValueError, TypeError):
        return False


def _render_source_warning_html(run_dir: Path, output_language: str = "English") -> str:
    """Return a warning banner if any domain has fewer sources than recommended."""
    try:
        w = _warning_strings(output_language)
        data = json.loads((run_dir / "validated_sources.json").read_text(encoding="utf-8"))
        ac = len(data.get("academic_sources", []))
        pa = len(data.get("patent_sources", []))
        mk = len(data.get("market_sources", []))
        warnings: list[str] = []
        if ac < 3:
            warnings.append(w["ac_few"].format(n=ac, pl="s" if ac != 1 else ""))
        if pa < 2:
            warnings.append(w["pa_few"].format(n=pa, pl="s" if pa != 1 else ""))
        if mk < 2:
            warnings.append(w["mk_few"].format(n=mk, pl="s" if mk != 1 else ""))
        # Staleness check: flag if ≥50% of market sources are older than 3 years or undated.
        # High-credibility institutional sources (government, research institutes) are
        # exempt from the "undated = stale" treatment — their content ages more slowly
        # and their omission of a date rarely signals outdated intelligence.
        market_sources = data.get("market_sources", [])
        if market_sources:
            cutoff = date.today().replace(year=date.today().year - 3)
            stale = sum(
                1 for ms in market_sources
                if ms.get("credibility_tier") != "high"
                and (
                    not ms.get("published_date")
                    or _date_is_before(ms["published_date"], cutoff)
                )
            )
            if stale >= max(1, len(market_sources) // 2):
                warnings.append(
                    w["mk_stale"].format(stale=stale, total=len(market_sources))
                )
        # Patent age check: flag patents filed 15+ years ago that may have expired.
        # Standard utility patent protection is 20 years from filing; at 15 years,
        # the remaining term is short enough that the landscape analysis may be
        # materially different once those patents lapse.
        patent_sources = data.get("patent_sources", [])
        if patent_sources:
            pat_age_cutoff = date.today().replace(year=date.today().year - 15)
            old_patents = sum(
                1 for p in patent_sources
                if p.get("published_date") and _date_is_before(p["published_date"], pat_age_cutoff)
            )
            if old_patents > 0:
                warnings.append(
                    w["pat_old"].format(
                        n=old_patents, total=len(patent_sources),
                        pl="s" if old_patents != 1 else "",
                    )
                )

        # Academic age check: warn when the oldest source is 5+ years old, since
        # fast-moving fields (materials, biotech) can diverge significantly from
        # a 2019 paper's conclusions.  Only surfaces the single oldest outlier
        # rather than a percentage so the warning stays specific and actionable.
        academic_sources = data.get("academic_sources", [])
        if academic_sources:
            ac_age_cutoff = date.today().replace(year=date.today().year - 5)
            old_ac = [
                (s["published_date"], s.get("title", ""))
                for s in academic_sources
                if s.get("published_date") and _date_is_before(s["published_date"], ac_age_cutoff)
            ]
            if old_ac:
                oldest_date, oldest_title = min(old_ac, key=lambda x: x[0])
                oldest_year = str(oldest_date)[:4]
                short_title = oldest_title[:60] + ("…" if len(oldest_title) > 60 else "")
                warnings.append(
                    w["ac_old"].format(year=oldest_year, title=short_title)
                )

        if not warnings:
            return ""
        items_html = "".join(
            f'<div style="margin-bottom:3px;">{html.escape(w)}</div>' for w in warnings
        )
        _rtl = ' dir="rtl" lang="ar"' if output_language == "Arabic" else ""
        return (
            f'<div{_rtl} style="background:#1c1400;border:1px solid #713f12;border-radius:8px;'
            f'padding:10px 16px;margin-bottom:14px;font-size:12px;color:#fbbf24;'
            f'font-family:system-ui;">'
            f'<div style="font-weight:700;margin-bottom:4px;">{html.escape(w["title"])}</div>'
            f'{items_html}'
            f'<div style="font-size:11px;color:#b45309;margin-top:4px;">'
            f'{html.escape(w["footer"])}</div>'
            f'</div>'
        )
    except Exception:
        return ""


def _build_sources_index(run_dir: Path) -> dict:
    """Build {source_id → source_dict} from validated_sources.json."""
    try:
        data = json.loads((run_dir / "validated_sources.json").read_text(encoding="utf-8"))
        idx: dict = {}
        for prefix, key in [("A", "academic_sources"), ("P", "patent_sources"), ("M", "market_sources")]:
            for i, src in enumerate(data.get(key, []), 1):
                idx[f"{prefix}{i}"] = src
        return idx
    except Exception:
        return {}


def _src_detail_panel_html(sources_index: dict) -> str:
    """Hidden source-detail drawer; data stored in a <div> so onclick works after innerHTML update."""
    if not sources_index:
        return ""
    src_json = html.escape(json.dumps(sources_index, ensure_ascii=False, default=str))
    return (
        f'<div id="_acadSrcData" style="display:none">{src_json}</div>'
        '<div id="_acadSrcPanel" style="display:none;margin-top:12px;'
        'background:#141414;border:1px solid #2d2d2d;border-radius:8px;'
        'padding:14px 16px;position:relative;">'
        '<button onclick="document.getElementById(\'_acadSrcPanel\').style.display=\'none\';" '
        'style="position:absolute;top:8px;right:10px;background:none;border:none;'
        'color:#555555;font-size:16px;cursor:pointer;line-height:1;padding:0;" '
        'title="Close">✕</button>'
        '<div id="_acadSrcContent"></div>'
        '</div>'
    )
