# Isolated Reviewer comparison v2

This credential/preflight security successor reuses the exact fixture, complete
Reviewer instruction arms, six request bytes/order, model/parameters and semantic
rubric from `aa1c591526db40683413073e3c759ab690e7b013`. The instruction roots remain
`ee0a00e442735cb78c6950eb55d0e4fe1398a9bf` and
`ff5dcee18f91672ea368e2bdb110f02377df80d5`. The fixture retains its v1 schema and
historical provenance verbatim; these are reused synthetic development controls,
not fresh held-out data. V1 is closed after zero POSTs. Its output and identities
are never imported, modified, removed or replayed.

The [v2 protocol](../../docs/prereg-2026-09-30-reviewer-comparison-v2.md) owns
authority and acceptance. This is a direct native instruction experiment with
source-locked extracted `_apply_reviewer_corrections` and `validate_final_report` plus explicit
length/citation retention, not the complete CrewAI wire/guardrail, Writer/Scorer,
general semantic correctness, or production activation. No-op plans can be
mechanically complete without semantic gain; partial application is incomplete.

## Three modes and credential boundary

`uv run python -m evals.reviewer_comparison_v2.runner` is read-only identity.
Import is standard-library-only. Default preparation is required to read no
credentials, create no experiment output and make no HTTP/DNS/socket request.
Earlier dotenv-only attempts exposed unrelated framework authentication; static
diagnosis also found CLI settings and tracing-consent paths. Those failed
observations are retained, not relabelled as private successful imports.

Before any v2 native request, the preregistered execution scope changed to
`source_loader.py`: normalized hash-locked source, with exactly the CrewAI
TaskOutput import and four unmeasured guardrail factories omitted. All other
AST nodes retain their structure, order and locations. Actual Pydantic models,
validators, serializers and helper function bodies run in an explicitly named
derived dictionary, not `academic_agent.evidence`, a fake module or a complete
production import. No fake TaskOutput, vendor hooks, environment flags or CLI
configuration are supplied. The scoring factory is not executed; its original
production formula/source bytes are unchanged. DecisionContext's complete
stdlib/Pydantic source is compiled in a separately labelled dictionary as well.
Its postponed annotations are completed by the real Pydantic `model_rebuild`
with that verified dictionary; no annotation or field is rewritten.

The manifest binds both source descriptors, located AST-v1 identities, exact
five-node omission rules, loader bytes and dependency versions. Empty 3.12
`type_params` fields are excluded explicitly for 3.11/3.12 AST portability;
other retained AST fields/locations are bound. Compilation uses
`dont_inherit=True, optimize=0`. Actual compiled-code hashes additionally enter
execution identity with the exact Python version/cache tag; they are not
universal cross-interpreter hashes.
The code encoding is explicit recursive fields/constants, not `marshal`'s
reference-count-sensitive object graph. Retaining diagnostic references cannot
change the identity of otherwise identical code. Cached exports/functions and their actual
code filenames are rechecked on use. This is not protection against a malicious
in-process Python writer or a general network sandbox: unused URL-check code
is retained but not exported by the measured loader.

Pydantic 2.12.5 and pydantic-core 2.41.5 are required. Installed plugin entries
must be empty; unknown populated/loading/malformed caches or replaced discovery
functions refuse before models are created or cached helpers are returned.
No plugin is disabled to manufacture an empty observation. The same gate applies
to DecisionContext. All six rendered request hashes must match the old targets.

Fresh-process tests use `-B`, a test-owned TEMP/TMP boundary and cumulative
startup-through-exit audit checks. Credential/settings/consent paths are denied
before any runtime-cache permission, including filesystem probes. Framework
imports, HTTPX clients and DNS/network are denied independently. A swallowed
guard exception still fails at exit. Python/dependency bytecode or ordinary
temporary probes are distinct from evaluation artifacts; no vendor config
cache is admitted. Ordinary pytest compatibility does not establish privacy of
other tests' framework imports or retroactively certify earlier collection.

After exact committed identity freeze, independent review and green CI, the
parent may explicitly select **one** of `--credential-preflight` or `--live`,
with `--expected-commit <full-sha> --expected-identity <sha256>
--reviewed-ci-commit <same-full-sha>`. The CI flag is an operator attestation,
not remotely verified CI or independent budget authority. Dirty tracked files,
uncommitted inputs, missing historical Git objects, drift and occupied v2 output
refuse admission. Shallow identity-only preparation does not fetch history.

Credential preflight prints only `syntax_admitted` with
`provider_authentication: not_checked`, or the fixed
`credential_preflight_failed` disposition. It creates no client, claim or file.
It is not provider authentication, a syntax ticket or permission for dispatch.
The live process independently repeats every gate, reads once, rechecks source,
commit, dependencies and request identity, then uses that same in-memory key.

The only key source is the fixed project `.env`, read-only and bounded to 64 KiB.
Only the exact left-hand name `DASHSCOPE_API_KEY` is interpreted. Other values,
including references to that name, are ignored without parsing or expansion.
Physical LF/CRLF and an optional initial BOM are recognized. A bare token or
matching outer quotes is accepted without unescaping, decoding, normalization,
or trimming the RHS/quoted interior. Optional literal `export` and horizontal
spacing before the name/equals are syntax. Selected inline comments, whitespace,
controls, non-ASCII, duplicate/missing/empty assignments, broken quotes,
substitutions, backslashes, stars and ellipsis masks fail closed.

