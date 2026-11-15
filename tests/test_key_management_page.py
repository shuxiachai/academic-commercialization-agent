"""Key management for an account, and the workbench of an account with no keys.

The flows run in tests/js/composer_contract.mjs (saved_keys: check_*,
tab_listed, needed) and the server half is tests/test_account_keys.py
(CheckSavedTests). This file holds the page as it is served: the markup, the
styles and the words.

What it guards, each seen on the live site on 2026-11-15:

- the addresses where keys come from were one sentence of plain text, six
  addresses to copy by hand;
- an account with no keys saw "10 of 10 runs left today" and an arrow to
  press, and learned keys were needed only by pressing it;
- a lost connection was reported as "Cannot reach the server. Is it still
  running?", in English whatever the interface language;
- the field the whole page is for had no name a screen reader could say;
- on a phone the run button dropped to the left of a row of its own.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from html.parser import HTMLParser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
JS = WEB / "static" / "js"
INDEX = (WEB / "index.html").read_text(encoding="utf-8")
CSS = (WEB / "static" / "css" / "workbench.css").read_text(encoding="utf-8")

VOID = {"input", "br", "img", "meta", "link", "hr", "source", "path", "circle", "rect", "line", "polyline"}


class _Page(HTMLParser):
    """Every element with its attributes, its ancestors and the text inside it."""

    def __init__(self):
        super().__init__()
        self.open, self.seen = [], []

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "inside": [n["tag"] for n in self.open],
                "within": [n["attrs"].get("id") for n in self.open if n["attrs"].get("id")], "text": ""}
        self.seen.append(node)
        if tag not in VOID:
            self.open.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.open.pop()

    def handle_endtag(self, tag):
        for at in range(len(self.open) - 1, -1, -1):
            if self.open[at]["tag"] == tag:
                del self.open[at:]
                return

    def handle_data(self, data):
        for node in self.open:
            node["text"] += data


@pytest.fixture(scope="module")
def page():
    parsed = _Page()
    parsed.feed(INDEX)
    by_id = {node["attrs"]["id"]: node for node in parsed.seen if node["attrs"].get("id")}
    return parsed.seen, by_id


@pytest.fixture(scope="module")
def strings():
    text = (JS / "i18n.js").read_text(encoding="utf-8")
    english, chinese = text.split('"Simplified Chinese": {', 1)

    def entry(table, key):
        found = re.search(rf'^\s+{key}: "((?:[^"\\]|\\.)*)"', table, re.M)
        assert found, key
        return found[1]

    return (lambda key: entry(english, key)), (lambda key: entry(chinese, key)), text


# ── Where keys come from ───────────────────────────────────────────────────

SOURCES = ["https://platform.deepseek.com/api-keys", "https://bailian.console.aliyun.com",
           "https://platform.openai.com/api-keys", "https://console.anthropic.com",
           "https://app.tavily.com", "https://serper.dev"]


def test_each_address_where_a_key_comes_from_is_a_link(page):
    seen, by_id = page
    links = [node for node in seen if node["tag"] == "a" and "byok-links" in node["within"]]
    assert [link["attrs"]["href"] for link in links] == SOURCES
    for link in links:
        # A new window: the form the visitor is filling in stays as it is.
        assert link["attrs"].get("target") == "_blank", link["attrs"]["href"]
        # What is shown is where it goes: no words standing in for an address.
        assert link["text"].strip() == link["attrs"]["href"].removeprefix("https://")
    # The sentence still names nothing as an address that is not a link.
    said = by_id["byok-links"]["text"]
    for link in links:
        said = said.replace(link["text"], "")
    assert not re.search(r"[a-z0-9-]+\.(com|dev|cn|ai)\b", said), said
    # In the form the keys are typed into, and nowhere else twice.
    assert "byok-form" in by_id["byok-links"]["within"]


def test_every_link_that_opens_a_new_window_gives_it_nothing_of_this_one(page):
    """A page opened in a new window can reach back through `window.opener`
    unless told otherwise, and is told where the visitor came from unless
    told otherwise. These lead from a form that holds API keys."""
    seen, _ = page
    outward = [node for node in seen if node["tag"] == "a" and node["attrs"].get("target") == "_blank"]
    assert len(outward) >= len(SOURCES)
    for link in outward:
        assert set(link["attrs"].get("rel", "").split()) >= {"noopener", "noreferrer"}, link["attrs"]
    # And none leaves by plain http, or to an address held in a script.
    for node in seen:
        if node["tag"] == "a" and node["attrs"].get("href", "").startswith("http"):
            assert node["attrs"]["href"].startswith("https://"), node["attrs"]["href"]


def test_the_words_between_the_links_are_in_both_languages():
    text = (JS / "byok_fields.js").read_text(encoding="utf-8")
    keys = ("byok_keys_model", "byok_keys_qwen", "byok_keys_search", "byok_keys_recommended", "byok_keys_json")
    for key in keys:
        assert len(re.findall(rf'^\s+{key}: "', text, re.M)) == 2, key
        assert f'data-byok-i18n="{key}"' in INDEX, key
    # The sentence of plain addresses is gone from every table that held it.
    for source in (text, (JS / "i18n.js").read_text(encoding="utf-8"), INDEX):
        assert "byok_hint" not in source


# ── The saved set, the tab's set, and the check ────────────────────────────

def test_the_form_says_which_keys_it_has_and_offers_what_can_be_done(page):
    _, by_id = page
    saved, tab = by_id["byok-saved"], by_id["byok-tab"]
    for block in (saved, tab):
        assert "hidden" in block["attrs"], "Nothing is claimed before the page knows"
        assert "byok-form" in block["within"]
    for name, home, label in (("byok-saved-check-now", "byok-saved", "byok_saved_check"),
                              ("byok-saved-remove", "byok-saved", "byok_saved_remove"),
                              ("byok-tab-clear", "byok-tab", "byok_tab_clear")):
        button = by_id[name]
        assert button["tag"] == "button" and button["attrs"]["type"] == "button", "Not a submit: the form is for new keys"
        assert home in button["within"] and button["attrs"]["data-i18n"] == label
    # What a check found is announced where it appears, and is not there until one was made.
    found = by_id["byok-saved-check"]
    assert found["attrs"].get("role") == "status" and "hidden" in found["attrs"] and "byok-saved" in found["within"]
    assert found["text"].strip() == ""
    # Hidden means hidden: these blocks are flex boxes, and a display rule beats the attribute.
    assert re.search(r"\.gate__saved\[hidden\], \.gate__saved-check\[hidden\] \{ display: none; \}", CSS)


def test_no_field_and_no_string_can_show_a_whole_saved_key(page, strings):
    """The summary lines have places for the ends of keys and nothing else,
    and no key field is filled from anything."""
    seen, _ = page
    english, chinese, _ = strings
    for table in (english, chinese):
        for key in ("byok_saved_summary", "byok_tab_summary"):
            assert set(re.findall(r"\{(\w+)\}", table(key))) - {"date"} == {"provider", "model", "llm", "search", "searchKey"}, key
        assert "{date}" in table("byok_saved_summary"), "When they were saved"
    for node in seen:
        if node["attrs"].get("id") in ("byok-llm-key", "byok-search-key"):
            assert "value" not in node["attrs"] and node["attrs"].get("type") == "password"
    app = (JS / "app.js").read_text(encoding="utf-8")
    assert not re.search(r'\$\("#byok-(llm|search)-key"\)\.value = (?!"")', app), "A key field is only ever emptied"


def test_what_a_check_says_is_said_in_both_languages(strings):
    english, chinese, _ = strings
    slots = {"byok_saved_check": set(), "byok_saved_checking": set(), "byok_saved_check_ok": {"time", "provider", "service"},
             "byok_saved_check_problem": {"time"}, "byok_saved_check_next": set(), "byok_saved_check_unverified": {"time"},
             "byok_saved_check_off": set(), "byok_saved_check_failed": set(), "byok_tab_clear": set(), "byok_tab_cleared": set(),
             "keys_needed": set(), "keys_needed_add": set(), "aria_topic": set(), "msg_network": set()}
    for key, expected in slots.items():
        for table in (english, chinese):
            assert set(re.findall(r"\{(\w+)\}", table(key))) == expected, key
        assert re.search(r"[一-鿿]", chinese(key)), key
        assert not re.search(r"[一-鿿]", english(key)), key
    # "Accepted" is said only of what was accepted; no answer is said as no answer.
    assert "accepted" in english("byok_saved_check_ok") and "接受" in chinese("byok_saved_check_ok")
    assert "could not be confirmed either way" in english("byok_saved_check_unverified")
    assert "无法确认" in chinese("byok_saved_check_unverified")
    # A saved key is replaced as a set: the advice says so, and does not say "save anyway".
    assert "whole set" in english("byok_saved_check_next") and "整组" in chinese("byok_saved_check_next")


def test_the_prose_says_what_the_new_controls_do(strings):
    """Prose is not covered by tests unless a test quotes it: the privacy
    page says what saved keys are used for, and a check on request is one
    more use; the operating guide lists every route."""
    english, chinese, _ = strings
    privacy = (WEB / "privacy.html").read_text(encoding="utf-8")
    assert f"When you press “{english('byok_saved_check')}” in the key form, the server asks each provider" in privacy
    assert f"你在密钥表单里点“{chinese('byok_saved_check')}”时，由服务器向各服务商确认" in privacy
    assert "What the providers answered is shown to you and not kept." in privacy
    assert "服务商的答复只显示给你，不会保存。" in privacy
    guide = (ROOT / "docs" / "operating-guide.md").read_text(encoding="utf-8")
    assert "| POST | `/api/auth/keys/check` |" in guide and "409 `no_saved_keys`" in guide
    assert '"Check these keys" in the key form calls `POST /api/auth/keys/check`' in guide


# ── An account with no keys ────────────────────────────────────────────────

def test_the_composer_says_keys_are_needed_and_how_to_add_them(page, strings):
    _, by_id = page
    english, chinese, _ = strings
    line, button = by_id["keys-needed"], by_id["keys-needed-add"]
    assert "hidden" in line["attrs"], "Not said until the page knows who is signed in and what they have"
    assert "composer" in " ".join(filter(None, line["within"])) or "composer__" in line["attrs"]["class"]
    assert button["tag"] == "button" and button["attrs"]["type"] == "button" and "keys-needed" in button["within"]
    assert english("keys_needed") in line["text"] and english("keys_needed_add") == button["text"].strip()
    assert chinese("keys_needed") == "先添加 API Key 才能开始评估。" and chinese("keys_needed_add") == "添加 API Key"
    # The line is a flex box; without this rule the attribute would not hide it.
    assert re.search(r"\.composer__need\[hidden\] \{ display: none; \}", CSS)
    # The day's allowance is still shown, and steps back.
    assert re.search(r"\.composer__quota--muted \{ opacity: 0\.\d+; \}", CSS)
    # Before the composer's own line about a free first assessment, which says the opposite.
    assert INDEX.index('id="keys-needed"') < INDEX.index('id="trial-note"')


# ── The server cannot be reached ───────────────────────────────────────────

_NETWORK = r"""
const fs=require('node:fs'),vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const map=new Map(); const storage={getItem:k=>map.get(k)??null,setItem:(k,v)=>map.set(k,String(v)),removeItem:k=>map.delete(k)};
const source=fs.readFileSync(input.root+'/web/static/js/api.js','utf8').replace(/^import .*;\r?\n/gm,'').replace(/export /g,'');
const ctx=vm.createContext({localStorage:storage,sessionStorage:storage,document:{},AbortSignal,
 fetch:async()=>{throw new TypeError('Failed to fetch');}});
