# Stage-aware Qwen canary: offline runner preparation

Date: 2026-09-15. No new provider/search calls or live cases were executed.
Baseline `0b62b1dca44f6324f84e4bbf15c86bd3c67513dd`; the
[protocol](prereg-2026-09-15-report-evidence-stage-qwen-canary.md) and SQ01/SQ02
fixture were committed as `94c27bd` before implementation. The original FQ01
failure, unrun FQ02 and sealed retrieval experiments remain unchanged.

## What this step establishes

A separate runner composes the real stage policy and HTTP adapter. Default
CLI invocation performs only identity verification. It does not read the
dedicated credential, create an experiment directory or contact Qwen. Future
execution requires a new protocol acknowledgement and fresh user authorization;
the proposed six-request/USD0.10 ceiling is not an authorization in this change.

Identity checks cover 16 paths, including package initialization and reused
frozen primitives, committed content, exact fixture, configuration and installed
dependency versions. Direct blob comparison also detects modifications hidden
from ordinary Git status. Raw disk hashes stay distinct from CRLF-normalized
Git comparison. This does not attest installed package bytes or isolate an
adversarial concurrent process; it is a local single-owner consistency check.

The original stage ledger's offline manifest remains intact. Separate write-once
identity and operator-acknowledgement records precede any HTTP dispatch. An
acknowledgement records operator intent, not independently verified consent.
Output paths must be new, contained and direct; occupied output is never resumed.
Only the process DashScope key is eligible, without dotenv or provider fallback.

Case acceptance is not HTTP acceptance. A read must be observed in the native
reply, paired with its actual later accepted tool message, and meet the case's
final state and policy/core constraints. SQ01 needs the complete frozen excerpt
and issued evidence citation; SQ02 needs observed missing text then abstention.
No-tool answers and uninspected abstention do not substitute for these states.
The first failure stops later dispatch; received usage remains recorded even
when the answer, identity recheck or result persistence fails.

## Offline verification and counterexample

- Pre-change full suite: **3,532 passed / 1,323 subtests**, 109.69 seconds.
- New test file: **81 passed**, 13.04 seconds.
- After restored mutation: **423 focused tests passed**, 16.81 seconds. This
  includes the old 342; it is not 423 new tests.
- Implementation full suite: **3,613 passed / 1,329 subtests**, 116.15 seconds.
- Delivery full suite after adding the result and guide links: **3,613 passed /
  1,332 subtests**, 109.79 seconds. The additional subtests include public-document
  link checks; they are not additional model observations.
- Latest Ruff 0.16.7, narrow Pylint and offline lock checks pass. All **60** old
  protected files remain unchanged, including 30 benchmark source snapshots
  and four prior paid artifacts. This broader list is a new protection scope,
  not a claim that the previous round's 49-file check covered 60 files.

`test_first_core_failure_suppresses_actual_second_case_http` was rerun after
removing the first-failure stop branch. It observed **3 actual intercepted
requests instead of 1** and failed as intended. Restoring the exact runner hash
then yielded the 423-test pass. A field or summary-only assertion would not
prove that the second case had avoided dispatch.

No unexpected implementation/test failure was reported in this iteration.
Local helper startup and an obsolete patch-executable path were separate
environment/tool-launch failures. They produced no provider request. The first
preregistration attempt did not commit; implementation permission was paused
until the successful `94c27bd` commit was actually verified. No ACL, warning
filter, assertion, skip or old fixture was changed to work around these failures.

Stable SHA-256 identities:

| Artifact | SHA-256 |
|---|---|
| Runner | `12f3c8e5e38feb1e496946d99118a2252e3796f51a483a8d03cc6e19a801179d` |
| CLI | `0fe99c15bc08b69d2abeffff47db8539b9f5571b54f67ad069a8de10b4bb6139` |
| Tests | `921ddeb69041e8028a15b549622112806384be9e12520d807e255957834d7ecb` |
| Fixture | `93d3872b7789a1ff99fbe236274a0ec7a52ce987ece9d53f63e4080fba27ffa6` |
| Fixed configuration | `88b4b81c67b155b3229788b87945a740e5c4af6b7b981e1be3ead096ada04b34` |

At committed implementation `5d6c56e64768dec1ba74ba38e0eb048b0093dd2c`, the
actual default CLI returned `identity_only`, `identity_verified=true`,
`live_authorized=false`, the 16-path identity and the above configuration hash.
This check used no synthetic or real credential and no output directory.

Independent read-only AI review verified stable source/test hashes and found
no actionable issues. Test and mutation executions are author/parent evidence;
the reviewer performed static inspection, not a second execution or human eval.

## Next gate, not a completed feature

SQ01/SQ02 are frozen **unrun live controls**, not two passed model cases. Scripted
HTTP tests establish the runner's mechanics, not native Qwen compliance or
semantic support. `semantic_support=not_assessed` and
`answer_verification=not_verified` remain even on a future protocol pass.

A real execution still needs exact final commit/fixture authorization and a
check that the frozen conservative estimate covers the proposed scope. No old
allowance, repeat or automatic production activation follows from this delivery.
Ownership, shared paid admission, customer receipts, failure UI and user value
remain separate production gates. This code package exposes no new website route.
