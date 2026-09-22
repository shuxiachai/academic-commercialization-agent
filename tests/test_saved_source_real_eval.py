"""Synthetic-only RU byte binding, capacity, reference isolation and freezing."""

import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from academic_agent import saved_source_real_eval as prep


def encode(value):
    return json.dumps(value, ensure_ascii=False).encode("utf-8")


def synthetic_inputs():
    documents = {}
    for name in ("D1", "D2"):
        titles = ["Synthetic Scaffolding review", "Synthetic Scaffolding alternatives",
                  "Synthetic Bioprocess Engineering" if name == "D1" else "Synthetic Interconnects and vias"]
        sources = {"topic": "SYNTHETIC " + name, "retained_historical_field": "not evidence"}
        for group, ids in (("academic", ["A1", "A2", "A3"]), ("patent", ["P1"]), ("market", ["M1"])):
            sources[group + "_sources"] = [{
                "source_id": source_id, "title": titles[index] if group == "academic" else "Synthetic " + source_id,
                "publisher": "SYNTHETIC publisher only", "source_type": "test_saved_record",
                "accessed_date": " exact historical date ", "published_date": "1801-01-02",
                "doi": " retained DOI ", "url": "https://example.invalid/synthetic",
                "evidence_summary": "  SYNTHETIC SAVED " + name + source_id + " 测试🙂\r\n<script>inert</script>\t",
                "summary_source": "abstract", "ignored_original_field": 9,
            } for index, source_id in enumerate(ids)]
        documents[name] = {"report": ("SYNTHETIC REPORT ONLY " + name).encode(), "sources": encode(sources),
                           "metadata": encode({"topic": sources["topic"], "status": "success", "evidence_mode": "live"})}
    questions = {"cases": [{"case_id": case_id, "doc_id": doc_id,
                            "question": f"Synthetic question {case_id}: what does this study discuss?",
                            "keyword_query": keyword} for case_id, doc_id, keyword in
                           zip(prep.CASE_IDS, prep.DOC_IDS, ("Bioprocess Engineering", "Scaffolding", "Interconnects", "tokamak"), strict=True)]}
    references = {"provenance": "AI_authored_draft", "blind_review": "not_run", "cases": [
        {"case_id": case_id, "acceptable_source_ids": ids} for case_id, ids in
        zip(prep.CASE_IDS, (["A3"], ["A1", "A2"], ["A3"], []), strict=True)]}
    scripts = {"cases": [{"case_id": case_id, "source_id": source_id} for case_id, source_id in
                         zip(prep.CASE_IDS, ("A3", "A1", "A3", None), strict=True)]}
    return {"documents": documents, "questions": encode(questions), "references": encode(references), "scripts": encode(scripts)}


@pytest.fixture
def inputs():
    return synthetic_inputs()


@pytest.fixture
def packet(inputs):
    return prep.build_packet(**inputs)


def test_raw_bytes_projection_order_dates_and_sandbox_alias(inputs, packet):
    """Raw and projection identity differ; no date normalization or subset is permitted."""
    prep.validate_packet(packet)
    assert packet["live_authorization"] is False
    assert packet["native_efficacy"] == packet["reference_review"] == "not_run"
    assert packet["purpose"] == "purposeful_development"
    for name in ("D1", "D2"):
        doc = packet["prepared"]["documents"][name]
        raw = inputs["documents"][name]
        assert doc["sandbox_alias"] == "20260922T000000Z-" + hashlib.sha256(raw["sources"]).hexdigest()[:32]
        assert doc["alias_scope"] == "sandbox_not_original_run_url"
        assert doc["raw_sha256"] == {key: hashlib.sha256(value).hexdigest() for key, value in raw.items()}
        rows = doc["snapshot"]["sources"]
        assert [row["source_id"] for row in rows] == ["A1", "A2", "A3", "P1", "M1"]
        assert all(row["accessed_date"] == " exact historical date " and row["published_date"] == "1801-01-02" for row in rows)
        assert doc["catalog"]["entries"] == [{"source_id": row["source_id"], "title": row["title"], "title_truncated": False} for row in rows]
    assert packet["prepared"]["documents"]["D1"]["sandbox_alias"] != packet["prepared"]["documents"]["D2"]["sandbox_alias"]
    assert not any(name.startswith("docs/") for name in packet["code_identity"]["working_file_sha256"])


