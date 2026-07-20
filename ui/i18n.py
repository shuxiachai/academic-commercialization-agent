"""i18n — All localisation dictionaries and accessor functions.

Contains:
    _SCORECARD_I18N, _scorecard_strings()
    _UI_I18N, _ui()
    _WARNING_I18N, _warning_strings()
    _CARD_LABELS_ZH, _CARD_LABELS_EN
    _PROFILE_CHOICES, _PROFILE_CHOICES_DEFAULT, _profile_choices()
"""

# ---------------------------------------------------------------------------
# Scorecard i18n
# ---------------------------------------------------------------------------

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
        "reviewer_notes": "Reviewer Notes",
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
        "reviewer_notes": "审阅备注",
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
        "reviewer_notes": "審閱備註",
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
        "reviewer_notes": "レビュアーノート",
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
        "reviewer_notes": "검토자 노트",
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
        "reviewer_notes": "Prüfungshinweise",
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
        "reviewer_notes": "Notes du réviseur",
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
        "reviewer_notes": "Notas del revisor",
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
        "reviewer_notes": "Note del revisore",
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
        "reviewer_notes": "Notas do revisor",
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
        "reviewer_notes": "Замечания рецензента",
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
        "reviewer_notes": "ملاحظات المراجع",
    },
}


def _scorecard_strings(output_language: str) -> dict[str, str]:
    d = dict(_SCORECARD_I18N.get(output_language, _SCORECARD_I18N["English"]))
    # Tile label translations for "Market" and "Evidence" (TRL/MRL/IP stay as acronyms)
    _kpi = {
        "Simplified Chinese":  ("市场", "证据"),
        "Traditional Chinese": ("市場", "證據"),
        "Japanese":            ("市場", "証拠"),
        "Korean":              ("시장", "증거"),
        "German":              ("Markt", "Belege"),
        "French":              ("Marché", "Preuves"),
        "Spanish":             ("Mercado", "Evidencia"),
        "Italian":             ("Mercato", "Prove"),
        "Portuguese":          ("Mercado", "Evidências"),
        "Russian":             ("Рынок", "Доказательства"),
        "Arabic":              ("السوق", "الأدلة"),
    }
    km, ke = _kpi.get(output_language, ("Market", "Evidence"))
    d.setdefault("kpi_market", km)
    d.setdefault("kpi_evidence", ke)
    return d


# ---------------------------------------------------------------------------
# UI shell i18n — controls buttons, labels, headers, progress, history
# Keys here use the dropdown *value* (e.g. "Chinese", not "Simplified Chinese")
# so language_dd.value can be used directly without a mapping step.
# ---------------------------------------------------------------------------

