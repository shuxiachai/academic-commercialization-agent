# Provider identity and diagnostic privacy boundary

Date: 2026-09-10
Status: offline_verified / no_paid_canary
Baseline: public main `855bda1af58f8b9697a64547bd82ac8b5dfe217f`.

## Observed defect

Fake-key replay through the real BYOK environment builder and language helper
showed an OpenAI selection sending its key to api.deepseek.com. Qwen selected
the same wrong destination with an empty bearer credential. The main factory
and auxiliary transport shared detection, but not model/key/base resolution.
This demonstrates a reachable defect, **not a confirmed historical disclosure**.

Access-code diagnostics printed complete assignment-looking secrets and
misclassified legitimate Base64 padding. PDF JSON parse errors included a
model excerpt; the HTTP exception logger could also print provider/Pydantic
echoes and the private paper capability. A real factory test additionally
found the advertised Anthropic provider's SDK absent from runtime dependencies.

## Shipped contract

- One immutable, secret-repr-free configuration resolves the logical provider,
  model, base and key for CrewAI and planning/translation. Explicit partial
  credentials fail closed; no empty-key auxiliary request is constructed.
- Inline BYOK pins all four destinations even in the presence of SDK-specific
  base environment variables. Child environment scrubbing also neutralizes
  those variables. Legacy operator DeepSeek/Qwen OPENAI_* aliases are retained.
- Endpoint configuration requires HTTPS without embedded credentials, query or
  fragment; known vendor hosts cannot contradict the logical provider. Custom
  operator HTTPS gateways are still a deliberate operator trust choice, not a
  public visitor URL option or proof of credential ownership.
- Auxiliary requests make one attempt and reject redirects. Qwen sends the
  non-thinking wire parameter; failures visibly retain the untranslated fallback.
- Assignment warnings withhold values; Base64 padding alone is not suspicious.
  Auxiliary warnings and PDF HTTP failure logging retain exception categories,
  not model content, exception chains or paper IDs. The JSON parser no longer
  includes model output in its exception.
- CrewAI stays at 1.14.7. Its declared Anthropic extra supplies the missing SDK.
  A dependency addition is not evidence that every model works online.

## Verification and falsification

Before edits: 2690 tests and 1211 subtests passed with no provider calls.
The focused new boundary module passes 43 tests, including real installed
provider client-parameter construction, four-provider operator/BYOK dispatch,
legacy aliases, missing credentials, cross-vendor/unsafe endpoints, urllib
redirect handling and HTTP-level private-error logging.

Six original-defect injections were detected at the intended regression
assertions: wrong auxiliary host, omitted SDK base, enabled redirects, echoed
access code, echoed model excerpt and traceback logging at the PDF HTTP seam.
Every injected change was restored. A focused test run also exposed import-time
deployment quota contamination; test fixtures now explicitly isolate runtime
limits instead of weakening admission assertions or relying on collection order.

Final local verification: **2734 tests and 1218 subtests**, **89.05% coverage**,
latest Ruff and narrow Pylint passed. Both real Chromium journeys passed with
zero provider calls; the composer intercepted 23 paid POST fixtures and three
held history reads. CI/deployment results are recorded on the release PR. Checks remain
zero-provider; no paid experiment, manual restart or production Tool Calling
activation is part of this repair.

## Limits and follow-up

This closes the named project-owned diagnostics, not all third-party SDK log
emissions or every other operator log path. Credentials must never be printed
to investigate historical use. If an OpenAI BYOK user actually exercised the
old helper, rotation is prudent; the offline replay cannot establish whether
that happened.

Planning/translation and inline PDF calls are still outside Crew-node usage
totals. Historical `cost_complete` means price coverage for recorded node
usage, not the complete end-to-end bill. Fixing Qwen dispatch makes a previously
failing auxiliary attempt functional; it is not an extra speculative planner
or supplement. No general cost/quality benefit is claimed.

Numeric matching, scoring citation contracts, PDF sampling/identity and the
legacy ops reader remain separate follow-up changes. Mixed market metric
classification needs a versioned impact analysis before changing calibrated
scores. Durable submission receipts, parser-process isolation, public-startup
policy and broader accounting are distinct designs; this patch does not
silently claim them solved.
