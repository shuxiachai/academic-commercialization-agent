# Erratum: adaptive role-gap v8 frozen query scope

**Date:** 2026-09-02 (Australia/Sydney)

**Status:** corrected before any provider request, model call, private label,
live runner, or production connection

## What the zero-network preflight found

The original v8 fixture was committed with raw SHA-256
`ebdaf5da97a941abf7499b87bfcd3602db117a1be054ed3d13ef4ca3906f88f2`.
The first implementation test stopped while expanding the frozen closure
portfolio because six of 80 closure queries shared only one exact token with
their case topic. The existing evidence-gap authorization boundary requires at
least two exact non-stop-word topic tokens. The cause was lexical inflection or
number rather than a different search intent: for example, `hydrolases` in the
topic did not equal `hydrolase` or `hydrolysis` in the query.

This was a useful preflight failure. The authorization rule was not weakened or
bypassed, and no synthetic context was substituted for the frozen case topic.

## Narrow correction

One existing exact topic token was appended to each affected query:

| Case | Role | Added topic token |
|---|---|---|
| AC01 | `enzymatic_pet_depolymerization` | `polyester` |
| AC01 | `monomer_yield` | `polyester` |
| AC01 | `enzyme_thermal_stability` | `polyester` |
| AD01 | `polyurethane_hydrolase` | `depolymerization` |
| AD01 | `enzyme_durability` | `depolymerization` |
| AD05 | `cycling_stability` | `carbon` |

The corrected fixture SHA-256 is
`0be98f249bfd1eaf891cd3c20903b9d6ae4cd2d6431282ee32e82298a2d8ecc7`.

## What did not change

The 16 topics, 80 semantic roles, 80 signal-group portfolios, role priorities,
anchor queries, intended closure meanings, AC/AD split, request and cost caps,
human gates, and falsification rules are unchanged. AC and AD were still
unopened when this correction was made. This erratum does not authorize a live
run and does not turn the corrected queries into evidence of retrieval value.