_UI_I18N: dict[str, dict[str, str]] = {

    # ── English ─────────────────────────────────────────────────────────────
    "English": {
        "header_title": "Academic Commercialization Assessment",
        "header_desc": (
            "Enter a research topic to launch <strong style='color:#e5e5e5;'>6 specialized AI agents</strong>"
            " that assess commercialization readiness — producing a scored report with verified citations."
            " Agents 1–3 run in parallel; expected run time: <strong style='color:#e5e5e5;'>2–3 minutes</strong>."
            " Input any language — the report is generated in the same language."
        ),
        "chip_sources":   "📚 OpenAlex · Semantic Scholar",
        "chip_agents":    "🔬 6 AI Agents",
        "chip_metrics":   "📊 TRL · IP · Market · Evidence",
        "chip_citations": "✓ Verified Citations",
        "topic_label":        "Research Topic",
        "topic_placeholder":  "e.g., perovskite solar cells for building-integrated photovoltaics  |  例如：钠离子电池在电网储能中的商业化",
        "lang_label":         "Report Language",
        "profile_label":      "Industry Profile",
        "run_btn":            "▶  Run Analysis",
        "cancel_btn":         "⏹  Cancel",
        "cancel_msg":         "⏹  Analysis cancelled.",
        "pdf_accordion_label": "📄 Upload Paper PDF (optional)",
        "pdf_desc": (
            "Upload a PDF to anchor the analysis on a specific paper — it becomes the"
            " primary source <strong style='color:#9a9a9a;'>(A1)</strong> and the pipeline"
            " searches for supporting evidence around its contribution."
        ),
        "upload_label": "Upload PDF",
        "extract_btn":  "Extract Contribution",
        "paper_title_label":        "Title",
        "paper_contribution_label": "Core Contribution",
        "paper_domain_label":       "Application Domain",
        "paper_doi_label":          "DOI / URL",
        "paper_metrics_label":      "Key Metrics (one per line)",
        "paper_topic_label":  "🔍 This drives the pipeline search — edit to focus or broaden",
        "paper_divider":      "Analysis Topic",
        "clear_paper_btn":    "✕  Clear Paper",
        "paper_run_btn":      "▶  Run Analysis with this Paper",
        "stage_init":     "Source Collection & Validation",
        "stage_evidence": "Phase 1 — Evidence Collection (Academic · Patent · Market)",
        "stage_writing":  "Agent 4 — Report Writing",
        "stage_review":   "Agent 5 — Quality Review & Citation Check",
        "stage_scoring":  "Agent 6 — Commercialization Scoring",
        "agent_academic": "Agent 1 — Academic Literature Analysis",
        "agent_patent":   "Agent 2 — Patent Landscape Analysis",
        "agent_market":   "Agent 3 — Market Intelligence Analysis",
        "sources_prefix": "Sources: ",
        "src_header":   "Collected Sources",
        "src_academic": "Academic",
        "src_patent":   "Patent",
        "src_market":   "Market",
        "src_evidence": "Evidence",
        "hist_desc":     "Past runs — paste a Run ID below to reload any report",
        "hist_refresh":  "↻  Refresh",
        "hist_cleanup":  "🗑  Keep Latest 20",
        "hist_filter":   "Filter by topic…",
        "hist_hint":     "Click any row to fill the Run ID field below",
        "hist_col_time":     "Time",
        "hist_col_topic":    "Topic",
        "hist_col_duration": "Duration",
        "hist_col_score":    "Score",
        "hist_col_status":   "Status",
        "hist_col_runid":    "Run ID",
        "run_id_label":  "Run ID",
        "load_btn":      "Load",
        "lang_badge_prefix": "Report language: ",
        "tab_analysis":  "Analysis",
        "tab_history":   "History",
    },

    # ── Simplified Chinese ───────────────────────────────────────────────────
    "Chinese": {
        "header_title": "学术成果商业化评估",
        "header_desc": (
            "输入研究主题，启动 <strong style='color:#e5e5e5;'>6 个专业 AI 智能体</strong>"
            "评估商业化可行性，生成带有核实引用的评分报告。"
            "智能体 1–3 并行运行，预计耗时 <strong style='color:#e5e5e5;'>2–3 分钟</strong>。"
            "支持任意语言输入，报告语言与输入一致。"
        ),
        "chip_sources":   "📚 OpenAlex · Semantic Scholar",
        "chip_agents":    "🔬 6 个 AI 智能体",
        "chip_metrics":   "📊 TRL · IP · 市场 · 证据",
        "chip_citations": "✓ 核实引用",
        "topic_label":        "研究主题",
        "topic_placeholder":  "例如：钠离子电池在电网储能中的商业化  |  e.g., perovskite solar cells",
        "lang_label":         "报告语言",
        "profile_label":      "行业类型",
        "run_btn":            "▶  运行分析",
        "cancel_btn":         "⏹  取消",
        "cancel_msg":         "⏹  分析已取消。",
        "pdf_accordion_label": "📄 上传论文 PDF（可选）",
        "pdf_desc": (
            "上传 PDF 可将分析锚定在特定论文上——该论文成为主要来源"
            "<strong style='color:#9a9a9a;'>（A1）</strong>，管线围绕其贡献搜索支撑证据。"
        ),
        "upload_label": "上传 PDF",
        "extract_btn":  "提取核心贡献",
        "paper_title_label":        "标题",
        "paper_contribution_label": "核心贡献",
        "paper_domain_label":       "应用领域",
        "paper_doi_label":          "DOI / 链接",
        "paper_metrics_label":      "关键指标（每行一项）",
        "paper_topic_label":  "🔍 此主题驱动管线搜索 — 可编辑以聚焦或拓宽范围",
        "paper_divider":      "分析主题",
        "clear_paper_btn":    "✕  清空论文",
        "paper_run_btn":      "▶  基于此论文运行分析",
        "stage_init":     "来源收集与验证",
        "stage_evidence": "阶段一 — 证据收集（学术 · 专利 · 市场）",
        "stage_writing":  "智能体 4 — 报告撰写",
        "stage_review":   "智能体 5 — 质量审查与引用核实",
        "stage_scoring":  "智能体 6 — 商业化评分",
        "agent_academic": "智能体 1 — 学术文献分析",
        "agent_patent":   "智能体 2 — 专利格局分析",
        "agent_market":   "智能体 3 — 市场情报分析",
        "sources_prefix": "来源：",
        "src_header":   "已收集来源",
        "src_academic": "学术",
        "src_patent":   "专利",
        "src_market":   "市场",
        "src_evidence": "证据",
        "hist_desc":     "历史运行记录 — 在下方粘贴运行 ID 可重新加载任意报告",
        "hist_refresh":  "↻  刷新",
        "hist_cleanup":  "🗑  保留最新 20 条",
        "hist_filter":   "按主题筛选…",
        "hist_hint":     "点击任意行自动填充下方运行 ID",
        "hist_col_time":     "时间",
        "hist_col_topic":    "主题",
        "hist_col_duration": "耗时",
        "hist_col_score":    "评分",
        "hist_col_status":   "状态",
        "hist_col_runid":    "运行 ID",
        "run_id_label":  "运行 ID",
        "load_btn":      "加载",
        "lang_badge_prefix": "报告语言：",
        "tab_analysis":  "分析",
        "tab_history":   "历史",
    },

    # ── Japanese ─────────────────────────────────────────────────────────────
    "Japanese": {
        "header_title": "学術商業化評価システム",
        "header_desc": (
            "研究トピックを入力して、商業化の準備状況を評価する"
            "<strong style='color:#e5e5e5;'>6 つの専門 AI エージェント</strong>を起動します。"
            "検証済み引用を含むスコアレポートを生成します。エージェント 1–3 は並列実行、"
            "所要時間は <strong style='color:#e5e5e5;'>2–3 分</strong>。"
            "任意の言語で入力可能 — レポートは同じ言語で生成されます。"
        ),
        "chip_sources":   "📚 OpenAlex · Semantic Scholar",
        "chip_agents":    "🔬 AI エージェント × 6",
        "chip_metrics":   "📊 TRL · IP · 市場 · 証拠",
        "chip_citations": "✓ 検証済み引用",
        "topic_label":        "研究トピック",
        "topic_placeholder":  "例：ペロブスカイト太陽電池の建物一体型光発電への応用",
        "lang_label":         "レポート言語",
        "profile_label":      "業界プロファイル",
        "run_btn":            "▶  分析を実行",
        "cancel_btn":         "⏹  キャンセル",
        "cancel_msg":         "⏹  分析をキャンセルしました。",
        "pdf_accordion_label": "📄 論文 PDF のアップロード（任意）",
        "pdf_desc": (
            "PDF をアップロードすることで特定の論文に分析を固定できます。"
            "その論文が主要ソース <strong style='color:#9a9a9a;'>（A1）</strong> となり、"
            "パイプラインはその貢献の周辺で裏付け証拠を検索します。"
        ),
        "upload_label": "PDF をアップロード",
        "extract_btn":  "貢献内容を抽出",
        "paper_title_label":        "タイトル",
        "paper_contribution_label": "主要貢献",
        "paper_domain_label":       "応用分野",
        "paper_doi_label":          "DOI / URL",
        "paper_metrics_label":      "主要指標（1 行 1 項目）",
        "paper_topic_label":  "🔍 このトピックがパイプライン検索を駆動します — 編集して焦点を絞ることができます",
        "paper_divider":      "分析トピック",
        "clear_paper_btn":    "✕  論文をクリア",
        "paper_run_btn":      "▶  この論文で分析を実行",
        "stage_init":     "ソース収集と検証",
        "stage_evidence": "フェーズ 1 — 証拠収集（学術 · 特許 · 市場）",
        "stage_writing":  "エージェント 4 — レポート作成",
        "stage_review":   "エージェント 5 — 品質レビューと引用確認",
        "stage_scoring":  "エージェント 6 — 商業化スコアリング",
        "agent_academic": "エージェント 1 — 学術文献分析",
        "agent_patent":   "エージェント 2 — 特許状況分析",
        "agent_market":   "エージェント 3 — 市場情報分析",
        "sources_prefix": "ソース：",
        "src_header":   "収集済みソース",
        "src_academic": "学術",
        "src_patent":   "特許",
        "src_market":   "市場",
        "src_evidence": "証拠",
        "hist_desc":     "過去の実行 — 下のフィールドに実行 ID を貼り付けてレポートを再読み込み",
        "hist_refresh":  "↻  更新",
        "hist_cleanup":  "🗑  最新 20 件を保持",
        "hist_filter":   "トピックでフィルタ…",
        "hist_hint":     "任意の行をクリックして下の実行 ID フィールドに入力",
        "hist_col_time":     "時刻",
        "hist_col_topic":    "トピック",
        "hist_col_duration": "所要時間",
        "hist_col_score":    "スコア",
        "hist_col_status":   "ステータス",
        "hist_col_runid":    "実行 ID",
        "run_id_label":  "実行 ID",
        "load_btn":      "読み込む",
        "lang_badge_prefix": "レポート言語：",
        "tab_analysis":  "分析",
        "tab_history":   "履歴",
    },

    # ── Korean ───────────────────────────────────────────────────────────────
    "Korean": {
        "header_title": "학술 상업화 평가 시스템",
        "header_desc": (
            "연구 주제를 입력하여 상업화 준비도를 평가하는"
            " <strong style='color:#e5e5e5;'>6개의 전문 AI 에이전트</strong>를 실행합니다."
            " 검증된 인용이 포함된 점수 보고서를 생성합니다."
            " 에이전트 1–3은 병렬 실행, 예상 소요 시간:"
            " <strong style='color:#e5e5e5;'>2–3분</strong>."
            " 어떤 언어로도 입력 가능 — 보고서는 같은 언어로 생성됩니다."
        ),
        "chip_sources":   "📚 OpenAlex · Semantic Scholar",
        "chip_agents":    "🔬 AI 에이전트 6개",
        "chip_metrics":   "📊 TRL · IP · 시장 · 증거",
        "chip_citations": "✓ 검증된 인용",
        "topic_label":        "연구 주제",
        "topic_placeholder":  "예: 페로브스카이트 태양전지의 건물 일체형 광전지 응용",
        "lang_label":         "보고서 언어",
        "profile_label":      "산업 프로파일",
        "run_btn":            "▶  분석 실행",
        "cancel_btn":         "⏹  취소",
        "cancel_msg":         "⏹  분석이 취소되었습니다.",
        "pdf_accordion_label": "📄 논문 PDF 업로드 (선택사항)",
        "pdf_desc": (
            "PDF를 업로드하면 특정 논문에 분석을 고정할 수 있습니다."
            " 해당 논문이 주요 소스 <strong style='color:#9a9a9a;'>(A1)</strong>가 되고"
            " 파이프라인은 그 기여 주변에서 지원 증거를 검색합니다."
        ),
        "upload_label": "PDF 업로드",
        "extract_btn":  "기여 내용 추출",
        "paper_title_label":        "제목",
        "paper_contribution_label": "핵심 기여",
        "paper_domain_label":       "응용 분야",
        "paper_doi_label":          "DOI / URL",
        "paper_metrics_label":      "주요 지표 (한 줄에 하나씩)",
        "paper_topic_label":  "🔍 이 주제가 파이프라인 검색을 구동합니다 — 편집하여 초점 조정 가능",
        "paper_divider":      "분석 주제",
        "clear_paper_btn":    "✕  논문 지우기",
        "paper_run_btn":      "▶  이 논문으로 분석 실행",
        "stage_init":     "소스 수집 및 검증",
        "stage_evidence": "단계 1 — 증거 수집 (학술 · 특허 · 시장)",
        "stage_writing":  "에이전트 4 — 보고서 작성",
        "stage_review":   "에이전트 5 — 품질 검토 및 인용 확인",
        "stage_scoring":  "에이전트 6 — 상업화 점수 산정",
        "agent_academic": "에이전트 1 — 학술 문헌 분석",
        "agent_patent":   "에이전트 2 — 특허 현황 분석",
        "agent_market":   "에이전트 3 — 시장 정보 분석",
        "sources_prefix": "출처: ",
        "src_header":   "수집된 출처",
        "src_academic": "학술",
        "src_patent":   "특허",
        "src_market":   "시장",
        "src_evidence": "증거",
        "hist_desc":     "이전 실행 — 아래에 실행 ID를 붙여넣어 보고서를 다시 로드",
        "hist_refresh":  "↻  새로고침",
        "hist_cleanup":  "🗑  최신 20개 유지",
        "hist_filter":   "주제로 필터링…",
        "hist_hint":     "행을 클릭하면 아래 실행 ID 필드에 자동 입력됩니다",
        "hist_col_time":     "시간",
        "hist_col_topic":    "주제",
        "hist_col_duration": "소요 시간",
        "hist_col_score":    "점수",
        "hist_col_status":   "상태",
        "hist_col_runid":    "실행 ID",
        "run_id_label":  "실행 ID",
        "load_btn":      "불러오기",
        "lang_badge_prefix": "보고서 언어: ",
        "tab_analysis":  "분석",
        "tab_history":   "기록",
    },

    # ── French ───────────────────────────────────────────────────────────────
    "French": {
        "header_title": "Évaluation de la Commercialisation Académique",
        "header_desc": (
            "Saisissez un sujet de recherche pour lancer"
            " <strong style='color:#e5e5e5;'>6 agents IA spécialisés</strong>"
            " qui évaluent la maturité commerciale — produisant un rapport noté avec des citations vérifiées."
            " Les agents 1–3 s'exécutent en parallèle ; durée prévue :"
            " <strong style='color:#e5e5e5;'>2–3 minutes</strong>."
            " Saisie dans n'importe quelle langue — le rapport est généré dans la même langue."
        ),
        "chip_sources":   "📚 OpenAlex · Semantic Scholar",
        "chip_agents":    "🔬 6 agents IA",
        "chip_metrics":   "📊 TRL · PI · Marché · Preuves",
        "chip_citations": "✓ Citations vérifiées",
        "topic_label":        "Sujet de recherche",
        "topic_placeholder":  "ex. : cellules solaires pérovskites pour la photovoltaïque intégrée au bâtiment",
        "lang_label":         "Langue du rapport",
        "profile_label":      "Profil industriel",
        "run_btn":            "▶  Lancer l'analyse",
        "cancel_btn":         "⏹  Annuler",
        "cancel_msg":         "⏹  Analyse annulée.",
        "pdf_accordion_label": "📄 Importer un PDF (facultatif)",
        "pdf_desc": (
            "Importez un PDF pour ancrer l'analyse sur un article spécifique —"
            " il devient la source principale <strong style='color:#9a9a9a;'>(A1)</strong>"
            " et le pipeline recherche des preuves autour de sa contribution."
        ),
        "upload_label": "Importer un PDF",
        "extract_btn":  "Extraire la contribution",
        "paper_title_label":        "Titre",
        "paper_contribution_label": "Contribution principale",
        "paper_domain_label":       "Domaine d'application",
        "paper_doi_label":          "DOI / URL",
        "paper_metrics_label":      "Indicateurs clés (un par ligne)",
        "paper_topic_label":  "🔍 Ce sujet guide la recherche du pipeline — modifiez pour affiner ou élargir",
        "paper_divider":      "Sujet d'analyse",
        "clear_paper_btn":    "✕  Supprimer l'article",
        "paper_run_btn":      "▶  Analyser avec cet article",
        "stage_init":     "Collecte et validation des sources",
        "stage_evidence": "Phase 1 — Collecte de preuves (Académique · Brevets · Marché)",
        "stage_writing":  "Agent 4 — Rédaction du rapport",
        "stage_review":   "Agent 5 — Révision qualité et vérification des citations",
        "stage_scoring":  "Agent 6 — Notation de la commercialisation",
        "agent_academic": "Agent 1 — Analyse de la littérature académique",
        "agent_patent":   "Agent 2 — Analyse du paysage de brevets",
        "agent_market":   "Agent 3 — Analyse du renseignement de marché",
        "sources_prefix": "Sources : ",
        "src_header":   "Sources collectées",
        "src_academic": "Académique",
        "src_patent":   "Brevet",
        "src_market":   "Marché",
        "src_evidence": "Preuves",
        "hist_desc":     "Exécutions passées — collez un ID d'exécution ci-dessous pour recharger un rapport",
        "hist_refresh":  "↻  Actualiser",
        "hist_cleanup":  "🗑  Garder les 20 dernières",
        "hist_filter":   "Filtrer par sujet…",
        "hist_hint":     "Cliquez sur une ligne pour remplir le champ ID ci-dessous",
        "hist_col_time":     "Heure",
        "hist_col_topic":    "Sujet",
        "hist_col_duration": "Durée",
        "hist_col_score":    "Score",
        "hist_col_status":   "Statut",
        "hist_col_runid":    "ID d'exécution",
        "run_id_label":  "ID d'exécution",
        "load_btn":      "Charger",
        "lang_badge_prefix": "Langue du rapport : ",
        "tab_analysis":  "Analyse",
        "tab_history":   "Historique",
    },

    # ── German ───────────────────────────────────────────────────────────────
    "German": {
        "header_title": "Akademische Kommerzialisierungsbewertung",
        "header_desc": (
            "Geben Sie ein Forschungsthema ein, um"
            " <strong style='color:#e5e5e5;'>6 spezialisierte KI-Agenten</strong>"
            " zu starten, die die Kommerzialisierungsbereitschaft bewerten."
            " Erwartete Laufzeit: <strong style='color:#e5e5e5;'>2–3 Minuten</strong>."
            " Eingabe in beliebiger Sprache — Bericht wird in derselben Sprache erstellt."
        ),
        "chip_sources":   "📚 OpenAlex · Semantic Scholar",
        "chip_agents":    "🔬 6 KI-Agenten",
        "chip_metrics":   "📊 TRL · IP · Markt · Belege",
        "chip_citations": "✓ Geprüfte Zitate",
        "topic_label":        "Forschungsthema",
        "topic_placeholder":  "z. B.: Perowskit-Solarzellen für gebäudeintegrierte Photovoltaik",
        "lang_label":         "Berichtssprache",
        "profile_label":      "Branchenprofil",
        "run_btn":            "▶  Analyse starten",
        "cancel_btn":         "⏹  Abbrechen",
        "cancel_msg":         "⏹  Analyse abgebrochen.",
        "pdf_accordion_label": "📄 PDF hochladen (optional)",
        "pdf_desc": (
            "Laden Sie ein PDF hoch, um die Analyse auf ein bestimmtes Paper zu fixieren —"
            " es wird zur Hauptquelle <strong style='color:#9a9a9a;'>(A1)</strong>"
            " und die Pipeline sucht nach unterstützenden Belegen."
        ),
        "upload_label": "PDF hochladen",
        "extract_btn":  "Beitrag extrahieren",
        "paper_title_label":        "Titel",
        "paper_contribution_label": "Hauptbeitrag",
        "paper_domain_label":       "Anwendungsgebiet",
        "paper_doi_label":          "DOI / URL",
        "paper_metrics_label":      "Schlüsselkennzahlen (eine pro Zeile)",
        "paper_topic_label":  "🔍 Dieses Thema steuert die Pipeline-Suche — bearbeiten zum Eingrenzen oder Erweitern",
        "paper_divider":      "Analysethema",
        "clear_paper_btn":    "✕  Paper entfernen",
        "paper_run_btn":      "▶  Analyse mit diesem Paper starten",
        "stage_init":     "Quellensammlung und -validierung",
        "stage_evidence": "Phase 1 — Beweiserhebung (Akademisch · Patent · Markt)",
        "stage_writing":  "Agent 4 — Berichtserstellung",
        "stage_review":   "Agent 5 — Qualitätsprüfung und Zitationscheck",
        "stage_scoring":  "Agent 6 — Kommerzialisierungsbewertung",
        "agent_academic": "Agent 1 — Analyse der Fachliteratur",
        "agent_patent":   "Agent 2 — Patentlandschaftsanalyse",
        "agent_market":   "Agent 3 — Marktanalyse",
        "sources_prefix": "Quellen: ",
        "src_header":   "Gesammelte Quellen",
        "src_academic": "Akademisch",
        "src_patent":   "Patent",
        "src_market":   "Markt",
        "src_evidence": "Belege",
        "hist_desc":     "Frühere Analysen — Ausführungs-ID unten einfügen, um einen Bericht neu zu laden",
        "hist_refresh":  "↻  Aktualisieren",
        "hist_cleanup":  "🗑  Neueste 20 behalten",
        "hist_filter":   "Nach Thema filtern…",
        "hist_hint":     "Zeile anklicken, um die Ausführungs-ID unten automatisch auszufüllen",
        "hist_col_time":     "Zeit",
        "hist_col_topic":    "Thema",
        "hist_col_duration": "Dauer",
        "hist_col_score":    "Bewertung",
        "hist_col_status":   "Status",
        "hist_col_runid":    "Ausführungs-ID",
        "run_id_label":  "Ausführungs-ID",
        "load_btn":      "Laden",
        "lang_badge_prefix": "Berichtssprache: ",
        "tab_analysis":  "Analyse",
        "tab_history":   "Verlauf",
    },

    # ── Spanish ──────────────────────────────────────────────────────────────
    "Spanish": {
        "header_title": "Evaluación de Comercialización Académica",
        "header_desc": (
            "Introduzca un tema de investigación para lanzar"
            " <strong style='color:#e5e5e5;'>6 agentes de IA especializados</strong>"
            " que evalúan la preparación para la comercialización."
            " Tiempo estimado: <strong style='color:#e5e5e5;'>2–3 minutos</strong>."
            " Ingrese en cualquier idioma — el informe se genera en el mismo idioma."
        ),
        "chip_sources":   "📚 OpenAlex · Semantic Scholar",
        "chip_agents":    "🔬 6 agentes de IA",
        "chip_metrics":   "📊 TRL · PI · Mercado · Evidencia",
        "chip_citations": "✓ Citas verificadas",
        "topic_label":        "Tema de investigación",
        "topic_placeholder":  "ej.: células solares de perovskita para fotovoltaica integrada en edificios",
        "lang_label":         "Idioma del informe",
        "profile_label":      "Perfil industrial",
        "run_btn":            "▶  Ejecutar análisis",
        "cancel_btn":         "⏹  Cancelar",
        "cancel_msg":         "⏹  Análisis cancelado.",
        "pdf_accordion_label": "📄 Subir PDF del artículo (opcional)",
        "pdf_desc": (
            "Suba un PDF para anclar el análisis en un artículo específico —"
            " se convierte en la fuente principal <strong style='color:#9a9a9a;'>(A1)</strong>"
            " y el pipeline busca evidencia de apoyo alrededor de su contribución."
        ),
        "upload_label": "Subir PDF",
        "extract_btn":  "Extraer contribución",
        "paper_title_label":        "Título",
        "paper_contribution_label": "Contribución principal",
        "paper_domain_label":       "Dominio de aplicación",
        "paper_doi_label":          "DOI / URL",
        "paper_metrics_label":      "Métricas clave (una por línea)",
        "paper_topic_label":  "🔍 Este tema guía la búsqueda del pipeline — edite para enfocar o ampliar",
        "paper_divider":      "Tema de análisis",
        "clear_paper_btn":    "✕  Borrar artículo",
        "paper_run_btn":      "▶  Analizar con este artículo",
        "stage_init":     "Recopilación y validación de fuentes",
        "stage_evidence": "Fase 1 — Recopilación de evidencia (Académica · Patentes · Mercado)",
        "stage_writing":  "Agente 4 — Redacción del informe",
        "stage_review":   "Agente 5 — Revisión de calidad y citas",
        "stage_scoring":  "Agente 6 — Puntuación de comercialización",
        "agent_academic": "Agente 1 — Análisis de literatura académica",
        "agent_patent":   "Agente 2 — Análisis del panorama de patentes",
        "agent_market":   "Agente 3 — Análisis de inteligencia de mercado",
        "sources_prefix": "Fuentes: ",
        "src_header":   "Fuentes recopiladas",
        "src_academic": "Académica",
        "src_patent":   "Patente",
        "src_market":   "Mercado",
        "src_evidence": "Evidencia",
        "hist_desc":     "Ejecuciones anteriores — pegue un ID de ejecución abajo para recargar un informe",
        "hist_refresh":  "↻  Actualizar",
        "hist_cleanup":  "🗑  Mantener últimas 20",
        "hist_filter":   "Filtrar por tema…",
        "hist_hint":     "Haga clic en cualquier fila para rellenar el campo ID de ejecución",
        "hist_col_time":     "Hora",
        "hist_col_topic":    "Tema",
        "hist_col_duration": "Duración",
        "hist_col_score":    "Puntuación",
        "hist_col_status":   "Estado",
        "hist_col_runid":    "ID de ejecución",
        "run_id_label":  "ID de ejecución",
        "load_btn":      "Cargar",
        "lang_badge_prefix": "Idioma del informe: ",
        "tab_analysis":  "Análisis",
        "tab_history":   "Historial",
    },

    # ── Portuguese ───────────────────────────────────────────────────────────
    "Portuguese": {
        "header_title": "Avaliação de Comercialização Académica",
        "header_desc": (
            "Insira um tema de pesquisa para lançar"
            " <strong style='color:#e5e5e5;'>6 agentes de IA especializados</strong>"
            " que avaliam a prontidão para comercialização."
            " Tempo estimado: <strong style='color:#e5e5e5;'>2–3 minutos</strong>."
            " Entrada em qualquer idioma — o relatório é gerado no mesmo idioma."
        ),
        "chip_sources":   "📚 OpenAlex · Semantic Scholar",
        "chip_agents":    "🔬 6 agentes de IA",
        "chip_metrics":   "📊 TRL · PI · Mercado · Evidências",
        "chip_citations": "✓ Citações verificadas",
        "topic_label":        "Tema de pesquisa",
        "topic_placeholder":  "ex.: células solares de perovskita para fotovoltaica integrada em edifícios",
        "lang_label":         "Idioma do relatório",
        "profile_label":      "Perfil industrial",
        "run_btn":            "▶  Executar análise",
        "cancel_btn":         "⏹  Cancelar",
        "cancel_msg":         "⏹  Análise cancelada.",
        "pdf_accordion_label": "📄 Carregar PDF do artigo (opcional)",
        "pdf_desc": (
            "Carregue um PDF para ancorar a análise num artigo específico —"
            " torna-se a fonte principal <strong style='color:#9a9a9a;'>(A1)</strong>"
            " e o pipeline procura evidências de suporte em torno da sua contribuição."
        ),
        "upload_label": "Carregar PDF",
        "extract_btn":  "Extrair contribuição",
        "paper_title_label":        "Título",
        "paper_contribution_label": "Contribuição principal",
        "paper_domain_label":       "Domínio de aplicação",
        "paper_doi_label":          "DOI / URL",
        "paper_metrics_label":      "Métricas-chave (uma por linha)",
        "paper_topic_label":  "🔍 Este tema guia a pesquisa do pipeline — edite para focar ou ampliar",
        "paper_divider":      "Tema de análise",
        "clear_paper_btn":    "✕  Limpar artigo",
        "paper_run_btn":      "▶  Analisar com este artigo",
        "stage_init":     "Recolha e validação de fontes",
        "stage_evidence": "Fase 1 — Recolha de evidências (Académica · Patentes · Mercado)",
        "stage_writing":  "Agente 4 — Redação do relatório",
        "stage_review":   "Agente 5 — Revisão de qualidade e citações",
        "stage_scoring":  "Agente 6 — Pontuação de comercialização",
        "agent_academic": "Agente 1 — Análise de literatura académica",
        "agent_patent":   "Agente 2 — Análise do panorama de patentes",
        "agent_market":   "Agente 3 — Análise de inteligência de mercado",
        "sources_prefix": "Fontes: ",
        "src_header":   "Fontes recolhidas",
        "src_academic": "Académica",
        "src_patent":   "Patente",
        "src_market":   "Mercado",
        "src_evidence": "Evidências",
        "hist_desc":     "Execuções anteriores — cole um ID de execução abaixo para recarregar um relatório",
        "hist_refresh":  "↻  Atualizar",
        "hist_cleanup":  "🗑  Manter últimas 20",
        "hist_filter":   "Filtrar por tema…",
        "hist_hint":     "Clique em qualquer linha para preencher o campo ID de execução",
        "hist_col_time":     "Hora",
        "hist_col_topic":    "Tema",
        "hist_col_duration": "Duração",
        "hist_col_score":    "Pontuação",
        "hist_col_status":   "Estado",
        "hist_col_runid":    "ID de execução",
        "run_id_label":  "ID de execução",
        "load_btn":      "Carregar",
        "lang_badge_prefix": "Idioma do relatório: ",
        "tab_analysis":  "Análise",
        "tab_history":   "Histórico",
    },

    # ── Arabic ───────────────────────────────────────────────────────────────
    "Arabic": {
        "header_title": "تقييم التسويق الأكاديمي",
        "header_desc": (
            "أدخل موضوع بحثيًا لتشغيل"
            " <strong style='color:#e5e5e5;'>6 وكلاء ذكاء اصطناعي متخصصين</strong>"
            " يقيّمون الجاهزية التجارية — مع تقرير مُقيَّم ومراجع موثّقة."
            " الوكلاء 1–3 يعملون بالتوازي؛ الوقت المتوقع:"
            " <strong style='color:#e5e5e5;'>2–3 دقائق</strong>."
            " أدخل بأي لغة — يُنشأ التقرير بنفس اللغة."
        ),
        "chip_sources":   "📚 OpenAlex · Semantic Scholar",
        "chip_agents":    "🔬 6 وكلاء ذكاء اصطناعي",
        "chip_metrics":   "📊 TRL · PI · السوق · الأدلة",
        "chip_citations": "✓ مراجع موثّقة",
        "topic_label":        "موضوع البحث",
        "topic_placeholder":  "مثال: خلايا شمسية بيروفسكيت للطاقة الكهروضوئية المتكاملة في المباني",
        "lang_label":         "لغة التقرير",
        "profile_label":      "الملف الصناعي",
        "run_btn":            "▶  تشغيل التحليل",
        "cancel_btn":         "⏹  إلغاء",
        "cancel_msg":         "⏹  تم إلغاء التحليل.",
        "pdf_accordion_label": "📄 تحميل ملف PDF للورقة (اختياري)",
        "pdf_desc": (
            "قم بتحميل ملف PDF لتثبيت التحليل على ورقة بحثية محددة —"
            " ستصبح المصدر الرئيسي <strong style='color:#9a9a9a;'>(A1)</strong>"
            " ويبحث النظام عن أدلة داعمة حول مساهمتها."
        ),
        "upload_label": "تحميل PDF",
        "extract_btn":  "استخراج المساهمة",
        "paper_title_label":        "العنوان",
        "paper_contribution_label": "المساهمة الرئيسية",
        "paper_domain_label":       "مجال التطبيق",
        "paper_doi_label":          "DOI / الرابط",
        "paper_metrics_label":      "المقاييس الرئيسية (سطر واحد لكل مقياس)",
        "paper_topic_label":  "🔍 هذا الموضوع يقود بحث النظام — يمكن تعديله للتركيز أو التوسيع",
        "paper_divider":      "موضوع التحليل",
        "clear_paper_btn":    "✕  مسح الورقة",
        "paper_run_btn":      "▶  تشغيل التحليل مع هذه الورقة",
        "stage_init":     "جمع المصادر والتحقق منها",
        "stage_evidence": "المرحلة 1 — جمع الأدلة (أكاديمية · براءات اختراع · سوق)",
        "stage_writing":  "الوكيل 4 — كتابة التقرير",
        "stage_review":   "الوكيل 5 — مراجعة الجودة والاستشهادات",
        "stage_scoring":  "الوكيل 6 — تقييم التسويق",
        "agent_academic": "الوكيل 1 — تحليل الأدبيات الأكاديمية",
        "agent_patent":   "الوكيل 2 — تحليل مشهد براءات الاختراع",
        "agent_market":   "الوكيل 3 — تحليل معلومات السوق",
        "sources_prefix": "المصادر: ",
        "src_header":   "المصادر المجمّعة",
        "src_academic": "أكاديمي",
        "src_patent":   "براءة اختراع",
        "src_market":   "سوق",
        "src_evidence": "أدلة",
        "hist_desc":     "عمليات التشغيل السابقة — الصق معرّف التشغيل أدناه لإعادة تحميل أي تقرير",
        "hist_refresh":  "↻  تحديث",
        "hist_cleanup":  "🗑  الاحتفاظ بآخر 20",
        "hist_filter":   "تصفية حسب الموضوع…",
        "hist_hint":     "انقر على أي صف لملء حقل معرّف التشغيل أدناه",
        "hist_col_time":     "الوقت",
        "hist_col_topic":    "الموضوع",
        "hist_col_duration": "المدة",
        "hist_col_score":    "النتيجة",
        "hist_col_status":   "الحالة",
        "hist_col_runid":    "معرّف التشغيل",
        "run_id_label":  "معرّف التشغيل",
        "load_btn":      "تحميل",
        "lang_badge_prefix": "لغة التقرير: ",
        "tab_analysis":  "التحليل",
        "tab_history":   "السجل",
    },

    # ── Russian ──────────────────────────────────────────────────────────────
    "Russian": {
        "header_title": "Оценка Коммерциализации Исследований",
        "header_desc": (
            "Введите тему исследования, чтобы запустить"
            " <strong style='color:#e5e5e5;'>6 специализированных ИИ-агентов</strong>,"
            " оценивающих готовность к коммерциализации."
            " Ожидаемое время выполнения: <strong style='color:#e5e5e5;'>2–3 минуты</strong>."
            " Ввод на любом языке — отчёт создаётся на том же языке."
        ),
        "chip_sources":   "📚 OpenAlex · Semantic Scholar",
        "chip_agents":    "🔬 6 ИИ-агентов",
        "chip_metrics":   "📊 TRL · ИС · Рынок · Доказательства",
        "chip_citations": "✓ Проверенные ссылки",
        "topic_label":        "Тема исследования",
        "topic_placeholder":  "напр.: перовскитные солнечные элементы для интегрированной в здания фотовольтаики",
        "lang_label":         "Язык отчёта",
        "profile_label":      "Отраслевой профиль",
        "run_btn":            "▶  Запустить анализ",
        "cancel_btn":         "⏹  Отмена",
        "cancel_msg":         "⏹  Анализ отменён.",
        "pdf_accordion_label": "📄 Загрузить PDF статьи (необязательно)",
        "pdf_desc": (
            "Загрузите PDF, чтобы зафиксировать анализ на конкретной статье —"
            " она становится основным источником <strong style='color:#9a9a9a;'>(A1)</strong>,"
            " а пайплайн ищет подтверждающие данные вокруг её вклада."
        ),
        "upload_label": "Загрузить PDF",
        "extract_btn":  "Извлечь вклад",
        "paper_title_label":        "Заголовок",
        "paper_contribution_label": "Основной вклад",
        "paper_domain_label":       "Область применения",
        "paper_doi_label":          "DOI / URL",
        "paper_metrics_label":      "Ключевые метрики (по одной на строку)",
        "paper_topic_label":  "🔍 Эта тема управляет поиском пайплайна — редактируйте для уточнения или расширения",
        "paper_divider":      "Тема анализа",
        "clear_paper_btn":    "✕  Очистить статью",
        "paper_run_btn":      "▶  Запустить анализ с этой статьёй",
        "stage_init":     "Сбор и валидация источников",
        "stage_evidence": "Фаза 1 — Сбор данных (Академические · Патенты · Рынок)",
        "stage_writing":  "Агент 4 — Написание отчёта",
        "stage_review":   "Агент 5 — Контроль качества и проверка ссылок",
        "stage_scoring":  "Агент 6 — Оценка коммерциализации",
        "agent_academic": "Агент 1 — Анализ академической литературы",
        "agent_patent":   "Агент 2 — Анализ патентного ландшафта",
        "agent_market":   "Агент 3 — Анализ рыночной информации",
        "sources_prefix": "Источники: ",
        "src_header":   "Собранные источники",
        "src_academic": "Академические",
        "src_patent":   "Патент",
        "src_market":   "Рынок",
        "src_evidence": "Доказательства",
        "hist_desc":     "Прошлые запуски — вставьте ID запуска ниже для перезагрузки отчёта",
        "hist_refresh":  "↻  Обновить",
        "hist_cleanup":  "🗑  Оставить последние 20",
        "hist_filter":   "Фильтр по теме…",
        "hist_hint":     "Нажмите на строку, чтобы заполнить поле ID запуска",
        "hist_col_time":     "Время",
        "hist_col_topic":    "Тема",
        "hist_col_duration": "Длительность",
        "hist_col_score":    "Оценка",
        "hist_col_status":   "Статус",
        "hist_col_runid":    "ID запуска",
        "run_id_label":  "ID запуска",
        "load_btn":      "Загрузить",
        "lang_badge_prefix": "Язык отчёта: ",
        "tab_analysis":  "Анализ",
        "tab_history":   "История",
    },

    # ── Hindi ────────────────────────────────────────────────────────────────
    "Hindi": {
        "header_title": "शैक्षणिक व्यावसायीकरण मूल्यांकन",
        "header_desc": (
            "व्यावसायीकरण तैयारी का मूल्यांकन करने के लिए एक शोध विषय दर्ज करें और"
            " <strong style='color:#e5e5e5;'>6 विशेष AI एजेंट</strong> लॉन्च करें।"
            " अपेक्षित समय: <strong style='color:#e5e5e5;'>2–3 मिनट</strong>।"
            " किसी भी भाषा में इनपुट करें — रिपोर्ट उसी भाषा में बनाई जाती है।"
        ),
        "chip_sources":   "📚 OpenAlex · Semantic Scholar",
        "chip_agents":    "🔬 6 AI एजेंट",
        "chip_metrics":   "📊 TRL · IP · बाज़ार · साक्ष्य",
        "chip_citations": "✓ सत्यापित उद्धरण",
        "topic_label":        "शोध विषय",
        "topic_placeholder":  "उदा.: पेरोव्सकाइट सौर सेल का भवन-एकीकृत फोटोवोल्टिक में उपयोग",
        "lang_label":         "रिपोर्ट भाषा",
        "profile_label":      "उद्योग प्रोफाइल",
        "run_btn":            "▶  विश्लेषण चलाएं",
        "cancel_btn":         "⏹  रद्द करें",
        "cancel_msg":         "⏹  विश्लेषण रद्द किया गया।",
        "pdf_accordion_label": "📄 PDF अपलोड करें (वैकल्पिक)",
        "pdf_desc": (
            "किसी विशिष्ट पेपर पर विश्लेषण केंद्रित करने के लिए PDF अपलोड करें —"
            " यह प्राथमिक स्रोत <strong style='color:#9a9a9a;'>(A1)</strong> बन जाता है"
            " और पाइपलाइन उसके योगदान के आसपास साक्ष्य खोजती है।"
        ),
        "upload_label": "PDF अपलोड करें",
        "extract_btn":  "योगदान निकालें",
        "paper_title_label":        "शीर्षक",
        "paper_contribution_label": "मुख्य योगदान",
        "paper_domain_label":       "अनुप्रयोग क्षेत्र",
        "paper_doi_label":          "DOI / URL",
        "paper_metrics_label":      "मुख्य मेट्रिक्स (प्रति पंक्ति एक)",
        "paper_topic_label":  "🔍 यह विषय पाइपलाइन खोज को चलाता है — फ़ोकस करने या विस्तार के लिए संपादित करें",
        "paper_divider":      "विश्लेषण विषय",
        "clear_paper_btn":    "✕  पेपर साफ़ करें",
        "paper_run_btn":      "▶  इस पेपर से विश्लेषण चलाएं",
        "stage_init":     "स्रोत संग्रह और सत्यापन",
        "stage_evidence": "चरण 1 — साक्ष्य संग्रह (शैक्षणिक · पेटेंट · बाज़ार)",
        "stage_writing":  "एजेंट 4 — रिपोर्ट लेखन",
        "stage_review":   "एजेंट 5 — गुणवत्ता समीक्षा और उद्धरण जांच",
        "stage_scoring":  "एजेंट 6 — व्यावसायीकरण स्कोरिंग",
        "agent_academic": "एजेंट 1 — शैक्षणिक साहित्य विश्लेषण",
        "agent_patent":   "एजेंट 2 — पेटेंट परिदृश्य विश्लेषण",
        "agent_market":   "एजेंट 3 — बाज़ार सूचना विश्लेषण",
        "sources_prefix": "स्रोत: ",
        "src_header":   "एकत्रित स्रोत",
        "src_academic": "शैक्षणिक",
        "src_patent":   "पेटेंट",
        "src_market":   "बाज़ार",
        "src_evidence": "साक्ष्य",
        "hist_desc":     "पिछले विश्लेषण — किसी रिपोर्ट को पुनः लोड करने के लिए रन ID नीचे पेस्ट करें",
        "hist_refresh":  "↻  ताज़ा करें",
        "hist_cleanup":  "🗑  नवीनतम 20 रखें",
        "hist_filter":   "विषय से फ़िल्टर करें…",
        "hist_hint":     "नीचे रन ID भरने के लिए किसी भी पंक्ति पर क्लिक करें",
        "hist_col_time":     "समय",
        "hist_col_topic":    "विषय",
        "hist_col_duration": "अवधि",
        "hist_col_score":    "अंक",
        "hist_col_status":   "स्थिति",
        "hist_col_runid":    "रन ID",
        "run_id_label":  "रन ID",
        "load_btn":      "लोड करें",
        "lang_badge_prefix": "रिपोर्ट भाषा: ",
        "tab_analysis":  "विश्लेषण",
        "tab_history":   "इतिहास",
    },
}


