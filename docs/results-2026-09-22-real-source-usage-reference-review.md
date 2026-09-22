# RU reference sidecar: independent LLM judgment, not native effectiveness

Date: 2026-09-22. This is a later review of the four development questions in
the [RU preparation](prereg-2026-09-22-real-source-usage-offline.md), not a rewrite
of that preparation's frozen packet, draft references or `not_run` fields.
Raw review material and all private data identities remain local.

## Review method

A fresh Codex subagent context received a frozen title-location rubric and only
case identifiers, document aliases, questions and complete visible ID/title
catalogs. It did not receive proposed references, scripted choices, assisted
keywords, keyword results, saved excerpts, full reports or previous judgments.
The task prohibited tools and external browsing. Shared project instructions
may still be present; this is not proof of independent training or absence of
shared model biases.

The requested role was `route_reviewer`, configured as `gpt-6-astra` with high
reasoning effort. Effective backend metadata was unavailable, so configuration
is not reported as an attested served model. The resulting references are
explicitly LLM-generated, never human expert gold.

Before dispatch, the exact rubric and review input were saved. The returned raw
judgment was retained before comparing it with the author drafts. The private
sidecar binds original packet, blind view, prompt/submitted-prompt and output
identities, provenance, mechanical checks, comparison and limits. No historical
file or original declaration was changed.

## Observed judgment and checks

All four returned candidate sets agreed with the original drafts. Two positive
questions had a single reading candidate; one retained two acceptable candidates;
the negative control found no fitting title in its supplied catalog. The
comparison is **4/4 development draft agreement**, not native model accuracy,
source truth, independent expert calibration or a success rate on unseen tasks.

Local checks verified case/document alignment, valid nonduplicate candidate IDs,
valid near-miss IDs and four exact title quotations. Matching a quotation proves
only literal correspondence, not semantic entailment or scientific correctness.
The reviewer judged title-level candidacy supported while retaining limitations.

In particular, overview-like titles do not establish an article's actual
publication type or which of two candidates is better. A complete saved catalog
can also contain a title already shortened during the original collection;
delivering it completely does not reconstruct the original publication title.
Catalog-level no-fit is not evidence that relevant research does not exist.

The unchanged assisted-keyword baseline already covers all three positive draft
cases, including an ambiguous multi-result case. The new reference review does
not show that a model outperforms that baseline or reduces a user's effort.
No adoption, willingness to pay, time saving or decision improvement was measured.

## Separate next gate

### Offline runner verification

The separate module CLI `academic_agent.saved_source_real_qwen_canary` now
implements the prepared RUQ boundary without changing the old builder, native
selector, shared app or historical batches. Its default path is identity-only.
The original private packet and review sidecar passed its local pure input
checks; this did not construct a provider client, read a model key or execute
a native request.

After edits, the complete zero-provider suite passed **6,826 tests and 1,610
subtests**, against the 6,745/1,601 starting baseline. Current Ruff and narrow
Pylint passed. The 81 new tests are part of that total, not additional samples.
A separate 177-case dependency selection passed before the last six controls
were added; it overlaps the full suite and is not a final extra denominator.

Independent review found two runner defects before any real request: failed
cases did not retain the already observed HTTP delivery evidence, and ordinary
Python equality could accept a Boolean in place of an integer after the strict
observer had rejected it. Bounded private observations now retain code-owned
failure stages, and failed strict receipt validation blocks acceptance. Invalid
HTTP bodies and foreign exception text are not persisted as diagnostic content.
An observation-write failure leaves the batch occupied and stops execution.

Five distinct reinjected defects each made one unchanged assertion fail:
dependency-map admission, premature default key lookup, partial-accounting
acceptance, replacing GET with POST and omitting a received GET observation.
Restoring the old weak HTTP gate additionally failed both Boolean controls.
All mutations were restored. An initially ineffective dependency mutation test
was strengthened to keep the altered origin internally self-consistent, so the
dependency check itself, not an unrelated digest mismatch, must reject it.

A fresh child exercised the actual execution composition with four intercepted
Qwen requests and four POST/GET pairs. It neither pre-imported CrewAI nor patched
CrewAI authentication, and observed no `api.main`, `crewai` or `crewai_core`
modules. Three negative controls rejected dotenv, credential-file and external
network access. The child uses synthetic identity fixtures, so this proves the
composition path, not real private admission or provider behavior.

Two earlier pytest setup failures came from HOME/APPDATA-sensitive imports in
the shared test harness, not this native composition. Four fresh-child harness
failures, including a diagnostic repeat, came from denying normal package
discovery's exact repository-root directory enumeration. That single read-only
enumeration is admitted; file, private-output, credential and network guards
remain. No project assertion, skip or warning policy was weakened. Final
independent static review closed both findings; the reviewer did not run tests.

These observations are offline engineering evidence. Complete CI, frozen
committed identity and a separately applicable live grant are still release and
execution gates, not consequences of these local passing counts.

### Native evaluation remains separate

The first [PR CI run](https://github.com/shuxiachai/academic-commercialization-agent/actions/runs/35714860457)
failed the fresh-child positive control in both Python 3.11 cells. Linux recorded
blocked `lib-dynload` directory access; Windows recorded a file-guard rejection
before any intercepted native request. Both Python 3.12 cells and browser,
container and lint checks passed. The aggregate coverage gate correctly failed.
Those diagnostics did not retain the full remote paths, so the exact remote
aliases or SQLite targets cannot be claimed as established causes.

A bounded test-only follow-up proved that comparing resolved roots with merely
absolute candidate paths rejects legitimate aliases and can miss symlink or
`..` escapes. Both sides now use canonical paths, with sensitive-path checks
before and after resolution. Local SQLite file URIs are decoded and checked by
the same rule; neither arbitrary `sys.path` entries nor shared/historical private
outputs are admitted. The native runner and production code are unchanged.

The 23 new portable controls directly execute the child's guard, and ten
standard-library-only WSL controls exercised real symlink/URI behavior. Restoring
the old guard produced 12 failures among the 23 controls; the fix was restored.
Final local checks passed 104 runner tests, the complete **6,849-test / 1,610-subtest**
suite, current Ruff and narrow Pylint. Independent static review found no
remaining issue. The prior local harness failures and this CI/repair chain
remain recorded; local success is not a substitute for the next complete CI.

The [RUQ protocol](prereg-2026-09-22-real-source-usage-qwen.md) prepares a distinct
current-code-bound native-to-HTTP/accounting observation. It must retain this
sidecar separately from the original packet, and it still needs implementation
review, full CI, frozen identity and applicable bounded data/credential/budget
authority before execution. Preparation and reference review are not a native
result or a production feature switch.

This reference-review step used no project Qwen API call or project model key.
The Codex review is an actual LLM judgment; its service usage is not measured by
the project's provider ledger and is not presented as a zero-cost model call.
