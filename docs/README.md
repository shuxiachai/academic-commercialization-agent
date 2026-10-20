# Documentation map

[English overview](../README.md) · [中文概览](../README.zh-CN.md)

Start with one reading path below; the experiment archive is not required
reading for running the application. This map separates application and
maintenance entry points from historical experiments. Frozen identity records
retain their original paths and hashes.

## Start with the question

| Reader / question | Document |
|---|---|
| What does it do, and can I run it? | [English](../README.md), [中文](../README.zh-CN.md) |
| What is implemented versus actually validated? | [Current evidence status](evidence-status.md) |
| Which test layers cover the boundaries, and what remains unproven? | [Testing status and boundary map](testing-status.md) |
| How do I configure providers, deploy and use the API? | [Operating guide](operating-guide.md) |
| Where are the important design decisions and exclusions? | [AGENTS.md](../AGENTS.md) |
| How do I contribute and reproduce CI? | [Contributing](../CONTRIBUTING.md) |
| What is the concise engineering case study? | [Portfolio case study](portfolio-case-study.md) |
| Where is the full experimental history? | [Experiment index](experiment-index.md) |

**中文阅读路径：** 先读[项目概览](../README.zh-CN.md)；运行和部署看
[操作指南](operating-guide.md)，判断完成度看[证据台账](evidence-status.md)，
追溯实验再打开[历史索引](experiment-index.md)。下面的目录说明区分生产入口、
实验材料和本地私人文件；目录存在不代表其中每个模块已上线。

## Repository map

