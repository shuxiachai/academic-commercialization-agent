"""The browser's part in an account's saved keys: it keeps none.

The server half is tests/test_account_keys.py; the page's flows run in
tests/js/composer_contract.mjs (saved_keys). This file holds what is left:
the two small things the browser still stores about keys, the copy an earlier
design left behind, and the words.

For a few hours on 2026-11-15 (#407, #408) the key form kept a copy of an
account's keys in the browser's local storage. That made keys follow a
browser instead of an account, and put a credential on a disk. Nothing writes
that copy now, nothing reads it, and one left behind is removed.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
JS = ROOT / "web" / "static" / "js"
LEFTOVER, DECLINED = "byok-remembered-v1", "byok-remember-off"

_HARNESS = r"""
const fs=require('node:fs'),vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const local=new Map(Object.entries(input.local??{}));
let deny={read:false,write:false,remove:false};
const storage=(map,guarded)=>({
 getItem:k=>{if(guarded&&deny.read)throw Error('restricted');return map.get(k)??null;},
 setItem:(k,v)=>{if(guarded&&deny.write)throw Error('quota');map.set(k,String(v));},
 removeItem:k=>{if(guarded&&deny.remove)throw Error('remove denied');map.delete(k);},
});
const source=fs.readFileSync(input.root+'/web/static/js/api.js','utf8').replace(/^import .*;\r?\n/gm,'').replace(/export /g,'');
function tab(){
 const session=new Map();
 const ctx=vm.createContext({localStorage:storage(local,true),sessionStorage:storage(session,false),
  fetch:async()=>{throw Error('no request belongs here');},document:{}});
 vm.runInContext(source,ctx);
 const run=code=>{try{return {value:vm.runInContext(code,ctx)};}catch(err){return {error:err.code??err.message};}};
 return {run,session};
}
const out=[]; let current=tab();
for(const step of input.steps){
 if(step.tab){current=tab(); out.push({tab:true}); continue;}
 if(step.deny){deny={...deny,...step.deny}; out.push({deny:true}); continue;}
 const done=current.run(step.run);
 out.push({...done, local:Object.fromEntries(local), session:Object.fromEntries(current.session)});
}
process.stdout.write(JSON.stringify(out));
"""

KEYS = {"provider": "qwen", "llmKey": "fixture-llm", "search": "tavily", "searchKey": "fixture-search", "model": "qwen3.8-27b"}
J = json.dumps
NEW_TAB = {"tab": True}


def play(steps, local=None):
    node = shutil.which("node")
    assert node, "Node must execute the actual client; skipping loses the seam"
    done = subprocess.run([node, "-e", _HARNESS], capture_output=True, text=True, encoding="utf-8", timeout=30,
                          input=json.dumps({"root": ROOT.as_posix(), "steps": steps, "local": local or {}}), check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def run(code):
    return {"run": code}


def test_a_copy_of_the_keys_left_in_the_browser_is_removed_and_never_read():
    left = {LEFTOVER: J({"owner": "a@example.org", "creds": KEYS})}
    out = play([run("getByok()"), run("discardBrowserKeys()"), run("getByok()"), NEW_TAB, run("getByok()")], local=left)
    assert out[0]["value"] is None, "Nothing gives the tab the keys of the copy"
    assert out[1]["value"] is True and out[1]["local"] == {}
    assert out[2]["value"] is None and out[4]["value"] is None
    # Removing what is not there succeeds; a browser that refuses says so.
    assert play([run("discardBrowserKeys()")])[0]["value"] is True
    out = play([{"deny": {"remove": True}}, run("discardBrowserKeys()")], local=left)
    assert out[1]["value"] is False
    # The functions that wrote and read the copy are gone, and nothing else names the slot.
    client = (JS / "api.js").read_text(encoding="utf-8")
    for gone in ("rememberByok", "restoreByok", "byokRemembered", "forgetByok", "rememberedSlot"):
        assert gone not in client, gone
    assert client.count(LEFTOVER) == 1 and "localStorage.removeItem(LEFTOVER_KEY)" in client
    for script in JS.glob("*.js"):
        if script.name != "api.js":
            assert LEFTOVER not in script.read_text(encoding="utf-8"), script.name


def test_saving_keys_in_the_tab_writes_nothing_that_outlives_it():
    saved, *_ = out = play([run(f"setByok({J(KEYS)})"), run("getByok()"), NEW_TAB, run("getByok()")])
    assert saved["local"] == {} and list(saved["session"]) == ["byok-credentials"]
    assert out[1]["value"] == KEYS and out[3]["value"] is None, "The tab's keys are the tab's"


def test_a_device_where_the_box_was_unticked_stays_unticked():
    """The box that saves keys to the account starts ticked. Someone who
    unticks it has decided, for this device: the form must not tick them back
    in next time, or their next save would store keys they declined to store.
    What records the decision is a mark with no key in it."""
    out = play([run("keySavingWanted()"), run("setKeySavingWanted(false)"), run("keySavingWanted()"), NEW_TAB,
                run("keySavingWanted()"), run("discardBrowserKeys()"), run("setByok(null)"), run("keySavingWanted()"),
                run("setKeySavingWanted(true)"), run("keySavingWanted()"), NEW_TAB, run("keySavingWanted()")])
    assert out[0]["value"] is True and out[0]["local"] == {}, "A browser that has said nothing: saved by default"
    assert out[2]["value"] is False and out[2]["local"] == {DECLINED: "1"}, "The mark says only that; it holds no key"
    assert out[4]["value"] is False, "...and a new tab knows it"
    assert out[7]["value"] is False and out[7]["local"] == {DECLINED: "1"}, "Signing out does not undo the decision"
    assert out[9]["value"] is True and out[9]["local"] == {} and out[11]["value"] is True, "Ticking it again does"


def test_a_browser_whose_storage_cannot_be_read_still_saves_to_the_account():
    """Saving to the account needs no browser storage, so there is nothing
    to decline there: the box is ticked. (When the box kept keys in the
    browser, unreadable storage meant it could keep none, and read as off.)"""
    out = play([{"deny": {"read": True}}, run("keySavingWanted()")])
    assert out[1]["value"] is True
    out = play([{"deny": {"write": True}}, run("setKeySavingWanted(false)"), {"deny": {"write": False}},
                run("keySavingWanted()")])
    assert "error" not in out[1] and out[3]["value"] is True, "A refused write of the mark is not an error in the page"


def test_the_page_asks_the_server_and_keeps_nothing():
    """The seams between the page and the account's keys."""
    app = (JS / "app.js").read_text(encoding="utf-8")
    client = (JS / "api.js").read_text(encoding="utf-8")
    # The three requests, and that saving sends the same fields a run would have carried.
    assert 'export const savedKeys = () => request("/api/auth/keys");' in client
    assert 'export const removeSavedKeys = () => request("/api/auth/keys", { method: "DELETE" });' in client
    save = client.split('export const saveKeys = (creds) => request("/api/auth/keys", {', 1)[1].split("});", 1)[0]
    assert "...json(byokBody(validateByok(creds)))," in save and 'method: "PUT",' in save
    # Whether the account has keys comes from its sign-in answer, before the page decides to ask for any.
    known = app.split("function applyAccountMode(me) {", 1)[1].split("\n}\n", 1)[0]
    assert "accountKeysSaved = me.keys_saved === true;" in known
    assert "function accountHasKeys() {\n  return accountKeysSaved || Boolean(api.getByok());\n}" in app
    # Every place that asked "does this account have keys" asks that, not "does this tab".
    for line in (
        "  const show = trialPays() && !accountHasKeys();",
        '  if (accountMode && !accountHasKeys() && !operatorPays() && !(operation === "run" && trialPays())) {',
        '  const onTrial = operation === "run" && !accountHasKeys() && trialPays();',
        "    const own = accountMode && accountHasKeys();",
        "      if (!accountHasKeys() && !operatorPays() && !trialPays()) await showGate(null, { keysOnly: true });",
        "        if (accountHasKeys() || operatorPays() || trialPays()) { finish(); return; }",
    ):
        assert line in app, line
    # A copy left by the earlier design is removed at boot and at sign-out; signing out removes nothing from the account.
    assert "i18n.apply();\n// A copy of an account's keys left in this browser by the earlier design.\napi.discardBrowserKeys();" in app
    out = app.split("async function exitCredentials() {", 1)[1].split("\n}\n", 1)[0]
    assert "const rememberedCleared = api.discardBrowserKeys();" in out and "removeSavedKeys" not in out
    assert "if (byokCleared && codeCleared && sessionCleared && receiptsCleared && rememberedCleared) {" in out
    # Saved keys leave the page: not in the tab's slot, not in the fields.
    saved = app.split("await api.saveKeys(creds);", 1)[1].split("finish();", 1)[0]
    for line in ("accountKeysSaved = true;", "api.setByok(null);", '$("#byok-llm-key").value = "";',
                 '$("#byok-search-key").value = "";'):
        assert line in saved, line
    # The box and the summary are in the form; the markup leaves the box unticked and both hidden.
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    row = re.search(r'<div id="byok-save-row" hidden>.*?</div>', index, re.S)[0]
    assert '<input type="checkbox" id="byok-save">' in row and "checked" not in row
    assert 'data-i18n="byok_to_account"' in row and 'data-i18n="byok_to_account_note"' in row
    listed = re.search(r'<div class="gate__saved" id="byok-saved" hidden>.*?</div>', index, re.S)[0]
    assert 'id="byok-saved-text"' in listed and 'id="byok-saved-remove" data-i18n="byok_saved_remove"' in listed
    assert "byok-remember" not in index


