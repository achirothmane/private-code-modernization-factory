# Private Code Modernization Factory — MVP

Evidence-first repository modernization analysis and constrained patch proposal generation. The tool does **not** grant an AI authority to rewrite or merge a repository blindly. It maps risk and architecture, discovers verification commands, generates a non-executing baseline harness, attaches deterministic migration recipes, produces constrained migration slices, and can generate a review-only diff for one supported slice at a time.

## Core pipeline

repo → snapshot → blockers → architecture graph → command discovery → baseline harness → recipe match → migration slice → constrained patch proposal → verification evidence

## Current capabilities

- Detect languages and build/dependency manifests.
- Detect tests and GitHub Actions CI.
- Discover existing test/build/lint commands from CI, package scripts, Python layout, tox, Make, Go, Cargo, Maven, Gradle, and legacy setup.py.
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
- Generate a patch proposal for exactly one migration slice at a time.
- Enforce an exact file allowlist and configurable diff budget.
- Generate patches only for deterministic high-confidence transforms; unsupported or ambiguous recipes are BLOCKED.
- Never apply the generated patch, create a commit, or auto-merge it.
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

A patch proposal writes:

- `patch/proposal.json`
- `patch/change.diff`

The generated `baseline.sh` intentionally does **not** execute commands copied from the target repository. Patch proposals likewise do **not** modify the repository.

## Initial recipe catalog

- Python `imp` → `importlib`
- Python `distutils` → `setuptools`
- `collections` ABCs → `collections.abc`
- `node-sass` → Dart Sass
- npm `request` → maintained HTTP client
- `ReactDOM.render` → `createRoot`
- `javax` → Jakarta assessment recipe

Wave 5 currently generates deterministic diffs for:

- `distutils.core` import → `setuptools`
- simple `collections` ABC imports/attribute references → `collections.abc`

Other recipes remain analysis-only until a transform can be encoded without semantic guessing.

## Run

```bash
python -m pip install -e .
modfactory analyze /path/to/repository --output .modfactory
```

Use a slice ID from `report.json` or `report.md` to request one proposal:

```bash
modfactory propose /path/to/repository \
  --slice-id <slice-id> \
  --output .modfactory \
  --diff-budget 80
```

CI-style risk gate:

```bash
modfactory analyze . --output .modfactory --fail-on high
```

## Patch proposal safety policy

A Wave 5 patch proposal must satisfy all of these conditions:

1. Exactly one migration slice is selected.
2. The slice is a compatibility slice with a recipe.
3. Recipe confidence is high.
4. A deterministic transform exists for that recipe.
5. The target resolves to a safe existing file inside the repository.
6. Changed files are a subset of the explicit allowlist.
7. Added + removed lines stay inside the diff budget.
8. Python output parses successfully when the target is Python.
9. The proposal remains review-only: no file write, commit, push, or merge.

Failure of any gate yields `BLOCKED`, not a best-effort patch.

## Architecture

- `scanner.py` — repository inventory and modernization evidence.
- `history.py` — churn and ownership evidence.
- `architecture.py` — internal dependency graph, cycles, hubs and upgrade boundaries.
- `commands.py` — evidence-backed baseline command discovery.
- `harness.py` — non-executing baseline harness generation.
- `recipes.py` — deterministic migration recipe catalog.
- `slices.py` — constrained migration slices and verification gates.
- `patches.py` — one-slice patch proposal engine and scope/diff-budget gates.
- `models.py` — structured snapshot model.
- `planner.py` — staged modernization plan.
- `report.py` — JSON + Markdown evidence and harness artifacts.
- `cli.py` — CLI and CI exit codes.

## Engineering waves

1. ✅ Safety/risk scanner + Git history.
2. ✅ Dependency/architecture graph + upgrade-boundary discovery.
3. ✅ Migration Recipe Engine.
4. ✅ Baseline command discovery + test harness generation.
5. ✅ Constrained one-slice Patch Proposal Engine.
6. Differential verification: before/after behavior, tests, performance and errors.
7. LLM/B300 layer for very large repositories and high-volume evaluation.

## Principle

**Access to code is not authority to merge. Generation is not evidence.**

Every automated change must earn approval by strengthening the evidence chain.
