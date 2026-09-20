# Private Code Modernization Factory — MVP

Evidence-first repository modernization analysis. The tool does **not** grant an AI authority to rewrite a repository blindly. It first maps risk and architecture, then produces constrained migration slices with explicit verification gates.

## Core pipeline

repo → snapshot → blockers → architecture graph → safety gate → migration slices → verification evidence

## Current capabilities

- Detect languages and build/dependency manifests.
- Detect tests and GitHub Actions CI.
- Detect selected obsolete APIs and deprecated dependency patterns.
- Flag oversized source files that increase migration blast radius.
- Analyze Git history for high-churn/single-owner hotspots.
- Build internal Python and JavaScript/TypeScript dependency graphs.
- Detect dependency cycles and high fan-in/fan-out hubs.
- Convert architecture boundaries into constrained migration slices.
- Produce a 0–100 modernization risk score and BLOCK / REVIEW / PASS gate.
- Emit JSON and Markdown evidence.
- Zero runtime dependencies.

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
- `models.py` — structured snapshot model.
- `planner.py` — staged modernization plan.
- `slices.py` — constrained migration slices and verification gates.
- `report.py` — JSON + Markdown evidence.
- `cli.py` — CLI and CI exit codes.

## Engineering waves

1. ✅ Safety/risk scanner + Git history.
2. ✅ Dependency/architecture graph + upgrade-boundary discovery.
3. Framework/version-specific migration recipes.
4. Baseline command discovery and test harness generation.
5. Patch generator constrained to one migration slice at a time.
6. Differential verification: before/after behavior, tests, performance and errors.
7. LLM/B300 layer for very large repositories and high-volume evaluation.

## Principle

**Access to code is not authority to merge. Generation is not evidence.**

Every automated change must earn approval by strengthening the evidence chain.
