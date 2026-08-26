# Evidence-gap domain adapters — Phase 4 live value-study protocol

**Frozen:** 2026-08-26, before the Phase 4 live runner or review packet was
implemented

**Production connection authorized:** no

**Live provider requests authorized by this document:** no

**Human labels authorized by this document:** no; a returned packet requires
its own reviewer declaration

## Why this protocol exists

The Phase 4 implementation result established offline request, schema,
quarantine, accounting, secret-isolation and production-disconnection
contracts for source-native OpenAlex and Lens adapters. It did not make a
provider request and therefore did not observe provider compatibility or
candidate value.

The earlier generic Tavily pilot returned only 5/25 descriptively relevant
candidates and 20/25 wrong sources. Its review was formally ineligible because
substantive generative-AI judgment was declared, but that poor descriptive
result is enough to require a stricter domain-specific value study before any
planner-trigger experiment.

This protocol adds the missing execution and human-review seams. It does not
connect either adapter to `pipeline_worker.py`, the production evidence
registry, or a delivered report.

## Frozen inputs and implementation identity

The eight-case challenge remains byte-identical to the earlier Phase 4
pre-registration:

- fixture:
  `tests/fixtures/evidence_gap_phase4_domain_challenge.json`;
- fixture SHA-256:
  `f9eee1fcf2ff5acb75e9da840b94baa43e3b10f7e3136dec9886c3a572663a24`;
- adapter implementation commit: `388512e`;
- `src/academic_agent/tools/domain_evidence_search.py` SHA-256:
  `ae79c38378321f6ce4481e682787ee49f930ec4c34b696d404fcf78d97b2eeab`;
- `src/academic_agent/evidence_gap_execution.py` SHA-256:
  `5b1b94ebd8130834603567f25336dcf106d58653e6bdd2b862509d396639e8fe`;
- `evidence_gap_phase4_audit.py` SHA-256:
  `e70c2e015ffc5a01b1f9e35634dd65b9a37062bc561b9deaff8fbfa3bfb09477`.

Any mismatch must stop before adapter construction, output-directory
reservation, or provider work. Updating a hash creates a new experiment and
requires a new pre-registration; the runner may not silently accept the new
bytes.

The four OpenAlex cases are D01–D04 and the four Lens cases are D05–D08. Each
contains one pre-authored query and authorizes at most one request returning at
most five provider rows. No model selects a provider, decides whether to
search, or rewrites a query in this study.

## Live execution protocol

Dry-run remains the default and performs zero requests. A live run additionally
requires all of the following:

1. an explicit `--execute-live` switch;
2. a new output directory that does not already exist;
3. a positive OpenAlex soft-stop no greater than USD 0.05;
4. an explicit acknowledgement that Lens request cost is uninspectable;
5. both `OPENALEX_API_KEY` and `LENS_API_KEY`; and
6. an exact match for every frozen fixture and implementation hash above.

All non-network checks happen before adapter construction. The runner then
reserves the output directory and persists the fully expanded frozen manifest
before the first request. Each completed case is written immediately to its own
write-once JSON journal before another case can run. This preserves the last
inspectable paid boundary if the process stops before aggregate artifacts are
finalized.

OpenAlex and Lens have separate accounting:

- OpenAlex provider-reported USD is accumulated exactly. The runner checks the
  soft stop before the next OpenAlex case. A single in-flight request may take
  the observed total slightly above the line; no later OpenAlex request may
  start once the line has been reached or exceeded.
- A missing OpenAlex cost makes that provider uninspectable and stops later
  OpenAlex cases.
- Lens cost remains `uninspectable`, never zero. The acknowledgement and the
  fixed four-request cap are its budget boundary.
- A failed request stops later cases for that provider because repeating a
  likely authentication or compatibility failure would spend budget without
  increasing evidence. Failure in one provider does not erase or prevent an
  independently authorized attempt for the other provider.

The global hard limit is eight provider requests. An adapter invocation is
still constrained to exactly one request and the executor receives an
`outbound_attempt_limit` of one. Internal retry, redirect following, source-page
fetching and report registration remain forbidden.

## Write-once execution artifacts

