# Pre-registration: regulator source title recovery candidate

Date registered: 2026-08-25

## Question

Can a deterministic, zero-LLM title recovery rule prevent structurally broken
titles from reaching validated evidence without rewriting a legitimate title or
inventing a document name?

This experiment is deliberately narrower than semantic title verification. It
tests whether an already accepted official regulator or clinical-registry URL
can retain a usable, traceable display title when the search provider's title
is structurally corrupt. It does not establish that a clean-looking title is
semantically correct.

## Evidence already observed before registration

The following are development observations, not prospective validation:

- The original 30-run benchmark and the ten tracked benchmark snapshots contain
  zero official regulator or clinical-registry titles.
- A census of 95 top-level historical runs contains three in-scope rows but only
  two unique ClinicalTrials.gov URLs. All three pass the structural screen.
- One production FDA 510(k) source carried the title
  `"'b, , 4 , I 'b, I - accessdata.fda.gov"` for K222658.
- Running the existing audit directly against `outputs/` failed because its
  mixed-layout discovery also treated `.paid-operation-ledger.json` as a flat
  `SourceCollection`. That input-boundary defect will receive its own regression
  assertion; it is not evidence for or against title recovery.

These observations determined the experiment but cannot be counted as a held-
out result.

## Frozen clean-control collection

The development challenge will contain 24 official records:

1. The first 12 usable records returned by the ClinicalTrials.gov v2 API for
   the fixed query `medical device`, preserving API order at collection time.
   A usable record has an NCT identifier and either `officialTitle` or
   `briefTitle`; `officialTitle` is preferred.
### Data-quality amendment recorded before candidate implementation

The fixed openFDA query returned K243224 with two literal `U+0099` C1 control
characters in `device_name`, rendered as `MitraClip` and `TriClip`. A second
official API request for that exact K-number confirmed the code points. The row
cannot honestly remain a clean control, and it will not be removed or replaced
after selection.

The frozen official sample is therefore classified as **23 clean controls plus
one observed upstream encoding anomaly**. Criterion 1 below applies to all
23 genuinely clean rows. K243224 joins the positive controls and must receive a
neutral identifier label or be rejected; the candidate must not guess that the
control character was intended to be a trademark symbol. This amendment was
made after collection but before candidate code or output was inspected.

2. The first 12 usable records returned by the openFDA device 510(k) API for
   decisions in calendar year 2024, sorted by `decision_date:desc`. A usable
   record has both `k_number` and `device_name`.

The exact request URLs, retrieval timestamp, selected fields, and SHA-256 of
each raw API response will be committed with the frozen challenge. If an
endpoint or query is invalid, the protocol will be amended before inspecting a
substitute response. Records will not be hand-picked after seeing whether the
candidate succeeds.

The official API title is a clean-control label. It is not proof that a search
provider will return the same wording, and it is not a prevalence sample.

## Positive and scope controls

The challenge will also retain, separately from the 24 clean controls:

- the observed K222658 broken title;
- deterministic synthetic corruptions covering replacement characters,
  isolated-letter fragments, empty punctuation, and host-only titles;
- an attacker-suffix host that must remain out of scope.

Synthetic cases test specified behavior only. They must never be included in a
real-world accuracy denominator.

## Candidate behavior

The candidate may act only after canonical URL validation and only for an
allowlisted official regulator or clinical-registry host.

1. Preserve every title that does not trigger the high-precision structural
   screen.
2. For a structurally broken title, derive a neutral label only when a supported
   identifier is present in the canonical URL:
   - `FDA 510(k) record <K-number>` for the known accessdata FDA path;
   - `ClinicalTrials.gov study <NCT-number>` for the known registry path.
3. If no supported identifier can be recovered, reject that source row rather
   than inventing a title.
4. Never fetch a second page, call an LLM, or infer the exact product/study name
   in the production path.
5. Applying the candidate twice must produce the same output.

The neutral label is intentionally less informative than an exact title. It is
traceable and honest about what the URL proves, while the evidence summary and
source URL remain available to the report workflow.

## Acceptance criteria registered before collection

The candidate may enter production only if all criteria pass:

1. **Clean preservation:** 23/23 official clean-control titles remain byte-for-
   byte unchanged and are not sent to review.
2. **Observed defects:** neither the K222658 production title nor the K243224
   official API title is retained. Any replacement contains only the URL-
   derived identifier and a neutral source label, without an inferred device
   name or guessed Unicode repair.
3. **Synthetic controls:** every in-scope malformed control is either replaced
   by a supported neutral label or rejected; none receives an inferred exact
   title.
4. **Scope safety:** attacker-suffix and unsupported hosts cannot receive an
   official fallback.
5. **Idempotence:** every accepted replacement is stable on a second pass.
6. **Audit boundary:** a directory containing run artifacts plus unrelated
   top-level JSON audits the run artifacts without reading the unrelated JSON;
   a flat-fixture-only directory retains strict validation.
7. **Seam coverage:** the recovered or rejected decision is asserted at the
   final `EvidenceSource` construction boundary, not only in a helper test.
8. **No paid or hidden work:** evaluation performs zero network calls, zero LLM
   calls, and reports clean, replaced, rejected, and unchecked denominators
   separately.

Any clean-control rewrite rejects production integration. A partial positive-
control result also rejects integration rather than relaxing the criterion.

## Defect re-injection

After the tests pass, temporarily bypass the recovery call at the
`EvidenceSource` construction seam. The known production case must then either
reach the source unchanged or fail the seam assertion. Restore the production
call and confirm the targeted suite returns green.

## Claims that remain prohibited

Even a passing result does not support claims of semantic title accuracy,
real-world precision/recall, source truth, lower LLM cost, higher report quality,
or better regulatory coverage. A provider-backed canary requires separate paid
authorization and its own result record.
