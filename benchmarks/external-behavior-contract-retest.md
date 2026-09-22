# External Behavior Contract Retest

Observed: 2026-09-22

Evidence workflow run: `35792033960`

Artifact: `10722567246`

## Question

Can ModFactory convert the two previously missed historical semantic regressions into explicit failures when the missing acceptance behavior is supplied as a frozen external characterization contract?

The contract is not stored inside the repository under review. ModFactory records both the external contract file SHA-256 and a canonical contract SHA-256 before running the same command against baseline and candidate trees.

## Before this iteration

The fixed-oracle historical benchmark reproduced both regressions but ModFactory discovered neither:

- historical regressions reproduced: 2/2
- detected by ModFactory: 0/2
- semantic detection signal: `NEGATIVE`

The repository tests passed while separate external probes reproduced the broken behavior.

## After adding external behavior contracts

| Repository | Baseline tests | External probe | Behavior contract before | Behavior contract after | ModFactory |
|---|---|---|---|---|---|
| `coleifer/peewee` | PASS | FAIL | PASS | FAIL | FAIL — `behavior-contract-regression` |
| `agentscope-ai/agentscope` | PASS | FAIL | PASS | FAIL | FAIL — `behavior-contract-regression` |

**Historical regressions reproduced:** 2/2

**Detected by ModFactory:** 2/2

**Missed:** 0/2

**Semantic detection signal:** `POSITIVE`

## Peewee #2376

Patch SHA-256:

`68800f4f1983f36fff45f120f811b3ae3f4b14f89d524ee89213eb5dab055cbe`

Behavior contract:

- case: `peewee-model-in-conversion`
- external contract file SHA-256: `0e83c5d5e7249dc4106b9d8dc6e9e4922b3915b8537ad131ada27cb0bab7b56b`
- frozen contract SHA-256: `6208da6be7d87f050b7488f9fc628527d03476accd7717ab939a55e511baad05`

Observed:

- baseline behavior: PASS
- candidate behavior: FAIL
- candidate failure: expected model IDs `['0', '1', '2']`, observed `[]`
- verdict: `FAIL — behavior-contract-regression`

## AgentScope #2055

Patch SHA-256:

`dba99edbef9b4aa0608cb3d0e64c411b51c6b07ea47b45b99930b0063f3004fa`

Behavior contract:

- case: `agentscope-local-list-tools`
- external contract file SHA-256: `6c7705f0bf1b28ef6b18d249f160089fecab3691207036871636ff7b36d9a0aa`
- frozen contract SHA-256: `f7aadad6f0352b8ba8d84fc3e511190a126ed7ba0a91a0111cdc7693d23b568c`

Observed:

- baseline behavior: PASS
- candidate behavior: FAIL
- candidate failure: `AttributeError: 'LocalWorkspace' object has no attribute '_glob_helper_path'`
- verdict: `FAIL — behavior-contract-regression`

## What this proves

The current system can detect semantic regressions that ordinary repository tests miss **when an independent behavior/characterization contract already captures the relevant behavior**.

This is stronger than the earlier test-oracle-integrity result because the patch does not modify the existing tests in either historical case.

## What this does not prove

This is not automatic semantic understanding and does not establish general semantic equivalence.

ModFactory still cannot invent the missing behavior contract from nothing. If neither the repository tests nor an independent characterization contract covers a behavior, that behavior can still regress without detection.

The current defensible product claim is therefore:

> ModFactory freezes independent verification evidence around a patch and can reject changes that violate explicit behavioral contracts even when the repository's ordinary tests remain green.

The next RETEST should measure whether real teams already possess or can cheaply create such characterization/replay contracts, and whether adding them reduces review risk or review time enough to justify repeated use.
