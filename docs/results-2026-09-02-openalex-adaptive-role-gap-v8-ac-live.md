# Adaptive role-gap v8 AC live-provider result

**Executed:** 2026-09-02

**Authorized merged revision:**
`59b5870614d23c0d9c61e7e398fa363026b6a528`

**Fixture SHA-256:**
`0be98f249bfd1eaf891cd3c20903b9d6ae4cd2d6431282ee32e82298a2d8ecc7`

**Cohort opened:** AC01-AC08 development only

**AD01-AD08 opened:** no

**Production connection:** false

**Model calls:** 0

**Provider-reported anonymous-budget usage:** USD 0.015

## Authorization and preflight

The owner separately authorized at most sixteen sequential anonymous OpenAlex
requests, a total soft stop of USD 0.02, and a single in-flight overrun. Retry,
redirect, model calls, recovery, supplementary search, AD access, and
production connection were forbidden.

Execution used a detached worktree at the exact merged revision. Before the
live flag was supplied, the default zero-network preflight verified:

- the exact fixture bytes;
- AC01-AC08 and all eight anchor plus forty possible closure identities;
- all six frozen implementation hashes;
- a maximum of sixteen requests and ninety-six provider rows;
- zero authorized model calls;
- the anonymous no-key mode and absent `OPENALEX_API_KEY`; and
- false production, report-workflow, recovery, and planner connections.

The preflight made zero provider requests. The live run then wrote to a fresh
write-once output directory.

## Execution outcome

The execution completed its mechanical boundary:

- 15/15 requests completed;
- every request had exactly one outbound attempt;
- all provider request IDs and idempotency keys were unique;
- 8/8 anchor requests completed;
- 7/7 selected closure requests completed;
- AC08 observed every frozen role and correctly emitted
  `abstain_no_mechanical_role_gap` instead of spending a closure request;
- 8/8 case portfolios were committed before the next case;
- known provider-reported cost was USD 0.015, below the USD 0.02 soft stop;
- request latency ranged from 645.631 ms to 2,424.569 ms, with 19,057.293 ms
  summed request latency; and
- final execution state was `completed` with
  `eligible_for_source_lock`.

The latency range is a description of these fifteen requests. It is not a p95,
SLO, throughput, or reliability claim.

OpenAlex returned ninety accounted rows. Seventy-two rows retained a
reconstructable abstract and eighteen were mechanically rejected because no
abstract could be reconstructed. This is provider-schema accounting, not a
source-relevance judgment. DOI-first and canonical-URL deduplication produced
sixty-four unique candidates and eight cross-lane duplicate occurrences.

## Per-case mechanical observations

| Case | Anchor roles observed | Missing roles | Route | Selected closure role | Anchor valid | Closure valid | Provider rejected | Unique |
|---|---:|---:|---|---|---:|---:|---:|---:|
| AC01 | 3/5 | 2 | search | `engineered_pet_hydrolase` | 6 | 6 | 0 | 12 |
| AC02 | 2/5 | 3 | search | `cell_free_biosynthesis` | 6 | 4 | 2 | 10 |
| AC03 | 3/5 | 2 | search | `flow_cell_operation` | 4 | 3 | 5 | 7 |
| AC04 | 4/5 | 1 | search | `wear_duration` | 4 | 5 | 3 | 8 |
| AC05 | 4/5 | 1 | search | `humid_building_envelope` | 6 | 5 | 1 | 9 |
| AC06 | 2/5 | 3 | search | `manganese_oxide_ion_sieve` | 4 | 4 | 4 | 6 |
| AC07 | 1/5 | 4 | search | `wastewater` | 5 | 5 | 2 | 7 |
| AC08 | 5/5 | 0 | abstain | — | 5 | 0 | 1 | 5 |

These are deterministic lexical observations over the returned title and
abstract fields. They do not establish that a missing role was truly absent,
that a selected route was correct, or that its closure added useful evidence.

## Artifact integrity

The run produced thirty-nine files: thirty-eight source artifacts named by
`artifact-index.json` plus the index itself. Independent SHA-256 recomputation
found 0/38 mismatches.

The indexed boundary contains:

- the manifest and final execution artifact;
- fifteen lane journals;
- eight route journals;
- eight case portfolios;
- complete provider-row, route, and unique-candidate CSV files;
- sixty-four blank candidate-review rows;
- eight blank case-review rows; and
- hashes for every preceding source artifact.

All sixty-four candidate rows and eight case rows have empty human labels.
`human_review_state` remains `not_prepared`, `source_lock_state` remains
`not_created`, and `source_value_state` remains `not_evaluated`.

## Mechanical interpretation

The live-provider stage passes only the frozen execution and accounting
boundary. It establishes that the adaptive 8-to-16-request sequence can run
against anonymous OpenAlex with a durable route between the anchor and optional
closure request.

It does not yet pass or fail the six source-value gates:

- candidate-pool precision at least 25%;
- relevant novel evidence in at least 6/8 cases;
- selected closure value in at least 4/8 cases;
- human-correct routing in at least 6/8 cases;
- human coverability in at least 6/8 cases; and
- coverability gain over anchor-only retrieval in at least two cases.

None of those metrics may be inferred from the router's lexical observations.

## Next boundary

The next step is a separately implemented, zero-network source lock and Schema
v2 human-review boundary tied to this exact artifact index. It must expose the
frozen baseline, role definitions, route, and source title/abstract while
keeping aggregate answers unavailable to the reviewer. Intake must preserve
the reviewer's raw declaration, distinguish incomplete or ineligible review
from a pass, and calculate all six gates only after every required label is
present.

AD01-AD08 remain unopened. This completed provider run does not authorize
tuning on AC, rerunning AC as validation, opening AD, connecting v8 to the
planner, or connecting Tool Calling to production.
