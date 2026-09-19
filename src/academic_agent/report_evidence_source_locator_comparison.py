"""Fixed offline observation of public bibliography title search.

This module projects only the frozen public report's reference IDs and titles
into the shipped Sources renderer.  It does not read a source registry, call a
provider, accept a user path/query, or change any runtime route.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


METHOD_ID = "report_evidence_source_locator_comparison_v1"
ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/report_evidence_source_locator_comparison.json"
REPORT = ROOT / "examples/solid-state-batteries-ev.md"
CONTRACT = ROOT / "tests/js/source_browser_contract.mjs"
FIXTURE_SHA256 = "74bc2a26041a9365802d635e7e348387a47ce48404718793a2e5ce2f78c0e867"
REPORT_SHA256_LF = "8fac15788439fecf6a6fbdcd32e4aea069ad8cfbb721aa54bd3abd8a8ee984cd"
ASSETS = (
    ("tests/js/source_browser_contract.mjs", "54cbb9a989ce6681ee0fca092441371c44617abdc76a8837d04d92647b928dca"),
    ("web/static/js/result.js", "575b6ba17de6660575369f08d271889e788570059d1823cdfe28f13f773b4650"),
    ("web/static/js/i18n.js", "1010e034767fee6829bcad0bd709cbe7784e7c024db62108e64c482790de958d"),
)


class ComparisonUnavailable(RuntimeError):
    """A safe fixed reason, never an observer diagnostic."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _lf_sha256(raw: bytes) -> str:
    return _sha256(raw.replace(b"\r\n", b"\n"))


