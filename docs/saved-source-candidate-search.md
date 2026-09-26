# Offline saved-source candidate search

This module locates **candidates in an already loaded source snapshot**. It is
not supplementary retrieval, a production endpoint, a native model adapter or
a generated-answer feature. The existing Sources viewer and gated saved-source
locator are unchanged. No provider is configured or called by this module.

## Two deliberately separate search lanes

`academic_agent.saved_source_candidate_search.search_saved_candidates(snapshot, query)`
returns code-owned observations without selecting or reading a source:

- `literal_result` preserves the frozen `lookup_sources` response: casefolded
  substring matching over saved titles and summaries, in saved order. A literal
  hit is not verified meaning, unit equivalence or evidence supporting a claim.
- `normalized_additions` only adds sources missed by that literal predicate.
  The `lexical_separator_v1` rule matches 2-4 complete ASCII alphabetic words,
  preserving case and order while allowing ASCII spaces/tabs or an adjacent
  ASCII hyphen between those words. Each lane has its own total, truncation
  flag and at most five visible hits; they are not a merged ranking.

All literal hits are excluded from additions, including a sixth or later hit
hidden by the legacy return cap. Field, word and compound boundaries remain
significant: matching cannot bridge title and summary, strip an enclosing
compound, or skip adjacent mathematical symbols into a new equivalence. After
rejecting a partial-word occurrence, scanning still considers overlapping
whole-word occurrences; a rejected prefix must not consume a later valid hit.

No Unicode dash/minus folding, newline or NBSP folding, stemming, casefolding,
number conversion or unit alias is added by the new lane. For example, `12 ms`
and `12-millisecond` are not normalized. Pure alphabetic chemical or unit words
may satisfy the grammar, but are not interpreted as chemistry or units.
`selection` stays null and `semantic_support` / `unit_equivalence` stay
`not_assessed`, even when exactly one candidate is returned.

The raw snapshot is not rewritten. Titles and metadata in results remain saved
values; no abstract/summary excerpt is returned. Missing, empty and whitespace-
only summary observations stay distinct. A title may match when saved text is
missing, which does not manufacture readable evidence.

## Explicit question-to-query bridge

`propose_saved_candidates(snapshot, question, *, proposer)` adds exactly one
trusted synchronous callback, invoked as `proposer(question, QUERY_POLICY)`.
Both arguments are strings. The callback receives neither the source catalog
nor saved summaries, report reference, snapshot hash, source IDs, paths or
reference labels. The snapshot is detached and validated **before** callback
entry; changing the original caller object during the callback cannot replace
the sources used for this search. An empty valid snapshot invokes no callback.

The callback must return a plain built-in dictionary with exactly one key:

```python
{"query": "phase-change"}
# Or explicitly decline to propose a query:
{"action": "decline"}
```

JSON strings, SDK envelopes, mappings/dict subclasses, extra fields, generated
answers and awaitable responses are not accepted. There is no repair, fallback,
automatic retry, second model turn or automatic read of the first candidate.
Malformed response, callback failure and explicit decline are separate states.

Questions are nonblank Unicode-scalar strings of at most 4,096 characters;
queries at most 256. Surrogates are rejected, and original strings are not
trimmed or silently truncated. Shape/type/length checks precede canonical JSON
serialization of the whitelisted proposal. The proposal cap is 4 KiB, measured
as compact `ensure_ascii=True` JSON bytes, not characters. This is post-return
admission, not a bound on memory the callback may already have allocated.
Candidate-result serialization has a separate, larger bound because ten saved
titles can legitimately exceed that proposal budget.

`callback_entries` and `query_executions` count actual entry attempts, including
a subsequent failure. They are not provider request, billing or token counts.
Unsupported normalization does not discard an otherwise available literal
result, and `no_additions` does not mean the literal lane had no hits. Failed or
unavailable observation uses null rather than a fabricated zero count.

## Local scripted example

```python
from academic_agent.report_evidence_snapshot import ReportEvidenceSnapshot, SnapshotSource
from academic_agent.saved_source_candidate_search import propose_saved_candidates, render_candidate_result

snapshot = ReportEvidenceSnapshot(
    report_ref="synthetic-example",
    sources=(SnapshotSource(
        source_id="A1", group="academic", title="Thermal store",
        publisher="Invented", source_type="synthetic", accessed_date="2026-09-26",
        summary="The phase change material stored heat in a laboratory panel.",
    ),),
)
result = propose_saved_candidates(
    snapshot, "Locate the saved thermal-storage material.",
    proposer=lambda question, policy: {"query": "phase-change"},
)
print(render_candidate_result(result).decode("ascii"))
```

This demonstrates a scripted callback and local candidate delivery, not model
inference or autonomous query quality. Metadata remains untrusted data: future
consumers must not execute titles or render them as trusted HTML.

## Limits and next admission boundary

The caller owns the loaded snapshot and the trusted synchronous callback. This
library is not a process sandbox, permission check, thread timeout, source
ownership check or paid-operation controller. A callback can independently
access closures, perform I/O or block; passing it only two strings does not
prevent those actions. Validation bounds the admitted snapshot, not arbitrary
objects' allocation before validation. Content hashes identify bytes, not
authenticity or semantic support.

The case-preserving rule deliberately misses some useful spellings. Broadening
recall can also add unrelated candidates, so a unique hit must not become an
automatic answer. Mechanical controls and a fixed callback do not establish
native provider compatibility, unseen relevance accuracy or user benefit.

There is no CLI, HTTP route, production worker import, provider factory or
credential option for this module. A future native adapter or product entry
needs its own request/data boundary, authorization, accounting and evaluation;
this library does not reopen any closed batch or activate the existing locator.
