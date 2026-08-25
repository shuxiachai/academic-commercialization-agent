"""Phase-1 evidence-gap contracts: eligibility, plans, and zero-call audit."""

from __future__ import annotations

import json
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from pydantic import ValidationError

import evidence_gap_audit
from academic_agent.evidence import EvidenceSource
from academic_agent.evidence_gap import (
    EVIDENCE_GAP_SHADOW_FILENAME,
    EvidenceGapError,
    GapPlanProposal,
    GapSearchIntent,
    build_gap_context,
    parse_shadow_configuration,
    persist_shadow_audit,
    run_shadow_assessment,
    source_collection_sha256,
    validate_gap_plan,
)
from academic_agent.source_pipeline import (
    AuthorityCoverage,
    ComponentCoverage,
    SourceCollection,
    _detect_weight_profile,
    _measure_authority_coverage,
)


_SUMMARY = (
    "This validated source contains enough specific evidence text for the "
    "strict source model and for deterministic evidence-gap unit tests."
)


def _source(source_id: str, source_type: str, url: str) -> EvidenceSource:
    return EvidenceSource(
        source_id=source_id,
        title=f"Validated source record {source_id}",
        url=url,
        publisher="Example Publisher",
        # A historical date keeps the synthetic fixture valid when Sydney has
        # crossed midnight but GitHub's UTC runners have not.
        accessed_date=date(2025, 1, 1),
        source_type=source_type,
        evidence_summary=_SUMMARY,
    )


def _collection(
    *,
    topic: str = "solid-state batteries for electric vehicles",
    profile: str = "industrial",
    authority: AuthorityCoverage | None = None,
    components: ComponentCoverage | None = None,
    failed_domains: dict[str, str] | None = None,
) -> SourceCollection:
    return SourceCollection(
        topic=topic,
        display_topic=topic,
        search_components=list((components or ComponentCoverage()).components),
        weight_profile=profile,
        collected_at=datetime(2025, 1, 1, tzinfo=UTC),
        academic_sources=[_source("A1", "academic_paper", "https://doi.org/10.1000/example")],
        patent_sources=[_source("P1", "patent", "https://patents.google.com/patent/US123")],
        market_sources=[_source("M1", "market_report", "https://example.com/market")],
        academic_queries=[topic],
        patent_queries=[topic],
        market_queries=[topic],
        authority_coverage=authority or AuthorityCoverage(),
        component_coverage=components or ComponentCoverage(),
        failed_domains=failed_domains or {},
    )


def _eligible_collection() -> SourceCollection:
    return _collection(
        topic="CAR-T cell therapy for blood cancers",
        profile="biomedical",
        authority=AuthorityCoverage(
            status="incomplete",
            required_categories=["regulatory", "clinical_registry"],
            covered_source_ids={"regulatory": ["M1"]},
            missing_categories=["clinical_registry"],
        ),
    )


class SyntheticFixtureDateTests(unittest.TestCase):
    def test_fixture_is_valid_when_sydney_is_one_day_ahead_of_utc(self):
        """A local calendar date must not make the UTC CI fixture future-dated."""

        class UtcRunnerDate(date):
            @classmethod
            def today(cls):
                return cls(2026, 8, 24)

        with patch("academic_agent.evidence.date", UtcRunnerDate):
            collection = _collection()

        self.assertEqual(
            collection.academic_sources[0].accessed_date,
            date(2025, 1, 1),
        )


class ShadowConfigurationTests(unittest.TestCase):
    def test_missing_and_explicit_false_values_are_disabled(self):
        self.assertEqual(parse_shadow_configuration(None).state, "disabled")
        for value in ("", "0", "false", "NO", " off "):
            with self.subTest(value=value):
                self.assertEqual(parse_shadow_configuration(value).state, "disabled")

    def test_truthy_values_require_an_explicit_known_spelling(self):
        for value in ("1", "true", "YES", " on "):
            with self.subTest(value=value):
                self.assertEqual(parse_shadow_configuration(value).state, "enabled")
        self.assertEqual(parse_shadow_configuration("enabled").state, "invalid")


