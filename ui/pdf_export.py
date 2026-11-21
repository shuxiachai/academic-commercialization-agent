"""pdf_export — reportlab PDF generation from markdown reports.

Font strategy, in priority order:
  1. An embedded TrueType face for the language (viewer-independent)
  2. A reportlab CID font — renders in Acrobat, but Chrome/Edge show empty
     glyphs because CID fonts are referenced, not embedded
  3. Helvetica, which has no CJK coverage at all

Step 1 is what makes CJK reports readable everywhere, so the candidate list
below covers Windows, Linux and macOS font locations.
"""

import html as _html
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Lock

# Bounded single-process stripes avoid one permanent lock per capability URL.
# A collision only serializes unrelated exports; multi-replica coordination is
# deliberately outside this deployment's file/ownership contract.
_PDF_CACHE_LOCKS = tuple(Lock() for _ in range(32))


def pdf_cache_lock(run_dir: Path):
    return _PDF_CACHE_LOCKS[hash(str(run_dir.resolve())) % len(_PDF_CACHE_LOCKS)]


def pdf_cache_complete(path: Path) -> bool:
    """Reject obvious legacy torn caches, not validate PDF semantics or freshness."""
    try:
        with path.open("rb") as handle:
            header = handle.read(5)
            handle.seek(0, 2)
            size = handle.tell()
            handle.seek(max(0, size - 2048))
            return header == b"%PDF-" and handle.read().rstrip().endswith(b"%%EOF")
    except FileNotFoundError:
        return False

#: Written into the document information of a PDF that opens with the
#: decision-conclusion card. A report exported before the card existed is
#: complete and has none; this is how the endpoint tells the two apart.
DECISION_CARD_MARK = "decision-card:v1"

#: Written into the document information of every PDF, naming the rules its
#: pages were drawn by: the display rules of its text (report_display.py) and,
#: since v3, this module's own page (the first page's summary, the header and
#: footer, the reference list's links). An export is cached beside the report
#: for good, so one made before a rule existed keeps the old pages: a PDF of
#: a Chinese report saved under English headings, exported before the
#: heading table, would have kept those headings after it. Raise the number
#: when either changes what a saved report is shown as.
#:
#: v3 (2026-11-21): source types in words, the mode codes in words, no
#: " - Google Patents", the summary, header, footer, metadata and links.
DISPLAY_MARK = "report-display:v3"

# The marks live in the document information's Keywords. Until v3 they were
# its Subject, which a reader's document properties show as the PDF's subject:
# "report-display:v2 decision-card:v1". A mark is looked for there and
# nowhere else, so report text that happened to contain one cannot pass for it.
_KEYWORDS = re.compile(rb"/Keywords\s*\(([^)]*)\)")


def _marks(path: Path) -> set[str]:
    """The marks a cached export carries; none when it cannot be read."""
    try:
        data = path.read_bytes()
    except OSError:
        return set()
    found = _KEYWORDS.search(data)
    return set(found.group(1).decode("ascii", "replace").split()) if found else set()


def pdf_carries_decision_card(path: Path) -> bool:
    """Whether a cached export was built with the card. A read fault is "no": rebuild."""
    return DECISION_CARD_MARK in _marks(path)


def pdf_carries_display(path: Path) -> bool:
    """Whether a cached export was drawn by the current display rules. A read fault is "no"."""
    return DISPLAY_MARK in _marks(path)


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


