# Anonymous OpenAlex evidence-gap study — live-value protocol

**Frozen:** 2026-08-27, after implementation and zero-network seam tests but
before any anonymous OpenAlex request or human label

**Production connection authorized:** no

**Live provider requests authorized by this document:** no; execution still
requires a separate explicit authorization naming the frozen revision, request
cap and soft stop

**Human labels authorized by this document:** no; any returned packet requires
its own source lock and reviewer declaration

## Why this narrower protocol exists

The original Phase 4 study required both OpenAlex and Lens credentials. The
project owner does not want to configure either key, and Lens access may add a
separate paid dependency. Removing the entire value study would leave the
academic adapter's real-provider compatibility and candidate value completely
unobserved.

OpenAlex documents a smaller anonymous API budget that does not require an API
key. This protocol therefore isolates the four already-frozen academic cases
and measures only the OpenAlex branch. It does not weaken or rewrite the
credentialed Phase 4 contract, and it does not convert anonymous access into a
claim of free, unlimited, or production-ready retrieval.

Official access and pricing references frozen with the protocol:

- <https://help.openalex.org/api/>;
- <https://help.openalex.org/access/pricing/>; and
- <https://help.openalex.org/access/example-costs/>.

## Frozen inputs and implementation identities

The study reuses the byte-identical Phase 4 challenge fixture:

- fixture: `tests/fixtures/evidence_gap_phase4_domain_challenge.json`;
- fixture SHA-256:
  `f9eee1fcf2ff5acb75e9da840b94baa43e3b10f7e3136dec9886c3a572663a24`;
- cases: D01, D02, D03 and D04, in that order;
- provider: OpenAlex;
- tool: `academic_search`; and
- one pre-authored query and at most one request per case.

The live runner must verify these implementation identities before reserving
output or constructing a transport:

- `src/academic_agent/tools/anonymous_openalex_search.py`:
  `bcaa201622fe5241115661cd9d5a6f7616761eddfedb9acf364b3693e7a044c9`;
- `src/academic_agent/tools/domain_evidence_search.py`:
  `ae79c38378321f6ce4481e682787ee49f930ec4c34b696d404fcf78d97b2eeab`;
- `src/academic_agent/evidence_gap_execution.py`:
  `5b1b94ebd8130834603567f25336dcf106d58653e6bdd2b862509d396639e8fe`;
- `evidence_gap_phase4_audit.py`:
  `e70c2e015ffc5a01b1f9e35634dd65b9a37062bc561b9deaff8fbfa3bfb09477`.

Any mismatch creates a new experiment and must stop before adapter
construction, output reservation, or provider work. A future live
authorization must also name the exact merged Git revision; this document does
not authorize whatever bytes happen to be present in a working tree.

## Anonymous request boundary

The existing Phase 4 OpenAlex parser remains unchanged. A separate adapter
composes it with a transport seam that requires one local non-secret sentinel,
removes that sentinel before the outbound request, and rejects unexpected
hosts, paths, fragments or sentinel multiplicity. The actual network endpoint
must contain no `api_key` query parameter.

The live path refuses to start if `OPENALEX_API_KEY` is configured. This is a
fail-closed identity rule: the study measures anonymous access and must not
silently consume a personal credential or a larger keyed budget.

The adapter and runner remain disconnected from `pipeline_worker.py`, the
production evidence registry, delivered reports and the phase-1 shadow
planner. Returned rows enter only the study's quarantine, audit and review
artifacts.

## Live execution protocol

Dry-run is the default and opens zero sockets. A live run additionally requires:

1. `--execute-live`;
2. a fresh output directory;
3. an explicit anonymous-daily-budget acknowledgement;
4. a positive provider-reported soft stop no greater than USD 0.01;
5. no configured `OPENALEX_API_KEY`;
6. exact fixture and implementation hashes; and
7. a separate user authorization for the exact merged revision.

The hard cap is four requests. Each attempted case owns exactly one request,
with no internal retry, redirect following, source-page fetch or model call.
The complete expanded manifest is written before the first request; each case
journal is committed before a later case may start.

Provider-reported `meta.cost_usd` is accumulated against the soft stop. The
runner checks the total before the next case. One in-flight request may make
the observed total slightly exceed the line. Missing or malformed accounting,
a failed request, or an exhausted soft stop produces an explicit partial state
and prevents later requests. It is never rewritten as zero cost or completion.

## Write-once artifacts

A finalized execution contains:

- `manifest.json` with the full frozen inputs and identities;
- `case-executions/D01.json` through the last attempted case;
- `execution.json` with request, completion and cost state;
- `candidates.csv` containing every candidate and provider rejection;
- `review.csv` with one blank row per quarantine-accepted candidate; and
- `artifact-index.json` with hashes for all aggregate source files.

Every artifact fixes `production_connected=false`,
`report_workflow_connected=false` and `api_key_used=false`. An existing output
path is never reused or resumed.

## Frozen value gates

If and only if all four provider requests complete with inspectable accounting,
a later source-locked human review may evaluate the existing Phase 4 gates for
the academic provider:

1. at least one quarantine-accepted candidate in at least 3/4 cases;
2. no more than 5% of accepted candidates labelled directly irrelevant; and
3. at least one directly relevant, materially baseline-absent candidate in at
   least 3/4 cases.

Every candidate URL must be attempted, baseline context must be visible, and
substantive generative-AI judgment is ineligible. Zero candidates, incomplete
labels, unavailable sources, source drift or uninspectable execution
accounting is a non-pass, never a clean zero-error result.

Passing would justify only a separately pre-registered planner-trigger study.
It would not authorize production connection.

## Explicit non-claims

The implementation, a later live run, or even an eligible value-gate pass does
not establish autonomous Agent tool choice, planner-trigger precision,
provider-wide precision, source truth, report improvement, user utility,
adoption, cost savings, latency, an SLO, or production Tool Calling readiness.
