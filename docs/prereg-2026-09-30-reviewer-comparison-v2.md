# Reviewer comparison v2: credential-safe execution successor

Registered on 2026-09-30 from main
`b818b9f2cf772390564f4d9e8ebc04afb47781c1`, before any v2 native request.
Method: `reviewer_comparison_v2`. The old
[v1 protocol](prereg-2026-09-30-reviewer-comparison.md) and
[pre-dispatch failure](results-2026-09-30-reviewer-comparison-preflight.md)
remain closed and unchanged.

## Motivation and unchanged comparison

An authorized value-free local check found the selected credential has valid
Bearer syntax but falls outside v1's narrower alphabet. The owner confirmed
it matches the console original. Neither fact authenticates it at the provider.
The new executor preserves a complete RFC 6750 `b64token`, rather than
discarding punctuation or expanding arbitrary shell/dotenv syntax.

Reuse the same three synthetic development controls and the exact old/current
Reviewer instruction blocks, fixed order, six rendered requests and frozen
semantic rubric from preparation
`aa1c591526db40683413073e3c759ab690e7b013`. Those controls were prepared and
inspected, but v1 sent none to a model. This is an explicitly dependent
development successor, not fresh held-out data or a retuned quality reference.
No claim, instruction, expected edit, source text or semantic threshold changes.

The scientific question remains whether comparison-fidelity instructions
correct a misassigned physical measurement and its dependent false target,
while preserving true instrument error, caveats and qualified independent
experiment proposals. Apply actual native plans with production correction
application and report validation; this is not the complete CrewAI workflow.

## Selected credential and explicit preflight

The new implementation lives only in `evals/reviewer_comparison_v2/` with its
own tests, protocol, manifest, execution identity and fixed output. It does not
import or reopen v1, change production credentials or add a provider fallback.

- Default import/identity mode reads no credentials, creates no evaluation
  batch/request/receipt/answer artifact and makes no HTTP/DNS/socket call,
  including indirect dotenv and framework authentication import paths. Python
  and dependency runtime-cache initialization is not a claim of absolute
  filesystem purity; it cannot admit a credential/configuration store.
- Explicit `--credential-preflight` checks only the authorized
  `DASHSCOPE_API_KEY` selected from this project's fixed `.env`. It requires
  committed source/request/dependency identity plus reviewed/green-CI identity.
  It creates no client, batch claim, evaluation file or model request. Public output is
  a fixed syntax disposition with provider authentication `not_checked`.
- Preflight is not a credential ticket or native allowance. The formal live
  process performs all gates independently, reads once and uses that same
  in-memory credential without a later reread or environment override.
- Select exactly one literal assignment by its left-hand variable name;
  never expand or use other variables. Read at most 64 KiB as UTF-8 with an
  optional initial BOM, recognizing LF/CRLF physical lines. Reading the whole
  file necessarily touches other bytes; only the selected value is used.
- Accept a bare value or matching outer single/double quotes. Do not unescape,
  interpolate, decode, normalize or trim quoted interiors. Whole-line comments
  are permitted, selected inline comments/ambiguous trailing text are not.
- Admit complete RFC 6750 Bearer token syntax within a local 10-256 ASCII-byte
  bound. This bound is not a vendor key-length rule. Preserve every admitted
  character, including punctuation and all trailing `=` bytes.
- Refuse controls, whitespace, non-ASCII, missing/duplicate/empty assignments,
  malformed delimiters, substitutions, backslashes and obvious mask/ellipsis
  forms. Never remove suspicious characters to manufacture an accepted key.
- Secrets remain memory-only with redacted representation. Never publish their
  text, position, length, shape, count, digest or exception detail. Reliable
  erasure of Python memory is not promised.

The selected native credential is not part of the manifest or execution hash.
An accepted syntax does not prove plaintext completeness, provider validity,
region compatibility, quota or billing availability.

## Source-locked helpers instead of framework initialization

Static diagnosis of the normal production import exposed authentication,
CLI settings and tracing-consent configuration paths unrelated to this direct
Reviewer comparison. Do not grow a series of vendor credential exceptions or
pretend a fake TaskOutput is the real class. The v2 measurement instead uses a
separately named, source-locked extraction of the production implementation
functions and Pydantic models; it is not the normally imported complete module.

Verify the normalized source-byte identity before parsing. Omit exactly the
single top-level `from crewai import TaskOutput` and four unmeasured top-level
factories: `make_scoring_guardrail`, `make_evidence_guardrail`,
`make_final_report_guardrail`, `make_reviewer_guardrail`. Match their exact
node kind, name, location and structure, then retain every other node and its
order unchanged. Refuse additional references to the omitted names or a changed
omission set. No annotation stand-in, fake schema or production module identity
is supplied; production source and historical byte locks stay untouched.

Compile only the verified derived tree with `dont_inherit=True, optimize=0`
in an explicitly labelled derived namespace. Bind the loader, source bytes,
exact omission rules and derived identity in the manifest. AST identities may
be portable within their stated encoding; bytecode comparisons/hashes are
Python-version-qualified, never a claimed universal 3.11/3.12 identity.
The included scoring computation is unmodified, but the omitted scoring and
other guardrail factories are not executed or validated by this experiment.

