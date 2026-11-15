"""Keys an account chose to keep on its device, and nobody else's.

An account's API keys lived in the open tab alone: closing the tab, or coming
back the next day still signed in, meant pasting two keys again. Reported on
2026-11-15 as a fault by an account that had saved its keys and was asked for
them on its next visit. The server still never stores a key. What an account
now gets, with a tick it can remove, is a second copy in this browser's local
storage, which a new tab reads back.

The tick first shipped unticked (#407) and starts ticked since later the same
day, on the owner's decision: the complaint was being asked again, and an
option that has to be found does not answer it. A device where the box was
unticked keeps it unticked, so that nobody who declined is ticked back in.

That copy is a live third-party credential on a disk, so these are the rules
it is held to:

- nothing is kept when keys are saved with the box unticked, and saving
  again without the tick removes what was kept;
- it is kept for one account and given back only to that account: someone
  else signing in on the same browser does not receive it, and it is
  removed when they do;
- signing out removes it;
- a copy that cannot be read is removed and never used.

The shipped api.js runs in Node against two maps standing for the browser's
storages; a "new tab" is a fresh module with the same local map and an empty
session map.
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
// One tab: its own session storage, the browser's shared local storage.
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
 if(step.corrupt!==undefined){local.set('byok-remembered-v1',step.corrupt); out.push({corrupt:true}); continue;}
 const done=current.run(step.run);
 out.push({...done, local:Object.fromEntries(local), session:Object.fromEntries(current.session)});
}
process.stdout.write(JSON.stringify(out));
"""

KEYS = {"provider": "qwen", "llmKey": "fixture-llm", "search": "tavily", "searchKey": "fixture-search", "model": "qwen3.8-27b"}
OTHER = {"provider": "deepseek", "llmKey": "fixture-other", "search": "serper", "searchKey": "fixture-other-search",
         "model": "deepseek-chat"}
SLOT = "byok-remembered-v1"
J = json.dumps


