# Private Code Modernization Factory — MVP

Evidence-first repository modernization analysis, constrained patch proposal generation, differential before/after verification, and escalation control.

The tool does not grant an AI authority to rewrite, merge, or deploy a repository blindly. It first strengthens the evidence itself, then decides whether deterministic automation, safety work, human review, or model evaluation is justified.

## Core pipeline

repo → snapshot → evidence refinement → blockers → architecture graph → baseline → recipe → migration slice → patch proposal → differential verification → scale/escalation benchmark → human review

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

The first reproducible corpus run on 2026-09-20 analyzed 10 pinned public repositories, 6,326 source files, and 2,195,930 lines. It initially reported 17 compatibility slices and 12 semantic escalations.

That result did not justify a B300 rental, but Wave 7B showed an even more important fact: many of those semantic signals were not genuine migration workloads.

## Wave 7B: Evidence Refinement Gate

Wave 7B refines evidence before any model call:

- Python legacy APIs are detected from AST imports/attributes instead of free-text matches.
- Documentation and comments mentioning distutils or imp do not become migration findings.
- npm deprecation findings come from direct package.json dependencies, not lockfile duplicates.
- Deprecated npm packages require observed import, require, dynamic import, or package-script usage before becoming semantic migration candidates.
- A direct deprecated dependency with no observed usage becomes dependency-hygiene work: verify removal, regenerate the lockfile, and run the baseline.
- javax detection is restricted to actual Java imports from known Jakarta-migration namespaces.
- Java SE namespaces, JCache, XML/config strings, documentation, and system-property text do not trigger Jakarta migration automatically.

The final Wave 7B run on the same exact 10-repository corpus produced:

- repositories analyzed: 10 / 10
- source files: 6,326
- lines: 2,195,930
- findings: 486
- compatibility slices: 3
- semantic escalations: 0
- safety blockers: 3
- architecture slices: 136
- LONG_CONTEXT_EVALUATION_CANDIDATE: 0
- B300 rental recommended: false

The semantic count therefore moved from 12 → 1 → 0 as evidence quality improved.

No model/compute benchmark is justified for this corpus because no genuine semantic candidate survives the Evidence Refinement Gate. Model evaluation is deferred until a future corpus produces a real semantic candidate that deterministic evidence cannot resolve.

## Compute gate

Repository size alone never justifies expensive compute.

A model benchmark is allowed only after a genuine semantic candidate survives evidence refinement. A B300-class benchmark is allowed only if a smaller/ordinary model benchmark is insufficient and the remaining workload is large enough that measured quality, latency, throughput, or total cost could improve materially.

Current decision: NOT_JUSTIFIED_BY_CURRENT_EVIDENCE.

## Reproducible public corpus

benchmarks/corpus.json pins 10 public repositories to exact commit SHAs across Python, JavaScript, and Java.

benchmarks/fetch_corpus.py fetches those commits without running project code. The manual GitHub Actions workflow .github/workflows/benchmark.yml runs static ModFactory logic and uploads benchmark evidence even when a corpus item fails, so partial failures remain diagnosable.

## Escalation tiers

- NO_MODERNIZATION_SIGNAL — no compatibility or architecture migration slice detected.
- ARCHITECTURE_REVIEW — architecture pressure exists, but no semantic migration signal justifies model escalation.
- DETERMINISTIC — detected compatibility work is covered by deterministic transforms.
- SAFETY_FIRST — tests, CI, or test-command evidence must be repaired before model intelligence.
- SEMANTIC_REVIEW_CANDIDATE — a genuine semantic migration exceeds deterministic transforms.
- LONG_CONTEXT_EVALUATION_CANDIDATE — large repository scale coexists with genuine semantic migration work; this authorizes only a model benchmark, never automatic B300 rental.

## Current deterministic transforms

- distutils.core imports → setuptools
- simple collections ABC imports or attribute references → collections.abc

General imp → importlib remains blocked until its semantics can be encoded and verified without guessing. Other migrations are escalated only when source-level evidence proves the relevant API/dependency is actually used.

## Safety boundaries

- target project code is never executed during analyze, propose, or benchmark;
- verify executes project tests only with explicit --allow-project-code;
- verification executes only in temporary copies;
- unsafe shell metacharacters are blocked;
- original repositories are never modified by verification;
- no ModFactory stage auto-merges or deploys.

## Architecture

- scanner.py — evidence-refined repository inventory and modernization signals.
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
7B. ✅ Evidence Refinement Gate.
7C. Model/compute benchmark only when a genuine semantic candidate survives 7B.

## Principle

**Generation is not evidence. Evidence is not authority. Scale is not proof that expensive compute is needed.**

Every escalation must earn its added complexity and cost with stronger evidence and measured improvement.
