# Product Continuity, Observed Evidence, and Authority

## Reviewed GitHub baseline — 18 November 2026

The public repository's default `main` branch contained the ModFactory Python package, CLI, existing unit tests, quickstart fixtures, historical modernization research, benchmark reports and GitHub Actions workflows.

The inspected branch had **no open pull requests**, while historical research and development branches existed. This is a dated repository observation, not a claim that all local development or third-party work is absent.

The [README](../README.md) emphasizes independent external patch verification. The [research log](research-log.md) describes a broader modernization pipeline. Both identities and the actual existing source are retained.

## What current artifacts substantiate

- [README](../README.md): identity-bound patch verification, protected approval evidence, frozen checks, external behavior contracts and PASS / REVIEW / BLOCKED / FAIL.
- [Current implementation](../src/modfactory/external_patch.py): the actual patch verification code, which must be examined for any behavioral claim.
- [Verification implementation](../src/modfactory/verification.py) and [CLI](../src/modfactory/cli.py): existing modernization and verification mechanisms.
- [Research log](research-log.md): the actual historical modernization work, including model and compute falsification.
- [Snapshot-oracle benchmark](../benchmarks/market-snapshot-oracle-after.md): improvement from partial to full detection in the two inspected cases.
- [Historical negative evidence](../benchmarks/historical-semantic-regressions.md): semantic regressions missed by original evidence.
- [External behavior retest](../benchmarks/external-behavior-contract-retest.md): detection when missing independent oracles were supplied.
- [Ordinary-model experiments](../benchmarks/results/wave7h-first-measured-models-2026-09-21.md): measured failed patch outputs and limitations.
- [CI workflow](../.github/workflows/ci.yml): the checks configured on push/pull request.

Before this documentation change, GitHub reported a completed **successful CI** run for the inspected `main` SHA. That establishes only the checks in that run, not a security audit, complete semantic verification, or customer demand.

## Honest evidence vocabulary

| Statement type | Required interpretation |
| --- | --- |
| Vision | Intended long-term engineering direction |
| Architecture or hypothesis | Designed approach whose behavior still needs testing |
| Existing code | Inspectable implementation at a particular revision |
| Test evidence | A result tied to a command, source, environment and input |
| External oracle | A sufficiently separate acceptance contract that candidate code cannot silently rewrite |
| Verified narrow claim | A result supported within the exact scope tested |
| Deployment authority | A distinct permission, **not** granted by PASS |
| Market acceptance | Repeated real usage and buyer outcomes supported by evidence |
| Unresolved gap | Failed, unknown, blocked or unverified behavior |

Negative evidence is a reason to adjust claims or mechanisms, not to delete history or rename the ambition.

## The current adoption question

The README defines a specific near-term observation target: a qualified visitor uses `verify-patch`, finds the verdict useful and voluntarily uses it a second time.

It states that expanding into a broader platform is not commercially justified before that loop is observed. Preserve this **current business validation boundary** without turning it into a permanent restriction on scientific research or long-term product identity.

A useful tool, good benchmark, repository star or green CI does not by itself demonstrate revenue, customer retention or product-market fit.

## Authorization, privacy, and practical limits

Current source keeps candidate verification in temporary copies, does not auto-merge or deploy, and requires explicit opt-in to execute project test commands. That is not complete hostile-code sandboxing.

Future access to private repositories, credentials, CI enforcement, cloud resources, payment systems, production services or customer data requires appropriate authority and protections; none is implied by a vision document.

This update adds [VISION.md](../VISION.md), [CLAUDE.md](../CLAUDE.md), four supporting English documents and a minimal pointer from README. It **does not** change source, tests, verification outcomes, package metadata, the license, existing benchmarks or deployment permissions.

**Preserve the historic engineering breadth, preserve negative and positive results, and keep the next task inside its actual authorization.**
