"""pdf_export — reportlab PDF generation from markdown reports."""

from pathlib import Path

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
