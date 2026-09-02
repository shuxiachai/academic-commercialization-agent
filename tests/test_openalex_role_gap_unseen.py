"""Zero-network seams for adaptive role-gap closure v8."""

from __future__ import annotations

import json
from pathlib import Path
import socket

import pytest

import openalex_role_gap_unseen as unseen


def _write_fixture(tmp_path: Path, payload: dict[str, object]) -> tuple[Path, str]:
    fixture = tmp_path / "challenge.json"
    fixture.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return fixture, unseen._sha256_bytes(fixture.read_bytes())  # noqa: SLF001


def _development_case(index: int = 0) -> unseen.PreparedRoleGapCase:
    return unseen.load_frozen_cases("development")[2][index]


def _candidate_for_role(role: unseen.RoleGapRoleSpec) -> unseen.RoleGapCandidateText:
    # One candidate per role keeps the test honest about candidate locality.
    # The filler abstract also exercises title+abstract normalization without
    # introducing phrases from another role.
    return unseen.RoleGapCandidateText(
        title=" | ".join(role.signal_groups[0]),
        abstract="Frozen synthetic candidate used only by a zero-network test.",
    )


def _candidates_covering(
    case: unseen.PreparedRoleGapCase,
    role_ids: set[str],
) -> tuple[unseen.RoleGapCandidateText, ...]:
    return tuple(
        _candidate_for_role(role)
        for _, role in case.spec.roles.ordered_roles()
        if role.role_id in role_ids
    )


def test_development_dry_run_exposes_six_identities_but_caps_two_calls_per_case():
    result = unseen.dry_run("development")

    assert result["fixture_sha256"] == unseen.EXPECTED_FIXTURE_SHA256
    assert result["case_count"] == 8
    assert [item["case_id"] for item in result["cases"]] == [
        f"AC{index:02d}" for index in range(1, 9)
    ]
    assert result["potential_call_identity_count"] == 48
    assert result["maximum_executed_search_request_count"] == 16
    assert result["maximum_provider_row_count"] == 96
    assert result["maximum_model_call_count"] == 0

    anchors = [case["anchor"] for case in result["cases"]]
    closures = [
        option for case in result["cases"] for option in case["closure_options"]
    ]
    assert len(anchors) == 8
    assert len(closures) == 40
    assert len(
        {item["idempotency_key"] for item in (*anchors, *closures)}
    ) == 48
    assert len(
        {item["anchor_contract_sha256"] for item in anchors}
    ) == 8
    assert len(
        {item["closure_contract_sha256"] for item in closures}
    ) == 40
    assert {item["result_limit"] for item in (*anchors, *closures)} == {6}

    for key in (
        "case_spec_sha256",
        "collection_sha256",
        "profile_sha256",
        "case_contract_sha256",
    ):
        assert len({item[key] for item in result["cases"]}) == 8

    assert result["provider_contract"] == {
        "provider": "anonymous_openalex",
        "maximum_requests_per_case": 2,
        "result_limit_per_request": 6,
        "require_abstract": True,
        "allow_redirects": False,
        "allow_retries": False,
    }
    assert result["routing_contract"] == {
        "anchor_lane_id": "anchor_search",
        "closure_lane_id": "role_closure",
        "candidate_local_signals": True,
        "group_match_requires_all_phrases": True,
        "provider_metadata_may_establish_role": False,
        "missing_role_tiebreak": "frozen_case_priority",
        "closure_query_must_be_frozen": True,
        "maximum_closure_calls": 1,
        "stop_when_no_gap": True,
    }
    assert result["qualification_contract"] == {
        "minimum_cases_with_relevant_novel_candidate": 6,
        "minimum_candidate_pool_precision": 0.25,
        "minimum_human_correct_routing_decisions": 6,
        "minimum_cases_with_selected_role_closure_value": 4,
        "minimum_human_coverable_cases": 6,
        "minimum_coverability_gain_over_anchor": 2,
    }
    for flag in (
        "production_connected",
        "report_workflow_connected",
        "shadow_planner_connected",
        "checkpoint_connected",
        "recovery_connected",
        "real_network_calls_performed",
        "real_model_calls_performed",
        "private_labels_opened",
        "human_qualification_performed",
        "live_provider_requests_authorized",
        "live_model_calls_authorized",
    ):
        assert result[flag] is False


def test_every_frozen_closure_option_reaches_the_serialized_boundary():
    """A valid option is useless if it disappears before the client seam."""

    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    result = unseen.dry_run("development")
    role_kinds = ("required", "scope", "supporting")
    expected = [
        {
            "case_id": case["case_id"],
            "role_id": role["role_id"],
            "role_kind": role_kind,
            "query": role["closure_query"],
        }
        for case in payload["development_cases"]
        for role_kind in role_kinds
        for role in case["roles"][role_kind]
    ]
    observed = [
        {
            "case_id": case["case_id"],
            "role_id": option["role_id"],
            "role_kind": option["role_kind"],
            "query": option["query"],
        }
        for case in result["cases"]
        for option in case["closure_options"]
    ]

    assert observed == expected
    assert all(
        len(option["idempotency_key"]) == 64
        and len(option["plan_sha256"]) == 64
        and len(option["closure_contract_sha256"]) == 64
        for case in result["cases"]
        for option in case["closure_options"]
    )