def _ui(language: str) -> dict[str, str]:
    """Return UI string dict for the given report-language dropdown value."""
    key = language if language != "Auto (detect from topic)" else "English"
    return _UI_I18N.get(key, _UI_I18N["English"])


# ---------------------------------------------------------------------------
# Warning i18n
# ---------------------------------------------------------------------------

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
    "Hindi": {
        "title": "स्रोत कवरेज चेतावनी",
        "footer": "चिह्नित क्षेत्रों में विश्लेषण गुणवत्ता सीमित हो सकती है।",
        "ac_few": "⚠ शैक्षणिक: केवल {n} स्रोत (अनुशंसित ≥3)",
        "pa_few": "⚠ पेटेंट: केवल {n} स्रोत (अनुशंसित ≥2)",
        "mk_few": "⚠ बाज़ार: केवल {n} स्रोत (अनुशंसित ≥2)",
        "mk_stale": "⚠ बाज़ार: {stale}/{total} स्रोत बिना तारीख के या 3 वर्ष से पुराने — बाज़ार जानकारी पुरानी हो सकती है",
        "pat_old": "⚠ पेटेंट: {n}/{total} पेटेंट 15+ वर्ष पहले दाखिल — उपयोग से पहले कानूनी स्थिति सत्यापित करें",
        "ac_old": "⚠ शैक्षणिक: सबसे पुराना स्रोत {year} का है (\"{title}\") — तेज़ी से बढ़ते क्षेत्रों में निष्कर्ष वर्तमान स्थिति नहीं दर्शा सकते",
    },
}


