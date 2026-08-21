"""Regression tests for a run that failed with zero patent sources.

Reproduced from run 20260805T055001Z-3c1c332da9, submitted via PDF upload:

    "Flexible piezoresistive electronic skin sensor based on carbon nanotube/PDMS
     micro-pyramid structure, with a sensitivity of 47.3 kPa, for tactile
     perception in industrial robots and medical rehabilitation."

Three defects lined up into a deadlock:

  1. _topic_domain_keywords read the clause after the first " for " as an
     application domain, yielding {industrial, medical, rehabilitation, robots}
  2. the patent domain applied those as a hard inclusion filter, and patent
     titles claim inventions rather than applications — so every relevant hit
     scored -1 and was dropped, including by the min_keep fallback
  3. with an empty source pool, the guardrail still demanded that each finding
     cite a source, which no output could satisfy; both retries produced the
     same result and the entire run failed

The searches themselves were fine. "Electronic skin, preparation method and use
thereof" was retrieved and then discarded.
"""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from academic_agent.evidence import (
    EvidenceFinding,
    EvidenceReport,
    EvidenceSource,
    make_scoring_guardrail,
    validate_evidence_report,
)
from academic_agent.source_pipeline import _filter_by_relevance, _topic_domain_keywords

class _Output:
    """Minimal stand-in for a CrewAI TaskOutput."""

    def __init__(self, raw: str):
        self.raw = raw
        self.pydantic = None


_UPLOADED_PAPER_TOPIC = (
    "Flexible piezoresistive electronic skin sensor based on carbon nanotube/PDMS "
    "micro-pyramid structure, with a sensitivity of 47.3 kPa, for tactile perception "
    "in industrial robots and medical rehabilitation."
)

# Titles actually returned by the patent search for that run, all rejected.
_REAL_PATENT_TITLES = [
    "Electronic skin, preparation method and use thereof",
    "Flexible bionic electronic skin and preparation method thereof",
    "WO2022040177A1 - SOFT BIOSENSORS BASED ON ELECTRONIC SKIN",
]


def _patent(idx: int, title: str) -> EvidenceSource:
    return EvidenceSource(
        source_id=f"P{idx}",
        title=title,
        url=f"https://patents.google.com/patent/EXAMPLE{idx}/en",
        publisher="Google Patents",
        accessed_date=date.today(),
        source_type="patent",
        credibility_tier="medium",
        credibility_reason="Patent record retrieved from Google Patents.",
        evidence_summary=(
            f"{title}. A patent covering flexible pressure sensing structures "
            "built on micro-structured elastomer substrates for tactile input."
        ),
    )


def _academic_stub() -> EvidenceSource:
    """One valid academic source — SourceCollection requires at least one."""
    return EvidenceSource(
        source_id="A1",
        title="A study of solid state battery electrolytes",
        url="https://records.test-domain.org/a1",
        publisher="Journal of Testing",
        accessed_date=date.today(),
        source_type="academic_paper",
        evidence_summary=(
            "Reports ionic conductivity measurements for a sulfide electrolyte "
            "across a range of operating temperatures and cycling conditions."
        ),
    )


# ---------------------------------------------------------------------------
# Defect 1 — domain keyword extraction on specification-style topics
# ---------------------------------------------------------------------------

class DomainKeywordScopeTests(unittest.TestCase):

    def test_short_topic_still_yields_domain_keywords(self):
        """The feature must keep working for the phrasing it was built for."""
        self.assertEqual(
            _topic_domain_keywords("large language models in clinical medicine"),
            frozenset({"clinical", "medicine"}),
        )

    def test_benchmark_topics_unaffected(self):
        for topic, expected in [
            ("solid-state batteries for electric vehicles", {"electric", "vehicles"}),
            ("CAR-T cell therapy for blood cancers", {"blood", "cancers"}),
            ("cultivated meat for food industry", {"food", "industry"}),
            ("quantum computing for drug discovery", {"discovery", "drug"}),
        ]:
            with self.subTest(topic=topic):
                self.assertEqual(_topic_domain_keywords(topic), frozenset(expected))

    def test_specification_style_topic_extracts_nothing(self):
        """A long uploaded-paper topic must disable the filter, not misuse it."""
        self.assertEqual(_topic_domain_keywords(_UPLOADED_PAPER_TOPIC), frozenset())

    def test_topic_without_preposition_extracts_nothing(self):
        self.assertEqual(
            _topic_domain_keywords("room temperature ambient pressure superconductors"),
            frozenset(),
        )

    def test_too_many_extracted_terms_disables_the_filter(self):
        """Several clauses swept up means the split found usage, not a field."""
        topic = "novel catalyst for hydrogen production in refining chemical steel cement plants"
        self.assertEqual(_topic_domain_keywords(topic), frozenset())


