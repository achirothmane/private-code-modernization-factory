# Independent Assurance and Evidence Integrity

## The fundamental trust problem

An upgrade patch may change both application behavior and the **tests, snapshots, golden files or commands used to approve it**. A green CI result can then be circular.

The [README](../README.md) identifies ModFactory's current contribution: bind a candidate to exact source and patch identity, protect verification-oracle identity, reuse frozen commands and evaluate appropriate external behavior contracts.

## Present decision semantics

| Outcome | Meaning within current code and evidence |
| --- | --- |
| PASS | Executed checks passed for the exact candidate under tested assumptions; not deployment permission |
| REVIEW | Additional evidence or explicit judgment is needed |
| BLOCKED | Required identity, oracle or trust conditions were not met |
| FAIL | Executed checks detected a regression |

A change to a test can be legitimate and still require an independent reviewer. A BLOCKED report is not a statement that the patch is necessarily incorrect.

An explicitly confirmed no-op yields REVIEW, not PASS. Existing results are not retroactively reclassified when a newer version adds stronger identity evidence.

## Grounded positive and negative cases

- [OpenTelemetry snapshots](../benchmarks/market-snapshot-oracle-after.md): two real update examples with relevant snapshot/test mutation blocked after a bounded classifier improvement.
- [balanced-match](../benchmarks/external-patch-evidence.md): a poisoned-test example where ordinary CI passed but ModFactory blocked the changed oracle.
- [Historical semantic regressions](../benchmarks/historical-semantic-regressions.md): **0/2 detected** from the available original evidence.
- [External-contract retest](../benchmarks/external-behavior-contract-retest.md): **2/2 detected** after missing acceptance conditions were supplied independently.

The 2/2 result is evidence for **those cases under those independent contracts**. It is not proof that the system can discover unknown semantic requirements or that all production migrations are safe.

## Possible future assurance

Long-term research might include formal contracts, test synthesis, property-based and metamorphic testing, richer runtime traces, architecture invariants, migration-specific differential evaluation, adversarial testing, security and performance assessments, independent evidence generation and stronger change provenance.

No technique, including formal verification, can establish an unspecified universal safety claim without explicit properties and trusted assumptions.

## Safety and authority boundaries

The present implementation uses temporary candidate trees but does not provide OS-level isolation of hostile project code. Running target checks is opt-in. Existing PASS results do not authorize merges, release or deployment.

Stronger future assurance may require external reviewers, hardened execution, system-level permissions, reproducible test conditions, human decision processes and verifiable recovery paths.

**Independent evidence is an architectural and procedural property, not a label a model assigns to its own result.**
