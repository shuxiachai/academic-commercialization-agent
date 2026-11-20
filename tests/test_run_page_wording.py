"""Wording on the run page that said more, or less, than the page knew.

Display only. The companion tests for the brief and the scorecard are in
tests/test_web_result_readability.py (SaidAccuratelyTests) and for the
checks' counts in tests/test_web_reliability.py.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_JS = _REPO / "web" / "static" / "js"
_I18N = (_JS / "i18n.js").read_text(encoding="utf-8")
_ENGLISH, _CHINESE = _I18N.split('"Simplified Chinese": {', 1)
_RESULT = (_JS / "result.js").read_text(encoding="utf-8")
_APP = (_JS / "app.js").read_text(encoding="utf-8")


def _string(table: str, key: str) -> str:
    found = re.search(rf'^\s+{key}: "((?:[^"\\]|\\.)*)",?\s*$', table, re.M)
    assert found, key
    return found[1]


# ── Usage and cost ────────────────────────────────────────────────────────

_HARNESS = """
    globalThis.localStorage = { getItem: () => null, setItem: () => {} };
    globalThis.document = { querySelectorAll: () => [], documentElement: {} };
    const run = await import("./run.mjs");
    const i18n = await import("./i18n.js");
    const cases = JSON.parse(process.argv[2]);
    const out = cases.map(({ usage, accounting, language, funded_by }) => {
      i18n.setLanguage(language ?? "English");
      return run.usageHeadline(usage, accounting ?? null, funded_by ?? null);
    });
    console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def headline(tmp_path_factory):
    node = shutil.which("node")
    assert node, "Node is required for the run header"
    work = tmp_path_factory.mktemp("usage-headline")
    source = (_JS / "run.js").read_text(encoding="utf-8").replace('import * as api from "./api.js";', "const api = {};")
    (work / "run.mjs").write_text(source, encoding="utf-8")
    shutil.copy2(_JS / "i18n.js", work / "i18n.js")
    (work / "harness.mjs").write_text(textwrap.dedent(_HARNESS), encoding="utf-8")

    def render(*cases):
        done = subprocess.run([node, "harness.mjs", json.dumps(list(cases))], capture_output=True, text=True,
                              encoding="utf-8", cwd=work)
        assert done.returncode == 0, done.stderr[-800:]
        return json.loads(done.stdout)

    return render


def _usage(**overrides):
    agents = [{"role": role, "model": "deepseek-v4.1-flash-1017", "total_tokens": 17_583, "cost_usd": 0.007}
              for role in ("a", "b", "c", "d", "e", "f")]
    return {"total_tokens": 105_500, "cost_usd": 0.0423, "cost_complete": True, "accounting_scope": "crew_nodes",
            "agents": agents, **overrides}


def test_the_fold_is_headed_by_what_the_run_used_and_what_that_cost(headline):
    """A finished run's header said "Usage & cost" and, opened, "105.5k
    tokens · Crew nodes only · Auxiliary LLM only · Invocations: 0 · Observed
    tokens: 0 · Observed cost estimate: $0 · ...". The one sum a reader could
    see was the helper ledger's $0, for a run that had used a hundred
    thousand tokens. The fold is now headed by the tokens and the estimate
    for them, or by a plain statement that there is none; the full
    accounting, helper ledger included, stays inside as the detail."""
    english, chinese = headline({"usage": _usage()}, {"usage": _usage(), "language": "Simplified Chinese"})
    assert english == "About 105.5k tokens · estimated cost $0.04 at the price on record for deepseek-v4.1-flash-1017"
    assert chinese == "约 10.6 万 token · 估算费用 $0.04（按 deepseek-v4.1-flash-1017 的记录价格）"


