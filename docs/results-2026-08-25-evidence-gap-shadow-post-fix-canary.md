# Evidence-gap shadow post-fix production canary — result

**Run:** [20260825T024919Z-d8c43b0ba3479dc46227b4bfaa82f0a4](https://academic-commercialization-agent.up.railway.app/run/20260825T024919Z-d8c43b0ba3479dc46227b4bfaa82f0a4)
**Protocol:** [frozen post-fix pre-registration](prereg-2026-08-25-evidence-gap-shadow-post-fix-canary.md)
**Pre-registration commit:** `0bc5693`
**Production revision:** `8d5ef489391cfa72905a8201d3bb55e76a236e14`
**Outcome:** passed the frozen one-run criteria, with disclosed residual limits

## Execution

The operator authorized one paid source run on the same previously observed
topic. The request was accepted at `2026-08-25T02:49:19Z` and no second run,
retry, or resume was submitted.

- Terminal state: `completed`, with `resumed_from=null`
- Elapsed time: 172 seconds
- Sources: 8 academic + 8 patent + 8 market
- Provider use: 87,015 tokens over 6 LLM requests
- Inspectable cost: `$0.035442`, below the `$0.05` soft stop
- Quality review: passed
- Consistency screen: 0 blockers and 0 warnings
- Checkpointing: all seven nodes committed with no errors

## Frozen criteria

| # | Result | Evidence |
|---|---|---|
| 1 | Pass at the deployment seam | GitHub deployment `6075343589` identified revision `8d5ef48...`, Railway reported `success`, readiness passed immediately before submission, and no later deployment preceded this run. The public run payload does not export its raw checkpoint identity, so this was not independently recomputed from the Railway volume. |
| 2 | Pass | The only admitted run reached `completed`; `resumed_from` was null. |
| 3 | Pass | The persisted source collection recorded `weight_profile=biomedical`. |
| 4 | Pass under the pre-registered official-source branch | Authority coverage required `regulatory`, accepted official FDA source `M7`, reported `complete`, and therefore correctly produced `no_gap` rather than the alternative missing-category signal. |
| 5 | Pass | `planner_state=not_run`, `executed_call_count=0`, additional search cost was `$0`, persistence was `written`, and `evidence_changed=false`. Independently loading the final `validated_sources.json` and applying the repository's canonical hash function reproduced `7b2dfae4b4c80b061cd147718fb4f859bdcacc9b2f335f26eaced36f92e78cf9`, exactly matching the pre-evaluation context hash. |
| 6 | Pass | *American Journal of Preventive Cardiology* recurred as `A5` and retained `credibility_tier=high`; the removed generic title-prefix rule did not label it predatory. |
| 7 | Pass | `$0.035442` was inspectable and below `$0.05`. |
| 8 | Pass | Operator history contained exactly one run at or after submission, no child resume, six ordinary workflow LLM requests, and zero planner or supplementary-search executions. |

The accepted regulator record was FDA 510(k) `K222658`. The
[official Devices@FDA entry](https://www.accessdata.fda.gov/SCRIPTS/cdrh/devicesatfda/index.cfm?db=pmn&id=K222658)
identifies it as the Accurate 24 non-invasive blood-pressure monitor and records
a substantially-equivalent decision. This confirms that `M7` is a real,
topically relevant regulator source rather than a host-only false positive.

## Residual limits and new observation

The result closes the two exact production defects that motivated PR #31:
automatic classification reached `biomedical`, authority coverage actually
ran, and the legitimate journal was no longer downgraded. It does not establish
that the current authority screen understands modality-level claim scope.

`M7` describes pulse-wave-transit-time measurement using piezo and NIRS
sensors, while the requested topic specifies PPG-based continuous monitoring.
The report correctly cautioned that `M7` did not confirm the exact PPG modality,
but the deterministic authority screen currently treats a validated regulator
category as covered. Accordingly, `no_gap` means only that an official
regulator source is present; it must not be presented as complete regulatory
evidence for the exact product concept. A modality-sensitive rule would need a
separately frozen semantic challenge set and abstention threshold rather than a
post-hoc keyword patch.

The PDF search title for `M7` was also persisted as garbled extracted text and
appeared that way in the report reference list. Its URL, FDA identity,
credibility, and evidence summary were usable, so this did not change the
frozen pass result. It is nevertheless a presentation-quality defect to assess
offline before deciding whether a high-precision FDA-specific title normalizer
is justified.

Finally, this is one repeated-topic observation. It is not a trigger-precision
rate, evidence-increment result, SLO, or proof that Tool Calling adds value.
Phase 2 remains disabled and still requires the separately frozen challenge set
and thresholds in the original phase-1 protocol.
