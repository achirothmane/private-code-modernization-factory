# Wave 7B — Evidence Refinement Result

Date: 2026-09-20

## Same pinned corpus

Repositories analyzed: 10 / 10  
Source files: 6,326  
Lines scanned: 2,195,930  
Errors: 0

## Before → after evidence refinement

| Metric | Wave 7A initial | Wave 7B final |
|---|---:|---:|
| Findings | 499 | 486 |
| Compatibility slices | 17 | 3 |
| Semantic escalations | 12 | 0 |
| Safety blockers | 5 | 3 |
| Architecture slices | 136 | 136 |
| Long-context candidates | 0 | 0 |

Semantic escalation progression during Wave 7B: **12 → 1 → 0**.

## What removed the false escalation pressure

- Python AST evidence removed documentation/comment matches such as the pytest distutils note.
- Direct package.json dependency evidence removed package-lock duplicates.
- Java import + Jakarta allowlist evidence removed Java SE, JCache, XML/config, documentation, and system-property javax matches.
- npm usage evidence reclassified Lodash's direct request dependency as dependency hygiene because no static import/require/script usage was observed.

## Remaining compatibility work

Three compatibility slices remain, all blocked by verification prerequisites rather than semantic uncertainty:

- python-twofish: 2 slices blocked because baseline tests are missing.
- ansible: 1 slice blocked because the benchmark does not see the required CI baseline evidence for that migration.
- No semantic review candidate survives.

## Compute decision

B300 rental recommended: **false**  
Decision: **NOT_JUSTIFIED_BY_CURRENT_EVIDENCE**

There is no surviving semantic workload in this corpus to benchmark with an LLM. Running a model benchmark now would measure a solution against a workload eliminated by better evidence.

A future model benchmark is allowed only when a genuine semantic candidate survives the Evidence Refinement Gate. B300-class compute remains a second-stage escalation after smaller/ordinary model configurations are measured and shown insufficient.
