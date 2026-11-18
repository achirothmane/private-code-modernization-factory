# Claude — ModFactory Repository Entry Point

## Preserve the full product

This repository is **ModFactory**, an evidence-first software modernization and independently verifiable change system. The [current README](README.md) focuses on **independent verification of externally produced code-upgrade patches**. The [research log](docs/research-log.md) preserves the broader modernization, architectural analysis, migration, model-evaluation and differential-verification work.

The [long-term VISION.md](VISION.md) spans software evolution, independent assurance, program understanding, diagnosis, repair evaluation, language/platform change and future engineering intelligence. **Do not narrow this enduring vision to one upgrade gate, snapshot classifier or easy benchmark.** Do not replace it with a generic AI agent, cloud control plane, CI plugin or speculative product without the owner's express approval.

A small current feature is permitted as an increment, **not a new definition of the complete product**. Equally, the future vision does not authorize unnecessary rewrites or feature expansion in a given task.

## Start from the actual source and evidence

Read the relevant files, not just filenames:

- [README.md](README.md): current product hypothesis, CLI, decision semantics and explicit limits.
- [VISION.md](VISION.md): open long-term product identity.
- [docs/research-log.md](docs/research-log.md): modernization analysis and experimental waves, including negative findings.
- [src/modfactory/](src/modfactory/): actual implementation; in particular inspect [external_patch.py](src/modfactory/external_patch.py), [verification.py](src/modfactory/verification.py), [behavior_contract.py](src/modfactory/behavior_contract.py), [cli.py](src/modfactory/cli.py) and relevant analysis/patch/model modules.
- [tests/](tests/): actual tests; inspect the specific tests affected by a proposed change.
- [pyproject.toml](pyproject.toml) and [.github/workflows/ci.yml](.github/workflows/ci.yml): current packaging and CI.
- [benchmarks/historical-semantic-regressions.md](benchmarks/historical-semantic-regressions.md) and [benchmarks/external-behavior-contract-retest.md](benchmarks/external-behavior-contract-retest.md): preserved 0/2 fixed-oracle failure and 2/2 external-contract detection.
- [benchmarks/market-snapshot-oracle-after.md](benchmarks/market-snapshot-oracle-after.md) and [benchmarks/external-patch-evidence.md](benchmarks/external-patch-evidence.md): real bounded positive signals.
- [benchmarks/results/wave7h-first-measured-models-2026-09-21.md](benchmarks/results/wave7h-first-measured-models-2026-09-21.md): failed model outputs and measured compute facts.
- [LICENSE](LICENSE): existing rights; do not silently change the license.

Additional vision materials:
- [Software evolution horizons](docs/01-SOFTWARE-EVOLUTION-HORIZONS.md).
- [Independent assurance](docs/02-INDEPENDENT-ASSURANCE-AND-EVIDENCE.md).
- [Future intelligence](docs/03-FUTURE-INTELLIGENCE-AND-TRANSFORMATION.md).
- [Continuity and permissions](docs/04-CONTINUITY-EVIDENCE-AND-AUTHORITY.md).

Inspect current source, branches, GitHub workflows and task-specific files before relying on an old benchmark or status statement.

## Owner authority and current task

- **Research/review:** inspect evidence, reproduce or compare only when appropriately enabled, and report findings without unrelated edits.
- **Documentation:** write requested finished documentation while preserving exact historical results and product semantics.
- **Authorized engineering:** implement real source changes and relevant tests, inspect actual before/after behavior, and report results. A documentation-only assignment is **not a permanent prohibition on coding later**.
- **Model evaluation:** use recorded model identity, task, prompt, allowed paths, execution environment, token/cost data where available and independent verification. Do not invent model performance or justify expensive compute by repository size.
- **Target-project execution:** do not run untrusted repository code merely because tests are available. The present verifier requires an explicit opt-in; its temporary copies are not hostile-code sandboxes.
- **External actions:** repository merge/write operations beyond the authorized task, release, public-service deployment, financial spending, external credentials and customer source access require separate permission and actual safety checks.

An open horizon never implies a standing instruction to build a new platform. A bounded task never implies permission to permanently reduce the product's vision.

## Evidence integrity is non-negotiable

The present result vocabulary is **PASS / REVIEW / BLOCKED / FAIL**. Preserve precise meanings from the current README and implementation.

- A PASS reflects **executed evidence for the exact candidate**, not permission to merge or deploy.
- An oracle that the candidate could modify cannot be silently treated as independent.
- Frozen baseline commands and truly external behavior contracts must not be weakened or replaced with easier post-patch tests merely to achieve green status.
- Protected test or snapshot changes can legitimately require review; a BLOCKED result is not a categorical statement that a patch is malicious or wrong.
- A no-op allowed by explicit opt-in is **REVIEW**, not an unearned PASS.
- The current candidate identity checks, temporary copies and allowlists do not create a full sandbox or semantic-equivalence theorem.
- Preserve negative benchmark evidence. Existing tests missed two historical semantic regressions before external contracts supplied missing behavior.
- Do not retroactively grant stronger assurance to older verification artifacts.
- Keep `deployment_admissible` false unless separately implemented authority rules and evidence justify a different documented contract.

The exact failure mechanism and scope matter more than high-level reassurance.

## Do the actual authorized work

Use existing code and contracts rather than producing ceremonial plans, redundant controls or invented implementations. For engineering changes, add meaningful regression evidence and consider independent oracles that a proposed patch cannot rewrite.

The currently recorded external-repeat-user target is a business validation requirement, **not** a permanent upper bound on technical research or a mandate for another product identity.

Report changed files, test commands actually run, CI outcomes, observed evidence level, limitations, external actions (if any) and unresolved gaps. Never declare total safe modernization, AGI capabilities, generalized semantic equivalence, paying customers or production adoption without appropriate proof.

**Preserve ModFactory's expansive engineering identity and protect its independent evidence boundary.**
