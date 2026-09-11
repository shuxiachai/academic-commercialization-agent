"""Attribution preparation must not manufacture evaluated market estimates."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from academic_agent import market_estimate_samples as samples


FIXTURE = Path(__file__).parent / "fixtures" / "market_estimate_controls_v1.json"
BUNDLE = json.loads(FIXTURE.read_text(encoding="utf-8"))


def cli(flag, source, output):
    return subprocess.run([sys.executable, "-m", "academic_agent.market_estimate_samples",
                           flag, str(source), "--output", str(output)],
                          capture_output=True, text=True, timeout=20, check=False)


def control_file(tmp_path, value):
    path = tmp_path / "inputs" / "controls.json"
    path.parent.mkdir()
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def unit(root, name="unit", *, mode="live", topic="batteries", bad=False):
    folder = root / name
    folder.mkdir(parents=True)
    report = {"topic": topic, "sources": [
        {"source_id": "M1", "url": "https://one.example/report", "evidence_summary":
         "The global battery market is USD 2 billion in 2025; projected USD 20 billion in 2030."},
        {"source_id": "M2", "url": "https://two.example/report", "evidence_summary":
         "A company raised USD 10 million. Its market opportunity has not been measured."},
    ]}
    if bad:
        report["sources"].append({"source_id": "M1"})
    (folder / "market_evidence.json").write_text(json.dumps(report), encoding="utf-8")
    (folder / "meta.json").write_text(json.dumps({"evidence_mode": mode}), encoding="utf-8")
    return folder


@pytest.mark.parametrize("case", BUNDLE["cases"], ids=lambda row: row["id"])
def test_frozen_engineering_case_compares_full_result_not_just_an_eligible_flag(case):
    """Same-year forecast/estimate, price basis and source family all matter."""
    assert samples.compare_control(case["left"], case["right"]) == case["expected"]


def test_control_cli_exports_the_same_summary_and_all_contract_outcomes(tmp_path):
    before = FIXTURE.read_bytes()
    result = cli("--controls", FIXTURE, tmp_path / "result")
    assert result.returncode == 0, result.stderr
    payload = json.loads((tmp_path / "result" / "samples.json").read_text(encoding="utf-8"))
    assert json.loads(result.stdout) == payload["summary"]
    # Assert the whole function-to-CLI projection, not one hard-coded field.
    # A future diagnostic key must not be computed and silently dropped.
    direct = samples.evaluate_controls(BUNDLE)
    assert {key: payload[key] for key in direct} == direct
    assert payload["summary"] == {"cases": 16, "checked": 16, "unavailable": 0, "contract_matches": 16,
                                  "verdicts": {"comparable_no_spread": 3, "comparable_spread": 1,
                                               "incomparable": 9, "insufficient_information": 3}}
    assert [row["actual"] for row in payload["cases"]] == [row["expected"] for row in BUNDLE["cases"]]
    assert payload["independent_accuracy"] == "not_measured"
    assert payload["production_effect"] == "none"
    assert payload["input_sha256"] == hashlib.sha256(before).hexdigest()
    assert payload["implementation_sha256"] == hashlib.sha256(Path(samples.__file__).read_bytes()).hexdigest()
    assert FIXTURE.read_bytes() == before


@pytest.mark.parametrize("defect", ["amount_anchor", "currency", "year_anchor", "duplicate_clause",
                                   "fake_key", "year_shape", "price_basis", "time_basis", "placeholder",
                                   "origin", "annotations", "source_family", "source_id", "negative", "bound"])
def test_corrupt_control_stays_unavailable_in_the_cli_denominator(tmp_path, defect):
    """Bad support cannot disappear or become a passing unsupported comparison."""
    bundle = deepcopy(BUNDLE)
    left = bundle["cases"][0]["left"]
    if defect == "amount_anchor":
        left["text"] = left["text"].replace("USD 2 billion", "USD 200 billion")
    elif defect == "currency":
        left["annotations"]["currency"] = "EUR"
        left["text"] = left["text"].replace("currency=USD", "currency=EUR")
    elif defect == "year_anchor":
        left["annotations"]["year"] = "2026"
    elif defect == "duplicate_clause":
        left["text"] += " year=2030;"
    elif defect == "fake_key":
        left["text"] = left["text"].replace("year=", "other_year=")
    elif defect in {"year_shape", "price_basis", "time_basis", "placeholder"}:
        key, value = {"year_shape": ("year", "2025-Q1"), "price_basis": ("price_basis", "N/A"),
                      "time_basis": ("time_basis", "not checked"), "placeholder": ("market_scope", "unknown")}[defect]
        old = left["annotations"][key]
        left["annotations"][key] = value
        left["text"] = left["text"].replace(f"{key}={old};", f"{key}={value};")
    elif defect == "origin":
        left["origin"] = "independent_human_review"
    elif defect == "annotations":
        left["annotations"].pop("year")
    elif defect in {"source_family", "source_id"}:
        left[defect] = None
    else:
        amount = "USD -2 billion" if defect == "negative" else "over USD 2 billion"
        left["text"] = left["text"].replace(left["amount"], amount)
        left["amount"] = amount
    path = control_file(tmp_path, bundle)
    process = cli("--controls", path, tmp_path / "result")
    assert process.returncode == 2
    payload = json.loads((tmp_path / "result" / "samples.json").read_text(encoding="utf-8"))
    assert payload["summary"]["cases"] == 16
    assert payload["summary"]["unavailable"] == 1
    assert payload["summary"]["contract_matches"] == 15
    assert payload["cases"][0]["status"] == "unavailable"
    direct = samples.evaluate_controls(bundle)
    assert {key: payload[key] for key in direct} == direct


def test_a_wrong_expectation_is_a_failed_contract_not_an_accuracy_success(tmp_path):
    bundle = deepcopy(BUNDLE)
    bundle["cases"][0]["expected"]["ratio"] = "2000"
    process = cli("--controls", control_file(tmp_path, bundle), tmp_path / "result")
    assert process.returncode == 2
    summary = json.loads(process.stdout)
    assert summary["checked"] == 16 and summary["contract_matches"] == 15


@pytest.mark.parametrize("defect", ["empty", "duplicate", "provenance", "root_shape"])
def test_invalid_cohort_is_not_an_empty_pass(tmp_path, defect):
    bundle = deepcopy(BUNDLE)
    if defect == "empty":
        bundle["cases"] = []
    elif defect == "duplicate":
        bundle["cases"][1]["id"] = bundle["cases"][0]["id"]
    elif defect == "provenance":
        bundle["origin"] = "expert_evaluation"
    else:
        bundle = []
    process = cli("--controls", control_file(tmp_path, bundle), tmp_path / "result")
    assert process.returncode == 2 and json.loads(process.stdout)["status"] == "unavailable"
    assert not (tmp_path / "result").exists()


def test_snapshot_cli_preserves_spans_hashes_unknowns_and_separate_denominators(tmp_path):
    """A saved source snippet is neither primary truth nor a completed review."""
    root = tmp_path / "inputs"
    unit(root)
    unit(root, "unit-r2")
    unit(root, "other-topic", topic="solar cells", mode="fixture")
    before = {p: p.read_bytes() for p in root.rglob("*.json")}
    process = cli("--snapshot", root, tmp_path / "result")
    assert process.returncode == 0, process.stderr
    payload = json.loads((tmp_path / "result" / "samples.json").read_text(encoding="utf-8"))
    assert json.loads(process.stdout) == payload["summary"]
    assert payload["summary"] == {"units": 3, "available": 3, "unavailable": 0, "modes": {"live": 2, "fixture": 1},
                                  "candidates": 4, "topics": 2, "reviewed": 0, "externally_verified": 0,
                                  "scored_comparisons": 0}
    for row in payload["candidates"]:
        raw = before[root / row["unit"] / "market_evidence.json"]
        source = json.loads(raw)["sources"][int(row["json_pointer"].split("/")[2])]
        assert row["text"] == source["evidence_summary"]
        assert row["file_sha256"] == hashlib.sha256(raw).hexdigest()
        assert row["meta_sha256"] == hashlib.sha256(before[root / row["unit"] / "meta.json"]).hexdigest()
        assert row["text_sha256"] == hashlib.sha256(row["text"].encode()).hexdigest()
        assert row["annotations"] == dict.fromkeys(samples.DIMENSIONS)
        assert row["expected"] is None and row["judgment"] == "unreviewed"
        assert row["external_verification"] == "not_performed" and row["source_url_verified"] is False
        assert row["source_id"] == source["source_id"] and row["source_url"] == source["url"]
        assert row["amount_candidates"]
        for amount in row["amount_candidates"]:
            assert row["text"][amount["start"]:amount["end"]] == amount["literal"]
    assert before == {p: p.read_bytes() for p in root.rglob("*.json")}
    assert "contract_matches" not in payload["summary"]
    assert "accuracy" not in payload["summary"]
    direct = samples.prepare_snapshot(root)
    assert {key: payload[key] for key in direct} == direct


@pytest.mark.parametrize("defect", ["missing_meta", "bad_mode", "mode_shape", "duplicate_source", "broken_json", "large"])
def test_bad_snapshot_unit_is_retained_and_cannot_partially_supply_candidates(tmp_path, defect):
    root = tmp_path / "inputs"
    folder = unit(root, bad=defect == "duplicate_source")
    if defect == "missing_meta":
        (folder / "meta.json").unlink()
    elif defect in {"bad_mode", "mode_shape"}:
        (folder / "meta.json").write_text(json.dumps({"evidence_mode": "unknown" if defect == "bad_mode" else []}), encoding="utf-8")
    elif defect == "broken_json":
        (folder / "market_evidence.json").write_text("SECRET-SOURCE-CONTENT", encoding="utf-8")
    elif defect == "large":
        (folder / "market_evidence.json").write_bytes(b"x" * (samples._MAX_BYTES + 1))
    unit(root, "good", topic="solar")
    process = cli("--snapshot", root, tmp_path / "result")
    assert process.returncode == 2
    data = json.loads((tmp_path / "result" / "samples.json").read_text(encoding="utf-8"))
    assert data["summary"]["units"] == 2 and data["summary"]["unavailable"] == 1
    assert data["summary"]["candidates"] == 2
    assert all(row["unit"] == "good" for row in data["candidates"])
    assert "SECRET-SOURCE-CONTENT" not in json.dumps(data) + process.stdout + process.stderr
    direct = samples.prepare_snapshot(root)
    assert {key: data[key] for key in direct} == direct


@pytest.mark.parametrize("target", ["occupied", "inside_input", "empty_input", "no_amounts"])
def test_nonexistent_work_or_overwrite_is_never_a_successful_preparation(tmp_path, target):
    root, output = tmp_path / "inputs", tmp_path / "result"
    folder = unit(root)
    if target == "occupied":
        output.mkdir()
        (output / "samples.json").write_text("keep", encoding="utf-8")
    elif target == "inside_input":
        output = root / "result"
    elif target == "empty_input":
        root = tmp_path / "empty"
        root.mkdir()
    else:
        value = json.loads((folder / "market_evidence.json").read_text())
        for source in value["sources"]:
            source["evidence_summary"] = "No monetary amount stated."
        (folder / "market_evidence.json").write_text(json.dumps(value), encoding="utf-8")
    before = {p: p.read_bytes() for p in root.rglob("*.json")}
    process = cli("--snapshot", root, output)
    assert process.returncode == 2
    assert before == {p: p.read_bytes() for p in root.rglob("*.json")}
    if target == "occupied":
        assert (output / "samples.json").read_text() == "keep"


def test_snapshot_candidates_cannot_be_relabelled_as_control_evaluation(tmp_path):
    """The actual CLI rejects a prepared snapshot at the controls entry point."""
    root = tmp_path / "inputs"
    unit(root)
    assert cli("--snapshot", root, tmp_path / "prepared").returncode == 0
    process = cli("--controls", tmp_path / "prepared" / "samples.json", tmp_path / "result")
    assert process.returncode == 2 and json.loads(process.stdout)["status"] == "unavailable"
    assert not (tmp_path / "result").exists()


def test_resolved_snapshot_escape_is_rejected_before_any_file_read(tmp_path, monkeypatch):
    """The resolution boundary works without requiring Windows symlink rights."""
    root = tmp_path / "inputs"
    unit(root)
    original = Path.resolve
    reads = []

    def resolved(path, *args, **kwargs):
        if path.name == "market_evidence.json":
            return tmp_path / "outside" / path.name
        return original(path, *args, **kwargs)

    def read(path):
        reads.append(path)
        raise AssertionError("escaped input was read")

    monkeypatch.setattr(Path, "resolve", resolved)
    monkeypatch.setattr(samples, "_read", read)
    value = samples.prepare_snapshot(root)
    assert value["summary"]["unavailable"] == 1
    assert value["candidates"] == [] and reads == []