Admit only the frozen Pydantic/pydantic-core dependency identity and an empty
Pydantic plugin-entry-point set; unknown installed or cached plugins stop
before model creation. DecisionContext uses its authentic stdlib/Pydantic
implementation. Re-render all six requests and require the existing v1 target
hashes without updating them to accommodate a serialization difference.

Runtime verification must exercise the actual extracted models, JSON validation,
serialization, correction application and final-report checks. Cold CLI and
owned repeated calls must not import CrewAI/core, access vendor credentials,
settings or consent stores, create clients, dispatch DNS/network or create
evaluation artifacts. Keep the strict cumulative audit and direct vendor-import
negative control, not only a returned success flag. Retained source still
defines unused URL-check helpers; extraction is not a general network sandbox.

Ordinary pytest compatibility and fresh CLI privacy are separate observations.
Do not retrospectively certify earlier unwrapped full-suite collection, or the
earlier dotenv-only focused attempts, as free of framework credential reads.
No native v2 request preceded this change of execution scope. The fixture,
rendered inputs, instructions, order and semantic rubric remain unchanged;
the loader change must be disclosed rather than claiming full production
module, complete guardrail or CrewAI-wire equivalence.

## Native gates and accounting

Keep at most six sequential synthetic requests to the fixed DashScope
compatible endpoint and exact `qwen3.5-plus`, non-thinking JSON Object output,
temperature zero and unchanged bounded output. Total soft stop USD 0.10;
the owner's standing bounded low-cost grant applies within this scope.
No retries, redirects, repair, fallback, resumed execution, search, extra paid
judge, real report transfer or production activation is authorized.

Gate source/commit/dependency/request identity, review/CI attestation and budget
before reading the selected key. Recheck execution identity after that one
read and before exclusive batch creation. Claim a fresh fixed v2 output
durably before client creation, and reserve every possible POST durably before
dispatch. Competing invocations cannot both obtain that local claim.

A preclaim credential failure leaves no batch artifact and permits only later
explicit syntax checking, not model dispatch. After a claim, any failure keeps
the batch occupied and closed, even when no POST was reached. Preserve v1's
existing occupied directory; do not delete it or reuse its allowance.

Capture valid numeric usage before later model/content/correction failure.
Unknown usage is not zero and stops later requests. The rate estimate and
reservation are not an invoice or monetary hard cap; an in-flight request can
slightly exceed a soft stop. No input reservation is a tokenizer proof.

Persist a response body/digest only after strict JSON parsing and the bounded
credential-echo screen succeed. Malformed responses, credential echoes or an
unfinished screen retain no body or response digest; a raw credential response
must not leave a digest of the secret. Already safely observed numeric usage
remains separate. This screen is not a proof against every possible encoding.

The double identity check and exclusive directory apply to a local single-owner
execution. They are not an immutable environment against malicious concurrent
source writers, distributed ownership or provider exactly-once delivery.

## Mechanical and semantic outcomes

Mechanical acceptance, source identity, report support and publication remain
different gates. A partial/unapplied plan, transport fault or unknown usage
stops later native requests; a mechanically valid semantic miss is retained
for subsequent judgment, not repaired or retried.

After the batch, a fresh LLM context receives only arm-hidden supplied sources,
the common original draft, actual delivered reports and the unchanged rubric.
Hide instruction arms, expected edits, reasons, prior reviews and desired
outcomes. Sources determine measured facts; the draft is not reference truth.
Preserve qualified hypothetical proposals without pretending they were measured.

Use `supported`, `mixed`, `unsupported`, `uncertain`, `not_reviewable`.
All three candidate reports must be mechanically complete and supported; a
local paired gain additionally requires at least one definite baseline
mixed/unsupported result to become supported with no regression elsewhere.
Both arms supported throughout means no observed gain. Missing or uncertain
baselines cannot manufacture improvement. Preserve the first fallible LLM
judgment and disclose unavailable backend metadata and blinding limitations.

## Verification and closure

Before native dispatch, run the full zero-provider baseline and updated suite,
latest Ruff, narrow Pylint, an independent strong review and green CI at the
exact committed preparation identity. Add synthetic seam tests for exact
serialized Authorization bytes, key/identity failure before claim, explicit
preflight without client/output, postclaim occupation and safe usage retention.
Reinject the old alphabet, early claim, key transformation/fallback, missing
second identity check and pre-screen response digest; require target assertions
to fail, then restore the same source bytes. Never weaken old assertions or skip.

Keep the execution preparation unmerged after this batch, linking its immutable
commit from qualified documentation on main. Old protocols/results/labels and
v1 artifacts are unchanged. Close v2 after success, failure or early stop; no
output replacement, consumed-batch replay or automatic production release.

Sources: [Bearer syntax, RFC 6750 section 2.1](https://www.rfc-editor.org/rfc/rfc6750.html#section-2.1),
[Alibaba Cloud API-key handling](https://www.alibabacloud.com/help/en/model-studio/get-api-key).
