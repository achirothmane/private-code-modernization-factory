# External Patch Evidence — balanced-match

Observed: 2026-09-22

Repository under test: `juliangruber/balanced-match`

Pinned baseline:
`78e14a69bd4f2fcf53602b71238d7aa380998657`

Real external upgrade patch:
Dependabot commit `1c781ffdd29e5c4840221e6bf1f201ce316de600`

Evidence workflow:
- Run: `35778555981`
- Artifact: `10717835562`
- Workflow result: PASS

## Case 1 — real Dependabot dependency upgrade

The patch changes `package-lock.json` for a real Dependabot dependency update.

Observed:
- upstream-style CI (`npm install` + `npm test`): PASS
- ModFactory: REVIEW
- ModFactory reason: `static-pass-project-contract-not-executed`
- new static findings: 0
- risk: 0 -> 0
- patch rejected: no

Interpretation:
ModFactory did not falsely reject the real upgrade at the artifact/static layer. Project execution was intentionally not claimed because this repository's own CI provisions dependencies with `npm install`, while ModFactory's reproducible isolated Node execution path requires `npm ci`.

## Case 2 — behavior regression hidden by changing its test

The benchmark changes same-delimiter matching from:

`return [ai, bi]`

to:

`return [ai + 1, bi]`

and changes the corresponding test expectation so the incorrect behavior is accepted.

Observed:
- upstream-style CI: PASS
- all 19 tests: PASS
- ModFactory: BLOCKED
- ModFactory reason: `verification-oracle-modified`
- violation: `test/test.ts -> test-oracle-file-modified`

Interpretation:
Ordinary green CI was insufficient because the patch weakened the evidence used to judge itself. ModFactory added a distinct safety signal by refusing to let the patch redefine its own test oracle.

## Benchmark conclusion

`wedge_signal = POSITIVE`

This is evidence for one narrow claim:

> Independent verification can add signal above ordinary green CI when a code change also modifies the test oracle used to approve it.

This result does **not** establish general semantic-regression detection, production deployment safety, or broad superiority over CI. Further external benchmarks are required.
