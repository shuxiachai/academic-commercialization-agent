# Pre-registration — adding a TRL 8 calibration anchor

Written before the change and before the treatment run. The previous
experiment's treatment arm is the baseline here: nothing has changed in the
repository since it was measured, so re-running it would spend money to
reproduce a number I already have.

## The finding this responds to

TRL scores across 30 runs on frozen evidence:

    2.0  ███ 3
    4.0  ███ 3
    5.0  ███ 3
    5.5  █ 1
    6.0  ███████████ 11
    7.0  █████ 5
    8.0  █ 1
    9.0  ███ 3

Eleven of thirty runs land on exactly 6.0, and the 8 band is empty but for
one run, while 7 and 9 are both populated.

## Diagnosed cause

The five calibration anchors the scorer is told to align against "before
submitting" carry TRL values 9, 9, 7, 7 and 3. **Nothing anchors 8.**

    LFP batteries        TRL=9   mass-produced by dozens of suppliers
    Monoclonal antibodies TRL=9  dozens of approved products
    PEM electrolysers    TRL=7   multiple vendors selling, industrial pilot scale
    L4 robotaxi          TRL=7   paid service in a few cities
    Tokamak fusion       TRL=3   laboratory net-energy gain

So a technology that is approved and selling but not mass-produced has no
reference point. The nearest anchor above requires dozens of suppliers; the
nearest below describes pilot scale. The scorer cannot reach the first, so
it settles at or under the second.

This also puts the anchors in direct conflict with the commercial-signal
table a few lines above them, which says "multiple companies selling
commercial products -> TRL 8-9" while the PEM anchor pins "multiple vendors
selling" at 7. Topic 07 satisfies two rows of that table — three named
companies selling, two national regulatory approvals — and scores 6.0. When
a general rule and a numbered example disagree, the example wins.

The previous experiment is what makes this diagnosis rather than a guess: it
removed the discount rule that was explaining the low scores away, the
reasoning changed to lead with the commercial evidence, and the scores did
not move at all.

## The change

Add a sixth anchor at TRL 8, describing the state 04, 05 and 07 are actually
in: approved and in commercial operation, first-of-a-kind units, not yet
mass-produced.

Floating offshore wind. Chosen because it is not a benchmark topic — the
suite scores none of it, and `tests/test_benchmark_calibration.py` enforces
that separation after anchors naming benchmark topics turned the benchmark
into a recitation test (difficulty 32).

## Predictions (registered before running)

| # | Prediction |
|---|---|
| P1 | Runs scoring exactly 6.0 drop from 11/30 to **≤ 6/30** |
| P2 | Topics 04 and 07 each rise by **≥ 0.5** (mean over 3 reps) |
| P3 | Topics 08 and 10 rise by **< 0.5** — both are low-TRL and must not drift |
| P4 | Pass rate against the anchored ranges stays **≥ 26/30** |

## Falsification criteria (registered before running)

| # | If this happens | Then |
|---|---|---|
| F1 | 08 or 10 rises by ≥ 0.5 | **Global inflation**, not a filled gap. Revert. |
| F2 | Runs at exactly 6.0 stay ≥ 9/30 | The missing anchor was **not** the cause. Revert and look again. |
| F3 | Pass rate falls below 26/30 | Net regression. Revert. |
| F4 | 09 rises by ≥ 0.5 | 09 already scores above its ceiling; pushing it further is the same inflation F1 tests for, on the topic where it is most visible. |

F2 is the one that decides whether this diagnosis was right. The previous
experiment failed on its equivalent, and the honest outcome of two failures
in a row is to stop changing the rubric, not to try a third guess.

## Method

    uv run python benchmark.py --fixtures --force --repeat 3 -c 3

Same frozen evidence as both previous arms. The anchor text is the only edit
between baseline and treatment.