def _build_styles(font_name: str, cjk_wrap: bool = False) -> dict:
    """Build the paragraph styles and palette used by the story builder.

    `cjk_wrap` breaks lines between characters, as Chinese and Japanese are
    set. Without it a Chinese paragraph broke only at its rare spaces: a line
    ran on to "kV技术" and the next began "[A8]。", leaving half a line empty.
    """
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
                              spaceBefore=sb, spaceAfter=sa, leftIndent=li,
                              wordWrap="CJK" if cjk_wrap else None)

    return {
        "font":  font_name,
        "LINK":  "#1d4ed8",
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


#: The width a paragraph is set in: A4 less the two 2 cm margins and the
#: frame's 6 pt padding on each side (SimpleDocTemplate's defaults).
_TEXT_WIDTH_PT = (21.0 - 4.0) / 2.54 * 72 - 12

# A web address in the report's text. evidence.py ends every reference entry
# with one, and the PDF showed them as text: nothing to click, and a long
# one broken wherever the line ran out ("…/US20|230123456A1…").
_URL = re.compile(r"https?://[^\s<>\"]+")
# What may follow an address in prose and is not part of it.
_URL_TAIL = ".,;:!?'\""
_PLACEHOLDER = re.compile("\x00(\\d+)\x00")
_TRAILING_PLACEHOLDER = re.compile("\x00(\\d+)\x00\\s*$")
# Where an address may be broken across lines: after "/", "-" or "?". A run of
# them stays together ("https://").
_URL_PIECES = re.compile(r"[^/?-]*[/?-]+|[^/?-]+")


def _split_url(text: str) -> tuple[str, str]:
    """An address as matched, less what follows it in a sentence."""
    url = text.rstrip(_URL_TAIL)
    while url.endswith(")") and url.count(")") > url.count("("):
        url = url[:-1]
    return url, text[len(url):]


def wrap_url(url: str, font_name: str, font_size: float, width: float) -> list[str]:
    """`url` as lines no wider than `width`, broken only after "/", "-" or "?".

    A piece with no such place in it that is still wider than a line is cut
    where the line ends, the one case left where nothing else fits.
    """
    from reportlab.pdfbase.pdfmetrics import stringWidth

    def fits(text: str) -> bool:
        return stringWidth(text, font_name, font_size) <= width

    lines: list[str] = []
    line = ""
    for piece in _URL_PIECES.findall(url):
        if fits(line + piece):
            line += piece
            continue
        if line:
            lines.append(line)
        while not fits(piece) and len(piece) > 1:
            cut = len(piece) - 1
            while cut > 1 and not fits(piece[:cut]):
                cut -= 1
            lines.append(piece[:cut])
            piece = piece[cut:]
        line = piece
    if line:
        lines.append(line)
    return lines


def _make_story_parser(styles: dict):
    """Return an _HtmlToStory instance bound to the given styles.

    The parser class is defined here rather than at module scope because it
    closes over reportlab flowables that are imported lazily — keeping the
    import cost out of module load, which matters for the CLI paths.
    """
    from html.parser import HTMLParser
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph, Spacer, Table, TableStyle, HRFlowable,
    )

    def link(url: str, shown: str) -> str:
        return f'<a href="{_html.escape(url, quote=True)}" color="{styles["LINK"]}">{shown}</a>'

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
            # Bare addresses met in the text, written as a placeholder until
            # their block is flushed, when it is known whether one ends it.
            self._urls: list[str] = []
            self._in_link: bool = False

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

        def _links(self, markup: str, style=None) -> str:
            """Placeholders as links. Given a `style`, an address that ends
            the block (every reference entry's) starts a line of its own and
            is broken only after "/", "-" or "?" (wrap_url); any other
            address is a link where it stands."""
            trailing = _TRAILING_PLACEHOLDER.search(markup) if style is not None else None
            if trailing is not None:
                url = self._urls[int(trailing.group(1))]
                width = _TEXT_WIDTH_PT - style.leftIndent - 2
                lines = wrap_url(url, style.fontName, style.fontSize, width)
                before = markup[:trailing.start()].rstrip()
                shown = link(url, "<br/>".join(_html.escape(line, quote=False) for line in lines))
                markup = (before + "<br/>" if before else "") + shown
            return _PLACEHOLDER.sub(
                lambda m: link(self._urls[int(m.group(1))], _html.escape(self._urls[int(m.group(1))], quote=False)),
                markup,
            )

        def _flush_block(self, style):
            t = self._block_buf.strip()
            if t:
                self.story.append(Paragraph(self._links(t, style), style))
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
            elif tag == "a":
                # A Markdown link. Only a web or mail address becomes one in
                # the PDF; an anchor or a relative path stays as its text.
                href = dict(attrs).get("href") or ""
                if re.match(r"(?:https?:|mailto:)", href) and not self._in_link:
                    self._in_link = True
                    self._write(f'<a href="{_html.escape(href, quote=True)}" color="{styles["LINK"]}">')

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
                    self.story.append(Paragraph("• " + self._links(t, styles["LI"]), styles["LI"]))
            elif tag == "a":
                if self._in_link:
                    self._in_link = False
                    self._write("</a>")
            elif tag in ("strong", "b"):
                self._write("</b>")
            elif tag in ("em", "i"):
                self._write("</i>")
            elif tag == "code":
                self._write("</font>")
            elif tag == "pre":
                self._flush_block(styles["Mono"])
            elif tag in ("td", "th"):
                self._row.append((self._links(self._cell_buf.strip()), self._cell_is_th))
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
            if self._in_link:
                self._write(_html.escape(data))
                return
            last = 0
            for match in _URL.finditer(data):
                url, tail = _split_url(match.group())
                self._write(_html.escape(data[last:match.start()]))
                self._urls.append(url)
                self._write(f"\x00{len(self._urls) - 1}\x00")
                self._write(_html.escape(tail))
                last = match.end()
            self._write(_html.escape(data[last:]))

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