def test_a_run_without_a_price_says_so_and_shows_no_sum(headline):
    """The server records "cost unknown" rather than zero for a model with no
    price. The header must not turn that, or a zero, into "$0"."""
    unpriced = _usage(cost_usd=None, cost_complete=False, unpriced_models=["deepseek-v4.1-flash-1017"])
    zero = _usage(cost_usd=0, cost_complete=True)
    nameless = {"total_tokens": 900, "cost_usd": None, "agents": []}
    english = headline({"usage": unpriced}, {"usage": zero}, {"usage": nameless})
    assert english == [
        "About 105.5k tokens · no cost shown, as no unit price is on record yet for deepseek-v4.1-flash-1017",
        # A zero from a priced model is not "no price": the cost is said to be unknown, nothing more.
        "About 105.5k tokens · cost cannot be estimated",
        "About 900 tokens · cost cannot be estimated",
    ]
    for line in english:
        assert "$" not in line
    chinese = headline({"usage": unpriced, "language": "Simplified Chinese"},
                       {"usage": nameless, "language": "Simplified Chinese"})
    assert chinese == ["约 10.6 万 token · deepseek-v4.1-flash-1017 还没有登记单价，所以不显示费用", "约 900 token · 费用无法估算"]


def test_a_run_on_the_readers_own_key_is_pointed_to_their_providers_console(headline):
    """Every run on the account's saved model and on the deployment's default
    said "cost cannot be estimated: no price on record for qwen3.8-2.4t-a95b"
    (production, 2026-11-20): a sentence about the price table, not about the
    reader's bill. Until the operator records that model's price
    (token_usage._PRICING), the line says no cost is shown and why, and a
    reader who paid with their own key is told where the exact amount is.
    A run the site paid for is not sent to a console its reader does not have."""
    unpriced = _usage(cost_usd=None, cost_complete=False, unpriced_models=["qwen3.8-2.4t-a95b"])
    assert headline({"usage": unpriced, "funded_by": "own_keys"},
                    {"usage": unpriced, "funded_by": "own_keys", "language": "Simplified Chinese"},
                    {"usage": unpriced, "funded_by": "deployment"}) == [
        "About 105.5k tokens · no cost shown, as no unit price is on record yet for qwen3.8-2.4t-a95b; "
        "see your provider's console for the exact amount",
        "约 10.6 万 token · qwen3.8-2.4t-a95b 还没有登记单价，所以不显示费用；准确金额请看你的服务商控制台",
        "About 105.5k tokens · no cost shown, as no unit price is on record yet for qwen3.8-2.4t-a95b",
    ]
    assert "runView.usageHeadline(usage, usage_accounting, funded_by)" in _APP


def test_a_partial_sum_is_a_floor_and_small_sums_are_not_rounded_to_nothing(headline):
    mixed = _usage(cost_usd=0.31, cost_complete=False, unpriced_models=["glm-5.3"],
                   agents=[{"model": "qwen3.8-max"}, {"model": "glm-5.3"}, {"model": "qwen3.8-max"}])
    tiny = _usage(total_tokens=1_200, cost_usd=0.0004)
    assert headline({"usage": mixed}, {"usage": tiny}, {"usage": mixed, "language": "Simplified Chinese"}) == [
        "About 105.5k tokens · estimated cost at least $0.31; no price on record for glm-5.3",
        "About 1.2k tokens · estimated cost under $0.01 at the price on record for deepseek-v4.1-flash-1017",
        "约 10.6 万 token · 估算费用至少 $0.31；glm-5.3 没有记录价格",
    ]


def test_where_nothing_was_counted_the_fold_keeps_its_plain_heading(headline):
    """No tokens on record, or a collector that says its record is not
    available: there is nothing to head the fold with, and the accounting
    text inside says why."""
    for case in ({"usage": None}, {"usage": {"total_tokens": 0}}, {"usage": _usage(), "accounting": {"state": "unavailable"}},
                 {"usage": {"total_tokens": "many"}}, {"usage": []}):
        assert headline(case) == [""], case
    # A lower bound is said as one.
    assert headline({"usage": _usage(), "accounting": {"state": "lower_bound"}}) == [
        "At least 105.5k tokens · estimated cost at least $0.04 at the price on record for deepseek-v4.1-flash-1017"]


