# ModFactory

**Independent verification for code-upgrade patches.**

Coding agents, codemods, Renovate, Dependabot, and migration tools can generate a patch. ModFactory is the separate evidence layer that asks:

> **Did this exact patch preserve the evidence and behavior we rely on?**

It hashes the patch and baseline, detects when a patch changes its own approval evidence, can run the same frozen checks before and after, and can enforce external behavior contracts that the patch cannot rewrite.

**Evidence before action.**

## Problem

A green CI run is not always independent evidence. An upgrade can change tests, assertions, snapshots, golden files, the test command itself, or behavior that existing tests never covered.

If a patch also changes the evidence used to approve it, `tests passed` can become circular. ModFactory does not say every test or snapshot change is wrong; it changes the decision from silent PASS to explicit review when the approval evidence moved.

## 60-second quickstart

Requires Python 3.10+ and Git.

~~~bash
git clone https://github.com/achirothmane/private-code-modernization-factory.git
cd private-code-modernization-factory
python -m pip install -e .
~~~

Run the included snapshot-oracle example:

~~~bash
modfactory verify-patch examples/quickstart/repo \
  --patch examples/quickstart/candidate.diff \
  --producer demo
~~~

Expected:

~~~text
Verification: BLOCKED
Reason: verification-oracle-modified
Level: static
~~~

The demo patch changes both application behavior and the snapshot that would approve that behavior. `BLOCKED` intentionally exits non-zero (`5`) so it can be used as a CI gate.

## Verify any external patch

~~~bash
modfactory verify-patch /path/to/baseline-repo \
  --patch /path/to/candidate.diff \
  --producer codex
~~~

The producer is metadata only. ModFactory records the exact patch SHA-256, changed baseline-file hashes, changed paths, static before/after evidence, and any verification-oracle violations. The original repository is never modified.

## Decision model

| Result | Meaning |
|---|---|
| **PASS** | The exact patch passed the evidence that was actually executed. This is **not** deployment authorization. |
| **REVIEW** | Static evidence passed, but stronger project/behavior evidence was not executed. |
| **BLOCKED** | The evidence boundary is not trustworthy or sufficient, for example the patch changed tests/snapshots/test commands or the baseline evidence failed. |
| **FAIL** | Executed before/after evidence found a regression. |

ModFactory deliberately prefers `REVIEW` or `BLOCKED` over false confidence.

## External behavior contracts

Repository tests can stay green and still miss a behavior regression. A behavior contract pins acceptance behavior **outside the repository under review**, so the patch cannot rewrite it.

Included example:

~~~bash
modfactory verify-patch examples/behavior-contract/repo \
  --patch examples/behavior-contract/candidate.diff \
  --behavior-contract examples/behavior-contract/behavior.json \
  --allow-project-code \
  --producer demo
~~~

Expected:

~~~text
Verification: FAIL
Reason: behavior-contract-regression
Level: behavior-contract
~~~

The same contract is frozen by SHA-256 and executed against both baseline and candidate trees.

Minimal contract:

~~~json
{
  "schema_version": 1,
  "commands": [
    {
      "id": "critical-behavior",
      "command": "python -c \"assert __import__('app').VALUE == 1\"",
      "working_directory": "."
    }
  ]
}
~~~

The contract file must live outside the repository path being verified.

## Run project checks before and after

Project execution is explicit opt-in:

~~~bash
modfactory verify-patch /path/to/repo \
  --patch /path/to/candidate.diff \
  --allow-project-code \
  --timeout 120
~~~

ModFactory discovers the baseline verification commands, freezes them, and reuses the same commands after the patch. It does not rediscover a weaker post-patch command set and call that independent evidence.

For supported dependency layouts:

~~~bash
modfactory verify-patch /path/to/repo \
  --patch /path/to/candidate.diff \
  --allow-project-code \
  --provision-environments
~~~

Current managed provisioning is intentionally narrow: Python virtual environments and npm projects with a reproducible npm lockfile. Unsupported cases fail closed rather than silently falling back.

## Protected approval evidence

Current protected categories include test/spec source files, test execution configuration, package test scripts, `__snapshots__`, `snapshot(s)`, `golden(s)`, `*.snap`, `*.approved.*`, and `*.golden`.

A change to one of these is not automatically a bad change. It means the patch changed part of the evidence used to approve itself and needs independent review.

## Evidence

### Real Renovate workflow: OpenTelemetry

`GoogleCloudPlatform/opentelemetry-operations-js` automatically updates snapshots after OpenTelemetry dependency upgrades. On two real merged upgrade PRs, ModFactory initially caught **1/2** oracle mutations. After the bounded snapshot/golden classifier fix, the same PRs became **2/2 blocked, 0 missed**.

- [before](benchmarks/market-snapshot-oracle-before.md)
- [after](benchmarks/market-snapshot-oracle-after.md)

### Green CI with a poisoned oracle

On `juliangruber/balanced-match`, an adversarial patch changed behavior and weakened the corresponding test expectation. Ordinary CI stayed green; ModFactory returned `BLOCKED — verification-oracle-modified`.

- [external patch evidence](benchmarks/external-patch-evidence.md)

### Historical semantic regressions

With only existing repository tests, reproduced Peewee #2376 and AgentScope #2055 were **0/2 automatically detected**. That negative result is preserved.

- [negative fixed-oracle evidence](benchmarks/historical-semantic-regressions.md)

When the missing acceptance behavior was supplied independently as an external frozen behavior contract, the same two cases became **2/2 detected** with `behavior-contract-regression`.

- [behavior-contract retest](benchmarks/external-behavior-contract-retest.md)

## Guarantees and limits

ModFactory currently guarantees only what its evidence supports:

- exact patch and changed baseline files are content-addressed;
- verification happens in temporary before/after copies;
- recognized tests/snapshots/golden evidence cannot be silently weakened and still produce an independent PASS;
- frozen project commands are reused before/after;
- external behavior contracts are independent of the repository under review;
- no stage auto-merges or deploys.

It **does not** prove general semantic equivalence, invent missing behavior coverage automatically, turn PASS into production safety, sandbox arbitrary untrusted project code, or support every package manager/runtime/environment.

`deployment_admissible` remains false in the current verification paths.

## Output

~~~text
.modfactory/
└── external-patch/
    ├── verification.json
    └── verification.md
~~~

The JSON artifact is for CI/automation. The Markdown report is for human review.

## Other commands

The repository still contains the earlier modernization-analysis pipeline:

~~~bash
modfactory analyze /path/to/repo
modfactory propose /path/to/repo --slice-id <slice-id>
modfactory verify /path/to/repo --slice-id <slice-id>
modfactory benchmark /path/to/corpus --manifest benchmarks/corpus.json
~~~

These are secondary to the current product hypothesis: **independent verification of externally produced upgrade patches**.

For the full engineering history, falsification waves, model experiments, and compute gates, see [docs/research-log.md](docs/research-log.md).

## Current validation target

The next target is external repeat usage:

**qualified visitor → runs `verify-patch` → receives a useful verdict → uses it on a second patch.**

No broader platform build is justified until that loop is observed.
