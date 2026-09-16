# Bounded saved-source catalog: offline discovery contract

Registered on 2026-09-16 before implementation. Baseline:
`f775cdcd529eb311bf9bc8d1171d35d7981964bb`. Method identity:
`report_evidence_catalog_v1`. This registration authorizes no live requests.

## Observed problem and free measurement

The closed [JQ batch](results-2026-09-16-report-evidence-final-json-qwen.md)
returned zero hits for a multi-concept contiguous query despite saved evidence
being present. Its valid JSON abstention was not a successful positive answer.
JQ, SQ and FQ remain failed, closed and unchanged; their observations cannot be
combined into one successful conversation.

A read-only inspection of 30 local benchmark source snapshots found 632 source
rows, 19--24 per snapshot. Total title lengths were 1,253--1,974 characters per
snapshot and the longest individual title was 245 characters. All 632 stored
summaries were nonempty. These are capacity observations, not correctness,
relevance, original CSV identity or independent coverage labels. An initial
PowerShell array `.count`/field-name collision was corrected before reporting
the source count, using explicit property aggregation.

## Candidate and rejected alternative

Give the model a bounded, unranked catalog of saved source IDs and titles before
it chooses one read. This removes the requirement to synthesize an exact phrase
just to discover an ID. Do not silently replace literal matching with token OR,
fuzzy or semantic matching: those methods introduce an unmeasured selection
policy. No external search, new evidence or summary scraping is involved.

Use a separate entry around the frozen core, not modifications to frozen policy,
snapshot, Qwen adapter, runner, fixtures or manifests. The new candidate narrows
its first action to a visible-ID read; after that actual result it permits only
finalization. This is catalog plus restricted action policy, not an experiment
isolating the causal effect of catalog text alone. Old APIs keep their behavior.

- At most 32 entries, titles clipped to 256 Unicode code points with an explicit
  flag. Preserve original IDs and snapshot order; never rank by the question,
  rewrite titles, invent metadata or renumber sources.
- Catalog fields are method identity, total/returned/omitted source counts,
  coverage (`complete` or `partial`), title-truncation count and entries. Each
  entry contains only source ID, title and title-truncation flag. No summary,
  URL, DOI, report reference, publisher, evidence ID or selected-answer label.
- The complete catalog JSON uses canonical ASCII serialization and at most
  6,144 bytes, including envelope/count fields. Keep a deterministic prefix;
  disclose omissions. An empty valid snapshot is complete zero, not a failed
  check. Construction failure is an error, never an empty successful catalog.
- Supply catalog data as a distinct user-data message, with code-owned system
  instructions warning that titles are untrusted and not evidence. Preserve
  the original user question, native assistant/tool IDs and paired results.
  Every callback history contains exactly one catalog message, not a growing
  copy per turn. The frozen overview still has no IDs; the new supplementary
  catalog explicitly does. Do not inject the old policy's contradictory note.
- Bound canonical callback arguments (messages, tools, tool choice) to 12 KiB
  before downstream dispatch. This is not proof of future provider wire size;
  any later transport must budget its complete HTTP envelope separately.
- Advertise only `read_source` with an enum of visible catalog IDs, or no tool
  for an empty catalog. Reject invisible, unknown, cross-snapshot IDs and any
  lookup/other tool before execution. The catalog is not a citation receipt.
- One actual read at most, followed by final-only. This stays below the frozen
  ceiling of two tool attempts and three turns; it does not spend spare slots
  on retry, fallback, pagination or repair. Source-title ambiguity remains a
  limitation, not permission to expand scope.
- The frozen executor alone issues read receipts for nonempty saved windows.
  Only receipts actually forwarded to the injected callback can be cited.
  Keep explicit missing text, partial windows, refusal and failure states.
  Preserve strict final parsing, `semantic_support=not_assessed` and
  `answer_verification=not_verified`. No semantic entailment claim follows.

The candidate is callback-only and has no provider or production imports. The
old stage/final-JSON transports allow a hit enum of at most five; a 32-ID catalog
must NOT be smuggled through their contract, truncated to pretend compatibility
or paired with their old live allowance. A later native transport needs a new
identity and separately frozen full-wire controls before a fresh live protocol.

## Prospective offline acceptance

New developer-authored controls are engineering cases, not held-out human or
model evaluations. Include a ceramic acoustic probe with separated resonance,
deployment and lifetime facts; a similar-title distractor with different facts;
a business record with missing text; and an unrelated record with instruction-
like title text. Additional boundary controls may vary IDs, length and Unicode.
Do not put expected answers or selected IDs in the model's catalog.

Acceptance requires actual core -> callback -> read -> final seams:

1. Multi-concept questions receive a discoverable ID without literal lookup;
   initial arguments contain titles but no summaries. A scripted selector then
   reads and returns the exact served receipt, with native call ID preserved.
2. Similar and identical titles remain separate by ID. No merged facts, guessed
   excerpts, cross-session citation or snapshot mutation can create evidence.
3. Source IDs, title-injected fake receipts and any unissued evidence ID are
   rejected if cited without a read. Missing text issues no receipt and remains
   an observable missing result before scripted abstention.
4. Unknown/omitted IDs, lookup, repeated read, malformed arguments, duplicate
   JSON fields, hostile titles and downstream failure cannot expand permissions.
5. Count, character, canonical-byte and callback-byte boundaries disclose partial
   coverage or fail before dispatch. Negative checks include emoji, CJK, escaped
   controls and an omitted relevant source; partial is not literature absence.
6. Pre-forward failure does not turn the core's early delivery bookkeeping into
   actual downstream delivery. Post-forward rejection retains already forwarded
   evidence while withholding failed answer/citations.
7. Re-inject missing catalog forwarding and bypassed visible-ID admission; the
   corresponding actual-callback/tool-dispatch tests must fail, then pass after
   restoring exact implementation bytes. Also exercise unissued-citation rejection.
8. Run baseline/final full zero-provider suites, latest Ruff, narrow Pylint,
   offline lock check and independent read-only review. Preserve all old frozen
   files and recorded batch artifacts; never relax assertions or add skips.

Replay the 30 local snapshots only to measure catalog size/omissions, without
model calls or public raw source dumps. A scripted demo accepts no credentials,
paths or arguments and labels all responses `scripted_offline`.

## Stop and next gate

No paid request, key access, network retrieval, production route, scoring change,
new live runner or v8 reclassification is in scope. Package deployment is not
activation. Catalog delivery and strict read-before-cite are necessary plumbing,
not evidence of correct model selection or reader value. Record exact limits
and failures before proposing a separate wire adaptation and fresh bounded live
validation; do not rerun the closed JQ batch until it passes.