# ---------------------------------------------------------------------------
# Defect 2 — the patent domain must not apply a hard domain filter
# ---------------------------------------------------------------------------

class PatentRelevanceFilterTests(unittest.TestCase):

    def test_real_rejected_patents_are_kept(self):
        """The exact titles the failing run discarded must now survive."""
        sources = [_patent(i, t) for i, t in enumerate(_REAL_PATENT_TITLES, 1)]
        kept, _removed = _filter_by_relevance(
            sources, _UPLOADED_PAPER_TOPIC, min_score=1, min_keep=1,
            skip_domain_filter=True,
        )
        self.assertEqual(len(kept), len(sources))

    def test_domain_filter_would_have_dropped_them_all(self):
        """Documents why skip_domain_filter is required rather than incidental.

        Uses a short topic so the length guard does not mask the effect — this
        asserts the filter's behaviour, not the topic-length heuristic.
        """
        short_topic = "pressure sensors for industrial robots"
        sources = [_patent(i, t) for i, t in enumerate(_REAL_PATENT_TITLES, 1)]

        with_filter, _ = _filter_by_relevance(
            sources, short_topic, min_score=1, min_keep=1, skip_domain_filter=False)
        without_filter, _ = _filter_by_relevance(
            sources, short_topic, min_score=1, min_keep=1, skip_domain_filter=True)

        self.assertEqual(len(with_filter), 0)
        self.assertEqual(len(without_filter), len(sources))

    def test_off_topic_patents_still_scored_out(self):
        """Dropping the domain filter must not disable relevance scoring."""
        junk = [
            _patent(9, "Method for brewing fermented barley beverages"),
            _patent(8, "Apparatus for harvesting sugarcane in tropical climates"),
        ]
        kept, removed = _filter_by_relevance(
            junk, "flexible piezoresistive electronic skin sensor",
            min_score=2, min_keep=0, skip_domain_filter=True)
        self.assertEqual(len(kept), 0)
        self.assertEqual(len(removed), 2)


# ---------------------------------------------------------------------------
# Defect 3 — an empty source pool must not deadlock the guardrail
# ---------------------------------------------------------------------------

def _report(sources: list[EvidenceSource], source_ids: list[str]) -> EvidenceReport:
    return EvidenceReport(
        topic="flexible electronic skin sensors",
        scope_summary="Patent landscape review for flexible tactile sensing devices.",
        search_queries=["electronic skin patent"],
        findings=[
            EvidenceFinding(
                finding_id="PF1",
                category="white_space",
                claim="No granted patent was found covering this micro-pyramid geometry.",
                claim_type="analyst_inference",
                source_ids=source_ids,
                confidence="low",
                commercial_implication="Possible freedom to operate, pending formal FTO analysis.",
                limitations="Based on a limited search, not an exhaustive registry review.",
            )
        ],
        sources=sources,
        limitations=["Patent search returned no usable records."],
    )


def _citation_errors(report: EvidenceReport) -> list[str]:
    return [e for e in validate_evidence_report(report, "P") if "no source_ids" in e]


class EmptySourcePoolTests(unittest.TestCase):

    def test_uncited_finding_allowed_when_no_sources_exist(self):
        """'No patent evidence found' is a result, not a validation failure.

        With an empty pool the rule is unsatisfiable, so enforcing it turns an
        empty domain into a failed run — which is what happened.
        """
        self.assertEqual(_citation_errors(_report([], [])), [])

    def test_citation_still_required_when_sources_exist(self):
        """The relaxation is conditional; it must not weaken the normal path."""
        src = _patent(1, "Electronic skin, preparation method and use thereof")
        self.assertEqual(len(_citation_errors(_report([src], []))), 1)

    def test_cited_finding_passes_normally(self):
        src = _patent(1, "Electronic skin, preparation method and use thereof")
        self.assertEqual(_citation_errors(_report([src], ["P1"])), [])

    def test_hallucinated_id_still_rejected_with_empty_pool(self):
        """Relaxing the citation rule must not allow invented references."""
        errors = validate_evidence_report(_report([], ["P1"]), "P")
        self.assertTrue(any("unknown sources" in e for e in errors))


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Defect 4 — a single unusable search result must not abort the run
# ---------------------------------------------------------------------------