Admit the complete RFC 6750 b64token alphabet, preserving punctuation and all
trailing equals signs, within a local 10-256 ASCII-byte bound (not a vendor key
length claim). There is no inherited-environment fallback, alternate path or
credential override. `SecretKey` has redacted representations and is not
serialized or hashed. Python secure memory erasure is not promised. File reads
necessarily touch neighboring bytes; no other variable is interpreted or logged.
Syntax admission does not establish plaintext completeness, provider validity,
region, quota or billing.

## Claim, transport and artifacts

Only after all gates, the one key read and repeated identity validation may
exclusive mkdir claim `outputs/reviewer_comparison_v2_native`. Identity,
manifest and claim journal are flushed/fsynced before client creation. Competing
native processes cannot both create a client. Credential failure before claim
leaves no output. Any postclaim failure preserves the occupied batch, including
zero-POST failures; never retry, resume, delete, replace or change its directory.

The fixed DashScope endpoint uses exact `qwen3.5-plus`, non-thinking JSON Object,
temperature zero, 1,500 output tokens and httpx 0.28.1. No SDK, tools, redirects,
proxy/environment trust, retries or fallback. TLS remains verified. Requests are
bounded to 48 KiB and whole responses to 128 KiB. Timeouts/elapsed checks are
bounded but not hard cancellation of synchronous socket reads.

Each of at most six sequential POSTs follows exclusive request persistence and
an append/flush/fsync reservation. Frozen input/output rates USD 0.573/3.44 per
million reserve 16,384 input + 1,500 output tokens: USD 0.014548032 each and
USD 0.087288192 for six, below the USD 0.10 soft stop. This is neither tokenizer
proof, provider invoice nor guaranteed in-flight cap. Reservations are not
recycled. Unknown usage is unknown, never zero; faults stop later requests.

Strict JSON parsing, an exact raw-byte credential screen, and a complete bounded
decoded-key/value/nested-escape screen MUST succeed before response bytes or
their digest persist. Numeric scalars are screened using their actual JSON
serialization as well: a valid all-digit Bearer token is not excluded from
credential protection merely because JSON parsed it as a number. Exponent
spellings can also change between the raw response and serialized value.
Malformed/echo/unfinished-screen responses leave neither body nor hash;
`response_sha256` remains null. Candidate usage, including derived cost, passes
its own decoded and actual-ledger-serialization credential screens before it
can replace the safe unknown state. Unsafe counts/cost remain unknown, never
zero, including in the stopped record. Independently safe numeric usage is
retained on a separate content echo or later content/mechanical failure. The
initial unknown representation is screened too; if even it is unsafe, only the
existing reservation remains unresolved. This is not a universal encoding detector.

Artifacts can include identity/manifest, requests, admitted responses, exact
model JSON, patch delivery/errors, final Markdown, usage/reservation journal and
mechanically complete blind packets. Do not publish raw output by default.
Exclusive mkdir/fsync is local ownership, not directory durability everywhere,
disk-loss safety, a malicious-writer defense, distributed locking or provider
exactly-once delivery. A double identity check is not an immutable environment.

## Judgment, verification and closure

The parent shuffles/renames blind packets and provides only their contents in a
fresh LLM context: supplied sources, original draft, actual final and unchanged
rubric. No arms, instructions, intermediate findings, reasons, expected edits
or prior judgments. Preserve first judgments and unavailable backend metadata.
Sources establish measurement facts; the draft is the object under review, not
reference truth. Missing/uncertain observations never manufacture success.
All three candidate deliveries must be mechanically complete and supported;
gain additionally needs one definite baseline mixed/unsupported to supported
pair and no regression. Both arms passing means gain unobserved.

`uv run pytest -q tests/test_reviewer_comparison_v2.py` exercises the inherited
64 control intents and new synthetic credential/claim/response seams, including
actual httpx request serialization through MockTransport. Tests deny real `.env`
and sockets. Fresh-process identity/helper tests deny framework imports and
configuration reads, and negative controls reject experiment mkdir/writes at
both Path and OS seams. Extraction tests exercise exact omissions, real model
validation/serialization, plugin refusal, derived-code drift and compiled-body
fidelity. Compiled-body equality alone is not runtime serialization proof.
Defect
reinjection must fail targeted assertions, followed by byte-identical restoration.
Parent owns full-suite/latest-lint/CI, independent strong review, final commit
freeze and any separately authorized native use. Test doubles are not native
quality or provider authentication evidence.

Source hashes normalize CRLF to LF outside this byte-preserved eval directory.
The manifest binds fixture, this README/attributes, credential/runner, tests,
protocol, extracted source descriptors and dependency versions/files. Fixture, manifest
and request bytes are not normalized. Keep this preparation unmerged at its
reviewed commit after the batch; main receives qualified documentation only.
No old protocol, output, label, production route/config or scoring changes.