class GapGateTests(unittest.TestCase):
    def test_source_count_alone_never_triggers_the_gate(self):
        context = build_gap_context(_collection())
        self.assertEqual(context.source_counts, {"academic": 1, "patent": 1, "market": 1})
        self.assertEqual(context.signals, ())

    def test_missing_authority_category_has_only_the_specialized_tool(self):
        context = build_gap_context(_eligible_collection())
        self.assertEqual(len(context.signals), 1)
        signal = context.signals[0]
        self.assertEqual(signal.code, "authority_category_missing")
        self.assertEqual(signal.subject, "clinical_registry")
        self.assertEqual(signal.scope, "market")
        self.assertEqual(signal.allowed_tools, ("authority_search",))

    def test_clinical_monitoring_topic_reaches_enabled_shadow_boundary(self):
        """The live false negative must be caught across classification and gate seams."""
        topic = "Wearable continuous blood pressure monitoring via photoplethysmography"
        profile = _detect_weight_profile(topic)
        collection = _collection(topic=topic, profile=profile)
        collection.authority_coverage = _measure_authority_coverage(
            topic,
            profile,
            [
                *collection.academic_sources,
                *collection.patent_sources,
                *collection.market_sources,
            ],
        )

        audit = run_shadow_assessment(
            collection,
            configuration=parse_shadow_configuration("true"),
        )

        self.assertEqual(profile, "biomedical")
        self.assertEqual(audit.gate_state, "eligible")
        self.assertTrue(audit.checked)
        self.assertEqual(
            [(signal.code, signal.subject) for signal in audit.context.signals],
            [("authority_category_missing", "regulatory")],
        )
        self.assertEqual(audit.executed_call_count, 0)

    def test_only_explicitly_incomplete_components_trigger(self):
        for status in ("partial", "unchecked"):
            collection = _collection(
                components=ComponentCoverage(
                    status=status,
                    components=["sensor networks", "edge AI inference"],
                    covered_source_ids={"sensor networks": ["A1"]},
                    unchecked_components=["edge AI inference"],
                )
            )
            with self.subTest(status=status):
                self.assertEqual(build_gap_context(collection).signals, ())

        incomplete = _collection(
            components=ComponentCoverage(
                status="incomplete",
                components=["sensor networks", "edge AI inference"],
                covered_source_ids={"sensor networks": ["A1"]},
                missing_components=["edge AI inference"],
            )
        )
        signal = build_gap_context(incomplete).signals[0]
        self.assertEqual(signal.code, "component_missing")
        self.assertEqual(
            signal.allowed_tools,
            ("academic_search", "patent_search", "market_search"),
        )

    def test_known_failed_domain_triggers_but_unknown_label_does_not(self):
        context = build_gap_context(_collection(failed_domains={"patent": "timeout", "regulation": "bad"}))
        self.assertEqual(len(context.signals), 1)
        self.assertEqual(context.signals[0].subject, "patent")
        self.assertEqual(context.signals[0].allowed_tools, ("patent_search",))

    def test_context_hash_is_stable_and_does_not_mutate_the_collection(self):
        collection = _eligible_collection()
        before = source_collection_sha256(collection)
        first = build_gap_context(collection)
        second = build_gap_context(collection)
        self.assertEqual(first, second)
        self.assertEqual(before, source_collection_sha256(collection))


