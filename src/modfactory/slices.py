from __future__ import annotations

import hashlib
from .models import RepoSnapshot


def _slice_id(kind: str, path: str, message: str) -> str:
    raw = f"{kind}|{path}|{message}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:10]


def build_migration_slices(snapshot: RepoSnapshot) -> list[dict[str, object]]:
    slices: list[dict[str, object]] = []

    if not snapshot.test_files and snapshot.source_files:
        slices.append({
            "id": _slice_id("safety", ".", "characterization-tests"),
            "kind": "safety",
            "priority": 0,
            "target": ".",
            "title": "Create characterization tests before code migration",
            "preconditions": ["Baseline behavior can be executed or observed"],
            "allowed_changes": ["tests only", "test fixtures", "test configuration"],
            "verification": ["new tests pass on baseline", "tests fail when protected behavior is deliberately broken"],
            "merge_gate": "human-review",
        })

    if not snapshot.ci_files and snapshot.source_files:
        slices.append({
            "id": _slice_id("safety", ".github/workflows", "ci-baseline"),
            "kind": "safety",
            "priority": 1,
            "target": ".github/workflows",
            "title": "Establish CI verification baseline",
            "preconditions": ["Test/build command is known"],
            "allowed_changes": ["CI workflow files only"],
            "verification": ["CI runs on pull requests", "intentional failing test makes CI fail"],
            "merge_gate": "human-review",
        })

    for finding in snapshot.findings:
        if finding.category != "legacy-api":
            continue
        slices.append({
            "id": _slice_id("compatibility", finding.path, finding.message),
            "kind": "compatibility",
            "priority": 10,
            "target": finding.path,
            "title": finding.message,
            "evidence": finding.evidence,
            "objective": finding.remediation,
            "preconditions": ["Relevant baseline tests are green", "CI baseline is green"],
            "allowed_changes": [finding.path, "directly related tests"],
            "verification": ["baseline tests remain green", "obsolete pattern no longer detected", "no unrelated file changes"],
            "merge_gate": "evidence+human-review",
        })

    for finding in snapshot.findings:
        if finding.category == "ownership":
            slices.append({
                "id": _slice_id("review", finding.path, finding.message),
                "kind": "review",
                "priority": 5,
                "target": finding.path,
                "title": "Add reviewer coverage for ownership hotspot",
                "evidence": finding.evidence,
                "preconditions": [],
                "allowed_changes": ["CODEOWNERS", "review policy", "tests around hotspot"],
                "verification": ["reviewer/owner is explicitly identified", "hotspot has targeted tests before migration"],
                "merge_gate": "human-review",
            })

    return sorted(slices, key=lambda x: (int(x["priority"]), str(x["target"]), str(x["id"])))
