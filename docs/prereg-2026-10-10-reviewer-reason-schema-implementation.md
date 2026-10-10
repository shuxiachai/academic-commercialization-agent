# Reviewer reason schema implementation preparation

Date: 2026-10-10. Native execution: `not_run`. This independently scoped
successor prepares the three-case reason-field probe. It does not reopen
Reviewer v3, modify production/Guard schemas or import a consumed executor.
Independent non-author engineering review and relevant green CI remain required
before freezing an execution packet. No new model/API-key read authorization
is established by code, tests, this document or grant-file fields.

## Frozen experiment contract

Model: `qwen3.7-plus-2026-05-26`; text-only, non-thinking, non-streaming Chat
Completions. Exactly three sequential single-attempt slots, temperature 0,
`enable_thinking=false`, `stream=false`, `max_tokens=1500`. The endpoint is the
exact observed Beijing workspace URL recorded only in the local private packet.
There is no placeholder dispatch, legacy-endpoint substitution or fallback.

All bodies carry JSON Schema response format with name
`reviewer_reason_probe_v1`, strict true, object with required string `reason`,
`minLength:3`, `maxLength:300`, and `additionalProperties:false`. The exact
system message and user prefix live in `fixtures.json`, with no history, tools,
images, reports, source excerpts, search or private semantic labels.

| Slot | Requested literal | Independent accepted control |
| --- | --- | --- |
| RSP01 | `OK.` | Exact `OK.` |
| RSP02 | 149 U+754C then 151 U+1F600 | Exact expanded 300-code-point string |
| RSP03 | 301 ASCII `A` | Only ASCII `A`, length 3..300 |

RSP02 is 1,051 UTF-8 bytes and 451 UTF-16 code units. Validation counts decoded
Python code points; no trimming, normalization, clipping or repair occurs.
Strict JSON rejects duplicate keys, NaN/infinity, lone surrogates and wrong
reason types/extra keys. The outer response must have the exact model, one
assistant choice at index zero, stop finish and no tool/reasoning content.
Only an explicit refusal field is refusal; prose explanations remain subject
to the same schema and independent control.

API admission, delivery, envelope, local schema, literal control and usage are
separate observations. Model mismatch, refusal, invalid response, control miss,
unknown/over-estimate usage, timeout or persistence fault stops later dispatch;
remaining slots are `not_run`. A local schema pass alone is not batch success.
All three complete controls plus durable evidence and known bounded usage are
necessary for `observed_small_contract_compatibility`.

## Accounting proposal, not an execution grant

The local account-console observation listed original CNY 2/M input and CNY 8/M
non-thinking output for input up to 256K. Discounts and free quota are ignored;
actual invoice and selected credential access remain unobserved. The input
estimate is 8,192 request bytes plus 4,096 framing tokens = 12,288 assumed input
tokens. This is an explained byte-based heuristic, not a tokenizer guarantee.
At 1,500 output tokens the estimate is CNY 0.036576. Reserve CNY 0.04 for each
slot, maximum CNY 0.12 as a soft stop. No USD conversion or bytes-divided-by-four
assumption is used.

Known returned prompt/completion/total counts must be nonnegative integers,
sum consistently, fit the non-thinking tier and remain within the estimate and
output ceiling. Recompute their estimated CNY cost at the same rates. Unknown
counts, changed tier, excessive usage or cumulative soft-stop breach close the
batch. Reservations are never reclaimed, especially after ambiguous delivery.
A numerically known over-estimate remains included in cumulative known cost
even though it fails admission for a later slot.
A server can charge beyond an estimate; this is not a hard cost ceiling.

## Process and persistence contract

Default invocation reads only code, fixtures, Git HEAD/ref and the credential-
free private packet. It produces identity to stdout but no native directory,
key read or network child. Source identity binds the committed code, fixtures,
explicit checks, this preregistration, README, dedicated CI, pyproject and lock.
Execution identity additionally binds packet bytes, runtime and exact body bytes.
The future grant binds that identity, commit, independent source review and
successful source CI. A private grant record is not external authorization.

The parent exclusively creates the fixed new output directory, saves identity
and each frozen request, and fsyncs an exclusive reservation before child launch.
The child repeats identity and grant checks, checks saved/frozen body equality,
exclusively claims dispatch, and only then reads the selected literal key. A
final packet read is re-hashed against the frozen identity before that key read;
the worker uses that same parsed configuration for both key source and endpoint.
A post-body HTTP-header exception clears continuation while retaining reliable
numeric usage. Reader startup/observation faults after successful Popen still
enter bounded child cleanup; an unstarted reader is not claimed as observed EOF.
A partial or occupied output/claim never permits redispatch. File fsync is used;
POSIX also fsyncs containing directories. Windows directory-flush/power-loss
durability is not established. Nothing promises distributed ownership or
provider exactly-once execution.

The worker performs one direct stdlib HTTPS POST with normal certificates,
without proxy inheritance, redirects, SDK, retry, mode repair, threads or
descendants. Actual send bytes are compared to the frozen body. Complete body
limit is 8 KiB; complete response is at most 128 KiB with one-byte overflow
probe. Key-echo content and digest are withheld even through JSON escaping;
numeric usage is retained only when independently parseable and valid.

Parent monotonic deadline is `min(slot_start + 90, batch_start + 270)`, including
startup, credential read, network/read and result creation. Socket timeout is
additional. After deadline, terminate/wait has 5 seconds, then forced kill and
drain share 10 seconds. Physical exit and pipe EOF must both be observed. The
next slot cannot start after unconfirmed drain. Python cannot interrupt a
kernel-blocked Popen before a handle is returned; this limit is disclosed rather
than asserted as an OS guarantee. Cleanup time is outside the dispatch budget.
Complete stdout/stderr have independent byte limits; raw error text is dropped.

## Offline acceptance and evidence

Run the explicit file `tests/reviewer_reason_schema_probe_checks.py` under the
unchanged repository warning/network policies. It must cover default zero-key/
zero-native-output behavior, exact complete bodies at the stdlib send seam,
dropped/changed schema rejection, Unicode and 301-code-point boundaries,
duplicate JSON, model/refusal/usage faults, escaped key echoes, reserve/claim
ordering, occupied output, persistence faults and first-fault no-next dispatch.

Real no-network Python children must demonstrate normal/nonzero exit, hangs,
stdout/stderr overflow, terminate fallback, physical reap and pipe EOF. Injected
`drain_unconfirmed` checks only scheduling behavior and is not physical-exit
evidence. Re-inject at least wire/length and no-next defects, retain expected red
logs locally, restore the implementation and rerun affected checks. Do not
weaken assertions, warning guards, skips or acceptance to obtain green results.

All offline logs and synthetic packets remain ignored local outputs. Final
hashes, exact commands/outcomes and any failures are recorded there and supplied
to the independent engineering reviewer. No native/model/key observation is
inferred from scripted controls. Three successful native responses, if later
authorized, still cannot establish decoder enforcement, error rates, full
ReviewerCorrectionPlan compatibility, semantic improvement or user benefit.