def test_the_header_uses_the_headline_and_keeps_the_full_accounting_inside():
    assert 'const headline = runView.usageHeadline(usage, usage_accounting, funded_by);' in _APP
    # The headline heads the fold; the plain name is only the fallback.
    assert '$("#run-usage-label").textContent = `· ${headline || runView.headerLabel("usage_details")}`;' in _APP
    # The accounting text and the helper ledger are still written into the fold, unchanged.
    assert 'spendEl.textContent = [spend, auxiliary].filter(Boolean).join(" · ");' in _APP


# ── Sources ───────────────────────────────────────────────────────────────

def test_the_sources_page_opens_with_a_sentence_in_the_readers_words():
    """It opened with "Browse saved source text only... summary_source is a
    recorded label, not proof of origin or completeness." That sentence, the
    count line and the "summary_source" lines are validated word for word by
    the saved-source rehearsal, so they stay; a plain sentence now stands
    before them, and the search hint, which nothing else reads, is reworded."""
    for table, plain, banned in ((_ENGLISH, "It is not the full paper", r"summary_source|locally browsable|semantic|fallback"),
                                 (_CHINESE, "它不是论文全文", r"summary_source|本地可浏览|语义|后备")):
        first = _string(table, "sources_plain")
        assert plain in first and not re.search(banned, first), first
        hint = _string(table, "sources_search_hint")
        assert not re.search(r"locally browsable|本地可浏览|literal|字面", hint), hint
        assert "A1" in hint
    assert _RESULT.index('el("p", "sources__plain", t("sources_plain"))') < _RESULT.index(
        'el("p", "sources__disclosure", t("sources_disclosure"))')


def test_the_sentences_the_rehearsal_validates_are_still_the_ones_it_expects():
    """They read like candidates for the same rewording and are not ours to
    reword here: src/academic_agent/report_evidence_source_locator_comparison.py
    compares the page's English text with these literals, and the rehearsal
    built on it fails when one differs."""
    contract = (_REPO / "src" / "academic_agent" / "report_evidence_source_locator_comparison.py").read_text(encoding="utf-8")
    compact = re.sub(r'"\s*\n\s*f?"', "", contract)
    disclosure = _string(_ENGLISH, "sources_disclosure")
    assert disclosure.replace("—", "—") in compact.replace("\\u2014", "—") or disclosure in compact
    assert _string(_ENGLISH, "sources_summary_unrecorded") in contract
    count = _string(_ENGLISH, "sources_count")
    assert count == "Matching saved records: {matched} / {total} locally browsable records. Showing {start}–{end}."
    assert "Matching saved records: {count} / {len(expected_rows)} locally browsable records. " in contract


# ── GO / NO-GO ────────────────────────────────────────────────────────────

def test_the_interface_writes_go_no_go_as_words_not_as_an_identifier():
    """"GO/NO_GO" with its underscore is how the code names the decision.
    The interface's own sentences write "GO / NO-GO". Until 2026-11-19 the
    report's lines kept the pipeline's spelling on the page; they are now
    shown the same way (report_display.text_for_display), and the sentences
    the Python side composes for the scope line say it that way themselves.
    The saved report and the writer's contract keep the identifier."""
    assert "GO/NO_GO" not in _I18N and "NO_GO" not in _I18N
    assert _ENGLISH.count("GO / NO-GO") >= 10 and _CHINESE.count("GO / NO-GO") >= 8
    index = (_REPO / "web" / "index.html").read_text(encoding="utf-8")
    assert "GO/NO_GO" not in index
    from academic_agent import report_display

    assert report_display.GO_NO_GO == "GO / NO-GO"
    for scope in report_display._SCOPE.values():
        assert not any("NO_GO" in sentence for sentence in scope.values())
    assert report_display.text_for_display("no actor-specific GO/NO_GO is assessed") == (
        "no actor-specific GO / NO-GO is assessed")
    tasks = (_REPO / "src" / "academic_agent" / "config" / "tasks.yaml").read_text(encoding="utf-8")
    assert "GO/NO_GO" in tasks, "the writer's contract keeps the identifier"
