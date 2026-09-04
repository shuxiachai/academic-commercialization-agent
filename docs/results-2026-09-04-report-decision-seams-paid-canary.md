# Report decision seams post-fix paid canary — result

**Execution date:** 2026-09-04 Australia/Sydney
**Deployed revision:** `46b93a3c6df64713eaab7c850e27c6382a704720`
**Manifest SHA-256:**
`2ca063df38f4cb5f58007d33919e307cde0b6cca288a81501de45aaad0e9a1ca`
**Case:** `RDS01`
**Root run:**
[`20260903T160613Z-6586ac1d3fe13034f891df46571b6401`](https://academic-commercialization-agent.up.railway.app/run/20260903T160613Z-6586ac1d3fe13034f891df46571b6401)
**Strict result:** `failed / report_not_inspectable`
**Production Tool Calling authorized:** no

## Result in one sentence

The exact authorized root preserved its revision, bounded Decision Context,
source collection and zero-call evidence-gap state, but the 30-minute API
watchdog terminated it during Reviewer execution; no final report, report
audit, scorecard or inspectable usage ledger reached the public boundary, so
the post-fix delivery question was not answered and the canary did not pass.

This is a failed canary, not evidence that the P1 report-audit mechanism is
wrong and not evidence that it works in production. The run produced useful
failure-path observations, but it cannot be replaced or resumed under the
frozen protocol.

## Authorization and preflight

The owner authorized one operator-funded root run on the exact revision above,
with a USD 0.10 soft stop, no operator retry, no recovery, no Planner call and
no supplementary search. One already admitted request was allowed to finish
slightly above the boundary, but no second root was authorized.

| Preflight item | Observation | Verdict |
|---|---|---|
| Public merge and deployment | PR #102 merged as `46b93a3c...`; Railway deployment `6247583855` reported `success` for that exact SHA | pass |
| CI | All eight push checks passed: Linux/Windows on Python 3.11/3.12, coverage, lint, browser smoke and Docker | pass |
| Manifest bytes | Committed bytes reproduced the frozen SHA-256 above | pass |
| Readiness | HTTP 200; `llm`, `search`, `outputs` and `paid_accounting` were all `ok`; providers were Qwen and Tavily | pass |
| Capacity | `active_runs=0` and `active_paid_operations=0` immediately before submission | pass |
| Deployed schema | `success_criteria` was present and `success_criteria_authority` allowed only `owner_approved` or null | pass |
| Access boundary | The selected owner code returned HTTP 200 from the read-only access check; the raw code was not written to a study artifact or URL | pass |
| History and paid ledger | Owner history contained nine runs; ledger readability was `ok`. The exact owner ledger count is intentionally not exposed and remained `not_inspectable` | recorded limitation |

The request returned HTTP 202 at `2026-09-03T16:06:12Z`. Its run ID was
persisted before the first poll. No ambiguous submission response occurred.

## Execution observations

The observed stage sequence was:

| First observation (UTC) | State |
|---|---|
| 16:06:12 | HTTP 202 accepted |
| 16:07:27 | three parallel evidence agents running |
| 16:18:20 | Writer running |
| 16:29:41 | Reviewer running |
| 16:36:50 | terminal `timeout` observed |

The run ID encodes a 16:06:13 UTC start. The terminal transition was observed
about 30 minutes later, matching the code-owned 1,800-second watchdog. The
public `elapsed_seconds=1404` is not a trustworthy terminal duration: after an
external watchdog kill, the current implementation derives finished duration
from the last `status.json` write, which was the Reviewer-stage update rather
than the later timeout marker. This is a separate observability defect exposed
by the run; it must not be reported as a 23-minute timeout.

The watchdog terminates the worker from the API process. Consequently the
worker's exception path cannot take its final usage snapshot, finish telemetry,
or invoke the narrow Reviewer-error fallback. This explains the observed
combination of a committed Writer checkpoint, `usage=null`, telemetry delivery
still `pending`, and no delivered Writer draft. It does not identify whether
the Reviewer request itself was slow, stalled or internally retried; those
facts are not exposed by the surviving artifacts.

## Surviving artifacts

The public status and progress endpoints agreed on all bounded fields that
survived:

- `pipeline_revision` was exactly
  `git:46b93a3c6df64713eaab7c850e27c6382a704720`;
- the Decision Context gate was `decision_support`, had no missing core fields,
  allowed one bounded GO/NO_GO decision, and reported threshold provenance as
  `owner_approved`;
- neither public response contained the raw success-criteria phrase;
- source collection retained 7 academic, 8 patent and 8 market sources, with
  no failed domain and complete three-component coverage;
- the evidence-gap shadow was written with `gate_state=no_gap`,
  `planner_state=not_run`, zero proposed and executed calls, USD 0 added search
  cost and `evidence_changed=false`;
- checkpoints committed retrieval, academic, patent, market and Writer, with
  no checkpoint error; Reviewer and Scorer were not committed;
- the nine surviving step rows show all three evidence agents finishing,
  Writer finishing and Reviewer starting. No Scorer action exists; and
- owner history increased from nine to ten with exactly one matching RDS01
  root. `recovery.state=not_requested`, and no child was created.

Only `sources`, `steps` and `gap-shadow` were advertised. The report endpoint
and the `scores`, `notes`, `grounding`, `consistency` and `report-audit`
artifact endpoints each returned HTTP 409. Both public status endpoints
carried `report_audit=null`. Equal null values are an unavailable check, not a
delivery pass.

## Frozen primary criteria

| # | Verdict | Observation |
|---:|---|---|
| 1 | **fail** | The exact revision and one-root/no-child bounds held, but the run timed out and committed only 5/7 nodes instead of completing the ordinary seven-node sequence. |
| 2 | **not_inspectable** | `usage=null`; per-role model identities, provider request count, tokens, partial cost and terminal cost did not survive the watchdog kill. Stage rows are not a substitute because transport retries occur below that seam. |
| 3 | **not_inspectable** | With no terminal cost, the USD 0.10 numerical criterion cannot be evaluated. Missing accounting is not zero cost. |
| 4 | **pass** | The persisted gap artifact reports no Planner execution, no supplementary call or cost, and no mutation of the validated evidence set. |
| 5 | **not_observed** | No Markdown report was delivered, so the code-owned applicability block could not be inspected. |
| 6 | **pass** | Status and progress exposed identical bounded authority state and omitted the raw owner-supplied criteria text. |
| 7 | **fail** | `report_audit.json` did not exist and both endpoints exposed null. There was therefore no denominator-bearing audit result or report-summary state for a browser to render. |
| 8 | **not_inspectable** | The report and evidence-to-citation audit were unavailable, so no manual threshold or electrolyte-family comparison could be joined to an audit finding. |

The strict count is **2 pass, 2 fail, 3 not_inspectable and 1 not_observed**.
Because every primary criterion had to pass, the canary failed.

## Generated-content observation

The secondary classification is `not_inspectable`. A Writer checkpoint exists,
but its payload is not a public report artifact and the protocol forbids using
a recovery child to turn it into a replacement outcome. No clean, caught or
missed content conclusion is therefore available.

## What this result changes

This run adds two concrete production observations that the offline suite did
not cover:

1. a valid Qwen run can consume the whole 30-minute process budget before the
   Reviewer finishes, even after all evidence agents and Writer have committed;
2. an API-side hard kill leaves terminal duration and partial provider usage
   under-observed, so the failure cannot be cost-audited from the public run
   contract.

The next change should address those failure seams before another paid
post-fix canary is proposed. Raising the global timeout alone would spend more
money without fixing missing accounting. A safer design must first preserve a
terminal timestamp and monotonic per-completed-call usage outside the worker's
final exception path, then define how much of the total deadline each stage may
consume and whether a validated Writer draft can be delivered safely when the
Reviewer cannot finish before that deadline.

No paid rerun, recovery child or replacement topic is authorized by this
result. Any later provider-backed validation requires a new pre-registration,
a different run identity and fresh owner authorization.

## Limits

No external source was opened during this audit. The run says nothing about
source truth, citation entailment, the scientific validity of the synthetic
thresholds, commercial decision correctness, user utility, stable Qwen latency
or production Tool Calling value. One timeout is not a rate, and the absent
cost cannot be reconstructed as zero.

See the
[pre-registration](prereg-2026-09-04-report-decision-seams-paid-canary.md)
and the preceding
[zero-network P1 result](results-2026-09-03-report-decision-and-citation-seams.md).
