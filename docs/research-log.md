# Research log

This document preserves the engineering/research history that previously occupied the project homepage.

The product-facing README is intentionally shorter: **problem → 60-second quickstart → decisions → guarantees/limits → evidence**.

---

# Private Code Modernization Factory — MVP

Evidence-first repository modernization analysis, constrained patch proposal generation, differential before/after verification, and escalation control.

The tool does not grant an AI authority to rewrite, merge, or deploy a repository blindly. It first strengthens the evidence and target context, then decides whether deterministic automation, safety work, human review, or model evaluation is justified.

## Core pipeline

repo → explicit target profile → snapshot → evidence refinement → target compatibility → blockers → architecture graph → baseline → recipe → migration slice → patch proposal → differential verification → context minimization → model-evaluation plan → provider-neutral model request → response scoring → human review

## Commands

Analyze one repository:

~~~bash
modfactory analyze /path/to/repository --output .modfactory
~~~

Generate one review-only proposal:

~~~bash
modfactory propose /path/to/repository \
  --slice-id <slice-id> \
  --output .modfactory \
  --diff-budget 80
~~~

Run static differential verification:

~~~bash
modfactory verify /path/to/repository \
  --slice-id <slice-id> \
  --output .modfactory
~~~

Explicitly enable project tests only inside a trusted environment:

~~~bash
modfactory verify /path/to/repository \
  --slice-id <slice-id> \
  --output .modfactory \
  --allow-project-code \
  --timeout 120
~~~

Benchmark a local corpus without executing target project code:

~~~bash
modfactory benchmark /path/to/corpus \
  --manifest benchmarks/corpus.json \
  --output benchmark-results
~~~

Declare the intended modernization destination explicitly:

~~~bash
modfactory analyze /path/to/repository \
  --target react-dom=18 \
  --target python=3.12 \
  --output .modfactory
~~~

Build a context-minimized model evaluation dataset without invoking a model:

~~~bash
modfactory eval-plan /path/to/repository \
  --target react-dom=18 \
  --output model-eval-results
~~~

Build a provider-neutral request artifact for one eligible semantic task:

~~~bash
modfactory model-request model-eval-results/model-eval/plan.json \
  --task-id <task-id> \
  --provider <provider-id> \
  --model <model-id> \
  --output model-benchmark
~~~

Score a provider response without executing project code:

~~~bash
modfactory model-score /path/to/repository \
  --request model-benchmark/model-bench/request.json \
  --response provider-response.json \
  --output model-benchmark
~~~

Project tests remain explicit opt-in:

~~~bash
modfactory model-score /path/to/repository \
  --request model-benchmark/model-bench/request.json \
  --response provider-response.json \
  --output model-benchmark \
  --allow-project-code \
  --timeout 120
~~~

Supported explicit targets currently include `react-dom`, `spring-boot`, and `python`. Corpus manifests can also define a different `targets` object per repository.

## Wave 7A: Scale & Escalation Benchmark

The first reproducible corpus run on 2026-09-20 analyzed 10 pinned public repositories, 6,326 source files, and 2,195,930 lines. It initially reported 17 compatibility slices and 12 semantic escalations.

That result did not justify a B300 rental. Wave 7B then showed that many apparent semantic signals were evidence-quality problems.

## Wave 7B: Evidence Refinement Gate

Wave 7B refines evidence before any model call:

- Python legacy APIs are detected from AST imports/attributes instead of free-text matches.
- Documentation and comments mentioning distutils or imp do not become migration findings.
- npm deprecation findings come from direct package.json dependencies, not lockfile duplicates.
- Deprecated npm packages require observed import, require, dynamic import, or package-script usage before becoming semantic migration candidates.
- A direct deprecated dependency with no observed usage becomes dependency-hygiene work.
- javax detection is restricted to actual Java imports from known Jakarta-migration namespaces.
- Java SE namespaces, JCache, XML/config strings, documentation, and system-property text do not trigger Jakarta migration automatically.

The same 10-repository corpus moved from 12 → 1 → 0 semantic escalations. Final Wave 7B: 3 compatibility slices, 3 safety blockers, 136 architecture slices, 0 long-context candidates.

## Wave 7C: Real Legacy Evidence + Target Compatibility Gate

Wave 7C deliberately searched a separate corpus of public repositories containing real source-level legacy API usage:

