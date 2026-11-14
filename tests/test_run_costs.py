"""What an assessment costs, said in money, and only where it was measured.

The landing and the keys form said "measured runs used about 100,000 model
tokens". A visitor deciding whether to sign up cannot turn that into a sum.
They now say what one assessment cost in model fees with each provider this
project has a recorded figure for, and nothing for a provider it has none
for. Every figure on the page is a row of the table in
docs/evidence-status.md ("What an assessment costs"), and every row there
names the result document or the saved run it comes from. A figure added to
the page from memory fails here.

The key guide ("Get both keys in 3 steps") recommends the cheapest measured
model provider and the search service the keys form already recommends, with
the links the keys form already gives.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_STATUS = (_ROOT / "docs" / "evidence-status.md").read_text(encoding="utf-8")
_INDEX = (_ROOT / "web" / "index.html").read_text(encoding="utf-8")
_STRINGS_FILE = (_ROOT / "web" / "static" / "js" / "i18n.js").read_text(encoding="utf-8")
_ENGLISH, _CHINESE = _STRINGS_FILE.split('"Simplified Chinese": {', 1)


def _string(table: str, key: str) -> str:
    found = re.search(rf'^\s+{key}: "((?:[^"\\]|\\.)*)",?\s*$', table, re.M)
    assert found, key
    return found[1]


def _cost_rows() -> list[dict[str, str]]:
    start = _STATUS.index("## What an assessment costs")
    section = _STATUS[start:_STATUS.index("\n## ", start + 5)]
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for line in section.splitlines() if line.startswith("| ") and not line.startswith("| Provider") and "---" not in line]
    keys = ("provider", "model", "measured", "runs", "per_run", "page", "source")
    assert rows and all(len(row) == len(keys) for row in rows), rows
    return [dict(zip(keys, row, strict=True)) for row in rows]


def test_the_record_names_a_source_for_every_figure():
    rows = _cost_rows()
    assert [row["model"] for row in rows] == ["`deepseek-chat`", "`qwen3.7-plus`", "`qwen3.8-max`", "`claude-sonnet-5-5`"]
    assert {row["provider"] for row in rows} == {"DeepSeek", "Model Studio (Qwen)", "Anthropic"}, "no figure for OpenAI: none was measured"
    for row in rows:
        assert re.fullmatch(r"2026-1[01]-\d\d", row["measured"]), row
        assert re.fullmatch(r"\$0\.\d\d", row["page"]), row
        document = re.search(r"\]\((results-[\w.-]+\.md)\)", row["source"])
        if document:
            # A batch: its total is in the result document, and the per-run figure is that total over its runs.
            text = (_ROOT / "docs" / document[1]).read_text(encoding="utf-8")
            total = re.search(r"USD (\d+\.\d\d) for the batch", row["per_run"])
            assert total and f"USD {total[1]}" in text, row
            assert abs(float(total[1]) / int(row["runs"]) - float(row["page"][1:])) <= 0.02, row
        else:
            # Single runs: the saved run is named, with the sum its usage record holds.
            assert re.search(r"`outputs/benchmark-runs/[\w.-]+`", row["source"]), row
            sums = [float(value) for value in re.findall(r"USD (0\.\d+)", row["per_run"])]
            assert sums and all(abs(value - float(row["page"][1:])) <= 0.015 for value in sums), row
            assert int(row["runs"]) == len(sums), row


def test_the_search_allowances_are_the_providers_own_words_with_the_day_they_were_read():
    start = _STATUS.index("## What an assessment costs")
    section = _STATUS[start:_STATUS.index("\n## ", start + 5)]
    assert "https://docs.tavily.com/documentation/api-credits" in section and "1,000 free API Credits every month" in section
    assert "https://serper.dev" in section and "2,500 free queries" in section
    assert "read on 2026-11-14" in section


@pytest.mark.parametrize("language", ["English", "Chinese"])
def test_every_sum_on_the_page_is_a_row_of_the_record(language):
    table = _ENGLISH if language == "English" else _CHINESE
    rows = _cost_rows()
    by_provider = {"DeepSeek": [r for r in rows if r["provider"] == "DeepSeek"],
                   "Qwen": [r for r in rows if r["provider"].startswith("Model Studio")],
                   "Anthropic": [r for r in rows if r["provider"] == "Anthropic"]}
    recorded = {row["page"] for row in rows}
    for key in ("landing_pay_cost", "byok_guide"):
        text = _string(table, key)
        assert set(re.findall(r"\$\d+(?:\.\d+)?", text)) == recorded, (language, key)
        for provider, provider_rows in by_provider.items():
            # Each provider's own sum stands beside its name: before it in
            # English ("about $0.05 with DeepSeek"), after it in Chinese.
            at = text.index(provider)
            beside = (re.split(r"[,:] ", text[:at])[-1] if language == "English"
                      else re.split(r"[，。：；]", text[at:])[0])
            assert set(re.findall(r"\$\d+(?:\.\d+)?", beside)) == {row["page"] for row in provider_rows}, (language, key, provider, beside)
        assert "OpenAI" not in text, "a provider without a measured figure is given none, and no remark"
        assert "100,000" not in text and "10 万" not in text
    # The landing also says which model and when; the keys form's line is the short one.
    landing = _string(table, "landing_pay_cost")
    for row in rows:
        assert row["model"].strip("`") in landing, (language, row["model"])
    months = {row["measured"][:7] for row in rows}
    assert months == {"2026-10", "2026-11"}
    for word in (("October 2026", "November 2026") if language == "English" else ("2026 年 10 月", "2026 年 11 月")):
        assert word in landing, (language, word)
    assert "1,000" in landing and "2,500" in landing, "the search allowances, as the record has them"
    # The sentence about who bills stays, and stays free of figures.
    body = _string(table, "landing_pay_body")
    assert not re.search(r"\$|token", body), (language, body)


def test_no_page_string_still_counts_a_run_in_tokens():
    assert "100,000 model tokens" not in _STRINGS_FILE and "10 万模型 token" not in _STRINGS_FILE
    assert "100,000 model tokens" not in _INDEX


def _guide(element_id: str) -> str:
    start = _INDEX.index(f'<details class="key-guide" id="{element_id}"')
    return _INDEX[start:_INDEX.index("</details>", start)]


@pytest.mark.parametrize("element_id,last_step", [("landing-key-guide", "key_guide_step3_landing"),
                                                  ("byok-key-guide", "key_guide_step3_form")])
def test_the_key_guide_is_three_steps_with_the_links_the_form_already_gives(element_id, last_step):
    guide = _guide(element_id)
    assert re.search(r'<summary data-i18n="key_guide_title">Get both keys in 3 steps</summary>', guide)
    assert " open" not in guide[:guide.index(">")], "folded until asked for"
    steps = re.findall(r"<li>(.*?)</li>", guide, re.S)
    assert len(steps) == 3
    assert [re.search(r'data-i18n="(\w+)"', step)[1] for step in steps] == ["key_guide_step1", "key_guide_step2", last_step]
    links = re.findall(r'<a href="([^"]+)" target="_blank" rel="noopener">([^<]+)</a>', guide)
    assert links == [("https://platform.deepseek.com/api-keys", "platform.deepseek.com/api-keys"),
                     ("https://app.tavily.com", "app.tavily.com")]
    # The same two addresses the keys form has always named, not new ones.
    hint = _INDEX[_INDEX.index('data-byok-i18n="byok_hint"'):]
    for _, shown in links:
        assert shown in hint[:400], shown
    assert "<img" not in guide, "no screenshots: they go stale"
    # A line for a deployment whose first assessment is free; hidden unless it is.
    assert re.search(rf'<p class="key-guide__trial" id="{element_id}-trial" data-i18n="key_guide_trial" hidden>', guide)


def test_the_guide_recommends_what_the_record_and_the_form_support():
    rows = _cost_rows()
    cheapest = min(rows, key=lambda row: float(row["page"][1:]))
    assert cheapest["provider"] == "DeepSeek"
    assert "DeepSeek" in _string(_ENGLISH, "key_guide_step1") and "cheapest" in _string(_ENGLISH, "key_guide_step1")
    assert "DeepSeek" in _string(_CHINESE, "key_guide_step1") and "最便宜" in _string(_CHINESE, "key_guide_step1")
    # The model it tells a newcomer to type is one the form offers for that provider.
    fields = (_ROOT / "web" / "static" / "js" / "byok_fields.js").read_text(encoding="utf-8")
    offered = re.search(r"deepseek: \[([^\]]*)\]", fields)[1]
    model = cheapest["model"].strip("`")
    assert f'"{model}"' in offered
    for table in (_ENGLISH, _CHINESE):
        for key in ("key_guide_step3_landing", "key_guide_step3_form"):
            assert model in _string(table, key), key
        assert "Tavily" in _string(table, "key_guide_step2") and "1,000" in _string(table, "key_guide_step2")
        # Nothing in the steps promises a first run: with a free first assessment they describe the ones after it.
        for key in ("key_guide_step1", "key_guide_step2", "key_guide_step3_landing", "key_guide_step3_form"):
            assert not re.search(r"\bfirst\b|首次|第一次", _string(table, key)), key
    assert "free first assessment" in _string(_ENGLISH, "key_guide_trial")
    assert "免费的首次评估" in _string(_CHINESE, "key_guide_trial")
