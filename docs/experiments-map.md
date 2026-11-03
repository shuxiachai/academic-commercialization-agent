# The experiment scripts and the Python files at the repository root

[Back to the documentation map](README.md) · [Experiment archive](experiment-index.md)

Four Python files sit at the repository root: the benchmark commands. The
runners, preflights and review tools of closed experiments, forty-seven files,
live under `experiments/`, one directory per study. They were at the root
until 2026-10-31; the layout and bytes every earlier protocol recorded are
kept at the tag `archive/root-experiments-2026-10` (921fc6a), and the move is
documented in the [relocation erratum](errata-2026-10-31-experiment-scripts-relocation.md).
None of these files is needed to run, deploy or understand the application.

This page says what each file is, which study it belongs to and where that
study's record is, so a reader can tell an archive from a loose end. The
one-line purposes are the files' own docstrings. Run one from the repository
root as `uv run python -m experiments.<directory>.<name>`. New tools do not go
here: put a probe or audit under `scripts/` ([how](README.md#repository-map)).

## Benchmark commands at the root (current)

The commands the [README](../README.md#tests-and-benchmark) documents.
Their outputs are the two curated CSVs under `outputs/benchmark/`.

| File | Purpose | Record |
|---|---|---|
| `benchmark.py` | Batch benchmark runner: runs the 10 test topics and saves full outputs | [Evidence ledger](evidence-status.md) |
| `benchmark_check.py` | Analyse benchmark outputs and generate `benchmark_summary.csv` | [Held-out TRL v2](results-2026-10-19-heldout-trl-v2.md) |
| `benchmark_fixtures.py` | Frozen evidence for benchmark runs | [Agent-topology ablation](prereg-2026-08-21-agent-topology-ablation.md) |
| `benchmark_identity.py` | Immutable execution identity for new benchmark batches, never the archive | [Cost scope and benchmark identity](results-2026-09-10-cost-scope-and-benchmark-identity.md) |

## `experiments/pipeline_audits/`: topology, fault recovery and a retrieval probe

| File | Purpose | Record |
|---|---|---|
| `ablation.py` | Run a fixture-only one/four/six-node agent-topology ablation | [Protocol](prereg-2026-08-21-agent-topology-ablation.md), [qwen3.8-flash rerun](results-2026-10-24-agent-topology-ablation-qwen.md) |
| `ablation_check.py` | Analyse agent-topology ablation outputs without making network calls | Same |
| `market_retrieval_probe.py` | Development probe: does market retrieval surface the topic's known operators? | [Market retrieval development probe](results-2026-10-19-market-retrieval-development-probe.md) |
| `checkpoint_fault_audit.py` | Run the pre-registered zero-network checkpoint fault-recovery audit | [Protocol](prereg-2026-08-23-checkpoint-fault-recovery.md), [result](results-2026-08-23-checkpoint-fault-recovery.md) |

## `experiments/evidence_gap/`: evidence-gap retrieval, phases 1 to 4 (August 2026)

Supplementary retrieval for domains the main search left thin. It remains
zero-call shadow mode in production; its last unseen evaluation failed the
admission gates ([ledger](evidence-status.md#tool-calling-experiments)).

| File | Purpose | Record |
|---|---|---|
| `evidence_gap_audit.py` | Audit the phase-1 evidence-gap gate over frozen source collections | [Phase 1](results-2026-08-25-evidence-gap-shadow-planner-phase1.md) |
| `evidence_gap_phase2_audit.py` | Replay the frozen Phase-2 bounded Tool Calling contract without networking | [Phase 2](results-2026-08-25-evidence-gap-tool-execution-phase2.md) |
| `evidence_gap_phase3_audit.py` | Frozen five-case live-provider compatibility audit for evidence-gap search | [Phase 3 adapter](results-2026-08-25-evidence-gap-live-adapter-phase3-implementation.md) |
| `evidence_gap_phase3_review.py` | Prepare and summarize the frozen Phase 3 human evidence-value review | [Phase 3 review packet](results-2026-08-25-evidence-gap-human-review-packet-phase3.md) |
| `evidence_gap_phase4_audit.py` | Frozen, zero-network preflight for Phase 4 domain evidence adapters | [Phase 4 protocol](prereg-2026-08-26-evidence-gap-domain-live-phase4.md) |
| `evidence_gap_phase4_live.py` | Production-disconnected live runner for the frozen Phase 4 value study | [Phase 4 implementation](results-2026-08-26-evidence-gap-domain-live-phase4-implementation.md) |
| `evidence_gap_phase4_review.py` | Lock, prepare, and summarize the Phase 4 domain-source value review | Same |
| `evidence_gap_openalex_live.py` | Frozen, anonymous OpenAlex value study disconnected from production | [Anonymous OpenAlex protocol](prereg-2026-08-27-evidence-gap-anonymous-openalex.md), [live run](results-2026-08-27-evidence-gap-anonymous-openalex-live.md) |
| `evidence_gap_openalex_review.py` | Lock and review the one anonymous OpenAlex live-value execution | [Review](results-2026-08-27-evidence-gap-anonymous-openalex-review.md) |

## `experiments/openalex_retrieval/`: OpenAlex retrieval challenges v2 to v8 (27 August to 3 September 2026)

Seven successive attempts to make OpenAlex retrieval precise enough to admit.
Each version has a zero-network preflight (`*_unseen.py`), a write-once live
runner and a review tool that locks the run before anyone reads it. None of
the seven was admitted.

| File | Purpose | Record |
|---|---|---|
| `openalex_precision_audit.py` | Label-blind development audit for the OpenAlex precision-v2 gate | [Precision v2 protocol](prereg-2026-08-27-openalex-precision-v2.md), [development](results-2026-08-27-openalex-precision-v2-development.md) |
| `openalex_precision_unseen.py` | Zero-network preflight for the frozen OpenAlex precision-v2 challenge | [Unseen implementation](results-2026-08-27-openalex-precision-v2-unseen-implementation.md) |
| `openalex_precision_live.py` | Production-disconnected runner for the precision-v2 unseen challenge | [Unseen live](results-2026-08-27-openalex-precision-v2-unseen-live.md) |
| `openalex_claim_scope_unseen.py` | Zero-network preflight for the frozen OpenAlex claim-scope v3 challenge | [Claim scope v3](results-2026-08-27-openalex-claim-scope-v3-implementation.md) |
| `openalex_claim_scope_live.py` | Production-disconnected live runner for the claim-scope v3 challenge | [Live implementation](results-2026-08-27-openalex-claim-scope-v3-live-implementation.md) |
| `openalex_claim_scope_review.py` | Lock and review the frozen OpenAlex claim-scope v3 execution | [Review implementation](results-2026-08-27-openalex-claim-scope-v3-review-implementation.md) |
| `openalex_scope_link_unseen.py` | Zero-network preflight for the frozen OpenAlex scope-link v4 challenge | [Scope link v4 protocol](prereg-2026-08-27-openalex-scope-link-v4.md) |
| `openalex_scope_link_live.py` | Production-disconnected live runner for the scope-link v4 challenge | [Live protocol](prereg-2026-08-28-openalex-scope-link-v4-live.md), [live result](results-2026-08-29-openalex-scope-link-v4-live.md) |
| `openalex_scope_link_abstention_review.py` | Diagnose the frozen scope-link v4 abstentions without changing their result | [Abstention diagnostic](prereg-2026-08-29-openalex-scope-link-v4-abstention-diagnostic.md), [review](results-2026-08-29-openalex-scope-link-v4-abstention-diagnostic-review.md) |
| `openalex_evidence_set_development.py` | Label-blind W01-W08 development runner for evidence-set v5 | [Development runner](results-2026-08-29-openalex-evidence-set-v5-development-runner-implementation.md) |
| `openalex_evidence_set_unseen.py` | Zero-network preflight for the frozen OpenAlex evidence-set v5 challenge | [Evidence set v5](results-2026-08-29-openalex-evidence-set-v5-implementation.md) |
| `openalex_evidence_set_failure_diagnostic.py` | Explain the sealed Qwen evidence-set v5 failure without rerunning it | [Failure diagnostic](results-2026-08-31-openalex-evidence-set-v5-qwen-failure-diagnostic.md) |
| `openalex_role_slot_unseen.py` | Zero-network preflight for the frozen role-slot consensus v6 challenge | [Role slot v6 protocol](prereg-2026-09-01-openalex-role-slot-consensus-v6.md), [offline](results-2026-09-01-openalex-role-slot-consensus-v6-offline.md) |
| `openalex_role_slot_development.py` | Write-once Y01-Y08 runner for role-slot consensus v6 | [Development runner](prereg-2026-09-01-openalex-role-slot-consensus-v6-development-runner.md), [development live](results-2026-09-01-openalex-role-slot-consensus-v6-development-live.md) |
| `openalex_role_slot_failure_review.py` | Review all frozen role-slot v6 provider candidates after mechanical failure | [Failure diagnostic](prereg-2026-09-01-openalex-role-slot-v6-failure-diagnostic.md), [review](results-2026-09-01-openalex-role-slot-v6-failure-diagnostic-review.md) |
| `openalex_role_directed_unseen.py` | Zero-network preflight for the frozen role-directed retrieval v7 study | [Role directed v7 offline](results-2026-09-01-openalex-role-directed-retrieval-v7-offline.md) |
| `openalex_role_directed_live.py` | Write-once live runner for the frozen AA01-AA08 v7 retrieval study | [Live runner protocol](prereg-2026-09-01-openalex-role-directed-retrieval-v7-live-runner.md), [live runner](results-2026-09-02-openalex-role-directed-retrieval-v7-live-runner.md) |
| `openalex_role_directed_review.py` | Source-lock and review the frozen role-directed retrieval v7 AA run | Same |
| `openalex_role_gap_unseen.py` | Zero-network preflight for adaptive role-gap closure v8 | [Role gap v8 protocol](prereg-2026-09-02-openalex-adaptive-role-gap-closure-v8.md), [offline](results-2026-09-02-openalex-adaptive-role-gap-closure-v8-offline.md) |
| `openalex_role_gap_live.py` | Write-once live runner for the frozen AC01-AC08 role-gap v8 study | [Live runner protocol](prereg-2026-09-02-openalex-adaptive-role-gap-v8-live-runner.md), [AC live](results-2026-09-02-openalex-adaptive-role-gap-v8-ac-live.md) |
| `openalex_role_gap_review.py` | Source-lock and review the frozen adaptive role-gap v8 AC run | [Human review](results-2026-09-03-openalex-adaptive-role-gap-v8-human-review.md) |
| `openalex_role_gap_evaluation.py` | Write-once evaluation runner for the frozen AD01-AD08 role-gap v8 study | [AD evaluation protocol](prereg-2026-09-03-openalex-adaptive-role-gap-v8-ad-evaluation.md), [AD live](results-2026-09-03-openalex-adaptive-role-gap-v8-ad-live.md) |
| `openalex_role_gap_evaluation_review.py` | Source-lock and review the frozen adaptive role-gap v8 AD unseen run | [AD human review](results-2026-09-03-openalex-adaptive-role-gap-v8-ad-human-review.md) |

## `experiments/report_evidence_canaries/`: saved-evidence follow-up canaries (September 2026)

Generated follow-up answers over a run's saved evidence. Experimental, not a
production feature; each canary verifies the identity of its frozen committed
batch by default, and only an explicitly authorised parent process may make
the one paid call ([contract](report-evidence-followup.md)).

| File | Purpose | Record |
|---|---|---|
| `report_evidence_followup_canary.py` | Explicitly authorized synthetic-only canary CLI; never a production endpoint | [Synthetic canary](prereg-2026-09-14-report-evidence-followup-qwen.md), [result](results-2026-09-15-report-evidence-followup-qwen-canary.md) |
| `report_evidence_stage_canary.py` | Check frozen stage-canary identity by default; paid mode needs fresh permission | [Stage canary](prereg-2026-09-15-report-evidence-stage-qwen-canary.md), [live](results-2026-09-15-stage-qwen-canary-live.md) |
| `report_evidence_catalog_canary.py` | Verify committed CQ identity by default; the explicit live path is parent-only | [Catalog canary](prereg-2026-09-16-report-evidence-catalog-qwen-canary.md) |
| `report_evidence_claim_canary.py` | Verify committed CLQ identity by default; only the parent may dispatch live | [Claim canary](prereg-2026-09-16-claim-qwen-canary.md) |
| `report_evidence_final_json_canary.py` | Check frozen final-JSON canary identity by default; live mode is parent-only | [Final JSON](prereg-2026-09-16-report-evidence-final-json-qwen.md), [result](results-2026-09-16-report-evidence-final-json-qwen.md) |
| `report_evidence_real_saved_canary.py` | Verify RS identity by default; only the parent may acknowledge the live batch | [Real saved offline](prereg-2026-09-16-report-evidence-real-saved-offline.md), [result](results-2026-09-16-report-evidence-real-saved-offline.md) |
| `report_evidence_contrast_check.py` | Print the bounded offline PCQ preparation or its allowlisted review view | [Proposition contrast](prereg-2026-09-17-claim-proposition-contrast.md), [result](results-2026-09-17-claim-proposition-contrast.md) |
| `report_evidence_claim_contrast_canary.py` | Verify committed PCQ identity by default; only the parent may dispatch live | [Contrast canary](prereg-2026-09-17-claim-proposition-contrast-qwen-canary.md), [runner](results-2026-09-17-claim-proposition-contrast-qwen-runner.md) |
| `report_evidence_relation_policy_canary.py` | Verify committed RP identity by default; native dispatch belongs to the parent | [Relation policy canary](prereg-2026-09-18-relation-policy-qwen-canary.md) |
| `report_evidence_source_locator_demo.py` | Fresh scripted offline selection controls, not model-quality observations | [Saved-source locator](prereg-2026-09-18-saved-source-locator.md), [read-first follow-up](results-2026-09-18-read-first-followup-implementation.md) |
| `saved_source_receipt_qwen_canary.py` | Parent-only RQ entry; default is read-only identity verification | [Receipt canary](prereg-2026-09-20-saved-source-receipt-qwen-canary.md) |

## Reading the table

- A "Same" record means the file belongs to the row above it.
- Dated documents written before 2026-10-31 name these files at the
  repository root and record the byte hashes they had there. Both are true at
  the archive tag; the erratum lists the nine files whose bytes changed in the
  move and why.
- A record is where the study registered or reported; it is not a claim that
  the study succeeded. Most of these did not, and the
  [ledger](evidence-status.md) says which.
- A file's docstring may name a batch code (AA, AC, AD, CQ, CLQ, PCQ, RP, RS,
  RQ, W, Y). Those are the frozen batches the protocol defines; the record
  explains them.
