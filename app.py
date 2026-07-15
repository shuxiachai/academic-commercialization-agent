import html
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")

import gradio as gr

from academic_agent.run_output import (
    DEFAULT_OUTPUT_ROOT,
    create_run_id,
)


TASK_STAGE_LABELS = [
    "Phase 1 — Evidence Collection (Academic · Patent · Market)",
    "Agent 4 — Report Writing",
    "Agent 5 — Quality Review & Citation Check",
    "Agent 6 — Commercialization Scoring",
]
_STAGE_INITIAL = "Source Collection & Validation"
SPINNER = ["|", "/", "-", "\\"]

_AGENT_SHORT_NAMES = ["Academic", "Patent", "Market", "Writer", "Reviewer", "Scorer"]
_AGENT_COLORS      = ["#3b82f6", "#8b5cf6", "#10b981", "#f59e0b", "#ec4899", "#06b6d4"]

# ---------------------------------------------------------------------------
# Live agent log renderer
# ---------------------------------------------------------------------------

def _render_source_preview_html(run_dir: Path) -> str:
    """Show collected source titles once validated_sources.json is available."""
    src_path = run_dir / "validated_sources.json"
    if not src_path.exists():
        return ""
    try:
        data = json.loads(src_path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    sections = [
        ("academic_sources",  "A", "#3b82f6", "Academic"),
        ("patent_sources",    "P", "#8b5cf6", "Patent"),
        ("market_sources",    "M", "#10b981", "Market"),
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
        f'text-transform:uppercase;margin-bottom:6px;">Collected Sources</div>'
        f'{rows_html}'
        f'</div>'
    )


# ---------------------------------------------------------------------------
# Score card helpers
# ---------------------------------------------------------------------------

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
    chips = "".join(
        f'<span style="display:inline-block;background:#222222;border:1px solid #333333;'
        f'color:#9a9a9a;font-size:9px;font-family:ui-monospace,monospace;font-weight:600;'
        f'padding:1px 5px;border-radius:4px;margin:1px 1px 0;cursor:pointer;" '
        f'onclick="{html.escape(_CHIP_ONCLICK.replace("{ID}", str(sid)))}" '
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


_SCORECARD_I18N: dict[str, dict[str, str]] = {
    "English": {
        "formula": "Scoring Formula", "out_of": "out of 100",
        "EXCELLENT": "Excellent", "GOOD": "Good", "MODERATE": "Moderate", "WEAK": "Early Stage",
        "risks": "Key Risks", "opps": "Key Opportunities",
        "trl_sub": "Tech Readiness", "mrl_sub": "Mfg Readiness",
        "ip_sub": "Patent Landscape", "mkt_sub": "Accessibility", "evi_sub": "Confidence",
        "bar_trl": "Technology Readiness", "bar_mrl": "Manufacturing Readiness",
        "bar_ip": "IP Landscape", "bar_mkt": "Market Accessibility", "bar_evi": "Evidence Confidence",
        "dl_md": "Download Report (.md)", "dl_pdf": "Download Report (.pdf)",
        "progress": "Analysis in progress",
        "err_failed": "✗ Analysis Failed", "err_run": "Run ID",
    },
    "Simplified Chinese": {
        "formula": "评分公式", "out_of": "满分 100",
        "EXCELLENT": "优秀", "GOOD": "良好", "MODERATE": "中等", "WEAK": "较弱",
        "risks": "主要风险", "opps": "主要机遇",
        "trl_sub": "技术成熟度", "mrl_sub": "制造成熟度",
        "ip_sub": "专利格局", "mkt_sub": "市场可及性", "evi_sub": "证据置信度",
        "bar_trl": "技术就绪度", "bar_mrl": "制造就绪度",
        "bar_ip": "专利格局", "bar_mkt": "市场可及性", "bar_evi": "证据置信度",
        "dl_md": "下载报告 (.md)", "dl_pdf": "下载报告 (.pdf)",
        "progress": "分析进行中",
        "err_failed": "✗ 分析失败", "err_run": "运行 ID",
    },
    "Traditional Chinese": {
        "formula": "評分公式", "out_of": "滿分 100",
        "EXCELLENT": "優秀", "GOOD": "良好", "MODERATE": "中等", "WEAK": "較弱",
        "risks": "主要風險", "opps": "主要機遇",
        "trl_sub": "技術成熟度", "mrl_sub": "製造成熟度",
        "ip_sub": "專利格局", "mkt_sub": "市場可及性", "evi_sub": "證據置信度",
        "bar_trl": "技術就緒度", "bar_mrl": "製造就緒度",
        "bar_ip": "專利格局", "bar_mkt": "市場可及性", "bar_evi": "證據置信度",
        "dl_md": "下載報告 (.md)", "dl_pdf": "下載報告 (.pdf)",
        "progress": "分析進行中",
        "err_failed": "✗ 分析失敗", "err_run": "執行 ID",
    },
    "Japanese": {
        "formula": "スコア計算式", "out_of": "100点満点",
        "EXCELLENT": "優秀", "GOOD": "良好", "MODERATE": "普通", "WEAK": "弱い",
        "risks": "主なリスク", "opps": "主な機会",
        "trl_sub": "技術成熟度", "mrl_sub": "製造成熟度",
        "ip_sub": "特許状況", "mkt_sub": "市場参入性", "evi_sub": "証拠の信頼性",
        "bar_trl": "技術準備レベル", "bar_mrl": "製造準備レベル",
        "bar_ip": "知財状況", "bar_mkt": "市場アクセス", "bar_evi": "証拠の信頼性",
        "dl_md": "レポートをダウンロード (.md)", "dl_pdf": "レポートをダウンロード (.pdf)",
        "progress": "分析中",
        "err_failed": "✗ 分析に失敗しました", "err_run": "実行 ID",
    },
    "Korean": {
        "formula": "점수 공식", "out_of": "100점 만점",
        "EXCELLENT": "우수", "GOOD": "양호", "MODERATE": "보통", "WEAK": "미흡",
        "risks": "주요 리스크", "opps": "주요 기회",
        "trl_sub": "기술 성숙도", "mrl_sub": "제조 성숙도",
        "ip_sub": "특허 현황", "mkt_sub": "시장 접근성", "evi_sub": "증거 신뢰도",
        "bar_trl": "기술 준비 수준", "bar_mrl": "제조 준비 수준",
        "bar_ip": "지식재산 현황", "bar_mkt": "시장 접근성", "bar_evi": "증거 신뢰도",
        "dl_md": "보고서 다운로드 (.md)", "dl_pdf": "보고서 다운로드 (.pdf)",
        "progress": "분석 중",
        "err_failed": "✗ 분석 실패", "err_run": "실행 ID",
    },
    "German": {
        "formula": "Bewertungsformel", "out_of": "von 100",
        "EXCELLENT": "AUSGEZEICHNET", "GOOD": "GUT", "MODERATE": "MÄSSIG", "WEAK": "SCHWACH",
        "risks": "Hauptrisiken", "opps": "Hauptchancen",
        "trl_sub": "Tech-Reife", "mrl_sub": "Fertigungs-Reife",
        "ip_sub": "Patentlandschaft", "mkt_sub": "Marktzugang", "evi_sub": "Belege",
        "bar_trl": "Technologiereife", "bar_mrl": "Fertigungsreife",
        "bar_ip": "IP-Landschaft", "bar_mkt": "Marktzugänglichkeit", "bar_evi": "Beweissicherheit",
        "dl_md": "Bericht herunterladen (.md)", "dl_pdf": "Bericht herunterladen (.pdf)",
        "progress": "Analyse läuft",
        "err_failed": "✗ Analyse fehlgeschlagen", "err_run": "Ausführungs-ID",
    },
    "French": {
        "formula": "Formule de score", "out_of": "sur 100",
        "EXCELLENT": "EXCELLENT", "GOOD": "BON", "MODERATE": "MODÉRÉ", "WEAK": "FAIBLE",
        "risks": "Risques clés", "opps": "Opportunités clés",
        "trl_sub": "Maturité tech.", "mrl_sub": "Maturité fab.",
        "ip_sub": "Brevets", "mkt_sub": "Accessibilité", "evi_sub": "Confiance",
        "bar_trl": "Maturité technologique", "bar_mrl": "Maturité de fabrication",
        "bar_ip": "Paysage PI", "bar_mkt": "Accessibilité marché", "bar_evi": "Confiance preuves",
        "dl_md": "Télécharger le rapport (.md)", "dl_pdf": "Télécharger le rapport (.pdf)",
        "progress": "Analyse en cours",
        "err_failed": "✗ Échec de l'analyse", "err_run": "ID d'exécution",
    },
    "Spanish": {
        "formula": "Fórmula de puntuación", "out_of": "de 100",
        "EXCELLENT": "EXCELENTE", "GOOD": "BUENO", "MODERATE": "MODERADO", "WEAK": "DÉBIL",
        "risks": "Riesgos clave", "opps": "Oportunidades clave",
        "trl_sub": "Madurez tech.", "mrl_sub": "Madurez fab.",
        "ip_sub": "Patentes", "mkt_sub": "Accesibilidad", "evi_sub": "Confianza",
        "bar_trl": "Madurez tecnológica", "bar_mrl": "Madurez de fabricación",
        "bar_ip": "Panorama PI", "bar_mkt": "Accesibilidad mercado", "bar_evi": "Confianza evidencias",
        "dl_md": "Descargar informe (.md)", "dl_pdf": "Descargar informe (.pdf)",
        "progress": "Análisis en curso",
        "err_failed": "✗ Análisis fallido", "err_run": "ID de ejecución",
    },
    "Italian": {
        "formula": "Formula di punteggio", "out_of": "su 100",
        "EXCELLENT": "ECCELLENTE", "GOOD": "BUONO", "MODERATE": "MODERATO", "WEAK": "DEBOLE",
        "risks": "Rischi chiave", "opps": "Opportunità chiave",
        "trl_sub": "Maturità tech.", "mrl_sub": "Maturità prod.",
        "ip_sub": "Brevetti", "mkt_sub": "Accessibilità", "evi_sub": "Attendibilità",
        "bar_trl": "Maturità tecnologica", "bar_mrl": "Maturità produttiva",
        "bar_ip": "Panorama brevetti", "bar_mkt": "Accessibilità mercato", "bar_evi": "Attendibilità prove",
        "dl_md": "Scarica il rapporto (.md)", "dl_pdf": "Scarica il rapporto (.pdf)",
        "progress": "Analisi in corso",
        "err_failed": "✗ Analisi non riuscita", "err_run": "ID esecuzione",
    },
    "Portuguese": {
        "formula": "Fórmula de pontuação", "out_of": "de 100",
        "EXCELLENT": "EXCELENTE", "GOOD": "BOM", "MODERATE": "MODERADO", "WEAK": "FRACO",
        "risks": "Principais riscos", "opps": "Principais oportunidades",
        "trl_sub": "Maturidade tech.", "mrl_sub": "Maturidade fab.",
        "ip_sub": "Patentes", "mkt_sub": "Acessibilidade", "evi_sub": "Confiança",
        "bar_trl": "Maturidade tecnológica", "bar_mrl": "Maturidade de fabricação",
        "bar_ip": "Panorama PI", "bar_mkt": "Acessibilidade mercado", "bar_evi": "Confiança evidências",
        "dl_md": "Baixar relatório (.md)", "dl_pdf": "Baixar relatório (.pdf)",
        "progress": "Análise em andamento",
        "err_failed": "✗ Análise falhou", "err_run": "ID da execução",
    },
    "Russian": {
        "formula": "Формула оценки", "out_of": "из 100",
        "EXCELLENT": "ОТЛИЧНО", "GOOD": "ХОРОШО", "MODERATE": "УМЕРЕННО", "WEAK": "СЛАБО",
        "risks": "Ключевые риски", "opps": "Ключевые возможности",
        "trl_sub": "Зрелость технол.", "mrl_sub": "Зрелость произв.",
        "ip_sub": "Патентный ландшафт", "mkt_sub": "Доступность рынка", "evi_sub": "Достоверность",
        "bar_trl": "Технологическая готовность", "bar_mrl": "Производственная готовность",
        "bar_ip": "Патентный ландшафт", "bar_mkt": "Доступность рынка", "bar_evi": "Достоверность данных",
        "dl_md": "Скачать отчёт (.md)", "dl_pdf": "Скачать отчёт (.pdf)",
        "progress": "Анализ выполняется",
        "err_failed": "✗ Ошибка анализа", "err_run": "ID запуска",
    },
    "Arabic": {
        "formula": "صيغة التقييم", "out_of": "من 100",
        "EXCELLENT": "ممتاز", "GOOD": "جيد", "MODERATE": "متوسط", "WEAK": "ضعيف",
        "risks": "المخاطر الرئيسية", "opps": "الفرص الرئيسية",
        "trl_sub": "نضج التقنية", "mrl_sub": "نضج التصنيع",
        "ip_sub": "المشهد البراءاتي", "mkt_sub": "إمكانية الوصول", "evi_sub": "موثوقية الأدلة",
        "bar_trl": "جاهزية التقنية", "bar_mrl": "جاهزية التصنيع",
        "bar_ip": "المشهد البراءاتي", "bar_mkt": "إمكانية الوصول للسوق", "bar_evi": "موثوقية الأدلة",
        "dl_md": "تنزيل التقرير (.md)", "dl_pdf": "تنزيل التقرير (.pdf)",
        "progress": "جارٍ التحليل",
        "err_failed": "✗ فشل التحليل", "err_run": "معرّف التشغيل",
    },
}


def _scorecard_strings(output_language: str) -> dict[str, str]:
    return _SCORECARD_I18N.get(output_language, _SCORECARD_I18N["English"])


_WARNING_I18N: dict[str, dict[str, str]] = {
    "English": {
        "title": "Source Coverage Warning",
        "footer": "Analysis quality in flagged domains may be limited.",
        "ac_few": "⚠ Academic: only {n} source{pl} (recommended ≥3)",
        "pa_few": "⚠ Patent: only {n} source{pl} (recommended ≥2)",
        "mk_few": "⚠ Market: only {n} source{pl} (recommended ≥2)",
        "mk_stale": "⚠ Market: {stale}/{total} sources are undated or older than 3 years — market intelligence may be outdated",
        "pat_old": "⚠ Patents: {n}/{total} patent{pl} filed 15+ years ago may have expired — verify legal status before relying on landscape analysis",
        "ac_old": "⚠ Academic: oldest source from {year} (\"{title}\") — findings in fast-moving fields may not reflect current state of the art",
    },
    "Simplified Chinese": {
        "title": "来源覆盖警告",
        "footer": "被标记领域的分析质量可能受限。",
        "ac_few": "⚠ 学术来源：仅 {n} 篇（建议 ≥3 篇）",
        "pa_few": "⚠ 专利来源：仅 {n} 项（建议 ≥2 项）",
        "mk_few": "⚠ 市场来源：仅 {n} 篇（建议 ≥2 篇）",
        "mk_stale": "⚠ 市场：{stale}/{total} 条来源无日期或超过 3 年 — 市场情报可能已过时",
        "pat_old": "⚠ 专利：{n}/{total} 项专利申请距今超过 15 年，可能已到期 — 使用前请核实法律状态",
        "ac_old": "⚠ 学术：最早来源为 {year} 年（\"{title}\"）— 在快速发展的领域，结论可能已不反映最新进展",
    },
    "Traditional Chinese": {
        "title": "來源覆蓋警告",
        "footer": "被標記領域的分析質量可能受限。",
        "ac_few": "⚠ 學術來源：僅 {n} 篇（建議 ≥3 篇）",
        "pa_few": "⚠ 專利來源：僅 {n} 項（建議 ≥2 項）",
        "mk_few": "⚠ 市場來源：僅 {n} 篇（建議 ≥2 篇）",
        "mk_stale": "⚠ 市場：{stale}/{total} 條來源無日期或超過 3 年 — 市場情報可能已過時",
        "pat_old": "⚠ 專利：{n}/{total} 項專利申請距今超過 15 年，可能已到期 — 使用前請核實法律狀態",
        "ac_old": "⚠ 學術：最早來源為 {year} 年（\"{title}\"）— 在快速發展的領域，結論可能已不反映最新進展",
    },
    "Japanese": {
        "title": "ソースカバレッジ警告",
        "footer": "フラグが立てられたドメインでは分析品質が制限される場合があります。",
        "ac_few": "⚠ 学術：{n} 件のみ（推奨 ≥3 件）",
        "pa_few": "⚠ 特許：{n} 件のみ（推奨 ≥2 件）",
        "mk_few": "⚠ 市場：{n} 件のみ（推奨 ≥2 件）",
        "mk_stale": "⚠ 市場：{stale}/{total} 件が未日付または3年以上経過 — 市場情報が古い可能性があります",
        "pat_old": "⚠ 特許：{n}/{total} 件が出願から15年以上経過し、失効している可能性があります",
        "ac_old": "⚠ 学術：最も古いソースは {year} 年（\"{title}\"）— 急速に発展する分野では最新動向を反映していない可能性があります",
    },
    "Korean": {
        "title": "출처 커버리지 경고",
        "footer": "표시된 도메인에서는 분석 품질이 제한될 수 있습니다.",
        "ac_few": "⚠ 학술: {n}개만 (권장 ≥3개)",
        "pa_few": "⚠ 특허: {n}개만 (권장 ≥2개)",
        "mk_few": "⚠ 시장: {n}개만 (권장 ≥2개)",
        "mk_stale": "⚠ 시장: {stale}/{total}개 출처가 날짜 없음 또는 3년 이상 경과 — 시장 정보가 오래되었을 수 있음",
        "pat_old": "⚠ 특허: {n}/{total}개 특허가 출원 후 15년 이상 경과하여 만료되었을 수 있음",
        "ac_old": "⚠ 학술: 가장 오래된 출처는 {year}년 (\"{title}\") — 빠르게 발전하는 분야에서는 최신 동향을 반영하지 않을 수 있음",
    },
    "German": {
        "title": "Quellabdeckungswarnung",
        "footer": "Die Analysequalität in markierten Domänen kann eingeschränkt sein.",
        "ac_few": "⚠ Akademisch: nur {n} Quelle(n) (empfohlen ≥3)",
        "pa_few": "⚠ Patent: nur {n} Quelle(n) (empfohlen ≥2)",
        "mk_few": "⚠ Markt: nur {n} Quelle(n) (empfohlen ≥2)",
        "mk_stale": "⚠ Markt: {stale}/{total} Quellen sind undatiert oder älter als 3 Jahre — Marktinformationen möglicherweise veraltet",
        "pat_old": "⚠ Patente: {n}/{total} Patent(e) vor mehr als 15 Jahren angemeldet — rechtlichen Status vor Verwendung prüfen",
        "ac_old": "⚠ Akademisch: älteste Quelle aus {year} (\"{title}\") — Erkenntnisse spiegeln möglicherweise nicht den aktuellen Stand der Technik wider",
    },
    "French": {
        "title": "Avertissement sur la couverture des sources",
        "footer": "La qualité de l'analyse dans les domaines signalés peut être limitée.",
        "ac_few": "⚠ Académique : seulement {n} source(s) (recommandé ≥3)",
        "pa_few": "⚠ Brevets : seulement {n} source(s) (recommandé ≥2)",
        "mk_few": "⚠ Marché : seulement {n} source(s) (recommandé ≥2)",
        "mk_stale": "⚠ Marché : {stale}/{total} sources non datées ou datant de plus de 3 ans — données de marché potentiellement obsolètes",
        "pat_old": "⚠ Brevets : {n}/{total} brevet(s) déposé(s) il y a plus de 15 ans peuvent être expirés — vérifier le statut légal",
        "ac_old": "⚠ Académique : la source la plus ancienne date de {year} (\"{title}\") — les conclusions peuvent ne pas refléter l'état de l'art actuel",
    },
    "Spanish": {
        "title": "Advertencia de cobertura de fuentes",
        "footer": "La calidad del análisis en los dominios marcados puede ser limitada.",
        "ac_few": "⚠ Académico: solo {n} fuente(s) (recomendado ≥3)",
        "pa_few": "⚠ Patentes: solo {n} fuente(s) (recomendado ≥2)",
        "mk_few": "⚠ Mercado: solo {n} fuente(s) (recomendado ≥2)",
        "mk_stale": "⚠ Mercado: {stale}/{total} fuentes sin fecha o con más de 3 años — inteligencia de mercado posiblemente desactualizada",
        "pat_old": "⚠ Patentes: {n}/{total} patente(s) presentada(s) hace más de 15 años pueden haber expirado — verificar estado legal",
        "ac_old": "⚠ Académico: la fuente más antigua es de {year} (\"{title}\") — los hallazgos pueden no reflejar el estado actual del arte",
    },
    "Italian": {
        "title": "Avviso sulla copertura delle fonti",
        "footer": "La qualità dell'analisi nei domini segnalati potrebbe essere limitata.",
        "ac_few": "⚠ Accademico: solo {n} fonte/i (consigliato ≥3)",
        "pa_few": "⚠ Brevetti: solo {n} fonte/i (consigliato ≥2)",
        "mk_few": "⚠ Mercato: solo {n} fonte/i (consigliato ≥2)",
        "mk_stale": "⚠ Mercato: {stale}/{total} fonti non datate o più vecchie di 3 anni — dati di mercato potenzialmente obsoleti",
        "pat_old": "⚠ Brevetti: {n}/{total} brevetto/i depositato/i oltre 15 anni fa potrebbero essere scaduti — verificare lo stato legale",
        "ac_old": "⚠ Accademico: la fonte più antica è del {year} (\"{title}\") — i risultati potrebbero non riflettere lo stato dell'arte attuale",
    },
    "Portuguese": {
        "title": "Aviso de cobertura de fontes",
        "footer": "A qualidade da análise nos domínios sinalizados pode ser limitada.",
        "ac_few": "⚠ Académico: apenas {n} fonte(s) (recomendado ≥3)",
        "pa_few": "⚠ Patentes: apenas {n} fonte(s) (recomendado ≥2)",
        "mk_few": "⚠ Mercado: apenas {n} fonte(s) (recomendado ≥2)",
        "mk_stale": "⚠ Mercado: {stale}/{total} fontes sem data ou com mais de 3 anos — inteligência de mercado possivelmente desatualizada",
        "pat_old": "⚠ Patentes: {n}/{total} patente(s) registrada(s) há mais de 15 anos pode(m) ter expirado — verificar estado legal",
        "ac_old": "⚠ Académico: a fonte mais antiga é de {year} (\"{title}\") — os resultados podem não refletir o estado atual da arte",
    },
    "Russian": {
        "title": "Предупреждение о покрытии источников",
        "footer": "Качество анализа в отмеченных доменах может быть ограничено.",
        "ac_few": "⚠ Академические: только {n} источник(ов) (рекомендуется ≥3)",
        "pa_few": "⚠ Патенты: только {n} источник(ов) (рекомендуется ≥2)",
        "mk_few": "⚠ Рыночные: только {n} источник(ов) (рекомендуется ≥2)",
        "mk_stale": "⚠ Рынок: {stale}/{total} источников без даты или старше 3 лет — рыночные данные могут быть устаревшими",
        "pat_old": "⚠ Патенты: {n}/{total} патент(ов) поданы более 15 лет назад и могут быть недействительными",
        "ac_old": "⚠ Академические: самый старый источник — {year} г. (\"{title}\") — выводы могут не отражать современное состояние области",
    },
    "Arabic": {
        "title": "تحذير تغطية المصادر",
        "footer": "قد تكون جودة التحليل في النطاقات المُشار إليها محدودة.",
        "ac_few": "⚠ أكاديمي: {n} مصدر(مصادر) فقط (يُوصى بـ ≥3)",
        "pa_few": "⚠ براءات الاختراع: {n} مصدر(مصادر) فقط (يُوصى بـ ≥2)",
        "mk_few": "⚠ السوق: {n} مصدر(مصادر) فقط (يُوصى بـ ≥2)",
        "mk_stale": "⚠ السوق: {stale}/{total} مصادر بلا تاريخ أو أقدم من 3 سنوات — قد تكون معلومات السوق قديمة",
        "pat_old": "⚠ براءات: {n}/{total} براءة(براءات) مُقدَّمة منذ أكثر من 15 عامًا قد تكون منتهية الصلاحية",
        "ac_old": "⚠ أكاديمي: أقدم مصدر من عام {year} (\"{title}\") — قد لا تعكس النتائج الحالة الراهنة للمجال",
    },
}


def _warning_strings(output_language: str) -> dict[str, str]:
    return _WARNING_I18N.get(output_language, _WARNING_I18N["English"])


def _read_output_language(run_dir) -> str:
    """Read output_language from the saved validated_sources.json for a run."""
    try:
        sources_path = run_dir / "validated_sources.json"
        if sources_path.exists():
            data = json.loads(sources_path.read_text(encoding="utf-8"))
            return data.get("output_language") or "English"
    except Exception:
        pass
    return "English"


def _read_weight_profile(run_dir) -> str:
    """Read weight_profile from validated_sources.json for a run."""
    try:
        sources_path = run_dir / "validated_sources.json"
        if sources_path.exists():
            data = json.loads(sources_path.read_text(encoding="utf-8"))
            return data.get("weight_profile") or "industrial"
    except Exception:
        pass
    return "industrial"


def _radar_svg(trl: float, mrl: float, pat: float, mkt: float, evi: float, color: str = "#6366f1") -> str:
    """Generate an inline SVG pentagon radar chart for the five scoring dimensions."""
    import math
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

    return (
        '<svg viewBox="0 0 200 200" width="190" height="190" '
        'xmlns="http://www.w3.org/2000/svg" style="overflow:visible;display:block;">'
        + "".join(parts)
        + "</svg>"
    )


_PROFILE_LABELS: dict[str, str] = {
    "industrial":      "Industrial",
    "biomedical":      "Biomedical",
    "material_science": "Material Science",
}


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
        return (
            f'<div style="background:#1c1400;border:1px solid #713f12;border-radius:8px;'
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


def _render_reviewer_notes_html(run_dir: Path) -> str:
    """Return a collapsible HTML block with Agent 5's reviewer notes, or '' if absent."""
    notes_path = run_dir / "reviewer_notes.md"
    if not notes_path.exists():
        return ""
    try:
        raw = notes_path.read_text(encoding="utf-8").strip()
        if not raw:
            return ""
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
            '&#x270E; Agent 5 — Reviewer Notes</summary>'
            '<div style="margin-top:12px;font-size:12px;color:#d4d4d4;line-height:1.7;">'
            + "".join(lines_html)
            + "</div></details>"
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

    return (
        f'<div style="font-family:system-ui,-apple-system,\'Segoe UI\',sans-serif;'
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
        f'{_kpi_tile("Market", mkt, 5, t["mkt_sub"], mkt_pct, mkt_ids)}'
        f'{_kpi_tile("Evidence", evi, 5, t["evi_sub"], evi_pct, evi_ids)}'
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


# ---------------------------------------------------------------------------
# Progress display
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
    all_stages = [_STAGE_INITIAL] + TASK_STAGE_LABELS
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
                    f'<span style="font-size:11px;color:#4b5563;">Sources: </span>'
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
                    f'<div style="{row_style}">{html.escape(agent_name)}</div>'
                    f'</div>'
                )
            continue

        dot = _progress_dot(state, spin)
        items.append(
            f'<div style="display:flex;align-items:flex-start;gap:10px;margin-bottom:12px;">'
            f'{dot}'
            f'<div style="padding-top:1px;">'
            f'<div style="{text_style}">{html.escape(label)}</div>'
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


def _run_duration(run_dir: Path) -> str:
    """Return human-readable run duration (e.g. '2m 34s') from run_id start to status.json mtime."""
    try:
        run_id = run_dir.name
        ts = run_id.split("-")[0]
        start_dt = datetime.strptime(ts, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        status_path = run_dir / "status.json"
        if not status_path.exists():
            return "—"
        import os as _os
        end_ts = _os.path.getmtime(status_path)
        from datetime import timezone as _tz
        end_dt = datetime.fromtimestamp(end_ts, tz=_tz.utc)
        secs = int((end_dt - start_dt).total_seconds())
        if secs < 0:
            return "—"
        if secs < 60:
            return f"{secs}s"
        return f"{secs // 60}m {secs % 60:02d}s"
    except Exception:
        return "—"


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


def _read_run_topic(run_dir: Path) -> str:
    """Read topic from status.json (supports all languages); fall back to report parsing."""
    try:
        data = json.loads((run_dir / "status.json").read_text(encoding="utf-8"))
        if t := data.get("topic"):
            return str(t)[:90]
    except Exception:
        pass
    report_path = run_dir / "commercialization_report.md"
    if report_path.exists():
        return _extract_topic_from_report(report_path)
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

    sources_index = _build_sources_index(run_dir)
    score_html = ""
    scores_path = run_dir / "commercialization_scores.json"
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

    score_html += _render_reviewer_notes_html(run_dir)
    score_html += _src_detail_panel_html(sources_index)
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
        f'<input type="text" placeholder="Filter by topic…" '
        f'oninput="{_hist_filter_js}" '
        f'style="flex:1;max-width:340px;background:#1a1a1a;border:1px solid #3d3d3d;'
        f'border-radius:6px;padding:4px 10px;font-size:12px;color:#e5e5e5;'
        f'font-family:system-ui;outline:none;" />'
        f'<span style="font-size:11px;color:#4b5563;white-space:nowrap;">'
        f'Click any row to fill the Run ID field below</span>'
        f'</div>'
        f'<div style="overflow-x:auto;">'
        f'<table style="width:100%;border-collapse:collapse;font-size:13px;">'
        f'<thead>'
        f'<tr style="background:#141414;border-bottom:1px solid #2d2d2d;">'
        f'<th style="text-align:left;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;white-space:nowrap;">Time</th>'
        f'<th style="text-align:left;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">Topic</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;white-space:nowrap;">Duration</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">Score</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">TRL</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">MRL</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">Patent</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">Market</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">Evidence</th>'
        f'<th style="text-align:center;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">Status</th>'
        f'<th style="text-align:left;padding:11px 14px;color:#777777;font-weight:700;'
        f'font-size:11px;letter-spacing:0.06em;text-transform:uppercase;">Run ID</th>'
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


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

# Reportlab built-in CID fonts — no font file needed, cross-platform.
# xhtml2pdf resolves these via pdfmetrics after registerFont() is called.
_CID_FONT_MAP: dict[str, str] = {
    "Simplified Chinese":  "STSong-Light",
    "Traditional Chinese": "MSung-Light",
    "Japanese":            "HeiseiKakuGo-W5",
    "Korean":              "HYGoThic-Medium",
}


def _register_cid_font(output_language: str) -> str:
    """Register a CID font for the given language and return its name.

    Returns '' for non-CJK languages (Latin fonts are built into reportlab).
    CID fonts are embedded in reportlab — no external font file required.
    """
    font_name = _CID_FONT_MAP.get(output_language, "")
    if not font_name:
        return ""
    try:
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))
        return font_name
    except Exception:
        return ""


def _generate_pdf(report_md: str, run_dir: Path, output_language: str = "English") -> Path | None:
    """Convert markdown report to PDF using reportlab Platypus for full CJK table support."""
    try:
        import markdown as md_lib
        from html.parser import HTMLParser
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer,
            Table, TableStyle, HRFlowable,
        )
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont

        # Font selection: prefer embedded TTFont (viewer-independent) over CID font.
        # CID fonts like STSong-Light are NOT embedded in the PDF and only render
        # in Adobe Acrobat; Chrome/Edge will show empty glyphs.
        _CJK_TTF_CANDIDATES: dict[str, list[str]] = {
            "Simplified Chinese": [
                # Windows
                "C:/Windows/Fonts/msyh.ttc",
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/simsun.ttc",
                # Linux (Ubuntu / Debian / Fedora / Alpine)
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/google-noto-cjk/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                # macOS
                "/System/Library/Fonts/PingFang.ttc",
                "/System/Library/Fonts/STHeiti Light.ttc",
            ],
            "Traditional Chinese": [
                # Windows
                "C:/Windows/Fonts/msjh.ttc",
                "C:/Windows/Fonts/mingliu.ttc",
                # Linux
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                # macOS
                "/System/Library/Fonts/PingFang.ttc",
            ],
            "Japanese": [
                # Windows
                "C:/Windows/Fonts/YuGothM.ttc",
                "C:/Windows/Fonts/meiryo.ttc",
                "C:/Windows/Fonts/msgothic.ttc",
                # Linux
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
                # macOS
                "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
                "/Library/Fonts/Osaka.ttf",
            ],
            "Korean": [
                # Windows
                "C:/Windows/Fonts/malgun.ttf",
                "C:/Windows/Fonts/gulim.ttc",
                # Linux
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                # macOS
                "/System/Library/Fonts/AppleSDGothicNeo.ttc",
            ],
        }

        fn = "Helvetica"
        for font_path in _CJK_TTF_CANDIDATES.get(output_language, []):
            if Path(font_path).is_file():
                try:
                    from reportlab.pdfbase.ttfonts import TTFont
                    _reg_name = "EmbeddedCJK"
                    pdfmetrics.registerFont(TTFont(_reg_name, font_path))
                    fn = _reg_name
                    break
                except Exception:
                    continue
        if fn == "Helvetica":
            # Fall back to CID font (renders in Acrobat; text still extractable elsewhere)
            cid_name = _CID_FONT_MAP.get(output_language, "")
            if cid_name:
                try:
                    pdfmetrics.registerFont(UnicodeCIDFont(cid_name))
                    fn = cid_name
                except Exception:
                    pass

        # Palette
        BLUE  = colors.HexColor("#2563eb")
        DARK  = colors.HexColor("#1a1a1a")
        H1C   = colors.HexColor("#111827")
        H2C   = colors.HexColor("#1e293b")
        H3C   = colors.HexColor("#374151")
        TH_BG = colors.HexColor("#f8fafc")
        GRID  = colors.HexColor("#d1d5db")

        def _s(name, size, mult=1.55, col=DARK, sb=0, sa=5, li=0):
            return ParagraphStyle(name, fontName=fn, fontSize=size,
                                  leading=size * mult, textColor=col,
                                  spaceBefore=sb, spaceAfter=sa, leftIndent=li)

        sH1   = _s("H1",   14, col=H1C, sb=0,  sa=8)
        sH2   = _s("H2",   12, col=H2C, sb=12, sa=4)
        sH3   = _s("H3",   10.5, col=H3C, sb=9, sa=4)
        sBody = _s("Body", 10,  sb=0,  sa=4)
        sLI   = _s("LI",   10,  sb=0,  sa=2, li=8)
        sTH   = _s("TH",   8.5, sb=0,  sa=0)
        sTD   = _s("TD",   8.5, sb=0,  sa=0)
        sMono = _s("Mono", 8,   sb=0,  sa=3)

        # Unicode characters that Microsoft YaHei (and most CJK fonts) lack glyphs for.
        # Subscript/superscript digits → plain digits; non-standard hyphens → hyphen-minus.
        _UNICODE_FIX = str.maketrans(
            "₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹‐‑‒―−–—",
            "01234567890123456789-------",
        )

        class _HtmlToStory(HTMLParser):
            """Parse markdown-generated HTML into a reportlab Platypus story.

            Uses a single _write() routing method so inline markup tags
            (strong/em/code) always land in the buffer that owns their context
            (block paragraph, list item, or table cell).
            """

            _SEMANTIC = {"h1","h2","h3","p","li","td","th","pre"}

            def __init__(self):
                super().__init__()
                self.story: list = []
                self._stk: list[str] = []
                self._block_buf: str = ""       # h1 / h2 / h3 / p
                self._li_stk: list[str] = []    # li (stack for nested lists)
                self._cell_buf: str = ""        # td / th
                self._tbl: list = []
                self._row: list = []
                self._cell_is_th: bool = False
                self._row_is_hdr: bool = False

            # -- buffer routing -------------------------------------------

            def _ctx(self) -> str:
                """Innermost semantic block tag on the stack."""
                for t in reversed(self._stk):
                    if t in self._SEMANTIC:
                        return t
                return ""

            def _write(self, text: str) -> None:
                text = text.translate(_UNICODE_FIX)
                ctx = self._ctx()
                if ctx == "li":
                    if self._li_stk:
                        self._li_stk[-1] += text
                elif ctx in ("td", "th"):
                    self._cell_buf += text
                else:
                    self._block_buf += text

            def _flush_block(self, style):
                t = self._block_buf.strip()
                if t:
                    self.story.append(Paragraph(t, style))
                self._block_buf = ""

            # -- parser callbacks -----------------------------------------

            def handle_starttag(self, tag, attrs):
                self._stk.append(tag)
                if tag in ("h1", "h2", "h3", "p"):
                    self._block_buf = ""
                elif tag == "li":
                    self._li_stk.append("")
                elif tag == "table":
                    self._tbl = []
                elif tag == "tr":
                    self._row = []
                    self._row_is_hdr = False
                elif tag in ("td", "th"):
                    self._cell_buf = ""
                    self._cell_is_th = (tag == "th")
                    if tag == "th":
                        self._row_is_hdr = True
                elif tag in ("strong", "b"):
                    self._write("<b>")
                elif tag in ("em", "i"):
                    self._write("<i>")
                elif tag == "code":
                    self._write("<font face='Courier' size='8'>")
                elif tag == "br":
                    self._write("<br/>")

            def handle_endtag(self, tag):
                if self._stk and self._stk[-1] == tag:
                    self._stk.pop()

                if tag == "h1":
                    self._flush_block(sH1)
                    self.story.append(
                        HRFlowable(width="100%", thickness=1.5,
                                   color=BLUE, spaceAfter=6))
                elif tag == "h2":
                    self._flush_block(sH2)
                    self.story.append(
                        HRFlowable(width="100%", thickness=0.5,
                                   color=GRID, spaceAfter=4))
                elif tag == "h3":
                    self._flush_block(sH3)
                elif tag == "p":
                    self._flush_block(sBody)
                elif tag == "li":
                    t = (self._li_stk.pop() if self._li_stk else "").strip()
                    if t:
                        self.story.append(Paragraph("• " + t, sLI))
                elif tag in ("strong", "b"):
                    self._write("</b>")
                elif tag in ("em", "i"):
                    self._write("</i>")
                elif tag == "code":
                    self._write("</font>")
                elif tag == "pre":
                    self._flush_block(sMono)
                elif tag in ("td", "th"):
                    self._row.append(
                        (self._cell_buf.strip(), self._cell_is_th))
                elif tag == "tr":
                    if self._row:
                        self._tbl.append((self._row, self._row_is_hdr))
                elif tag == "table":
                    self._build_table()
                    self.story.append(Spacer(1, 4))

            def handle_data(self, data: str) -> None:
                top = self._stk[-1] if self._stk else ""
                # Skip whitespace-only text between structural table tags
                if top in ("table", "tbody", "thead", "tr", "ul", "ol"):
                    return
                # Escape & < > so reportlab's XML parser doesn't mis-read them
                # as entity/tag markup. Inline <b>/<i> tags added by
                # handle_starttag are written directly and must NOT be escaped.
                import html as _html
                self._write(_html.escape(data))

            def _build_table(self):
                if not self._tbl:
                    return
                n_cols = max(len(row) for row, _ in self._tbl)
                avail = 16.5 * cm
                col_w = [avail / n_cols] * n_cols

                cells = []
                style_cmds = [
                    ("GRID",           (0, 0), (-1, -1), 0.5, GRID),
                    ("VALIGN",         (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING",     (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING",  (0, 0), (-1, -1), 3),
                    ("LEFTPADDING",    (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
                    ("FONTNAME",       (0, 0), (-1, -1), fn),
                    ("FONTSIZE",       (0, 0), (-1, -1), 8.5),
                ]

                for r_idx, (row, is_hdr) in enumerate(self._tbl):
                    p_row = []
                    for c_idx in range(n_cols):
                        if c_idx < len(row):
                            text, is_th = row[c_idx]
                        else:
                            text, is_th = "", False
                        st = sTH if (is_hdr or is_th) else sTD
                        p_row.append(Paragraph(text, st))
                    cells.append(p_row)
                    if is_hdr:
                        style_cmds.append(
                            ("BACKGROUND", (0, r_idx), (-1, r_idx), TH_BG))

                tbl = Table(cells, colWidths=col_w, repeatRows=1)
                tbl.setStyle(TableStyle(style_cmds))
                self.story.append(Spacer(1, 4))
                self.story.append(tbl)

        html_body = md_lib.markdown(report_md, extensions=["tables", "fenced_code"])
        parser = _HtmlToStory()
        parser.feed(html_body)
        story = parser.story

        pdf_path = run_dir / "commercialization_report.pdf"
        doc = SimpleDocTemplate(
            str(pdf_path), pagesize=A4,
            rightMargin=2 * cm, leftMargin=2 * cm,
            topMargin=2 * cm,   bottomMargin=2 * cm,
        )
        doc.build(story)
        return pdf_path

    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main analysis runner
# ---------------------------------------------------------------------------

def extract_paper_from_pdf(pdf_file) -> tuple:
    """Extract PaperContribution from uploaded PDF.
    Returns 10 values: title, contribution, domain, metrics_str, topic, doi_url,
    paper_json, card_visible, status_msg, submit_btn_update.
    """
    _no_change = gr.update()
    if pdf_file is None:
        return ("", "", "", "", "", "", "", gr.update(visible=False),
                '<p style="color:#f59e0b;font-size:13px;margin:6px 0">⚠ Please upload a PDF file first.</p>',
                _no_change)

    try:
        from academic_agent.pdf_extractor import extract_paper_contribution
        pc = extract_paper_contribution(pdf_file)
    except Exception as exc:
        return ("", "", "", "", "", "", "", gr.update(visible=False),
                f'<p style="color:#f87171;font-size:13px;margin:6px 0">✗ Extraction failed: {html.escape(str(exc))}</p>',
                _no_change)

    metrics_str = "\n".join(pc.key_metrics)
    doi_url = pc.url or (f"https://doi.org/{pc.doi}" if pc.doi and not pc.doi.startswith("10.0000/uploaded-") else "")
    paper_json = pc.model_dump_json()

    return (
        pc.title,
        pc.core_contribution,
        pc.application_domain,
        metrics_str,
        pc.commercialization_topic,
        doi_url,
        paper_json,
        gr.update(visible=True),
        "",                          # clear status bar — paper card appearing is enough feedback
        gr.update(visible=False),    # hide the normal Run Analysis button
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
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    start = time.time()
    tick = 0
    try:
        while proc.poll() is None:
            elapsed = int(time.time() - start)
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
                _render_source_preview_html(run_dir),
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

    # Read final status written by the worker.
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        status = {"done": False, "error": None, "output_language": "English"}

    # If the process was cancelled (GeneratorExit path doesn't reach here),
    # or exited before marking done, return silently.
    if not status.get("done"):
        yield "", "", "", gr.update(visible=False), gr.update(visible=False), gr.update(interactive=True), gr.update(visible=False), ""
        return

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
    output_language = status.get("output_language") or "English"

    lang_badge = (
        f'<div style="font-family:system-ui;margin-bottom:10px;">'
        f'<span style="background:#1a1a1a;border:1px solid #2d2d2d;color:#9a9a9a;'
        f'font-size:11px;font-weight:600;padding:3px 10px;border-radius:20px;">'
        f'🌐 Report language: {html.escape(output_language)}</span></div>'
    ) if output_language != "English" else ""
    wp = _read_weight_profile(run_dir)
    sources_index = _build_sources_index(run_dir)
    score_html = (lang_badge + _render_source_warning_html(run_dir, output_language) + _render_score_html(scores_json, research_topic.strip(), output_language, wp, sources_index=sources_index)) if scores_json else lang_badge
    score_html += _render_reviewer_notes_html(run_dir)
    score_html += _src_detail_panel_html(sources_index)
    t = _scorecard_strings(output_language)
    md_update = gr.update(value=str(report_path), visible=True, label=t["dl_md"]) if report_path.exists() else gr.update(visible=False)

    # Yield results immediately; PDF is generated in background to avoid blocking.
    yield "", score_html, report, md_update, gr.update(visible=False), gr.update(interactive=False), gr.update(visible=False), ""

    _pdf_result: list[Path | None] = [None]
    def _bg_pdf() -> None:
        _pdf_result[0] = _generate_pdf(report, run_dir, output_language)
    _pdf_thread = threading.Thread(target=_bg_pdf, daemon=True)
    _pdf_thread.start()
    _pdf_thread.join(timeout=45)

    pdf_path_obj = _pdf_result[0]
    pdf_update = gr.update(value=str(pdf_path_obj), visible=True, label=t["dl_pdf"]) if pdf_path_obj else gr.update(visible=False)
    yield "", score_html, report, md_update, pdf_update, gr.update(interactive=True), gr.update(visible=False), ""


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

/* ── Cancel button ── */
.cancel-btn button {
    background: #2d1515 !important;
    color: #f87171 !important;
    border-color: #7f1d1d !important;
}
.cancel-btn button:hover {
    background: #3f1f1f !important;
    color: #fca5a5 !important;
    border-color: #dc2626 !important;
}

/* ── Report markdown ── */
.report-md h2 { margin-top: 1.6em; padding-bottom: 0.3em; border-bottom: 1px solid #2d2d2d; }
.report-md h3 { margin-top: 1.2em; }
.report-md p, .report-md li { line-height: 1.7; }
.report-md table { width: 100%; border-collapse: collapse; font-size: 0.88em; }
.report-md th { background: #141414; font-weight: 700; padding: 8px 12px; border: 1px solid #2d2d2d; text-align: left; }
.report-md td { padding: 7px 12px; border: 1px solid #2d2d2d; }

/* ── Prevent Gradio accordion from creating an inner scroll container ── */
details > div,
details > .padding {
    overflow: visible !important;
    max-height: none !important;
}

/* ── PDF paper card ── */
.paper-card-wrap {
    border: 1px solid #2a3a5a !important;
    border-left: 3px solid #3b82f6 !important;
    border-radius: 8px !important;
    margin-top: 6px !important;
    background: #0c1628 !important;
}
.paper-divider {
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 16px 0 10px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: #60a5fa;
}
.paper-divider::before, .paper-divider::after {
    content: '';
    flex: 1;
    height: 1px;
    background: #1e3a5a;
}
/* Highlight the analysis topic textbox */
.paper-topic-box textarea {
    background: rgba(37, 99, 235, 0.08) !important;
    border: 1.5px solid #3b82f6 !important;
    border-radius: 6px !important;
    font-size: 14px !important;
    color: #e0eaff !important;
}
.paper-topic-box label span {
    color: #60a5fa !important;
    font-weight: 600 !important;
}
/* Clear paper button: subtle red on hover */
.clear-paper-btn button {
    color: #9a9a9a !important;
    border-color: #2d2d2d !important;
    background: transparent !important;
}
.clear-paper-btn button:hover {
    color: #f87171 !important;
    border-color: #7f1d1d !important;
    background: #2d1515 !important;
}
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
    Agents 1–3 run in parallel; expected run time: <strong style="color:#e5e5e5;">2–3 minutes</strong>.
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

    with gr.Tabs() as tabs:
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

            with gr.Accordion("📄 Upload Paper PDF (optional)", open=False) as pdf_accordion:
                gr.HTML(
                    '<p style="font-size:12px;color:#6b7280;margin:2px 0 12px;">'
                    'Upload a PDF to anchor the analysis on a specific paper — it becomes the '
                    'primary source <strong style="color:#9a9a9a">(A1)</strong> and the pipeline '
                    'searches for supporting evidence around its contribution.'
                    '</p>'
                )
                with gr.Row(equal_height=True):
                    pdf_upload  = gr.File(label="Upload PDF", file_types=[".pdf"], scale=4)
                    extract_btn = gr.Button("Extract Contribution", variant="secondary", scale=1)
                extract_status   = gr.HTML(value="")
                paper_json_state = gr.State("")

                with gr.Group(visible=False, elem_classes=["paper-card-wrap"]) as paper_card:
                    # ── Paper metadata ────────────────────────────────────────
                    paper_title_box        = gr.Textbox(label="Title", interactive=True, lines=1)
                    paper_contribution_box = gr.Textbox(label="Core Contribution", interactive=True, lines=3)
                    with gr.Row(equal_height=True):
                        paper_domain_box = gr.Textbox(label="Application Domain", interactive=True, lines=1, scale=3)
                        paper_doi_box    = gr.Textbox(label="DOI / URL", interactive=True, lines=1, scale=2)
                    paper_metrics_box = gr.Textbox(label="Key Metrics (one per line)", interactive=True, lines=2)

                    # ── Analysis topic (highlighted) ──────────────────────────
                    gr.HTML('<div class="paper-divider"><span>Analysis Topic</span></div>')
                    paper_topic_box = gr.Textbox(
                        label="🔍 This drives the pipeline search — edit to focus or broaden",
                        interactive=True,
                        lines=2,
                        elem_classes=["paper-topic-box"],
                    )

                    # ── Action buttons ────────────────────────────────────────
                    with gr.Row(equal_height=True):
                        clear_paper_btn = gr.Button(
                            "✕  Clear Paper", variant="secondary", scale=1,
                            elem_classes=["clear-paper-btn"],
                        )
                        paper_run_btn = gr.Button(
                            "▶  Run Analysis with this Paper", variant="primary", scale=3,
                        )

            with gr.Row(equal_height=True):
                language_dd = gr.Dropdown(
                    label="Report Language",
                    choices=[
                        "Auto (detect from topic)",
                        "English", "Chinese", "Japanese", "Korean",
                        "French", "German", "Spanish", "Portuguese",
                        "Arabic", "Russian", "Hindi",
                    ],
                    value="Auto (detect from topic)",
                    scale=2,
                )
                profile_dd = gr.Dropdown(
                    label="Industry Profile",
                    choices=[
                        "Auto (detect from topic)",
                        "industrial",
                        "material_science",
                        "biomedical",
                        "clean_tech",
                        "software_ai",
                    ],
                    value="Auto (detect from topic)",
                    scale=2,
                )
                submit_btn = gr.Button("▶  Run Analysis", variant="primary", scale=3)
                cancel_btn = gr.Button(
                    "⏹  Cancel", variant="secondary", scale=1,
                    visible=False, elem_classes=["cancel-btn"],
                )

            progress_output = gr.HTML()
            log_output      = gr.HTML()
            score_output    = gr.HTML()
            report_output   = gr.Markdown(elem_classes=["report-md"])
            with gr.Row():
                download_md  = gr.File(label="Download Report (.md)", visible=False, scale=1)
                download_pdf = gr.File(label="Download Report (.pdf)", visible=False, scale=1)

            extract_btn.click(
                fn=extract_paper_from_pdf,
                inputs=[pdf_upload],
                outputs=[
                    paper_title_box, paper_contribution_box, paper_domain_box,
                    paper_metrics_box, paper_topic_box, paper_doi_box,
                    paper_json_state, paper_card, extract_status, submit_btn,
                ],
            )

            clear_paper_btn.click(
                fn=lambda: (
                    "", "", "", "", "", "",   # clear all paper fields
                    "",                       # clear paper_json_state
                    gr.update(value=None),    # reset pdf_upload
                    gr.update(visible=False), # hide paper_card
                    "",                       # clear extract_status
                    gr.update(visible=True),  # restore submit_btn
                ),
                outputs=[
                    paper_title_box, paper_contribution_box, paper_domain_box,
                    paper_metrics_box, paper_topic_box, paper_doi_box,
                    paper_json_state, pdf_upload, paper_card, extract_status, submit_btn,
                ],
            )

            # Collapse the accordion first so progress display is immediately visible.
            paper_run_btn.click(
                fn=lambda: gr.update(open=False),
                inputs=[],
                outputs=[pdf_accordion],
            )

            paper_run_event = paper_run_btn.click(
                fn=run_analysis_from_paper,
                inputs=[
                    paper_title_box, paper_contribution_box, paper_domain_box,
                    paper_metrics_box, paper_topic_box, paper_doi_box,
                    paper_json_state, language_dd, profile_dd,
                ],
                outputs=[progress_output, score_output, report_output, download_md, download_pdf,
                         submit_btn, cancel_btn, log_output],
            )

            submit_event = submit_btn.click(
                fn=run_analysis,
                inputs=[topic_input, language_dd, profile_dd],
                outputs=[progress_output, score_output, report_output, download_md, download_pdf,
                         submit_btn, cancel_btn, log_output],
            )
            cancel_btn.click(
                fn=lambda: (
                    "",
                    "",
                    "",
                    gr.update(value=None, visible=False),
                    gr.update(value=None, visible=False),
                    gr.update(interactive=True),
                    gr.update(visible=False),
                    "",
                ),
                outputs=[progress_output, score_output, report_output,
                         download_md, download_pdf, submit_btn, cancel_btn, log_output],
                cancels=[submit_event, paper_run_event],
            )
            clear_btn.click(
                fn=lambda: ("", "", "", "",
                            gr.update(value=None, visible=False),
                            gr.update(value=None, visible=False)),
                outputs=[topic_input, progress_output, score_output, report_output,
                         download_md, download_pdf],
            )

        # ── History tab ───────────────────────────────────────────────────
        with gr.Tab("History") as history_tab:
            with gr.Row():
                gr.HTML('<p style="font-size:13px;color:#9a9a9a;margin:6px 0;">Past runs — paste a Run ID below to reload any report</p>')
                refresh_btn = gr.Button("↻  Refresh", variant="secondary", scale=0, min_width=110)
                cleanup_btn = gr.Button("🗑  Keep Latest 20", variant="secondary", scale=0, min_width=150)

            cleanup_status = gr.HTML(value="")
            history_output = gr.HTML(value=_render_history_html())

            def _do_cleanup():
                msg = _cleanup_old_runs(keep_n=20)
                status_html = (
                    f'<p style="font-size:12px;color:#9a9a9a;margin:4px 0 8px;">{html.escape(msg)}</p>'
                )
                return status_html, _render_history_html()

            refresh_btn.click(fn=_render_history_html, outputs=history_output)
            cleanup_btn.click(fn=_do_cleanup, outputs=[cleanup_status, history_output])
            history_tab.select(fn=_render_history_html, outputs=history_output)

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
