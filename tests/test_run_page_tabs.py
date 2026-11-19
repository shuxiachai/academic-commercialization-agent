"""The run page's tabs are tabs to a screen reader and to a keyboard.

They were six buttons in a row: no role, nothing saying which was selected
or what it controlled, and Tab had to be pressed through every one of them
to reach the report. They follow the WAI-ARIA tabs pattern now: a tablist,
tabs that say whether they are selected and which panel is theirs, panels
that name their tab, one tab stop for the whole strip, and Left / Right /
Home / End to move along it, selecting as they go.

On a narrow screen the strip scrolls sideways, as it did, and now shows
that it does: the edge with more behind it fades.

Run through Node against the shipped result.js, like the other page tests.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

_SCRIPT = r'''
const fs=require('node:fs'), vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element {
 constructor(tag){Object.assign(this,{tag,children:[],dataset:{},style:{},attributes:{},listeners:{},textContent:'',className:'',
  focused:0,scrolled:0,scrollLeft:0,clientWidth:0,scrollWidth:0});}
 append(...items){this.children.push(...items);}
 replaceChildren(...items){this.children=[...items];}
 addEventListener(type,heard){(this.listeners[type]??=[]).push(heard);}
 setAttribute(name,value){this.attributes[name]=String(value);}
 focus(){this.focused++;}
 scrollIntoView(){this.scrolled++;}
 set innerHTML(value){this.children=[];}
 querySelector(selector){const id=selector.match(/data-view="([^"]+)"/)[1];return this.children.find(n=>n.dataset.view===id);}
}
const context=vm.createContext({localStorage:{getItem:()=>input.language??null},
 document:{createElement:tag=>new Element(tag)},
 api:{getArtifact:async()=>({}),getReport:async()=>'# Report',
  getFeedback:async(id)=>{context.feedbackAsked.push(id); throw new Error('none');}},
 feedbackAsked:[],
 container:new Element('main'), second:new Element('main')});
for(const name of ['i18n.js','result.js']) vm.runInContext(
 fs.readFileSync(input.root+'/web/static/js/'+name,'utf8').replace(/^import .*;\r?\n/gm,'').replace(/export /g,''),context);
const out={keys:{}};
for(const [key,index,count] of input.keys) out.keys[[key,index,count].join('/')]=vm.runInContext(`tabKeyTarget(${JSON.stringify(key)},${index},${count})`,context);
out.overflow=input.overflow.map(([scrollLeft,clientWidth,scrollWidth])=>vm.runInContext(`tabsOverflow(${JSON.stringify({scrollLeft,clientWidth,scrollWidth})})`,context));
vm.runInContext(`render(container,'fixture',{artifacts:${JSON.stringify(input.artifacts)}}); render(second,'other',{artifacts:['report']})`,context);
setImmediate(async()=>{
 const strip=context.container.children.find(n=>n.className==='tabs');
 const panels=context.container.children.find(n=>n.className==='panels');
 const view=()=>({strip:{...strip.attributes,more:strip.dataset.more},
  tabs:strip.children.map(t=>({id:t.id,view:t.dataset.view,type:t.type,active:t.dataset.active,tabIndex:t.tabIndex,focused:t.focused,scrolled:t.scrolled,...t.attributes})),
  panels:panels.children.map(p=>({id:p.id,view:p.dataset.view,hidden:p.hidden,tabIndex:p.tabIndex,...p.attributes}))});
 out.first=view();
 const press=async(key)=>{let prevented=false; for(const heard of strip.listeners.keydown??[]) await heard({key,preventDefault(){prevented=true;}}); await new Promise(r=>setImmediate(r)); return prevented;};
 out.steps=[];
 for(const key of input.presses){const prevented=await press(key); const now=view(); out.steps.push({key,prevented,selected:now.tabs.find(t=>t['aria-selected']==='true')?.view,
  stops:now.tabs.filter(t=>t.tabIndex===0).map(t=>t.view),shown:now.panels.filter(p=>!p.hidden).map(p=>p.view),focused:now.tabs.map(t=>t.focused),scrolled:now.tabs.map(t=>t.scrolled)});}
 // A strip wider than its box: the hint follows where it has been scrolled to.
 Object.assign(strip,{clientWidth:300,scrollWidth:520,scrollLeft:0}); for(const heard of strip.listeners.scroll??[]) heard(); out.hints=[strip.dataset.more];
 strip.scrollLeft=110; for(const heard of strip.listeners.scroll??[]) heard(); out.hints.push(strip.dataset.more);
 strip.scrollLeft=220; for(const heard of strip.listeners.scroll??[]) heard(); out.hints.push(strip.dataset.more);
 const other=context.second.children.find(n=>n.className==='tabs');
 out.other=other.children.map(t=>t.id);
 // Who is asked whether the report helped: see test_the_feedback_question_is_not_asked_of_a_reader.
 context.feedbackAsked.length=0;
 for(const [name,extra] of input.feedback){
  context.probe=new Element('main'); context.extra={state:'completed',artifacts:['report'],...extra};
  vm.runInContext(`render(probe,${JSON.stringify(name)},extra)`,context);
 }
 await new Promise(r=>setImmediate(r));
 out.feedbackAsked=[...context.feedbackAsked];
 console.log(JSON.stringify(out));
});
'''


def _run(artifacts, presses=(), language=None):
    node = shutil.which("node")
    assert node, "Node is required for the tabs' contract"
    payload = {"root": str(ROOT), "artifacts": artifacts, "presses": list(presses), "language": language,
               "keys": [["ArrowRight", 0, 4], ["ArrowRight", 3, 4], ["ArrowLeft", 0, 4], ["ArrowLeft", 2, 4], ["Home", 2, 4],
                        ["End", 1, 4], ["Enter", 1, 4], [" ", 1, 4], ["Tab", 1, 4], ["a", 0, 4], ["ArrowRight", 0, 1], ["ArrowDown", 1, 4]],
               "overflow": [[0, 300, 300], [0, 300, 520], [110, 300, 520], [220, 300, 520], [0, 0, 0], [219.6, 300, 520]],
               "feedback": [["owner", {"viewer_can_modify": True}], ["reader", {"viewer_can_modify": False}],
                            ["no-owner-on-record", {"viewer_can_modify": None}], ["older-server", {}],
                            ["unfinished", {"viewer_can_modify": True, "state": "failed"}]]}
    done = subprocess.run([node, "-e", _SCRIPT], input=json.dumps(payload), capture_output=True, text=True,
                          encoding="utf-8", timeout=60)
    assert done.returncode == 0, done.stderr[-1500:]
    return json.loads(done.stdout)


_ALL = ["scores", "report", "sources", "grounding", "retrieval"]
_VIEWS = ["score", "report", "sources", "checks", "retrieval"]


def test_the_strip_is_a_tablist_and_each_tab_says_what_it_selects():
    seen = _run(_ALL)["first"]
    assert seen["strip"]["role"] == "tablist"
    assert seen["strip"]["aria-label"] == "Parts of this assessment"
    assert [tab["view"] for tab in seen["tabs"]] == _VIEWS
    for tab, panel in zip(seen["tabs"], seen["panels"], strict=True):
        assert (tab["role"], tab["type"]) == ("tab", "button")
        assert tab["id"] and panel["id"] and tab["id"] != panel["id"]
        assert tab["aria-controls"] == panel["id"], "a tab names the panel it shows"
        assert (panel["role"], panel["aria-labelledby"]) == ("tabpanel", tab["id"]), "a panel names its tab"
        assert panel["tabIndex"] == 0, "a panel can be reached from its tab"
    assert len({tab["id"] for tab in seen["tabs"]} | {panel["id"] for panel in seen["panels"]}) == 2 * len(_VIEWS)
    # Exactly one is selected, and it is the only tab stop in the strip.
    assert [tab["aria-selected"] for tab in seen["tabs"]] == ["true", "false", "false", "false", "false"]
    assert [tab["tabIndex"] for tab in seen["tabs"]] == [0, -1, -1, -1, -1]
    assert [tab["active"] for tab in seen["tabs"]] == ["true", "false", "false", "false", "false"], "the look follows the same fact"
    assert [panel["hidden"] for panel in seen["panels"]] == [False, True, True, True, True]


def test_the_name_of_the_strip_is_said_in_chinese_too():
    assert _run(_ALL, language="Simplified Chinese")["first"]["strip"]["aria-label"] == "这份评估的各个部分"


def test_two_assessments_on_one_page_do_not_share_ids():
    """The comparison view draws two. An id used twice would send
    aria-controls to the other assessment's panel."""
    seen = _run(["report"])
    assert seen["first"]["tabs"][0]["id"] != seen["other"][0]


