# Private Code Modernization Factory — MVP

Evidence-first repository modernization analysis. The MVP does **not** modify code automatically. It first determines whether a repository is safe to modernize and produces a staged migration plan with explicit exit criteria.

## Why this exists

AI can generate large code changes quickly, but large unverified rewrites create hidden operational risk. This project treats modernization as an evidence problem:

`repo -> snapshot -> blockers -> safety gate -> staged migration plan -> verification evidence`

The commercial direction is a managed modernization factory: analyze a customer repository, create the safety baseline, execute small migration slices, and deliver reviewable PRs plus evidence.

## Current MVP

- Detects languages and build/dependency manifests.
- Detects tests and GitHub Actions CI.
- Detects selected obsolete APIs and deprecated dependency patterns.
- Flags oversized source files that increase migration blast radius.
- Analyzes Git history for high-churn/single-owner hotspots.
- Produces a 0–100 modernization risk score.
- Produces a BLOCK / REVIEW / PASS gate.
- Produces staged migration plans and constrained migration slices.
- Emits JSON and Markdown evidence.
- Has zero runtime dependencies.

## Run

```bash
python -m pip install -e .
modfactory analyze /path/to/repository --output .modfactory
```

To make the analyzer usable as a CI gate:

```bash
modfactory analyze . --output .modfactory --fail-on high
```

## Demo

```bash
modfactory analyze examples/legacy_app --output demo-report
cat demo-report/report.md
```

The included synthetic legacy example intentionally contains compatibility blockers and no tests/CI so the analyzer should block modernization until a safety baseline exists.

## Architecture

- `scanner.py` — deterministic repository inventory and evidence collection.
- `history.py` — churn and ownership evidence from Git history.
- `models.py` — structured findings/snapshot model.
- `planner.py` — staged modernization plan.
- `slices.py` — constrained migration slices with explicit change/verification boundaries.
- `report.py` — JSON + Markdown evidence generation.
- `cli.py` — command-line interface and CI exit codes.

## Next engineering waves

1. Dependency/architecture graph and upgrade-boundary discovery.
2. Framework/version-specific migration recipes.
3. Baseline command discovery and test harness generation.
4. Patch generator constrained to one migration slice at a time.
5. Differential verification: before/after tests, API behavior, performance and errors.
6. LLM/B300 layer for very large repositories, long-context architectural reasoning, multi-agent patch proposals, and high-volume evaluation.

## Principle

**Access to code is not authority to merge. Generation is not evidence.**

Every automated change must earn approval by improving the evidence chain.
