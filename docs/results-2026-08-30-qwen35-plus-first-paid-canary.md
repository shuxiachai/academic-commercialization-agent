# Qwen3.5 Plus first paid canary

Date: 2026-08-30
Status: single_canary_complete / live_transport_observed / quality_not_validated

## Scope

This was an operator-authorized exploratory canary after the Qwen3.5 Plus
adapter reached public main. It was one production-isolated root run, not a
pre-registered benchmark and not evidence of general model quality.

- Merged revision:
  ff8732d604c12a01d437716aa1585eefb933f8bd.
- Run:
  20260830T125659Z-50c35c817187f804658dda7dcc9a894a.
- Public record:
  <https://academic-commercialization-agent.up.railway.app/run/20260830T125659Z-50c35c817187f804658dda7dcc9a894a>.
- Topic: solid-state sodium-ion batteries using sulfide electrolytes for grid
  storage commercialization.
- Recovery: not requested.
- Evidence-gap planner: shadow no_gap; zero tool calls.

The run used the deployed service and the configured operator Qwen credential.
It did not authorize an evidence-gap supplement, recovery child or a second
root run.

## Observations

The root run completed in 306 seconds.

- Academic sources: 8.
- Patent sources: 8.
- Market sources: 8.
- Failed retrieval domains: none.
- Evidence incomplete: false.
- Provider requests: 7.
- Tokens recorded: 79,261.
- Conservative estimated cost: USD 0.075657.
- Cost completeness: true.
- Every recorded role model: exactly qwen3.5-plus.
- Checkpoints: all seven persisted stages complete.
- Claim grounding: 2 checked, 0 unsupported and 3 unverifiable; all three
  unverifiable claims were in the market domain.
- Quality review: passed.
- Consistency screen: 0 errors and 0 warnings.
- Trace:
  0c8a63f9ed45872726d8ce00cd083c1b, with Phoenix delivery attempted.

The reviewer role recorded two requests while every other role recorded one.
The observable artifacts establish one extra reviewer request, but they do not
retain enough provider detail to prove whether its exact cause was guardrail
regeneration or another CrewAI-internal retry. This record therefore does not
invent a root cause.

## Score-rationale seam found by the canary

The deterministic scoring payload was correct:

- market accessibility: 2.5;
- evidence confidence: 3.5;
- weighted total: 50.3.

However, Qwen emitted the corresponding narrative as "rated at 25" and
"moderate (35)". These are the internal integer scores before the established
divide-by-ten delivery scale. The formula and stored numeric fields were
correct, but the prose that reached the report was not. This is the same class
of seam defect the project treats as high risk: a value can be computed and
stored correctly while a contradictory representation reaches the client.

A census of 79 existing top-level score.json artifacts found no prior use of
either exact phrase. The existing normalizer covered explicit "score is 30",
Chinese score labels and "30/50", but not these Qwen-specific forms.

The fix is deliberately narrow:

- normalize a raw integer only after a score-like noun and "rated at/as";
- normalize a parenthesized raw integer only after a score-like noun and a
  bounded qualitative rating adjective;
- preserve percentages, dates, unlabelled counts and candidate-source counts;
- leave the scoring formula and evidence_confidence floor unchanged.

The two exact canary phrases were added as client-boundary tests. After the fix,
the implementation was removed once while the tests remained: both tests
failed on the original phrases. Restoring the implementation made the whole
score-narrative class pass again.

## Separate quality finding

Manual inspection also found that the report converted an orientation-mode
statement that no owner-approved threshold existed into several apparently
mandatory numeric decision thresholds. One citation attached to a
sulfide-electrolyte processing claim also described an oxide-electrolyte
source.

Those are not score-scale defects and are not changed by this patch. Treating
them as one regex problem would either miss semantic substitutions or create
false-positive blocking on completed paid reports. They remain a separately
scoped decision-contract and citation-entailment problem that needs its own
measured design.

## What this establishes

This single canary establishes that, for this request:

- the official endpoint accepted the adapter's non-thinking JSON requests;
- CrewAI returned structured payloads through every pipeline role;
- the exact provider model identity and usage reached accounting;
- the run completed through the API, checkpoints and browser report seam.

It does not establish:

- Qwen report quality across topics, languages or decision modes;
- equivalence to the frozen DeepSeek benchmark;
- stable latency, retry rate, token usage or realised cost;
- semantic correctness of every citation or recommendation;
- production Tool Calling, which remained at zero calls.

The accurate claim is therefore "one live Qwen3.5 Plus end-to-end canary
completed and exposed a repaired narrative seam," not "Qwen is fully validated
for production."
