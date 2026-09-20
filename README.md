# Private Code Modernization Factory — MVP

Evidence-first repository modernization analysis. The tool does **not** grant an AI authority to rewrite a repository blindly. It maps risk and architecture, discovers the repository's own verification commands, generates a non-executing baseline harness, attaches deterministic migration recipes where justified, then produces constrained migration slices with explicit verification and rollback gates.

## Core pipeline

repo → snapshot → blockers → architecture graph → command discovery → baseline harness → recipe match → safety gate → migration slices → verification evidence

## Current capabilities

- Detect languages and build/dependency manifests.
- Detect tests and GitHub Actions CI.
- Discover existing test/build/lint commands from CI, package scripts, Python layout, Make, Go, Cargo, Maven, and Gradle.
- Mark discovered repository commands as manual/sandbox-only; ModFactory never auto-executes them.
- Generate a baseline harness under the output directory, including static Python syntax validation without importing repository modules.
- Detect selected obsolete APIs and deprecated dependency patterns.
- Flag oversized source files that increase migration blast radius.
- Analyze Git history for high-churn/single-owner hotspots.
- Build internal Python and JavaScript/TypeScript dependency graphs.
- Detect dependency cycles and high fan-in/fan-out hubs.
- Attach migration recipes for known modernization patterns.
- Encode preconditions, allowed scope, verification, and rollback triggers.
- Convert architecture boundaries and recipes into constrained migration slices.
- Produce a 0–100 modernization risk score and BLOCK / REVIEW / PASS gate.
- Emit JSON and Markdown evidence.
- Zero runtime dependencies.

## Generated evidence bundle

Running an analysis writes:

- `report.json`
- `report.md`
- `harness/harness.json`
- `harness/baseline.sh`
- optional generated static-check helpers such as `harness/python_syntax_check.py`

The generated `baseline.sh` intentionally does **not** execute commands copied from the target repository. It only runs generated static checks. Discovered build/test commands are recorded for human review or later sandbox execution.

## Initial recipe catalog

- Python `imp` → `importlib`
- Python `distutils` → `setuptools`
- `collections` ABCs → `collections.abc`
- `node-sass` → Dart Sass
- npm `request` → maintained HTTP client
- `ReactDOM.render` → `createRoot`
- `javax` → Jakarta assessment recipe (advisory; explicitly blocks global replacement)

## Run

```bash
python -m pip install -e .
modfactory analyze /path/to/repository --output .modfactory
```

CI-style gate:

```bash
modfactory analyze . --output .modfactory --fail-on high
```

## Architecture

- `scanner.py` — repository inventory and modernization evidence.
- `history.py` — churn and ownership evidence.
- `architecture.py` — internal dependency graph, cycles, hubs and upgrade boundaries.
- `commands.py` — evidence-backed baseline command discovery.
- `harness.py` — non-executing baseline harness generation.
- `recipes.py` — deterministic migration recipe catalog.
- `models.py` — structured snapshot model.
- `planner.py` — staged modernization plan.
- `slices.py` — constrained migration slices and verification gates.
- `report.py` — JSON + Markdown evidence and harness artifacts.
- `cli.py` — CLI and CI exit codes.

## Engineering waves

1. ✅ Safety/risk scanner + Git history.
2. ✅ Dependency/architecture graph + upgrade-boundary discovery.
3. ✅ Migration Recipe Engine.
4. ✅ Baseline command discovery + test harness generation.
5. Patch generator constrained to one migration slice at a time.
6. Differential verification: before/after behavior, tests, performance and errors.
7. LLM/B300 layer for very large repositories and high-volume evaluation.

## Principle

**Access to code is not authority to merge. Generation is not evidence.**

Every automated change must earn approval by strengthening the evidence chain.