vm.runInContext(source,ctx);
(async()=>{const out={};
 for(const [name,call] of Object.entries(input.calls)){
  try{await vm.runInContext(call,ctx); out[name]={ok:true};}
  catch(err){out[name]={status:err.status,code:err.code,message:err.message};}
 }
 process.stdout.write(JSON.stringify(out));})();
"""


def test_a_lost_connection_is_named_and_a_paid_request_is_still_unknown():
    node = shutil.which("node")
    assert node, "Node must execute the actual client; skipping loses the seam"
    calls = {"read": "checkSavedKeys()", "saved": "savedKeys()",
             "paid": "request('/api/runs', { method: 'POST', body: '{}' })"}
    done = subprocess.run([node, "-e", _NETWORK], capture_output=True, text=True, encoding="utf-8", timeout=30,
                          input=json.dumps({"root": ROOT.as_posix(), "calls": calls}), check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    out = json.loads(done.stdout)
    for name in ("read", "saved"):
        assert out[name] == {"status": 0, "code": "network_unreachable",
                             "message": "Cannot reach the server. Check your connection and try again."}, name
    # Losing the answer to a paid request does not prove it never arrived: that keeps its own code.
    assert out["paid"]["code"] == "paid_ack_unknown"


def test_no_page_asks_the_reader_whether_the_server_is_running(strings):
    english, chinese, _ = strings
    assert english("msg_network") == "Cannot reach the server. Check your connection and try again."
    assert chinese("msg_network") == "连接不上服务器，请检查网络后重试。"
    for path in [*WEB.glob("*.html"), *JS.glob("*.js")]:
        text = path.read_text(encoding="utf-8")
        assert "Is it still running" not in text and "still running?" not in text, path.name
    # Wherever the page shows a failure's own sentence, the unreachable server is said from the table.
    app = (JS / "app.js").read_text(encoding="utf-8")
    assert app.count("err.message") == 1 and 'err?.code === "network_unreachable" ? t("msg_network") : err.message' in app
    result = (JS / "result.js").read_text(encoding="utf-8")
    assert result.count("err.message") == 1 and 'err?.code === "network_unreachable" ? t("msg_network") : err.message' in result


# ── Names a screen reader can say ──────────────────────────────────────────

def test_the_topic_field_has_a_name_in_both_languages(page, strings):
    _, by_id = page
    english, chinese, _ = strings
    topic = by_id["topic"]
    assert topic["tag"] == "textarea"
    # A placeholder is not a name: it goes when typing starts, and is an example, not a label.
    assert topic["attrs"]["aria-label"] == english("aria_topic") == "Research topic or paper"
    assert topic["attrs"]["data-i18n-aria-label"] == "aria_topic"
    assert chinese("aria_topic") == "研究课题或论文"
    i18n = (JS / "i18n.js").read_text(encoding="utf-8")
    assert "data-i18n-aria-label" in i18n, "The table's name is put on the field when the language changes"


def test_every_field_of_the_decision_context_is_inside_its_label(page, strings):
    seen, by_id = page
    english, chinese, _ = strings
    fields = [node for node in seen if "data-context-field" in node["attrs"]]
    assert len(fields) >= 6
    labelled = {node["attrs"]["for"] for node in seen if node["tag"] == "label" and "for" in node["attrs"]}
    for field in fields:
        named = ("label" in field["inside"] or field["attrs"].get("id") in labelled
                 or field["attrs"].get("aria-label") or field["attrs"].get("aria-labelledby") in by_id)
        assert named, field["attrs"]
    # So is every field of the key form: three of them had a placeholder and no name.
    for name, key in (("byok-llm-key", "aria_llm_key"), ("byok-model", "aria_model_name"), ("byok-search-key", "aria_search_key")):
        assert by_id[name]["attrs"]["aria-label"] == english(key) and by_id[name]["attrs"]["data-i18n-aria-label"] == key
        assert re.search(r"[\u4e00-\u9fff]", chinese(key)), key
    for node in seen:
        if node["tag"] in ("input", "select", "textarea") and "byok-form" in node["within"]:
            if node["attrs"].get("type") in ("hidden", "submit"):
                continue
            named = ("label" in node["inside"] or node["attrs"].get("id") in labelled
                     or node["attrs"].get("aria-label") or node["attrs"].get("aria-labelledby") in by_id)
            assert named, node["attrs"]


# ── The run button on a phone ──────────────────────────────────────────────

def test_the_run_button_keeps_to_the_right_when_the_bar_wraps():
    """The bar is a wrapping flex row with a spacer before the button. When
    the row is too narrow the button wraps and the spacer stays above, so it
    sat at the left of a row of its own. An automatic left margin puts it at
    the right end of whichever row it lands on."""
    assert re.search(r"\.composer__bar \.send-btn \{ margin-left: auto; \}", CSS)
    bar = re.search(r"\.composer__bar \{[^}]*\}", CSS)[0]
    assert "flex-wrap: wrap" in bar, "The reason the margin is needed"
    # It is still the last thing in the bar.
    start = INDEX.index('class="composer__bar"')
    inside = INDEX[start:INDEX.index("</form>", start)]
    assert inside.rindex('class="send-btn') > inside.rindex("composer__spacer")
