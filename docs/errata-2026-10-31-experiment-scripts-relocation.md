# Erratum: the experiment scripts moved from the repository root to `experiments/`

**Date:** 2026-10-31.

**Affects:** every dated protocol, result and erratum that names a runner,
preflight or review tool by its root path (`openalex_precision_unseen.py`,
`evidence_gap_phase4_audit.py`, `report_evidence_stage_canary.py`, …) or
records its byte hash. The [experiments map](experiments-map.md) lists all
forty-seven files with their study.

## What changed and why

Forty-seven experiment scripts sat at the repository root beside the
application. Each study's protocol had locked their paths and, for nine of
them, their byte hashes, and AGENTS.md said not to move them as a cosmetic
cleanup because a path or hash change can invalidate a paid protocol before it
makes a request. That protection is for studies that may still run. Every
study these files belong to is closed: no batch is open, and the live canaries
refuse to run on any commit other than the one their protocol froze.

So the layout the protocols recorded is kept, not on `main`, but at the
annotated tag `archive/root-experiments-2026-10` (commit 921fc6a, the last
`main` before this change). At that tag every path named in a dated document
exists and every recorded hash matches. On `main` the files now live under
`experiments/<study>/`:

| Directory | Files | Study |
|---|---|---|
| `experiments/pipeline_audits/` | 4 | agent-topology ablation, checkpoint fault recovery, market retrieval probe |
| `experiments/evidence_gap/` | 9 | evidence-gap retrieval, phases 1 to 4 |
| `experiments/openalex_retrieval/` | 23 | OpenAlex retrieval challenges v2 to v8 |
| `experiments/report_evidence_canaries/` | 11 | saved-evidence follow-up canaries |

The four benchmark commands (`benchmark*.py`) stay at the root.

## What was edited, and what was not

Moving a file does not change its bytes. Bytes changed only where a file
named a path that the move made wrong:

- the repository-root constant in 22 moved scripts (`Path(__file__).resolve().parent`
  became `.parents[2]`);
- sibling imports and sibling path strings inside the moved scripts, the
  identity path tuples of the nine `src/academic_agent/*_qwen_canary.py`
  modules that list their root entry script, and the imports and path strings
  of 49 test files, 9 source modules and 1 other files;
- the sha256 literals that moved scripts hold for sibling scripts whose bytes
  changed, listed below. Each was recomputed over the committed (LF) bytes.

Hash literals in dated documents were not touched: they describe the bytes at
the archive tag, which is where those documents' claims are checked. No
fixture, no protocol and no result was edited. No prose in any moved script
was edited, so usage lines in old docstrings still name root paths; the map
gives the current command.

| File whose bytes changed | Hash before | Hash after | Held by |
|---|---|---|---|
| `experiments/evidence_gap/evidence_gap_phase4_audit.py` | `e70c2e015ffc…` | `7fcbd69009e8…` | `experiments/evidence_gap/evidence_gap_openalex_live.py`, `experiments/evidence_gap/evidence_gap_phase4_live.py` |
| `experiments/openalex_retrieval/openalex_claim_scope_unseen.py` | `6104a060b80b…` | `ff86c02aa6dd…` | `experiments/openalex_retrieval/openalex_claim_scope_live.py` |
| `experiments/openalex_retrieval/openalex_precision_unseen.py` | `7dbe457aca21…` | `9278f66e15fc…` | `experiments/openalex_retrieval/openalex_precision_live.py` |
| `experiments/openalex_retrieval/openalex_role_directed_unseen.py` | `c69b67add9b0…` | `e250be5e0ec4…` | `experiments/openalex_retrieval/openalex_role_directed_live.py` |
| `experiments/openalex_retrieval/openalex_role_gap_evaluation.py` | `1f188fbdef22…` | `7b7cb761091e…` | `experiments/openalex_retrieval/openalex_role_gap_evaluation_review.py` |
| `experiments/openalex_retrieval/openalex_role_gap_live.py` | `4c9be921531b…` | `37ef5dca9691…` | `experiments/openalex_retrieval/openalex_role_gap_review.py` |
| `experiments/openalex_retrieval/openalex_role_gap_unseen.py` | `51c77c8615cf…` | `6531bdd21dad…` | `experiments/openalex_retrieval/openalex_role_gap_evaluation.py`, `experiments/openalex_retrieval/openalex_role_gap_live.py` |
| `experiments/openalex_retrieval/openalex_role_slot_unseen.py` | `3bd69fa0a670…` | `c0e65d76a10e…` | `experiments/openalex_retrieval/openalex_role_slot_development.py` |
| `experiments/openalex_retrieval/openalex_scope_link_unseen.py` | `1e3c0b15c960…` | `bbd9676cc413…` | `experiments/openalex_retrieval/openalex_evidence_set_development.py`, `experiments/openalex_retrieval/openalex_scope_link_live.py` |

## What this does and does not claim

- The offline test suite, including every experiment test, passes on the new
  layout. That is the whole verification: it shows the files import, their
  identity checks agree with the committed bytes, and nothing in `api/`,
  `src/` or `web/` depends on their location.
- No live runner was executed. The paid canaries are commit-anchored and were
  closed before this change; the move does not reopen them, and a reader who
  wants to verify a historical batch does so at the tag.
- The experimental modules under `src/academic_agent/` did not move. Only
  the path tuples of the nine canary modules changed, by one entry each.

AGENTS.md and CONTRIBUTING now say that `experiments/` is the frozen
location and that the rule against relocation applies there.