class WebSourceValidationTests(unittest.TestCase):
    """_web_source rejects by returning (None, reason); it must never raise.

    Google Patents serves "No information is available for this page." for some
    records — 42 characters against the model's 60-character minimum. That
    ValidationError propagated out of collect_source_collection and killed the
    whole run, which only surfaced once the patent domain began requesting a
    full budget rather than three results.
    """

    def _result(self, snippet: str) -> dict:
        return {
            "title": "US1234567B2 - Flexible graphene electrode",
            "link": "https://patents.google.com/patent/US1234567B2/en",
            "snippet": snippet,
        }

    def test_placeholder_snippet_yields_a_usable_source(self):
        """The exact payload that aborted a run.

        Google Patents returns this for records with no indexed abstract. It is
        42 characters, over _safe_summary's old floor of 20 but under the
        model's 60, so it was passed through and then rejected by validation —
        taking the whole run with it. It must now produce a valid source.
        """
        from datetime import date
        from academic_agent.source_pipeline import _web_source

        source, reason = _web_source(
            self._result("No information is available for this page."),
            "P1", "patent", date.today(), lambda url: (True, ""),
        )
        self.assertIsNotNone(source, f"rejected with: {reason}")
        self.assertGreaterEqual(len(source.evidence_summary), 60)

    def test_validation_failure_returns_reason_instead_of_raising(self):
        """Even so, construction must not be able to abort the caller.

        _web_source signals rejection with (None, reason) everywhere else; the
        constructor is wrapped so an unforeseen constraint cannot propagate.
        """
        from datetime import date
        from unittest.mock import patch
        from pydantic import ValidationError
        from academic_agent.source_pipeline import _web_source

        err = ValidationError.from_exception_data(
            "EvidenceSource",
            [{"type": "value_error", "loc": ("evidence_summary",),
              "input": "x", "ctx": {"error": ValueError("too short")}}],
        )
        with patch("academic_agent.source_pipeline.EvidenceSource", side_effect=err):
            source, reason = _web_source(
                self._result("A sufficiently long and perfectly ordinary patent "
                             "abstract describing a flexible graphene electrode."),
                "P1", "patent", date.today(), lambda url: (True, ""),
            )
        self.assertIsNone(source)
        self.assertIn("evidence_summary", reason)

    def test_summary_floor_matches_the_model(self):
        """_safe_summary must clear EvidenceSource's floor, not a lower one.

        The two thresholds disagreed: _safe_summary accepted anything over
        _ABSTRACT_MIN_CHARS (20) while the model demands 60 for Latin text, so
        every snippet of length 20-59 passed here and failed validation.
        """
        from academic_agent.source_pipeline import _safe_summary

        for snippet, title in [
            ("No information is available for this page.", "Graphene electrode"),
            ("Short.", "X"),                       # tiny title too
            ("", "US1234567B2 - Flexible graphene electrode"),
        ]:
            with self.subTest(snippet=snippet[:24]):
                self.assertGreaterEqual(len(_safe_summary(snippet, title)), 60)

    def test_cjk_summary_keeps_the_lower_floor(self):
        """CJK is denser, so the model allows 20 — do not over-pad it."""
        from academic_agent.source_pipeline import _safe_summary

        cjk = "柔性石墨烯电极用于可穿戴传感器件的制备方法与应用。"
        self.assertEqual(_safe_summary(cjk, "石墨烯"), cjk)

    def test_usable_snippet_still_accepted(self):
        from datetime import date
        from academic_agent.source_pipeline import _web_source

        snippet = (
            "A flexible graphene-based electrode structure for wearable sensing "
            "devices, comprising a patterned conductive layer on an elastomer film."
        )
        source, reason = _web_source(
            self._result(snippet), "P1", "patent", date.today(),
            lambda url: (True, ""),
        )
        self.assertIsNotNone(source)
        self.assertEqual(reason, "")


# ---------------------------------------------------------------------------
# Defect 5 — an empty domain must not deadlock the scoring guardrail either
# ---------------------------------------------------------------------------

