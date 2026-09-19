"""Execute the isolated shipped JS; these tests never make real HTTP requests."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource
from academic_agent.report_evidence_source_locator import locate_saved_source, render_locator_result


ROOT = Path(__file__).resolve().parents[1]
RUN_ID = "20260919T000000Z-" + "a" * 32


def _selection(source_id="A1"):
    return {"role": "assistant", "content": None, "tool_calls": [{
        "id": "scripted-ui", "type": "function",
        "function": {"name": "read_source", "arguments": json.dumps({"source_id": source_id})},
    }]}


@pytest.fixture(scope="module")
def browser_fixtures():
    """Real frozen serialization supplies UI cases, not handwritten success JSON."""
    prefix = '  前🙂 e\u0301\t\r\n<img src=x onerror="alert(1)"> **not markdown**\n'
    suffix = "\nEXACT_TAIL  \t"
    exact_text = prefix + "界" * (1500 - len(prefix) - len(suffix)) + suffix

    def envelope(text, *, count=1, title="<script>hostile()</script> 保存标题", reply=None, question="Find the source"):
        snapshot = ReportEvidenceSnapshot(report_ref=RUN_ID, sources=tuple(
            SnapshotSource(
                source_id=f"A{index + 1}", group="academic", title=title,
                publisher="Publisher\n<img src=x>", source_type="academic",
                url="javascript:alert(1)", doi=None, published_date="1899-01-02",
                accessed_date="2026-09-19", summary=text, origin="abstract",
            ) for index in range(count)
        ))
        result = locate_saved_source(snapshot, question, selector=lambda _: _selection() if reply is None else reply)
        return {
            "schema_version": 1, "selector_mode": "injected_callback",
            "billing_integration": "not_implemented", "result": json.loads(render_locator_result(result)),
        }

    return {
        "run_id": RUN_ID,
        "excerpt": envelope(exact_text), "missing_text": envelope(None), "empty_text": envelope(""),
        "blank_text": envelope(" \t\r\n\u0085\u001c\u3000"),
        "declined": envelope("saved", reply={"role": "assistant", "content": '{"action":"decline"}'}),
        "refused": envelope("saved", reply={"role": "assistant", "content": None, "refusal": "No"}),
        "out_of_scope": envelope("x" * 1501), "no_sources": envelope(None, count=0),
        "budget": envelope("saved", question="🙂" * 4096),
        "partial": envelope("saved", count=33, title="t" * 300),
    }


@pytest.mark.parametrize("scenario", ["domain", "malformed", "inputs", "lifecycle", "errors", "json_wait"])
def test_saved_source_lab_shipped_behavior(browser_fixtures, scenario):
    """Missing payload facts, stale delivery and double dispatch must fail closed."""
    node = shutil.which("node")
    assert node, "Node is required; the isolated browser contract cannot be skipped"
    run = subprocess.run(
        [node, str(ROOT / "tests/js/saved_source_lab_contract.mjs"), scenario],
        input=json.dumps(browser_fixtures, ensure_ascii=True),
        capture_output=True, text=True, encoding="utf-8", cwd=ROOT, timeout=40,
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert json.loads(run.stdout) == {"scenario": scenario, "passed": True}