- h2oai/wave — ReactDOM.render in TypeScript/React source.
- StackStorm/st2web — ReactDOM.render in application source.
- picturepan2/devices.css — direct node-sass dependency plus require usage.
- sbstjn/timesheet.js — direct node-sass dependency plus runtime usage.
- prezi/changelog — import imp plus imp.load_source.

The first run produced 4 semantic escalations, all inside h2oai/wave, making it appear to be a LONG_CONTEXT_EVALUATION_CANDIDATE.

Target context falsified that conclusion: the relevant h2oai/wave packages declare react-dom 17 and 16. ReactDOM.render is expected for those versions; createRoot becomes relevant when React 18+ is the current or target stack. Wave 7C therefore added a Target Compatibility Gate that resolves the nearest package.json and only treats ReactDOM.render as a migration signal when react-dom is 18+.

Final Wave 7C on the same 5 repositories:

- repositories analyzed: 5 / 5
- source files: 1,040
- lines: 980,491
- findings: 34
- compatibility slices: 3
- semantic escalations: 0
- safety blockers: 3
- architecture slices: 45
- LONG_CONTEXT_EVALUATION_CANDIDATE: 0
- B300 rental recommended: false

The apparent semantic count moved **4 → 0** after target compatibility was added.

The three remaining compatibility cases are real node-sass/imp evidence, but they are blocked by missing verification prerequisites rather than semantic ambiguity. The correct next step for those cases is baseline/test/CI enablement, not an LLM.

## Wave 7D: Explicit Target Profile + Context Locality Gate

Wave 7D fixes a deeper ambiguity: the current dependency version is not the same thing as the client's intended modernization destination.

For example, `ReactDOM.render` is valid evidence in a React 17 repository but is not a required migration until the intended target is React 18+. The same principle applies to Python runtime removals and Spring Boot 3 / Jakarta transitions.

Wave 7D adds explicit target profiles to analyze, propose, verify, benchmark, and eval-plan. The 5-repository semantic corpus now declares `{"react-dom": "18"}` for the pinned h2oai/wave commit.

That target-defined run produced a genuine semantic workload:

- repositories analyzed: 5 / 5
- source files: 1,040
- lines: 980,491
- h2oai/wave semantic escalations: 4
- h2oai/wave safety blockers: 0
- eligible model-evaluation tasks: 4
- B300 rental recommended: false

The first classifier called h2oai/wave a long-context candidate because the repository contains 819,615 scanned lines. The Context Minimization Gate then constructed task-specific evidence bundles:

- `ide/src/index.tsx`: 13,898 characters
- `ui/src/index.tsx`: 21,314 characters
- `ui/src/markdown.tsx`: 25,677 characters
- `ui/src/plot.tsx`: 61,303 characters

All four bundles are classified `small`; none requires full-repository context. The final tier is therefore **LOCAL_MODEL_EVALUATION_CANDIDATE**, with the next gate **ORDINARY_MODEL_BENCHMARK_FIRST**.

This falsifies the stronger compute claim:

**large repository != large task context != B300 requirement**

No model was invoked in Wave 7D. The next wave must compare ordinary-model outputs on the exact same four tasks before any long-context or B300-class experiment is considered.

## Wave 7E: Deterministic Falsification Before Model Inference

Wave 7E began with the plan to benchmark an ordinary model on the four React 18 migration tasks from Wave 7D. Before spending inference, the same tasks were tested against a narrower hypothesis: can their semantics be encoded deterministically without guessing?

The answer for this pinned case is yes.

A constrained `reactdom-render-to-createroot` transform now supports only three root-lifetime patterns:

- `document.getElementById(...)` entry roots;
- one-shot containers produced by `appendChild(...)`;
- reusable named containers created with `document.createElement(...)`, where exactly one persistent React root is retained.

Any other container-lifetime shape remains blocked instead of being rewritten speculatively.

Real benchmark on `h2oai/wave@fff04af6d92584d75ce7e946d2c449230461dfcb` with explicit target `react-dom=18`:

- React compatibility slices: 4
- deterministic patch proposals: 4 / 4
- static differential verification passes: 4 / 4
- target migration findings removed: 4 / 4
- new findings after verification: 0
- semantic escalations: 0
- eligible model-evaluation tasks: 0
- model inference run: false
- project code executed: false
- final tier: **DETERMINISTIC**
- B300 rental recommended: false

Changed-line counts were 9, 4, 4, and 6 for the four real files.

This falsified the Wave 7D next-step hypothesis before inference:

**a task that survives evidence/target/context gates can still become deterministic after its semantic shape is understood.**

