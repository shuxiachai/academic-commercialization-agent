"""A user confirms the planner's reading of a topic before a run searches it.

The planner once renamed "hyperloop" and drifted on vertical farming; each
time the run spent all its stages, and a daily run, on off-topic sources.
These pin the preview endpoint, the confirmed plan's bounds, and that the
confirmed plan is what retrieval actually searches.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from academic_agent.checkpoint_runtime import retrieval_identity
from academic_agent.language import TopicSearchPlan
from academic_agent.run_spec import RUN_SPEC_FILENAME, RunSpec, SearchPlan
from academic_agent.source_clients import SourceCollectionError
from api import access, plan_preview, runs
from api.main import app
from tests.test_weight_profile_chain import _collect

_PLAN = {
    "search_topic": "hyperloop transportation system",
    "aliases": ["vacuum tube maglev train"],
    "components": [],
}


class SearchPlanBoundsTests(unittest.TestCase):
    def test_whitespace_is_collapsed(self):
        plan = SearchPlan(search_topic="  hyperloop \n transport ", aliases=[" maglev   train "])
        self.assertEqual(plan.search_topic, "hyperloop transport")
        self.assertEqual(plan.aliases, ("maglev train",))

    def test_phrases_outside_the_planner_bounds_are_rejected(self):
        for bad in (
            {"search_topic": "ab"},
            {"search_topic": "x" * 201},
            {"search_topic": " ".join(["word"] * 25)},
            {"search_topic": "hyperloop", "aliases": ["a", "b", "c"]},
            {"search_topic": "hyperloop", "aliases": ["hyperloop"]},
            {"search_topic": "hyperloop", "unexpected": "field"},
        ):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                SearchPlan(**bad)

    def test_one_component_is_dropped_like_the_planner_drops_it(self):
        self.assertEqual(SearchPlan(search_topic="hyperloop", components=["maglev"]).components, ())

    def test_a_plan_is_part_of_the_retrieval_identity(self):
        from datetime import date
        identity = lambda spec: retrieval_identity(spec, revision="r", as_of_date=date(2026, 10, 21)).input_sha256  # noqa: E731
        self.assertNotEqual(
            identity(RunSpec(topic="hyperloop")),
            identity(RunSpec(topic="hyperloop", search_plan=SearchPlan(**_PLAN))),
        )


def _searched(**overrides) -> tuple[str, list[str]]:
    """What retrieval searched: from the collection, or from the shortage
    diagnostics when the fixture sources do not match that phrase."""
    try:
        collection = _collect(**overrides)
    except SourceCollectionError as exc:
        return exc.diagnostics["search_topic"], exc.diagnostics["aliases"]
    return collection.topic, collection.search_aliases


class RetrievalSearchesTheConfirmedPlanTests(unittest.TestCase):
    def test_the_planner_is_not_called_again(self):
        with patch("academic_agent.language.plan_topic_search", side_effect=AssertionError("planned twice")):
            searched = _searched(search_plan=SearchPlan(**_PLAN))
        self.assertEqual(searched, ("hyperloop transportation system", ["vacuum tube maglev train"]))

    def test_a_requested_assessment_is_still_left_out_of_the_search(self):
        plan = SearchPlan(search_topic="hyperloop commercial viability")
        with patch("academic_agent.language.plan_topic_search", side_effect=AssertionError("planned twice")):
            self.assertEqual(_searched(search_plan=plan)[0], "hyperloop")

    def test_without_a_plan_the_worker_still_plans(self):
        planned = TopicSearchPlan(search_topic="planner reading of the topic")
        with patch("academic_agent.language.plan_topic_search", return_value=planned) as planner:
            searched = _searched()
        planner.assert_called_once()
        self.assertEqual(searched[0], "planner reading of the topic")

    def test_the_worker_passes_the_spec_plan_to_retrieval(self):
        from academic_agent import pipeline_worker, run_output, source_pipeline

        seen: dict = {}

        def _capture(topic, **kwargs):
            seen.update(kwargs)
            raise RuntimeError("stop here; the rest of the run costs money")

        with TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-id"
            RunSpec(topic="hyperloop", search_plan=SearchPlan(**_PLAN)).save(run_dir)
            argv = ["pipeline_worker", "run-id", "hyperloop", "--run-spec", str(run_dir / RUN_SPEC_FILENAME)]
            with mock.patch.object(source_pipeline, "collect_source_collection", _capture), \
                    mock.patch.object(run_output, "DEFAULT_OUTPUT_ROOT", Path(tmp)), \
                    mock.patch.object(sys, "argv", argv), \
                    mock.patch.object(sys, "stderr", mock.Mock()):
                with self.assertRaises(SystemExit):
                    pipeline_worker.main()
        self.assertEqual(seen.get("search_plan"), SearchPlan(**_PLAN))


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for patcher in (
            patch.object(runs, "DEFAULT_OUTPUT_ROOT", self.tmp),
            patch.object(runs, "DAILY_CAP", 0),
            patch.object(access, "ACCESS_CODE", None),
            patch.object(access, "ACCESS_CODES", "for-alice,for-bob"),
            patch.object(access, "ADMIN_CODE", None),
            patch.object(plan_preview, "DAILY_LIMIT", 2),
            patch.object(plan_preview, "_counts", {}),
            patch.object(plan_preview, "plan_topic_search", return_value=TopicSearchPlan(
                search_topic="hyperloop transportation system", aliases=("vacuum tube maglev train",))),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        runs._registry.clear()
        self.addCleanup(runs._registry.clear)
        self.client = TestClient(app)

    def _preview(self, code: str | None = "for-alice", topic: str = "帮我评估 hyperloop 的商业潜力"):
        headers = {"X-Access-Code": code} if code else {}
        return self.client.post("/api/plan", json={"topic": topic}, headers=headers)

    def test_the_access_check_advertises_previews(self):
        r = self.client.get("/api/access/check", headers={"X-Access-Code": "for-alice"})
        self.assertEqual(r.json(), {"ok": True, "plan_preview": True, "daily_quota": False})

    def test_a_preview_returns_the_planner_reading(self):
        r = self._preview()
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(r.json(), {"resolved": True, **_PLAN})

    def test_an_unresolved_topic_says_so(self):
        with patch.object(plan_preview, "plan_topic_search",
                          return_value=TopicSearchPlan(search_topic="", resolved=False)):
            self.assertEqual(self._preview().json()["resolved"], False)

    def test_previews_need_an_access_code(self):
        self.assertEqual(self._preview(code=None).status_code, 401)

    def test_each_code_has_its_own_daily_cap(self):
        self.assertEqual([self._preview().status_code for _ in range(2)], [200, 200])
        limited = self._preview()
        self.assertEqual(limited.status_code, 429)
        self.assertEqual(limited.headers["X-Error-Code"], "plan_preview_limit")
        self.assertEqual(self._preview(code="for-bob").status_code, 200)

    def test_previews_do_not_take_a_daily_run(self):
        with patch.object(runs, "DAILY_CAP", 1):
            self.assertEqual(self._preview().status_code, 200)
            self.assertEqual(runs._daily_counts.get(access.owner_id("for-alice"), 0), 0)

    def test_a_zero_limit_turns_previews_off(self):
        with patch.object(plan_preview, "DAILY_LIMIT", 0):
            self.assertEqual(self._preview().status_code, 404)
            r = self.client.get("/api/access/check", headers={"X-Access-Code": "for-alice"})
            self.assertEqual(r.json()["plan_preview"], False)

    @patch("api.runs.subprocess.Popen")
    def test_a_confirmed_plan_is_frozen_into_the_run_spec(self, mock_popen):
        proc = MagicMock()
        proc.poll.return_value = None
        mock_popen.return_value = proc
        r = self.client.post("/api/runs", headers={"X-Access-Code": "for-alice"},
                             json={"topic": "帮我评估 hyperloop 的商业潜力", "search_plan": _PLAN})
        self.assertEqual(r.status_code, 202, r.text)
        self.assertEqual(RunSpec.load(self.tmp / r.json()["run_id"]).search_plan, SearchPlan(**_PLAN))

    @patch("api.runs.subprocess.Popen")
    def test_a_malformed_plan_is_rejected_before_a_run_starts(self, mock_popen):
        r = self.client.post("/api/runs", headers={"X-Access-Code": "for-alice"},
                             json={"topic": "hyperloop", "search_plan": {"search_topic": "x"}})
        self.assertEqual(r.status_code, 422)
        mock_popen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
