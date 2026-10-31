"""Fresh scripted offline selection controls, not model-quality observations."""

import json
import sys

from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource
from academic_agent.report_evidence_source_locator import locate_saved_source, render_locator_result


def synthetic_snapshot() -> ReportEvidenceSnapshot:
    return ReportEvidenceSnapshot(report_ref="locator-fresh-synthetic-storage-notes", sources=(
        SnapshotSource(
            source_id="A101", group="academic", title="Woven flax storage liner",
            publisher="Synthetic materials notebook", source_type="academic",
            accessed_date="2026-09-18", origin="abstract",
            summary="  A woven flax liner was stored at 18 °C.\nNo shelf-life measurement was saved.  ",
        ),
        SnapshotSource(
            source_id="P102", group="patent", title="Clay container label holder",
            publisher="Synthetic design notebook", source_type="patent",
            accessed_date="2026-09-18", summary=None,
        ),
    ))


def main() -> None:
    """No arguments, input paths, credentials or writes; stdout is JSON data."""
    snapshot = synthetic_snapshot()
    results = []
    # Selection is prescribed, not inferred or evaluated for relevance.
    for source_id in ("A101", "P102"):
        def select(_request, /, _source_id=source_id):
            return {"role": "assistant", "tool_calls": [{
                "id": "scripted_locator", "type": "function",
                "function": {"name": "read_source", "arguments": json.dumps({"source_id": _source_id})},
            }]}
        results.append(json.loads(render_locator_result(locate_saved_source(
            snapshot, "Locate a saved storage note.", selector=select,
        ))))
    results.append(json.loads(render_locator_result(locate_saved_source(
        snapshot, "Locate a saved storage note.",
        selector=lambda request: {"role": "assistant", "content": '{"action":"decline"}'},
    ))))
    print(json.dumps({
        "mode": "scripted_offline", "selection_quality": "not_assessed", "results": results,
    }, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("This scripted_offline demo accepts no arguments.")
    main()
