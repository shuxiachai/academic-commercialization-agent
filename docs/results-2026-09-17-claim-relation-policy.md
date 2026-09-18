# Explicit relation policy: offline delivery, not model validation

Date: 2026-09-17. New development-only policy following the closed PCQ failure.
Protocol: [offline contract](prereg-2026-09-17-claim-relation-policy.md).

## Why this is separate

PCQ01 delivered a complete saved excerpt but the native answer confused missing
measurement with refutation of a physical property. Its two requests and failed
label check stay unchanged. Rewording the old frozen prompt or retrospectively
repairing the answer would destroy that evidence. This stage adds a distinct
injected-callback policy; it does not establish that wording alone fixes Qwen.

The protocol and eight new fictional development controls were committed as
`8ac970a` before implementation. Fixture SHA-256:
`a39622a3f2fd1f40da3d1f112e8d989e78ed25ccef4d369f8b714bde58fadf4c`.
These are dependent development contrasts, not held-out accuracy samples.

## Reference assessment and limits

A separate requested `route_reviewer / gpt-6-astra / high` context received
only IDs, verbatim claims, saved text and a neutral relation rubric in its task
message. Author labels, categories and rationales were omitted; full parent
history was not forked. Inherited project context could still contain past
diagnoses. The review is explicitly label-blinded and context-limited, not fully
blind, human expert gold or independent external truth. Effective backend
metadata is unavailable.

Seven text-bearing reference relations agreed; the eighth control had no saved
text and was judged unavailable/not-reviewable. All nine supplied source
quotations occur literally. No material ambiguity was reported. Literal
matching checks transcription, not entailment. The author labels were prepared
in memory before review; review preceded the protocol commit. The protocol is
prospective for implementation, not a retrospective preregistration of review.

The local prompt file hash is
`17dff60fe1402d8159d594ef30806d3dc3c526f4d51aa88afd93d32809b2bfe2`.
The canonicalized judgment JSON hash is
`af41e6e3f978eceae07ca3312dae5d5256adf8e1fb4d2897efdd0253d7b4a298`.
The latter identifies a JSON transcription, not byte-for-byte raw response or
all inherited context. Raw local review records stay ignored. Reviewer inference
uses resources outside the project-provider ledger; no project Qwen request
or external-source check was made here.

## Implemented boundary

The new `run_relation_policy_followup(snapshot, claim, *, callback)` takes a
single positional request object at its injected callback boundary. Signature
preflight rejects directly wired old keyword-only native adapters before their
ledger or HTTP can be touched. This is an interface fence, not a sandbox for
arbitrary Python callbacks.

Only a detached system message gains the explicit rubric. Original user claim,
catalog, tool call/result and read text retain their bytes. The unchanged inner
wrapper owns strict final parsing, relation/receipt admission and semantic
unverified flags. The new layer does not load control labels or correct a
semantically wrong but structurally admitted answer.

`PolicyResult.inner` is the frozen result whose counters terminate at the
policy bridge. `PolicyResult.audit` records final callback entry separately:
configured policy identity, actual request/policy hashes, transformed bytes,
read delivery/usability, blocked reason and exception type. A second request
can reach the inner bridge and then be blocked by the new layer; its receipt
must not be claimed as delivered to the final callback. An exception after
entry does not erase that entry. Configured policy with zero entries is not a
successful delivery.

The complete transformed request still has a 12,288-byte ceiling, two callback
entries and one local read. No truncation, repair, retry or larger allowance
compensates for policy overhead. Exceptions disclose type, not callback content.
The single-request API introduces no native wire/usage-accounting contract.

## Local existing-snapshot capacity

A socket-blocked local probe projected 30 existing benchmark snapshots with
632 source rows, using one fixed invented proposition, the first source
positionally and at most 1,500 saved codepoints. All 60 scripted callback
entries fit the unchanged ceiling; their actual byte hashes matched the new
audit. First requests were 6,944-7,860 bytes; final requests were 7,983-9,876
bytes. The policy text itself is 1,297 UTF-8 bytes.

All outcomes were scripted abstentions with unverified semantic flags.
No source text left the machine. This is capacity evidence for these projected
snapshots and short claim, not retrieval quality, source truth, the identity of
the original calibration CSV, arbitrary maximal inputs or an HTTP-wire test.
Longer claims/catalogs may be refused more often because overhead consumes the
same budget; passing these 30 probes does not remove that tradeoff.

## Verification record

Observed pre-edit baseline: 5,139 tests and 1,440 subtests passed in 313.46s.
An earlier run's terminal result was lost during context compaction; it finished
before the observable baseline was rerun. No outcome is inferred from that lost
output. Both invocations were zero-provider tests.

The new test file alone passes 56 tests. Together with the frozen claim-wrapper
regression file it passes 116; these are not 116 new tests. Three targeted
mutations were applied one at a time and restored:

- Omit policy append: all eight contrast tests fail at the actual callback
  request comparison, after equality with the successful frozen inner baseline.
- Omit transformed-byte admission: four over-limit cases fail because the
  callback actually receives 12,289 bytes; the four exact-limit controls still
  pass. The older preflight explicitly passes in each case.
- Omit claim identity admission: the whitespace-changed claim reaches one
  callback instead of zero; that case fails and three instruction guards pass.

After restoration the module SHA-256 is
`2c77e90ece7ae37bd59e65fc71df5478d037d8c16966b54f074e0fc85c8a7691`.
These targeted mutation failures are intended regression observations, not
unexplained failures, exhaustive mutation coverage or semantic accuracy tests.
All 236 files in the pre-edit frozen inspection inventory retained their hashes.
That inventory covers old protocols, dated results, fixtures and follow-up
modules, not every file on the computer.

An independent read-only reviewer found no actionable issue in the new
implementation, seam tests or current public explanations. It performed static
inspection, not tests or external requests; a sandbox helper error prevented
its own hash recomputation. Test/capacity/mutation figures came from the author
and parent, which independently checked the restored source identity.

Repository-wide Ruff 0.16.8 and narrow Pylint passed. The final full suite passed
5,195 tests and 1,448 subtests in 278.77s; no new skip or warning suppression
was added. Exact-commit CI outcomes are recorded in the pull request rather
than inferred from local/subset validation.

## What this does not establish

There is no new native Qwen outcome, paid runner, production route, scoring
change, model-output repair, merge or deployment. Scripted relations and
mechanical receipt checks do not establish semantic correctness. The failed
PCQ batch and older frozen experiments stay closed.

Next is a separately identified native wire contract and bounded synthetic
experiment for the new policy, not reuse of an old adapter/runner/allowance.
Fresh unseen evidence remains necessary before general effectiveness claims.
