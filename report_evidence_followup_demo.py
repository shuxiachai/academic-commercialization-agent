"""Synthetic scripted demonstration; no provider adapter, files or credentials."""

import json
import sys

from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource
from academic_agent.report_evidence_followup import run_followup


def main() -> None:
    snapshot = ReportEvidenceSnapshot(report_ref="synthetic-demo", sources=tuple(
        SnapshotSource(
            source_id=source_id, group=group, title=f"Synthetic {group} sensor record",
            publisher="Synthetic example", source_type=group, accessed_date="2020-01-01",
            summary=summary, origin=origin,
        )
        for source_id, group, summary, origin in (
            ("A1", "academic", "Synthetic sensor response was measured only in a laboratory fixture.", "abstract"),
            ("P1", "patent", "Synthetic patent search snippet; no legal conclusion was assessed.", "search_snippet"),
            ("M1", "market", None, "unknown"),
        )
    ))

    def scripted_transport(*, messages, tools, tool_choice):
        assert tool_choice == "auto" and len(tools) == 2
        results = [message for message in messages if message["role"] == "tool"]
        if not results:
            name, args, call_id = "lookup_sources", {"query": "sensor"}, "demo_lookup"
        elif len(results) == 1:
            assert results[0]["tool_call_id"] == "demo_lookup"
            hit = json.loads(results[0]["content"])["hits"][0]
            name, args, call_id = "read_source", {"source_id": hit["source_id"], "offset": 0, "length": 1500}, "demo_read"
        else:
            assert results[-1]["tool_call_id"] == "demo_read"
            read = json.loads(results[-1]["content"])
            assert read["text"] == snapshot.sources[0].summary
            return {"role": "assistant", "content": json.dumps({
                "answer": "The saved synthetic summary says: " + read["text"],
                "status": "answered", "evidence_ids": [read["evidence_id"]],
            })}
        return {"role": "assistant", "content": None, "tool_calls": [{
            "id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)},
        }]}

    result = run_followup(snapshot, "What was measured for the synthetic sensor?", transport=scripted_transport)
    print(json.dumps({
        "mode": "scripted_offline", "result": result.model_dump(mode="json"),
        "verification_limits": ["semantic_support_not_assessed", "real_model_compatibility_not_tested",
                                "saved_summary_not_verified_full_text", "reader_utility_not_measured"],
    }, ensure_ascii=True, separators=(",", ":")))


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("This synthetic demonstration accepts no arguments.")
    main()
