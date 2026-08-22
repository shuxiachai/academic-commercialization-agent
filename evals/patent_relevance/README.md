# Patent-relevance evaluation fixtures

This directory contains tracked challenge evidence for the human relevance
audit described in
[`docs/prereg-2026-08-22-patent-relevance-audit.md`](../../docs/prereg-2026-08-22-patent-relevance-audit.md).

`sodium-ion-grid-storage-challenge.json` contains only the six patent records
from retained run `20260707T012519Z-6e9d3f0d66`. It deliberately excludes the
run's academic, market, report, score, credentials, and operational artifacts.
The run was selected after a relevance weakness was observed, so this corpus is
diagnostic and must not be described as held out.

The 75 benchmark-core records are not duplicated here. They are read directly
from the complete tracked `benchmark_fixtures/*.json` census so later fixture
drift is detected by the packet manifest rather than hidden by another copy.
