# Result — CrewAI 1.14.7 against 1.15.29 on frozen evidence

The decision rule was stated in [pull request 325](https://github.com/shuxiachai/academic-commercialization-agent/pull/325)
before any run. There is no separate protocol document; the deviations from
what that pull request planned are listed below.

**Summary.** The upgrade would close the last four Dependabot alerts (mcp
#71–#73, opentelemetry-api #67). By the rule stated in advance it is **not
adopted**, and the pin stays at 1.14.7:

- Completion did not fall: 20 of 21 runs in each arm.
- Median tokens per run rose 1.9% (76,464 to 77,902), inside the 15% bound.
- One topic left its expected TRL range: topic 10 scored 2 and 2 on 1.14.7,
  and 3 and 2 on 1.15.29. The rule allows none.

That one departure is the size of the old version's own variation: the
committed 30-run baseline has topic 10 at 3, 2, 2. Four follow-up runs on two
other models all scored 2. On its own it would be a weak reason to hold back.

The stronger reason was found while reading a CI failure, and the benchmark
did not measure it. **CrewAI 1.15.29 checks the size of every request before
sending it, and when a model is missing from its catalogue it assumes a window
of 8,192 tokens.** If a task then takes a second model turn, the conversation,
evidence registry included, is replaced by a model-written summary. Three of
the five models used here are missing from the catalogue. It did not fire in
any of the 28 upgrade-arm runs, and it cannot fire on the first turn of a
task. It can fire on a later one, and any key a user brings may name such a
model.

## What was run

Frozen fixture evidence, so the framework was the only variable.

| | Baseline arm | Upgrade arm |
|---|---|---|
| Code | `main` at `9b13295` | `upgrade/crewai-1.15.29` at `52f5e84` |
| CrewAI | 1.14.7 | 1.15.29 |
| Python, platform | 3.13.13, Windows | 3.13.13, Windows |
| Evidence | fixtures, 85 days old | the same; digests equal in every pair |

Command, per batch: `benchmark.py --fixtures --only <topics> --experiment-id <id>`
with `LLM_PROVIDER=qwen`, `QWEN_MODEL=<model>` and
`AGENT_OBSERVABILITY_ENABLED=false`. Every run is one row in
[runs.json](artifacts/2026-11-05-crewai-1.15.29-comparison/runs.json).

**Deviations from the plan.**
- **Repetition is across models, not within one.** The plan was two
  repetitions of ten topics on one model. Only free quota was authorised, and
  no model had enough for forty runs. Each topic ran once per arm on each of
  two models, so a pair shares its model and the second model is the
  repetition.
- **Models.** Topics 01–05: `qwen3.6-plus` and `qwen3.6-flash`. Topics 06–10:
  `qwen3.5-plus-2026-02-15`, with `qwen3.5-397b-a17b` on 06–09 and
  `qwen3.7-max-preview` on 10. Topic 08 also ran on `qwen3.7-max-preview`.
  None is the production model, whose quota was left untouched.
- **One model excluded.** `qwen-max` failed all five runs in both arms at the
  same step: it returned `source_ids` as a string where the evidence schema
  requires a list. It is excluded from both arms and its ten runs are in the
  artifact.
- **Two single runs are counted.** A pilot (topic 03, `qwen3.6-plus`) and a
  model qualification (topic 06, `qwen3.5-397b-a17b`) on the baseline arm are
  that arm's observation for those cells.
- **Not tabulated.** The plan also named formula and structure checks, the
  numeric-citation proxy, recorded cost and reviewer correction counts. They
  are not compared here. Cost on free quota is not meaningful.

Counted runs: 42, of which 21 per arm. Excluded: 10. Follow-up: 4. Recorded
tokens across all 56: 3,483,954, for successful runs only. No run hit a rate
limit.

## Outcomes

| | 1.14.7 | 1.15.29 |
|---|---:|---:|
| Completed | 20 / 21 | 20 / 21 |
| TRL inside the expected range | 17 / 20 | 15 / 20 |
| — among the 19 pairs where both arms completed | 16 | 15 |
| Median tokens per run | 76,464 | 77,902 |
| Median seconds per run | 438 | 372 |
| Mean overall score | 62.1 | 60.9 |

Across the 19 pairs where both arms completed, TRL was identical in 15 and
within one level in all 19. The overall score differed by −0.24 on average,
median 0.00, from −6.0 to +5.3.

Each arm lost one run, on a different topic, to the same step: the reviewer's
correction plan failed its contract after its retries (baseline: topic 08 on
`qwen3.5-plus-2026-02-15`; upgrade: topic 02 on `qwen3.6-flash`).

| Topic | Model | TRL 1.14.7 | TRL 1.15.29 | Overall 1.14.7 | Overall 1.15.29 | Tokens 1.14.7 | Tokens 1.15.29 |
|---|---|---:|---:|---:|---:|---:|---:|
| 01 (7–9) | `qwen3.6-plus` | 9 | 9 | 72.5 | 72.5 | 65,816 | 84,650 |
| 01 | `qwen3.6-flash` | 8 | 8 | 70.3 | 73.3 | 73,386 | 65,230 |
| 02 (6–8) | `qwen3.6-plus` | 7 | 7 | 68.1 | 68.1 | 71,335 | 72,059 |
| 02 | `qwen3.6-flash` | 7 | failed | 69.6 | — | 103,655 | — |
| 03 (5–7) | `qwen3.6-plus` | 6 | 6 | 58.0 | 60.0 | 77,003 | 79,013 |
| 03 | `qwen3.6-flash` | 5 | 5 | 48.7 | 52.7 | 92,755 | 78,862 |
| 04 (6–8) | `qwen3.6-plus` | 7 | 7 | 69.3 | 70.3 | 77,315 | 77,264 |
| 04 | `qwen3.6-flash` | 6 | 6 | 62.0 | 58.0 | 75,926 | 77,056 |
| 05 (7–9) | `qwen3.6-plus` | 8 | 8 | 68.8 | 68.8 | 80,468 | 78,540 |
| 05 | `qwen3.6-flash` | 7 | 8 | 67.1 | 71.8 | 81,445 | 79,190 |
| 06 (6–8) | `qwen3.5-plus-2026-02-15` | 7 | 7 | 69.8 | 69.1 | 83,945 | 85,238 |
| 06 | `qwen3.5-397b-a17b` | 7 | 7 | 69.1 | 69.1 | 92,214 | 94,038 |
| 07 (6–8) | `qwen3.5-plus-2026-02-15` | 6.5 | 6 | 65.4 | 59.8 | 73,187 | 84,810 |
| 07 | `qwen3.5-397b-a17b` | 6.5 | 7 | 65.4 | 65.1 | 73,255 | 73,907 |
| 08 (2–4) | `qwen3.5-plus-2026-02-15` | failed | 5 ⚑ | — | 51.1 | — | 68,985 |
| 08 | `qwen3.5-397b-a17b` | 6 ⚑ | 6 ⚑ | 56.8 | 55.8 | 67,256 | 68,911 |
| 08 | `qwen3.7-max-preview` | 4 | 4 | 64.4 | 61.4 | 90,088 | 86,155 |
| 09 (3–5) | `qwen3.5-plus-2026-02-15` | 6 ⚑ | 6 ⚑ | 64.0 | 60.0 | 69,877 | 70,143 |
| 09 | `qwen3.5-397b-a17b` | 6 ⚑ | 6 ⚑ | 64.0 | 64.0 | 70,465 | 70,868 |
| 10 (1–2) | `qwen3.5-plus-2026-02-15` | 2 | 3 ⚑ | 31.7 | 37.0 | 75,556 | 76,872 |
| 10 | `qwen3.7-max-preview` | 2 | 2 | 36.7 | 30.7 | 95,234 | 111,657 |

⚑ outside the expected range, shown in brackets beside the topic.

## The rule, applied

1. **Completion does not fall.** Holds: 20 of 21 in each arm.
2. **No topic leaves its range that was inside it at baseline in every
   repetition.** Fails on topic 10. Topics 01–07 hold; topic 02 has one
   upgrade observation because the other run failed. Topics 08 and 09 were
   not inside the range at baseline in every repetition, so the rule does not
   apply to them.
3. **Median tokens rise by no more than 15%.** Holds: +1.9%.

The rule said that anything else is reported and the pin stays.

**Context for topic 10, gathered after the verdict and not part of it.**
- Four follow-up runs, topic 10 on `qwen3.6-plus` and `qwen3.5-397b-a17b`,
  one per arm: all four scored 2.
- The committed 30-run baseline, on older code and another model, has topic
  10 at 3, 2 and 2 across three repetitions
  ([stability table](../outputs/benchmark/benchmark_stability.csv)). In that
  table four of ten topics move by a level or more between repetitions.

So seven of the eight topic-10 runs here scored 2, and the one 3 is a value
the old version has produced itself.

## What the benchmark did not measure: the pre-call context check

**How it was found.** CI on the pull request failed one test,
`test_cold_start_real_crew_success_ignores_shared_threads`, which runs three
mocked five-task crews under a 5-second limit per crew. An earlier local
failure of the same test had been put down to machine load. It is not load.
Five alternating runs on each version:

| Mocked five-task crew | 1.14.7 | 1.15.29 |
|---|---:|---:|
| First crew in the process | 0.24–0.47 s | 3.36–4.01 s |
| Later crews | 0.17–0.30 s | 2.67–3.07 s |

On the CI runner the first crew took 5.391 s and the test stopped.

**Mechanism.** Before every model call, 1.15.29 counts the request's input
tokens and compares them with the model's usable window
(`get_llm_response` → `_proactively_summarize_context` in
`crewai/utilities/agent_utils.py`). 1.14.7 has no such step; it summarised
only after a provider refused a request as too long.

- **Counting.** On OpenAI's own host the count is a request to the
  provider's token-count endpoint. Sampled stacks during the slow seconds are
  inside that request, and the test process looked up `api.openai.com`; on
  1.14.7 it looked up nothing. The test replaces the generation call but not
  this one, so under 1.15.29 it sends its dummy prompt and placeholder key to
  OpenAI. On an OpenAI-compatible server, which is how this project reaches
  Qwen and DeepSeek, no request is made: the count is characters divided by
  four, with a warning logged on every call.
- **Window.** The window comes from a catalogue shipped with CrewAI, at 85%
  of the listed size. A model that is not listed gets 8,192 tokens, so 6,963
  usable.

| Model, through this project's factory | Usable window 1.15.29 assumes |
|---|---:|
| `qwen3.7-max-2026-06-08` (production) | 843,036 |
| `qwen3.8-flash`, `qwen3.5-plus-2026-02-15` | 843,036 |
| `qwen3.5-397b-a17b` | 222,822 |
| `deepseek-chat` | 111,411 |
| `qwen-plus` | 109,670 |
| `qwen-max` | 26,112 |
| `qwen3.6-plus`, `qwen3.6-flash`, `qwen3.7-max-preview` | **6,963** |

- **What happens over the window.** If the conversation is one system and
  one user message, nothing: the request is sent as it is. That is the first
  turn of every task here, and a guardrail retry starts a new conversation of
  the same shape. If the conversation has more messages, which happens when
  the executor asks the model to repair a malformed reply, everything but the
  system message is replaced by a summary the model writes.

**Demonstration.** [compaction_probe.py](artifacts/2026-11-05-crewai-1.15.29-comparison/compaction_probe.py)
builds the model through `llm_config.create_llm`, replaces its call methods
and blocks name resolution. With a registry of 700 rows, about 14,300 tokens
at four characters each:

| Model | Turn | Registry rows left | Summarising calls |
|---|---|---:|---:|
| `qwen3.6-plus` | first | 700 | 0 |
| `qwen3.6-plus` | second | **0** | 3 |
| `qwen3.7-max-2026-06-08` | first | 700 | 0 |
| `qwen3.7-max-2026-06-08` | second | 700 | 0 |

On 1.14.7 the probe reports that the check does not exist.

The summarising calls go through the model's async method. This project's
retry, deadline and refused-parameter handling wrap the synchronous one, so
those calls run outside all three.

**In the benchmark.** The upgrade-arm logs carry the per-call warning, so the
check ran. None carries the "Context summarization triggered" panel that a
verbose run prints, in any of the 28 upgrade-arm runs, 13 of them on models
with the 6,963 window. The comparison above is therefore not affected by it.

**Why it matters here.** Every report rests on a registry the code validated
and the model may not rewrite. A summary written by the model in its place
breaks that silently: the run completes and the report looks normal.
Accounts must bring their own key, and the model that key names is not
limited to CrewAI's catalogue.

## Limits

- One run per topic, model and arm. With this spread a one-level TRL
  difference in one pair cannot be told from noise, in either direction.
- Not the production model, and no run used live retrieval.
- The second-turn path is shown by construction, not observed in a pipeline
  run. How often the executor takes a second turn here was not measured.
- Whether a provider with its own count endpoint other than OpenAI makes the
  extra request was not checked.
- CrewAI's anonymous telemetry endpoint is present in both versions; the
  test process on 1.15.29 looked it up because it ran long enough for an
  export. That is not a change.
- While building the demonstration, two earlier probe runs replaced only the
  synchronous call, so the summariser sent synthetic text to the Qwen
  endpoint with a placeholder key and was refused (401). Nothing was billed
  and no real evidence or key was involved. The committed probe blocks name
  resolution.

## What adopting it later would take

Not done in this change, and each is a decision for the maintainer:

- Turning the check off for every agent (`respect_context_window=False`)
  removes the pre-call step, and with it the older summarise-after-refusal
  path, so an over-long request fails instead of being rewritten. It needs its
  own test and a rerun of the suite.
- The cold-start test must stop reaching OpenAI's host under 1.15.29.
- Until then the four alerts stay open. The vulnerable code is not reached by
  this deployment: it opens no MCP session, runs no MCP server, never reads
  trace context from a request, and installs no web-framework instrumentation.