def play(steps, local=None):
    node = shutil.which("node")
    assert node, "Node must execute the actual client; skipping loses the seam"
    done = subprocess.run([node, "-e", _HARNESS], capture_output=True, text=True, encoding="utf-8", timeout=30,
                          input=json.dumps({"root": ROOT.as_posix(), "steps": steps, "local": local or {}}), check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return json.loads(done.stdout)


def run(code):
    return {"run": code}


NEW_TAB = {"tab": True}


def test_nothing_is_kept_unless_the_account_asked():
    saved, later, *_ = out = play([run(f"setByok({J(KEYS)})"), run("getByok()"), NEW_TAB,
                                   run("restoreByok('a@example.org')"), run("getByok()"),
                                   run("byokRemembered('a@example.org')")])
    assert saved["value"] is True and later["value"] == KEYS
    assert saved["local"] == {}, "Saving keys writes nothing outside the tab"
    assert list(saved["session"]) == ["byok-credentials"]
    assert [step.get("value") for step in out[3:]] == [False, None, False], "A new tab has no keys, as before"
    assert out[-1]["local"] == {}


def test_a_remembered_copy_comes_back_in_a_new_tab_of_the_same_account():
    out = play([run(f"setByok({J(KEYS)})"), run(f"rememberByok({J(KEYS)}, ' A@Example.ORG ')"),
                run("byokRemembered('a@example.org')"), NEW_TAB,
                run("getByok()"), run("restoreByok('A@example.org')"), run("getByok()"), run("byokBody(getByok())")])
    assert out[1]["value"] is True
    assert json.loads(out[1]["local"][SLOT]) == {"owner": "a@example.org", "creds": KEYS}, "One account's, by its address in lower case"
    assert out[2]["value"] is True
    assert out[4]["value"] is None, "The new tab starts without keys until the account is known"
    assert out[5]["value"] is True and out[6]["value"] == KEYS
    assert json.loads(out[6]["session"]["byok-credentials"]) == KEYS, "...and then holds them as a tab always did"
    assert out[7]["value"] == {"llm_provider": "qwen", "llm_api_key": "fixture-llm", "tavily_api_key": "fixture-search",
                               "llm_model": "qwen3.8-27b"}
    assert SLOT in out[6]["local"], "Reading it back does not use it up"


def test_another_account_on_the_same_browser_does_not_receive_it_and_it_goes():
    out = play([run(f"rememberByok({J(KEYS)}, 'a@example.org')"), NEW_TAB,
                run("byokRemembered('b@example.org')"), run("restoreByok('b@example.org')"), run("getByok()"), NEW_TAB,
                run("restoreByok('a@example.org')"), run("getByok()")])
    assert out[2]["value"] is False and SLOT in out[2]["local"], "Asking whether there is one changes nothing"
    assert out[3]["value"] is False and out[4]["value"] is None
    assert out[3]["local"] == {}, "Someone else signed in here: the first account's keys do not stay on this disk"
    assert out[6]["value"] is False and out[7]["value"] is None, "...so they are not there for the first account either"


@pytest.mark.parametrize("owner", ["null", "''", "'   '", "undefined", "42", "{}"])
def test_without_an_account_nothing_is_kept_and_nothing_is_given_back(owner):
    out = play([run(f"rememberByok({J(KEYS)}, {owner})")])
    assert out[0]["value"] is False and out[0]["local"] == {}
    kept = {SLOT: J({"owner": "a@example.org", "creds": KEYS})}
    out = play([run(f"restoreByok({owner})"), run("getByok()"), run(f"byokRemembered({owner})")], local=kept)
    assert [step["value"] for step in out] == [False, None, False]
    assert out[-1]["local"] == kept, "No account is not another account: the copy is left for its owner"


def test_keys_already_in_the_tab_are_not_replaced():
    """What the tab holds is the person's latest choice, e.g. keys typed here
    a moment ago without the tick, while another tab's remembered copy exists."""
    kept = {SLOT: J({"owner": "a@example.org", "creds": KEYS})}
    out = play([run(f"setByok({J(OTHER)})"), run("restoreByok('a@example.org')"), run("getByok()")], local=kept)
    assert out[1]["value"] is False and out[2]["value"] == OTHER
    assert out[2]["local"] == kept


def test_saving_without_the_tick_and_signing_out_both_remove_it():
    out = play([run(f"rememberByok({J(KEYS)}, 'a@example.org')"), run("forgetByok()"), run("byokRemembered('a@example.org')"),
                NEW_TAB, run("restoreByok('a@example.org')"), run("getByok()"), run("forgetByok()")])
    assert out[1]["value"] is True and out[1]["local"] == {}
    assert out[2]["value"] is False and out[4]["value"] is False and out[5]["value"] is None
    assert out[6]["value"] is True, "Forgetting what is not there succeeds"


@pytest.mark.parametrize("stored", [
    "not json", "null", "[]", "42", '"text"', "{}",
    J({"owner": "a@example.org"}),
    J({"owner": "a@example.org", "creds": None}),
    J({"owner": "a@example.org", "creds": {**KEYS, "llmKey": ""}}),
    J({"owner": "a@example.org", "creds": {**KEYS, "provider": "elsewhere"}}),
    J({"owner": "a@example.org", "creds": {**KEYS, "model": "not a model name"}}),
    J({"owner": ["a@example.org"], "creds": KEYS}),
    J({"creds": KEYS}),
    J(KEYS),
])
def test_a_copy_that_cannot_be_read_is_removed_and_never_used(stored):
    out = play([run("byokRemembered('a@example.org')"), run("restoreByok('a@example.org')"), run("getByok()")],
               local={SLOT: stored})
    assert "error" not in out[0] and "error" not in out[1], "A damaged copy is not an error in the page"
    assert [step["value"] for step in out] == [False, False, None]
    assert out[1]["local"] == {}, "It is not left to be tried again"
    assert out[2]["session"] == {}


def test_only_valid_keys_are_kept():
    out = play([run(f"rememberByok({J({**KEYS, 'llmKey': ' '})}, 'a@example.org')"),
                run("rememberByok(null, 'a@example.org')")])
    assert [step.get("error") for step in out] == ["invalid_byok", "invalid_byok"]
    assert out[-1]["local"] == {}


def test_a_browser_that_refuses_the_write_says_so_and_the_tab_still_has_its_keys():
    out = play([{"deny": {"write": True}}, run(f"setByok({J(KEYS)})"), run(f"rememberByok({J(KEYS)}, 'a@example.org')"),
                run("getByok()"), run("byokRemembered('a@example.org')")])
    assert out[2]["value"] is False, "The page can tell the person the keys were not kept"
    assert out[3]["value"] == KEYS and out[3]["local"] == {}
    assert out[4]["value"] is False, "...and the form does not show a tick for them afterwards"
    # A browser that refuses the removal: signing out reports it, as it does for the other credentials.
    out = play([run(f"rememberByok({J(KEYS)}, 'a@example.org')"), {"deny": {"remove": True}}, run("forgetByok()"),
                run("byokRemembered('a@example.org')"), run("restoreByok('a@example.org')"), run("getByok()")])
    assert out[2]["value"] is False
    assert [step["value"] for step in out[3:]] == [False, False, None], "...and this page does not use what it failed to remove"


def test_what_the_page_says_about_keys_matches_where_they_are_kept():
    """ "Your keys stay in this browser" read as a promise that they would be
    there next time. Every sentence that says where keys are kept now says
    for how long, and the privacy page names the second place."""
    strings = (JS / "i18n.js").read_text(encoding="utf-8")
    english, chinese = strings.split('"Simplified Chinese": {', 1)

    def entry(table, key):
        return re.search(rf'^\s+{key}: "((?:[^"\\]|\\.)*)"', table, re.M)[1]

    for key in ("account_sub", "account_sub_trial", "landing_pay_body"):
        said = entry(english, key)
        assert "until you sign out unless you turn that off" in said and "remembered on" in said, key
        assert "直到你退出登录" in entry(chinese, key) and "可以取消" in entry(chinese, key), key
    for key in ("byok_account_note", "byok_trial_note"):
        assert "remembered on this device until you sign out unless you untick Remember below" in entry(english, key), key
        assert "默认在这台设备上记住，直到你退出登录；取消勾选下方的“记住”则只保留在当前标签页" in entry(chinese, key), key
    # Nothing still says the tab is the default, or that remembering has to be chosen.
    for table in (english, chinese):
        for key in ("account_sub", "account_sub_trial", "landing_pay_body", "byok_account_note", "byok_trial_note"):
            for stale in ("unless you choose to remember", "unless you tick Remember", "默认只在当前标签页"):
                assert stale not in entry(table, key), (key, stale)
    for table in (english, chinese):
        for key in ("account_sub", "account_sub_trial", "landing_pay_body", "byok_account_note"):
            said = entry(table, key)
            assert "never stores" in said or "不会保存" in said or "从不保存" in said, (key, "the server's part is unchanged")
    # A visitor with keys alone is not offered the choice, and is told the tab is all there is.
    assert "disappear from this browser when the tab closes" in entry(english, "byok_sub")
    # The tick says what it does and what it costs.
    for word in ("unencrypted", "until you sign out", "Untick this on a shared computer"):
        assert word in entry(english, "byok_remember_note"), word
    for word in ("未加密", "退出登录", "公用电脑上请取消勾选"):
        assert word in entry(chinese, "byok_remember_note"), word
    assert "Leave this off" not in entry(english, "byok_remember_note"), "The box is on: the advice is to untick it"
    privacy = (ROOT / "web" / "privacy.html").read_text(encoding="utf-8")
    for sentence in (
        "If you are signed in, a copy of the keys is also kept in local storage, unencrypted, so that a new tab has "
        'them, unless you untick "Remember these keys on this device" when you save them',
        "removed when you sign out, when you save keys without the tick, when you delete your account, and when "
        "another account signs in on the same browser",
        "Unticking the box is itself remembered in local storage, as a mark that holds no key",
        "如果你已登录，密钥还会以未加密的形式在本地存储里另存一份，新开的标签页可以直接使用；保存时取消勾选“在这台设备上记住这些密钥”则不会另存",
        "退出登录、不勾选再次保存、删除账号，或有另一个账号在同一浏览器登录时，这份副本会被删除",
        "取消勾选这一选择本身也记在本地存储里，只是一个不含密钥的标记",
    ):
        assert sentence in privacy, sentence
    assert "If you are signed in and tick" not in privacy and "如果你已登录并勾选" not in privacy
    assert "stay in your browser tab" not in privacy and "只留在你的浏览器标签页里" not in privacy
    # The page's own names for the tick are the ones the privacy page quotes.
    assert entry(english, "byok_remember") == "Remember these keys on this device"
    assert entry(chinese, "byok_remember") == "在这台设备上记住这些密钥"


def test_the_page_keeps_forgets_and_restores_at_the_right_moments():
    """The seams between the page and the functions above. The flows
    themselves run in tests/js/composer_contract.mjs (remembered_keys)."""
    app = (JS / "app.js").read_text(encoding="utf-8")
    # Restored when the account is known, before the page decides whether it has keys.
    known = app.split("function applyAccountMode(me) {", 1)[1].split("\n}\n", 1)[0]
    assert known.index("api.restoreByok(me.email);") < known.index("byokMode = Boolean(api.getByok());")
    # Signing out and deleting the account both remove the copy; a failed removal is not a clean sign-out.
    out = app.split("async function exitCredentials() {", 1)[1].split("\n}\n", 1)[0]
    assert "const rememberedCleared = api.forgetByok();" in out
    assert "if (byokCleared && codeCleared && sessionCleared && receiptsCleared && rememberedCleared) {" in out
    deleted = app.split("// The account is gone server-side.", 1)[1].split("location.reload();", 1)[0]
    assert "api.forgetByok();" in deleted
    # Nothing but those functions touches the slot, and the session slot is still the tab's.
    client = (JS / "api.js").read_text(encoding="utf-8")
    assert 'const rememberedSlot = credentialSlot("localStorage", REMEMBERED_KEY);' in client
    assert 'const byokSlot = credentialSlot("sessionStorage", BYOK_KEY);' in client
    for script in JS.glob("*.js"):
        if script.name != "api.js":
            assert SLOT not in script.read_text(encoding="utf-8"), script.name
    # The box is in the form and only an account is shown it. The markup leaves
    # it unticked and hidden: whether it is ticked is the script's to say, for
    # an account, so a visitor with keys alone never has a ticked box.
    index = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    row = re.search(r'<div id="byok-remember-row" hidden>.*?</div>', index, re.S)[0]
    assert '<input type="checkbox" id="byok-remember">' in row and "checked" not in row
    assert 'data-i18n="byok_remember"' in row and 'data-i18n="byok_remember_note"' in row
    # Ticked for an account unless this device declined; a copy already kept shows as ticked either way.
    assert ('$("#byok-remember").checked = account && (api.byokRemembered(accountEmail) || api.byokRememberWanted());'
            in app)
    # The choice made at each save is the one the form opens with next time.
    saved = app.split("// Keys saved for the account; the identity and its history are unchanged.", 1)[1].split("finish();", 1)[0]
    assert saved.count("api.setByokRememberWanted(") == 1 and 'api.setByokRememberWanted($("#byok-remember").checked);' in saved


def test_a_device_where_the_box_was_unticked_stays_unticked():
    """The box starts ticked. Someone who unticks it has decided, for this
    device: the form must not tick them back in next time, or their next
    save would keep keys they declined to keep. What records the decision
    is a mark with no key in it, which signing out leaves alone."""
    mark = "byok-remember-off"
    out = play([run("byokRememberWanted()"), run("setByokRememberWanted(false)"), run("byokRememberWanted()"), NEW_TAB,
                run("byokRememberWanted()"), run("forgetByok()"), run("setByok(null)"), run("byokRememberWanted()"),
                run("setByokRememberWanted(true)"), run("byokRememberWanted()"), NEW_TAB, run("byokRememberWanted()")])
    assert out[0]["value"] is True and out[0]["local"] == {}, "A browser that has said nothing: remembered by default"
    assert out[2]["value"] is False and out[2]["local"] == {mark: "1"}, "The mark says only that; it holds no key"
    assert out[4]["value"] is False, "...and a new tab knows it"
    assert out[7]["value"] is False and out[7]["local"] == {mark: "1"}, "Signing out does not undo the decision"
    assert out[9]["value"] is True and out[9]["local"] == {} and out[11]["value"] is True, "Ticking it again does"
    # The mark and the copy do not disturb each other.
    out = play([run(f"rememberByok({J(KEYS)}, 'a@example.org')"), run("setByokRememberWanted(false)"),
                run("byokRemembered('a@example.org')"), run("setByokRememberWanted(true)"), run("byokRemembered('a@example.org')")])
    assert out[2]["value"] is True and out[4]["value"] is True
    assert set(out[1]["local"]) == {SLOT, mark} and set(out[3]["local"]) == {SLOT}


def test_a_browser_whose_storage_cannot_be_read_is_not_ticked():
    """Nothing can be kept there, so a ticked box would only produce the
    'could not keep them' message on every save."""
    out = play([{"deny": {"read": True}}, run("byokRememberWanted()")])
    assert out[1]["value"] is False
    # A refused write of the mark is not an error in the page; the box is then ticked again next time.
    out = play([{"deny": {"write": True}}, run("setByokRememberWanted(false)"), {"deny": {"write": False}},
                run("byokRememberWanted()")])
    assert "error" not in out[1] and out[3]["value"] is True
