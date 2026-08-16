"""Regression coverage distilled from a completed production assessment.

The run produced 19 numeric market-finding occurrences, but five were exact
repetitions of a claim with the same cited source.  Reporting 19 as though they
were independent assertions exaggerated the size of the evidence problem.
The production run ID is a capability credential, so the fixture deliberately
contains only the minimum evidence slice and never the ID or run URL.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

import api.runs as runs
from academic_agent.claim_grounding import check_report
from academic_agent.run_output import save_claim_grounding
from api.main import app

_REPO = Path(__file__).resolve().parent.parent
_FIXTURE = Path(__file__).parent / "fixtures" / "production_grounding_crispr.json"


class _Source:
    def __init__(self, source_id: str):
        self.source_id = source_id
        self.evidence_summary = "production search snippet " * 20
        self.summary_source = "search_snippet"


class _Finding:
    def __init__(self, row: dict):
        self.finding_id = row["finding_id"]
        self.claim = row["claim"]
        self.source_ids = row["source_ids"]


class _Report:
    def __init__(self, fixture: dict):
        self.findings = [_Finding(row) for row in fixture["findings"]]
        self.sources = [_Source(source_id) for source_id in fixture["sources"]]


class _Task:
    def __init__(self, raw: str):
        self.raw = raw


def _load_fixture() -> tuple[str, dict]:
    text = _FIXTURE.read_text(encoding="utf-8")
    return text, json.loads(text)


def _evidence_json(fixture: dict) -> str:
    """Expand the compact fixture only where the persisted seam needs schema.

    Repeating all of EvidenceReport's boilerplate nineteen times in the fixture
    would obscure the production facts it preserves.  The expansion is test
    scaffolding; the claim text, IDs and citation pairs remain fixture data.
    """
    findings = [
        {
            "finding_id": row["finding_id"],
            "category": "market estimate",
            "claim": row["claim"],
            "claim_type": "estimate",
            "source_ids": row["source_ids"],
            "confidence": "medium",
            "commercial_implication": "This estimate informs market sizing.",
            "limitations": "Only a search snippet was retained.",
        }
        for row in fixture["findings"]
    ]
    sources = [
        {
            "source_id": source_id,
            "title": f"Sanitized production market source {source_id}",
            "url": f"https://example.org/{source_id.lower()}",
            "doi": None,
            "publisher": "Commercial market publisher",
            "published_date": None,
            "accessed_date": "2026-08-16",
            "source_type": "market_report",
            "credibility_tier": "medium",
            "credibility_reason": "Commercial estimate with proprietary methodology.",
            "evidence_summary": "A retained search snippet described quantitative market estimates and forecasts.",
            "summary_source": "search_snippet",
            "citation_count": None,
        }
        for source_id in fixture["sources"]
    ]
    return json.dumps({
        "topic": "CRISPR gene editing for genetic diseases",
        "scope_summary": "Sanitized market evidence from a completed production assessment.",
        "search_queries": ["sanitized production query"],
        "findings": findings,
        "sources": sources,
        "limitations": ["Only the evidence needed for the regression is retained."],
    })


class ProductionGroundingRegressionTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.fixture_text, cls.fixture = _load_fixture()

    def test_fixture_contains_no_capability_credential(self):
        self.assertNotIn("run_id", self.fixture_text)
        self.assertNotIn("/run/", self.fixture_text)

    def test_exact_repetitions_count_once(self):
        expected = self.fixture["expected"]
        report = _Report(self.fixture)
        self.assertEqual(len(report.findings), expected["raw_numeric_occurrences"])

        result = check_report(report)

        self.assertEqual(result.unverifiable_count, expected["unique_numeric_claims"])
        self.assertEqual(result.duplicates_collapsed, expected["duplicates_collapsed"])
        self.assertEqual(len(result.checks), expected["unique_numeric_claims"])

    def test_same_claim_with_different_sources_is_not_collapsed(self):
        fixture = {
            "sources": ["M1", "M2"],
            "findings": [
                {"finding_id": "MF1", "claim": "The market reached USD 4.76 billion.",
                 "source_ids": ["M1"]},
                {"finding_id": "MF2", "claim": "The market reached USD 4.76 billion.",
                 "source_ids": ["M2"]},
            ],
        }

        result = check_report(_Report(fixture))

        self.assertEqual(result.unverifiable_count, 2)
        self.assertEqual(result.duplicates_collapsed, 0)

    def test_saved_counts_reach_both_endpoints_and_the_artifact(self):
        """The value must survive the worker/API/browser seam, not merely be
        correct inside check_report.  Two earlier reliability fields were
        computed correctly but silently dropped at this boundary."""
        expected = self.fixture["expected"]
        tasks = [_Task(""), _Task(""), _Task(_evidence_json(self.fixture))]

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "20260101T000000Z-aaaaaaaaaa"
            summary = save_claim_grounding(tasks, run_id=run_id, output_root=root)
            run_dir = root / run_id
            (run_dir / "status.json").write_text(json.dumps({
                "stage": "Done", "done": True, "error": None,
                "claim_grounding": summary,
            }), encoding="utf-8")

            with patch.object(runs, "DEFAULT_OUTPUT_ROOT", root):
                client = TestClient(app)
                status = client.get(f"/api/runs/{run_id}").json()
                progress = client.get(f"/api/runs/{run_id}/progress").json()
                artifact = client.get(f"/api/runs/{run_id}/grounding").json()

        for payload in (status["claim_grounding"], progress["claim_grounding"], artifact,
                        artifact["by_domain"]["market"]):
            with self.subTest(payload=payload):
                self.assertEqual(
                    payload["duplicates_collapsed"], expected["duplicates_collapsed"]
                )


def _node() -> str | None:
    return shutil.which("node")


@unittest.skipUnless(_node(), "node not installed")
class ProductionGroundingPresentationTests(unittest.TestCase):

    def test_collapsed_repetitions_are_disclosed_to_the_reader(self):
        with TemporaryDirectory() as tmp:
            work = Path(tmp)
            source = (_REPO / "web" / "static" / "js" / "result.js").read_text(
                encoding="utf-8"
            )
            source = source.replace('import * as api from "./api.js";', "const api = {};")
            (work / "result.mjs").write_text(source, encoding="utf-8")
            shutil.copy2(_REPO / "web" / "static" / "js" / "i18n.js", work / "i18n.js")
            (work / "harness.mjs").write_text(textwrap.dedent("""
                globalThis.localStorage = { getItem: () => null, setItem: () => {} };
                function makeNode(tag) {
                    return {
                        tagName: tag, className: "", textContent: "", hidden: false,
                        dataset: {}, children: [], innerHTML: "",
                        append(...kids) { this.children.push(...kids); },
                        addEventListener() {}, querySelector() { return makeNode("div"); },
                    };
                }
                globalThis.document = { createElement: makeNode };
                const { renderGrounding } = await import("./result.mjs");
                const node = renderGrounding(JSON.parse(process.argv[2]));
                function flatten(n, out = []) {
                    out.push(n.textContent || "");
                    for (const child of n.children || []) flatten(child, out);
                    return out;
                }
                console.log(JSON.stringify(flatten(node)));
            """), encoding="utf-8")
            payload = {
                "checked": 0, "ungrounded": 0, "unverifiable": 14,
                "duplicates_collapsed": 5,
            }
            result = subprocess.run(
                [_node(), str(work / "harness.mjs"), json.dumps(payload)],
                capture_output=True, text=True, encoding="utf-8", timeout=300, cwd=work,
            )

        self.assertEqual(result.returncode, 0, result.stderr[:400])
        rendered = " | ".join(json.loads(result.stdout))
        self.assertIn("5", rendered)
        self.assertIn("repeated", rendered.lower())
