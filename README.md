# Private Code Modernization Factory — MVP

Evidence-first repository modernization analysis, constrained patch proposal generation, differential before/after verification, and escalation control.

The tool does not grant an AI authority to rewrite, merge, or deploy a repository blindly. It first strengthens the evidence and target context, then decides whether deterministic automation, safety work, human review, or model evaluation is justified.

## Core pipeline

repo → snapshot → evidence refinement → target compatibility → blockers → architecture graph → baseline → recipe → migration slice → patch proposal → differential verification → scale/escalation benchmark → human review

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

## Compute gate

Repository size, legacy syntax, or an expensive-looking migration never justifies expensive compute by itself.

A model benchmark is allowed only after a genuine semantic candidate survives:
1. source-level evidence refinement;
2. usage evidence;
3. target-version / target-stack compatibility;
4. verification prerequisites.

A B300-class benchmark is allowed only if a smaller/ordinary model benchmark is insufficient and measured quality, latency, throughput, or total cost can plausibly improve.

Current decision: **NOT_JUSTIFIED_BY_CURRENT_EVIDENCE**.

## Reproducible corpora

- benchmarks/corpus.json — broad 10-repository Wave 7A/7B corpus.
- benchmarks/semantic-corpus.json — 5 repositories selected for real source-level legacy usage and target-context falsification.
- benchmarks/fetch_corpus.py — fetches exact pinned commits without executing target project code.
- .github/workflows/benchmark.yml — manual broad benchmark.
- .github/workflows/semantic-benchmark.yml — manual Wave 7C benchmark.

Artifacts are uploaded even when a corpus item fails, preserving diagnostic evidence.

## Escalation tiers

- NO_MODERNIZATION_SIGNAL — no compatibility or architecture migration slice detected.
- ARCHITECTURE_REVIEW — architecture pressure exists, but no semantic migration signal justifies model escalation.
- DETERMINISTIC — detected compatibility work is covered by deterministic transforms.
- SAFETY_FIRST — tests, CI, or test-command evidence must be repaired before model intelligence.
- SEMANTIC_REVIEW_CANDIDATE — a genuine semantic migration exceeds deterministic transforms after context gates.
- LONG_CONTEXT_EVALUATION_CANDIDATE — large repository scale coexists with genuine semantic migration work after context gates; this authorizes only a model benchmark, never automatic B300 rental.

## Current deterministic transforms

- distutils.core imports → setuptools
- simple collections ABC imports or attribute references → collections.abc

General imp → importlib remains blocked until its semantics can be encoded and verified without guessing. Other migrations escalate only when source, usage, target compatibility, and verification evidence support them.

## Safety boundaries

- target project code is never executed during analyze, propose, or benchmark;
- verify executes project tests only with explicit --allow-project-code;
- verification executes only in temporary copies;
- unsafe shell metacharacters are blocked;
- original repositories are never modified by verification;
- no ModFactory stage auto-merges or deploys.

## Architecture

- scanner.py — evidence-refined, target-aware repository modernization signals.
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
7C. ✅ Real Legacy Evidence Corpus + Target Compatibility Gate.
7D. Model/compute benchmark only when a genuine semantic candidate survives all current gates.

## Principle

**Generation is not evidence. Evidence is not authority. Legacy syntax is not a migration requirement. Scale is not proof that expensive compute is needed.**

Every escalation must earn its added complexity and cost with stronger evidence and measured improvement.
