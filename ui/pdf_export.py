"""pdf_export — reportlab PDF generation from markdown reports.

Font strategy, in priority order:
  1. An embedded TrueType face for the language (viewer-independent)
  2. A reportlab CID font — renders in Acrobat, but Chrome/Edge show empty
     glyphs because CID fonts are referenced, not embedded
  3. Helvetica, which has no CJK coverage at all

Step 1 is what makes CJK reports readable everywhere, so the candidate list
below covers Windows, Linux and macOS font locations.
"""

from pathlib import Path

# Reportlab built-in CID fonts — no font file needed, cross-platform.
# Resolved via pdfmetrics.registerFont(UnicodeCIDFont(...)) in _resolve_font.
_CID_FONT_MAP: dict[str, str] = {
    "Simplified Chinese":  "STSong-Light",
    "Traditional Chinese": "MSung-Light",
    "Japanese":            "HeiseiKakuGo-W5",
    "Korean":              "HYGoThic-Medium",
}

# Embedded TrueType candidates per language, tried in order.
_CJK_TTF_CANDIDATES: dict[str, list[str]] = {
    "Simplified Chinese": [
        # Windows
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        # Linux (Ubuntu / Debian / Fedora / Alpine).
        # The Noto entries are kept for distributions that ship a TrueType
        # build, but Debian's fonts-noto-cjk is OpenType/CFF and TTFont
        # rejects it ("postscript outlines are not supported"), so the
        # WenQuanYi entry below is what actually resolves there — and is
        # what the container image installs.
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
        # Linux. WenQuanYi last: it is a Chinese face, but it carries the full
        # kana and Hangul ranges and is TrueType, so it is the one that resolves
        # on Debian where the Noto build is OpenType/CFF and TTFont rejects it.
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        # macOS
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/Library/Fonts/Osaka.ttf",
    ],
    "Korean": [
        # Windows
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/gulim.ttc",
        # Linux. WenQuanYi last, for the same reason as the Japanese list: it
        # covers Hangul and is TrueType, so it resolves on Debian.
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        # macOS
        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    ],
}

_EMBEDDED_FONT_NAME = "EmbeddedCJK"
_FALLBACK_FONT = "Helvetica"

# Characters that Microsoft YaHei (and most CJK faces) have no glyph for.
# Without this, a paper reporting "CO₂" or an en-dash range renders as blank
# boxes even though the surrounding CJK text is fine.
# Subscript/superscript digits → plain digits; every dash variant → hyphen-minus.
_UNICODE_FIX = str.maketrans(
    "₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹‐‑‒―−–—",
    "01234567890123456789-------",
)


def _resolve_font(output_language: str) -> str:
    """Register and return the best available font name for this language.

    Falls through embedded TrueType → CID → Helvetica. Returns the name the
    caller should pass to reportlab styles.
    """
    from reportlab.pdfbase import pdfmetrics

    for font_path in _CJK_TTF_CANDIDATES.get(output_language, []):
        if not Path(font_path).is_file():
            continue
        try:
            from reportlab.pdfbase.ttfonts import TTFont
            pdfmetrics.registerFont(TTFont(_EMBEDDED_FONT_NAME, font_path))
            return _EMBEDDED_FONT_NAME
        except Exception:
            continue    # corrupt or unsupported face — try the next candidate

    cid_name = _CID_FONT_MAP.get(output_language, "")
    if cid_name:
        try:
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            pdfmetrics.registerFont(UnicodeCIDFont(cid_name))
            return cid_name
        except Exception:
            pass

    return _FALLBACK_FONT


def _build_styles(font_name: str) -> dict:
    """Build the paragraph styles and palette used by the story builder."""
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib import colors

    BLUE  = colors.HexColor("#2563eb")
    DARK  = colors.HexColor("#1a1a1a")
    H1C   = colors.HexColor("#111827")
    H2C   = colors.HexColor("#1e293b")
    H3C   = colors.HexColor("#374151")
    TH_BG = colors.HexColor("#f8fafc")
    GRID  = colors.HexColor("#d1d5db")

    def _s(name, size, mult=1.55, col=DARK, sb=0, sa=5, li=0):
        return ParagraphStyle(name, fontName=font_name, fontSize=size,
                              leading=size * mult, textColor=col,
                              spaceBefore=sb, spaceAfter=sa, leftIndent=li)

    return {
        "font":  font_name,
        "H1":    _s("H1",   14,   col=H1C, sb=0,  sa=8),
        "H2":    _s("H2",   12,   col=H2C, sb=12, sa=4),
        "H3":    _s("H3",   10.5, col=H3C, sb=9,  sa=4),
        "Body":  _s("Body", 10,   sb=0,  sa=4),
        "LI":    _s("LI",   10,   sb=0,  sa=2, li=8),
        "TH":    _s("TH",   8.5,  sb=0,  sa=0),
        "TD":    _s("TD",   8.5,  sb=0,  sa=0),
        "Mono":  _s("Mono", 8,    sb=0,  sa=3),
        "BLUE":  BLUE,
        "GRID":  GRID,
        "TH_BG": TH_BG,
    }