class ScoringWithAnEmptyDomainTests(unittest.TestCase):
    """The same deadlock, one task later.

    Defect 3 above fixed it for the evidence tasks; the scoring model kept
    min_length=1 on every *_source_ids field. "Uranium-235 production and
    storage" retrieved zero patents, so the scorer was asked to cite a patent
    that does not exist. It cannot, so it failed, retried twice, and the run
    was lost after the other five agents had already succeeded.
    """

    def _score(self, **overrides) -> str:
        import json
        payload = {
            "trl_score": 40, "trl_rationale": "Laboratory scale only, per A1.",
            "trl_source_ids": ["A1"],
            "mrl_score": 30, "mrl_rationale": "No production process described.",
            "mrl_source_ids": ["A1"],
            "patent_strength": 30, "patent_rationale": "No patent records retrieved.",
            "patent_source_ids": [],
            "market_accessibility": 20, "market_rationale": "Forecasts only, no products.",
            "market_source_ids": ["M1"],
            "evidence_confidence": 20,
            "evidence_rationale": "Thin registry across all three domains.",
            "evidence_source_ids": ["A1", "M1"],
            "overall_score": 30.0,
            "scoring_rationale": "Early stage with a thin evidence base.",
            "key_risks": ["No patent coverage found."],
            "key_opportunities": ["White space may exist."],
        }
        payload.update(overrides)
        return json.dumps(payload)

    def test_empty_patent_ids_accepted_when_no_patents_retrieved(self):
        """The exact shape of the failing run: 3 academic, 0 patent, 8 market."""
        guardrail = make_scoring_guardrail(
            known_source_ids=frozenset({"A1", "M1"}),   # no P ids at all
        )
        ok, result = guardrail(_Output(self._score()))
        self.assertTrue(ok, f"rejected with: {result}")

    def test_empty_patent_ids_rejected_when_patents_exist(self):
        """Permissiveness must not become "citations optional"."""
        guardrail = make_scoring_guardrail(
            known_source_ids=frozenset({"A1", "M1", "P1"}),
        )
        ok, result = guardrail(_Output(self._score()))
        self.assertFalse(ok)
        self.assertIn("patent_source_ids", result)

    def test_empty_market_ids_rejected_when_market_sources_exist(self):
        guardrail = make_scoring_guardrail(
            known_source_ids=frozenset({"A1", "M1"}),
        )
        ok, result = guardrail(_Output(self._score(market_source_ids=[])))
        self.assertFalse(ok)
        self.assertIn("market_source_ids", result)

    def test_hallucinated_ids_still_rejected(self):
        """Relaxing the floor must not weaken the phantom-ID check."""
        guardrail = make_scoring_guardrail(
            known_source_ids=frozenset({"A1", "M1"}),
        )
        ok, result = guardrail(_Output(self._score(patent_source_ids=["P9"])))
        self.assertFalse(ok)
        self.assertIn("P9", result)


class EmptyRegistryRubricTests(unittest.TestCase):
    """An empty registry must not be scored as an open landscape.

    "Uranium-235 production and storage" retrieved zero patents and the scorer
    gave patent_strength 4.0/5, reasoning that "the patent landscape appears
    open due to the absence of retrieved patent records". The rubric's top band
    is defined as "few relevant patents, strong early-mover opportunity", so
    that inference followed the instructions as written.

    Nothing retrieved is a fact about the search, not about the world — and for
    export-controlled subjects a blank result correlates with dense IP, not
    sparse IP. These assert the rubric now says so; the scoring itself is a
    model judgement and is checked by the benchmark, not here.
    """

    def _rubric(self) -> str:
        import yaml
        path = Path(__file__).resolve().parent.parent / "src/academic_agent/config/agents.yaml"
        agents = yaml.safe_load(path.read_text(encoding="utf-8"))
        return agents["commercialization_scorer"]["backstory"]

    def test_rubric_caps_the_score_for_an_empty_registry(self):
        text = self._rubric()
        self.assertIn("EMPTY REGISTRY RULE", text)
        self.assertIn("never above 30", text)

    def test_rubric_forbids_calling_it_open(self):
        text = self._rubric()
        for forbidden in ('"open"', '"uncontested"', '"white space"'):
            with self.subTest(word=forbidden):
                self.assertIn(forbidden, text)

    def test_rubric_names_why_retrieval_fails(self):
        """The reason matters: it is why blank does not mean sparse."""
        text = self._rubric()
        self.assertIn("export-controlled", text)


# ---------------------------------------------------------------------------
# Retrieval-backend failure: degrade, but never silently
# ---------------------------------------------------------------------------

