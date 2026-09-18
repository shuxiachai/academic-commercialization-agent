# Relation-policy native runner: engineering gate, not a model result

Date: 2026-09-18. The [RPQ protocol](prereg-2026-09-18-relation-policy-qwen-canary.md)
was committed as `b7922f4` before runner implementation. Preparation baseline:
`696f9ca864006f86dcdd083e1e20e6e1d811e85f`.

## Why this step is separate

The closed PCQ batch read a complete excerpt but confused absence of measurement
with refutation of a physical claim. Its failure stays unchanged. The later
explicit relation policy and native adapter have only scripted engineering
evidence. This runner creates a distinct, fixed-output native experiment for
that policy rather than patching a consumed prompt or replaying an old batch.

Exactly RP01-RP03 from the frozen RP fixture are selected in advance. They are
dependent synthetic development controls, with earlier context-limited LLM
reference review, not unseen data, independent samples or human expert gold.
Only their literal claims, synthetic catalog and selected saved-text windows
may enter a later native request. Reference labels and rationales stay local.

## What the runner must preserve

Identity-only CLI operation verifies the committed project closure, literal
fixture identity, disk/blob bytes, configuration and locked installed versions.
It does not load credentials, create a batch or contact Qwen. Native execution
has a separate exact protocol acknowledgement, a fixed exclusive output and
no resume, model, source, case or output override. Version matching is not
installed-library byte attestation; operator acknowledgement is not independent
consent or CI attestation.

The new runner composes the frozen RP wrapper with the exact RP native adapter
and ledger. The policy callback audit, frozen inner receipt and HTTP journal
are inspected independently. The policy adds bytes before the native callback,
so its lengths cannot be compared with pre-policy inner lengths as if they
were identical. Entry into a callback also does not prove that HTTP was sent.

A valid but wrong relation remains a mechanical success and a separate
reference mismatch. The batch stops at that first mismatch. Incomplete first
reads stop before buying another turn; persistence failure prevents the next
case even if its predecessor was mechanically correct. No result is repaired.
Unknown usage retains its reservation and remains explicitly unknown, not free.

The ceiling remains six sequential requests, two per case, one local read,
12 KiB complete HTTP JSON and USD 0.10 conservative soft budget. The fixed
Qwen model, endpoint and inherited HTTP restrictions do not change. Publication
is local write-once, not distributed admission or provider exactly-once.

## Observations and evidence boundaries

The unchanged pre-edit full suite passed 5,383 tests and 1,492 subtests in
360.00 seconds. A fresh socket-blocked callback rehearsal delivered one usable
receipt per selected case through six callback entries. Initial callback sizes
were 4,363 / 4,403 / 4,366 bytes; final sizes 5,141 / 5,181 / 5,071. Those were
scripted replies, not HTTP or model inference.

The new focused suite passed 148 tests in 33.76 seconds, then 148 in 32.16
after the last mutation was restored. These exercise real RP, local reads,
the exact adapter/ledger and intercepted HTTP with fake credentials. They do
not call the project provider or demonstrate model-quality improvement.

Three preregistered omissions and two review-driven test controls were
reintroduced separately, with valid downstream scripted replies:

| Omitted boundary | Expected failures | Observed seam |
|---|---:|---|
| RP callback-audit admission | 12 | Six HTTP requests instead of two |
| First-stage complete-read admission | 2 | Partial/offset reads buy a second request instead of stopping at one |
| First label-mismatch stop | 1 | Six HTTP requests instead of two |
| Post-call identity check on the error path | 2 | Two rather than three, or four rather than five identity checks |
| Protected environment get in the test guard | 1 | Six HTTP requests rather than one in the injected-read control |

For the partial-read and error-path identity mutations, two other selected
controls still passed; for the missing environment guard, the non-injected
control still passed. The first four mutations restored the exact runner
bytes; the last restored the test file. Guard removal retained an empty fake
environment and a valid provider response, not access to actual credentials.
These are targeted regression observations, not exhaustive mutation coverage.

Independent review found that provider rejection could mask a missing post-call
identity check. The test now asserts the actual count/order as well as usage
and stopping. The targeted error-path mutation confirms that distinction.

The initial focused run had 146 passes, two failures and two teardown errors:
a new blanket environment guard rejected asyncio's normal debug lookup before
the intended HTTP seam. A parent full run was stopped and invalidated after
that known failure was reported. The repair is test-only: normal environment
get calls receive defaults from a fake empty mapping. A get whose name contains
KEY, QWEN or PROXY, direct indexing and items() remain denied and recorded;
ordinary iteration sees an empty mapping. The injected handler
returns a valid scripted response if its guard is absent, preventing an
unrelated missing-response error from making the negative case pass. No warning
ignore, assertion weakening, runtime workaround or skip was added.

Restored identities:

- Runner: `b8c14767ba576b7ff0f990e0c0453f9c126cf0cc1d4893a654b4e97689daf00b`.
- CLI: `bb6f41c04b62a8b708d4dc7f169f618a936236d264335736090b5dafee5e769f`.
- Tests: `6c4302a59d245e43475e09f1e5e6876972d8e7e40fc3b209b36abed5c5a8d58d`.

The pre-edit inventory contained 506 tracked source, test, fixture, dependency
and documentation files. Of these, 503 retain their exact hashes; the three
intentional changes are the current evidence ledger, archive index and follow-up
guide. AGENTS.md is a separately edited current index outside that inventory.
Twenty files in the closed PCQ and CLQ output directories retain their hashes.
This is a bounded inventory, not an attestation of every local file.

One later full run reported 5,531 passed and 1,496 passed subtests, but failed
one archive-navigation subtest. The parent created this dated result while
that run was active, before its matching index update was observed by the
test. The captured assertion contains the earlier index without the link.
That run is a failure, not the final validation. The current index includes
the result; freeze all edited files and repeat the full suite without concurrent
edits. Final full-suite, lint and exact-head CI outcomes are recorded on
[PR153](https://github.com/shuxiachai/academic-commercialization-agent/pull/153)
instead of changing this document during validation again.

A different requested route_reviewer / gpt-6-astra / high context reviewed the
protocol, source and restored tests without authoring them or running tests.
It found no remaining actionable source/test issue after the three test
weaknesses described above were corrected. Effective backend model metadata
is unavailable; this is independent static review, not independent test
execution or model attestation. Focused/mutation observations came from the
implementation expert; full-suite and inventory observations came from the
parent. Neither local results nor static review substitute for exact-head CI.

## Limits and next gate

No new project-provider call, real-report disclosure, production route,
merge or deployment belongs to this implementation stage. Old batches remain
occupied and closed. A later native run requires the new exact committed
identity, unchanged fixture, independent source review and green exact-head CI
under the applicable synthetic-only scope.

Mechanical acceptance, frozen-label agreement, subsequent fallible LLM judgment,
fresh unseen validation, real-report usefulness and production admission are
separate gates. The intended nonempty-insufficiency path remains unproven live
until a new native observation actually establishes that narrow outcome.
