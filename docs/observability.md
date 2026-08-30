# Agent observability

The pipeline can emit OpenTelemetry traces using OpenInference semantics and
send them to Arize Phoenix or another OTLP-compatible collector. This is an
optional diagnostic projection, not a replacement for the files under
`outputs/<run_id>/`: the report, evidence registry, status, and step events
remain the source of truth when the collector is absent or unavailable.

## Why this layer exists

The 30 stored benchmark runs all have their final report, evidence artifacts,
scorecard, and aggregate elapsed time. None has `status.json` or `steps.jsonl`,
and neither artifact expresses parent/child spans or per-stage latency anyway.
Before this integration, those runs could answer *what was produced* but not
*where time was spent* or *which framework/model operation failed*.

The adapter adds three things without changing the six-agent pipeline:

- one `commercialization_assessment` root Trace per worker run;
- project-owned spans for source collection, crew execution, claim grounding,
  and report/score consistency;
- OpenInference auto-instrumentation for CrewAI tasks and the provider SDKs
  actually used by CrewAI 1.14.7 (OpenAI-compatible, including the logical
  Kimi provider, and optional Anthropic).

The implementation lives in `src/academic_agent/observability/`. Phoenix is a
backend selected through configuration; the application code is coupled to
OTLP/OpenInference semantics rather than to Phoenix storage or UI APIs.

## Enable it locally

Tracing is off by default. Start a local Phoenix collector, for example:

```bash
docker run --rm -p 6006:6006 arizephoenix/phoenix
```

Then add the following to `.env`:

```bash
AGENT_OBSERVABILITY_ENABLED=true
PHOENIX_COLLECTOR_ENDPOINT=http://localhost:6006/v1/traces
PHOENIX_PROJECT_NAME=academic-commercialization-agent
```

For Phoenix Cloud, launch the Space and copy its base URL. Spaces are
tenant-scoped: with a browser URL such as
`https://app.phoenix.arize.com/s/my-space`, configure that whole base URL:

```bash
AGENT_OBSERVABILITY_ENABLED=true
PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com/s/<space-name>
PHOENIX_API_KEY=replace-with-your-phoenix-key
PHOENIX_PROJECT_NAME=academic-commercialization-agent
```

The locked `phoenix.otel` adapter preserves the `/s/<space-name>` route and
appends `/v1/traces`. Do not replace the Space URL with the account-root
`https://app.phoenix.arize.com/v1/traces`: that drops the tenant route.

`OTEL_EXPORTER_OTLP_HEADERS` is not another endpoint. It is a lower-level way
to supply request headers and the Phoenix SDK accepts it as an authentication
fallback. This project prefers `PHOENIX_API_KEY`; do not configure both unless
you intentionally manage the raw OTLP headers.

The worker uses a batch processor and waits at most two seconds at completion.
That bound can be changed between 100 ms and 10 seconds:

```bash
AGENT_OBSERVABILITY_FLUSH_TIMEOUT_MS=2000
```

No extra LLM or search request is made by tracing.

## What reaches the collector

The adapter records low-cardinality operational metadata:

- a one-way 16-character fingerprint of the run id;
- input character count, never the topic itself;
- source counts and failed-domain count;
- pipeline and OpenInference span kinds;
- model/usage metadata exposed by the instrumentors;
- exception class, never the exception message, on project-owned spans.

`TraceConfig` is set in code with inputs, outputs, invocation parameters, tool
definitions, embedding text, and vectors hidden. Code-level enforcement is
intentional: an environment-variable typo must not upload an unpublished
paper, a system prompt, or a model answer. The full run id is also excluded
because a run URL is a capability in this application.

## Status contract

`status.json`, `GET /api/runs/{run_id}`, and
`GET /api/runs/{run_id}/progress` all expose the same `observability` object:

| Field | Meaning |
|---|---|
| `state=disabled` | tracing was intentionally not enabled |
| `state=active` | a provider and root span were configured |
| `state=degraded` | configuration, span handling, or bounded flush failed |
| `delivery=pending` | the run is still open |
| `delivery=attempted` | the bounded flush completed |
| `delivery=timed_out` | the flush did not complete within the bound |
| `trace_id` | correlation id for the Phoenix trace, when setup succeeded |

`delivery=attempted` deliberately does **not** say "delivered". OTLP export
completion does not prove that a remote backend persisted the trace. Runs made
before this feature return `observability: null`, which is distinct from an
intentional `disabled` state.

## Failure isolation and tests

Observability cannot raise into source collection, CrewAI execution, artifact
generation, or error handling. Setup errors, span errors, and flush timeouts
become `degraded` state with only the exception class retained. The original
pipeline exception always wins.

The tests use an in-memory span exporter and mock the Phoenix provider setup;
the test suite remains zero-network. They assert that:

- root and domain spans share one Trace;
- raw run ids and topics do not appear in project-owned attributes;
- both instrumentors receive the same enforced redaction config;
- Collector/setup/span failures do not fail the operation;
- the Trace state and id reach both API endpoints, not merely `status.json`.

Run the focused suite with:

```bash
uv run pytest -q tests/test_observability.py tests/test_pipeline_worker.py tests/test_api_contract.py
```
