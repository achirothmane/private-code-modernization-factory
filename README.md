# Private Code Modernization Factory — MVP

Evidence-first repository modernization analysis, constrained patch proposal generation, and differential before/after verification.

The tool does not grant an AI authority to rewrite, merge, or deploy a repository blindly. It maps risk and architecture, discovers verification commands, generates a non-executing baseline harness, attaches deterministic migration recipes, produces constrained migration slices, generates a review-only patch proposal, then verifies the proposed change inside temporary repository copies.

## Core pipeline

repo → snapshot → blockers → architecture graph → command discovery → baseline harness → recipe → migration slice → patch proposal → before/after verification → human review

## Current capabilities

- Detect languages and build/dependency manifests.
- Detect tests and GitHub Actions CI.
- Discover test/build/lint commands from CI, package scripts, Python layout, tox, Make, Go, Cargo, Maven, Gradle, and legacy setup.py.
- Generate a baseline harness without importing repository modules.
- Detect selected obsolete APIs and deprecated dependency patterns.
- Analyze Git history, dependency cycles, and dependency hubs.
- Attach migration recipes with preconditions, verification requirements, and rollback triggers.
- Generate one-slice deterministic patch proposals with file allowlists and diff budgets.
- Refuse unsupported, ambiguous, medium-confidence, or advisory transformations.
- Materialize proposed changes only inside temporary copies during verification.
- Compare before/after findings, risk score, source-file count, and dependency cycles.
- Require the targeted finding to disappear and block new findings.
- Keep project-code execution OFF by default.
- With explicit --allow-project-code, run discovered test commands in temporary before/after copies.
- Distinguish baseline failure from patch regression.
- Record test timing as observation only; performance timing is not yet a gate.
- Never modify the original repository, create commits, auto-merge, or deploy.

## Commands

Analyze:

~~~bash
modfactory analyze /path/to/repository --output .modfactory
~~~

Generate a review-only proposal:

~~~bash
modfactory propose /path/to/repository \
  --slice-id <slice-id> \
  --output .modfactory \
  --diff-budget 80
~~~

Run static differential verification without executing project code:

~~~bash
modfactory verify /path/to/repository \
  --slice-id <slice-id> \
  --output .modfactory
~~~

Inside a trusted environment, explicitly enable project tests:

~~~bash
modfactory verify /path/to/repository \
  --slice-id <slice-id> \
  --output .modfactory \
  --allow-project-code \
  --timeout 120
~~~

## Verification outcomes

- PASS — static differential gates pass and opted-in project tests pass before and after.
- REVIEW — static gates pass, but project code was not executed.
- FAIL — the patch introduces static evidence regression or breaks tests after a green baseline.
- BLOCKED — verification cannot fairly attribute an outcome, for example because the baseline already fails.

A PASS still requires human review. It is not merge or deployment authority.

## Generated evidence

Analysis:
- report.json
- report.md
- harness/harness.json
- harness/baseline.sh

Patch proposal:
- patch/proposal.json
- patch/change.diff

Differential verification:
- verification/verification.json
- verification/verification.md

## Current deterministic transforms

Wave 5/6 can currently propose and verify:

- distutils.core imports → setuptools
- simple collections ABC imports/attribute references → collections.abc

Semantic migrations such as general imp → importlib remain BLOCKED until a transform can be encoded and verified without semantic guessing.

## Safety boundaries for test execution

Discovered project commands are not executed by default. Even with --allow-project-code:

- execution happens only in temporary copies;
- shell metacharacters such as pipes, redirections, &&, command substitution, and semicolons are blocked;
- commands have a timeout;
- only discovered test commands are considered;
- original repository files are never modified.

For untrusted third-party repositories, run the opt-in test phase inside a dedicated sandbox/container with restricted credentials and network access.

## Architecture

- scanner.py — repository inventory and modernization evidence.
- history.py — churn and ownership evidence.
- architecture.py — dependency graph, cycles, hubs, upgrade boundaries.
- commands.py — evidence-backed command discovery.
- harness.py — non-executing baseline harness generation.
- recipes.py — migration recipe catalog.
- slices.py — constrained migration slices.
- patches.py — one-slice patch proposal engine.
- verification.py — temporary-copy differential verification and optional project tests.
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
7. LLM/B300 layer for very large repositories and high-volume evaluation.

## Principle

**Generation is not evidence. Evidence is not authority.**

A change can move toward approval only when its evidence becomes stronger, but merge and deployment remain separate human-controlled consequences.
