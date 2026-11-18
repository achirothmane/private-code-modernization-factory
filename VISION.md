# ModFactory — Comprehensive, Future-Open Vision for Software Evolution Engineering

## Product identity: independent evidence for changing software

**ModFactory** (the private-code-modernization-factory repository) is an evolving **evidence-first software modernization and independent change-verification system**. Its central question is not merely whether a patch compiles or whether an agent says it succeeded. It asks whether **the exact proposed software change preserves or improves the intended behavior under evidence that the change itself cannot quietly redefine**.

The current [README](README.md) presents **independent verification of externally produced code-upgrade patches** as the leading product hypothesis. The [research log](docs/research-log.md) preserves a wider and earlier modernization program: target-aware repository analysis, architectural evidence, deterministic migration recipes, bounded proposals, differential verification, context-minimized model evaluation and human review.

**Both are part of the project's real history and capability horizon.** The emphasis on independent patch verification must not erase the broader evolution engineering ambition; the broader ambition must not falsely declare that all modernization, behavioral equivalence or autonomous change are already solved.

The existing implementation uses Python, Git, tests, benchmarks and verification artifacts. These mechanisms are assets, not the permanent limits of the vision.

## A broad, non-exhaustive engineering future

The enduring aim is to make **software change increasingly intelligible, testable, recoverable and trustworthy**, across programming languages, architectures, deployment models and future forms of software.

Potential capabilities may span:

- **Understanding existing systems:** recovering structure, dependencies, runtime assumptions, implicit contracts, invariants, hidden state, data flow, usage sites and operational constraints.
- **Specifying intended evolution:** language and framework upgrades, platform migrations, API changes, data-model transformations, security improvements, architecture changes, performance work and as-yet-unknown forms of software adaptation.
- **Creating and revising candidate changes:** deterministic transforms, human-authored patches, agent-produced proposals, hybrid transformations, migration plans and coordinated multi-file or multi-system changes.
- **Independent correctness evidence:** frozen and externalized oracles, behavioral characterization, before-and-after tests, differential execution, metamorphic properties, type and static analysis, formal methods, performance and security assessments, reproducible experiments and causal diagnosis.
- **Diagnosing failures and uncertainty:** explaining a change's likely failure mechanism, distinguishing absent coverage from passing evidence, locating gaps in tests or specifications, comparing alternative repairs and avoiding circular self-approval.
- **Controlled delivery and recovery:** reviewable proof records, provenance, attestations where valid, rollback analysis, compatibility assessment, staged release evidence and safeguards against hidden authority transfer.
- **Learning across change tasks:** extracting reusable engineering knowledge from real regressions, successful transformations, failure modes, repositories and verified human decisions.
- **New paradigms:** software systems, languages, infrastructures and forms of machine intelligence that cannot be reliably specified today.

This is an **open long-term capability horizon**. It is neither a required immediate feature backlog nor a claim of universal semantic verification, AI autonomy, total coverage or technical feasibility of every possible future mechanism.

## Modernization and independent verification reinforce one another

The historical modernization pipeline is recorded in [research-log.md](docs/research-log.md) and remains a legitimate part of the product's vision. In contrast, the current README focuses on a sharply testable question: can an external patch's evidence be trusted when the patch may also alter tests, snapshots or their execution commands?

Neither perspective should substitute for the other:

- **Modernization intelligence** investigates what should change, why, and how candidate changes might be constructed.
- **Independent verification** investigates what the exact candidate actually changed and what trustworthy evidence supports acceptance.
- **Human and organizational authority** determines what may be executed, merged, released or deployed.

A narrower present-day commercial experiment can be pursued without permanently redefining the full product as a snapshot checker, dependency-upgrade gate or static report generator.

## The present evidence boundary must remain exact

The [README](README.md) defines the current four-way decision:

| Result | Current meaning |
| --- | --- |
| **PASS** | The exact candidate passed the evidence actually executed; **not** deployment authorization |
| **REVIEW** | A limited positive result with stronger project or behavior checks not run, or explicit review needed |
| **BLOCKED** | The evidence boundary cannot justify independent approval or the candidate violates a protected condition |
| **FAIL** | Executed before-and-after evidence found a regression |

The source implementation and actual reports determine the precise result for each run. **An old PASS cannot be retroactively upgraded** to a stronger claim merely because later identity protections were added.

Current mechanisms include exact patch/baseline/candidate identities, protected approval-oracle detection, frozen test commands, external behavior contracts, temporary candidate copies, and explicit opt-in before executing target project code. These mechanisms reduce particular risks; they are not an adversarial code-execution sandbox or a general equivalence proof.

An intentional no-op is a separately identified **REVIEW**, not a silent PASS. Verified test-execution results are evidence at their scope, not an authorization to merge, deploy, approve a security-sensitive upgrade or use affected systems in production. The README records `deployment_admissible` as false on current paths.

## Positive and negative results are equally part of the product

The existing benchmark archive is foundational evidence, not marketing material to clean up when inconvenient.