class GapPlanContractTests(unittest.TestCase):
    def setUp(self):
        self.context = build_gap_context(_eligible_collection())
        self.trigger = self.context.signals[0].signal_id

    def _intent(self, **overrides) -> GapSearchIntent:
        values = {
            "tool": "authority_search",
            "query": "CAR-T blood cancer trial results",
            "trigger_ids": (self.trigger,),
            "result_limit": 5,
        }
        values.update(overrides)
        return GapSearchIntent(**values)

    def _proposal(self, *calls: GapSearchIntent) -> GapPlanProposal:
        return GapPlanProposal(
            decision="search",
            rationale="The required registry category is absent from validated evidence.",
            calls=calls,
        )

    def test_schema_rejects_unknown_fields_and_a_third_intent(self):
        with self.assertRaises(ValidationError):
            GapPlanProposal.model_validate(
                {
                    "decision": "abstain",
                    "rationale": "There is not enough expected evidence value.",
                    "calls": [],
                    "surprise": True,
                }
            )
        with self.assertRaises(ValidationError):
            self._proposal(self._intent(), self._intent(query="second query"), self._intent(query="third query"))

    def test_known_trigger_and_authorized_tool_are_required(self):
        with self.assertRaisesRegex(EvidenceGapError, "unknown trigger"):
            validate_gap_plan(
                self.context,
                self._proposal(self._intent(trigger_ids=("gap-invented0000",))),
            )
        with self.assertRaisesRegex(EvidenceGapError, "not authorized"):
            validate_gap_plan(
                self.context,
                self._proposal(self._intent(tool="academic_search")),
            )

    def test_eligible_context_must_search_or_explicitly_abstain(self):
        proposal = GapPlanProposal(
            decision="no_gap",
            rationale="No supplementary evidence is required for this collection.",
        )
        with self.assertRaisesRegex(EvidenceGapError, "must search or explicitly abstain"):
            validate_gap_plan(self.context, proposal)

    def test_duplicate_intents_are_rejected_after_normalization(self):
        with self.assertRaisesRegex(EvidenceGapError, "duplicate"):
            validate_gap_plan(
                self.context,
                self._proposal(
                    self._intent(),
                    self._intent(query="  car-t  BLOOD cancer trial results "),
                ),
            )

    def test_valid_plan_gets_stable_local_idempotency_and_market_domain(self):
        first = validate_gap_plan(self.context, self._proposal(self._intent()))
        second = validate_gap_plan(self.context, self._proposal(self._intent()))
        self.assertEqual(first, second)
        self.assertEqual(first.calls[0].output_domain, "market")
        self.assertEqual(len(first.calls[0].idempotency_key), 64)


class ShadowExecutionTests(unittest.TestCase):
    def test_disabled_mode_never_invokes_an_injected_planner(self):
        planner = MagicMock(side_effect=AssertionError("must not run"))
        audit = run_shadow_assessment(
            _eligible_collection(),
            configuration=parse_shadow_configuration("false"),
            planner=planner,
        )
        planner.assert_not_called()
        self.assertEqual(audit.gate_state, "disabled")
        self.assertFalse(audit.checked)

    def test_disabled_mode_does_not_even_serialize_the_collection(self):
        collection = MagicMock()
        collection.model_dump.side_effect = AssertionError("must not inspect")
        audit = run_shadow_assessment(
            collection,
            configuration=parse_shadow_configuration("false"),
        )
        collection.model_dump.assert_not_called()
        self.assertEqual(audit.gate_state, "disabled")

    def test_no_gap_mode_never_invokes_an_injected_planner(self):
        planner = MagicMock(side_effect=AssertionError("must not run"))
        audit = run_shadow_assessment(
            _collection(),
            configuration=parse_shadow_configuration("true"),
            planner=planner,
        )
        planner.assert_not_called()
        self.assertEqual(audit.gate_state, "no_gap")
        self.assertTrue(audit.checked)

    def test_planner_failure_is_not_reported_as_no_gap(self):
        audit = run_shadow_assessment(
            _eligible_collection(),
            configuration=parse_shadow_configuration("true"),
            planner=MagicMock(side_effect=RuntimeError("provider unavailable")),
        )
        self.assertEqual(audit.gate_state, "eligible")
        self.assertEqual(audit.planner_state, "failed")
        self.assertEqual(audit.failure_type, "planner_RuntimeError")
        self.assertEqual(audit.executed_call_count, 0)

    def test_planner_mutation_is_visible_even_when_the_planner_raises(self):
        collection = _eligible_collection()

        def mutate_then_fail(_context):
            collection.topic = "mutated topic"
            raise RuntimeError("planner failed after mutation")

        audit = run_shadow_assessment(
            collection,
            configuration=parse_shadow_configuration("true"),
            planner=mutate_then_fail,
        )
        self.assertEqual(audit.planner_state, "failed")
        self.assertEqual(audit.failure_type, "source_collection_mutated")
        self.assertTrue(audit.evidence_changed)
        self.assertEqual(audit.executed_call_count, 0)

    def test_valid_proposal_remains_zero_call_and_does_not_change_evidence(self):
        collection = _eligible_collection()
        trigger = build_gap_context(collection).signals[0].signal_id

        def planner(_context):
            return {
                "decision": "search",
                "rationale": "The missing registry category warrants one bounded query.",
                "calls": [
                    {
                        "tool": "authority_search",
                        "query": "CAR-T blood cancer trial status",
                        "trigger_ids": [trigger],
                        "result_limit": 5,
                    }
                ],
            }

        before = source_collection_sha256(collection)
        audit = run_shadow_assessment(
            collection,
            configuration=parse_shadow_configuration("true"),
            planner=planner,
        )
        self.assertEqual(audit.planner_state, "planned")
        self.assertEqual(audit.proposed_call_count, 1)
        self.assertEqual(audit.executed_call_count, 0)
        self.assertEqual(audit.added_search_cost_usd, 0.0)
        self.assertFalse(audit.evidence_changed)
        self.assertEqual(before, source_collection_sha256(collection))

    def test_invalid_configuration_is_a_failed_check(self):
        audit = run_shadow_assessment(
            _collection(),
            configuration=parse_shadow_configuration("tru"),
        )
        self.assertEqual(audit.gate_state, "failed")
        self.assertFalse(audit.checked)
        self.assertEqual(audit.failure_type, "invalid_configuration")