@pytest.fixture(scope="module")
def strings():
    text = (JS / "i18n.js").read_text(encoding="utf-8")
    english, chinese = text.split('"Simplified Chinese": {', 1)

    def entry(table, key):
        return re.search(rf'^\s+{key}: "((?:[^"\\]|\\.)*)"', table, re.M)[1]

    return (lambda key: entry(english, key)), (lambda key: entry(chinese, key)), text


def test_what_the_page_says_about_keys_is_what_happens_to_them(strings):
    """Every sentence said "this server never stores them". The keys are
    saved with the account now, and each of those sentences says so."""
    english, chinese, text = strings
    for key in ("account_sub", "account_sub_trial", "landing_pay_body", "byok_account_note", "byok_trial_note"):
        assert "saved with your account, encrypted" in english(key), key
        assert "加密保存到你的账号里" in chinese(key), key
    for stale in ("never stores them", "不会保存它们", "本服务器从不保存", "stay in this browser", "保存在这个浏览器",
                  "Remember these keys", "记住这些密钥", "byok_remember"):
        assert stale not in text, stale
    assert "you add them once" in english("account_sub") and "wherever you sign in" in english("account_sub")
    assert "you can remove them at any time" in english("landing_pay_body") and "随时可以删除" in chinese("landing_pay_body")
    # The box says what ticking and unticking do.
    for word in ("Saved with your account, encrypted", "wherever you sign in", "Untick to use them in this tab only",
                 "nothing is saved", "asked for again next time"):
        assert word in english("byok_to_account_note"), word
    for word in ("加密保存到你的账号里", "任何设备登录后都能直接使用", "取消勾选则只在当前标签页使用", "不会保存", "下次需要重新填写"):
        assert word in chinese("byok_to_account_note"), word
    # The summary has a place for each thing the server says, in both languages.
    for table in (english, chinese):
        for slot in ("{provider}", "{model}", "{llm}", "{search}", "{searchKey}"):
            assert slot in table("byok_saved_summary"), slot
    # The submit button keeps its own words: the box's strings must not take its key.
    assert english("byok_save") == "Save keys" and chinese("byok_save") == "保存密钥"
    for table in text.split('"Simplified Chinese": {', 1):
        keys = re.findall(r"^    ([a-z0-9_]+): ", table, re.M)
        assert len(keys) == len(set(keys)), sorted(key for key in set(keys) if keys.count(key) > 1)
    # A visitor with keys alone has no account: that form still says the tab is all there is.
    assert "disappear from this browser when the tab closes" in english("byok_sub")
    # What the markup shows before the script runs is the same text.
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    for key in ("landing_pay_body", "account_sub", "account_sub_trial", "byok_to_account", "byok_to_account_note"):
        assert f'data-i18n="{key}"' in index and english(key) in index, key