@pytest.mark.parametrize("kind", ["report", "metadata", "sources"])
def test_raw_drift_invalidates_even_unchanged_projection(packet, kind):
    """An added whitespace byte must not retain an old raw packet binding."""
    changed = deepcopy(packet)
    raw = base64.b64decode(changed["raw"]["documents"]["D1"][kind])
    changed["raw"]["documents"]["D1"][kind] = base64.b64encode(raw + b" ").decode()
    with pytest.raises(prep.PreparationError, match="^Offline saved-source preparation unavailable\\.$"):
        prep.validate_packet(changed)


@pytest.mark.parametrize("field", ["prepared", "packet_sha256", "code_identity", "live_authorization", "raw_input_sha256"])
def test_forged_binding_fields_rejected(packet, field):
    """A digest or prepared projection cannot declare its own integrity."""
    packet[field] = True
    with pytest.raises(prep.PreparationError):
        prep.validate_packet(packet)


def test_reference_and_script_rebinding_never_changes_preview_or_review(inputs, packet):
    """Changing draft labels does not select a different source or leak labels to wire."""
    before = prep.preview_wire(packet)
    labels = json.loads(inputs["references"])
    labels["cases"][0]["acceptable_source_ids"] = ["M1"]
    inputs["references"] = encode(labels)
    changed = prep.build_packet(**inputs)
    assert changed["packet_sha256"] != packet["packet_sha256"]
    assert changed["prepared"] == packet["prepared"]
    assert prep.preview_wire(changed) == before
    assert prep.review_view(changed) == prep.review_view(packet)
    assert prep._inputs(changed)["scripts"] == prep._inputs(packet)["scripts"]
    actions = json.loads(inputs["scripts"])
    actions["cases"][0]["source_id"] = "P1"
    inputs["scripts"] = encode(actions)
    assert prep.preview_wire(prep.build_packet(**inputs)) == before
    for wire in before.values():
        assert len(wire) <= 12288
        assert all(marker not in wire for marker in (b"acceptable_source_ids", b"keyword_query", b"SYNTHETIC SAVED",
                                                     b"SYNTHETIC REPORT", b"sandbox_alias", b"blind_review"))
        body = json.loads(wire)
        assert set(body) == {"model", "messages", "tools", "tool_choice", "stream", "enable_thinking", "parallel_tool_calls", "temperature", "max_tokens"}
    for case in prep.review_view(packet)["cases"]:
        assert set(case) == {"case_id", "doc_id", "question", "catalog"}
        assert all(set(row) == {"source_id", "title"} for row in case["catalog"])


@pytest.mark.parametrize("kind", ["questions", "references", "scripts"])
def test_case_order_and_count_are_fixed(inputs, kind):
    """Reordered/missing cases cannot silently align labels, documents or scripts."""
    value = json.loads(inputs[kind])
    value["cases"].reverse()
    inputs[kind] = encode(value)
    with pytest.raises(prep.PreparationError):
        prep.build_packet(**inputs)


@pytest.mark.parametrize("fault", ["doc_mapping", "duplicate_question", "extra_case", "review_claim", "bad_reference", "bad_script", "same_docs"])
def test_fixed_protocol_and_separate_choice_validation(inputs, fault):
    """The preparation cannot manufacture completed judging or accept invisible IDs."""
    kind = "questions"
    q, r, s = (json.loads(inputs[key]) for key in ("questions", "references", "scripts"))
    if fault == "doc_mapping":
        q["cases"][0]["doc_id"] = "D2"
    elif fault == "duplicate_question":
        q["cases"][1]["question"] = q["cases"][0]["question"]
    elif fault == "extra_case":
        q["cases"].append(q["cases"][0])
    elif fault == "review_claim":
        r["blind_review"] = "passed"
        kind = "references"
    elif fault == "bad_reference":
        r["cases"][0]["acceptable_source_ids"] = ["A99"]
        kind = "references"
    elif fault == "bad_script":
        s["cases"][0]["source_id"] = "A99"
        kind = "scripts"
    else:
        inputs["documents"]["D2"] = inputs["documents"]["D1"]
    inputs[kind] = encode({"questions": q, "references": r, "scripts": s}[kind])
    with pytest.raises(prep.PreparationError):
        prep.build_packet(**inputs)


