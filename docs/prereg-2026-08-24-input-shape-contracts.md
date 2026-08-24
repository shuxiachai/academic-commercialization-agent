# Pre-registration: real-traffic input-shape contracts

**Registered:** 2026-08-24, before changing request validation or the browser
topic-shape helper.

## Question

Can the public submission boundary distinguish three shapes that are absent
from the 30-run calibration benchmark—specific Chinese topics, unusably short
inputs, and explicit non-research content requests—without turning a heuristic
into a hard research-topic classifier?

This is a zero-network contract audit. It does not add topics to the TRL
calibration benchmark, evaluate report correctness, or justify changing the
scoring formula. The paid Chinese production run completed earlier on the same
date is operational evidence, not an observation used to tune these rules.

## Frozen cases and expected outcomes

| ID | Input | Expected contract |
|---|---|---|
| C1 | `  钠离子电池在低成本储能系统中的商业化应用  ` | Accept. Trim only boundary whitespace, return the normalized topic, persist that exact value in the immutable RunSpec, and pass it to the worker. No browser scope warning. |
| S1 | `AI` | Reject with HTTP 422 before `runs.start_run` is called. |
| S2 | spaces, tabs, and newlines only | Reject with HTTP 422 before `runs.start_run` is called. Never turn malformed public input into an internal 500. |
| B1 | `AI education` | Show the existing advisory confirmation before the paid request; allow the user to continue after confirmation. |
| N1 | `Write me a birthday poem` | Show the same advisory confirmation before the paid request; do not add an API-level ban. |
| N2 | `帮我写一首生日诗` | Show the same advisory confirmation before the paid request; do not add an API-level ban. |

The distinction is intentional. Length and whitespace are deterministic input
validity properties. Whether a longer phrase is a legitimate research topic
is not: a culinary process, a music-generation model, or a creative-industry
technology can all be commercial research. Non-research detection must
therefore be an optional confirmation and precision takes priority over recall.

## Negative controls

The advisory detector must not warn for either of these adjacent legitimate
topics:

- `AI-assisted poetry generation models for creative industries`
- `生成式人工智能在音乐创作产业中的商业化应用`

It must also return false for all ten topics in
`benchmark_fixtures/manifest.json`. An attached paper continues to suppress a
length-only warning because the paper supplies scope, but it must not suppress
an explicit content-generation request.

## Implementation boundary

1. Normalize `RunRequest.topic` before Pydantic applies its existing 3–300
   character constraint. Do not catch the later RunSpec exception or convert
   arbitrary validation failures into short-topic errors.
2. Extend the shipped JavaScript helper with only high-precision imperative
   patterns. Do not build a keyword classifier for every non-technical domain.
3. Assert the paid seam: invalid inputs must not call `runs.start_run`; accepted
   Chinese text must reach the HTTP response, durable RunSpec, and worker
   command with the same normalized value.
4. Keep the confirmation call before `api.startRun` and test that ordering from
   the shipped JavaScript.

## Falsification criteria

The change is rejected or narrowed if any of the following occurs:

- one frozen benchmark topic or either adjacent legitimate control is warned;
- a malformed short input reaches `runs.start_run`;
- a valid Chinese topic changes anywhere between request, RunSpec, response,
  and worker launch;
- an explicit non-research request is blocked rather than merely confirmed;
- the full zero-network suite, Ruff, or the narrow Pylint check fails.
