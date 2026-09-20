from __future__ import annotations

from collections import Counter

from .models import RepoSnapshot


def build_plan(snapshot: RepoSnapshot) -> list[dict[str, object]]:
    steps: list[dict[str, object]] = []

    def add(phase: int, title: str, objective: str, exit_criteria: list[str], risk_reduced: list[str]):
        steps.append({
            "phase": phase,
            "title": title,
            "objective": objective,
            "exit_criteria": exit_criteria,
            "risk_reduced": risk_reduced,
        })

    categories = Counter(f.category for f in snapshot.findings)

    add(0, "Freeze the baseline",
        "Capture current build/test behavior before changing implementation.",
        ["Current revision recorded", "Build command documented", "Baseline report generated"],
        ["unknown starting state"])

    if categories["verification"] or not snapshot.test_files:
        add(1, "Create characterization tests",
            "Protect current behavior before dependency or framework upgrades.",
            ["Critical paths have tests", "Tests fail when protected behavior is intentionally changed"],
            ["silent regressions", "unsafe automated edits"])
    else:
        add(1, "Validate the existing test safety net",
            "Confirm current tests cover the modules that will change.",
            ["Tests run deterministically", "Coverage gaps for migration targets are identified"],
            ["false confidence"])

    if categories["delivery"] or not snapshot.ci_files:
        add(2, "Establish CI evidence",
            "Run verification automatically on every modernization change.",
            ["CI runs on pull requests", "Failing tests block merge", "Artifacts/logs are retained"],
            ["unverified merges"])

    if categories["legacy-api"]:
        add(3, "Remove obsolete APIs first",
            "Eliminate known compatibility blockers in isolated patches.",
            ["Each blocker has its own patch", "Tests remain green after every blocker removal"],
            ["runtime incompatibility", "upgrade blockers"])

    add(4, "Upgrade in small dependency/framework slices",
        "Move one compatibility boundary at a time rather than rewriting the system.",
        ["Each slice is independently reviewable", "Rollback is possible per slice", "CI is green"],
        ["large blast radius", "hard-to-localize regressions"])

    add(5, "Run regression and behavior comparison",
        "Compare post-migration behavior against the frozen baseline.",
        ["No unexplained behavior deltas", "Performance/error deltas are documented"],
        ["behavior drift"])

    add(6, "Produce release evidence",
        "Package the proof required for a human to approve deployment.",
        ["Change inventory complete", "Known risks documented", "Rollback procedure tested"],
        ["opaque AI-generated changes"])

    return steps