The ordinary-model benchmark is therefore not justified for these four React tasks. A model benchmark should be opened only when a future real case still has eligible semantic tasks after deterministic-transform discovery.

## Wave 7F: First Real Semantic Survivor

Wave 7F searched for a real migration that still survives evidence quality, target compatibility, safety prerequisites, deterministic-transform discovery, and context minimization.

Pinned candidate:

- repository: `auth0/node-wsfed`
- commit: `3bd751a1749d8746b981ce0e8daabe9eaec654b0`
- migration: deprecated `request@~2.88.2`
- scope: **test-suite modernization**, not production runtime code
- observed usage sites: 7 test files
- baseline command: `npm test`
- GitHub Actions CI: present

Measured result:

- repositories analyzed: 1 / 1
- source files: 22
- test files: 25
- CI files: 5
- compatibility slices: 1
- deterministic proposals: 0
- semantic escalations: 1
- safety blockers: 0
- eligible model-evaluation tasks: 1
- escalation tier: **LOCAL_MODEL_EVALUATION_CANDIDATE**
- B300 rental recommended: false

The original model-evaluation bundle only included three nearby tests. Wave 7F strengthened this gate: npm semantic tasks now enumerate every observed static import/require usage site and convert the allowed-change scope into exact paths.

For this candidate the final bundle contains:

- `package.json`
- `test/federationServerService.tests.js`
- `test/jwt.tests.js`
- `test/metadata.tests.js`
- `test/wsfed-encryption.tests.js`
- `test/wsfed-sha1.tests.js`
- `test/wsfed.custom_form.tests.js`
- `test/wsfed.tests.js`

Total context: **38,731 characters**, classified `small`; full-repository context required: false.

No model inference was run in Wave 7F. This environment does not currently expose a generic measured inference channel that can return a comparable model identity, latency, token usage, and cost for this benchmark, so those metrics were not invented.

Wave 7F therefore establishes the first benchmark-ready semantic survivor. The next engineering step is an ordinary-model runner/scorer that consumes this exact task bundle and records patch correctness, scope compliance, tests, latency, tokens, and cost when a measured inference provider is available.

## Wave 7G: Provider-Neutral Model Runner + Scorer

Wave 7G builds the benchmark machinery required by the Wave 7F semantic survivor without binding ModFactory to one inference vendor.

The benchmark is split into three independent layers:

1. **Request contract** — freezes the exact semantic task, provider/model identity, context files, allowlist, and response schema.
2. **Provider adapter runner** — any future provider adapter implements one `invoke(request)` method. The runner measures wall-clock latency and accepts token/cost metrics only when the provider returns them.
3. **Response scorer** — validates the response envelope, verifies repository baseline hashes, rejects unsafe/out-of-scope diffs, applies the patch only inside a temporary copy, re-runs static analysis, and optionally runs project tests when explicitly enabled.

Safety and reproducibility gates added in Wave 7G:

- every context file now carries a SHA-256 hash of its full source;
- the complete task is hashed into `task_sha256`;
- `benchmark_id` is deterministically derived from that task hash;
- changed repository context after request creation blocks scoring;
- task tampering after request creation blocks scoring;
- file creation/deletion, rename/copy operations, binary patches, path traversal, and changes outside the explicit allowlist are blocked;
- multi-file unified diffs are normalized for reproducible `git apply`;
- the original repository is never modified;
- unknown latency/token/cost metrics remain null rather than being estimated.

A real contract run was generated against the Wave 7F Auth0 survivor:

- workflow run: `35487640138`
- artifact: `10598316289`
- benchmark ID: `126397b865a6199a`
- task ID: `model-d866304f07`
- context files: 8
- request usage sites: 7
- allowed-change paths: 8
- context characters: 38,731
- context band: small
- provider invoked: false

The in-process provider-neutral runner is covered by a fake adapter test that proves latency measurement plus provider-supplied input tokens, output tokens, and cost are preserved in the canonical response envelope. No real inference was performed.

Wave 7G therefore closes the **measurement infrastructure** gap. It does **not** claim a model quality result yet.

## Wave 7H: First Measured Ordinary-Model Benchmarks

Wave 7H executed real local inference on the exact Wave 7F/7G benchmark `126397b865a6199a` instead of inferring model capability from repository size.

The task remained unchanged:

- repository: `auth0/node-wsfed@3bd751a1749d8746b981ce0e8daabe9eaec654b0`
- migration: deprecated `request~2.88.2` in seven test-suite usage sites
- context files: 8
- prompt context: 13,184 provider-reported input tokens
- context band: small
- full-repository context required: false
- project code executed: false