#: The card's one coloured thing is the conclusion itself. Not green and red
#: alone: DEFER and "none stated" are the common cases and neither is an alarm.
_CARD_TONES = {
    "go": "#15803d", "conditional_go": "#a16207", "defer": "#a16207", "no_go": "#b91c1c",
    "conflicting": "#b91c1c", "not_stated": "#475569",
}


def decision_card_story(card: dict, styles: dict) -> list:
    """The decision-conclusion card as flowables: one bordered box of paragraphs.

    `card` is decision_verdict.card_text(): its words are the report's own and
    the code's fixed copy, so everything is escaped as text here and nothing
    in it is read as markup.
    """
    import html as _html
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    def text(value: str) -> str:
        return _html.escape(str(value).translate(_UNICODE_FIX))

    base = styles["Body"]
    label = ParagraphStyle("CardLabel", parent=base, fontSize=8.5, leading=12, textColor=styles["H3"].textColor, spaceAfter=2)
    headline = ParagraphStyle(
        "CardHeadline", parent=base, fontSize=15, leading=20, spaceAfter=3,
        textColor=colors.HexColor(_CARD_TONES.get(card.get("tone"), _CARD_TONES["not_stated"])),
    )
    body = ParagraphStyle("CardBody", parent=base, fontSize=9.5, leading=14, spaceAfter=3)
    small = ParagraphStyle("CardSmall", parent=base, fontSize=8, leading=11, textColor=styles["H3"].textColor, spaceAfter=0)

    cell = [Paragraph(f"<b>{text(card['title'])}</b>", label)]
    if card.get("asked"):
        cell.append(Paragraph(text(" · ".join(card["asked"])), body))
    cell.append(Paragraph(f"<b>{text(card['headline'])}</b>", headline))
    if card.get("detail"):
        cell.append(Paragraph(text(card["detail"]), body))
    for lead, quote in card.get("quotes", []):
        # A full-width colon carries its own space.
        gap = "" if str(lead).endswith("：") else " "
        # decision_verdict.joined breaks the line after a conclusion line with no stop.
        cell.append(Paragraph(f"{text(lead)}{gap}“{text(quote).replace(chr(10), '<br/>')}”", body))
    if card.get("where"):
        cell.append(Paragraph(text(card["where"]), small))
    cell.append(Paragraph(text(card["note"]), small))

    box = Table([[cell]], colWidths=["100%"])
    box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, styles["GRID"]),
        ("BACKGROUND", (0, 0), (-1, -1), styles["TH_BG"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [Spacer(1, 4), box, Spacer(1, 8)]


#: The grade's colour, the one coloured thing in the summary, as the page
#: colours its badge (result.js band(): success, accent, warning, muted).
_BAND_TONES = {"strong": "#15803d", "moderate": "#1d4ed8", "early": "#a16207", "nascent": "#475569"}


def _text(value) -> str:
    """Words from the report or the code's copy, as paragraph text: escaped, never markup."""
    return _html.escape(str(value).translate(_UNICODE_FIX))


def _labelled(label: str, chinese: bool) -> str:
    """A card label as the lead of a line: "Biggest risk:"; a label ending in a colon keeps its own."""
    if label.endswith((":", "：")):
        return label
    return label + ("：" if chinese else ":")


def _lead(label: str, chinese: bool) -> str:
    """A bold label leading a line; a full-width colon needs no space after it."""
    return f"<b>{_text(_labelled(label, chinese))}</b>" + ("" if chinese else " ")


#: The languages set without spaces between words, broken between characters.
_CJK_WRAP = frozenset({"Simplified Chinese", "Traditional Chinese", "Japanese"})


def summary_story(summary: dict, styles: dict, *, chinese: bool = False) -> list:
    """The first page's summary (report_summary.summary) as flowables.

    One bordered box: the score and its grade, the five dimensions with the
    readiness level, the source counts, the decision context and the brief's
    three lines. Without a score, one sentence saying why, and nothing else.
    """
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    base = styles["Body"]
    muted = styles["H3"].textColor
    small = ParagraphStyle("SumSmall", parent=base, fontSize=8.5, leading=12, textColor=muted, spaceAfter=2)
    body = ParagraphStyle("SumBody", parent=base, fontSize=9, leading=13, spaceAfter=3)
    if "note" in summary:
        return [Spacer(1, 2), Paragraph(_text(summary["note"]), body), Spacer(1, 6)]

    tone = colors.HexColor(_BAND_TONES.get(summary["band_key"], _BAND_TONES["nascent"]))
    figure = ParagraphStyle("SumFigure", parent=base, fontSize=18, leading=22, textColor=tone, spaceAfter=4)
    cell = ParagraphStyle("SumCell", parent=base, fontSize=8.5, leading=11, spaceAfter=0)
    value = ParagraphStyle("SumValue", parent=cell, alignment=2)

    parts: list = [Paragraph(f"<b>{_text(summary['title'])}</b>", small)]
    parts.append(Paragraph(
        f"<b>{_text(summary['score'])}</b> <font size='10' color='#475569'>{_text(summary['unit'])}</font>"
        f"<font size='11'>  <b>{_text(summary['band'])}</b></font>"
        f"<font size='9' color='#475569'> · {_text(summary['readiness'])}</font>", figure))

    rows = [[Paragraph(_text(label), cell), Paragraph(_text(shown), value), Paragraph(_text(note), cell)]
            for label, shown, note in summary["rows"]]
    table = Table(rows, colWidths=[4.6 * 28.3465, 1.9 * 28.3465, None], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -2), 0.4, styles["GRID"]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    parts += [table, Spacer(1, 5)]
    if summary.get("sources"):
        label, line = summary["sources"]
        parts.append(Paragraph(_lead(label, chinese) + _text(line), body))
    label, line, asked = summary["context"]
    parts.append(Paragraph(_lead(label, chinese) + _text(line)
                           + "".join(f" · {_text(more)}" for more in asked), body))
    for label, line, quoted in summary["brief"]:
        # The report's own summary sentence is a quotation, as on the page.
        shown = f"“{_text(line)}”" if quoted else _text(line)
        parts.append(Paragraph(_lead(label, chinese) + shown, body))

    box = Table([[parts]], colWidths=["100%"])
    box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, styles["GRID"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [Spacer(1, 2), box, Spacer(1, 10)]


def notice_story(note: str, styles: dict) -> list:
    """The draft notice, above the text as the page has it: nobody should read
    a paragraph of a draft as the assessment before learning what it is."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

    body = ParagraphStyle("Notice", parent=styles["Body"], fontSize=9.5, leading=14, spaceAfter=0)
    box = Table([[Paragraph(_text(note), body)]], colWidths=["100%"])
    box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, colors.HexColor("#a16207")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fefce8")),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [Spacer(1, 4), box, Spacer(1, 6)]


def _fit(text: str, font_name: str, size: float, width: float) -> str:
    """`text`, cut with an ellipsis to fit `width`."""
    from reportlab.pdfbase.pdfmetrics import stringWidth

    if stringWidth(text, font_name, size) <= width:
        return text
    while text and stringWidth(text + "…", font_name, size) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _page_canvas(page: dict, font_name: str):
    """A canvas class that draws the header and footer once the page count is known.

    "Page 3 of 11" needs the eleven before page 3 is finished, so each page is
    kept until the document is done and then drawn with its furniture: the
    header "ACA · topic", and a footer with the run's link, the date the
    report was made and its model, and the page number.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen.canvas import Canvas

    width, height = A4
    # Where the text column starts and ends: the margin and the frame's 6 pt padding.
    left, right = 2 * cm + 6, width - 2 * cm - 6
    grey, rule, blue = colors.HexColor("#475569"), colors.HexColor("#d1d5db"), colors.HexColor("#1d4ed8")

    class PageCanvas(Canvas):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._kept: list[dict] = []

        def showPage(self):  # noqa: N802 - reportlab's name
            self._kept.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._kept)
            # Annotations are named by a running count, which restoring a
            # kept page would wind back: the footer's link on page 2 would
            # take the name of a link in the text of page 3.
            count = self._annotationCount
            for state in self._kept:
                self.__dict__.update(state)
                self._annotationCount = count
                self._furniture(total)
                count = self._annotationCount
                super().showPage()
            super().save()

        def _furniture(self, total: int) -> None:
            self.saveState()
            self.setStrokeColor(rule)
            self.setLineWidth(0.5)
            self.setFillColor(grey)
            self.setFont(font_name, 8)
            self.drawString(left, height - 1.25 * cm, _fit(page["header"], font_name, 8, right - left))
            self.line(left, height - 1.45 * cm, right, height - 1.45 * cm)
            self.line(left, 1.55 * cm, right, 1.55 * cm)
            number = page["page"].format(page=self._pageNumber, pages=total)
            self.setFont(font_name, 7.5)
            self.drawRightString(right, 1.15 * cm, number)
            room = right - left - stringWidth(number, font_name, 7.5) - 12
            shown = _fit(page["link_text"], font_name, 7.5, room)
            if page.get("link"):
                self.setFillColor(blue)
                self.drawString(left, 1.15 * cm, shown)
                self.linkURL(page["link"], (left, 1.05 * cm, left + stringWidth(shown, font_name, 7.5), 1.45 * cm),
                             relative=0, thickness=0)
                self.setFillColor(grey)
            else:
                self.drawString(left, 1.15 * cm, shown)
            if page.get("footer"):
                self.drawString(left, 0.78 * cm, _fit(page["footer"], font_name, 7.5, right - left))
            self.restoreState()

    return PageCanvas


def _generate_pdf(report_md: str, run_dir: Path, output_language: str = "English", *,
                  decision_card: dict | None = None, card_at: int = 0,
                  summary: dict | None = None, notice: str | None = None, page: dict | None = None,
                  file_name: str = "commercialization_report.pdf") -> Path:
    """Convert a markdown report to PDF. Raises if generation fails.

    The first page carries, after the first `card_at` characters of the
    report (the caller sets that to the end of the scope paragraph, or of
    the title where there is none), in this order: the decision-conclusion
    card (`decision_card`, decision_verdict.card_text), a draft's notice
    (`notice`) and the summary (`summary`, report_summary.summary). `page`
    (report_summary.page_text) is the header, footer and document
    information; without it the pages have neither, as before. The document
    information's Keywords always carry DISPLAY_MARK, and DECISION_CARD_MARK
    when the card is drawn.

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
    styles = _build_styles(font_name, cjk_wrap=output_language in _CJK_WRAP)
    inserted: list = []
    if decision_card is not None:
        inserted += decision_card_story(decision_card, styles)
    if notice:
        inserted += notice_story(notice, styles)
    if summary is not None:
        inserted += summary_story(summary, styles, chinese=output_language == "Simplified Chinese")
    if inserted:
        story = markdown_to_story(report_md[:card_at], styles) + inserted + markdown_to_story(report_md[card_at:], styles)
    else:
        story = markdown_to_story(report_md, styles)

    marks = DISPLAY_MARK if decision_card is None else f"{DISPLAY_MARK} {DECISION_CARD_MARK}"
    info = {"keywords": marks, "creator": "ACA"}
    if page is not None:
        info.update(title=page["title"], author=page["author"], subject=page["subject"])

    pdf_path = run_dir / file_name
    # Rendering can write bytes before raising. Publishing directly to the
    # cache let the NEXT download return those partial bytes as a 200. Build a
    # uniquely owned sibling, close it (Windows), then replace only on success.
    # A process crash may leave a temporary sibling, never a new partial cache.
    with NamedTemporaryFile(dir=run_dir, prefix=".report-", suffix=".pdf.tmp", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        doc = SimpleDocTemplate(
            str(temporary), pagesize=A4,
            rightMargin=2 * cm, leftMargin=2 * cm,
            topMargin=2 * cm,   bottomMargin=2 * cm,
            **info,
        )
        if page is None:
            doc.build(story)
        else:
            doc.build(story, canvasmaker=_page_canvas(page, font_name))
        temporary.replace(pdf_path)
    finally:
        temporary.unlink(missing_ok=True)
    return pdf_path
