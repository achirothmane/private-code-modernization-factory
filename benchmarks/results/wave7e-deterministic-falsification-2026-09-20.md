# Wave 7E — Deterministic Falsification Before Model Inference

Date: 2026-09-20

## Goal

Before running the ordinary-model benchmark authorized by Wave 7D, attempt to falsify the need for model inference by encoding the four surviving React 18 migrations as narrow deterministic transforms.

## Pinned target-defined case

- repository: h2oai/wave
- commit: fff04af6d92584d75ce7e946d2c449230461dfcb
- explicit target: react-dom=18
- workflow run: 35486650503
- artifact: 10598540319

## Deterministic transform boundary

The transform accepts only:

1. document.getElementById(...) entry roots;
2. one-shot appendChild(...) containers;
3. reusable named containers created by document.createElement(...), with one persistent createRoot instance.

Unknown root-lifetime shapes are blocked.

## Real results

| Target | Changed lines | Proposal | Static differential verification | Finding removed | New findings |
|---|---:|---|---|---|---:|
| ide/src/index.tsx | 9 | PROPOSED | PASS-to-REVIEW (project tests intentionally not executed) | true | 0 |
| ui/src/index.tsx | 4 | PROPOSED | PASS-to-REVIEW (project tests intentionally not executed) | true | 0 |
| ui/src/markdown.tsx | 4 | PROPOSED | PASS-to-REVIEW (project tests intentionally not executed) | true | 0 |
| ui/src/plot.tsx | 6 | PROPOSED | PASS-to-REVIEW (project tests intentionally not executed) | true | 0 |

Totals:

- React slices: 4
- deterministic proposals: 4 / 4
- static verification passes: 4 / 4
- semantic escalations: 0
- eligible model tasks after deterministic pass: 0
- model inference run: false
- project code executed: false

## Corpus result

Across the five-repository semantic corpus:

- repositories analyzed: 5 / 5
- source files: 1,040
- lines: 980,491
- compatibility slices: 7
- deterministic proposals: 4
- semantic escalations: 0
- safety blockers: 3
- architecture slices: 45
- escalation tiers: 1 DETERMINISTIC, 1 ARCHITECTURE_REVIEW, 3 SAFETY_FIRST
- B300 decision: NOT_JUSTIFIED_BY_CURRENT_EVIDENCE

The three non-React compatibility cases remain blocked by missing tests/CI rather than model capability.

## Decision

Ordinary-model benchmark for the four Wave 7D React tasks: **cancelled as unnecessary**.

Long-context benchmark: **not justified**.

B300 benchmark/rental: **not justified**.

No external model API was invoked and no GPU was rented.

## Rule established

**semantic-looking != model-required**

The sequence is now:

evidence → explicit target → safety prerequisites → deterministic-transform discovery → context minimization → model evaluation only if semantic work still survives.