Examples from recorded investigations:

- A real OpenTelemetry/Renovate snapshot-oracle study progressed from **1/2** detected mutations to **2/2 blocked** after a bounded classifier correction. See [the after record](benchmarks/market-snapshot-oracle-after.md).
- A [balanced-match external patch study](benchmarks/external-patch-evidence.md) showed how a behavior regression accompanied by a weakened test could leave ordinary CI green while ModFactory produced **BLOCKED**.
- Historical [Peewee and AgentScope semantic cases](benchmarks/historical-semantic-regressions.md) were **0/2 detected** by the original fixed-oracle approach; independent external behavior contracts [detected 2/2](benchmarks/external-behavior-contract-retest.md) when the missing acceptance properties were explicitly supplied.
- [Wave 7H ordinary-model experiments](benchmarks/results/wave7h-first-measured-models-2026-09-21.md) failed patch-validity checks on the measured task. Larger models and compute did not automatically solve protocol correctness.

These are **bounded, historically observed outcomes**, not measured general reliability, benchmark superiority, independent buyer adoption or future production guarantees.

## Scientific rigor and the impossibility of shortcutting evidence

General semantic equivalence, behavior preservation and safety cannot be inferred from a finite collection of ordinary tests. A complete evidence story depends on an explicit system and threat model, verified assumptions, adequate oracles and the actual scope of the checks.

A model's self-evaluation is not independent verification. Static checks alone cannot establish runtime compatibility. A test may pass because the behavior it was intended to protect has never been specified. Formal guarantees, where pursued, require precisely defined properties and trusted premises rather than broad promises of infallibility.

The long-term product can pursue stronger program understanding, formal verification, adaptive testing, independent reproducibility and even new scientific methods without pretending they are already achieved.

## Software and AI horizons beyond today's workflow

More capable coding agents, new program analysis techniques, novel runtime systems and possibly future AGI or ASI could change the economics and mechanisms of software evolution. Their appearance, abilities and timelines are uncertain.

ModFactory may interoperate with future intelligence while retaining a crucial distinction: **the agent proposing a change must not silently control the independent evidence used to judge it**. Independence is a property of the trust boundary and evaluation procedure, not of an agent's name or a marketing claim.

The product is not obliged to depend on any specific foundation model, hosting platform, language, framework, GPU class or commercial automation service.

## Value and commercialization are questions, not assumptions

The [current README](README.md) identifies a near-term validation loop: **a qualified visitor runs `verify-patch`, receives a useful verdict, and voluntarily repeats the process on another patch**. It explicitly states that a broader platform build is not commercially justified until this repeated use is observed.

That is a **current commercial and execution decision**, not an eternal constraint on the product's research vision or a mandate to stop all exploration if one channel fails.

Potential economic value would need real evidence of avoided regressions, reduced review burden, faster safe upgrades, repeated integration, actual paid commitments or other outcomes. Benchmarks, downloaded code, CI badges and hypothetical savings alone do not prove revenue.

## Trust, permissions and operational responsibility

The current verifier does not auto-merge or deploy. Running arbitrary target project code requires an explicit opt-in, and temporary worktree isolation must not be represented as OS/container security isolation.

Future authority-bearing integrations—repository write operations, CI policy enforcement, external credentials, production modifications, security-sensitive project code execution, cloud provisioning or customer-data access—need explicit task authority and appropriate isolation and review.

Preserve source provenance, rights, private-code confidentiality, dependency licenses and the integrity of independent evidence.

## Distinguish vision from reality on every iteration

1. **Permanent product vision:** trustworthy engineering of software evolution.
2. **Current target and authorized task:** the bounded problem and work actually requested.
3. **Designed mechanism:** a hypothesis, algorithm or planned workflow.
4. **Implemented system:** source and artifacts under an identified revision.
5. **Executed evidence:** reproducible tests or measurements under stated conditions.
6. **Independently verified claim:** a conclusion supported by a sufficiently separate oracle or reviewer at the proper scope.
7. **Operational/commercial result:** actual deployment, adoption, buyer decision or settled payment, each separately established.
8. **Unresolved gap:** what failed, is missing, is unknown or cannot currently be claimed.

**Bounded delivery does not shrink the vision. A broad vision is not standing permission to execute unrequested changes.**

## Supporting references

- [Software evolution and modernization horizons](docs/01-SOFTWARE-EVOLUTION-HORIZONS.md).
- [Independent assurance and evidence integrity](docs/02-INDEPENDENT-ASSURANCE-AND-EVIDENCE.md).
- [Future intelligence and transformation research](docs/03-FUTURE-INTELLIGENCE-AND-TRANSFORMATION.md).
- [Continuity, observed status and authority](docs/04-CONTINUITY-EVIDENCE-AND-AUTHORITY.md).

**ModFactory's future is not merely generating software changes. It is building progressively stronger ways to understand, justify, verify and govern change while preserving honest boundaries of knowledge.**
