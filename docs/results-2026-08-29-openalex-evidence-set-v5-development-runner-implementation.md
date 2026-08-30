# Result: evidence-set v5 label-blind development runner

**Date:** 2026-08-29

**Result state:** zero-network runner implementation complete; W01-W08 model
quality and all human-label-dependent development gates remain `not_evaluated`.

## Outcome

The production-disconnected W01-W08 development runner now implements the paid
call boundary required by the frozen
[v5 protocol](prereg-2026-08-29-openalex-evidence-set-v5.md). It locks the
exact 64-row public title/abstract packet, source lock, completed human labels,
and reviewer declaration before any case expansion. The label and declaration
bytes are hashed but never decoded or parsed. Only the already label-blind
packet is parsed.

The runner derives W01-W08 role descriptions mechanically from the previously
frozen v4 source-text concept groups. It does not hand-author roles from the
completed labels. Each judge input contains only candidate SHA-256, title,
abstract, topic, and code-owned role descriptions. Baseline text, URL, DOI,
publisher, OpenAlex metadata, v4 decisions, human labels, and reviewer notes
cannot cross the model boundary.

No DeepSeek call, OpenAlex request, private-label parse, production import,
report connection, or planner trigger occurred in this implementation phase.

## Paid-call boundary

`src/academic_agent/tools/deepseek_evidence_judge.py` adds a strict
OpenAI-shaped DeepSeek adapter with these properties:

- fixed `https://api.deepseek.com/chat/completions` endpoint and
  `deepseek-chat` model;
- temperature zero and JSON-object response mode;
- exactly one transport invocation per adapter call;
- no redirect, retry, repair, fallback, streaming, or model switching;
- absent or inconsistent provider model identity is terminal;
- absent or inconsistent token accounting is terminal rather than zero cost;
- cached prompt tokens use the repository's existing provider-aware pricing;
- request body hash, prompt hash, provider IDs, token usage, cost basis,
  latency, and trace ID reach the response contract; and
- credentials exist only in the outbound authorization header and cannot
  enter request identities, model prompts, errors, or artifacts.

`openalex_evidence_set_development.py` adds the write-once study runner:

1. verify every source and implementation byte identity;
2. reserve a new output directory;
3. write the complete manifest before constructing a model client;
4. perform at most 16 calls under an explicit USD soft stop;
5. write each pass response and usage before permitting the next call;
6. after both passes, write the complete deterministic case decision before
   permitting the next case; and
7. write execution, all-candidate decisions, and a hashed artifact index.

Malformed judge JSON is not repaired. It remains a completed, billed call and
the existing kernel converts the case to explicit abstention. Transport,
identity, usage, or cost failures stop the study without retry. A partial run
cannot report label-join readiness, and zero checked candidates cannot report
a passing agreement rate.

## Real zero-network preflight

The default CLI path was executed against the real local W01-W08 packet. It
verified:

- 8/8 ordered cases and 64/64 ordered candidate identities;
- 16 distinct model inputs and 16 distinct prompt identities;
- source lock SHA-256
  `8a9747f4240fc7c529d8d8f2a737fb21b502579ad2f69c19587bf093cabba7af`;
- packet SHA-256
  `68e15abdca46f4a65d33a75aedaa9a0eac2112a90a8b1e6eb1d00e71e59b8616`;
- labels SHA-256
  `45d12929290de9482dfcd89af61fc6e5ea74b6e63c0eec9f686f4fa0aa11d3ad`;
- declaration SHA-256
  `eb17b0ae23599575afcd9a68ad6a6d64644d4c0001fd10cdabb853a3f3ee1a31`;
- v4 fixture SHA-256
  `f4267c6a79c0bb8a685664de5086e4cfff59ebac1b352cbb56c2277957a55cc3`;
- strict adapter SHA-256
  `2228d4933df066d9ced0dd4b067a85f7377ad5456f33b52005f7a996bc4cbd50`;
- `real_network_calls_performed=false` and
  `real_model_calls_performed=false`; and
- `private_label_bytes_hashed=true` with
  `private_label_content_parsed=false`.

The runner records its observed self-hash instead of embedding it in itself,
which would create a recursive identity. Every other behavior-bearing
dependency is checked against an expected SHA-256 before output reservation.
A future paid authorization must name the merged Git revision, which binds the
runner's observed bytes as well.

## Verification

Focused zero-network tests after the final accounting hardening:

```text
15 passed in 1.99s
```

The first complete-suite run, before adding the final token-total seam test,
reported:

```text
1747 passed, 639 subtests passed in 29.68s
```

After the final token-total seam test and documentation sync, the complete
zero-network suite reported:

```text
1748 passed, 639 subtests passed in 30.09s
```

`uv run --with ruff ruff check .` passed with the CI-equivalent latest Ruff.
The narrow `E0701` Pylint check rated the two new runtime modules 10.00/10.

No warning ignore, relaxed assertion, skipped test, or network-dependent test
was added.

## Defect re-injection

The manifest write was temporarily moved after adapter construction. The
client-boundary test failed because its injected factory observed that
`manifest.json` did not exist. After restoring the correct order, the same
test passed. This proves the test observes the durable pre-call boundary rather
than merely checking a manifest field after execution.

The earlier v5 kernel phase separately re-injected quote bypass and
computed-but-undelivered role defects. Those tests remain green and are not
replaced by this runner-order check.

## What remains unobserved

This result establishes implementation and zero-network preflight only. It
does not establish:

- DeepSeek JSON validity, order robustness, semantic accuracy, token use,
  latency, or cost on W01-W08;
- any of the five frozen development gates;
- whether X01-X08 may be requested;
- OpenAlex source truth, report improvement, planner precision, user value,
  or production Tool Calling; or
- production reliability, adoption, ROI, or an SLO.

The next eligible action is a separately authorized run naming the merged
revision, `deepseek-chat`, at most 16 sequential model calls, zero OpenAlex
requests, and an explicit soft USD stop. Only after all responses and decisions
are durably committed may a separate checker parse the locked human labels.
A failed development gate seals v5; W01-W08 may not be tuned and replayed into
a pass.
