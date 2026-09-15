"""New synthetic stage-policy demo; no provider adapter or user-supplied paths."""

import json
import sys

from academic_agent.report_evidence_guarded_followup import run_policy_followup
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource


def main():
    snapshot = ReportEvidenceSnapshot(report_ref="stage-demo-only", sources=(SnapshotSource(
        source_id="A7", group="academic", title="Invented orchard probe calibration",
        publisher="Synthetic control", source_type="academic", accessed_date="2026-09-15",
        summary="The invented orchard probe measured 18 units in a synthetic fixture.", origin="abstract",
    ),))

    def scripted(*, messages, tools, tool_choice):
        results = [message for message in messages if message["role"] == "tool"]
        if not results:
            name, args, call_id = "lookup_sources", {"query": "orchard"}, "find_demo"
        elif len(results) == 1:
            assert [tool["function"]["name"] for tool in tools] == ["read_source"]
            source_id = json.loads(results[-1]["content"])["hits"][0]["source_id"]
            name, args, call_id = "read_source", {"source_id": source_id, "offset": 0, "length": 1500}, "read_demo"
        else:
            assert tools == [] and tool_choice == "none"
            result = json.loads(results[-1]["content"])
            return {"role": "assistant", "content": json.dumps({
                "answer": result["text"], "status": "answered", "evidence_ids": [result["evidence_id"]],
            })}
        return {"role": "assistant", "content": None, "tool_calls": [{
            "id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)},
        }]}

    result = run_policy_followup(snapshot, "Inspect the invented orchard control", transport=scripted)
    print(json.dumps({"mode": "scripted_offline", "result": result.model_dump(mode="json"),
                      "limits": ["no_live_stage_adapter", "no_semantic_verification", "no_reader_utility_measurement"]},
                     ensure_ascii=True, separators=(",", ":")))


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("This synthetic demonstration accepts no arguments.")
    main()