Two pinned local Qwen2.5-Coder baselines were run through `llama.cpp b11057` on GitHub Actions CPU:

| Model | GGUF SHA-256 | Input tokens | Output tokens | Wall latency | Prompt throughput | Generation throughput | Score |
|---|---|---:|---:|---:|---:|---:|---|
| Qwen2.5-Coder 3B Instruct Q4_K_M | `724fb256bec1ff062b2f65e4569e871ad2e95ab2a3989723d1769c54294730b7` | 13,184 | 805 | 857,983.985 ms | 18.56 tok/s | 5.45 tok/s | FAIL — patch did not apply cleanly |
| Qwen2.5-Coder 7B Instruct Q4_K_M | `509287f78cb4d4cf6b3843734733b914b2c158e43e22a7f4bf5e963800894d3c` | 13,184 | 98 | 571,535.098 ms | 24.12 tok/s | 3.91 tok/s | FAIL — invalid unified diff |

The lower total latency of the 7B run is not a speed win: it stopped after only 98 output tokens. Its per-token generation throughput was lower than the 3B run.

### 3B failure

The 3B model returned a diff touching only `package.json`. Its rationale claimed the usage sites had been migrated, but the diff contained no test-file changes. The scorer accepted the response envelope, diff structure, and allowlist scope, then rejected the patch at `git apply --check` with `patch-does-not-apply-cleanly`.

### 7B failure

The 7B model returned only a hunk changing `request` to `axios`, without file headers. The scorer rejected it immediately as `unified-diff-invalid`.

Neither model reached semantic before/after verification or project tests.

### Compute conclusion

These failures do **not** justify long-context or B300-class compute:

- task context is already small;
- both models saw all seven usage sites;
- failure occurred at patch protocol/completeness before semantic verification;
- increasing parameters from ~3.4B to ~7.6B did not produce a valid patch.

The next gate is therefore **DECOMPOSE_BEFORE_SCALE**: split one eight-file semantic migration into smaller file-scoped patch tasks, aggregate only validated partial patches, and re-run the same evidence gates before considering a stronger remote model or larger hardware.

No API model charges were measured. `cost_usd` remains null because local inference used GitHub Actions compute whose monetary cost was not attributed by the benchmark.

## Compute gate

Repository size, legacy syntax, or an expensive-looking migration never justifies expensive compute by itself.

A model benchmark is allowed only after a genuine semantic candidate survives:
1. source-level evidence refinement;
2. usage evidence;
3. explicit or inferred target-version / target-stack compatibility;
4. verification prerequisites;
5. deterministic-transform discovery;
6. context minimization.

A long-context benchmark additionally requires task-level evidence that the minimized context is still large. A B300-class benchmark is allowed only if a smaller/ordinary model benchmark is insufficient and measured quality, latency, throughput, or total cost can plausibly improve.

Wave 7H measured two local ordinary models. Both failed before semantic verification while task context remained small. The current post-benchmark gate is **DECOMPOSE_BEFORE_SCALE**.

Current B300 decision: **NOT_JUSTIFIED_BY_CURRENT_EVIDENCE**.

## Reproducible corpora

- benchmarks/corpus.json — broad 10-repository Wave 7A/7B corpus.
- benchmarks/semantic-corpus.json — 5 repositories selected for real source-level legacy usage; Wave 7D also carries per-repository explicit modernization targets.
- benchmarks/wave7f-corpus.json — isolated pinned semantic-survivor corpus for Auth0 node-wsfed.
- benchmarks/fetch_corpus.py — fetches exact pinned commits without executing target project code.
- .github/workflows/benchmark.yml — manual broad benchmark.
- .github/workflows/semantic-benchmark.yml — manual Wave 7C–7E target-aware benchmark, deterministic proposal evidence, and model-evaluation-plan artifact.
- .github/workflows/wave7f-semantic-survivor.yml — manual first-survivor benchmark.
- .github/workflows/wave7g-runner-contract.yml — manual provider-neutral request-contract validation.
- .github/workflows/wave7h-local-ordinary-model.yml — manual pinned 3B local-model benchmark.
- .github/workflows/wave7h-local-7b-model.yml — manual pinned 7B local-model comparison.

Artifacts are uploaded even when a corpus item fails, preserving diagnostic evidence.

## Escalation tiers

