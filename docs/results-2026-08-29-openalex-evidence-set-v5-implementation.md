# Result: OpenAlex quote-grounded evidence-set v5 kernel and unseen preflight

**Date:** 2026-08-29

**Result state:** zero-network kernel complete; development qualification,
provider compatibility and source value `not_evaluated`.

## Outcome

The production-disconnected v5 decision kernel and raw-byte-locked X01-X08
preflight now implement the offline portion of the frozen
[v5 protocol](prereg-2026-08-29-openalex-evidence-set-v5.md). The model-facing
surface contains only candidate identity, title and abstract plus code-owned
role descriptions. It cannot receive provider topics, keywords or scores,
prior v4 decisions, or human labels and notes.

The kernel parses two order-reversed judgment passes, mechanically verifies
every proposed title or abstract quote, requires exact agreement on `KEEP` and
role IDs, and fails closed to `ABSTAIN` on malformed output, missing rows,
duplicate identities, disagreement or unverifiable text. The deterministic
selector then chooses the smallest evidence set that covers every required
role plus the frozen scope and supporting minimums, using provider index and
candidate SHA-256 as tie breakers and never selecting more than three sources.
Every candidate disposition and every selected role reaches one validated case
audit model.

No semantic model was called, no OpenAlex request was made, no private label
was opened, and no production, report or planner connection was added.

## Added boundaries

- `src/academic_agent/openalex_evidence_set.py`: strict Pydantic contracts,
  model-input projection, raw-response parsing, quote verification,
  two-pass consensus, deterministic bounded set cover and final audit seam;
- `openalex_evidence_set_unseen.py`: raw-fixture verification before parsing,
  X01-X08 contract expansion, deterministic collection/plan/profile/case and
  idempotency identities, and explicit zero-authority dry-run output;
- `tests/test_openalex_evidence_set.py`: decision, quote, ordering, selection,
  serialization and production-disconnection seams;
- `tests/test_openalex_evidence_set_unseen.py`: fixture, case order, hidden
  field, identity, request-cap and import-boundary seams.

The fixture remains byte-identical to the pre-registration:

```text
f0c4cc86593f54a36040cf1b7d95b42207726b9323172b7dccae2df47ca5a521
```

## Zero-network preflight

The default command completed with:

- 8/8 ordered X01-X08 cases;
- eight distinct source-collection, plan, profile, case-contract and
  idempotency identities;
- at most eight future OpenAlex searches and sixteen future judge calls;
- one abstract-bearing Works query contract, no redirect, internal retry or
  supplementary fetch;
- provider metadata retained for audit but inadmissible to the selector;
- request contract SHA-256
  `328a25581a874251704856289210ee8a3caedb27b462bb6e59e1743a00c9fe1c`;
- judge contract SHA-256
  `dc824c41409057bc7f790b9cec4c50b586e1930557b8a7a05dbc91cd057db5d5`;
- selection contract SHA-256
  `d9fafbe1423e4a29878a47783eabed977c6a5d9e786c8ea02857e4a277f17559`;
- `real_network_calls_performed=false`,
  `real_model_calls_performed=false`, `private_labels_opened=false`, and all
  production/report/planner and live-authorization flags false.

## Verification

Focused zero-network tests:

```text
21 passed in 2.17s
```

Full zero-network suite:

```text
1733 passed, 639 subtests passed in 33.10s
```

Static checks:

```text
uv run --with ruff ruff check \
  src/academic_agent/openalex_evidence_set.py \
  openalex_evidence_set_unseen.py \
  tests/test_openalex_evidence_set.py \
  tests/test_openalex_evidence_set_unseen.py
All checks passed!

uv run pylint --disable=all --enable=E0701 \
  src/academic_agent/openalex_evidence_set.py \
  openalex_evidence_set_unseen.py
Your code has been rated at 10.00/10
```

No warning filter, ignored warning, relaxed assertion or skipped test was
added.

## Defect re-injection

Two protocol-mandated defects were introduced only long enough to run their
exact seam test and were then reverted.

1. The quote verifier was changed so a role could survive when only one of the
   two judge-pass quotes was present in source text. The paraphrase test failed
   because the candidate incorrectly became `KEEP` instead of `ABSTAIN`.
2. A correctly verified supporting role was removed while constructing the
   serialized selected-source payload. The client-boundary test failed with
   `selected source must deliver every verified KEEP role`.

After restoration, all 21 focused tests and the complete repository suite
returned to green. These failures show that the tests observe the authorization
and delivery seams, not only internal role fields.

## What remains unobserved

This result establishes the offline contracts and deterministic kernel only.
It does not establish:

- DeepSeek output validity, agreement, relevance or cost;
- the five frozen development gates on consumed W01-W08;
- OpenAlex compatibility or any X01-X08 provider result;
- candidate precision, recall, source truth, novelty or set coverage;
- report improvement, planner-trigger quality or completed Tool Calling;
- production reliability, user value, adoption or ROI.

The next eligible step is a separately authorized, label-blind W01-W08
development qualification on the merged implementation revision. It may make
at most sixteen `deepseek-chat` calls, must make zero OpenAlex calls, and must
commit every raw response and deterministic decision before private labels are
opened. A failed development gate seals v5; it does not authorize tuning and
replay. X01-X08 and production remain out of scope until that result exists.
