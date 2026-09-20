from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from .commands import discover_commands
from .models import RepoSnapshot
from .patches import _apply_recipe, build_patch_proposal
from .scanner import scan_repository


UNSAFE_COMMAND_TOKENS = ("|", ";", "&", ">", "<", "\x60", "$(", "\n", "\r")


def _finding_key(item: object) -> tuple[str, str, str]:
    return (
        str(getattr(item, "category", "")),
        str(getattr(item, "path", "")),
        str(getattr(item, "message", "")),
    )


def _copy_repository(source: Path, destination: Path) -> None:
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            ".git", ".hg", ".svn", ".modfactory", ".pytest_cache",
            ".mypy_cache", "__pycache__", ".venv", "venv", "node_modules",
            "dist", "build",
        ),
    )


def _materialize_after_tree(
    root: Path,
    destination: Path,
    proposal: dict[str, object],
) -> tuple[bool, str | None]:
    _copy_repository(root, destination)
    changed_files = proposal.get("changed_files", [])
    if not isinstance(changed_files, list) or len(changed_files) != 1:
        return False, "proposal-must-change-exactly-one-file"
    target = str(changed_files[0])
    recipe_id = str(proposal.get("recipe_id", ""))
    target_path = destination / target
    try:
        before = target_path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        return False, f"target-read-failed: {exc}"

    after, blocked_reason = _apply_recipe(recipe_id, before, target)
    if blocked_reason:
        return False, f"transform-blocked: {blocked_reason}"
    if after == before:
        return False, "transform-produced-no-change"

    target_path.write_text(after, encoding="utf-8")
    return True, None


def _safe_argv(command: str) -> tuple[list[str] | None, str | None]:
    if any(token in command for token in UNSAFE_COMMAND_TOKENS):
        return None, "shell-metacharacter-blocked"
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        return None, f"command-parse-failed: {exc}"
    if not argv:
        return None, "empty-command"
    return argv, None


def _run_command(command: str, cwd: Path, timeout_seconds: int) -> dict[str, object]:
    argv, blocked_reason = _safe_argv(command)
    if blocked_reason:
        return {
            "command": command,
            "status": "BLOCKED",
            "reason": blocked_reason,
            "returncode": None,
            "duration_seconds": 0.0,
        }

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "command": command,
            "status": "TIMEOUT",
            "reason": "timeout",
            "returncode": None,
            "duration_seconds": round(time.perf_counter() - started, 4),
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
        }
    except OSError as exc:
        return {
            "command": command,
            "status": "ERROR",
            "reason": str(exc),
            "returncode": None,
            "duration_seconds": round(time.perf_counter() - started, 4),
        }

    stdout = completed.stdout or ""
    stderr = completed.stderr or ""
    return {
        "command": command,
        "argv": argv,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "returncode": completed.returncode,
        "duration_seconds": round(time.perf_counter() - started, 4),
        "stdout_sha256": hashlib.sha256(stdout.encode("utf-8")).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr.encode("utf-8")).hexdigest(),
        "stdout_tail": stdout[-4000:],
        "stderr_tail": stderr[-4000:],
    }


def _run_test_commands(
    root: Path,
    snapshot: RepoSnapshot,
    timeout_seconds: int,
    limit: int = 3,
) -> list[dict[str, object]]:
    commands = [
        item for item in discover_commands(root, snapshot)
        if item.get("kind") == "test"
    ][:limit]
    return [
        _run_command(str(item["command"]), root, timeout_seconds)
        for item in commands
    ]


