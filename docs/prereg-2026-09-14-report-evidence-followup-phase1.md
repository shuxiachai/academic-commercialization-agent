# Report evidence follow-up: isolated protocol contract

Date: 2026-09-14 (Australia/Sydney)

Status: implementation protocol; no live execution authorized by this document.

## Question and non-model baseline

Can an explicitly injected conversational transport request bounded read-only
tools over one supplied source snapshot, receive each result under the original
tool-call ID, and then answer or stop without changing the report?

The intended reader task is locating the saved material behind a report claim
and seeing what material is missing. The non-model baseline is browsing the
same source index and saved summaries directly. Whether a conversational view
helps readers more than that baseline is an untested hypothesis, not a reason
to claim utility or deploy a paid endpoint.

This is not another version of automatic supplementary retrieval. Adaptive
Role-Gap v8 remains failed and sealed. No reserved cohorts, source selectors,
old labels, scoring rules, CrewAI tasks or production shadow settings change.

## Pre-implementation observation

A read-only count over the 30 local `outputs/benchmark/` unit directories found
30 `validated_sources.json` artifacts containing 632 source entries and 632
non-empty summaries. Origin fields describe 173 abstracts, 451 search snippets
and eight unspecified origins; the longest saved summary is 1,500 characters.
Entries repeat across runs and are not 632 distinct papers. The current local
snapshot includes the previously disclosed fixture unit and is not renewed
proof of the archived benchmark CSV's original byte identity.

No source text or run-capability URL is copied into the public protocol. This
count establishes available material only, not truth, semantic support, user
value or adequacy of the stored excerpt.

## Phase-one boundaries

- Use a separate, production-disconnected module and synthetic demonstration.
- The trusted caller supplies one source snapshot. Model tool arguments cannot
  select another run, filesystem path, URL or provider.
- Expose only a bounded source index and saved-summary reader. Do not fetch
  full text, scrape pages, run supplementary search or alter source registration.
- Preserve summary provenance and truncation/absence explicitly. A registered
  source is not automatically evidence for any particular claim.
- Implement the assistant `tool_calls` / `role=tool` / `tool_call_id` round trip
  through an injected transport. Do not infer native model behavior from a
  Python function called unconditionally by the application.
- Bound tool attempts and conversational turns before dispatch. Unknown tools,
  malformed arguments, ambiguous call identities and exhausted budgets cannot
  fall through to another tool, run, network client or unlimited retry.
- No ambient credentials, concrete provider transport, server route, browser
  integration, new dependencies or paid requests in this phase.

The wire-message shape follows the vendor's
[Function Calling documentation](https://help.aliyun.com/en/model-studio/qwen-function-calling),
checked on 2026-09-14. Following a documented message shape is not a successful
compatibility test of the exact configured model.

## Offline acceptance

Use fresh synthetic protocol cases, explicitly labeled as scripted rather than
human-reviewed or model-generated. Assert at the request/result/answer seam:

1. The next transport request receives the exact matching tool-call ID and
   actual saved evidence, with no silent drop or fabricated source substitution.
2. Multiple requests remain inside the same detached snapshot. Missing sources,
   missing summaries, invalid input and protocol failure remain distinct.
3. Invalid names/arguments, duplicate IDs, repeated calls, oversized output and
   exhausted budgets do not cause unbounded work or unauthorized dispatch.
4. Tool content is data, never an instruction to expand permissions. Original
   report/source bytes remain unchanged.
5. The returned observation names which evidence was actually delivered; it
   does not mark a final answer semantically verified merely because execution
   completed. No-tool and failed checks are not evidence-support passes.
6. Reinject representative missing-result or scope/budget defects and require
   the corresponding seam assertions to fail, then restore the exact fix.

Run the repository's full before/after offline suite, latest Ruff and narrow
Pylint. Keep all original assertions, skips and warning policy. Report actual
results separately from this preregistration.

## Separate gates after this phase

A real provider round trip needs a separately approved exact model, inputs,
request limit and cost limit. A public paid follow-up endpoint additionally
needs ownership, admission, receipts, usage accounting, privacy and failure
delivery review. Neither is implied by this protocol's offline pass.

Compare a small set of reader tasks against ordinary source browsing before
expanding the feature. Stop if tools add no useful navigation or reproducible
evidence trace, or if a simpler interface meets the task. General citation
entailment, automatic supplementation and report-quality improvement remain
separate unestablished claims.