def test_empty_anchor_probe_exposes_every_negative_observation_and_route_identity():
    result = unseen.dry_run("development")

    for case in result["cases"]:
        probe = case["empty_anchor_route_probe"]
        assert case["route_probe_uses_provider_observations"] is False
        assert probe["checked"] is True
        assert probe["action"] == "search"
        assert probe["reason"] == "highest_priority_missing_role"
        assert len(probe["observations"]) == 5
        assert all(not observation["observed"] for observation in probe["observations"])
        assert all(
            observation["checked_candidate_count"] == 0
            for observation in probe["observations"]
        )
        assert probe["missing_role_ids"] == case["closure_priority_role_ids"]
        selected = probe["selected_closure"]
        assert selected["role_id"] == case["closure_priority_role_ids"][0]
        matching_option = next(
            option
            for option in case["closure_options"]
            if option["role_id"] == selected["role_id"]
        )
        assert selected["query"] == matching_option["query"]
        assert (
            selected["closure_contract_sha256"]
            == matching_option["closure_contract_sha256"]
        )


def test_role_phrases_split_across_candidates_cannot_complete_one_signal_group():
    """This is the required regression seam for cross-candidate pooling."""

    case = _development_case()
    target_role_id = "engineered_pet_hydrolase"
    other_role_ids = {
        role.role_id
        for _, role in case.spec.roles.ordered_roles()
        if role.role_id != target_role_id
    }
    split_candidates = (
        unseen.RoleGapCandidateText(
            title="An engineered catalyst for polymer recycling",
            abstract="No named hydrolase appears in this candidate.",
        ),
        unseen.RoleGapCandidateText(
            title="PETase activity in a polyester assay",
            abstract="No engineering claim appears in this candidate.",
        ),
    )
    candidates = (*split_candidates, *_candidates_covering(case, other_role_ids))

    decision = unseen.route_anchor_candidates(case, candidates)
    observation = next(
        item for item in decision.observations if item.role_id == target_role_id
    )

    assert observation.observed is False
    assert target_role_id in decision.missing_role_ids
    assert decision.action == "search"
    assert decision.selected_closure is not None
    assert decision.selected_closure.role_id == target_role_id


def test_frozen_priority_wins_when_serialized_role_order_points_elsewhere():
    case = _development_case()
    # AC01 serializes enzymatic_pet_depolymerization before
    # polyester_textile_waste, but its frozen priority orders them oppositely
    # once engineered_pet_hydrolase has been observed.
    missing = {"enzymatic_pet_depolymerization", "polyester_textile_waste"}
    covered = {
        role.role_id
        for _, role in case.spec.roles.ordered_roles()
        if role.role_id not in missing
    }

    decision = unseen.route_anchor_candidates(
        case,
        _candidates_covering(case, covered),
    )

    assert decision.missing_role_ids[:2] == (
        "polyester_textile_waste",
        "enzymatic_pet_depolymerization",
    )
    assert decision.selected_closure is not None
    assert decision.selected_closure.role_id == "polyester_textile_waste"


def test_fully_observed_anchor_abstains_without_a_closure_call():
    case = _development_case()
    all_role_ids = {
        role.role_id for _, role in case.spec.roles.ordered_roles()
    }

    decision = unseen.route_anchor_candidates(
        case,
        _candidates_covering(case, all_role_ids),
    )

    assert all(observation.observed for observation in decision.observations)
    assert decision.action == "abstain"
    assert decision.reason == "abstain_no_mechanical_role_gap"
    assert decision.missing_role_ids == ()
    assert decision.selected_closure is None


def test_selected_query_is_exactly_one_pre_frozen_closure_option():
    case = _development_case(1)
    covered = {
        role.role_id
        for _, role in case.spec.roles.ordered_roles()
        if role.role_id != case.spec.closure_priority_role_ids[0]
    }

    decision = unseen.route_anchor_candidates(
        case,
        _candidates_covering(case, covered),
    )

    assert decision.selected_closure is not None
    expected_role = case.spec.closure_priority_role_ids[0]
    expected_option = next(
        option for option in case.closure_options if option.role_id == expected_role
    )
    assert decision.selected_closure == expected_option
    assert decision.selected_closure.query == expected_option.call.query


def test_unseen_cohort_has_distinct_identities_and_zero_live_authority():
    development = unseen.dry_run("development")
    challenge = unseen.dry_run("unseen")

    assert [item["case_id"] for item in challenge["cases"]] == [
        f"AD{index:02d}" for index in range(1, 9)
    ]
    assert {
        item["case_contract_sha256"] for item in development["cases"]
    }.isdisjoint(item["case_contract_sha256"] for item in challenge["cases"])
    development_calls = {
        item["idempotency_key"]
        for case in development["cases"]
        for item in (case["anchor"], *case["closure_options"])
    }
    challenge_calls = {
        item["idempotency_key"]
        for case in challenge["cases"]
        for item in (case["anchor"], *case["closure_options"])
    }
    assert development_calls.isdisjoint(challenge_calls)
    assert challenge["real_network_calls_performed"] is False
    assert challenge["real_model_calls_performed"] is False
    assert challenge["live_provider_requests_authorized"] is False