def _warning_strings(output_language: str) -> dict[str, str]:
    return _WARNING_I18N.get(output_language, _WARNING_I18N["English"])


# ---------------------------------------------------------------------------
# Card labels (for paper extraction UI)
# ---------------------------------------------------------------------------

_CARD_LABELS_ZH = {
    "title":       "标题",
    "contribution":"核心贡献",
    "domain":      "应用领域",
    "doi":         "DOI / 链接",
    "metrics":     "关键指标（每行一项）",
    "topic":       "🔍 此主题驱动管线搜索 — 可编辑以聚焦或拓宽范围",
    "divider":     "分析主题",
    "clear_btn":   "✕  清空论文",
    "run_btn":     "▶  基于此论文运行分析",
}
_CARD_LABELS_EN = {
    "title":       "Title",
    "contribution":"Core Contribution",
    "domain":      "Application Domain",
    "doi":         "DOI / URL",
    "metrics":     "Key Metrics (one per line)",
    "topic":       "🔍 This drives the pipeline search — edit to focus or broaden",
    "divider":     "Analysis Topic",
    "clear_btn":   "✕  Clear Paper",
    "run_btn":     "▶  Run Analysis with this Paper",
}


# ---------------------------------------------------------------------------
# Profile choices
# ---------------------------------------------------------------------------