- NO_MODERNIZATION_SIGNAL — no compatibility or architecture migration slice detected.
- ARCHITECTURE_REVIEW — architecture pressure exists, but no semantic migration signal justifies model escalation.
- DETERMINISTIC — detected compatibility work is covered by deterministic transforms.
- SAFETY_FIRST — tests, CI, or test-command evidence must be repaired before model intelligence.
- SEMANTIC_REVIEW_CANDIDATE — semantic work exists but is not yet eligible for model evaluation.
- LOCAL_MODEL_EVALUATION_CANDIDATE — semantic work survives all gates and deterministic context minimization keeps the model task local; benchmark an ordinary model first.
- LONG_CONTEXT_EVALUATION_CANDIDATE — at least one eligible semantic task remains large after context minimization; this authorizes only a long-context model benchmark, never automatic B300 rental.

## Current deterministic transforms

- distutils.core imports → setuptools
- simple collections ABC imports or attribute references → collections.abc
- React 18 target: supported `ReactDOM.render` shapes → `createRoot(...).render(...)`, with root lifetime preserved for supported one-shot and reusable-container patterns

General imp → importlib remains blocked until its semantics can be encoded and verified without guessing. Unsupported React root-lifetime shapes are also blocked rather than guessed. Other migrations escalate only when source, usage, target compatibility, deterministic-transform discovery, and verification evidence support them.

## Safety boundaries

- target project code is never executed during analyze, propose, or benchmark;
- verify executes project tests only with explicit --allow-project-code;
- verification executes only in temporary copies;
- unsafe shell metacharacters are blocked;
- original repositories are never modified by verification;
- no ModFactory stage auto-merges or deploys.

## Architecture

- scanner.py — evidence-refined, target-aware repository modernization signals.
- targets.py — explicit modernization target parsing and per-repository target overrides.
- history.py — churn and ownership evidence.
- architecture.py — dependency graph, cycles, hubs, upgrade boundaries.
- commands.py — evidence-backed command discovery.
- harness.py — non-executing baseline harness generation.
- recipes.py — migration recipe catalog.
- slices.py — constrained migration slices.
- patches.py — one-slice patch proposal engine.
- verification.py — temporary-copy differential verification.
- benchmark.py — corpus scale, deterministic coverage, context-locality, and escalation measurement.
- model_eval.py — context-minimized, non-executing model evaluation task generation with full-file context hashes.
- model_bench.py — provider-neutral request contract, adapter runner, safe patch scoring, latency/token/cost recording, and baseline identity gates.
- models.py — structured evidence models.
- planner.py — staged modernization plan.
- report.py — evidence reports.
- cli.py — CLI.

## Engineering waves

1. ✅ Safety/risk scanner + Git history.
2. ✅ Dependency/architecture graph + upgrade-boundary discovery.
3. ✅ Migration Recipe Engine.
4. ✅ Baseline command discovery + test harness generation.
5. ✅ Constrained one-slice Patch Proposal Engine.
6. ✅ Differential Verification Engine.
7A. ✅ Scale & Escalation Benchmark.
7B. ✅ Evidence Refinement Gate.
7C. ✅ Real Legacy Evidence Corpus + Target Compatibility Gate.
7D. ✅ Explicit Target Profile + Model Evaluation Harness + Context Locality Gate.
7E. ✅ Deterministic Falsification Before Model Inference — 4/4 real React 18 tasks converted to verified deterministic proposals; model benchmark cancelled for this case.
7F. ✅ First Real Semantic Survivor — Auth0 node-wsfed test-suite request migration survives all current gates; exact 8-file bundle, 38,731 characters, model benchmark justified but not yet executed.
7G. ✅ Provider-Neutral Model Runner + Scorer — exact task/request hashing, repository baseline identity, safe diff application, provider adapter contract, latency/token/cost envelope, and real Auth0 request artifact.
7H. ✅ First Measured Ordinary-Model Benchmarks — pinned 3B and 7B Qwen2.5-Coder local inference on `126397b865a6199a`; both failed patch protocol/completeness gates, so long-context/B300 escalation remains closed.
7I. Usage-Site Decomposition — split multi-file semantic migrations into file-scoped model tasks, validate each partial patch independently, then aggregate before any stronger-model escalation.

## Principle

**Generation is not evidence. Evidence is not authority. Legacy syntax is not a migration requirement. A semantic-looking task is not automatically a model task. Repository size is not task-context size. Scale is not proof that expensive compute is needed.**

Every escalation must earn its added complexity and cost with stronger evidence and measured improvement.

