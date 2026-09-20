from __future__ import annotations

import hashlib
from .models import RepoSnapshot
from .recipes import recipe_for_finding


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
        recipe = recipe_for_finding(finding)
        recipe_payload = recipe.to_dict() if recipe else None
        slices.append({
            "id": _slice_id("compatibility", finding.path, finding.message),
            "kind": "compatibility",
            "priority": 10,
            "target": finding.path,
            "title": finding.message,
            "evidence": finding.evidence,
            "objective": finding.remediation,
            "recipe": recipe_payload,
            "preconditions": list(recipe.preconditions) if recipe else ["Relevant baseline tests are green", "CI baseline is green"],
            "allowed_changes": [finding.path, "directly related tests"],
            "verification": list(recipe.verification) if recipe else ["baseline tests remain green", "obsolete pattern no longer detected", "no unrelated file changes"],
            "rollback_triggers": list(recipe.rollback_triggers) if recipe else ["Any baseline regression"],
            "merge_gate": "evidence+human-review",
        })

    for boundary in snapshot.architecture.get("upgrade_boundaries", []):
        boundary_type = str(boundary.get("type", "architecture"))
        if boundary_type == "dependency-cycle":
            paths = [str(p) for p in boundary.get("paths", [])]
            target = paths[0] if paths else "."
            slices.append({
                "id": _slice_id("architecture", target, "dependency-cycle"),
                "kind": "architecture",
                "priority": 6,
                "target": target,
                "title": "Isolate dependency cycle before broad upgrade",
                "evidence": str(boundary.get("reason", "dependency cycle detected")),
                "preconditions": ["Relevant baseline tests are green"],
                "allowed_changes": paths + ["directly related tests"],
                "verification": ["cycle is removed or explicitly documented as preserved", "no new dependency cycles are introduced"],
                "merge_gate": "evidence+human-review",
            })
        elif boundary_type == "dependency-hub":
            target = str(boundary.get("path", "."))
            slices.append({
                "id": _slice_id("architecture", target, "dependency-hub"),
                "kind": "architecture",
                "priority": 7,
                "target": target,
                "title": "Protect dependency hub before migration",
                "evidence": str(boundary.get("reason", "dependency hub detected")),
                "preconditions": ["Targeted tests cover callers and callees"],
                "allowed_changes": [target, "directly related tests"],
                "verification": ["callers remain compatible", "fan-in/fan-out delta is explained", "no unrelated file changes"],
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
