# Market Snapshot-Oracle Evidence — After Bounded Classifier Fix

Observed: 2026-09-22

Evidence workflow run: `35798053120`

Artifact: `10725235089`

Upstream: `GoogleCloudPlatform/opentelemetry-operations-js`

## Before

The unmodified classifier recognized only 1 of 2 real dependency-upgrade PRs that changed snapshot/oracle artifacts:

- PR #537: REVIEW — snapshot mutation missed
- PR #543: BLOCKED — test-file mutation detected

Result: **1/2 blocked — PARTIAL**.

## Bounded change

The oracle classifier was extended only to recognize established snapshot/golden artifact conventions:

- `__snapshots__`, `snapshot`, `snapshots`
- `golden`, `goldens`
- `*.snap`
- `*.approved.*`
- `*.golden`

## After

| PR | Snapshot changed | ModFactory | Oracle mutation blocked |
|---|---:|---|---:|
| #537 | yes | BLOCKED — `verification-oracle-modified` | yes |
| #543 | yes | BLOCKED — `verification-oracle-modified` | yes |

Result: **2/2 blocked, 0 missed — POSITIVE**.

PR #537 is the key market case: it changed only a snapshot artifact plus dependency manifests/lockfiles, so the previous detector did not see an ordinary test source file. After the bounded fix, the changed `__snapshots__` artifact itself is treated as part of the verification oracle.

## Product interpretation

This does not say the dependency upgrades are wrong. It says an upgrade that changes the evidence used to approve itself should not be silently upgraded from green CI to an independent safety PASS. ModFactory requires explicit review of the changed oracle.

This is a real workflow already present in an upstream project whose Renovate configuration automatically runs `update-snapshot-tests` after OpenTelemetry upgrades.