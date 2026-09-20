# Private Code Modernization Factory — MVP

Evidence-first repository modernization analysis, constrained patch proposal generation, differential before/after verification, and scale/escalation measurement.

The tool does not grant an AI authority to rewrite, merge, or deploy a repository blindly. It measures where deterministic automation works, where verification prerequisites are missing, and where semantic or long-context evaluation may be justified.

## Core pipeline

repo → snapshot → blockers → architecture graph → baseline → recipe → migration slice → patch proposal → differential verification → scale/escalation benchmark → human review

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

## Wave 7A: Scale & Escalation Benchmark

Wave 7A measures repository size, analysis time, findings, recipes, migration slices, deterministic proposal coverage, blocked reasons, safety blockers, semantic escalations, architecture pressure, and long-context evaluation candidates.

The workload bands are screening heuristics, not hardware requirements. LONG_CONTEXT_EVALUATION_CANDIDATE does not mean a B300 is required.

The benchmark deliberately reports b300_rental_recommended = false and b300_decision = NOT_JUSTIFIED_BY_WAVE_7A. A B300-class rental can only be considered after a separate model benchmark measures quality, latency, throughput, and total cost against smaller hardware or cloud alternatives.

## Reproducible public corpus

benchmarks/corpus.json pins 10 public repositories to exact commit SHAs across Python, JavaScript, and Java, from very small legacy codebases to large actively maintained projects.

benchmarks/fetch_corpus.py fetches those exact commits without running project code. The manual GitHub Actions workflow .github/workflows/benchmark.yml fetches the corpus, runs only static ModFactory logic, and uploads benchmark.json plus benchmark.md.

## Escalation tiers

- NO_MODERNIZATION_SIGNAL — no compatibility or architecture migration slice detected.
- DETERMINISTIC — detected compatibility work is covered by deterministic transforms.
- SAFETY_FIRST — tests, CI, or test-command evidence must be repaired before adding model intelligence.
- SEMANTIC_REVIEW_CANDIDATE — migration semantics exceed deterministic transforms.
- LONG_CONTEXT_EVALUATION_CANDIDATE — large repository scale coexists with semantic or architecture migration work; this only authorizes a model benchmark, not expensive compute rental.

## Current deterministic transforms

- distutils.core imports → setuptools
- simple collections ABC imports or attribute references → collections.abc

General imp → importlib, node-sass → sass, HTTP-client replacement, React root migration, and Jakarta migration remain blocked or review-only until their semantics can be encoded and verified without guessing.

## Safety boundaries

- target project code is never executed during analyze, propose, or benchmark;
- verify executes project tests only with explicit --allow-project-code;
- verification executes only in temporary copies;
- unsafe shell metacharacters are blocked;
- original repositories are never modified by verification;
- no ModFactory stage auto-merges or deploys.

## Architecture

- scanner.py — repository inventory and modernization evidence.
- history.py — churn and ownership evidence.
- architecture.py — dependency graph, cycles, hubs, upgrade boundaries.
- commands.py — evidence-backed command discovery.
- harness.py — non-executing baseline harness generation.
- recipes.py — migration recipe catalog.
- slices.py — constrained migration slices.
- patches.py — one-slice patch proposal engine.
- verification.py — temporary-copy differential verification.
- benchmark.py — corpus scale, deterministic coverage, and escalation measurement.
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
7B. Model/compute benchmark only for cases that survive 7A.

## Principle

**Generation is not evidence. Evidence is not authority. Scale is not proof that expensive compute is needed.**

Every escalation must earn its added complexity and cost with measured improvement.
