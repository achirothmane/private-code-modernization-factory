# Historical Semantic Regression Evidence

Observed: 2026-09-22

Evidence workflow run: `35785381422`

Artifact: `10719764297`

## Question

Can the current ModFactory implementation discover real semantic regressions when the existing test oracle is held fixed and does not cover the broken behavior?

This benchmark intentionally adds no new detector. A separate external probe establishes whether the historical regression is present after the original baseline tests run.

## Results

| Repository | Historical case | Baseline tests | External probe | ModFactory | Detected? |
|---|---|---:|---:|---|---:|
| `coleifer/peewee` | #2376, production diff from `ebe3ad5023d60ebf2fb91528d422a01596220cde` | PASS | FAIL | REVIEW — `static-pass-project-contract-not-executed` | no |
| `agentscope-ai/agentscope` | #2055 root-cause hunk from `81538d356803d0224d8076c1e793702143c866f4` | PASS | FAIL | REVIEW — `static-pass-project-contract-not-executed` | no |

**Historical regressions reproduced:** 2/2

**Detected by ModFactory:** 0/2

**Semantic detection signal:** `NEGATIVE`

## Peewee #2376

The benchmark applies only the production-code change from the historical regression-introducing commit to its parent. The baseline `tests/keys.py` and `tests/regressions.py` files are held unchanged and loaded directly, avoiding unrelated optional PostgreSQL/Cockroach test imports.

Observed:

- baseline tests: PASS
- external regression probe: FAIL
- ModFactory: REVIEW
- new static findings: none
- risk score: unchanged
- semantic regression detected: no

The external probe reproduces the model-instance conversion failure documented by the later #2376 fix.

## AgentScope #2055

The benchmark applies the documented root-cause hunk: removal of the default `_glob_helper_path: str | None = None` while `LocalWorkspace.list_tools()` still reads that attribute. The existing local-workspace tests are held unchanged.

Observed:

- baseline `workspace_local_test.py`: PASS — 17 tests
- external `LocalWorkspace.list_tools()` probe: FAIL with `AttributeError: 'LocalWorkspace' object has no attribute '_glob_helper_path'`
- ModFactory: REVIEW
- new static findings: none
- risk score: unchanged
- semantic regression detected: no

## Interpretation

This is a real limitation, not a false PASS.

ModFactory returned `REVIEW`, so it did **not** claim the patches were deployment-safe. However, it also did not discover either semantic regression. The current implementation therefore has evidence for a narrower capability:

> It can protect verification-oracle integrity and run a reproducible evidence contract, but it does not independently discover arbitrary untested semantic behavior changes.

The earlier `balanced-match` benchmark remains positive for test-oracle integrity. This benchmark is negative for semantic regressions outside the existing oracle.

## Product consequence

Do not market the current system as a general semantic-equivalence or semantic-regression verifier.

The next product decision should be whether one bounded behavioral layer—such as explicit characterization/replay contracts supplied independently of the patch—adds enough detection value to justify another RETEST iteration. Do not expand languages, agents, dashboards, or migration recipes before that evidence exists.