def test_which_key_goes_where():
    keys = _run(_ALL)["keys"]
    assert keys == {"ArrowRight/0/4": 1, "ArrowRight/3/4": 0, "ArrowLeft/0/4": 3, "ArrowLeft/2/4": 1, "Home/2/4": 0, "End/1/4": 3,
                    "Enter/1/4": None, " /1/4": None, "Tab/1/4": None, "a/0/4": None, "ArrowRight/0/1": 0, "ArrowDown/1/4": None}


def test_the_arrow_keys_move_along_the_strip_and_select_as_they_go():
    steps = _run(_ALL, presses=["ArrowRight", "ArrowRight", "End", "ArrowRight", "ArrowLeft", "Home", "x", "Tab"])["steps"]
    assert [step["selected"] for step in steps] == ["report", "sources", "retrieval", "score", "retrieval", "score", "score", "score"]
    for step in steps:
        assert step["stops"] == [step["selected"]], "one tab stop, and it is the selected tab"
        assert step["shown"] == [step["selected"]], "the panel shown is the selected tab's"
    assert [step["prevented"] for step in steps] == [True] * 6 + [False, False], "only the keys it acts on are taken from the page"
    # Focus goes with the selection: the tab moved to is focused, once per move.
    assert steps[5]["focused"] == [2, 1, 1, 0, 2], steps[5]["focused"]
    assert steps[7]["focused"] == steps[5]["focused"], "a key it does not act on moves nothing"


