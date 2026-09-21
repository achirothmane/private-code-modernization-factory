from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from .model_bench import (
    _git_apply,
    inspect_unified_diff,
    validate_repository_baseline,
    validate_request_integrity,
    validate_response_envelope,
)
from .model_eval import _npm_usage_sites
from .scanner import scan_repository
from .verification import _copy_repository, _finding_key


IMPORT_PATTERNS = (
    re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""from\s+['"]([^'"]+)['"]"""),
    re.compile(r"""import\s*\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""import\s+['"]([^'"]+)['"]"""),
)


def _task_from_plan(plan: dict[str, object], task_id: str) -> dict[str, object]:
    tasks = plan.get("tasks", [])
    if not isinstance(tasks, list):
        raise ValueError("plan.tasks must be a list")
    for item in tasks:
        if isinstance(item, dict) and str(item.get("task_id")) == task_id:
            return item
    raise ValueError(f"Task {task_id!r} was not found in the plan")


def _legacy_package(task: dict[str, object]) -> str | None:
    recipe = task.get("recipe")
    if not isinstance(recipe, dict):
        return None
    recipe_id = str(recipe.get("id", ""))
    if recipe_id == "npm-request-to-modern-http":
        return "request"
    if recipe_id == "node-sass-to-sass":
        return "node-sass"
    return None


def _external_packages(text: str) -> set[str]:
    packages: set[str] = set()
    for pattern in IMPORT_PATTERNS:
        for match in pattern.finditer(text):
            spec = match.group(1)
            if spec.startswith((".", "/")):
                continue
            if spec.startswith("@"):
                parts = spec.split("/")
                if len(parts) >= 2:
                    packages.add("/".join(parts[:2]))
            else:
                packages.add(spec.split("/", 1)[0])
    return packages


def _context_by_path(task: dict[str, object]) -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    context_files = task.get("context_files", [])
    if not isinstance(context_files, list):
        return result
    for item in context_files:
        if isinstance(item, dict) and isinstance(item.get("path"), str):
            result[str(item["path"])] = dict(item)
    return result


def build_usage_site_decomposition(
    plan: dict[str, object],
    task_id: str,
) -> dict[str, object]:
    parent = _task_from_plan(plan, task_id)
    package = _legacy_package(parent)
    if package is None:
        raise ValueError("Task recipe is not supported for usage-site decomposition")

    context = _context_by_path(parent)
    manifest = next(
        (
            item for item in context.values()
            if item.get("role") in {"target", "manifest"}
            and str(item.get("path", "")).endswith("package.json")
        ),
        None,
    )
    if manifest is None:
        raise ValueError("A package.json context file is required for npm decomposition")

    usage_sites = sorted(
        (
            item for item in context.values()
            if item.get("role") == "usage-site"
        ),
        key=lambda item: str(item.get("path", "")),
    )
    if not usage_sites:
        raise ValueError("No usage-site context files were found")

    tasks: list[dict[str, object]] = []
    for site in usage_sites:
        path = str(site["path"])
        suffix = hashlib.sha1(path.encode("utf-8")).hexdigest()[:10]
        tasks.append({
            "task_id": f"{task_id}-site-{suffix}",
            "parent_task_id": task_id,
            "task_kind": "usage-site",
            "slice_id": parent.get("slice_id"),
            "target": path,
            "title": parent.get("title"),
            "objective": (
                f"Migrate only the {package!r} usage in {path}. "
                "Do not modify package.json or any other file."
            ),
            "legacy_package": package,
            "target_profile": parent.get("target_profile", {}),
            "recipe": parent.get("recipe"),
            "allowed_changes": [path],
            "preconditions": parent.get("preconditions", []),
            "acceptance_criteria": [
                "patch applies cleanly",
                f"{package} static import/require usage is absent from this file after the patch",
                "no files outside the single target path are modified",
                "no new repository findings are introduced",
                "any newly required external package is reported for later manifest finalization",
            ],
            "rollback_triggers": parent.get("rollback_triggers", []),
            "baseline_commands": parent.get("baseline_commands", []),
            "context_files": [
                {**manifest, "role": "manifest-readonly"},
                dict(site),
            ],
            "context_characters": int(manifest.get("characters", 0)) + int(site.get("characters", 0)),
            "context_band": "small",
            "requires_full_repository_context": False,
            "model_instruction": (
                f"Modify ONLY {path}. Migrate the deprecated {package} usage in this file while preserving "
                "the observable HTTP behavior used by these tests. package.json is read-only context and must "
                "not be edited. Return a complete unified diff with ---/+++ file headers for exactly this file. "
                "Do not claim changes that are not present in the diff."
            ),
            "evaluation_dimensions": [
                "patch-applies-cleanly",
                "single-file-scope-only",
                "local-legacy-usage-removed",
                "no-new-findings",
                "dependency-requirements-explicitly-observable",
            ],
        })

    return {
        "schema_version": 1,
        "plan_kind": "usage-site-decomposition",
        "repository": plan.get("repository"),
        "parent_task_id": task_id,
        "legacy_package": package,
        "manifest_path": manifest["path"],
        "usage_sites": [str(item["path"]) for item in usage_sites],
        "eligible_tasks": len(tasks),
        "blocked_tasks": 0,
        "compute_policy": {
            "invoke_model": False,
            "rent_b300": False,
            "next_gate": "RUN_FILE_SCOPED_ORDINARY_MODEL_BENCHMARK",
            "rule": (
                "Validate each file-scoped patch independently. Aggregate only accepted partial patches. "
                "Do not finalize the manifest or claim full migration until every usage site is covered."
            ),
        },
        "tasks": tasks,
        "blocked": [],
    }


def write_usage_site_decomposition(
    plan: dict[str, object],
    out_dir: str | Path,
) -> tuple[Path, Path, Path]:
    out = Path(out_dir) / "decomposition"
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "plan.json"
    jsonl_path = out / "tasks.jsonl"
    md_path = out / "plan.md"
    json_path.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for task in plan.get("tasks", []):
            handle.write(json.dumps(task, ensure_ascii=False) + "\n")

    lines = [
        "# ModFactory Usage-Site Decomposition",
        "",
        f"Parent task: {plan['parent_task_id']}",
        f"Legacy package: {plan['legacy_package']}",
        f"Usage-site tasks: {plan['eligible_tasks']}",
        f"Next gate: {plan['compute_policy']['next_gate']}",
        "",
        "| Task | Target | Context chars | Allowed files |",
        "|---|---|---:|---:|",
    ]
    for task in plan.get("tasks", []):
        lines.append(
            f"| {task['task_id']} | {task['target']} | {task['context_characters']} | "
            f"{len(task['allowed_changes'])} |"
        )
    lines.extend([
        "",
        "package.json is context-only during usage-site migration.",
        "No model was invoked and no project code was executed.",
        "",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, jsonl_path, md_path


def _target_still_uses_package(root: Path, target: str, package: str) -> bool:
    return target in {
        path.relative_to(root).as_posix()
        for path in _npm_usage_sites(root, package)
    }


def score_usage_site_response(
    repository: str | Path,
    request: dict[str, object],
    response: dict[str, object],
) -> dict[str, object]:
    root = Path(repository).resolve()
    request_valid, request_errors = validate_request_integrity(request)
    envelope_valid, envelope_errors, metrics = validate_response_envelope(request, response)
    task = request.get("task")
    if not isinstance(task, dict):
        task = {}

    base: dict[str, object] = {
        "schema_version": 1,
        "score_kind": "usage-site-partial",
        "benchmark_id": request.get("benchmark_id"),
        "task_id": request.get("task_id"),
        "parent_task_id": task.get("parent_task_id"),
        "provider": request.get("provider"),
        "model": request.get("model"),
        "metrics": metrics,
        "status": "FAIL",
        "reason": "request-invalid",
        "gates": {},
        "original_repository_modified": False,
        "project_code_executed": False,
    }
    if not request_valid:
        return {**base, "reason": "request-integrity-invalid", "request_errors": request_errors}
    if not envelope_valid:
        return {**base, "reason": "response-envelope-invalid", "envelope_errors": envelope_errors}
    if task.get("task_kind") != "usage-site":
        return {**base, "reason": "not-a-usage-site-task"}

    baseline_valid, baseline_mismatches = validate_repository_baseline(root, request)
    if not baseline_valid:
        return {
            **base,
            "reason": "repository-baseline-mismatch",
            "baseline_mismatches": baseline_mismatches,
        }

    diff = str(response.get("unified_diff", ""))
    diff_info = inspect_unified_diff(diff)
    target = str(task.get("target", ""))
    changed_files = list(diff_info.get("changed_files", []))
    exact_scope = bool(diff_info.get("valid")) and changed_files == [target]
    gates: dict[str, object] = {
        "response_envelope_valid": True,
        "diff_structure_valid": bool(diff_info.get("valid")),
        "exact_single_file_scope": exact_scope,
        "changed_files": changed_files,
        "allowed_files": [target],
    }
    base["gates"] = gates
    if not diff_info.get("valid"):
        return {
            **base,
            "reason": "unified-diff-invalid",
            "diff_errors": diff_info.get("errors", []),
        }
    if not exact_scope:
        return {**base, "reason": "single-file-scope-violation"}

    package = str(task.get("legacy_package", ""))
    if not package:
        return {**base, "reason": "legacy-package-missing"}

    with TemporaryDirectory(prefix="modfactory-site-before-") as before_td, TemporaryDirectory(prefix="modfactory-site-after-") as after_td:
        before_root = Path(before_td)
        after_root = Path(after_td)
        _copy_repository(root, before_root)
        _copy_repository(root, after_root)

        before_target = before_root / target
        after_target = after_root / target
        before_text = before_target.read_text(encoding="utf-8", errors="ignore")

        check_ok, check_detail = _git_apply(after_root, diff, check_only=True)
        gates["patch_applies_cleanly"] = check_ok
        if not check_ok:
            return {
                **base,
                "reason": "patch-does-not-apply-cleanly",
                "patch_detail": check_detail,
            }
        apply_ok, apply_detail = _git_apply(after_root, diff, check_only=False)
        if not apply_ok:
            return {
                **base,
                "reason": "patch-application-failed",
                "patch_detail": apply_detail,
            }

        after_text = after_target.read_text(encoding="utf-8", errors="ignore")
        used_before = _target_still_uses_package(before_root, target, package)
        used_after = _target_still_uses_package(after_root, target, package)
        gates["legacy_usage_present_before"] = used_before
        gates["local_legacy_usage_removed"] = used_before and not used_after

        before_snapshot = scan_repository(before_root)
        after_snapshot = scan_repository(after_root)
        before_keys = {_finding_key(item) for item in before_snapshot.findings}
        after_keys = {_finding_key(item) for item in after_snapshot.findings}
        new_findings = sorted(after_keys - before_keys)
        gates["no_new_findings"] = not new_findings
        gates["risk_non_increasing"] = after_snapshot.risk_score <= before_snapshot.risk_score

        before_packages = _external_packages(before_text)
        after_packages = _external_packages(after_text)
        dependency_requirements = sorted(after_packages - before_packages - {package})

        static_gate_names = (
            "response_envelope_valid",
            "diff_structure_valid",
            "exact_single_file_scope",
            "patch_applies_cleanly",
            "legacy_usage_present_before",
            "local_legacy_usage_removed",
            "no_new_findings",
            "risk_non_increasing",
        )
        passed = sum(1 for key in static_gate_names if gates.get(key) is True)
        base["dependency_requirements"] = dependency_requirements
        base["new_findings"] = [
            {"category": c, "path": p, "message": m}
            for c, p, m in new_findings
        ]
        base["static_quality"] = {
            "gates_passed": passed,
            "gates_known": len(static_gate_names),
            "ratio": round(passed / len(static_gate_names), 4),
        }
        if passed != len(static_gate_names):
            return {**base, "reason": "partial-static-regression"}

        return {
            **base,
            "status": "REVIEW",
            "reason": "partial-static-pass-manifest-not-finalized",
            "verification_level": "file-scoped-static",
            "accepted_diff": diff,
        }


def aggregate_usage_site_responses(
    repository: str | Path,
    decomposition_plan: dict[str, object],
    requests: list[dict[str, object]],
    responses: list[dict[str, object]],
) -> dict[str, object]:
    if len(requests) != len(responses):
        raise ValueError("requests and responses must have the same length")

    expected = {
        str(task.get("task_id")): str(task.get("target"))
        for task in decomposition_plan.get("tasks", [])
        if isinstance(task, dict)
    }
    scores: list[dict[str, object]] = []
    accepted_diffs: list[str] = []
    dependency_requirements: set[str] = set()
    covered_targets: set[str] = set()

    for request, response in zip(requests, responses):
        score = score_usage_site_response(repository, request, response)
        scores.append(score)
        task_id = str(score.get("task_id"))
        if score.get("status") != "REVIEW" or task_id not in expected:
            continue
        target = expected[task_id]
        if target in covered_targets:
            continue
        covered_targets.add(target)
        accepted_diffs.append(str(score.get("accepted_diff", "")))
        dependency_requirements.update(
            str(item) for item in score.get("dependency_requirements", [])
        )

    missing_targets = sorted(set(expected.values()) - covered_targets)
    root = Path(repository).resolve()
    combined = "\n".join(diff.rstrip() for diff in accepted_diffs if diff).strip()
    remaining_usage: list[str] = []

    if not missing_targets and combined:
        with TemporaryDirectory(prefix="modfactory-site-aggregate-") as td:
            temp_root = Path(td)
            _copy_repository(root, temp_root)
            check_ok, detail = _git_apply(temp_root, combined + "\n", check_only=True)
            if not check_ok:
                return {
                    "schema_version": 1,
                    "status": "BLOCKED",
                    "reason": "aggregate-patch-does-not-apply-cleanly",
                    "patch_detail": detail,
                    "scores": scores,
                }
            apply_ok, detail = _git_apply(temp_root, combined + "\n", check_only=False)
            if not apply_ok:
                return {
                    "schema_version": 1,
                    "status": "BLOCKED",
                    "reason": "aggregate-patch-application-failed",
                    "patch_detail": detail,
                    "scores": scores,
                }
            package = str(decomposition_plan.get("legacy_package", ""))
            remaining_usage = [
                path.relative_to(temp_root).as_posix()
                for path in _npm_usage_sites(temp_root, package)
            ]

    ready = not missing_targets and not remaining_usage and bool(combined)
    return {
        "schema_version": 1,
        "status": "READY_FOR_MANIFEST_FINALIZATION" if ready else "PARTIAL",
        "reason": (
            "all-usage-sites-statically-validated"
            if ready
            else "usage-sites-remain-or-partials-failed"
        ),
        "parent_task_id": decomposition_plan.get("parent_task_id"),
        "expected_usage_sites": len(expected),
        "accepted_usage_sites": len(covered_targets),
        "missing_targets": missing_targets,
        "remaining_legacy_usage": remaining_usage,
        "dependency_requirements": sorted(dependency_requirements),
        "aggregate_diff": combined + ("\n" if combined else ""),
        "scores": scores,
        "manifest_finalized": False,
        "project_code_executed": False,
    }


def write_decomposition_score(score: dict[str, object], out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir) / "decomposition-score"
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "score.json"
    md_path = out / "score.md"
    json_path.write_text(json.dumps(score, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "# ModFactory Usage-Site Partial Score",
        "",
        f"Status: **{score.get('status')}**",
        f"Reason: {score.get('reason')}",
        f"Task: {score.get('task_id')}",
        f"Dependencies observed: {score.get('dependency_requirements', [])}",
        "",
        "This score validates only one usage-site patch. It does not finalize package.json or claim full migration.",
        "",
    ]
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, md_path
