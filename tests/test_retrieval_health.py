"""Refusals reach the audit, and /api/health/retrieval counts them across runs."""

from __future__ import annotations

import json
import unittest
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest
from fastapi.testclient import TestClient

import academic_agent.source_pipeline as pipeline
from academic_agent.source_clients import (
    ARXIV_RATE_LIMITED,
    OPENALEX_RATE_LIMITED,
    PUBMED_RATE_LIMITED,
    S2_RATE_LIMITED,
    ArxivClient,
    OpenAlexClient,
    PubMedClient,
    SemanticScholarClient,
)
from api import access, retrieval_health, runs
from api.main import app


def _http(code: int) -> HTTPError:
    return HTTPError(url="", code=code, msg="", hdrs=None, fp=None)


class _Ok:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


@pytest.fixture(autouse=True)
def _fresh_semantic_scholar_turn():
    import academic_agent.source_clients as clients
    clients._s2_next_turn = 0.0


@patch("academic_agent.source_clients.time.sleep")
@patch("academic_agent.source_clients.urlopen")
class ClientGiveUpNoteTests(unittest.TestCase):
    def test_semantic_scholar_records_a_refusal_it_cannot_retry_past(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = _http(429)
        client = SemanticScholarClient(timeout=5, retries=1)
        self.assertEqual(client.search("hyperloop"), [])
        self.assertEqual(client.last_error, S2_RATE_LIMITED)

    def test_the_last_429_is_not_followed_by_a_pointless_wait(self, mock_urlopen, mock_sleep):
        mock_urlopen.side_effect = _http(429)
        with patch("academic_agent.source_clients.s2_wait_turn"):  # pacing sleeps too
            SemanticScholarClient(timeout=5, retries=1).search("hyperloop")
        self.assertEqual(mock_sleep.call_count, 1)

    def test_a_refusal_that_a_retry_recovers_from_is_not_recorded(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = [_http(429), _Ok(b'{"data": [{"title": "Paper"}]}')]
        client = SemanticScholarClient(timeout=5, retries=1)
        self.assertEqual(client.search("hyperloop"), [{"title": "Paper"}])
        self.assertIsNone(client.last_error)

    def test_openalex_records_only_the_refusal_it_gives_up_on(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = [_http(429), _Ok(b'{"results": [{"id": "W1"}]}')]
        client = OpenAlexClient(timeout=5, retries=1)
        self.assertEqual(client.search("hyperloop"), [{"id": "W1"}])
        self.assertIsNone(client.last_error)
        mock_urlopen.side_effect = _http(429)
        client.search("hyperloop")
        self.assertEqual(client.last_error, OPENALEX_RATE_LIMITED)

    def test_openalex_records_a_server_error(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = _http(503)
        client = OpenAlexClient(timeout=5, retries=1)
        client.search_recent("hyperloop")
        self.assertEqual(client.last_error, "OpenAlex request failed (HTTP 503)")

    def test_pubmed_records_refusals_and_failures(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = _http(429)
        client = PubMedClient(timeout=5, retries=1)
        self.assertEqual(client.search("hyperloop"), [])
        self.assertEqual(client.last_error, PUBMED_RATE_LIMITED)
        mock_urlopen.side_effect = _http(500)
        client = PubMedClient(timeout=5, retries=1)
        client.search("hyperloop")
        self.assertEqual(client.last_error, "PubMed request failed (HTTP 500)")

    def test_arxiv_records_refusals_and_network_failures(self, mock_urlopen, _sleep):
        mock_urlopen.side_effect = _http(429)
        client = ArxivClient(timeout=5, retries=1)
        self.assertEqual(client.search("hyperloop"), [])
        self.assertEqual(client.last_error, ARXIV_RATE_LIMITED)
        mock_urlopen.side_effect = URLError("network down")
        client = ArxivClient(timeout=5, retries=1)
        client.search("hyperloop")
        self.assertTrue(client.last_error.startswith("arXiv request failed"))


class _Lane:
    def __init__(self, error: str | None = None):
        self.last_error = error

    def search(self, *args, **kwargs):
        return []

    search_recent = search_by_topic = fetch_works_by_ids = search

    def fetch_referenced_works(self, *args, **kwargs):
        return []

    def get_mesh_terms(self, *args, **kwargs):
        return []


class AuditNoteTests(unittest.TestCase):
    def _audits(self, *, maximum_sources: int, **errors: str):
        _, audits = pipeline._collect_academic_primary(
            "Hyperloop transportation system",
            _Lane(errors.get("openalex")), _Lane(errors.get("s2")), date(2026, 10, 21),
            maximum_sources=maximum_sources,
            pubmed=_Lane(errors.get("pubmed")), arxiv=_Lane(errors.get("arxiv")),
            user_topic="hyperloop",
        )
        return {a.query.split("]")[0] + "]": a for a in audits}

    def test_a_refusal_gets_a_row_even_when_no_slot_was_open(self):
        rows = self._audits(maximum_sources=0, s2=S2_RATE_LIMITED, arxiv=ARXIV_RATE_LIMITED)
        self.assertEqual(rows["[S2]"].rejected_reasons, [S2_RATE_LIMITED])
        self.assertEqual(rows["[S2]"].result_count, 0)
        self.assertEqual(rows["[arXiv]"].rejected_reasons, [ARXIV_RATE_LIMITED])
        self.assertNotIn("[PubMed]", rows)

    def test_a_refusal_is_noted_on_the_row_that_was_searched(self):
        rows = self._audits(maximum_sources=8, pubmed=PUBMED_RATE_LIMITED, openalex=OPENALEX_RATE_LIMITED)
        self.assertEqual(rows["[PubMed]"].rejected_reasons, [PUBMED_RATE_LIMITED])
        self.assertIn(OPENALEX_RATE_LIMITED, rows["[OA-Cited]"].rejected_reasons)
        self.assertEqual(rows["[S2]"].rejected_reasons, [])

    def test_the_notes_count_as_failures(self):
        for note in (S2_RATE_LIMITED, PUBMED_RATE_LIMITED, ARXIV_RATE_LIMITED, OPENALEX_RATE_LIMITED,
                     "OpenAlex request failed (HTTP 503)", "request failed: timed out"):
            self.assertTrue(retrieval_health._FAILURE_NOTE.match(note), note)


def _row(query: str, count: int = 0, *reasons: str, domain: str = "academic") -> dict:
    return {"domain": domain, "query": query, "result_count": count,
            "accepted_source_ids": [], "rejected_reasons": list(reasons)}


class SummarizeTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        self.dirs: list[Path] = []

    def _run(self, record: dict | str | None, name: str = "validated_sources.json") -> Path:
        run_dir = self.root / f"20261021T00{len(self.dirs):04d}Z-ab"
        run_dir.mkdir()
        if record is not None:
            text = record if isinstance(record, str) else json.dumps(record)
            (run_dir / name).write_text(text, encoding="utf-8")
        self.dirs.insert(0, run_dir)  # newest first
        return run_dir

    def _summary(self, window: int = 20) -> dict:
        return retrieval_health.summarize(self.dirs, window=window)

    def _lanes(self, summary: dict) -> dict[str, tuple[int, int, int]]:
        return {lane["lane"]: (lane["observed_runs"], lane["empty_runs"], lane["failed_runs"])
                for lane in summary["lanes"]}

    def test_counts_runs_per_lane_and_flags_failing_and_empty_lanes(self):
        for _ in range(3):
            self._run({"audit": [
                _row("[OA-Cited] hyperloop", 20),
                _row("[OA-Syn] maglev train", 5),
                _row("[OA-Syn] vacuum tube transport", 0),
                _row("[S2] hyperloop", 0, S2_RATE_LIMITED),
                _row("[OA-Recent] hyperloop", 0),
                _row("[Relevance-Filter]", 0, "dropped A3"),
            ]})
        summary = self._summary()
        lanes = self._lanes(summary)
        self.assertEqual(summary["runs_examined"], 3)
        self.assertEqual(lanes["OA-Cited"], (3, 0, 0))
        self.assertEqual(lanes["OA-Syn"], (3, 0, 0))  # one synonym found papers
        self.assertEqual(lanes["S2"], (3, 3, 3))
        self.assertNotIn("Relevance-Filter", lanes)
        self.assertEqual(summary["failing"], ["S2"])
        self.assertEqual(summary["mostly_empty"], ["OA-Recent"])

    def test_too_few_observations_are_not_flagged(self):
        for _ in range(2):
            self._run({"audit": [_row("[S2] hyperloop", 0, S2_RATE_LIMITED)]})
        self.assertEqual(self._summary()["failing"], [])

    def test_older_labels_and_web_rows_share_lanes(self):
        self._run({"audit": [
            _row("[SemanticScholar] hyperloop", 0),
            _row("[OpenAlex-Recent 2023+] hyperloop", 4),
            _row("[OA-Cluster:T10021] hyperloop", 3),
            _row("[Serper-Fallback]", 0, "Tavily search failed for 'x' after 3 attempts: boom"),
            _row("hyperloop pilot company 2026", 9, domain="market"),
        ], "failed_domains": {"patent": "Serper search failed for 'y'"}})
        lanes = self._lanes(self._summary())
        self.assertEqual(lanes["S2"], (1, 1, 0))
        self.assertEqual(lanes["OA-Recent"], (1, 0, 0))
        self.assertEqual(lanes["OA-Cluster"], (1, 0, 0))
        self.assertEqual(lanes["academic web search"], (1, 1, 1))
        self.assertEqual(lanes["market web search"], (1, 0, 0))
        self.assertEqual(lanes["patent web search"], (1, 1, 1))

    def test_a_paper_title_holding_the_words_is_not_a_failure(self):
        self._run({"audit": [_row(
            "[OA-Cited] hyperloop", 3,
            "OpenAlex title not relevant to topic: 'Why the request failed in court'",
        )]})
        self.assertEqual(self._lanes(self._summary())["OA-Cited"], (1, 0, 0))

    def test_reads_the_diagnostics_of_a_run_short_of_sources(self):
        self._run({"stage": "academic", "audit": [_row("[OA-Cited] hyperloop", 0, OPENALEX_RATE_LIMITED)]},
                  name="retrieval_diagnostics.json")
        self.assertEqual(self._lanes(self._summary())["OA-Cited"], (1, 1, 1))

    def test_window_counts_only_runs_with_an_audit(self):
        self._run({"audit": [_row("[S2] old", 0)]})
        self._run({"audit": [_row("[OA-Cited] new", 4)]})
        self._run(None)            # still running
        self._run("{not json")     # unreadable
        summary = self._summary(window=1)
        self.assertEqual(summary["runs_examined"], 1)
        self.assertEqual(list(self._lanes(summary)), ["OA-Cited"])

    def test_the_summary_names_no_topic_or_run(self):
        self._run({"audit": [_row("[S2] secret topic", 0, S2_RATE_LIMITED)]})
        text = json.dumps(self._summary())
        self.assertNotIn("secret", text)
        self.assertNotIn("20261021", text)


class EndpointTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        for patcher in (
            patch.object(runs, "DEFAULT_OUTPUT_ROOT", self.root),
            patch.object(access, "ACCESS_CODE", None),
            patch.object(access, "ACCESS_CODES", "for-alice,for-bob"),
            patch.object(access, "ADMIN_CODE", "for-admin"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(app)
        self._run("20261021T010000Z-aa", "for-alice", _row("[S2] alice topic", 0, S2_RATE_LIMITED))
        self._run("20261021T020000Z-bb", "for-bob", _row("[OA-Cited] bob topic", 7))

    def _run(self, run_id: str, code: str, row: dict) -> None:
        run_dir = self.root / run_id
        run_dir.mkdir()
        (run_dir / ".owner").write_text(access.owner_id(code), encoding="utf-8")
        (run_dir / "validated_sources.json").write_text(json.dumps({"audit": [row]}), encoding="utf-8")

    def _lanes(self, code: str) -> list[str]:
        r = self.client.get("/api/health/retrieval", headers={"X-Access-Code": code})
        self.assertEqual(r.status_code, 200)
        return [lane["lane"] for lane in r.json()["lanes"]]

    def test_requires_an_access_code(self):
        self.assertEqual(self.client.get("/api/health/retrieval").status_code, 401)

    def test_is_scoped_like_the_run_list(self):
        self.assertEqual(self._lanes("for-alice"), ["S2"])
        self.assertEqual(self._lanes("for-bob"), ["OA-Cited"])
        self.assertEqual(self._lanes("for-admin"), ["OA-Cited", "S2"])

    def test_window_is_bounded(self):
        r = self.client.get("/api/health/retrieval?window=101", headers={"X-Access-Code": "for-admin"})
        self.assertEqual(r.status_code, 422)
