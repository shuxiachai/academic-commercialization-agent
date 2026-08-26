# Erratum: target-user form enums and Stage 2 AI-use timing

**Recorded:** 2026-08-26, after both Stage 1 folders were returned and before
either Stage 2 report was materialized or exposed

## What the first returns revealed

Both reviewers completed the substantive Stage 1 questions, but both used
natural-language labels where packet schema v1 expected fixed enums. Examples
included `No` instead of `NONE`, a prose decision instead of `DEFER`, and a
percentage confidence instead of an integer from 1 to 5. The validator rejected
these mechanically even though their intended meaning was inspectable.

This was an instrument-usability defect, not a reviewer-quality result. The
generated README described the concepts but did not enumerate the legal CSV
values. A schema can be strict internally and still fail at its human boundary
if the person filling it cannot see the contract.

The returned folders are retained byte for byte in the private audit packet.
The study owner created separate normalized copies with a field-by-field coding
record before any report or follow-up outcome existed. No original response was
overwritten. The coding does not change the two registered slots, selected
topics, reports, questions, or result threshold.

## A second timing defect found before Stage 2

The Stage 1 profile asked for generative-AI use, but it was locked before a
reviewer could read the Stage 2 report. If the reviewer later used AI for the
follow-up, schema v1 had no field in which to disclose that new behavior. The
summary could therefore classify a response using a declaration that only
described work performed before report exposure.

Follow-up schema v2 adds its own `generative_ai_use` and
`generative_ai_notes`. Eligibility now excludes substantive AI use declared at
either stage. Translation or clerical use remains retained with disclosure and
requires notes. The Stage 2 snapshot records the follow-up schema version so a
legacy form cannot be interpreted under the new rule silently.

## Implementation correction

- Stage 1 and Stage 2 README files render enum options directly from the
  validator constants instead of maintaining a second handwritten list.
- Numeric scales and required free-text behavior are explicit.
- Packet and source-lock schema v1 are now checked at every later command.
- Stage 2 snapshots are schema v2 and bind that version alongside the existing
  reviewer, baseline, source, and delivered-report hashes.
- Public AI-use disclosure separates Stage 1 from Stage 2.
- Substantive AI use at either stage excludes the row from target-user evidence.

The test suite asserts that every accepted enum is present in the generated
instructions, that the Stage 2 schema reaches the snapshot, that non-`NONE` AI
use requires notes, and that Stage 2 substantive AI use reaches the eligibility
decision. The old profile-only eligibility expression is deliberately
re-injected before release; the seam test must fail before the implementation
is restored.

## Claim boundary

At the time of this correction there are two coded Stage 1 baselines and zero
follow-up observations. This erratum establishes a cleaner measurement seam;
it is not evidence of report usefulness, factual accuracy, adoption, ROI, or a
six-stage advantage.
