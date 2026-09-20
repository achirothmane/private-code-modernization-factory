# Wave 7F — First Real Semantic Survivor

Date: 2026-09-20

## Candidate

- repository: auth0/node-wsfed
- commit: 3bd751a1749d8746b981ce0e8daabe9eaec654b0
- deprecated dependency: request~2.88.2
- scope: test-suite modernization only
- runtime production usage claim: none

## Evidence

- 7 test files statically require request
- npm test exists
- GitHub Actions test workflow exists
- 25 test files detected
- 5 CI files detected
- 0 safety blockers
- recipe confidence: medium
- deterministic transform: intentionally unavailable

## Final benchmark result

- compatibility slices: 1
- deterministic proposals: 0
- semantic escalations: 1
- eligible model tasks: 1
- tier: LOCAL_MODEL_EVALUATION_CANDIDATE
- next compute gate: RUN_ORDINARY_MODEL_BENCHMARK
- B300 rental recommended: false

## Context bundle

The final task bundle contains package.json plus all seven observed request usage sites.

Context characters: 38,731
Context band: small
Full repository required: false

Allowed changes are exact paths, not a generic "directly related tests" permission.

## Inference status

No model inference was run.

The current connected tool environment does not expose a generic measured inference endpoint that returns a comparable model identity, latency, token usage, and cost for this task. Wave 7F does not fabricate those metrics.

## Decision

A real ordinary-model benchmark is now justified for this task.

Long-context benchmark: not justified.
B300 benchmark/rental: not justified.

Next: build a provider-neutral runner/scorer and execute the task only when a measured inference provider is available.