def build_differential_verification(
    root: str | Path,
    snapshot: RepoSnapshot,
    slice_id: str,
    diff_budget: int = 80,
    allow_project_code: bool = False,
    timeout_seconds: int = 120,
) -> dict[str, object]:
    root_path = Path(root).resolve()
    proposal = build_patch_proposal(
        root_path,
        snapshot,
        slice_id,
        diff_budget=diff_budget,
    )

    base: dict[str, object] = {
        "slice_id": slice_id,
        "status": "BLOCKED",
        "reason": "proposal-not-verifiable",
        "verification_level": "none",
        "allow_project_code": allow_project_code,
        "original_repository_modified": False,
        "proposal": proposal,
        "static_checks": {},
        "project_tests": {
            "executed": False,
            "before": [],
            "after": [],
        },
        "deployment_admissible": False,
        "requires_human_review": True,
    }

    if proposal.get("status") != "PROPOSED":
        return {
            **base,
            "reason": f"proposal-{proposal.get('reason', 'blocked')}",
        }

    changed_files = proposal.get("changed_files", [])
    if not isinstance(changed_files, list) or len(changed_files) != 1:
        return {**base, "reason": "proposal-file-cardinality-invalid"}
    target = str(changed_files[0])
    selected = proposal.get("slice")
    if not isinstance(selected, dict):
        return {**base, "reason": "proposal-slice-missing"}
    target_message = str(selected.get("title", ""))

    with TemporaryDirectory(prefix="modfactory-before-") as before_td, TemporaryDirectory(prefix="modfactory-after-") as after_td:
        before_root = Path(before_td)
        after_root = Path(after_td)
        _copy_repository(root_path, before_root)
        ok, materialize_error = _materialize_after_tree(root_path, after_root, proposal)
        if not ok:
            return {**base, "reason": "after-tree-materialization-failed", "detail": materialize_error}

        before_snapshot = scan_repository(before_root, targets=snapshot.target_profile)
        after_snapshot = scan_repository(after_root, targets=snapshot.target_profile)

        before_keys = {_finding_key(item) for item in before_snapshot.findings}
        after_keys = {_finding_key(item) for item in after_snapshot.findings}
        target_key = next(
            (
                key for key in before_keys
                if key[1] == target and key[2] == target_message
            ),
            None,
        )
        new_findings = sorted(after_keys - before_keys)
        removed_findings = sorted(before_keys - after_keys)

        static_checks = {
            "target_finding_present_before": target_key is not None,
            "target_finding_removed_after": target_key is not None and target_key not in after_keys,
            "new_findings": [
                {"category": c, "path": p, "message": m}
                for c, p, m in new_findings
            ],
            "removed_findings": [
                {"category": c, "path": p, "message": m}
                for c, p, m in removed_findings
            ],
            "risk_before": before_snapshot.risk_score,
            "risk_after": after_snapshot.risk_score,
            "risk_non_increasing": after_snapshot.risk_score <= before_snapshot.risk_score,
            "source_file_count_before": len(before_snapshot.source_files),
            "source_file_count_after": len(after_snapshot.source_files),
            "source_file_count_stable": len(before_snapshot.source_files) == len(after_snapshot.source_files),
            "dependency_cycles_before": len(before_snapshot.architecture.get("cycles", [])),
            "dependency_cycles_after": len(after_snapshot.architecture.get("cycles", [])),
            "no_new_dependency_cycles": (
                len(after_snapshot.architecture.get("cycles", []))
                <= len(before_snapshot.architecture.get("cycles", []))
            ),
        }

        static_pass = bool(
            static_checks["target_finding_present_before"]
            and static_checks["target_finding_removed_after"]
            and not static_checks["new_findings"]
            and static_checks["risk_non_increasing"]
            and static_checks["source_file_count_stable"]
            and static_checks["no_new_dependency_cycles"]
        )

        result: dict[str, object] = {
            **base,
            "static_checks": static_checks,
        }

        if not static_pass:
            return {
                **result,
                "status": "FAIL",
                "reason": "static-differential-regression",
                "verification_level": "static",
            }

        if not allow_project_code:
            return {
                **result,
                "status": "REVIEW",
                "reason": "static-pass-project-tests-not-executed",
                "verification_level": "static",
                "deployment_admissible": False,
            }

        before_tests = _run_test_commands(
            before_root,
            before_snapshot,
            timeout_seconds=timeout_seconds,
        )
        after_tests = _run_test_commands(
            after_root,
            after_snapshot,
            timeout_seconds=timeout_seconds,
        )
        project_tests = {
            "executed": True,
            "before": before_tests,
            "after": after_tests,
        }
        result["project_tests"] = project_tests

        if not before_tests:
            return {
                **result,
                "status": "BLOCKED",
                "reason": "no-test-command-executed",
                "verification_level": "static",
            }

        if any(item.get("status") != "PASS" for item in before_tests):
            return {
                **result,
                "status": "BLOCKED",
                "reason": "baseline-failed-before",
                "verification_level": "tests-before",
            }

        if len(after_tests) != len(before_tests):
            return {
                **result,
                "status": "FAIL",
                "reason": "test-command-set-changed",
                "verification_level": "tests",
            }

        if any(item.get("status") != "PASS" for item in after_tests):
            return {
                **result,
                "status": "FAIL",
                "reason": "regression-after-patch",
                "verification_level": "tests",
            }

        performance = []
        for before_item, after_item in zip(before_tests, after_tests):
            before_seconds = float(before_item.get("duration_seconds", 0.0))
            after_seconds = float(after_item.get("duration_seconds", 0.0))
            ratio = None
            if before_seconds > 0:
                ratio = round(after_seconds / before_seconds, 3)
            performance.append({
                "command": before_item.get("command"),
                "before_seconds": before_seconds,
                "after_seconds": after_seconds,
                "ratio": ratio,
                "gating": False,
            })

        return {
            **result,
            "status": "PASS",
            "reason": "static-and-project-tests-pass",
            "verification_level": "tests",
            "performance_observation": performance,
            "deployment_admissible": True,
        }