def _make_story_parser(styles: dict):
    """Return an _HtmlToStory instance bound to the given styles.

    The parser class is defined here rather than at module scope because it
    closes over reportlab flowables that are imported lazily — keeping the
    import cost out of module load, which matters for the CLI paths.
    """
    import html as _html
    from html.parser import HTMLParser
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph, Spacer, Table, TableStyle, HRFlowable,
    )

    class _HtmlToStory(HTMLParser):
        """Parse markdown-generated HTML into a reportlab Platypus story.

        Uses a single _write() routing method so inline markup tags
        (strong/em/code) always land in the buffer that owns their context
        (block paragraph, list item, or table cell).
        """

        _SEMANTIC = {"h1", "h2", "h3", "p", "li", "td", "th", "pre"}

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
                self._flush_block(styles["H1"])
                self.story.append(
                    HRFlowable(width="100%", thickness=1.5,
                               color=styles["BLUE"], spaceAfter=6))
            elif tag == "h2":
                self._flush_block(styles["H2"])
                self.story.append(
                    HRFlowable(width="100%", thickness=0.5,
                               color=styles["GRID"], spaceAfter=4))
            elif tag == "h3":
                self._flush_block(styles["H3"])
            elif tag == "p":
                self._flush_block(styles["Body"])
            elif tag == "li":
                t = (self._li_stk.pop() if self._li_stk else "").strip()
                if t:
                    self.story.append(Paragraph("• " + t, styles["LI"]))
            elif tag in ("strong", "b"):
                self._write("</b>")
            elif tag in ("em", "i"):
                self._write("</i>")
            elif tag == "code":
                self._write("</font>")
            elif tag == "pre":
                self._flush_block(styles["Mono"])
            elif tag in ("td", "th"):
                self._row.append((self._cell_buf.strip(), self._cell_is_th))
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
            self._write(_html.escape(data))

        def _build_table(self):
            if not self._tbl:
                return
            n_cols = max(len(row) for row, _ in self._tbl)
            avail = 16.5 * cm
            col_w = [avail / n_cols] * n_cols

            cells = []
            style_cmds = [
                ("GRID",           (0, 0), (-1, -1), 0.5, styles["GRID"]),
                ("VALIGN",         (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING",     (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING",  (0, 0), (-1, -1), 3),
                ("LEFTPADDING",    (0, 0), (-1, -1), 6),
                ("RIGHTPADDING",   (0, 0), (-1, -1), 6),
                ("FONTNAME",       (0, 0), (-1, -1), styles["font"]),
                ("FONTSIZE",       (0, 0), (-1, -1), 8.5),
            ]

            for r_idx, (row, is_hdr) in enumerate(self._tbl):
                p_row = []
                for c_idx in range(n_cols):
                    if c_idx < len(row):
                        text, is_th = row[c_idx]
                    else:
                        # Pad short rows. Defensive: reportlab's Table pads
                        # jagged input itself, so this is belt-and-braces
                        # rather than load-bearing — which is why no test
                        # can distinguish its presence from its absence.
                        text, is_th = "", False
                    st = styles["TH"] if (is_hdr or is_th) else styles["TD"]
                    p_row.append(Paragraph(text, st))
                cells.append(p_row)
                if is_hdr:
                    style_cmds.append(
                        ("BACKGROUND", (0, r_idx), (-1, r_idx), styles["TH_BG"]))

            tbl = Table(cells, colWidths=col_w, repeatRows=1)
            tbl.setStyle(TableStyle(style_cmds))
            self.story.append(Spacer(1, 4))
            self.story.append(tbl)

    return _HtmlToStory()


def markdown_to_story(report_md: str, styles: dict) -> list:
    """Convert a markdown report into a list of reportlab flowables."""
    import markdown as md_lib

    html_body = md_lib.markdown(report_md, extensions=["tables", "fenced_code"])
    parser = _make_story_parser(styles)
    parser.feed(html_body)
    return parser.story


def _generate_pdf(report_md: str, run_dir: Path, output_language: str = "English") -> Path:
    """Convert a markdown report to PDF. Raises if generation fails.

    Failures used to be swallowed and returned as None, on the reasoning that
    the report was already saved and shown, so a PDF problem should not take
    the run down — "the caller simply hides the download button". That was
    written for the Gradio interface, which rendered the PDF during a run and
    could drop a button from the page it was building.

    The only caller now is GET /api/runs/{id}/report.pdf, which runs *because*
    someone asked for the download. There is no button left to hide: the
    request fails either way, and the sole question is whether it carries the
    reason. It did not — that endpoint wraps this call to report the cause,
    and the swallow made its handler unreachable, so every failure arrived as
    a bare "PDF rendering produced no file" with the reportlab error gone.
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate

    font_name = _resolve_font(output_language)
    styles = _build_styles(font_name)
    story = markdown_to_story(report_md, styles)

    pdf_path = run_dir / "commercialization_report.pdf"
    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=A4,
        rightMargin=2 * cm, leftMargin=2 * cm,
        topMargin=2 * cm,   bottomMargin=2 * cm,
    )
    doc.build(story)
    return pdf_path
