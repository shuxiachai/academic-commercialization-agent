# Stage-aware Qwen transport: intercepted HTTP result

Date: 2026-09-15. Scope: offline engineering checks, not a live model run.
The [protocol](prereg-2026-09-15-report-evidence-stage-qwen-transport.md) was
committed as `da37cbc` before implementation, against
`fd806a4ed30782b978654d8385d58a3492316276`.

## The boundary repaired

The previous stage wrapper could request finalization with no tools, but the
frozen Qwen adapter accepted only `auto`. Replacing `none` with `auto` would
make the layers fit while undoing the restriction. A cooperative scripted
reply could hide that defect unless the actual request was inspected.

The new `StageQwenFollowupTransport` keeps the old source/runner unchanged and
reuses their pinned HTTP, strict decoding, secret detection and usage primitives.
It accepts only the policy's exact initial declarations, read declaration with
the supplied hit enum, or final-only callback. A reply outside the declared
actions is rejected before local dispatch, with received usage retained.

The final callback's `tools=[]` maps to an omitted `tools` member on the wire;
explicit `tool_choice=none` is preserved. This happens before canonical encoding
and durable reservation, so the journal hash identifies the actual HTTP body.
Other stages preserve the complete supplied schema and enum order. No dummy
tool, forced replacement or paid repair is introduced.

The official [Function Calling guide](https://help.aliyun.com/en/model-studio/qwen-function-calling)
documents `none` or omission of `tools` for disabling selection. Its examples
do not establish exact-model acceptance of an empty tool array. Independent
review therefore recommended omission, not a claim that `[]` was observed to
fail. No provider request was used to resolve this compatibility question.

## Identity and accounting are not production authorization

`StageQwenLedger` creates its own code-owned manifest with a stage-aware
transport identity, stage choices and final-wire representation. The prior
auto-only manifest is not reused. The reused limits and rates retain their
frozen conservative meaning, not a new price quote or a new paid allowance.
Dependency paths document coupling; they do not claim verified source hashes.

The exact model and Beijing destination, explicit key, TLS/no proxy/no redirect/
no retry restrictions, bounds and owned async timeout are retained. No `.env`
or ambient credential lookup was added. Known usage survives rejected model or
protocol replies; unknown usage, unresolved intent and persistence failure stop
later dispatch. A secret in an outgoing transcript is rejected before reserve;
response secrets and exception bodies are not persisted as diagnostic text.

This is a network-capable library exercised through an intercepted transport,
not a network sandbox. An offline manifest label cannot authorize a real call.
The ledger is single-owner and does not provide public paid admission, customer
receipts, source ownership or a resumable experiment.

## Preserve the observed test failure

The full pre-change suite passed **3,439 tests / 1,313 subtests**, 122.45 seconds.
The first new-file execution reported **38 passed / 54 failed / 19 errors**,
5.77 seconds; these are reported outcome categories, not an inferred case count.
Its global `socket.connect` / `connect_ex` guard broke Windows Proactor event-loop
self-pipe creation, with missing `_ssock` and teardown warnings. This is evidence
of a test-isolation defect, not a provider response or a demonstrated adapter bug.

The fixture was repaired at the HTTP construction boundary: an actual
`httpx.AsyncClient` must have the intercepted `MockTransport`, no proxy/mounts
and no environment transport; synchronous HTTP entry points are refused. This
lets the event loop create its internal socketpair without permitting provider
HTTP from this adapter. No warning ignore, skip or weakened outcome assertion
was used to suppress the failure. This narrow isolation is not a general
process-wide network sandbox.

Two later validation attempts also exposed an overlong pytest parameter ID on
Windows (including its focused reproduction). Only the display ID was shortened;
the oversized argument and rejection assertion were retained. An inaccessible
default temporary directory was handled with a fresh workspace `--basetemp`,
without changing permissions. These are separate from the historical paid
closure failure, not repeated evidence of a provider defect.

## Offline verification

The new file passes **93 tests**. Its combined regression with the frozen
snapshot/core/policy/transport/runner tests passes **342 tests**, 4.80 seconds.
These overlap with the full suite and are not added to its denominator.

For defect re-injection,
`test_lookup_read_final_preserves_none_wire_schema_ids_and_durable_hash` was
run with the actual final wire changed to `auto` after reservation. It failed
with `assert 'auto' == 'none'`, rather than merely checking a configuration
field. The original source hash was restored and the combined 342 tests passed
again. This expected red result is separate from unexpected validation failures.

The restored implementation SHA-256 is
`5c16d4b174b87dbcc74bd5c0031e8e313b1df6b2abc32daa14ce4357bcc855b3`;
the test file is
`304add11220bd37feb0570a87ef2bd47ef7d515abe51d411bc216a16e0f2c581`.
All 49 protected old source, protocol, benchmark and paid-artifact hashes remain
unchanged. Latest Ruff 0.16.7, the project's narrow Pylint check and offline lock
validation pass. These checks used AI-assisted implementation and review, not
independent human or semantic labels.

The post-change full local suite passes **3,532 tests / 1,323 subtests**,
101.43 seconds. This is 93 additional tests, not 342 new tests. The timing is a
local test observation, not an application latency or performance claim.

The final independent read-only AI review verified both hashes and found no
actionable blockers in source, tests or documentation. The reviewer inspected
the contract statically; the test/mutation executions above are author/parent
evidence, not a second independent execution. The final documentation-only check
passes 6 tests / 629 subtests, 1.74 seconds, in its own denominator.

## Limits and next gate

No new provider/search call, real key, user report, reserved evaluation cohort
or production route was used. FQ01 remains failed, FQ02 unrun, and v8 sealed.
The tests exercise native-shaped HTTP and real local lookup/read functions but
their replies are scripted. They do not establish new Qwen closure success,
semantic support, human utility or autonomous supplementation.

`protocol_accepted` in the transport ledger is not the core's final-envelope or
evidence verdict. A future runner must inspect both and stop on either failure.
It also needs its own fresh synthetic fixture, source/config/dependency identity,
exclusive output and bounded live authorization; the old runner and unused
allowance cannot be reused. Deploying this package adds no website follow-up.
