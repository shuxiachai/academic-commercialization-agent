# Regulator-source title quality audit — frozen protocol

**Frozen:** 2026-08-25, after the denominator census and before the detector
or audit command was implemented.

## Why this is a protocol, not a pre-registration

The post-fix blood-pressure canary had already exposed one garbled FDA title,
and a read-only census had already established that the 30 stored benchmark
runs contain zero sources from the regulator and clinical-registry domains in
scope. Those facts cannot honestly be called unseen predictions. This document
freezes what will be implemented and how the resulting zero denominator will
be reported; it does not relabel a retrospective check as a held-out study.

## Question

Can a zero-network audit:

1. enumerate every stored collection and preserve its content hash;
2. identify sources whose URL belongs to the same narrow regulator or clinical
   registry domain set used by the production coverage policy;
3. distinguish a zero denominator from a clean pass;
4. flag the exact known production title without broadly rejecting plausible
   regulator titles; and
5. retain case-level evidence so a later normalization proposal can be judged
   against observed inputs rather than anecdotes?

The audit does **not** normalize titles and does not change production
retrieval, source scoring, authority coverage, reports, or the Evidence-gap
Planner.

## Frozen scope

The authority hosts are the current production sets on 2026-08-25:

- regulator: `fda.gov`, `ema.europa.eu`, `mhra.gov.uk`, `tga.gov.au`,
  `pmda.go.jp`;
- clinical registry: `clinicaltrials.gov`, `clinicaltrialsregister.eu`,
  `euclinicaltrials.eu`, `isrctn.com`, `anzctr.org.au`.

Exact hosts and their subdomains are in scope. A suffix such as
`fda.gov.attacker.example` is not.

The development census is the 30 direct-child `validated_sources.json` files
under `outputs/benchmark/`. The tracked ten-topic fixture directory will be
run as a reproducibility cross-check, but it is not an additional independent
sample.

## Precision-first title screen

Only explicit structural failures are eligible for `review_required`:

- an empty title;
- a title that is only its URL or host;
- a Unicode replacement character, which proves a decoding loss occurred;
- at least four one-letter alphabetic fragments that make up at least half of
  the alphabetic tokens **and** an official host printed in the title.

The final rule is deliberately conjunctive. Punctuation density, short titles,
all-caps words, product codes, and generic PDF suffixes are not enough to flag
a title because those patterns are common in valid regulator records. A clean
result means only “none of these structural screens fired,” not that the title
is semantically correct.

## Frozen challenge

`evals/regulator_title_quality/challenge-v1.json` contains:

- the exact `M7` title and URL observed in the completed production run
  `20260825T024919Z-d8c43b0ba3479dc46227b4bfaa82f0a4`;
- disclosed synthetic negative controls for normal FDA and registry titles;
- a host-boundary negative control; and
- an explicit decoding-loss positive control.

The production case is post-hoc and the controls are synthetic. Passing this
challenge tests a narrow regression contract, not prevalence, recall, or title
truth.

## Result states

- `not_assessable_zero_denominator`: every collection loaded, but no in-scope
  title existed; this must never be rendered as pass.
- `checked_no_structural_flags`: at least one in-scope title was checked and no
  frozen screen fired.
- `review_required`: at least one in-scope title fired a frozen screen.
- `failed`: a collection, challenge, expected count, or output contract could
  not be validated.

The command may complete successfully with
`not_assessable_zero_denominator`. Completion says the census ran; it does not
invent a quality denominator.

## Acceptance criteria

1. Exactly 30 stored benchmark collections load and appear in the manifest.
2. The observed benchmark state is
   `not_assessable_zero_denominator`, not pass or clean.
3. The exact `M7` case is `review_required` for the frozen fragmented-token
   reason.
4. Both plausible-title controls remain clean and the attacker-domain control
   remains out of scope.
5. Every challenge expectation matches, all fixture and challenge hashes are
   persisted, and repeated evaluation is byte-for-byte deterministic after
   excluding the chosen output directory.
6. Tests run with networking disabled, the writer refuses to overwrite an
   existing audit, the original defect is re-injected once, and the complete
   zero-network suite plus CI lint gates remain green.

## Claims explicitly forbidden

This audit cannot establish regulator-title error rate, title correctness,
source truth, report correctness, held-out precision/recall, or that a title
normalizer should ship. With zero benchmark denominator and one known positive
case, the only valid next-step decision is whether a separately tested,
authority-specific normalizer is worth investigating.