def test_fixture_byte_drift_fails_before_case_expansion(tmp_path, monkeypatch):
    fixture = tmp_path / "drifted.json"
    fixture.write_bytes(unseen.DEFAULT_FIXTURE_PATH.read_bytes() + b" ")

    def must_not_expand(*args, **kwargs):
        raise AssertionError("case expansion ran before the raw hash check")

    monkeypatch.setattr(unseen, "build_case", must_not_expand)
    with pytest.raises(
        unseen.OpenAlexRoleGapPreflightError,
        match="fixture byte identity drifted",
    ):
        unseen.load_frozen_cases("development", fixture)


def test_case_order_drift_is_rejected_with_a_matching_test_hash(tmp_path):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["development_cases"][0], payload["development_cases"][1] = (
        payload["development_cases"][1],
        payload["development_cases"][0],
    )
    fixture, fixture_hash = _write_fixture(tmp_path, payload)

    with pytest.raises(ValueError, match="AC01 through AC08"):
        unseen.load_frozen_cases(
            "development",
            fixture,
            expected_fixture_sha256=fixture_hash,
        )


def test_priority_must_name_every_role_exactly_once(tmp_path):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["development_cases"][0]["closure_priority_role_ids"][-1] = (
        payload["development_cases"][0]["closure_priority_role_ids"][0]
    )
    fixture, fixture_hash = _write_fixture(tmp_path, payload)

    with pytest.raises(ValueError, match="closure-priority role IDs must be unique"):
        unseen.load_frozen_cases(
            "development",
            fixture,
            expected_fixture_sha256=fixture_hash,
        )


def test_priority_drift_changes_route_identity_but_not_frozen_call_identities(
    tmp_path,
):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    priority = payload["development_cases"][0]["closure_priority_role_ids"]
    priority[0], priority[1] = priority[1], priority[0]
    fixture, fixture_hash = _write_fixture(tmp_path, payload)

    original = unseen.dry_run("development")
    drifted = unseen.dry_run(
        "development",
        fixture,
        expected_fixture_sha256=fixture_hash,
    )
    original_case = original["cases"][0]
    drifted_case = drifted["cases"][0]

    assert drifted_case["case_spec_sha256"] != original_case["case_spec_sha256"]
    assert (
        drifted_case["case_contract_sha256"]
        != original_case["case_contract_sha256"]
    )
    assert (
        drifted_case["anchor"]["idempotency_key"]
        == original_case["anchor"]["idempotency_key"]
    )
    assert [
        option["idempotency_key"] for option in drifted_case["closure_options"]
    ] == [
        option["idempotency_key"] for option in original_case["closure_options"]
    ]
    assert (
        drifted_case["empty_anchor_route_probe"]["selected_closure"]["role_id"]
        == priority[0]
    )


def test_closure_query_drift_changes_only_its_query_bound_call(tmp_path):
    payload = json.loads(unseen.DEFAULT_FIXTURE_PATH.read_text(encoding="utf-8"))
    payload["development_cases"][0]["roles"]["required"][0][
        "closure_query"
    ] += " validation"
    fixture, fixture_hash = _write_fixture(tmp_path, payload)

    original = unseen.dry_run("development")["cases"][0]
    drifted = unseen.dry_run(
        "development",
        fixture,
        expected_fixture_sha256=fixture_hash,
    )["cases"][0]

    assert drifted["collection_sha256"] == original["collection_sha256"]
    assert drifted["profile_sha256"] == original["profile_sha256"]
    assert drifted["anchor"]["idempotency_key"] == original["anchor"][
        "idempotency_key"
    ]
    assert drifted["case_contract_sha256"] != original["case_contract_sha256"]
    assert (
        drifted["closure_options"][0]["idempotency_key"]
        != original["closure_options"][0]["idempotency_key"]
    )
    assert [
        option["idempotency_key"] for option in drifted["closure_options"][1:]
    ] == [
        option["idempotency_key"] for option in original["closure_options"][1:]
    ]


def test_dry_run_opens_no_socket_even_when_socket_creation_is_blocked(monkeypatch):
    def block_socket(*args, **kwargs):
        raise AssertionError("preflight attempted to create a socket")

    monkeypatch.setattr(socket, "socket", block_socket)

    result = unseen.dry_run("development")

    assert result["case_count"] == 8
    assert result["real_network_calls_performed"] is False


def test_preflight_imports_no_provider_model_execution_or_private_review_code():
    source = Path("openalex_role_gap_unseen.py").read_text(encoding="utf-8")

    for forbidden in (
        "anonymous_openalex_search",
        "OpenAlexEvidenceSearchAdapter",
        "execute_gap_plan",
        "qwen",
        "litellm",
        "crewai",
        "urllib",
        "role_directed_review",
        "outputs/private-notes",
    ):
        assert forbidden not in source