@pytest.mark.parametrize("fault", ["fixture", "status", "topic", "dry_run", "duplicate_id", "missing_group", "wrong_group", "bad_json", "title", "catalog", "blank", "long_text"])
def test_source_and_metadata_admission_never_repairs_or_filters(inputs, fault):
    """Malformed, overlong or partial catalogs must fail rather than drop distractors."""
    doc = inputs["documents"]["D1"]
    sources, meta = json.loads(doc["sources"]), json.loads(doc["metadata"])
    if fault == "fixture":
        meta["evidence_mode"] = "fixture"
    elif fault == "status":
        meta["status"] = "failed"
    elif fault == "topic":
        meta["topic"] += " "
    elif fault == "dry_run":
        meta["dry_run"] = 0
    elif fault == "duplicate_id":
        sources["academic_sources"][1]["source_id"] = "A1"
    elif fault == "missing_group":
        del sources["market_sources"]
    elif fault == "wrong_group":
        sources["patent_sources"][0]["source_id"] = "A4"
    elif fault == "title":
        sources["academic_sources"][0]["title"] = "T" * 257
    elif fault == "catalog":
        for index in range(4, 34):
            sources["academic_sources"].append({**sources["academic_sources"][0], "source_id": f"A{index}"})
    elif fault in ("blank", "long_text"):
        sources["market_sources"][0]["evidence_summary"] = " " if fault == "blank" else "x" * 1501
    doc["sources"], doc["metadata"] = encode(sources), encode(meta)
    if fault == "bad_json":
        doc["metadata"] = b'{"status":"success","status":"success"}'
    with pytest.raises(prep.PreparationError) as error:
        prep.build_packet(**inputs)
    assert str(error.value) == "Offline saved-source preparation unavailable."


@pytest.mark.parametrize("kind", list(prep.RAW_LIMITS))
def test_all_raw_byte_limits(inputs, kind):
    """Raw prose and labels, not just source windows, have whole-byte bounds."""
    target = inputs["documents"]["D1"] if kind in ("report", "metadata", "sources") else inputs
    target[kind] = b"x" * (prep.RAW_LIMITS[kind] + 1)
    with pytest.raises(prep.PreparationError):
        prep.build_packet(**inputs)


def test_ascii_expansion_and_whole_packet_limit(inputs, packet, monkeypatch):
    """Codepoint-valid questions can overflow full escaped HTTP, and envelopes count too."""
    value = json.loads(inputs["questions"])
    value["cases"][0]["question"] = "界" * 4096
    inputs["questions"] = encode(value)
    with pytest.raises(prep.PreparationError):
        prep.build_packet(**inputs)
    packet["unknown_private_field"] = "x" * prep.MAX_PACKET_BYTES
    with pytest.raises(prep.PreparationError):
        prep.serialize_packet(packet)
    monkeypatch.setattr(prep, "REQUEST_BYTES", 100)
    with pytest.raises(prep.PreparationError):
        prep.build_packet(**synthetic_inputs())


def test_write_once_private_freeze_and_no_path_leaks(packet, tmp_path, monkeypatch):
    """The private packet may not overwrite, follow symlinks, or export outside outputs."""
    monkeypatch.setattr(prep, "PRIVATE_ROOT", tmp_path)
    target = tmp_path / "packet.json"
    digest = prep.freeze_packet(packet, target)
    original = target.read_bytes()
    assert digest == hashlib.sha256(original).hexdigest()
    assert json.loads(original) == packet
    for path in (target, tmp_path.parent / "PUBLIC-PRIVATE-SENTINEL.json", tmp_path / "absent" / "packet.json"):
        with pytest.raises(prep.PreparationError) as error:
            prep.freeze_packet(packet, path)
        assert "PRIVATE-SENTINEL" not in str(error.value) and str(tmp_path) not in str(error.value)
    assert target.read_bytes() == original
    # Simulated lstat is portable on Windows without permission to create links.
    real = Path.lstat
    def linked(path):
        value = real(path)
        if path == tmp_path:
            from types import SimpleNamespace
            import stat
            return SimpleNamespace(st_mode=stat.S_IFLNK, st_file_attributes=0)
        return value
    monkeypatch.setattr(Path, "lstat", linked)
    with pytest.raises(prep.PreparationError):
        prep.freeze_packet(packet, tmp_path / "new.json")
    assert not (tmp_path / "new.json").exists()