_PROFILE_CHOICES: dict[str, list[tuple[str, str]]] = {
    "Chinese": [
        ("自动检测（从主题判断）", "Auto (detect from topic)"),
        ("工业制造",            "industrial"),
        ("材料科学",            "material_science"),
        ("生物医药",            "biomedical"),
        ("清洁技术",            "clean_tech"),
        ("软件 / AI",          "software_ai"),
    ],
    "Japanese": [
        ("自動検出（トピックから）", "Auto (detect from topic)"),
        ("産業製造",              "industrial"),
        ("材料科学",              "material_science"),
        ("生物医学",              "biomedical"),
        ("クリーンテック",         "clean_tech"),
        ("ソフトウェア / AI",      "software_ai"),
    ],
    "Korean": [
        ("자동 감지 (주제에서)", "Auto (detect from topic)"),
        ("산업 제조",          "industrial"),
        ("재료 과학",          "material_science"),
        ("생물의학",           "biomedical"),
        ("클린테크",           "clean_tech"),
        ("소프트웨어 / AI",    "software_ai"),
    ],
    "Arabic": [
        ("كشف تلقائي (من الموضوع)", "Auto (detect from topic)"),
        ("التصنيع الصناعي",         "industrial"),
        ("علم المواد",              "material_science"),
        ("الطب الحيوي",            "biomedical"),
        ("التقنيات النظيفة",        "clean_tech"),
        ("البرمجيات / الذكاء الاصطناعي", "software_ai"),
    ],
    "Russian": [
        ("Авто (из темы)",   "Auto (detect from topic)"),
        ("Промышленность",   "industrial"),
        ("Материаловедение", "material_science"),
        ("Биомедицина",      "biomedical"),
        ("Чистые технологии","clean_tech"),
        ("ПО / ИИ",          "software_ai"),
    ],
    "Hindi": [
        ("स्वत: पहचान (विषय से)", "Auto (detect from topic)"),
        ("औद्योगिक",              "industrial"),
        ("सामग्री विज्ञान",        "material_science"),
        ("जैव चिकित्सा",           "biomedical"),
        ("स्वच्छ प्रौद्योगिकी",    "clean_tech"),
        ("सॉफ्टवेयर / AI",         "software_ai"),
    ],
}

_PROFILE_CHOICES_DEFAULT = [
    ("Auto (detect from topic)", "Auto (detect from topic)"),
    ("Industrial",      "industrial"),
    ("Material Science","material_science"),
    ("Biomedical",      "biomedical"),
    ("Clean Tech",      "clean_tech"),
    ("Software / AI",   "software_ai"),
]


def _profile_choices(lang: str) -> list[tuple[str, str]]:
    return _PROFILE_CHOICES.get(lang, _PROFILE_CHOICES_DEFAULT)
