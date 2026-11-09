"""A damaged optional log must not hide a completed run or duplicate events."""

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api import runs
from api.main import app

ROOT = Path(__file__).resolve().parents[1]
RUN = "20260908T010203Z-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
GOOD = b'{"type":"finish","agent_idx":0}\n'


@pytest.fixture
def run_log(tmp_path, monkeypatch):
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    directory = tmp_path / RUN
    directory.mkdir()
    (directory / "status.json").write_text('{"done":true,"stage":"Done"}', encoding="utf-8")
    (directory / "commercialization_report.md").write_text("# Preserved report", encoding="utf-8")
    return directory / "steps.jsonl"


def progress(client, since=0):
    response = client.get(f"/api/runs/{RUN}/progress", params={"since": since})
    assert response.status_code == 200
    assert response.json()["state"] == "completed"
    assert response.json()["done"] is True
    assert client.get(f"/api/runs/{RUN}").status_code == 200
    assert client.get(f"/api/runs/{RUN}/report").text == "# Preserved report"
    return response.json()


@pytest.mark.parametrize("bad", [b"null", b"[]", b"{}", b"false", b"", b"not-json", b"\xff",
    b'{"type":[]}', b'{"type":"finish","agent_idx":{}}',
    b'{"type":"finish","ts":NaN}', b'{"type":"finish","thought":null}'])
def test_bad_step_is_local_and_cursor_skips_its_physical_line(run_log, bad):
    """The old reader either raised HTTP 500 or replayed the healthy neighbour."""
    raw = GOOD + bad + b"\n" + GOOD.replace(b":0", b":1")
    run_log.write_bytes(raw)
    client = TestClient(app)
    body = progress(client)
    assert [s["agent_idx"] for s in body["steps"]] == [0, 1]
    assert body["steps_read_state"] == "partial"
    assert body["steps_rejected"] == 1
    assert body["steps_next_cursor"] == 3
    later = progress(client, body["steps_next_cursor"])
    assert later["steps"] == []
    assert later["steps_rejected"] == 1  # Loss remains visible after the cursor passed it.
    assert run_log.read_bytes() == raw


@pytest.mark.parametrize("tail", [b'{"type":"fi', b'{"type":"finish"}', b'{"type":"action","thought":"\xe4'])
def test_uncommitted_tail_is_delivered_once_after_newline(run_log, tail):
    """Even parseable JSON without the writer's newline is not a committed row."""
    run_log.write_bytes(GOOD + tail)
    client = TestClient(app)
    first = progress(client)
    assert len(first["steps"]) == 1
    assert first["steps_next_cursor"] == 1
    assert first["steps_read_state"] == "partial"
    assert first["steps_rejected"] == 0
    run_log.write_bytes(GOOD + GOOD.replace(b":0", b":1"))
    later = progress(client, first["steps_next_cursor"])
    assert [s["agent_idx"] for s in later["steps"]] == [1]
    assert later["steps_read_state"] == "readable"
    assert progress(client, later["steps_next_cursor"])["steps"] == []


def test_absent_empty_and_permission_denied_logs_are_distinct(run_log):
    """A failed read cannot impersonate an empty successful observation."""
    client = TestClient(app)
    assert progress(client)["steps_read_state"] == "absent"
    run_log.write_bytes(b"")
    assert progress(client)["steps_read_state"] == "readable"
    original = Path.open

    def fail_log(path, *args, **kwargs):
        if path == run_log:
            raise PermissionError("private diagnostic path")
        return original(path, *args, **kwargs)

    with patch.object(Path, "open", fail_log):
        body = progress(client, 4)
    assert body["steps_read_state"] == "unavailable"
    assert body["steps_next_cursor"] == 4
    assert "private diagnostic" not in json.dumps(body)


def test_shipped_follower_uses_server_cursor_and_still_finishes(run_log):
    """Test real HTTP page values through the actual JS follower, not a counter helper."""
    run_log.write_bytes(GOOD + b"null\n" + GOOD)
    client = TestClient(app)
    first = progress(client)
    second = progress(client, first["steps_next_cursor"])
    node = shutil.which("node")
    assert node, "Node is required for client seam tests"
    script = r'''
const fs=require('node:fs'), vm=require('node:vm'), assert=require('node:assert/strict');
const input=JSON.parse(fs.readFileSync(0,'utf8')), cursors=[], timers=[];
let done=0, updates=0;
const ctx=vm.createContext({api:{getProgress:async(id,cursor)=>{
  cursors.push(cursor);
  return cursors.length===1 ? {...input.first,state:'running'} : input.second;
}}, t:k=>k, setTimeout:fn=>timers.push(fn), clearTimeout:()=>{}, done:()=>done++, update:()=>updates++});
vm.runInContext(fs.readFileSync(input.root+'/web/static/js/run.js','utf8')
  .replace(/^import .*;\r?\n/gm,'').replace(/export /g,''),ctx);
vm.runInContext("follow('fixture',{onUpdate:update,onDone:done})",ctx);
setImmediate(async()=>{
  assert.equal(timers.length,1); await timers.shift()();
  assert.deepEqual(cursors,[0,input.first.steps_next_cursor]);
  assert.equal(done,1); assert.equal(updates,2); assert.equal(timers.length,0);
  console.log('cursor and completion reached client');
});
'''
    result = subprocess.run([node, "-e", script], input=json.dumps({"root": str(ROOT), "first": first, "second": second}),
                            text=True, encoding="utf-8", capture_output=True, timeout=30, check=True)
    assert "completion reached client" in result.stdout


def test_provider_attempt_rows_reach_the_client_with_their_timing(run_log):
    """A timed-out provider attempt is billed but absent from usage, which counts
    successful requests only. The worker now logs every attempt as a step; the
    progress endpoint must deliver the attempt number, outcome and duration
    rather than strip them to the older action/finish shape."""
    run_log.write_bytes(
        GOOD
        + b'{"type":"llm_attempt","agent_idx":3,"ts":1762600000.5,"call":1,"attempt":1,'
        b'"outcome":"timeout","duration_seconds":150.2,"retry":true}\n'
        + b'{"type":"llm_attempt","agent_idx":3,"ts":1762600155.0,"call":1,"attempt":2,'
        b'"outcome":"returned","duration_seconds":112.4,"retry":false}\n'
    )
    client = TestClient(app)

    body = progress(client)

    assert body["steps_rejected"] == 0
    attempts = [s for s in body["steps"] if s["type"] == "llm_attempt"]
    assert [(s["attempt"], s["outcome"], s["duration_seconds"], s["retry"]) for s in attempts] == [
        (1, "timeout", 150.2, True),
        (2, "returned", 112.4, False),
    ]
    assert attempts[0]["ts"] == 1762600000.5
    assert [s["call"] for s in attempts] == [1, 1]
