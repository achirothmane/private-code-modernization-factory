# Market Snapshot-Oracle Evidence — Before Classifier Fix

Observed: 2026-09-22

Evidence workflow run: `35797909947`

Artifact: `10724803042`

Upstream: `GoogleCloudPlatform/opentelemetry-operations-js`

The upstream Renovate configuration runs `npm run update-snapshot-tests` after OpenTelemetry dependency upgrades. Two real merged upgrade PRs were replayed without changing ModFactory's oracle classifier first.

| PR | Snapshot changed | ModFactory | Oracle mutation blocked |
|---|---:|---|---:|
| #537 | yes | REVIEW — `static-pass-project-contract-not-executed` | no |
| #543 | yes | BLOCKED — `verification-oracle-modified` | yes |

Result: **1/2 blocked, 1/2 missed — PARTIAL**.

PR #537 changed `packages/opentelemetry-cloud-monitoring-exporter/__snapshots__/instrument-snapshot.test.ts.js`, but the current classifier did not recognize `__snapshots__` as a test-oracle location.

This is the market evidence motivating the bounded classifier change. No broader feature is justified by this result.