class FailedDomainReportingTests(unittest.TestCase):
    """A domain whose backend failed and a domain that found nothing must not
    look the same.

    Losing the market search used to lose the whole run — including academic
    sources already retrieved and validated, the slowest part of the pipeline,
    discarded because a different backend was down. Degrading is better, but
    only if the reason travels with the data: the scoring rubric reads a thin
    market registry as evidence about the technology ("only forecasts -> score
    from academic evidence, typically TRL 2-5"), so an outage would otherwise
    produce a confident, low, and entirely wrong score.
    """

    @staticmethod
    def _collection(**overrides):
        """A minimal valid SourceCollection; only failed_domains varies."""
        from datetime import datetime, UTC

        from academic_agent.source_pipeline import SourceCollection

        base = dict(
            topic="solid state batteries",
            collected_at=datetime.now(UTC),
            academic_sources=[_academic_stub()],
            academic_queries=["q"],
            patent_queries=["q"],
            market_queries=["q"],
        )
        base.update(overrides)
        return SourceCollection(**base)

    def test_a_healthy_run_records_no_failure(self):
        self.assertEqual(self._collection().failed_domains, {})

    def test_scope_warning_reaches_the_report_writer(self):
        """Persisting the warning is not enough if no prompt consumes it."""
        warning = "TOPIC SCOPE -- state which indications are assessed."
        notice = self._collection(scope_warning=warning).crew_inputs()[
            "retrieval_notice"
        ]
        self.assertIn(warning, notice)

    def test_the_report_writer_is_told_which_domain_failed(self):
        inputs = self._collection(
            failed_domains={"market": "Tavily search failed: HTTP 432"},
        ).crew_inputs()
        notice = inputs["retrieval_notice"]
        self.assertIn("RETRIEVAL FAILURE", notice)
        self.assertIn("market", notice)
        self.assertIn("Evidence Limitations", notice)

    def test_the_notice_forbids_reading_absence_as_evidence(self):
        """The specific misreading this exists to prevent."""
        notice = self._collection(
            failed_domains={"patent": "backend down"},
        ).crew_inputs()["retrieval_notice"]
        self.assertIn("not", notice.lower())
        for word in ("empty", "sparse", "undeveloped"):
            self.assertIn(word, notice.lower())

    def test_a_healthy_run_still_permits_reporting_a_genuinely_thin_domain(self):
        """The opposite error: treating every sparse domain as an outage would
        suppress a real finding about an early-stage technology."""
        notice = self._collection().crew_inputs()["retrieval_notice"]
        self.assertIn("searched successfully", notice)
        self.assertIn("finding about the technology", notice)

    def test_notice_is_always_supplied_to_the_report_task(self):
        """Missing key would make CrewAI interpolation fail at runtime, long
        after retrieval, on a run that had already cost real money."""
        for failed in ({}, {"market": "x"}, {"patent": "y", "market": "z"}):
            with self.subTest(failed=sorted(failed)):
                self.assertIn("retrieval_notice", self._collection(
                    failed_domains=failed).crew_inputs())

    def test_report_task_actually_consumes_the_placeholder(self):
        """A crew input nothing references is dead weight, and the notice
        would never reach the reader."""
        import yaml
        from pathlib import Path as _P

        cfg = yaml.safe_load(
            (_P(__file__).resolve().parent.parent
             / "src" / "academic_agent" / "config" / "tasks.yaml").read_text(encoding="utf-8")
        )
        self.assertIn("{retrieval_notice}", cfg["commercialization_report_task"]["description"])


class EmptyAssigneeListMustNotBeReadAsAFinding(unittest.TestCase):
    """The same failure shape as an empty domain, one level down.

    Lens.org is the only source that exposes structured applicant names, and
    it is off by default (LENS_API_KEY unset skips the block entirely). So
    patent_assignees is empty on essentially every run, and the emptiness is
    an artifact of how retrieval works — not a fact about the patents. The
    only thing standing between that artifact and a confident sentence about
    market fragmentation is a rule in the patent task prompt. Deleting the
    rule breaks nothing, fails no test, and produces a plausible report, so
    it needs a test that says out loud why it must stay.
    """

    def _patent_task(self):
        import yaml

        cfg = yaml.safe_load(
            (Path(__file__).resolve().parent.parent
             / "src" / "academic_agent" / "config" / "tasks.yaml").read_text(encoding="utf-8")
        )
        keys = [k for k in cfg if "patent" in k]
        self.assertEqual(len(keys), 1, f"expected one patent task, got {keys}")
        # Collapse whitespace: the block scalar keeps the source line breaks,
        # so a phrase can straddle two lines. What is asserted below is the
        # rule's content, which must not depend on where the YAML wraps.
        return " ".join(cfg[keys[0]]["description"].split())

    def test_rule_states_empty_means_field_absent_not_unassigned(self):
        text = self._patent_task()
        self.assertIn("empty assignee list", text.lower())
        self.assertIn("NOT that the patents are unassigned", text)

    def test_rule_forbids_the_specific_inferences_it_would_invite(self):
        """Naming the wrong conclusions matters more than naming the right
        one: 'assignees unavailable' is a limitation an LLM will happily note
        and then reason past. These three are what it reasons *to*."""
        text = self._patent_task().lower()
        for inference in ("competitive concentration", "market fragmentation", "crowded"):
            with self.subTest(inference=inference):
                self.assertIn(inference, text)
