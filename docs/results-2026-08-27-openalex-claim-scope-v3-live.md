# Result: OpenAlex claim-scope v3 frozen live execution

**Executed:** 2026-08-27

**Revision:** `ad70d72120e86dad5d04f99cce319a61a623508e`

**Protocol:**
[`prereg-2026-08-27-openalex-claim-scope-v3.md`](prereg-2026-08-27-openalex-claim-scope-v3.md)

## Result in one sentence

The production-disconnected V01-V08 run completed eight anonymous OpenAlex
requests for USD 0.008 of provider-reported usage and the frozen claim-scope
gate retained 13 candidates across 7/8 cases, so the mechanical source-lock
gate passed; source relevance, baseline-relative novelty, wrong-source rate,
planner precision and report value remain `not_evaluated` until an eligible
human review is returned.

## Preconditions and authority

The study owner authorized one complete observation with:

- at most eight V01-V08 cases in frozen order;
- exactly one request per attempted case;
- a USD 0.01 provider-reported soft stop;
- no retry, redirect, API key, LLM, supplementary search or recovery;
- no Planner, report-workflow or production connection.

Before execution:

1. PR #63 was merged as revision `ad70d721...`;
2. all eight `main` CI jobs passed on Linux and Windows, Python 3.11/3.12,
   coverage, lint, Chromium smoke and Docker;
3. Railway deployment `6121001674` reported `success` for the same revision;
4. `/health/ready` returned HTTP 200 with all four checks `ok`;
5. `/health` reported zero active runs and zero active paid operations;
6. the zero-network preflight revalidated all eight collection, plan, profile,
   idempotency, fixture and implementation identities;
7. `OPENALEX_API_KEY` was confirmed unset without reading or printing a value;
8. the write-once output directory did not already exist.

## Observed execution

| Measure | Observation |
|---|---:|
| Authorized cases | 8 |
| Attempted / successful cases | 8 / 8 |
| Requests | 8 |
| Retries / redirects | 0 / 0 |
| Provider rows | 64 |
| Claim-scope `ACCEPT` | 13 |
| Claim-scope `ABSTAIN` | 51 |
| Cases with at least one `ACCEPT` | 7/8 |
| Provider-reported cost | USD 0.008 |
| Summed request latency | 13,120.4 ms |
| Stopped reason | `completed` |
| Review packet eligibility | `eligible_for_source_lock` |
| Source value | `not_evaluated` |

Every case made one request and reported USD 0.001. Per-case results were:

| Case | Provider rows | `ACCEPT` | `ABSTAIN` | Latency (ms) |
|---|---:|---:|---:|---:|
| V01 | 8 | 2 | 6 | 2,023.9 |
| V02 | 8 | 1 | 7 | 893.7 |
| V03 | 8 | 4 | 4 | 1,835.1 |
| V04 | 8 | 0 | 8 | 1,630.2 |
| V05 | 8 | 1 | 7 | 1,635.5 |
| V06 | 8 | 2 | 6 | 1,666.8 |
| V07 | 8 | 1 | 7 | 1,731.3 |
| V08 | 8 | 2 | 6 | 1,703.9 |

The frozen mechanical threshold was at least one accepted candidate in 6/8
cases. The observed 7/8 passes only that threshold. It is not evidence that any
accepted paper is relevant or novel.

## Write-once evidence identity

The source directory is
`outputs/2026-08-27-openalex-claim-scope-v3-live-ad70d72/`. It is intentionally
gitignored because it contains full provider responses. The public result
records the hashes needed to detect later byte drift:

| File | SHA-256 |
|---|---|
| `manifest.json` | `a28e6d2d84d539b256917ee89d0bb58e043b34592bc2e97899a4bb44a8630ede` |
| `execution.json` | `aea0ded720262bb013df9c244d673acd3398f7efb8738d61d5f89ba3774eb60a` |
| `candidates.csv` | `391fafd74a1b1ed6b3eb5eb20abd88e32dfea5692d5f9ab251880d38d79b912b` |
| `review.csv` | `117b6256d3122bd1308f073648abf7e07528c22805d479801ae2bb2206bc2bd6` |
| `artifact-index.json` | `ac4387fecd94394b20fed5e861af717204053182ff0897e5d9e32ab2b4457c4d` |
| `case-executions/V01.json` | `002e0714aaad07c2c340d3770223258f73647334c186125fa379e93de5783fbf` |
| `case-executions/V02.json` | `c89241f3ecb5677f4f26633be624e12ef0a8690be994001e1f608e31c186f296` |
| `case-executions/V03.json` | `8ffd57429135f14a07a71d16fe813c5a5788d66674d60f1a2042cf92e0fd318c` |
| `case-executions/V04.json` | `211091ae9ce2fc00cd080c3fc758b884aa10201701c8a53981ba731ba306ecff` |
| `case-executions/V05.json` | `aa487770203a4dc3eec14feabd8358c73e822682e63e2ecd8e7e8f76e9d633ea` |
| `case-executions/V06.json` | `3f4ae61ecc4c1e91e91ee97704e522a83263c698277822c770ab820914f2adb7` |
| `case-executions/V07.json` | `1c7ff909b5a82b9b57f63eeadf01297d5880be4ecf5d77e7db8088f2be5e1e68` |
| `case-executions/V08.json` | `9239a761e2b1e872e50b79d8d134aba4d3ae02ce09276e1ad0d751950e45142d` |

The four aggregate hashes were independently recomputed after the run and
matched `artifact-index.json` byte for byte.

## What passed and what did not

Passed:

- anonymous OpenAlex provider compatibility for these eight one-request cases;
- complete request/result/cost accounting for this run;
- the pre-registered 6/8 mechanical accepted-case gate;
- write-once case journals and aggregate artifact integrity;
- continued production and report-workflow disconnection.

Not yet evaluated:

- whether any of the 13 accepted candidates is directly relevant;
- whether a relevant candidate adds evidence absent from the frozen baseline;
- the frozen 5% maximum wrong-source rate;
- whether at least 6/8 cases contain novel relevant evidence;
- planner-trigger precision, report improvement, source truth, adoption or ROI.

A provenance-locked Schema v2 packet has now been generated for all 13
candidates, and its blank preflight correctly reports
`incomplete / not_evaluated`. The next admissible step is one eligible human
return using that exact packet. Profiles, queries, cases, labels, thresholds
and provider responses may not be changed or rerun after this observation.

