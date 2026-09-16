# Catalog-native saved-evidence Qwen synthetic canary

Registered: 2026-09-16, before implementation and any CQ provider request.
Baseline: `3bd02fc5badbc25ccf873a49ce8c04b53c681d6c` (PR #151).
Protocol identity: `report_evidence_catalog_qwen_canary_v1`.
Transport identity: `report_evidence_catalog_qwen_transport_v1`.

## Question, observations and authority

JQ01 made two paid requests but only performed a literal lookup; the long query
matched no saved source. Its accepted final JSON was an abstention, not a read
followed by an evidenced answer. JQ02 is unrun. The local JQ summary and case
were re-read before this change. JQ/SQ/FQ and v8 stay closed, with their original
bytes and failure interpretations.

The catalog wrapper and its separate adapter now pass intercepted HTTP tests.
That is not a native model closure observation. This batch asks whether the
exact model can select a visible saved record, actually read it, and return
strict final JSON in the SAME conversation. A missing-text control must first
observe missing text through the tool, not infer absence from a title.

The user previously approved synthetic-only exact Qwen calls under USD 0.10
and at most six sequential requests, then explicitly said not to seek repeated
approval for equivalent low-cost continuations. This continuation authorizes
ONE fresh CQ batch after offline tests, independent review and committed
identity freeze. Tighten the batch to **four sequential requests**, two per
case, USD 0.10 total soft stop, accepting a small single in-flight overshoot.
Only the parent operator may execute paid work. No unused old allowance is
reused, and failure does not authorize a replacement batch.

No real reports, benchmark source text, reserved cohorts, external searches,
retries, redirects, repair, fallback, recovery, model replacement or production
activation. The two fixtures are invented, not new independent evaluation data.
No scoring formula, CrewAI version, prompt caching or production gate changes.

## Frozen fresh fixture and required observations

Fixture: `tests/fixtures/report_evidence_catalog_qwen_canary.json`.
Raw-byte SHA-256:
`f0426492e137c33214fc6db7063b89f790f4d19ee416b07eeebff0014313b60c`.

Each case has six sources in fixed order; the target is sixth, beyond the old
five-hit boundary. Every source has publisher `Synthetic example`, access date
`2026-09-16`, and no URL/DOI. The top-level target ID is a gate label, not model
input. Only the question and normal snapshot projection reach the wrapper/model.
The model sees all six unranked titles/IDs, not an expected answer or target hint.

| Case | Target and content | Mechanical requirement |
|---|---|---|
| CQ01 | A6, ceramic humidity resonator; shift 24 kHz at 60% relative humidity; no outdoor deployment or long-term stability study | Native read of the complete A6 saved text, exact paired delivery in the second accepted HTTP request, accepted evidenced answer citing the actual receipt |
| CQ02 | M6, harbor filtration venture revenue record; summary absent | Native M6 read, paired missing_text delivery in the second accepted HTTP request, accepted abstention with no evidence IDs or successful-read receipts |

CQ01's other titles concern temperature, film absorption, chamber service,
pressure and optical probes. CQ02's distractors are funding, another venture,
a prototype, a market overview and licensing. They test a bounded discovery
path, not a representative retrieval distribution or a general ranking metric.
Questions name the intended subject; easy synthetic selection must not become
a claim of realistic evidence-gap planning accuracy.

Exactly two observed, accounted requests and one actual read are required per
passing case. Wrong source, early abstention, no-tool answer, partial read,
title-only citation, missing paired delivery or failed final parsing fails.
For CQ02, claiming absence without a read also fails. First failure stops the
whole batch and leaves later cases explicitly unrun.

After the mechanical result, the parent separately inspects CQ01's answer for
the 24 kHz / 60% condition and both testing limitations, and CQ02's lack of
invented revenue. Record this as a narrow AI content observation, not human
review, independent accuracy or general entailment. Do not retrospectively
relax a mechanical failure because its prose looks plausible.

## New runner, immutable identities and publication

Add a separate module `report_evidence_catalog_qwen_canary.py`, root CLI
`report_evidence_catalog_canary.py` and dedicated test file. Keep all 98
protected old source/configuration/protocol/result/fixture artifacts unchanged.
Reuse immutable helpers only by direct calls with explicit inputs. Do not
monkeypatch old globals, loosen the five-hit adapter or alter the catalog wire.

Create a fresh CatalogQwenFollowupTransport bound to each case snapshot and
share one CatalogQwenLedger. Its manifest truthfully remains an offline adapter
contract, not a grant. A separate code-owned experiment manifest and explicit
authorization/identity records bind the live runner scope, configuration,
fixture and implementation commit before dispatch; do not overwrite or
misrepresent the inherited manifest. The runner independently enforces four
requests in addition to the ledger's six-request ceiling. No caller-defined
manifest or CLI flag may bypass fixed fixtures and limits.

Default CLI behavior verifies identity only, without reading keys, creating
output or sending requests. Live mode requires the exact protocol
acknowledgement, full implementation SHA and fixture SHA. A CLI acknowledgement
is operator intent, not independent user-consent verification. Verify committed
blobs AND actual disk bytes for every executing dependency, all new files and
the protocol; bind dependency versions to uv.lock. Follow the existing fixed
LF comparison contract, reject symlinks/junctions and status-hidden edits.
Identity drift before a call stops it; drift after a response preserves observed
usage but prevents further work. Unrelated private worktree dirt is preserved.

Use a fresh, exclusive child of outputs with an existing real parent directory.
Persist setup before any HTTP. Case and summary records publish write-once only
after complete flush/fsync/close, with no overwrite or recovery fallback. A
complete-looking provisional file is not a committed pass. Publish failed and
unrun facts truthfully; unresolved intent, setup/final persistence failure or
unknown usage prevents additional requests. This is a local single-owner
experiment, not distributed admission, hostile-process isolation, directory
power-loss durability or provider exactly-once execution.

## Credentials, wire and cost

Use only process DASHSCOPE_API_KEY and the frozen official Beijing endpoint:
`https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions`.
The parent may load only that assignment from the existing project .env into
the invocation process if necessary. Do not print the value, save it in
artifacts, alter .env or durable environment, or borrow another provider key.
Imports and identity-only mode must not load dotenv or discover a credential.

Keep exact `qwen3.5-plus`, non-thinking/non-streaming, temperature zero,
no parallel calls, 512 output tokens, full 12 KiB request / 64 KiB response,
10-second connect / 60-second owned request deadline, TLS, trust_env=False,
zero retries and no redirects. First request exposes only the six-ID read
schema with auto; final-only uses none, omits tools and requests JSON Object.
Keep strict core validation and full saved-window comparison before reservation.

The [official pricing table](https://www.alibabacloud.com/help/en/model-studio/model-pricing)
was checked on 2026-09-16. Beijing non-thinking prices range from USD 0.115/0.688
to 0.573/3.44 per million input/output tokens across context tiers. Retain the
existing conservative highest-tier rates, 16384-input reservation and
USD 0.011149312 per possible request. Four reservations total USD 0.044597248,
below the USD 0.10 soft stop. Estimates and reservations are not invoices.
The alias and reported response-model string are not independent backend
version attestation; no model migration is permitted if identity is rejected.

Track actual HTTP/usage, complete canonical request hashes, native call IDs,
paired payloads, catalog receipt observation and strict final result separately.
Forwarding into a callback alone is not HTTP delivery. Every received failure
retains reported usage; unknown usage remains lower-bound with no retry.
Semantic support stays not_assessed and answer verification not_verified.

## Verification, stop and follow-up

Starting suite passed 4098 tests / 1370 subtests in 128.87 seconds. Before live
use require full final suite, focused runner tests with the real wrapper and
intercepted HTTP, latest Ruff, narrow Pylint, offline lock and independent
read-only review. Test default no-key/no-output behavior; hidden source drift;
all setup/publication failures; true four-request shared accounting; fresh
per-case state; correct sixth-ID selection; wrong/partial/no-read negatives;
known/unknown usage and first-case failure blocking CQ02 at the HTTP seam.
Re-inject first-failure continuation or a gate bypass into NEW code only,
require an actual extra-request/failure assertion to turn red, restore exact
source hashes and rerun. Do not weaken assertions or add skips.

Freeze the final implementation identity before the single parent-run batch.
Publish only qualified aggregates and artifact hashes; raw traces remain local.
Close the batch after pass or failure without automatic retuning or another
paid attempt. Two mechanical passes still do not authorize production routing,
evidence-gap search, broad semantic claims or user-value claims. Production
integration requires its own admission, ownership, privacy and value gates.