| Area | What belongs here | Where to start |
|---|---|---|
| `api/`, `web/`, `ui/` | HTTP serving, browser client and shared presentation; isolated/default-off surfaces also live here | [Operating guide](operating-guide.md) |
| `src/academic_agent/` | Pipeline, retrieval and runtime code **alongside experimental libraries**; not every module is production-connected | [Boundary-specific code map](../AGENTS.md#layout-and-boundary-specific-reading) |
| `tests/`, `e2e/` | Offline regression contracts and opt-in zero-provider browser journeys | [Contributor checks](../CONTRIBUTING.md#checks-before-and-after-a-change) |
| Root Python scripts | `benchmark*.py` are the benchmark commands. The rest (`openalex_*`, `evidence_gap_*`, `report_evidence_*`, `ablation*`, …) are frozen experiment runners whose protocols lock their paths and hashes; none is needed to run the application | [Supported setup](operating-guide.md#local-setup-and-provider-selection), then the relevant [experiment protocol](experiment-index.md) |
| `docs/` | Current guides plus dated protocols, results and errata | This map for current reading; [archive](experiment-index.md) for history |
| `evals/`, `benchmark_fixtures/`, `test_papers/` | Evaluation material, fixtures and test inputs; each has its own provenance and scope | [Evidence ledger](evidence-status.md) and the relevant protocol |
| `examples/`, `assets/` | Public sample reports (also served without credentials at `/samples` from the allowlist in `api/samples.py`) and presentation images, not automatically current results | [Versioned public sample](../README.md), [sample index](../examples/README.md) |
| `scripts/` | Operational report and container font check; `audits/` holds offline audit tools and `demos/` holds scripted examples | [Current tool commands](#relocated-maintenance-and-demo-commands), [contributor checks](../CONTRIBUTING.md) |
| `outputs/`, `output/playwright/` | Local run/evaluation artifacts, temporary test trees and browser failure screenshots | See local/private boundaries below; do not treat the whole directory as disposable |
| `notes/` | Separate private repository for personal project narratives and original review material, when present locally | Local/private only; not part of a public clone |

Configuration and deployment entry files remain at the root: `pyproject.toml`,
`uv.lock`, `.env.example`, `Dockerfile`, `docker-compose.yml` and `.github/`.
Use the documented FastAPI or CLI commands, not an arbitrary root-level script.
The remaining experimental runners can bind their paths and source hashes.
Their migration requires a separate identity and compatibility review.

Do not add new scripts at the root. Put a new experiment runner, probe or
audit under `scripts/` (offline audits in `scripts/audits/`, run as
`uv run python -m scripts.audits.<name>`) and its tests in `tests/`.
`market_retrieval_probe.py` (2026-10-19) is the last root-level addition; it
stays where its dated result cites it.

## Relocated maintenance and demo commands

Eleven root scripts now live under `scripts/`. There are no forwarding files at
the old root locations. Run the commands below from the repository root and
keep any existing arguments. Audit commands use Python module entry points so
their package imports resolve consistently.

Some entries in `AGENTS.md` and dated protocols retain the original script
locations. `AGENTS.md` itself participates in frozen source identities, so
those bytes have been retained. This table gives the current location of these
eleven tools; it does not change historical commits, study results or execution
permissions. Other instructions in `AGENTS.md` still apply.

| Former root file | Current file | Current command |
|---|---|---|
| `ops_report.py` | [Operational report](../scripts/ops_report.py) | `uv run python scripts/ops_report.py` |
| `reviewer_audit.py` | [Reviewer audit](../scripts/audits/reviewer_audit.py) | `uv run python -m scripts.audits.reviewer_audit` |
| `target_user_pilot.py` | [Target-user pilot](../scripts/audits/target_user_pilot.py) | `uv run python -m scripts.audits.target_user_pilot` |
| `user_utility_audit.py` | [Utility audit](../scripts/audits/user_utility_audit.py) | `uv run python -m scripts.audits.user_utility_audit` |
| `patent_relevance_eval.py` | [Patent relevance audit](../scripts/audits/patent_relevance_eval.py) | `uv run python -m scripts.audits.patent_relevance_eval` |
| `patent_relevance_candidate.py` | [Patent candidate](../scripts/audits/patent_relevance_candidate.py) | `uv run python -m scripts.audits.patent_relevance_candidate` |
| `regulator_title_audit.py` | [Regulator title audit](../scripts/audits/regulator_title_audit.py) | `uv run python -m scripts.audits.regulator_title_audit` |
| `regulator_title_recovery_candidate.py` | [Regulator title candidate](../scripts/audits/regulator_title_recovery_candidate.py) | `uv run python -m scripts.audits.regulator_title_recovery_candidate` |
| `report_evidence_followup_demo.py` | [Follow-up demo](../scripts/demos/report_evidence_followup_demo.py) | `uv run python scripts/demos/report_evidence_followup_demo.py` |
| `report_evidence_guarded_followup_demo.py` | [Guarded demo](../scripts/demos/report_evidence_guarded_followup_demo.py) | `uv run python scripts/demos/report_evidence_guarded_followup_demo.py` |
| `report_evidence_catalog_demo.py` | [Catalog demo](../scripts/demos/report_evidence_catalog_demo.py) | `uv run python scripts/demos/report_evidence_catalog_demo.py` |

The operational report still reads the repository's `outputs/` by default and
writes its report to stdout. An explicit relative `--root` remains relative to
the caller's working directory. Audit methods, labels and historical data are
unchanged; a relocated command does not reopen a closed study.

## Runtime and operations

| Question | Document |
|---|---|
| How do checkpoints and recovery remain safe? | [Checkpoint recovery](checkpoint-recovery.md) |
| What can an offline volume-copy rehearsal establish? | [Synthetic restore scope and operator prerequisites](offline-volume-restore.md) |
| Does that rehearsal cover helper/PDF accounting? | [Synthetic auxiliary restoration and limits](results-2026-09-29-auxiliary-volume-restore.md) |
| What happens on timeout or incomplete accounting? | [Runtime terminal integrity](runtime-terminal-integrity.md) |
| Which helper calls are observed separately from Crew costs? | [Auxiliary LLM accounting and limits](results-2026-09-27-auxiliary-llm-accounting.md) |
| How do traces avoid exporting private data? | [Observability](observability.md) |
| How are new semantic reviews performed without human sign-off? | [LLM-only review policy](llm-review-policy.md) |

## Tool Calling contracts and history

Start with the [current production boundary](operating-guide.md#optional-saved-source-locator)
and the version ledger. The saved-source wrapper is default-off; deployment
exposure and new paid execution have separate gates. Saved-source location is not supplementary web search
or generated claim verification. An isolated contract or closed native trial
does not authorize a new paid call or enable a production feature.

| Question | Document |
|---|---|
| What happened in each Tool Calling version? | [Version ledger](evidence-status.md#tool-calling-experiments) |
| How can I inspect the isolated saved-evidence tool conversation? | [Report evidence follow-up](report-evidence-followup.md) |
| How can a query propose local candidates without reading or answering? | [Offline candidate-search contract](saved-source-candidate-search.md) |
| What does the isolated saved-source HTTP/browser entry protect? | [Saved-source entry contract](saved-source-entry.md) |
| How is saved-source paid admission prepared without activating it? | [Backend controller and receipts](saved-source-paid-controller.md) |
| How does the isolated receipt page recover a lost acknowledgement? | [Receipt HTTP/browser contract](saved-source-receipt-entry.md) |
| How can isolated receipts deliver truthful native usage? | [Usage delivery contract](saved-source-usage.md) |

<details>
<summary>Dated query and saved-source trials — expand for a specific historical question</summary>

These links retain the previous map's entry points. For the complete chronology,
use the [experiment archive](experiment-index.md); these are not additional setup steps.

| Question | Historical protocol / result |
|---|---|
| How is the native query wire prepared without a live allowance? | [Separate Qwen query protocol](prereg-2026-09-26-candidate-query-qwen-transport.md) |
| What did the synthetic native query controls establish? | [NQ protocol](prereg-2026-09-26-candidate-query-synthetic-canary.md) and [failed coverage result](results-2026-09-27-candidate-query-synthetic-canary.md) |
| What happened to the four positive saved-source native controls? | [Closed development result and provenance limits](results-2026-09-27-positive-source-selection-closeout.md) |
| Did nearby ordered terms improve the unchanged candidate baseline? | [Offline rule](prereg-2026-09-27-ordered-window-conjunction-offline.md) and [zero-gain result](results-2026-09-27-ordered-window-conjunction-offline.md) |
| How is a native Qwen receipt trial bounded? | [RQ synthetic preregistration](prereg-2026-09-20-saved-source-receipt-qwen-canary.md) |
| What did the native receipt/browser trial actually verify? | [RQ result and limits](results-2026-09-20-saved-source-receipt-qwen-canary.md) |
| How is real saved-report selection prepared without sending data? | [RU offline protocol](prereg-2026-09-22-real-source-usage-offline.md) |
| What did the real-data offline rehearsal observe? | [RU preparation result](results-2026-09-22-real-source-usage-offline.md) |
| What must a separate native saved-source usage pilot preserve? | [RUQ preparation protocol](prereg-2026-09-22-real-source-usage-qwen.md) |
| What did the independent title-reference review establish? | [LLM review and limits](results-2026-09-22-real-source-usage-reference-review.md) |
| What did the native real saved-source usage pilot establish? | [RUQ result and limits](results-2026-09-22-real-source-usage-qwen.md) |

</details>

## Local and private material

- `notes/` is ignored by the public repository and maintained separately. Use
  its concise interview narrative for quick recall and its full decision history
  for deeper context. Neither raw reviews nor personal drafts belong in public docs.
- `outputs/` mixes saved runs, frozen experiments and test scratch. The public
  repository tracks only the two curated benchmark CSVs there; other local
  artifacts can contain unpublished research and must not be uploaded by default.
- Git worktrees may also live under ignored folders. A clean `git status` does
  not account for ignored evidence, local credentials or running processes.
- `.env` is private configuration; `.venv/` and caches serve local tooling.
  Directory names or age alone do not authorize removal. The script relocation
  does not move or delete these local files or complete a cache/worktree cleanup.

## Current guides are not historical results

The overview, operating guide and evidence ledger describe the current state.
Files named `prereg-*`, `results-*`, `erratum-*`, `errata-*` and the
[v2.0.0 release record](release-v2.0.0.md) retain their original dates, numbers
and conditions. A later code fix cannot retrospectively turn a failed study
into a pass.

Dated documents, frozen evidence and historical source locks remain unchanged.
The relocated tool paths are listed above rather than rewritten into old study
records. The [archive index](experiment-index.md) also links immutable README
and AGENTS snapshots from before consolidation, so earlier reasoning remains
retrievable.

Resume notes and original reviewer forms belong to the separate private notes
repository. Public docs contain only already-public aggregates and disclosed
method limits. Do not use this navigation work to publish private artifacts.

## Maintenance rule

Add a dated result when an experiment finishes, update the concise current
ledger, and link it here only if it establishes a new reading path. Do not
copy the full run narrative into both language overviews and AGENTS again.
Current bilingual benchmark numbers must continue to match the committed CSV.
Prefer an existing guide or archive entry over another navigation document.
Preserve old entry links when regrouping the map; do not publish private files
or change frozen paths as a documentation cleanup.
