from __future__ import annotations

import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from .model_bench import _git_apply, _verification_oracle_violations, inspect_unified_diff
from .scanner import scan_repository
from .verification import (
    _copy_repository,
    _finding_key,
    build_verification_contract,
    provision_verification_environment,
    run_verification_contract,
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _baseline_file_hashes(root: Path, changed_files: list[str]) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for rel in changed_files:
        candidate = (root / rel).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            raise ValueError(f"Patch path escapes repository root: {rel}")
        if not candidate.is_file():
            raise ValueError(f"Patch target does not exist in baseline repository: {rel}")
        evidence.append({
            "path": rel,
            "sha256": _sha256_bytes(candidate.read_bytes()),
        })
    return evidence


def _command_signature(contract: dict[str, object]) -> list[tuple[str, str, str, str]]:
    raw = contract.get("commands", [])
    if not isinstance(raw, list):
        return []
    return [
        (
            str(item.get("kind", "")),
            str(item.get("command", "")),
            str(item.get("source", "")),
            str(item.get("working_directory", ".")),
        )
        for item in raw
        if isinstance(item, dict)
    ]


def _static_repository_compare(
    before_root: Path,
    after_root: Path,
    targets: dict[str, str],
) -> dict[str, object]:
    before = scan_repository(before_root, targets=targets)
    after = scan_repository(after_root, targets=targets)
    before_keys = {_finding_key(item) for item in before.findings}
    after_keys = {_finding_key(item) for item in after.findings}
    new_findings = sorted(after_keys - before_keys)
    removed_findings = sorted(before_keys - after_keys)

    return {
        "new_findings": [
            {"category": category, "path": path, "message": message}
            for category, path, message in new_findings
        ],
        "removed_findings": [
            {"category": category, "path": path, "message": message}
            for category, path, message in removed_findings
        ],
        "risk_before": before.risk_score,
        "risk_after": after.risk_score,
        "risk_non_increasing": after.risk_score <= before.risk_score,
        "source_file_count_before": len(before.source_files),
        "source_file_count_after": len(after.source_files),
        "source_file_count_stable": len(before.source_files) == len(after.source_files),
        "dependency_cycles_before": len(before.architecture.get("cycles", [])),
        "dependency_cycles_after": len(after.architecture.get("cycles", [])),
        "no_new_dependency_cycles": (
            len(after.architecture.get("cycles", []))
            <= len(before.architecture.get("cycles", []))
        ),
    }


def verify_external_patch(
    repository: str | Path,
    patch_path: str | Path,
    *,
    targets: dict[str, str] | None = None,
    producer: str | None = None,
    allow_project_code: bool = False,
    provision_environments: bool = False,
    timeout_seconds: int = 120,
) -> dict[str, object]:
    root = Path(repository).resolve()
    patch_file = Path(patch_path).resolve()
    patch_bytes = patch_file.read_bytes()
    try:
        diff = patch_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Patch artifact must be UTF-8 text") from exc

    target_profile = dict(targets or {})
    patch_sha256 = _sha256_bytes(patch_bytes)
    diff_info = inspect_unified_diff(diff)
    changed_files = [
        str(path) for path in diff_info.get("changed_files", [])
        if isinstance(path, str)
    ]

    base: dict[str, object] = {
        "schema_version": 1,
        "status": "FAIL",
        "reason": "patch-artifact-invalid",
        "verification_level": "none",
        "producer": producer,
        "original_repository_modified": False,
        "patch_artifact": {
            "path": str(patch_file),
            "sha256": patch_sha256,
            "size_bytes": len(patch_bytes),
            "changed_files": changed_files,
        },
        "baseline_files": [],
        "static_checks": {},
        "verification_contract": None,
        "target_contract_evidence": None,
        "project_checks": {"executed": False, "before": [], "after": []},
        "project_tests": {"executed": False, "before": [], "after": []},
        "environment_evidence": {
            "requested": provision_environments,
            "before": None,
            "after": None,
        },
        "deployment_admissible": False,
        "requires_human_review": True,
    }

    if not diff_info.get("valid"):
        return {
            **base,
            "reason": "unified-diff-invalid",
            "diff_errors": diff_info.get("errors", []),
        }
    if not changed_files:
        return {**base, "reason": "patch-has-no-changed-files"}

    try:
        baseline_files = _baseline_file_hashes(root, changed_files)
    except ValueError as exc:
        return {**base, "reason": "baseline-identity-invalid", "detail": str(exc)}
    base["baseline_files"] = baseline_files

    with TemporaryDirectory(prefix="modfactory-external-before-") as before_td, TemporaryDirectory(prefix="modfactory-external-after-") as after_td:
        before_root = Path(before_td)
        after_root = Path(after_td)
        _copy_repository(root, before_root)
        _copy_repository(root, after_root)

        check_ok, check_detail = _git_apply(after_root, diff, check_only=True)
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

        static = _static_repository_compare(before_root, after_root, target_profile)
        base["static_checks"] = static
        static_pass = bool(
            not static["new_findings"]
            and static["risk_non_increasing"]
            and static["source_file_count_stable"]
            and static["no_new_dependency_cycles"]
        )
        if not static_pass:
            return {
                **base,
                "status": "FAIL",
                "reason": "static-differential-regression",
                "verification_level": "static",
            }

        oracle_violations = _verification_oracle_violations(
            before_root,
            after_root,
            set(changed_files),
        )
        if oracle_violations:
            return {
                **base,
                "status": "BLOCKED",
                "reason": "verification-oracle-modified",
                "verification_level": "static",
                "oracle_violations": oracle_violations,
            }

        before_snapshot = scan_repository(before_root, targets=target_profile)
        after_snapshot = scan_repository(after_root, targets=target_profile)
        before_contract = build_verification_contract(
            before_root,
            before_snapshot,
            isolated_dependencies=provision_environments,
        )
        after_contract = build_verification_contract(
            after_root,
            after_snapshot,
            isolated_dependencies=provision_environments,
        )
        base["verification_contract"] = before_contract
        base["target_contract_evidence"] = {
            "contract_sha256": after_contract.get("contract_sha256"),
            "dependency_inputs": after_contract.get("dependency_inputs"),
            "runtime_fingerprint": after_contract.get("runtime_fingerprint"),
            "environment_model": after_contract.get("environment_model"),
        }

        before_signature = _command_signature(before_contract)
        after_signature = _command_signature(after_contract)
        if before_signature != after_signature:
            return {
                **base,
                "status": "BLOCKED",
                "reason": "verification-command-contract-modified",
                "verification_level": "contract",
                "verification_command_contract_before": before_signature,
                "verification_command_contract_after": after_signature,
            }

        if not allow_project_code:
            return {
                **base,
                "status": "REVIEW",
                "reason": "static-pass-project-contract-not-executed",
                "verification_level": "static",
            }

        test_commands = [
            item for item in before_contract.get("commands", [])
            if isinstance(item, dict) and item.get("kind") == "test"
        ] if isinstance(before_contract.get("commands"), list) else []
        if not test_commands:
            return {
                **base,
                "status": "BLOCKED",
                "reason": "no-test-command-in-verification-contract",
                "verification_level": "contract",
            }

        before_env = None
        after_env = None
        if provision_environments:
            before_env, before_environment = provision_verification_environment(
                before_root,
                before_contract,
                timeout_seconds=timeout_seconds,
            )
            base["environment_evidence"]["before"] = before_environment
            if before_env is None:
                return {
                    **base,
                    "status": "BLOCKED",
                    "reason": "baseline-environment-provisioning-failed",
                    "verification_level": "environment-before",
                }

            after_env, after_environment = provision_verification_environment(
                after_root,
                before_contract,
                timeout_seconds=timeout_seconds,
            )
            base["environment_evidence"]["after"] = after_environment
            if after_env is None:
                return {
                    **base,
                    "status": "BLOCKED",
                    "reason": "target-environment-provisioning-failed",
                    "verification_level": "environment-after",
                }

        before_checks = run_verification_contract(
            before_root,
            before_contract,
            timeout_seconds=timeout_seconds,
            execution_env=before_env,
        )
        base["project_checks"] = {
            "executed": True,
            "before": before_checks,
            "after": [],
        }
        before_tests = [item for item in before_checks if item.get("kind") == "test"]
        base["project_tests"] = {
            "executed": True,
            "before": before_tests,
            "after": [],
        }

        if not before_checks or any(item.get("status") != "PASS" for item in before_checks):
            return {
                **base,
                "status": "BLOCKED",
                "reason": "baseline-verification-contract-failed",
                "verification_level": "contract-before",
            }

        after_checks = run_verification_contract(
            after_root,
            before_contract,
            timeout_seconds=timeout_seconds,
            execution_env=after_env,
        )
        base["project_checks"]["after"] = after_checks
        base["project_tests"]["after"] = [
            item for item in after_checks if item.get("kind") == "test"
        ]

        if len(after_checks) != len(before_checks):
            return {
                **base,
                "status": "FAIL",
                "reason": "verification-contract-result-cardinality-changed",
                "verification_level": "contract",
            }
        if any(item.get("status") != "PASS" for item in after_checks):
            return {
                **base,
                "status": "FAIL",
                "reason": "regression-after-external-patch",
                "verification_level": "contract",
            }

        return {
            **base,
            "status": "PASS",
            "reason": (
                "external-patch-pass-isolated-dependencies"
                if provision_environments
                else "external-patch-pass-shared-host"
            ),
            "verification_level": (
                "external-patch-isolated-dependencies"
                if provision_environments
                else "external-patch-shared-host"
            ),
            "deployment_admissible": False,
        }


def render_external_patch_markdown(result: dict[str, object]) -> str:
    artifact = result.get("patch_artifact", {})
    lines = [
        "# Independent External Patch Verification",
        "",
        f"**Status:** {result.get('status', 'UNKNOWN')}",
        f"**Reason:** {result.get('reason', 'unknown')}",
        f"**Verification level:** {result.get('verification_level', 'none')}",
        f"**Producer metadata:** {result.get('producer') or 'unspecified'}",
        f"**Patch SHA-256:** {artifact.get('sha256') if isinstance(artifact, dict) else None}",
        f"**Deployment admissible:** {result.get('deployment_admissible', False)}",
        "",
        "## Artifact identity",
        "",
    ]
    if isinstance(artifact, dict):
        lines.append(f"- Changed files: {artifact.get('changed_files', [])}")
        lines.append(f"- Size bytes: {artifact.get('size_bytes')}")
    lines.extend(["", "## Baseline identity", ""])
    for item in result.get("baseline_files", []):
        if isinstance(item, dict):
            lines.append(f"- {item.get('path')}: {item.get('sha256')}")

    lines.extend([
        "",
        "## Verification boundary",
        "",
        "The patch producer is metadata only and does not affect the verdict. The original repository is never modified. PASS means the frozen evidence contract passed for this exact patch and baseline; it is not a deployment authorization.",
        "",
    ])
    return "\n".join(lines)


def write_external_patch_verification(
    result: dict[str, object],
    out_dir: str | Path,
) -> tuple[Path, Path]:
    out = Path(out_dir) / "external-patch"
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "verification.json"
    md_path = out / "verification.md"
    json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_external_patch_markdown(result), encoding="utf-8")
    return json_path, md_path
