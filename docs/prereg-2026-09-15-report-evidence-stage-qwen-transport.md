# Stage-aware saved-evidence Qwen transport: offline contract

Registered: 2026-09-15, before implementing the separate adapter.
Baseline: `fd806a4ed30782b978654d8385d58a3492316276` (PR #145).
Scope: offline implementation and intercepted HTTP tests; no live authorization.

## Why this boundary comes next

The [stage policy](results-2026-09-15-report-evidence-stage-policy.md) can
reserve reading and finalization only if its transport preserves the narrowed
actions. Its final-only callback uses no tools and `tool_choice=none`; the
frozen native adapter accepts only `auto`. Quietly replacing `none` with `auto`
would undo that boundary, even if a cooperative mock still returned an answer.

The previous synthetic batch remains FQ01 FAIL / FQ02 unrun: three requests,
no read receipt or final answer. Its old allowance is not reused. The original
core, stage policy, adapter, runner, fixtures and recorded results remain intact.
None of the 30 existing benchmark source snapshots will be sent to a provider.

The official [Function Calling guide](https://help.aliyun.com/zh/model-studio/qwen-function-calling)
documents `none` for disabling tool selection (checked 2026-09-15). This is a
wire-contract reference, not evidence that the exact pinned model/endpoint has
completed the new conversation. Do not migrate endpoint, model or dependencies
as part of this change, or copy the guide's unrestricted demonstration loop.

## Allowed implementation

Add a separate transport and its tests, preserving exact `qwen3.5-plus` and the
existing pinned official Beijing destination. Reuse frozen HTTP/validation
primitives where safe; do not rewrite a paid experiment or route production
through the new adapter. Keep the ordinary pipeline, scores and v8 unchanged.

The new adapter must preserve the supplied permitted tool schemas, including
the lookup-hit ID enum, and transmit explicit final-only semantics. Inconsistent
mode/tool combinations fail before request reservation or dispatch. A returned
tool call during final-only mode must not reach a local tool or cause repair.

Credential, TLS, proxy, redirect, retry, timeout, byte, output-token and usage
boundaries remain strict. Actual serialized HTTP bytes and pre-dispatch journal
identity must agree. A received but invalid reply still has observed usage;
unknown usage is not zero and prevents another dispatch. Never persist raw
secrets or provider exception bodies. Prior auto-only configuration must not be
misrepresented as the identity of the stage-aware protocol.

## Acceptance at actual seams

Use a synthetic key and httpx's intercepted transport, never a real endpoint.
Exercise the real stage wrapper, local tools, new adapter and durable journal.

1. Lookup -> permitted read -> final response keeps native call IDs, exact saved
   text and evidence receipts. The last HTTP body disables tools; the recorded
   request hash equals the exact transmitted bytes.
2. Direct read and missing-text abstention reach finalization with no hidden
   lookup or invented read receipt. These are scripted controls, not model cases.
3. An illegal mode, tool set or final-stage tool request cannot be transformed
   into an allowed operation or paid repair. Check actual HTTP/local-tool counts.
4. Wrong model, unknown/contradictory usage, redirection, timeout, excess size,
   exhausted request/budget allowance and persistence failure remain explicit;
   failed pre-dispatch persistence results in zero intercepted HTTP calls.
5. Raw/JSON-escaped key echoes and exception bodies cannot enter returned
   messages, transcripts or diagnostics. Ambient model/key/base/proxy values
   cannot alter the actual request destination or selected credential.
6. Re-inject a wire-level none-to-auto defect, observe the new boundary test
   fail, restore its hash and rerun. Do not weaken old or new assertions/skips.

Run the full zero-provider suite before/after, old/new focused suites, latest
Ruff, narrow Pylint and independent read-only review. Report their actual
denominators separately. Preserve the original frozen-file hashes.

## Explicit non-goals and next gate

No paid model/search request, live CLI, production route, source expansion,
customer-data transmission, scoring change, model substitution or old-case
repeat is authorized here. The experiment ledger is single-process and is not
the public application's shared admission or customer receipt service.

This adapter does not establish model compliance, semantic support or user
benefit. A later live test needs a separate frozen runner/configuration,
synthetic fixture identity, fresh output directory and bounded authorization;
neither the old allowance nor this offline pass grants it. Production rollout
still requires its own payer/ownership, receipt and user-visible failure seams.
