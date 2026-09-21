# Wave 7H — First Measured Ordinary-Model Benchmarks

Date span: 2026-09-20 to 2026-09-21

## Benchmark identity

- benchmark ID: 126397b865a6199a
- task ID: model-d866304f07
- repository: auth0/node-wsfed
- commit: 3bd751a1749d8746b981ce0e8daabe9eaec654b0
- migration: request~2.88.2 test-suite modernization
- context files: 8
- observed request usage sites: 7
- input tokens: 13,184
- full repository required: false

## Invalidated provider path

A first attempt used GitHub Models because the repository GITHUB_TOKEN exposed Models: read. The live endpoint returned HTTP 410 with code github_models_retirement_brownout. That provider path was removed from ModFactory rather than retained as dead integration code.

This attempt produced no model response and is not counted as a model-quality benchmark.

## Measured run A — Qwen2.5-Coder 3B Instruct Q4_K_M

- workflow run: 35488493217
- artifact: 10598850015
- llama.cpp: b11057
- GGUF SHA-256: 724fb256bec1ff062b2f65e4569e871ad2e95ab2a3989723d1769c54294730b7
- quantization: Q4_K Medium
- model parameters reported by llama.cpp: 3,397,103,616
- model bytes: 2,098,976,768
- context configured: 24,576
- input tokens: 13,184
- output tokens: 805
- wall-clock latency: 857,983.985 ms
- prompt eval: 710,316.81 ms, 18.56 tok/s
- generation eval: 147,616.77 ms, 5.45 tok/s
- cost_usd: null
- project code executed: false

Scorer result: **FAIL — patch-does-not-apply-cleanly**

The generated diff changed only package.json although the rationale claimed the seven request usage sites were migrated. The patch failed git apply validation before semantic rescanning or tests.

## Measured run B — Qwen2.5-Coder 7B Instruct Q4_K_M

- workflow run: 35598656962
- artifact: 10638450540
- llama.cpp: b11057
- GGUF SHA-256: 509287f78cb4d4cf6b3843734733b914b2c158e43e22a7f4bf5e963800894d3c
- quantization: Q4_K Medium
- model parameters reported by llama.cpp: 7,615,616,512
- model bytes: 4,677,120,000
- context configured: 20,480
- input tokens: 13,184
- output tokens: 98
- wall-clock latency: 571,535.098 ms
- prompt eval: 546,679.28 ms, 24.12 tok/s
- generation eval: 24,823.59 ms, 3.91 tok/s
- cost_usd: null
- project code executed: false

Scorer result: **FAIL — unified-diff-invalid**

The generated output was only a hunk replacing request with axios. It contained no file headers and therefore could not identify a changed file or be treated as a valid unified diff.

## Comparison

Both models received the same evidence bundle and all seven usage sites.

The 7B run had lower wall time only because it emitted 98 tokens instead of 805. Generation throughput was lower per token than the 3B run.

Increasing model size from approximately 3.4B to 7.6B parameters did not move the task through the first patch-validity gate.

## Decision

Ordinary-model inference has now been measured.

Long-context benchmark justified: **no**
B300 benchmark justified: **no**
B300 rental justified: **no**

The observed failure mode is patch protocol/completeness, not missing repository context.

Next gate: **DECOMPOSE_BEFORE_SCALE**

Split the eight-file migration into file-scoped tasks, score each generated patch independently, and aggregate only validated patches before trying a stronger remote model or larger compute.

## Important cost note

No provider API charge was incurred or measured. The benchmark intentionally records cost_usd as null because GitHub Actions compute consumption was not converted into a dollar cost.
