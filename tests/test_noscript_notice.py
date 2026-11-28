"""Static contracts for the bilingual notices shown without JavaScript."""

from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES_URL = "https://github.com/shuxiachai/academic-commercialization-agent/tree/main/examples"
VOID_ELEMENTS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


@dataclass
class Element:
    tag: str
    attrs: dict[str, str | None]
    children: list[Element] = field(default_factory=list)
    text_parts: list[str] = field(default_factory=list)

    def descendants(self):
        for child in self.children:
            yield child
            yield from child.descendants()

    def text(self) -> str:
        return " ".join((*self.text_parts, *(child.text() for child in self.children))).strip()


class TreeParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.root = Element("[document]", {})
        self.stack = [self.root]

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        element = Element(tag, dict(attrs))
        self.stack[-1].children.append(element)
        if tag not in VOID_ELEMENTS:
            self.stack.append(element)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.stack[-1].children.append(Element(tag, dict(attrs)))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                return

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.stack[-1].text_parts.append(data.strip())


def _parse(path: Path) -> Element:
    assert path.is_file(), f"missing HTML file: {path}"
    parser = TreeParser()
    parser.feed(path.read_text(encoding="utf-8"))
    parser.close()
    return parser.root


def _find(root: Element, *, tag: str | None = None, element_id: str | None = None) -> Element:
    matches = [
        element
        for element in root.descendants()
        if (tag is None or element.tag == tag)
        and (element_id is None or element.attrs.get("id") == element_id)
    ]
    assert len(matches) == 1, (tag, element_id, len(matches))
    return matches[0]


def _assert_bilingual(notice: Element) -> None:
    for language in ("en", "zh-CN"):
        parts = [element for element in notice.descendants() if element.attrs.get("lang") == language]
        assert parts, f"noscript notice is missing lang={language!r} content"
        assert any(part.text() for part in parts), f"noscript lang={language!r} content is empty"


def test_noscript_notices_keep_their_required_location_languages_and_examples_link():
    """#452: script-disabled pages must not leave readers with inert, unexplained UI."""
    index = _parse(ROOT / "web/index.html")
    body = _find(index, tag="body")
    assert body.children and body.children[0].tag == "noscript"
    _assert_bilingual(body.children[0])

    samples = _parse(ROOT / "web/samples.html")
    reader = _find(samples, element_id="sample-reader")
    notice = _find(reader, tag="noscript")
    skeleton = next(
        element for element in reader.children if "skeleton" in (element.attrs.get("class") or "").split()
    )
    assert notice in reader.children
    assert reader.children.index(notice) < reader.children.index(skeleton)
    _assert_bilingual(notice)
    assert any(
        element.tag == "a" and element.attrs.get("href") == EXAMPLES_URL
        for element in notice.descendants()
    )