def test_the_tab_the_page_opens_on_is_selected_without_moving_the_page():
    """Bringing a tab into view scrolls the page too. A stopped run on a
    phone, whose one tab sits under its reason, its run ID and its draft
    notice, opened part-way down, past its own header (seen 2026-11-19 in a
    local preview). The first tab is selected in place; a tab the reader
    moves to is still brought into view, which is what the call is for."""
    seen = _run(_ALL, presses=["ArrowRight", "End"])
    assert [tab["scrolled"] for tab in seen["first"]["tabs"]] == [0, 0, 0, 0, 0]
    assert seen["first"]["tabs"][0]["aria-selected"] == "true"
    assert seen["steps"][0]["scrolled"] == [0, 1, 0, 0, 0]
    assert seen["steps"][1]["scrolled"] == [0, 1, 0, 0, 1]


def test_the_strip_shows_which_way_it_can_still_be_scrolled():
    seen = _run(_ALL)
    assert seen["overflow"] == ["", "end", "both", "start", "", "start"]
    assert seen["hints"] == ["end", "both", "start"], "the hint follows the scrolling"
    css = (ROOT / "web" / "static" / "css" / "result.css").read_text(encoding="utf-8")
    for edge in ("end", "start", "both"):
        assert f'.tabs[data-more="{edge}"]' in css, edge
    assert "mask-image" in css


def test_the_feedback_question_is_not_asked_of_a_reader():
    """Under a finished report the page asks its owner whether it helped,
    and reads the answer already given. For someone else's run that read was
    refused with a 404 on every visit: a failed request in the console of
    everyone who opened a shared link, found by the browser smoke. A reader
    is not asked, so nothing is requested for them. Where the server cannot
    say whose the run is, or does not say, it is asked as before."""
    assert _run(["report"])["feedbackAsked"] == ["owner", "no-owner-on-record", "older-server"]


@pytest.mark.parametrize("artifacts,expected", [(["report"], ["report"]), (["scores", "report"], ["score", "report"])])
def test_a_run_with_fewer_parts_has_fewer_tabs_and_still_one_selected(artifacts, expected):
    seen = _run(artifacts, presses=["ArrowRight", "ArrowLeft"])
    assert [tab["view"] for tab in seen["first"]["tabs"]] == expected
    assert [tab["aria-selected"] for tab in seen["first"]["tabs"]].count("true") == 1
    assert seen["steps"][-1]["selected"] == expected[0]