A finalized run contains:

- `manifest.json`: complete source collections, validated plans, fixture hash
  and implementation hashes;
- `case-executions/D01.json` through the last attempted case: one immutable
  executor audit per completed case;
- `execution.json`: provider-separated completion, request and cost states;
- `candidates.csv`: every provider row exactly once, including provider and
  local quarantine disposition;
- `review.csv`: a blank row for every quarantine-accepted candidate; and
- `artifact-index.json`: SHA-256 values for the four aggregate source files.

An existing path is never overwritten. A partial directory is evidence of an
interrupted study, not permission to resume it or infer that unrecorded cases
made zero requests.

## Source lock and Schema v2 human review

The live directory is not accepted directly as a human-review source. After a
study owner inspects the finalized run, a separate write-once source-lock file
must bind:

- every aggregate source-file SHA-256;
- the artifact-index SHA-256;
- the frozen fixture and implementation identities;
- the study-owner identifier and UTC timestamp; and
- an explicit confirmation that the run is the authorized output.

Only a complete eight-case run with four requests per provider may be locked
for this value study. This prevents a partial run or a zero-row denominator
from being presented as a clean review.

The separate human packet uses schema version 2. It exposes, for every case,
the topic, query, failed evidence domain, collection SHA-256, gap state and
baseline source identities/summaries. Candidate identity hashes cover provider,
case, accepted source id, title and URL. Preparing or summarizing a packet makes
zero network or model calls.

Every accepted candidate must be labelled as one of:

- `YES/YES`: directly relevant and materially absent from the frozen baseline;
- `YES/NO`: directly relevant but already represented in the baseline;
- `NO/N/A`: not directly relevant to the declared gap; or
- `UNVERIFIABLE/UNVERIFIABLE`: the source was attempted but could not be
  inspected sufficiently.

A source-grounded note is required for every label. The reviewer declaration
must state whether every URL was attempted, elapsed time, expertise and any
generative-AI use. `NONE` and `LANGUAGE_ONLY` are eligible. Substantive
generated judgments are retained but excluded from the human-value result.

## Frozen provider-specific value gates

Each provider is evaluated separately. A provider passes only if all three
conditions hold:

1. at least one quarantine-accepted candidate exists in at least 3/4 cases;
2. no more than 5% of its accepted candidates are labelled `relevant=NO`; and
3. at least one `YES/YES` candidate exists in at least 3/4 cases.

Both providers must pass for the overall domain strategy to pass. Zero
accepted candidates, incomplete labels, an inaccessible source, substantive AI
use, missing baseline context, source drift or uninspectable execution
accounting is a non-pass, never a zero-error success.

Even an eligible pass does not authorize production connection. It only makes
a separately pre-registered planner-trigger precision study worth considering.

## Acceptance criteria for the implementation PR

The runner and review tooling may merge while disconnected only if tests prove:

1. fixture and all implementation hashes are checked before adapter
   construction;
2. missing credentials, missing Lens acknowledgement, invalid budget and an
   existing output path make zero requests;
3. no case can make more than one request and no run can exceed eight;
4. OpenAlex reported cost and Lens uninspectable cost remain distinct through
   the final JSON boundary;
5. every provider row reaches exactly one CSV disposition and every accepted
   source reaches the blank review seam;
6. per-case journals exist before a later case starts;
7. the source lock rejects partial execution and all later source drift;
8. the Schema v2 packet exposes and revalidates baseline context, candidate
   identities, label pairs, declarations and provider-specific thresholds;
9. zero accepted candidates and zero completed labels cannot become a pass;
10. secrets never reach artifacts, stdout or raised text;
11. the production worker still imports neither runner, executor nor adapter;
12. a deliberately removed implementation-hash gate and a deliberately dropped
    provider row each make a targeted seam test fail; and
13. the full zero-network suite, latest Ruff, CI exception-order check and
    coverage floor remain green.

## Explicit non-claims

Implementation tests or a later live result do not establish autonomous Agent
tool choice, planner precision, source truth, provider-wide precision, report
improvement, user utility, cost savings, latency, an SLO, or permission to
connect Tool Calling to production reports.
