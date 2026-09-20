# Wave 7D — Explicit Target Profile + Context Locality Gate

Date: 2026-09-20

## Goal

Turn modernization intent into explicit evidence, then determine whether a real semantic migration task actually requires long repository context before any model or expensive GPU is used.

## Target-defined case

Pinned repository:

- repository: h2oai/wave
- commit: fff04af6d92584d75ce7e946d2c449230461dfcb
- current UI react-dom: ^17.0.2
- current IDE react-dom: ^16.13.1
- explicit modernization target: react-dom=18

The explicit target turns four real ReactDOM.render call sites into legitimate React 18 migration tasks rather than treating React 16/17 code as defective by default.

## Corpus benchmark

Workflow run: 35485108170
Artifact: 10597288372

- repositories analyzed: 5 / 5
- source files: 1,040
- lines: 980,491
- semantic escalations: 4
- safety blockers: 3 across the full corpus
- h2oai/wave safety blockers: 0
- h2oai/wave eligible semantic tasks: 4
- B300 rental recommended: false

## Context Minimization Gate

The h2oai/wave repository contains 819,615 scanned lines, but the four evaluation tasks require only these deterministic context bundles:

| Target | Context characters | Band | Full repository required |
|---|---:|---|---|
| ide/src/index.tsx | 13,898 | small | false |
| ui/src/index.tsx | 21,314 | small | false |
| ui/src/markdown.tsx | 25,677 | small | false |
| ui/src/plot.tsx | 61,303 | small | false |

Maximum task context: 61,303 characters.
Full-repository-context tasks: 0 / 4.

The classifier therefore returns:

- tier: LOCAL_MODEL_EVALUATION_CANDIDATE
- B300 gate: ORDINARY_MODEL_BENCHMARK_FIRST
- B300 rental recommended: false

## Model evaluation harness

`modfactory eval-plan` now emits:

- plan.json
- tasks.jsonl
- plan.md

Each task contains the explicit target profile, target source, nearest manifest, nearby executable test sources, recipe, allowed changes, acceptance criteria, rollback triggers, baseline commands, and evaluation dimensions.

The harness never invokes a model and never executes or merges generated code.

## Decision

Ordinary model benchmark justified: **yes**
Long-context model benchmark justified: **no**
B300 benchmark justified: **no**
B300 rental recommended: **no**

No model inference was run in Wave 7D. The next evidence-producing step is to run the same four tasks through an ordinary model and measure patch correctness, scope compliance, test/build success, latency, and cost.

## Rule established

**current stack != intended target**

and

**large repository != large model context**

Only task-level evidence after target resolution and context minimization can justify escalation to long-context compute.
