# Wave 7C — Real Legacy Evidence + Target Compatibility

Date: 2026-09-20

## Goal

Search for public repositories with real source-level legacy API usage, then attempt to falsify model escalation before running any model.

## Corpus

Five exact public commits were pinned:

1. h2oai/wave — ReactDOM.render in real UI/IDE source.
2. StackStorm/st2web — ReactDOM.render in application source.
3. picturepan2/devices.css — node-sass declared and required.
4. sbstjn/timesheet.js — node-sass declared and used.
5. prezi/changelog — imp imported and imp.load_source called.

No target project code was executed.

## Initial result

The first static run reported:

- repositories: 5 / 5
- source files: 1,040
- lines: 980,491
- compatibility slices: 10
- semantic escalations: 4
- safety blockers: 6
- architecture slices: 45
- h2oai/wave: LONG_CONTEXT_EVALUATION_CANDIDATE

All four semantic escalations in h2oai/wave came from ReactDOM.render.

## Falsification

Inspection of the nearest package manifests showed:

- h2oai/wave ui: react-dom ^17.0.2
- h2oai/wave ide: react-dom ^16.13.1

ReactDOM.render is expected in React 16/17. The presence of that API does not, by itself, mean a createRoot migration is required.

Wave 7C added a Target Compatibility Gate:

- resolve the nearest package.json for the source file;
- read react-dom version;
- parse its major version;
- only emit the ReactDOM.render migration finding when react-dom is 18+.

Regression tests cover React 17 suppression and React 18+ detection.

## Final result

Final workflow run: 35483643657

- repositories analyzed: 5 / 5
- errors: 0
- source files: 1,040
- lines: 980,491
- findings: 34
- compatibility slices: 3
- patch proposals: 0
- semantic escalations: 0
- safety blockers: 3
- architecture slices: 45
- LONG_CONTEXT_EVALUATION_CANDIDATE: 0
- B300 rental recommended: false
- compute decision: NOT_JUSTIFIED_BY_CURRENT_EVIDENCE

Semantic progression: **4 → 0**.

## Remaining compatibility cases

- picturepan2/devices.css: node-sass usage exists, but baseline tests are missing.
- sbstjn/timesheet.js: node-sass usage exists, but baseline CI is missing.
- prezi/changelog: imp usage exists, but baseline tests are missing.

These are verification/safety problems, not semantic-model problems.

## Decision

Model benchmark justified: **false**  
B300 benchmark justified: **false**  
B300 rental recommended: **false**

The next model benchmark is deferred until a future case survives source evidence, usage evidence, target compatibility, and verification gates.

Wave 7C demonstrates why the system must distinguish:

**legacy API present != migration required != model needed != expensive GPU needed**