def _read(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError:
        raise ComparisonUnavailable("asset_unavailable") from None


def _load_fixture() -> dict[str, Any]:
    raw = _read(FIXTURE)
    if _sha256(raw) != FIXTURE_SHA256:
        raise ComparisonUnavailable("fixture_identity_mismatch")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ComparisonUnavailable("fixture_unavailable") from None
    required = {
        "schema_version", "cohort_id", "source_report", "source_report_sha256_lf",
        "catalog_origin", "saved_text_status", "keyword_origin", "reference_status",
        "observer_assets", "catalog", "cases",
    }
    if type(data) is not dict or set(data) != required:
        raise ComparisonUnavailable("fixture_contract_mismatch")
    if (data["schema_version"] != 1
            or data["cohort_id"] != "public_bibliography_title_lookup_development_v1"
            or data["source_report"] != "examples/solid-state-batteries-ev.md"
            or data["source_report_sha256_lf"] != REPORT_SHA256_LF
            or data["catalog_origin"] != "public_report_reference_title_projection_not_original_registry"
            or data["saved_text_status"] != "unavailable_in_public_input"
            or type(data["catalog"]) is not list or len(data["catalog"]) != 20
            or type(data["cases"]) is not list or len(data["cases"]) != 6):
        raise ComparisonUnavailable("fixture_contract_mismatch")
    return data


def _asset_hashes() -> dict[str, str]:
    hashes = {path: _lf_sha256(_read(ROOT / path)) for path, _ in ASSETS}
    if any(hashes[path] != expected for path, expected in ASSETS):
        raise ComparisonUnavailable("observer_asset_drift")
    return hashes


def prepare_manifest() -> dict[str, Any]:
    """Bind the report/catalog/assets before starting the one fixed observer."""
    fixture = _load_fixture()
    report = _read(REPORT)
    if _lf_sha256(report) != REPORT_SHA256_LF:
        raise ComparisonUnavailable("report_identity_mismatch")
    catalog = fixture["catalog"]
    expected_ids = tuple([f"A{i}" for i in range(1, 5)] + [f"P{i}" for i in range(1, 9)] + [f"M{i}" for i in range(1, 9)])
    if tuple(row.get("source_id") for row in catalog) != expected_ids:
        raise ComparisonUnavailable("catalog_identity_mismatch")
    try:
        report_text = report.decode("utf-8")
        for row in catalog:
            if set(row) != {"source_id", "title"} or not isinstance(row["title"], str):
                raise ValueError
            if f"[{row['source_id']}] {row['title']}." not in report_text:
                raise ValueError
        cases = fixture["cases"]
        for case in cases:
            if (set(case) != {"case_id", "question", "keyword_query", "acceptable_source_ids", "reference_kind"}
                    or not isinstance(case["question"], str) or not isinstance(case["keyword_query"], str)
                    or not isinstance(case["acceptable_source_ids"], list)):
                raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ComparisonUnavailable("catalog_projection_mismatch") from None
    assets = _asset_hashes()
    if fixture["observer_assets"] != [{"path": path, "sha256_lf": digest} for path, digest in ASSETS]:
        raise ComparisonUnavailable("fixture_asset_mismatch")
    return {"fixture": fixture, "catalog": catalog, "cases": cases, "asset_hashes_before": assets}


def _payload(catalog: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    return {
        "academic_sources": catalog[:4], "patent_sources": catalog[4:12], "market_sources": catalog[12:],
    }


def _run_node(manifest: dict[str, Any]) -> dict[str, Any]:
    node = shutil.which("node")
    if not node:
        raise ComparisonUnavailable("node_unavailable")
    actions = [action for case in manifest["cases"] for action in (
        {"search": case["question"]}, {"search": case["keyword_query"]},
    )]
    input_value = {"root": str(ROOT), "payload": _payload(manifest["catalog"]), "report": "", "actions": actions}
    try:
        completed = subprocess.run(
            [node, str(CONTRACT)], input=json.dumps(input_value, ensure_ascii=False), text=True,
            encoding="utf-8", capture_output=True, timeout=30, check=True,
        )
        result = json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, UnicodeError, json.JSONDecodeError):
        raise ComparisonUnavailable("observer_unavailable") from None
    if type(result) is not dict:
        raise ComparisonUnavailable("observer_parse_mismatch")
    return result


def _ids(state: Any) -> list[str] | None:
    if type(state) is not dict:
        return None
    rows = state.get("rows")
    if type(rows) is not list:
        return None
    ids = [row.get("id") if type(row) is dict else None for row in rows]
    return ids if all(type(value) is str for value in ids) else None


def _title_only_row(source: dict[str, str]) -> dict[str, Any]:
    # These are literal output fields of the hash-bound English observer, not
    # invented saved text or a Python implementation of the JS search matcher.
    return {
        "id": source["source_id"], "title": source["title"],
        "link": {"tag": "span", "href": None, "rel": None, "target": None},
        "excerpt_tag": "details", "summary_tag": "summary", "excerpts": [],
        "excerpt_children": [],
        "excerpt_state": ["No saved excerpt is recorded (field missing or null)."],
        "summary_source": ["No readable summary_source label is recorded."],
        "faults": [], "meta": [""],
    }


def _validate_state(
    state: Any, query: str, expected_rows: dict[str, dict[str, Any]], reason: str,
) -> list[str]:
    ids = _ids(state)
    if (ids is None or len(ids) != len(set(ids))
            or any(source_id not in expected_rows for source_id in ids)):
        raise ComparisonUnavailable(reason)
    # Validate membership before indexing; compare order and every exposed row
    # field, so hidden IDs, excerpts, links or metadata cannot acquire evidence.
    if (ids != [source_id for source_id in expected_rows if source_id in ids]
            or state["rows"] != [expected_rows[source_id] for source_id in ids]):
        raise ComparisonUnavailable(reason)
    for name, disabled, text, value in (
        ("search", False, "", query), ("clear", not query, "Clear search", ""),
        ("prev", True, "Previous 50", ""), ("next", True, "Next 50", ""),
    ):
        control = state.get(name)
        if (type(control) is not dict or type(control.get("disabled")) is not bool
                or type(control.get("focused")) is not bool
                or control != {"disabled": disabled, "text": text, "value": value,
                               "focused": False, "attributes": {}}):
            raise ComparisonUnavailable(reason)
    count = len(ids)
    # All twenty title rows fit one page. The shipped status must corroborate
    # the delivered rows; an empty rows array alone is not a zero-match fact.
    expected = {
        "rows": state["rows"],
        "status": [f"Matching saved records: {count} / {len(expected_rows)} locally browsable records. "
                   f"Showing {1 if count else 0}–{count}."],
        "warnings": [], "errors": [], "missing": [],
        "notes": [] if count else ["No match in searchable saved fields."],
        "disclosure": ["Browse saved source text only. It may be a cleaned or truncated abstract, "
                       "search snippet, or title fallback—not paper full text or semantic verification. "
                       "summary_source is a recorded label, not proof of origin or completeness."],
        "source_html_writes": [], "forbidden_tags": [],
        "report_html": '<article class="prose"></article>', "active_tab": "sources",
        "requests": [{"runId": "fixture", "artifact": "report"}, {"runId": "fixture", "artifact": "sources"}],
        **{name: state[name] for name in ("search", "clear", "prev", "next")},
    }
    if state != expected:
        raise ComparisonUnavailable(reason)
    return ids


def _validate_observation(observation: dict[str, Any], manifest: dict[str, Any]) -> tuple[list[list[str]], list[list[str]]]:
    if type(observation) is not dict:
        raise ComparisonUnavailable("observer_state_mismatch")
    states = observation.get("states")
    if type(states) is not list or len(states) != 13:
        raise ComparisonUnavailable("observer_state_mismatch")
    if observation.get("storage_writes") != [] or observation.get("logs") != []:
        raise ComparisonUnavailable("observer_side_effect_mismatch")
    requests = observation.get("requests")
    if requests != [{"runId": "fixture", "artifact": "report"}, {"runId": "fixture", "artifact": "sources"}]:
        raise ComparisonUnavailable("observer_request_mismatch")
    expected_ids = [row["source_id"] for row in manifest["catalog"]]
    expected_rows = {row["source_id"]: _title_only_row(row) for row in manifest["catalog"]}
    initial_ids = _validate_state(states[0], "", expected_rows, "initial_delivery_incomplete")
    if initial_ids != expected_ids:
        raise ComparisonUnavailable("initial_delivery_incomplete")
    diagnostic_hits: list[list[str]] = []
    keyword_hits: list[list[str]] = []
    for index, case in enumerate(manifest["cases"], 1):
        for condition, query in (("diagnostic", case["question"]), ("keyword", case["keyword_query"])):
            state = states[index * 2 - (1 if condition == "diagnostic" else 0)]
            ids = _validate_state(state, query, expected_rows, "filter_observation_incomplete")
            if condition == "keyword":
                keyword_hits.append(ids)
            else:
                diagnostic_hits.append(ids)
    return diagnostic_hits, keyword_hits


def _grade(cases: list[dict[str, Any]], hit_lists: list[list[str]] | None) -> list[dict[str, Any]]:
    grades: list[dict[str, Any]] = []
    for index, case in enumerate(cases):
        reference = case["acceptable_source_ids"]
        hits = None if hit_lists is None else hit_lists[index]
        intersection = None if hits is None else [value for value in hits if value in reference]
        grades.append({
            "case_id": case["case_id"], "acceptable_source_ids": reference,
            "observed_ids": hits, "candidate_count": None if hits is None else len(hits),
            "acceptable_intersection": intersection,
            "reference_coverage": None if not reference or hits is None else len(intersection) / len(reference),
            "unique_acceptable_hit": None if hits is None else len(hits) == 1 and len(intersection) == 1,
            "no_fit_control_match": None if hits is None or reference else not hits,
        })
    return grades


def run_fixed_comparison() -> dict[str, Any]:
    """Run the fixed public baseline once; all observation failure remains visible."""
    manifest = None
    try:
        manifest = prepare_manifest()
        observation = _run_node(manifest)
        diagnostic_hits, keyword_hits = _validate_observation(observation, manifest)
        after = _asset_hashes()
        if after != manifest["asset_hashes_before"]:
            raise ComparisonUnavailable("observer_asset_drift")
        state, reason = "available", None
    except ComparisonUnavailable as exc:
        state, reason = "unavailable", exc.args[0]
        diagnostic_hits = keyword_hits = None
        after = None
    cases = manifest["cases"] if manifest else []
    observed = 6 if state == "available" else 0
    return {
        "method_id": METHOD_ID, "state": state, "reason": reason, "planned_cases": 6,
        "positive_reference_cases": 5, "no_fit_cases": 1, "paired_observations_planned": 12,
        "observed_cases": observed, "unavailable_cases": 6 - observed,
        "paired_observations_observed": 2 * observed,
        "condition_counts": {
            condition: {"planned_cases": 6, "observed_cases": observed, "unavailable_cases": 6 - observed,
                        "positive_reference_cases": 5, "no_fit_cases": 1,
                        "evaluable_positive_cases": 5 if observed else 0,
                        "evaluable_no_fit_cases": 1 if observed else 0}
            for condition in ("question_literal_diagnostic", "prepared_keyword_assisted")
        },
        "conditions": {
            "question_literal_diagnostic": _grade(cases, diagnostic_hits),
            "prepared_keyword_assisted": _grade(cases, keyword_hits),
        },
        "input_provenance": None if manifest is None else {
            "fixture_sha256": FIXTURE_SHA256,
            **{key: manifest["fixture"][key] for key in (
                "source_report", "source_report_sha256_lf", "catalog_origin", "saved_text_status",
                "keyword_origin", "reference_status",
            )},
        },
        "asset_hashes_before": manifest["asset_hashes_before"] if manifest else None, "asset_hashes_after": after,
        "model_lane": {"state": "not_run", "evaluated_cases": 0, "quality": None, "benefit": None},
    }


def main() -> None:
    if len(sys.argv) != 1:
        raise SystemExit(2)
    print(json.dumps(run_fixed_comparison(), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
