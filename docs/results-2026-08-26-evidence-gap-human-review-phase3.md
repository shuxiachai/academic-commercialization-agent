# Result: Phase 3 evidence-gap review return and method audit

**Date:** 2026-08-26
**Source pilot revision:** `adde83dfd7d40c7fdd425b6f665eb121bb300e33`
**Protocol:**
[`prereg-2026-08-25-evidence-gap-human-review-phase3.md`](prereg-2026-08-25-evidence-gap-human-review-phase3.md)

## Outcome

The returned form contains complete, source-grounded labels for all 25
candidates, and every URL is declared attempted. It does **not** produce an
eligible human-value headline. The frozen summarizer reports
`protocol_status=excluded_substantive_ai`, `decision=not_evaluated`, and
`metrics=null` because the returned declaration names
`OpenAI-Codex-GPT-5` and records `generative_ai_use=MOST_OR_ALL`.

After return, the study owner stated that a person had checked the content and
that parts of the declaration might imperfectly describe the process. That
clarification is retained here, but it does not identify an eligible
`NONE` or `LANGUAGE_ONLY` category or retract the returned declaration.
The raw form was therefore not rewritten, and the review remains excluded
under the pre-registered rule.

A second method issue was discovered during intake: packet schema v1 told the
reviewer to compare novelty against the frozen baseline but did not expose the
expanded baseline collection in the reviewer packet. A post-audit summary
therefore adds
`method_issues=["baseline_context_not_exposed_to_reviewer"]` and
`baseline_context_exposed_to_reviewer=false`. It also remains
`excluded_substantive_ai / not_evaluated`.

Production Tool Calling stays disconnected.

## Returned labels

All 25 row identities, titles and URLs matched the frozen packet. No row was
blank, partially completed, duplicated, changed, or marked
`UNVERIFIABLE`.

| Case | Gap domain | Relevant | Not relevant | Rows |
|---|---|---:|---:|---:|
| L01 | academic | 0 | 5 | 5 |
| L02 | patent | 0 | 5 | 5 |
| L03 | market | 2 | 3 | 5 |
| L04 | regulatory | 1 | 4 | 5 |
| L05 | clinical registry | 2 | 3 | 5 |
| **Total** | — | **5** | **20** | **25** |

The form contains five `YES/YES` pairs and twenty `NO/N/A` pairs. For
transparency only, direct arithmetic over those labels would be:

- wrong-source count: 20/25;
- wrong-source rate: 80%;
- cases with at least one `YES/YES`: L03, L04 and L05, or 3/5.

These are **descriptive counts, not protocol headline metrics**. The formal
summary correctly leaves both thresholds `not_evaluated`. Even if the
returned labels were treated as eligible, the 80% wrong-source rate would miss
the frozen maximum of 5% by a wide margin; the 3/5 case-level novelty threshold
alone would be met. The combined decision would therefore still be a fail.

## What the labels suggest

The mixed-domain basic-search adapter was transport-compatible but not
selective enough for production evidence injection:

- general web search found no directly relevant academic performance source in
  L01 and no directly relevant closed-pore patent claim in L02;
- market retrieval found two concrete medium-voltage data-centre signals, but
  three broad forecasts or adjacent transformer pages were not direct evidence;
- the regulatory case found one device-specific FDA authorization signal among
  four generic pages; and
- the clinical case found two matching registered mRNA-vaccine studies among
  three modality, tumour-scope, or personalization mismatches.

This is one five-case diagnostic sample. It does not estimate a general
provider precision rate, but it is strong enough to reject connecting the
current generic adapter to reports.

## Baseline visibility erratum

The write-once source manifest already contained each frozen
`source_collection`, its collection hash, failed-domain state, authority
coverage and synthetic baseline source. Packet schema v1 copied only the case
target and candidate identities. The reviewer could infer that a directly
relevant source filled a declared failed or missing category, but could not
inspect the baseline representation from the packet itself.

That omission matters because “the check found novelty” and “the reviewer was
not given the comparison material” must not collapse into the same state. The
review tool now:

1. projects the frozen collection identity, gap state and complete baseline
   source identity/summary into `baseline_contexts`;
2. writes those contexts into packet schema v2 and explains the relative-
   novelty boundary in the reviewer README;
3. verifies the contexts again against the write-once source manifest during
   summarization; and
4. keeps schema-v1 packets readable but marks
   `baseline_context_not_exposed_to_reviewer`, preventing an otherwise
   eligible old packet from producing headline metrics.

This does not retroactively repair the returned form. The original packet,
original summary and post-audit interpretation remain separate immutable
artifacts.

## Artifact identities

The raw returned forms remain local and Git-ignored. Their identities are
recorded for audit:

| Artifact | SHA-256 |
|---|---|
| `labels.csv` | `5e1d67004fd1d98ae589859f3e62f6f728c395f5be81db42b9124014dbbafc0d` |
| `reviewer_declaration.csv` | `261be9531e51f3fbed7d0c44a711290dd0c4abc54762087c2fbeff25350573d8` |
| `final-summary.json` | `fb8623e38404303b1a2be0c77311bc2620eabcc383e0b556edaf4bca13e3813f` |
| `post-audit-summary.json` | `b00f7cddd3d871c1b490ad9eeecfd6d179eaebc70f3de88dc40b4aa1fb377edf` |

The original paid source hashes and packet-manifest hash remain unchanged.

## Verification

The review subset passes **19/19**. The original omission was then re-injected
by removing the legacy baseline method issue: the new seam test failed because
a schema-v1 packet incorrectly became `complete`. Restoring the check returned
the test to green. The complete zero-network suite passes **1,465 tests plus
627 subtests**. Latest Ruff, the narrow CI Pylint checks, and the **87.07%**
coverage result all pass the existing gates.
A real zero-network schema-v2 packet was also generated from the original four
paid artifacts rather than a test fixture. It exposes all five baseline
contexts, reports `baseline_context_exposed_to_reviewer=true`, remains
`incomplete / not_evaluated` at 0/25 labels, and has packet-manifest SHA-256
`7d1e4e23b65d6aedfe4854768e1dd7431b6819b09c7af9770e7aefc2d60198d7`.


## Decision and next gate

Do not connect supplementary results to `validated_sources.json`, and do not
run the planner-trigger study yet. The next value experiment should first
replace the one-size-fits-all search with narrow domain strategies and freeze
an unseen challenge:

- academic: scholarly APIs and performance-study filters;
- patent: claim-oriented patent retrieval rather than generic web results;
- market: company, customer, funding or deployment evidence;
- regulatory: exact device/action records from authority sources; and
- clinical: registry-native condition, intervention and study-type fields.

A future packet must use schema v2 and an independently declared eligible
review process. Only after candidate relevance clears its own gate is planner
trigger precision worth measuring.

## Supported claim

> One disconnected five-case Tavily pilot proved request, quarantine and cost
> compatibility, but its returned form contained only 5/25 directly relevant
> candidates and was ineligible for a human-value headline because substantive
> AI use was declared. The generic adapter remains out of production, and the
> reviewer packet now exposes its frozen comparison baseline instead of treating
> missing comparison context as a successful novelty check.
