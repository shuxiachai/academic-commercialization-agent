# Regulator-title recovery post-integration production canary — result

**Run:** [20260825T063703Z-efb379b66c5c46133bf50b7d5397a41f](https://academic-commercialization-agent.up.railway.app/run/20260825T063703Z-efb379b66c5c46133bf50b7d5397a41f)
**Protocol:** [frozen pre-registration](prereg-2026-08-25-regulator-title-recovery-paid-canary.md)
**Pre-registration commit:** `b9303a1`
**Authorized production revision:** `8c592fcb35c4e89ce62764d1cd13bfb39f282bb0`
**Outcome:** valid production observation, but not a pass because the primary
recovery trigger was not observed

## Execution

The operator authorized one paid root run on the repeated blood-pressure topic.
One initial local `curl` invocation failed shell parsing before it formed an
HTTP request. The owner history still contained exactly four entries after that
client-side failure. The request was then submitted once from a persisted JSON
payload, and the returned run id was written to the ignored audit directory
before polling began. No retry, resume, cancellation, topic substitution, or
second paid operation followed.

- Terminal state: `completed`, with no error and `resumed_from=null`
- Elapsed time: 161 seconds
- Sources: 3 academic + 8 patent + 8 market; no failed domain
- Provider use: 77,724 tokens over 6 ordinary workflow requests
- Inspectable cost: `$0.032665`, below the `$0.05` soft stop
- Quality review: passed
- Consistency screen: 0 blockers and 0 warnings
- Checkpointing: `retrieval`, all three evidence nodes, `writer`, `reviewer`,
  and `scorer` committed without an error
- Recovery: `not_requested`; no child run or reused node
- Operator history: exactly 4 before and 5 after, with this run as the only new
  entry

## Frozen criteria

| # | Result | Evidence |
|---|---|---|
| 1 | `not_inspectable` at the public run boundary | GitHub deployment `6077280941` and Railway deployment state identified the authorized revision before submission. The public status, steps, sources, and report endpoints do not export checkpoint `identity.pipeline_revision`, so the exact field cannot be observed independently and is not inferred into a pass. |
| 2 | `pass` | The one root run completed, created no recovery child, and exposed the ordinary seven committed checkpoint nodes with no checkpoint error. |
| 3 | `pass` | Cost was complete and inspectable at `$0.032665`, below `$0.05`. |
| 4 | `pass` | The shadow check ran with `gate_state=no_gap`, `planner_state=not_run`, zero proposed or executed calls, `$0` additional search cost, `evidence_changed=false`, and `persistence_state=written`. Pydantic-loading the delivered source collection and applying the repository's canonical hash function independently reproduced `07ffcda8db8375e9070c887393405c3819a57b46114983bad33045e14dcafd75`, exactly matching the artifact. |
| 5 | `not_observed` | K222658 did not recur, and no supported FDA 510(k) or ClinicalTrials.gov URL arrived with a defect recognized by the frozen structural detector. Absence is not a recovery pass. |
| 6 | `pass` only for the recovery transformation seam | FDA source `M5` was observable. Its persisted title produced zero frozen structural-defect codes, carried no recovery disclosure, and therefore followed the byte-preserving branch. This says nothing about whether the upstream title was semantically true; the separate finding below shows that it was not. |
| 7 | `not_observed` | No neutral identifier label was recovered, so report delivery of a recovered label could not be tested. |
| 8 | `pass` | Owner history increased from four to exactly five root runs. There was one effective production POST, no resume, and no Planner or supplementary-search request. |

The canary therefore did not pass its primary question. It did establish that
the integrated workflow completed under the frozen budget and that the recovery
seam did not rewrite the one structurally clean title it observed. Those are
supporting observations, not evidence that malformed supported titles recover
in production.

## New finding: structurally plausible but semantically damaged title

The accepted regulator source was `M5`:

> `TM Clinical Platform with ClearSightm Finger Cuffs 510(k)`

Its URL is the official FDA record
[`K140312`](https://www.accessdata.fda.gov/cdrh_docs/pdf14/K140312.pdf). The
first page of that document identifies the device as the **EV1000 Clinical
Platform with ClearSight Finger Cuffs**. The persisted search-result title lost
the `EV1000` entity and converted trademark notation into the literal fragments
`TM` and `m`. The same damaged title reached the delivered report reference
exactly once.

This is not a U+FFFD decoding failure: the delivered report contains zero
replacement characters. It also does not match any frozen structural defect,
so the detector correctly followed its current precision-first contract rather
than guessing that a grammatically plausible title was wrong. The report body
still named EV1000 because the evidence summary retained that entity, but the
reference title remained inaccurate.

This finding must not be converted into a one-example production patch. The URL
uses `/cdrh_docs/pdf14/K140312.pdf`, outside the two exact identifier paths in
the frozen recovery rule, and the defect requires title-truth comparison rather
than debris detection. A defensible follow-up needs a separately frozen set of
clean and entity-damaged official titles, a precision-first semantic or
metadata comparison, and an abstention path. Until that exists, the honest
status is: structural recovery passed its development challenge, its production
trigger remains unobserved, and one different class of title-quality defect is
now measured.

## Boundary of the result

This is one repeated-topic provider-backed observation. It is not a title error
rate, production precision/recall, report-quality improvement, SLO, or proof
that the recovery rule handles malformed titles in production. It also does not
establish independent source truth beyond the one FDA record opened for this
audit.
