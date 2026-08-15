"""One weight profile, decided before retrieval, used by everything after.

A user who disagrees with the auto-detected profile can override it. That
override used to be applied by the worker to the *returned* SourceCollection —
after retrieval had already finished. Scoring saw the corrected profile;
retrieval never did.

The gap is not cosmetic, because retrieval branches on the profile. The
biomedical path runs a PubMed MeSH expansion no other profile runs, so
correcting a misdetected topic to "biomedical" produced biomedical weights
applied to sources gathered as industrial — the search the correction existed
to trigger had already been skipped.

These pin the order rather than the value: the profile has to be known before
the first search, and the same one has to come back out.
"""

from __future__ import annotations

import unittest
import warnings
from datetime import date

from academic_agent.evidence import _WEIGHT_PROFILES
from academic_agent.source_pipeline import _detect_weight_profile, collect_source_collection

from tests.test_source_pipeline import (
    MatchingCrossref,
    _NullArXiv,
    _NullLens,
    _NullOpenAlex,
    _NullPubMed,
    _NullS2,
    fake_search,
)

#: Detects as industrial, which is what makes it useful here: any biomedical
#: behaviour observed under this topic came from the override, not the words.
_INDUSTRIAL_TOPIC = "Test commercialization topic"


class _RecordingPubMed(_NullPubMed):
    """Records whether the MeSH expansion was reached."""

    def __init__(self) -> None:
        self.mesh_calls = 0

    def get_mesh_terms(self, *args, **kwargs) -> list:
        self.mesh_calls += 1
        return []


def _collect(**overrides):
    kwargs = dict(
        searcher=fake_search,
        crossref=MatchingCrossref(),
        openalex=_NullOpenAlex(),
        s2=_NullS2(),
        pubmed=_NullPubMed(),
        arxiv=_NullArXiv(),
        lens=_NullLens(),
        url_checker=lambda url: (True, ""),
        minimum_sources=3,
        maximum_sources=3,
        accessed_date=date(2026, 6, 30),
    )
    kwargs.update(overrides)
    return collect_source_collection(_INDUSTRIAL_TOPIC, **kwargs)


class ProfileReachesRetrievalTests(unittest.TestCase):

    def test_the_topic_alone_detects_as_industrial(self):
        """The premise every other test here rests on. Without this, a
        biomedical result below could be the topic rather than the override."""
        self.assertEqual(_detect_weight_profile(_INDUSTRIAL_TOPIC), "industrial")

    def test_an_override_reaches_the_biomedical_search_branch(self):
        """The regression, stated as behaviour rather than as a field value.

        MeSH expansion runs only for the biomedical profile. Asserting on
        collection.weight_profile alone would have passed against the old code
        too — that field was being set correctly, just too late to matter.
        """
        pubmed = _RecordingPubMed()
        _collect(pubmed=pubmed, weight_profile="biomedical")
        self.assertGreater(pubmed.mesh_calls, 0)

    def test_without_the_override_that_branch_is_not_reached(self):
        """The other half. A test that only checks the branch runs would pass
        if it always ran."""
        pubmed = _RecordingPubMed()
        _collect(pubmed=pubmed)
        self.assertEqual(pubmed.mesh_calls, 0)

    def test_the_collection_carries_the_profile_it_retrieved_under(self):
        """Retrieval and scoring must not be able to disagree: whatever drove
        the search is what the scorer is handed."""
        collection = _collect(weight_profile="biomedical")
        self.assertEqual(collection.weight_profile, "biomedical")

    def test_no_override_still_detects_from_the_topic(self):
        self.assertEqual(_collect().weight_profile, "industrial")

    def test_every_known_profile_is_accepted(self):
        for name in sorted(_WEIGHT_PROFILES):
            with self.subTest(profile=name):
                self.assertEqual(_collect(weight_profile=name).weight_profile, name)


class UnknownProfileTests(unittest.TestCase):
    """A typo must not look like a working override.

    The weights lookup defaults an unrecognised name to industrial without
    complaint, so accepting one here would score against a rubric nobody chose
    while the run reported the name that was asked for.
    """

    def test_an_unknown_profile_warns_and_falls_back_to_detection(self):
        with self.assertWarnsRegex(UserWarning, "unknown weight_profile"):
            collection = _collect(weight_profile="biomedcial")
        self.assertEqual(collection.weight_profile, "industrial")

    def test_the_warning_names_the_profiles_that_would_have_worked(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _collect(weight_profile="bio")
        self.assertIn("biomedical", str(caught[0].message))


class WorkerPassesItBeforeRetrievalTests(unittest.TestCase):
    """The seam. The value was always computed; what broke was where it went.

    Asserted at the call rather than on the result, because the defect was
    precisely a correct value applied after the thing it should have decided.
    """

    def _run_worker_with(self, weight_profile: str | None):
        """Drive main() as far as the retrieval call, then stop it.

        Everything after retrieval is a six-agent LLM run, so the capture
        raises: what is under test is the argument, and letting the worker fail
        past that point exercises its own error path rather than costing a run.
        """
        import sys
        from pathlib import Path
        from tempfile import TemporaryDirectory
        from unittest import mock

        from academic_agent import pipeline_worker, run_output, source_pipeline

        seen: dict = {}

        def _capture(topic, **kwargs):
            seen.update(kwargs)
            raise RuntimeError("stop here; the rest of the run costs money")

        argv = ["pipeline_worker", "run-id", "a topic"]
        if weight_profile is not None:
            argv += ["--weight-profile", weight_profile]

        with TemporaryDirectory() as tmp:
            with mock.patch.object(source_pipeline, "collect_source_collection", _capture), \
                    mock.patch.object(run_output, "DEFAULT_OUTPUT_ROOT", Path(tmp)), \
                    mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(sys, "stderr", mock.Mock()):
                with self.assertRaises(SystemExit):
                    pipeline_worker.main()
        return seen

    def test_the_chosen_profile_is_an_argument_to_retrieval(self):
        self.assertEqual(
            self._run_worker_with("biomedical").get("weight_profile"), "biomedical")

    def test_the_auto_label_is_not_passed_through_as_a_profile_name(self):
        """"Auto (detect from topic)" is the dropdown's wording for "no
        preference". Forwarded as-is it is an unknown profile, which now warns
        on every single auto run."""
        self.assertIsNone(
            self._run_worker_with("Auto (detect from topic)").get("weight_profile"))

    def test_no_profile_means_none(self):
        self.assertIsNone(self._run_worker_with(None).get("weight_profile"))


if __name__ == "__main__":
    unittest.main()