class ShadowPersistenceTests(unittest.TestCase):
    def test_written_state_matches_the_downloadable_artifact(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            audit = run_shadow_assessment(
                _eligible_collection(),
                configuration=parse_shadow_configuration("true"),
            )
            persisted = persist_shadow_audit(root, audit)
            payload = json.loads((root / EVIDENCE_GAP_SHADOW_FILENAME).read_text(encoding="utf-8"))
        self.assertEqual(persisted.persistence_state, "written")
        self.assertEqual(payload, persisted.model_dump(mode="json"))

    def test_failed_write_is_visible_and_does_not_raise(self):
        with TemporaryDirectory() as temp:
            not_a_directory = Path(temp) / "run"
            not_a_directory.write_text("occupied", encoding="utf-8")
            audit = run_shadow_assessment(
                _collection(),
                configuration=parse_shadow_configuration("true"),
            )
            persisted = persist_shadow_audit(not_a_directory, audit)
        self.assertEqual(persisted.persistence_state, "failed")
        self.assertEqual(persisted.persistence_error_type, "FileExistsError")


class FrozenAuditTests(unittest.TestCase):
    def _write_fixture(self, root: Path, name: str, collection: SourceCollection) -> None:
        directory = root / name
        directory.mkdir()
        (directory / "validated_sources.json").write_text(
            collection.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def test_audit_checks_every_fixture_twice_without_calls_or_mutation(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            self._write_fixture(root, "01", _collection())
            self._write_fixture(root, "02", _eligible_collection())
            result, rows = evidence_gap_audit.evaluate_collections(
                root,
                expected_count=2,
            )
        self.assertTrue(result["passed"])
        self.assertEqual(result["executed_call_count"], 0)
        self.assertEqual(result["input_mutation_count"], 0)
        self.assertEqual(len(rows), 2)
        self.assertFalse(result["production_tool_calls_authorized"])

    def test_empty_or_partial_fixture_set_fails_closed(self):
        with TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaisesRegex(evidence_gap_audit.EvidenceGapAuditError, "no validated"):
                evidence_gap_audit.evaluate_collections(root)
            self._write_fixture(root, "01", _collection())
            with self.assertRaisesRegex(evidence_gap_audit.EvidenceGapAuditError, "expected exactly 2"):
                evidence_gap_audit.evaluate_collections(root, expected_count=2)

    def test_writer_refuses_to_replace_a_previous_audit(self):
        with TemporaryDirectory() as temp:
            output = Path(temp) / "audit"
            output.mkdir()
            with self.assertRaisesRegex(evidence_gap_audit.EvidenceGapAuditError, "refusing to overwrite"):
                evidence_gap_audit.write_audit(output, {}, [])


if __name__ == "__main__":
    unittest.main()
