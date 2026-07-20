"""ui.py — Gradio Blocks definition + all UI callbacks."""

import html

import gradio as gr

from ui.i18n import _ui, _profile_choices, _PROFILE_CHOICES_DEFAULT, _CARD_LABELS_EN
from ui.html_misc import _header_html, _pdf_desc_html, _paper_divider_html
from ui.history import _render_history_html, _cleanup_old_runs, _load_run
from ui.runner import extract_paper_from_pdf, run_analysis_from_paper, run_analysis
from academic_agent.run_output import DEFAULT_OUTPUT_ROOT

# ---------------------------------------------------------------------------
# CSS
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

/* ── Remove Gradio's viewport-locked inner scrollbar ── */
/* Gradio 6.x fill_height=True (default) locks the app to 100vh and adds
   overflow:auto at several levels. fill_height=False is set in Python;
   these rules act as belt-and-suspenders for any remaining containers.  */
html, body {
    height: auto !important;
    overflow-y: auto !important;
}
.gradio-container,
.gradio-container > .main,
.gradio-container > .main > .wrap,
.gradio-container > .main > .contain,
.gradio-container .tabs,
.gradio-container .tabitem,
.gradio-container [role="tabpanel"],
.gradio-container .gap,
.gradio-container .col {
    height: auto !important;
    min-height: unset !important;
    max-height: none !important;
    overflow: visible !important;
    flex-shrink: 0 !important;
}
/* Details/accordion inner wrapper — Gradio 6.x nests extra divs */
details > div > div,
details > .padding,
details > .padding > div {
    overflow: visible !important;
    max-height: none !important;
    height: auto !important;
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

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

_theme = gr.themes.Default(
    primary_hue=gr.themes.colors.blue,
    neutral_hue=gr.themes.colors.slate,
).set(
    button_primary_background_fill="#2563eb",
    button_primary_background_fill_hover="#1d4ed8",
    button_primary_text_color="#ffffff",
)


# ---------------------------------------------------------------------------
# Language-change callback
# ---------------------------------------------------------------------------

def _on_lang_change(lang: str):
    """Return gr.update() for every UI shell component when the language dropdown changes."""
    t = _ui(lang)
    hist_html = _render_history_html(ui_lang=lang)
    return (
        gr.update(value=_header_html(t)),
        gr.update(label=t["topic_label"], placeholder=t["topic_placeholder"]),
        gr.update(label=t["lang_label"]),
        gr.update(label=t["profile_label"], choices=_profile_choices(lang)),
        gr.update(value=t["run_btn"]),
        gr.update(value=t["cancel_btn"]),
        gr.update(label=t["pdf_accordion_label"]),
        gr.update(value=_pdf_desc_html(t)),
        gr.update(label=t["upload_label"]),
        gr.update(value=t["extract_btn"]),
        gr.update(label=t["paper_title_label"]),
        gr.update(label=t["paper_contribution_label"]),
        gr.update(label=t["paper_domain_label"]),
        gr.update(label=t["paper_doi_label"]),
        gr.update(label=t["paper_metrics_label"]),
        gr.update(label=t["paper_topic_label"]),
        gr.update(value=_paper_divider_html(t["paper_divider"])),
        gr.update(value=t["clear_paper_btn"]),
        gr.update(value=t["paper_run_btn"]),
        gr.update(value=f'<p style="font-size:13px;color:#9a9a9a;margin:6px 0;">'
                        f'{html.escape(t["hist_desc"])}</p>'),
        gr.update(value=t["hist_refresh"]),
        gr.update(value=t["hist_cleanup"]),
        gr.update(value=hist_html),
        gr.update(label=t["run_id_label"]),
        gr.update(value=t["load_btn"]),
        gr.update(label=t["tab_analysis"]),
        gr.update(label=t["tab_history"]),
        lang,
    )


# ---------------------------------------------------------------------------
# Gradio Blocks
# ---------------------------------------------------------------------------

with gr.Blocks(title="Academic Commercialization Assessment", fill_height=False) as demo:
    ui_lang_state = gr.State("English")
    header_html_comp = gr.HTML(_header_html(_ui("English")))

    with gr.Tabs() as tabs:
        # ── Analysis tab ──────────────────────────────────────────────────
        with gr.Tab("Analysis") as analysis_tab:
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
                pdf_desc_comp = gr.HTML(_pdf_desc_html(_ui("English")))
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
                    paper_divider_html = gr.HTML(_paper_divider_html(_CARD_LABELS_EN["divider"]))
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
                        ("Auto (detect from topic)", "Auto (detect from topic)"),
                        ("English",   "English"),
                        ("简体中文",   "Chinese"),
                        ("日本語",    "Japanese"),
                        ("한국어",    "Korean"),
                        ("Français",  "French"),
                        ("Deutsch",   "German"),
                        ("Español",   "Spanish"),
                        ("Português", "Portuguese"),
                        ("العربية",   "Arabic"),
                        ("Русский",   "Russian"),
                        ("हिन्दी",   "Hindi"),
                    ],
                    value="Auto (detect from topic)",
                    scale=2,
                )
                profile_dd = gr.Dropdown(
                    label="Industry Profile",
                    choices=_PROFILE_CHOICES_DEFAULT,
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
                inputs=[pdf_upload, ui_lang_state],
                outputs=[
                    paper_title_box, paper_contribution_box, paper_domain_box,
                    paper_metrics_box, paper_topic_box, paper_doi_box,
                    paper_json_state, paper_card, extract_status, submit_btn,
                    clear_paper_btn, paper_run_btn, paper_divider_html,
                ],
            )

            def _clear_paper(ui_lang: str = "English"):
                t = _ui(ui_lang)
                return (
                    gr.update(value="", label=t["paper_title_label"]),
                    gr.update(value="", label=t["paper_contribution_label"]),
                    gr.update(value="", label=t["paper_domain_label"]),
                    gr.update(value="", label=t["paper_metrics_label"]),
                    gr.update(value="", label=t["paper_topic_label"]),
                    gr.update(value="", label=t["paper_doi_label"]),
                    "",
                    gr.update(value=None),
                    gr.update(visible=False),
                    "",
                    gr.update(visible=True),
                    gr.update(value=t["clear_paper_btn"]),
                    gr.update(value=t["paper_run_btn"]),
                    gr.update(value=_paper_divider_html(t["paper_divider"])),
                )

            clear_paper_btn.click(
                fn=_clear_paper,
                inputs=[ui_lang_state],
                outputs=[
                    paper_title_box, paper_contribution_box, paper_domain_box,
                    paper_metrics_box, paper_topic_box, paper_doi_box,
                    paper_json_state, pdf_upload, paper_card, extract_status, submit_btn,
                    clear_paper_btn, paper_run_btn, paper_divider_html,
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

            def _on_cancel(lang: str):
                msg = _ui(lang).get("cancel_msg", "⏹  Analysis cancelled.")
                cancel_html = (
                    f'<p style="color:#9a9a9a;font-size:13px;margin:4px 0;">{html.escape(msg)}</p>'
                )
                return (
                    cancel_html,
                    "",
                    "",
                    gr.update(value=None, visible=False),
                    gr.update(value=None, visible=False),
                    gr.update(interactive=True),
                    gr.update(visible=False),
                    "",
                )

            cancel_btn.click(
                fn=_on_cancel,
                inputs=[ui_lang_state],
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
                hist_desc_html = gr.HTML(
                    '<p style="font-size:13px;color:#9a9a9a;margin:6px 0;">'
                    'Past runs — paste a Run ID below to reload any report</p>'
                )
                refresh_btn = gr.Button("↻  Refresh", variant="secondary", scale=0, min_width=110)
                cleanup_btn = gr.Button("🗑  Keep Latest 20", variant="secondary", scale=0, min_width=150)

            cleanup_status = gr.HTML(value="")
            history_output = gr.HTML(value=_render_history_html())

            def _do_cleanup(ui_lang: str = "English"):
                msg = _cleanup_old_runs(keep_n=20)
                status_html = (
                    f'<p style="font-size:12px;color:#9a9a9a;margin:4px 0 8px;">{html.escape(msg)}</p>'
                )
                return status_html, _render_history_html(ui_lang)

            refresh_btn.click(fn=_render_history_html, inputs=[ui_lang_state], outputs=history_output)
            cleanup_btn.click(fn=_do_cleanup, inputs=[ui_lang_state], outputs=[cleanup_status, history_output])
            history_tab.select(fn=_render_history_html, inputs=[ui_lang_state], outputs=history_output)

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

    # Wire UI language switching — runs on every Report Language dropdown change
    language_dd.change(
        fn=_on_lang_change,
        inputs=[language_dd],
        outputs=[
            header_html_comp,
            topic_input,
            language_dd,
            profile_dd,
            submit_btn,
            cancel_btn,
            pdf_accordion,
            pdf_desc_comp,
            pdf_upload,
            extract_btn,
            paper_title_box,
            paper_contribution_box,
            paper_domain_box,
            paper_doi_box,
            paper_metrics_box,
            paper_topic_box,
            paper_divider_html,
            clear_paper_btn,
            paper_run_btn,
            hist_desc_html,
            refresh_btn,
            cleanup_btn,
            history_output,
            run_id_input,
            load_btn,
            analysis_tab,
            history_tab,
            ui_lang_state,
        ],
    )
