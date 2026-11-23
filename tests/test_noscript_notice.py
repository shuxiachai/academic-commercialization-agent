from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_static_pages_explain_javascript_requirement_in_both_languages():
    index = (ROOT / "web/index.html").read_text(encoding="utf-8")
    samples = (ROOT / "web/samples.html").read_text(encoding="utf-8")
    assert '<noscript class="noscript-notice">' in index
    assert "JavaScript is required" in index
    assert "启用 JavaScript" in index
    assert '<noscript class="samples__notice noscript-notice">' in samples
    assert "JavaScript is required" in samples
    assert "启用 JavaScript" in samples
    assert "github.com/shuxiachai/academic-commercialization-agent/tree/main/examples" in samples


def test_noscript_notice_uses_repository_tokens_not_inline_styles():
    css = (ROOT / "web/static/css/base.css").read_text(encoding="utf-8")
    start = css.index(".noscript-notice")
    assert "#" not in css[start : start + 600]
    assert "style=" not in (ROOT / "web/index.html").read_text(encoding="utf-8")