def render_verification_markdown(result: dict[str, object]) -> str:
    static = result.get("static_checks", {})
    project = result.get("project_tests", {})
    lines = [
        "# Differential Verification Report",
        "",
        f"**Status:** {result.get('status', 'UNKNOWN')}",
        f"**Reason:** {result.get('reason', 'unknown')}",
        f"**Verification level:** {result.get('verification_level', 'none')}",
        f"**Project code executed:** {result.get('allow_project_code', False)}",
        f"**Deployment admissible:** {result.get('deployment_admissible', False)}",
        "",
        "## Static before/after evidence",
        "",
    ]
    if isinstance(static, dict) and static:
        lines.extend([
            f"- Target finding present before: {static.get('target_finding_present_before')}",
            f"- Target finding removed after: {static.get('target_finding_removed_after')}",
            f"- Risk: {static.get('risk_before')} -> {static.get('risk_after')}",
            f"- New findings: {len(static.get('new_findings', []))}",
            f"- Source file count stable: {static.get('source_file_count_stable')}",
            f"- No new dependency cycles: {static.get('no_new_dependency_cycles')}",
            "",
        ])
    else:
        lines.extend(["Static verification did not run.", ""])

    lines.extend(["## Project test evidence", ""])
    if isinstance(project, dict) and project.get("executed"):
        for phase in ("before", "after"):
            lines.append(f"### {phase.title()}")
            for item in project.get(phase, []):
                lines.append(
                    f"- {item.get('command')} -> {item.get('status')} "
                    f"({item.get('duration_seconds')}s)"
                )
            lines.append("")
    else:
        lines.extend([
            "Project commands were not executed. Re-run with explicit opt-in inside a trusted environment to obtain behavioral test evidence.",
            "",
        ])

    lines.extend([
        "## Authority boundary",
        "",
        "Verification does not merge, deploy, or modify the original repository. PASS means the configured evidence gates passed; human review remains required.",
        "",
    ])
    return "\n".join(lines)


def write_verification(result: dict[str, object], out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir) / "verification"
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "verification.json"
    md_path = out / "verification.md"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    md_path.write_text(render_verification_markdown(result), encoding="utf-8")
    return json_path, md_path
