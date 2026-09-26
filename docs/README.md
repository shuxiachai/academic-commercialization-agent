# Documentation map

[English overview](../README.md) · [中文概览](../README.zh-CN.md)

## Start with the question

| Reader / question | Document |
|---|---|
| What does it do, and can I run it? | [English](../README.md), [中文](../README.zh-CN.md) |
| What is implemented versus actually validated? | [Current evidence status](evidence-status.md) |
| How do I configure providers, deploy and use the API? | [Operating guide](operating-guide.md) |
| Where are the important design decisions and exclusions? | [AGENTS.md](../AGENTS.md) |
| How do I contribute and reproduce CI? | [Contributing](../CONTRIBUTING.md) |
| How do checkpoints and recovery remain safe? | [Checkpoint recovery](checkpoint-recovery.md) |
| What can an offline volume-copy rehearsal establish? | [Synthetic restore scope and operator prerequisites](offline-volume-restore.md) |
| What happens on timeout or incomplete accounting? | [Runtime terminal integrity](runtime-terminal-integrity.md) |
| How do traces avoid exporting private data? | [Observability](observability.md) |
| What is the concise engineering case study? | [Portfolio case study](portfolio-case-study.md) |
| What happened in each Tool Calling version? | [Version ledger](evidence-status.md#tool-calling-experiments) |
| How can I inspect the isolated saved-evidence tool conversation? | [Report evidence follow-up](report-evidence-followup.md) |
| What does the isolated saved-source HTTP/browser entry protect? | [Saved-source entry contract](saved-source-entry.md) |
| How is saved-source paid admission prepared without activating it? | [Backend controller and receipts](saved-source-paid-controller.md) |
| How does the isolated receipt page recover a lost acknowledgement? | [Receipt HTTP/browser contract](saved-source-receipt-entry.md) |
| How is a native Qwen receipt trial bounded? | [RQ synthetic preregistration](prereg-2026-09-20-saved-source-receipt-qwen-canary.md) |
| What did the native receipt/browser trial actually verify? | [RQ result and limits](results-2026-09-20-saved-source-receipt-qwen-canary.md) |
| How can isolated receipts deliver truthful native usage? | [Usage delivery contract](saved-source-usage.md) |
| How is real saved-report selection prepared without sending data? | [RU offline protocol](prereg-2026-09-22-real-source-usage-offline.md) |
| What did the real-data offline rehearsal observe? | [RU preparation result](results-2026-09-22-real-source-usage-offline.md) |
| What must a separate native saved-source usage pilot preserve? | [RUQ preparation protocol](prereg-2026-09-22-real-source-usage-qwen.md) |
| What did the independent title-reference review establish? | [LLM review and limits](results-2026-09-22-real-source-usage-reference-review.md) |
| What did the native real saved-source usage pilot establish? | [RUQ result and limits](results-2026-09-22-real-source-usage-qwen.md) |
| How are new semantic reviews performed without human sign-off? | [LLM-only review policy](llm-review-policy.md) |
| Where is the full experimental history? | [Experiment index](experiment-index.md) |

## Current guides are not historical results

The overview, operating guide and evidence ledger describe the current state.
Files named `prereg-*`, `results-*`, `errata-*` and the
[v2.0.0 release record](release-v2.0.0.md) retain their original dates, numbers
and conditions. A later code fix cannot retrospectively turn a failed study
into a pass.

The documentation consolidation leaves those files, frozen evidence, source
locks and experimental implementation paths unchanged. Its
[archive index](experiment-index.md) also links immutable README and AGENTS
snapshots from before consolidation, so earlier reasoning remains retrievable.

Resume notes and original reviewer forms belong to the separate private notes
repository. Public docs contain only already-public aggregates and disclosed
method limits. Do not use this navigation work to publish private artifacts.

## Maintenance rule

Add a dated result when an experiment finishes, update the concise current
ledger, and link it here only if it establishes a new reading path. Do not
copy the full run narrative into both language overviews and AGENTS again.
Current bilingual benchmark numbers must continue to match the committed CSV.
