"""Saved artifacts -> FastAPI -> shipped renderer -> observed DOM contracts.

The VM records DOM sinks and API invocations, never pass/fail facts derived
from fixture inputs. Real HTML parsing, keyboard behavior and layout belong to
the separate strict loopback Chromium smoke.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from academic_agent.run_output import save_report, save_source_collection
from api import runs
from api.main import app


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "tests" / "js" / "source_browser_contract.mjs"
REPORT = "HEALTHY_REPORT_SENTINEL"
EXACT_TEXT = "  Leading whitespace\t\r\n前🙂 **not markdown** <img src=x onerror=alert(1)>\n" + "长🙂 text\t" * 900 + "\r\nEXACT_TAIL  \n"
EMPTY_NOTE = "The three saved source groups are explicitly empty."
NO_MATCH = "No match in searchable saved fields."


def _source(source_id: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "source_id": source_id, "title": f"Title for {source_id}",
        "url": f"https://example.test/{source_id.lower()}",
        "publisher": "Synthetic publisher", "published_date": "2026-09-18",
        "credibility_tier": "high", "evidence_summary": f"Saved text for {source_id}",
        "summary_source": "abstract",
    }
    row.update(overrides)
    return row


def _collection(*rows: object, **domains: object) -> dict[str, object]:
    return {"academic_sources": list(rows), "patent_sources": [], "market_sources": [], **domains}


def _stored_collection() -> dict[str, object]:
    # Only one A10 here. Deliberate duplicate preservation has a separate test.
    rows = [_source("A1", evidence_summary=EXACT_TEXT),
            _source("A10", evidence_summary="Body mentions A1 but is A10.")]
    rows.extend(_source(f"A{i}") for i in range(2, 55) if i != 10)
    rows[-1]["evidence_summary"] = "OVER_BUDGET_SENTINEL" + "x" * 16_385
    return _collection(
        *rows,
        patent_sources=[_source("P1", title="Literal .* TITLE NEEDLE")],
        market_sources=[_source("M1", publisher="市场资料", evidence_summary="Market excerpt needle")],
    )


def _render(payload: object, **scenario: object) -> dict:
    node = shutil.which("node")
    assert node, "Node is required; this browser boundary cannot be silently skipped"
    result = subprocess.run(
        [node, str(CONTRACT)],
        input=json.dumps({"root": str(ROOT), "payload": payload, **scenario}),
        text=True, encoding="utf-8", capture_output=True, timeout=30, check=True,
    )
    observations = json.loads(result.stdout)
    assert observations["storage_writes"] == [], "Search must not persist saved text"
    assert observations["logs"] == [], "Search must not log saved text"
    return observations


def _ids(state: dict) -> list[str]:
    return [row["id"] for row in state["rows"]]


def _assert_exact_excerpt(row: dict, expected: str) -> None:
    assert row["excerpt_tag"] == "details"
    assert row["summary_tag"] == "summary"
    assert row["excerpts"] == [expected], "Saved excerpt must reach textContent verbatim"
    assert row["excerpt_children"] == [0]


def _assert_exact_id(state: dict) -> None:
    assert _ids(state) == ["A1"], "Whole-ID search must not include A10 or body mentions"


def _assert_one_source_read(result: dict) -> None:
    assert [r for r in result["requests"] if r["artifact"] == "sources"] == [
        {"runId": "fixture", "artifact": "sources"},
    ]


def test_saved_sources_api_bytes_drive_searchable_safe_browser_dom(tmp_path, monkeypatch):
    """An artifact existing on disk did not mean its exact text reached the UI."""
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-source-browser"
    monkeypatch.setattr(runs, "DEFAULT_OUTPUT_ROOT", tmp_path)
    save_report(REPORT, run_id, tmp_path)
    run_dir = tmp_path / run_id
    (run_dir / "status.json").write_text('{"done": true, "stage": "Done"}', encoding="utf-8")
    collection = _stored_collection()
    save_source_collection(json.dumps(collection, ensure_ascii=False), run_id, tmp_path)
    saved_before = (run_dir / "validated_sources.json").read_bytes()

    client = TestClient(app)
    response = client.get(f"/api/runs/{run_id}/sources")
    report = client.get(f"/api/runs/{run_id}/report")
    assert response.status_code == report.status_code == 200
    assert response.json() == collection
    assert report.text == REPORT
    result = _render(response.json(), report=report.text, actions=[
        {"search": " A1 "}, {"search": "[a1]"}, {"search": "body mentions A1"},
        {"search": ".*"}, {"search": "TITLE NEEDLE"}, {"search": "市场资料"},
        {"search": "excerpt needle"}, {"search": "EXACT_TAIL"},
        {"search": "not anywhere"}, {"click": "clear"}, {"click": "next"},
        {"click": "prev"}, {"tab": "report"}, {"tab": "sources"},
    ])
    states = result["states"]
    expected_ids = ["A1", "A10"] + [f"A{i}" for i in range(2, 55) if i != 10] + ["P1", "M1"]
    assert _ids(states[0]) == expected_ids[:50]
    _assert_exact_excerpt(states[0]["rows"][0], collection["academic_sources"][0]["evidence_summary"])
    assert states[0]["rows"][0]["link"] == {
        "tag": "a", "href": "https://example.test/a1", "target": "_blank", "rel": "noopener noreferrer",
    }
    for index in (1, 2):
        _assert_exact_id(states[index])
    for index, expected in ((3, ["A10"]), (4, ["P1"]), (5, ["P1"]), (6, ["M1"]), (7, ["M1"]), (8, ["A1"])):
        assert _ids(states[index]) == expected
    assert states[9]["notes"] == [NO_MATCH]
    assert _ids(states[10]) == expected_ids[:50]
    assert states[10]["search"]["focused"] and states[10]["clear"]["disabled"]
    assert _ids(states[11]) == expected_ids[50:]
    assert states[11]["next"]["disabled"] and not states[11]["prev"]["disabled"]
    assert _ids(states[12]) == expected_ids[:50] and states[12]["prev"]["disabled"]
    assert states[13]["active_tab"] == "report" and REPORT in states[13]["report_html"]
    assert _ids(states[14]) == expected_ids[:50]
    for state in states:
        assert state["warnings"], "Partial-search warning must survive filtering and paging"
        assert state["source_html_writes"] == state["forbidden_tags"] == []
        assert REPORT in state["report_html"]
    _assert_one_source_read(result)
    assert (run_dir / "validated_sources.json").read_bytes() == saved_before


def test_literal_search_keeps_field_boundaries_and_deliberate_duplicates():
    """Concatenating fields invented a match; de-duplication would lose saved rows."""
    result = _render(_collection(
        _source("A1", title="alpha", publisher="beta", evidence_summary="gamma"),
        _source("A1", title="Second saved record", evidence_summary="duplicate retained"),
        _source("A10", evidence_summary="A1 appears only in this body"),
    ), actions=[{"search": "alpha beta"}, {"search": "[A1]"}, {"search": "appears only"}, {"click": "clear"}])
    states = result["states"]
    assert _ids(states[0]) == _ids(states[4]) == ["A1", "A1", "A10"]
    assert states[1]["notes"] == [NO_MATCH] and not states[1]["warnings"]
    assert _ids(states[2]) == ["A1", "A1"]
    assert [r["title"] for r in states[2]["rows"]] == ["alpha", "Second saved record"]
    assert _ids(states[3]) == ["A10"]
    _assert_one_source_read(result)


@pytest.mark.parametrize("payload", [None, [], {"academic_sources": "bad"}])
def test_source_root_faults_are_observed_not_invented_from_inputs(payload):
    """Malformed registry roots must show partial scope, not a clean empty list."""
    result = _render(payload, language="Simplified Chinese", actions=[{"tab": "report"}])
    state = result["states"][0]
    assert state["rows"] == []
    assert state["notes"] == ["在当前不完整的搜索范围内，没有可浏览的已保存记录。"]
    assert "搜索范围不完整" in state["warnings"][0]
    assert result["states"][1]["active_tab"] == "report"
    assert REPORT in result["states"][1]["report_html"]
    _assert_one_source_read(result)


def test_partial_domains_rows_and_metadata_preserve_healthy_neighbors():
    """One damaged group, row or field must neither hide neighbors nor claim completeness."""
    result = _render(_collection(
        None, "bad row", [], _source("A1"), _source("A2", title={"not": "text"}, evidence_summary=["invalid"]),
        patent_sources=None,
        market_sources=[_source("M1", publisher=4, credibility_tier=["high"])],
    ), actions=[{"search": "not anywhere"}, {"click": "clear"}])
    state = result["states"][0]
    assert _ids(state) == ["A1", "A2", "M1"]
    _assert_exact_excerpt(state["rows"][0], "Saved text for A1")
    assert state["rows"][1]["title"] == "Saved title unavailable"
    assert state["rows"][1]["excerpts"] == []
    assert state["rows"][1]["faults"] and state["rows"][2]["faults"]
    assert "[object Object]" not in json.dumps(state)
    assert result["states"][1]["notes"] == [NO_MATCH]
    assert all(s["warnings"] for s in result["states"])


def test_missing_null_blank_invalid_excerpts_and_recorded_labels_remain_distinct():
    """Missing evidence is not blank text, malformed text, or a verified origin."""
    missing = _source("A1")
    missing.pop("evidence_summary")
    result = _render(_collection(
        missing, _source("A2", evidence_summary=None), _source("A3", evidence_summary=""),
        _source("A4", evidence_summary=" \t\r\n "),
        _source("A5", evidence_summary=42),
        _source("A6", summary_source="<img src=x>", evidence_summary=EXACT_TEXT),
    ))
    rows = result["states"][0]["rows"]
    assert rows[0]["excerpt_state"] == rows[1]["excerpt_state"] == [
        "No saved excerpt is recorded (field missing or null).",
    ]
    assert rows[0]["excerpts"] == rows[1]["excerpts"] == []
    assert rows[2]["excerpt_state"] == rows[3]["excerpt_state"] == [
        "The saved excerpt is empty or whitespace-only; any saved whitespace is preserved.",
    ]
    _assert_exact_excerpt(rows[2], "")
    _assert_exact_excerpt(rows[3], " \t\r\n ")
    assert rows[4]["excerpt_state"] == ["The saved excerpt has an invalid type and cannot be displayed or searched."]
    assert rows[4]["excerpts"] == []
    assert rows[5]["summary_source"] == ["Unrecognized recorded summary_source label: <img src=x>"]
    _assert_exact_excerpt(rows[5], EXACT_TEXT)
    assert result["states"][0]["source_html_writes"] == result["states"][0]["forbidden_tags"] == []


def test_explicit_empty_arrays_and_no_match_are_distinct_from_missing_groups():
    """No rows inspected must not masquerade as a complete empty registry."""
    empty = _render(_collection(), actions=[{"search": "anything"}])["states"]
    partial = _render({"academic_sources": [], "market_sources": []})["states"][0]
    assert empty[0]["notes"] == [EMPTY_NOTE] and empty[0]["warnings"] == []
    assert empty[1]["notes"] == [NO_MATCH] and empty[1]["warnings"] == []
    assert partial["warnings"] and partial["notes"] != [EMPTY_NOTE]
    assert partial["notes"] != [NO_MATCH]
    assert partial["rows"] == []


def test_no_sources_artifact_never_requests_endpoint_and_preserves_report():
    """A conditional missing tab must disclose non-read without issuing a GET."""
    result = _render(None, artifacts=["report"])
    state = result["states"][0]
    assert result["requests"] == [{"runId": "fixture", "artifact": "report"}]
    assert state["missing"] == ["No saved sources artifact is listed for this run; no source read was requested."]
    assert state["search"] is None and state["active_tab"] == "report"
    assert REPORT in state["report_html"]


@pytest.mark.parametrize("language,expected", [
    ("English", ["artifact is unavailable (409)", "resource is unavailable (404)", "could not be read or parsed"]),
    ("Simplified Chinese", ["文件不可用（409）", "资源不可用（404）", "无法读取或解析"]),
])
def test_source_read_errors_localized_without_echoing_payload_keep_report(language, expected):
    """Server/parser messages can contain private bytes and must not reach the panel."""
    for status, message in zip((409, 404, None), expected, strict=True):
        result = _render(None, language=language, failure={
            "status": status, "message": "RAW_PRIVATE_PAYLOAD <img src=x> secret fixture",
        }, actions=[{"tab": "report"}])
        state = result["states"][0]
        assert len(state["errors"]) == 1 and message in state["errors"][0]
        assert state["rows"] == [] and state["search"] is None
        assert "RAW_PRIVATE_PAYLOAD" not in json.dumps(result)
        assert result["states"][1]["active_tab"] == "report"
        assert REPORT in result["states"][1]["report_html"]
        _assert_one_source_read(result)


def test_absolute_http_links_positive_control_and_unsafe_links_stay_inert():
    """A VM without URL made rejecting every link look like successful safety."""
    urls = [
        "https://example.test/paper?q=1", "http://example.test/paper",
        "javascript:alert(1)", "data:text/html,<img src=x>", "/relative", "//example.test/path",
        "https://user:password@example.test/paper", "https://example.test/\ncontrol",
        "https://example.test/\u007fcontrol",
    ]
    malicious = '<img src=x onerror="alert(1)"><script>bad()</script>'
    result = _render(_collection(*[
        _source(f"A{i}", url=url, title=malicious, publisher=malicious, evidence_summary=malicious)
        for i, url in enumerate(urls, 1)
    ]))
    state = result["states"][0]
    for index, row in enumerate(state["rows"]):
        assert row["title"] == malicious
        _assert_exact_excerpt(row, malicious)
        if index < 2:
            assert row["link"] == {"tag": "a", "href": urls[index], "target": "_blank", "rel": "noopener noreferrer"}
        else:
            assert row["link"]["tag"] == "span" and row["link"]["href"] is None
            assert row["faults"]
    assert state["source_html_writes"] == state["forbidden_tags"] == []


def test_row_budget_page_size_and_search_beyond_visible_page():
    """Search must include admitted off-page rows but never inspect the unbounded tail."""
    result = _render(_collection(
        *[_source(f"A{i}") for i in range(1, 1002)], patent_sources=[_source("P1")],
    ), actions=[*({"click": "next"} for _ in range(19)),
                {"search": "A1000"}, {"search": "A1001"}, {"search": "P1"}])
    pages = result["states"][:20]
    assert [row["id"] for state in pages for row in state["rows"]] == [f"A{i}" for i in range(1, 1001)]
    assert all(len(s["rows"]) == 50 and s["warnings"] for s in pages)
    assert pages[-1]["next"]["disabled"]
    assert _ids(result["states"][20]) == ["A1000"]
    assert all(s["notes"] == [NO_MATCH] for s in result["states"][21:])
    _assert_one_source_read(result)
    # The limit counts inspected malformed rows too, not only renderable ones.
    malformed = _render(_collection(*([None] * 1000), _source("A1")))["states"][0]
    assert malformed["rows"] == [] and malformed["warnings"]


def test_string_budget_counts_utf16_and_omits_whole_field_not_tail():
    """An over-budget excerpt must not become a plausible truncated saved quote."""
    exact = "🙂" * 8190 + "TAIL"  # Exactly 16,384 UTF-16 code units.
    result = _render(_collection(
        _source("A1", evidence_summary=exact),
        _source("A2", evidence_summary=exact + "Z"),
        _source("A3", title="x" * 16_385, evidence_summary="HEALTHY_NEIGHBOR"),
    ), actions=[{"search": "TAIL"}, {"search": "HEALTHY_NEIGHBOR"}])
    rows = result["states"][0]["rows"]
    _assert_exact_excerpt(rows[0], exact)
    assert rows[1]["excerpts"] == [] and "outside the display budget" in rows[1]["excerpt_state"][0]
    assert rows[2]["title"] == "Saved title unavailable"
    assert _ids(result["states"][1]) == ["A1"]
    assert _ids(result["states"][2]) == ["A3"]
    assert all(s["warnings"] for s in result["states"])


def test_total_budget_boundary_does_not_search_or_display_rejected_text():
    """Per-field limits alone permit unbounded aggregate copying and searching."""
    rows = [{"source_id": f"A{i}", "title": "t", "evidence_summary": "x" * 16_384} for i in range(1, 128)]
    used = sum(len(value) for row in rows for value in row.values())
    remaining = 2 * 1024 * 1024 - used - len("A128") - len("t")
    boundary_text = "y" * (remaining - len("AGGREGATE_TAIL")) + "AGGREGATE_TAIL"
    rows.extend([
        {"source_id": "A128", "title": "t", "evidence_summary": boundary_text},
        {"source_id": "A129", "title": "t", "evidence_summary": "AFTER_BUDGET"},
    ])
    result = _render(_collection(*rows), actions=[
        {"search": "A127"}, {"search": "AGGREGATE_TAIL"}, {"search": "AFTER_BUDGET"},
    ])
    _assert_exact_excerpt(result["states"][1]["rows"][0], "x" * 16_384)
    assert _ids(result["states"][2]) == ["A128"]
    _assert_exact_excerpt(result["states"][2]["rows"][0], boundary_text)
    assert result["states"][3]["notes"] == [NO_MATCH]
    assert all(s["warnings"] for s in result["states"])
    _assert_one_source_read(result)


def test_late_old_sources_response_cannot_pollute_new_render_or_selection():
    """Two renders sharing one container must not share pending-read destinations."""
    result = _render(_collection(_source("M1", evidence_summary="NEW_RUN_ONLY")),
                     stale={"payload": _collection(_source("A1", evidence_summary="OLD_RUN_ONLY"))},
                     actions=[{"search": "OLD_RUN_ONLY"}, {"click": "clear"}, {"tab": "report"}])
    states = result["states"]
    assert states[0]["rows"] == []  # The old sources promise is actually held.
    assert _ids(states[1]) == _ids(states[2]) == ["M1"]
    assert states[1]["rows"] == states[2]["rows"]
    assert states[3]["notes"] == [NO_MATCH]
    assert _ids(states[4]) == ["M1"]
    assert states[5]["active_tab"] == "report" and REPORT in states[5]["report_html"]
    assert [r for r in result["requests"] if r["artifact"] == "sources"] == [
        {"runId": "old", "artifact": "sources"}, {"runId": "new", "artifact": "sources"},
    ]


@pytest.mark.parametrize("mutation", ["omit_excerpt", "truncate_text", "id_prefix"])
def test_contract_assertions_kill_in_memory_production_mutations(mutation):
    """The same positive assertions must go red when the historical defect returns."""
    payload = _collection(_source("A1", evidence_summary=EXACT_TEXT), _source("A10"))
    healthy = _render(payload, actions=[{"search": "A1"}])
    mutant = _render(payload, mutation=mutation, actions=[{"search": "A1"}])
    if mutation == "id_prefix":
        _assert_exact_id(healthy["states"][1])
        with pytest.raises(AssertionError, match="Whole-ID search"):
            _assert_exact_id(mutant["states"][1])
    else:
        _assert_exact_excerpt(healthy["states"][0]["rows"][0], EXACT_TEXT)
        with pytest.raises(AssertionError, match="Saved excerpt"):
            _assert_exact_excerpt(mutant["states"][0]["rows"][0], EXACT_TEXT)
