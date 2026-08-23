# Pre-registration: checkpoint fault-recovery audit

**Registered:** 2026-08-23, before running the 30-unit audit  
**Code baseline:** `52fa4af8783431ef1e331395b5d50cb38ad6c69e`  
**Study type:** zero-network, zero-model-cost process fault injection  
**Status:** pre-registered; results must be reported separately

## Question

When a worker process is terminated immediately after a validated node has
published its checkpoint manifest, can a fresh worker resume from an immutable
child-owned snapshot without repeating any already committed LLM-stage work?

This audit is about the runtime boundary, not report quality. It uses the real
`pipeline_worker.main` path, the production checkpoint identity/inspection
code, status persistence, CrewAI hydration seam, and final artifact path. A
deterministic provider double supplies outputs so the experiment cannot spend
tokens or silently reach a network service.

## Measurement before implementation

`outputs/benchmark/` contains 30 complete historical runs. None contains a
`checkpoints/*/manifest.json`, because all 30 predate the checkpoint feature.
They therefore provide frozen real `SourceCollection` inputs but cannot supply
a retrospective recovery rate. Any recovery percentage must come from the
prospective units below; the absence of old manifests is not counted as a pass
or a failure.

## Frozen inputs

The audit selects the ten canonical benchmark directories: names beginning
with two digits and excluding the `__r2` and `__r3` repeats. The exact
`validated_sources.json` bytes are frozen here so a later local-file change is
reported as an input mismatch rather than silently changing the study.

| Fixture | SHA-256 |
|---|---|
| `01-car-t-cell-therapy-for-blood-cancers` | `e17a716a4a4d25a26e0292b9317b3c81db3a3c7c0b9d49a22806c48f56ce6a98` |
| `02-mrna-vaccines-for-cancer-immunotherapy` | `f3380e820d4eccb4a2761f9b203266fb5e965332860f3ae707c0bcf01ef563d1` |
| `03-solid-state-batteries-for-electric-vehicles` | `6ff31da36946834ac69d1151eb54845f770f0b8b5ac4820b15cc0a397ca8558f` |
| `04-perovskite-solar-cells-for-utility-scale-powe` | `58b39151921a8a9ec5446c908d028b8b030f79b3b7da1d737853a3099b3abdf0` |
| `05-crispr-gene-editing-for-genetic-diseases` | `a0bd1aefe3e91d171cacc6252cf2a3a6d9f096485c88f30ce519fc4447a83a18` |
| `06-carbon-capture-and-storage-for-industrial-emi` | `6f541afb495a4657f73c3aa8566afb135c5cc59df1e9f0fd96c5819de7e8185a` |
| `07-cultivated-meat-for-food-industry` | `bd7b7086c71bea82384167ce872172ac5697f12aa74bc705d08a9e8bbb48237c` |
| `08-quantum-computing-for-drug-discovery` | `efc02a138bc6e7201cb2430bb5547d266fcbd43fdd19aaab1a5a953d980acb66` |
| `09-graphene-based-flexible-electronics` | `0929309d40c3e957274facaaa7c85744a5f3393898748ebf1f6b5f679f40999d` |
| `10-room-temperature-ambient-pressure-superconduc` | `a6b0486565c3fddcc672028ddbd2e1eb6878b02d453223a39993665c47b94b96` |

If any fixture is absent or has a different digest, execution must stop before
creating study units. It must not replace the fixture with another run.

## Frozen fault matrix

Each fixture is run once at each boundary, for 30 units total:

| Scenario | Parent is terminated after | Expected task prefix reused by child | Expected task suffix executed by child |
|---|---|---|---|
| `after_academic` | `academic` manifest is durable | `academic` | `patent` through `scorer` |
| `after_market` | `market` manifest is durable | `academic`, `patent`, `market` | `writer` through `scorer` |
| `after_reviewer` | `reviewer` manifest is durable | `academic` through `reviewer` | `scorer` |

The provider double executes the evidence nodes in logical checkpoint order.
This makes the injected prefix deterministic; it does not measure CrewAI's
parallel scheduling latency or production provider timing.

## Injection and recovery protocol

1. Start the real pipeline worker in a separate OS process with the frozen
   `SourceCollection` and a deterministic six-task Crew double.
2. The double records a node execution before invoking its normal task
   callback. After the selected callback has returned, it publishes a sentinel
   and waits. The controller verifies the selected manifest exists and then
   terminates the process. A cooperative Python exception is not sufficient.
3. Copy the parent's checkpoint tree and RunSpec into the child's private
   `.resume-source/` snapshot.
4. Rename the parent directory out of the run-id path before starting the
   child. This makes an accidental fallback to the parent path fail while
   preserving the parent bytes for an immutability comparison.
5. Start a fresh worker process. It must hydrate the contiguous prefix, execute
   only the suffix, and finish through the same status/artifact path as a normal
   run.
6. Recompute every assertion from persisted unit evidence. A stored `passed`
   field is never trusted as the result.

## Pre-registered pass criteria

The study passes only if **all 30 units** satisfy every condition below:

1. The fault sentinel was observed, the target manifest existed before
   termination, and the parent process did not exit successfully.
2. The child process exited zero and `status.json` says `stage=Done` and
   `done=true`.
3. `recovery.state` is `reused`; `reused_nodes` is exactly `retrieval` plus the
   expected task prefix; and `next_node` is the first expected suffix node.
4. The child's execution log is exactly the expected suffix. The intersection
   of parent and child task execution logs is empty.
5. `checkpointing.state` is `complete`, all seven nodes are committed, and no
   checkpoint error is present.
6. The original parent run-id path is absent during child execution, while the
   detached parent tree's content hash is unchanged after the child completes.
7. The child owns valid manifests for all seven nodes. Missing status,
   execution logs, manifests, or inspection fields make the unit fail; they do
   not mean “zero errors”.

The aggregate recovery success rate is `passing_units / 30`. The target is
30/30 (100%); there is no partial threshold. One failed or uninspectable unit
falsifies the claim that this frozen protocol recovered reliably.

## Negative control

The checker must reject an otherwise valid persisted unit after one seam value
is changed (for example, removing a reused node or reporting a child execution
of an already committed node). This control is run in the test suite and again
against a temporary copy of the completed audit. It prevents a checker that
merely trusts the producer's `passed` field.

## Claims this audit cannot support

Even a 30/30 result does **not** establish:

- exactly-once provider execution; a crash before manifest publication remains
  an at-least-once boundary;
- token, latency, or dollar savings under a real model;
- a production incident recovery rate or Railway restart SLO;
- report correctness, evidence truth, or an advantage of six agents;
- recovery from arbitrary non-contiguous checkpoints.

A single paid DeepSeek canary may be proposed only after this offline audit is
frozen and reviewed. It requires separate user authorization and a separate
soft spending limit. No paid call is authorized by this pre-registration.

## Commands

Plan only (default; creates no files):

```bash
uv run python checkpoint_fault_audit.py --fixtures-root outputs/benchmark
```

Execute the frozen offline matrix:

```bash
uv run python checkpoint_fault_audit.py --fixtures-root outputs/benchmark \
  --output-root outputs/checkpoint-fault-audit/20260823-offline-v1 --execute
```

Recheck persisted evidence without rerunning workers:

```bash
uv run python checkpoint_fault_audit.py \
  --check outputs/checkpoint-fault-audit/20260823-offline-v1
```
