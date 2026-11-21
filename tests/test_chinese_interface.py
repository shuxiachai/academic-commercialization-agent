"""The Chinese interface says things in Chinese: what was still English until 2026-11-15.

Found by opening each page with the interface set to Chinese and listing
what was shown, said to a screen reader or put in the tab without a Chinese
character in it:

- the composer's five scoring domains ("Industrial" ... "Software / AI"),
  beside "自动方案", which translated "Auto profile" word for word and said
  nothing about domains;
- the brief's readiness clause, "TRL 9 (actual system proven in operational
  environment)", which is saved in English with the scorecard;
- the tab's title on the application and the sample reader;
- the labels of controls that have no text (aria-label) and what a pointer
  shows on hover (title);
- the names of the English samples on a card whose every other word was
  Chinese.

The shipped modules run in Node, as in the other page tests. The saved
scorecard and reports are not changed by any of this.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

from academic_agent import evidence
from api import samples

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "static" / "js"
PAGES = ("index.html", "samples.html", "admin.html", "privacy.html")
CJK = re.compile(r"[㐀-鿿]")
LATIN_WORD = re.compile(r"[A-Za-z]{3,}")

_HARNESS = r"""
const fs=require('fs'), vm=require('vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
class Node{
 constructor(dataset={}){this.dataset=dataset;this.attributes={};this.textContent='';this.placeholder='';this.title='';}
 setAttribute(name,value){this.attributes[name]=String(value);}
}
const marked={
 '[data-i18n]':[new Node({i18n:'profile_industrial'}), new Node({i18n:'auto_profile'})],
 '[data-i18n-placeholder]':[new Node({i18nPlaceholder:'runs_search'})],
 '[data-i18n-aria-label]':[new Node({i18nAriaLabel:'aria_profile'}), new Node({i18nAriaLabel:'brand_full'})],
 '[data-i18n-title]':[new Node({i18nTitle:'title_attach'})],
};
let stored=input.language;
const context=vm.createContext({
 localStorage:{getItem:()=>stored, setItem:(_key,value)=>{stored=value;}},
 document:{documentElement:{lang:''}, querySelectorAll:(selector)=>marked[selector]??[], createElement:()=>new Node()},
 api:{},
});
const source=(name)=>fs.readFileSync(input.root+'/web/static/js/'+name,'utf8').replace(/^import .*;\r?\n/gm,'').replace(/export /g,'');
vm.runInContext(source('i18n.js')+source('result.js'),context);
const run=(code)=>vm.runInContext(code,context);
const out={};
const tables=run('STRINGS');
out.tables={en:{...tables.English}, zh:{...tables['Simplified Chinese']}};
const snapshot=()=>({
 text:marked['[data-i18n]'].map(n=>n.textContent),
 placeholder:marked['[data-i18n-placeholder]'].map(n=>n.placeholder),
 aria:marked['[data-i18n-aria-label]'].map(n=>n.attributes['aria-label']),
 title:marked['[data-i18n-title]'].map(n=>n.title),
 lang:run('document.documentElement.lang'),
 pageTitle:[run('pageTitle()'), run('pageTitle("Console")')],
 trl:input.labels.map(label=>run(`trlText(${JSON.stringify(label)})`)),
 brief:run(`decisionBrief({scores:${JSON.stringify(input.scores)}})`)?.trl,
 names:input.samples.map(sample=>run(`sampleTitle(${JSON.stringify(sample)})`)),
});
out.views={};
for(const language of ['English','Simplified Chinese']){ run(`setLanguage(${JSON.stringify(language)})`); out.views[language]=snapshot(); }
process.stdout.write(JSON.stringify(out));
"""

LABELS = [evidence._trl_label(level) for level in range(1, 10)]
ODD_LABELS = ["TRL 7", "TRL 10 (beyond the scale)", "Level 7 (system prototype)", "TRL 7 (系统原型)x", ""]
SCORES = {"overall_score": 61.0, "trl_score": 7, "trl_label": LABELS[6], "mrl_score": 5}
SAMPLES = [
    {"slug": "a", "title": "Robotic-assisted surgery", "title_zh": "机器人辅助手术"},
    {"slug": "b", "title": "特高压直流输电", "title_zh": ""},
    {"slug": "c", "title": "Hyperloop"},
    {"slug": "d", "title": "Space-based solar power", "title_zh": "   "},
    {"slug": "e"},
    {"slug": "f", "title": "Named", "title_zh": 7},
]


@pytest.fixture(scope="module")
def page():
    node = shutil.which("node")
    assert node, "Node is required; missing execution is not a passing seam"
    done = subprocess.run(
        [node, "-e", _HARNESS], capture_output=True, text=True, encoding="utf-8", timeout=60, check=False,
        input=json.dumps({"root": ROOT.as_posix(), "language": "English", "labels": LABELS + ODD_LABELS,
                          "scores": SCORES, "samples": SAMPLES}, ensure_ascii=False))
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def test_the_scoring_domains_are_named_in_chinese(page):
    en, zh = page["tables"]["en"], page["tables"]["zh"]
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    select = re.search(r'<select class="chip-select" id="profile".*?</select>', index, re.S)[0]
    options = re.findall(r'<option value="([^"]*)" data-i18n="([^"]+)">([^<]*)</option>', select)
    assert len(options) == select.count("<option") == 6, "Every option is marked for translation"
    # The values the API takes are untouched; the words are the table's.
    assert [value for value, _key, _text in options] == [
        "", "industrial", "material_science", "biomedical", "clean_tech", "software_ai"]
    for value, key, text in options:
        assert en[key] == text, (key, "the markup's English is the table's")
        assert CJK.search(zh[key]) and zh[key] != en[key], key
        if value:
            assert key == f"profile_{value}"
    assert zh["auto_profile"] == "自动识别领域" and "方案" not in zh["auto_profile"]
    assert en["auto_profile"] == "Auto profile", "English is as it was"
    assert page["views"]["Simplified Chinese"]["text"] == ["工业制造", "自动识别领域"]
    assert page["views"]["English"]["text"] == ["Industrial", "Auto profile"]


def test_a_readiness_label_is_said_in_the_readers_language(page):
    en, zh = page["tables"]["en"], page["tables"]["zh"]
    english, chinese = page["views"]["English"], page["views"]["Simplified Chinese"]
    # English: every label exactly as saved, the nine and the odd ones alike.
    assert english["trl"] == LABELS + ODD_LABELS
    # The brief says the level and the score (result.js trlReading); the level's
    # sentence is said under the scorecard's "Why" where the score is between levels.
    assert english["brief"] == "TRL 7 (score 7 / 9)"
    # Chinese: the nine fixed sentences, by level; anything else as saved.
    assert chinese["trl"][9:] == ODD_LABELS
    for level, shown in enumerate(chinese["trl"][:9], start=1):
        assert shown == zh[f"trl_level_{level}"]
        assert re.fullmatch(rf"TRL {level}（[^（）A-Za-z]+）", shown), shown
    assert len(set(chinese["trl"][:9])) == 9
    assert chinese["brief"] == "TRL 7（评分 7 / 9）"
    # The English table's sentences are the pipeline's own, word for word, so
    # the level a Chinese reader is told is the level the scorecard recorded.
    for level in range(1, 10):
        assert en[f"trl_level_{level}"] == evidence._trl_label(level)


def test_labels_without_text_and_hover_titles_follow_the_language(page):
    english, chinese = page["views"]["English"], page["views"]["Simplified Chinese"]
    assert english["aria"] == ["Scoring profile", "Academic Commercialization Assessment"]
    assert chinese["aria"] == ["评分所用的领域", "学术成果商业化评估"]
    assert english["title"] == ["Attach a paper (PDF)"] and chinese["title"] == ["附加论文（PDF）"]
    assert english["placeholder"] == ["Search runs"] and CJK.search(chinese["placeholder"][0])
    assert (english["lang"], chinese["lang"]) == ("en", "zh-CN")


class _Attributes(HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = []

    def handle_starttag(self, tag, attrs):
        given = dict(attrs)
        for name, marker in (("aria-label", "data-i18n-aria-label"), ("title", "data-i18n-title"),
                             ("placeholder", "data-i18n-placeholder")):
            value = given.get(name)
            if value and LATIN_WORD.search(value):
                self.found.append((given.get("id") or given.get("class") or tag, name, value, given.get(marker)))


# Set by the page's script when it paints, each from its own strings; listed
# so that a new English attribute fails here until it is marked or painted.
PAINTED_BY_SCRIPT = {
    "index.html": {
        ("theme-toggle", "aria-label"), ("theme-toggle", "title"),        # theme.js
        ("mobile-menu", "aria-label"),                                     # chrome.js
        ("run-btn", "title"),                                              # app.js syncComposer
        ("topic", "placeholder"),                                          # app.js, topic_placeholder
        ("byok-model", "placeholder"), ("byok-search-key", "placeholder"), ("byok-llm-key", "placeholder"),  # byok_fields.js
    },
    "samples.html": {("sample-list", "aria-label"), ("theme-toggle", "aria-label"), ("theme-toggle", "title")},
    "admin.html": {("funnel-days", "aria-label"), ("theme-toggle", "aria-label"), ("theme-toggle", "title")},
    "privacy.html": {("theme-toggle", "aria-label"), ("theme-toggle", "title")},
}


@pytest.mark.parametrize("name", PAGES)
def test_no_label_in_the_markup_is_left_in_english(name, page):
    en, zh = page["tables"]["en"], page["tables"]["zh"]
    parser = _Attributes()
    html = (ROOT / "web" / name).read_text(encoding="utf-8")
    parser.feed(html)
    assert parser.found, name
    unmarked = []
    for where, attribute, value, key in parser.found:
        if key is None:
            painted = (where, attribute) in PAINTED_BY_SCRIPT[name] or (
                # The decision-context fields: decision_context.js paints every placeholder.
                name == "index.html" and attribute == "placeholder" and where.startswith("decision-"))
            if not painted:
                unmarked.append((where, attribute, value))
            continue
        assert key in en and key in zh, (name, key)
        assert CJK.search(zh[key]) or key in NOT_TRANSLATED, (name, key, zh[key])
        # What the markup says before the script runs is the table's English.
        assert en[key].split("  ")[0] == value.split("  ")[0], (name, key, value)
    assert not unmarked, unmarked
    # Every key the page names, of any kind, exists in both tables.
    for key in re.findall(r'data-i18n(?:-placeholder|-aria-label|-title)?="([^"]+)"', html):
        assert key in en and key in zh, (name, key)


def test_labels_a_script_sets_come_from_the_strings_too():
    """The three this change found written in place, and a guard against a fourth."""
    app = (JS / "app.js").read_text(encoding="utf-8")
    assert 'remove.setAttribute("aria-label", t("remove_paper"));' in app
    admin = (JS / "admin.js").read_text(encoding="utf-8")
    assert '$("#funnel-days").setAttribute("aria-label", t("funnel_window"));' in admin
    assert 'funnel_window: "Window"' in admin and 'funnel_window: "统计时段"' in admin
    reader = (JS / "samples.js").read_text(encoding="utf-8")
    assert 'listNode.setAttribute("aria-label", t("samples_title"));' in reader
    written_in_place = re.compile(
        r'setAttribute\("(?:aria-label|title|placeholder|alt)",\s*"[A-Za-z]'
        r'|\.(?:title|placeholder|ariaLabel)\s*=\s*"[A-Za-z]')
    for script in sorted(JS.glob("*.js")):
        found = written_in_place.findall(script.read_text(encoding="utf-8"))
        assert not found, (script.name, found)


def test_the_tab_is_named_from_the_strings_on_every_page(page):
    english, chinese = page["views"]["English"], page["views"]["Simplified Chinese"]
    assert english["pageTitle"] == ["Academic Commercialization Assessment",
                                    "Console · Academic Commercialization Assessment"]
    assert chinese["pageTitle"] == ["学术成果商业化评估", "Console · 学术成果商业化评估"]
    # What each page is served with is what the English interface then sets,
    # so nothing flickers for an English reader.
    served = {name: re.search(r"<title>([^<]*)</title>", (ROOT / "web" / name).read_text(encoding="utf-8"))[1]
              for name in PAGES}
    assert served["index.html"] == "Academic Commercialization Assessment"
    for name in ("samples.html", "admin.html", "privacy.html"):
        assert served[name].endswith(" · Academic Commercialization Assessment"), name
    # No page keeps the served title as the name it returns to.
    app = (JS / "app.js").read_text(encoding="utf-8")
    assert "const baseTitle = () => i18n.pageTitle();" in app and "= document.title;" not in app
    assert app.count("document.title = baseTitle();") >= 3, "at boot, on a change of language, and when the tab is seen again"
    reader = (JS / "samples.js").read_text(encoding="utf-8")
    assert 'const defaultTitle = () => i18n.pageTitle(t("samples_title"));' in reader and "= document.title;" not in reader
    for name in ("admin.js", "privacy.js"):
        assert "document.title = i18n.pageTitle(" in (JS / name).read_text(encoding="utf-8"), name


def test_a_sample_goes_by_its_chinese_name_in_the_chinese_interface(page):
    english, chinese = page["views"]["English"], page["views"]["Simplified Chinese"]
    assert english["names"] == ["Robotic-assisted surgery", "特高压直流输电", "Hyperloop", "Space-based solar power", "e", "Named"]
    assert chinese["names"] == ["机器人辅助手术", "特高压直流输电", "Hyperloop", "Space-based solar power", "e", "Named"]
    # The catalogue: a Chinese name for every sample whose title is not already Chinese.
    for sample in samples.list_samples():
        if CJK.search(sample["title"]):
            assert sample["title_zh"] == "", sample["slug"]
        else:
            assert CJK.search(sample["title_zh"]), sample["slug"]
    # Both places that draw a card use the one function.
    assert "link.textContent = result.sampleTitle(sample);" in (JS / "app.js").read_text(encoding="utf-8")
    reader = (JS / "samples.js").read_text(encoding="utf-8")
    assert 'el("span", "sample-card__title", sampleTitle(sample))' in reader
    assert "`${sampleTitle(sample)} · ${t(\"samples_title\")}`" in reader


# Chinese entries with no Chinese character in them, each for a reason.
NOT_TRANSLATED = {
    "brand": "the product's short name",
    "tokens_suffix": "the unit, as providers and the usage tables write it",
    "brief_verdict": "a pattern of placeholders",
    "sample_verdict": "a pattern of placeholders",
    "reviewer_notes_join": "punctuation",
    "rel_numbers_sep": "punctuation",
    "byok_llm_placeholder": "the term on every provider's console",
    "byok_serper_placeholder": "a provider's name and the same term",
    "account_keys": "the same term",
    "compare_delta": "a formula",
    "verdict_go": "the conclusion's code, as the form, the scope line and the report write it",
    "verdict_no_go": "the same code",
    "verdict_label_colon": "punctuation",
}


def test_every_chinese_entry_is_in_chinese_or_listed_with_its_reason(page):
    """A key added to both tables with its English pasted into the Chinese
    one passes the key-parity test and reads as English on a Chinese page."""
    en, zh = page["tables"]["en"], page["tables"]["zh"]
    assert len(zh) > 600 and set(zh) == set(en)
    left = sorted(key for key, value in zh.items() if value.strip() and not CJK.search(value))
    assert left == sorted(NOT_TRANSLATED), sorted(set(left) ^ set(NOT_TRANSLATED))
    # The sample reader's own, smaller table.
    source = (JS / "samples_i18n.js").read_text(encoding="utf-8")
    chinese = source.split('"Simplified Chinese": {', 1)[1].split("\n  },", 1)[0]
    entries = re.findall(r'^\s+([a-z0-9_]+): "((?:[^"\\]|\\.)*)",?\s*(?://.*)?$', chinese, re.M)
    assert len(entries) >= 15, len(entries)
    assert not [key for key, value in entries if value.strip() and not CJK.search(value)]
    assert zh["brief_risk"] == "最大风险"
