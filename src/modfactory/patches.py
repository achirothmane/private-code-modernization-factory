from __future__ import annotations

import ast
import difflib
import json
import re
from pathlib import Path

from .models import RepoSnapshot
from .slices import build_migration_slices


DEFAULT_DIFF_BUDGET = 80
SUPPORTED_RECIPES = {
    "python-distutils-to-setuptools",
    "python-collections-abc",
}
COLLECTION_ABCS = {
    "Mapping",
    "MutableMapping",
    "Sequence",
    "MutableSequence",
}


def _safe_target(root: Path, target: str) -> Path | None:
    candidate = (root / target).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    if not candidate.exists() or not candidate.is_file():
        return None
    return candidate


def _changed_line_count(before: str, after: str) -> int:
    matcher = difflib.SequenceMatcher(a=before.splitlines(), b=after.splitlines())
    changed = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        changed += (i2 - i1) + (j2 - j1)
    return changed


def _unified_diff(path: str, before: str, after: str) -> str:
    return "".join(difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
    ))


def _transform_distutils(text: str) -> tuple[str, str | None]:
    pattern = re.compile(r"(?m)^(?P<indent>\s*)from\s+distutils\.core\s+import\s+(?P<names>[^\n#]+)(?P<suffix>\s*(?:#.*)?)$")
    changed = False

    def replace(match: re.Match[str]) -> str:
        nonlocal changed
        changed = True
        return f"{match.group('indent')}from setuptools import {match.group('names').rstrip()}{match.group('suffix')}"

    updated = pattern.sub(replace, text)
    if not changed:
        return text, "Only 'from distutils.core import ...' is supported by the deterministic Wave 5 transform."
    return updated, None


def _transform_collections_abc(text: str) -> tuple[str, str | None]:
    changed = False
    blocked_mixed_import = False
    line_pattern = re.compile(
        r"(?m)^(?P<indent>\s*)from\s+collections\s+import\s+(?P<names>[^\n#]+)(?P<suffix>\s*(?:#.*)?)$"
    )

    def replace_import(match: re.Match[str]) -> str:
        nonlocal changed, blocked_mixed_import
        raw_names = match.group("names").strip()
        if "(" in raw_names or ")" in raw_names:
            blocked_mixed_import = True
            return match.group(0)

        names = [item.strip() for item in raw_names.split(",") if item.strip()]
        base_names = {item.split()[0] for item in names}
        if not names or not base_names.issubset(COLLECTION_ABCS):
            if base_names & COLLECTION_ABCS:
                blocked_mixed_import = True
            return match.group(0)

        changed = True
        return (
            f"{match.group('indent')}from collections.abc import "
            f"{match.group('names').rstrip()}{match.group('suffix')}"
        )

    updated = line_pattern.sub(replace_import, text)

    direct_pattern = re.compile(
        r"\bcollections\.(Mapping|MutableMapping|Sequence|MutableSequence)\b"
    )
    updated, direct_count = direct_pattern.subn(r"collections.abc.\1", updated)
    if direct_count:
        changed = True

    if blocked_mixed_import:
        return text, (
            "Mixed or parenthesized 'from collections import ...' statements are blocked "
            "because moving only selected names could change import semantics."
        )
    if not changed:
        return text, "No deterministic collections ABC replacement was found."
    return updated, None


def _apply_recipe(recipe_id: str, text: str) -> tuple[str, str | None]:
    if recipe_id == "python-distutils-to-setuptools":
        return _transform_distutils(text)
    if recipe_id == "python-collections-abc":
        return _transform_collections_abc(text)
    return text, f"Recipe {recipe_id!r} does not yet have a deterministic Wave 5 patch transform."


def validate_proposal_scope(proposal: dict[str, object]) -> tuple[bool, list[str]]:
    allowed = {str(path) for path in proposal.get("allowed_files", [])}
    changed = {str(path) for path in proposal.get("changed_files", [])}
    violations = sorted(changed - allowed)
    return not violations, violations


def build_patch_proposal(
    root: str | Path,
    snapshot: RepoSnapshot,
    slice_id: str,
    diff_budget: int = DEFAULT_DIFF_BUDGET,
) -> dict[str, object]:
    root_path = Path(root).resolve()
    slices = build_migration_slices(snapshot)
    selected = next((item for item in slices if item.get("id") == slice_id), None)

    base = {
        "slice_id": slice_id,
        "status": "BLOCKED",
        "applies_changes": False,
        "creates_commits": False,
        "auto_merges": False,
        "requires_human_review": True,
        "diff_budget": diff_budget,
        "changed_lines": 0,
        "changed_files": [],
        "allowed_files": [],
        "diff": "",
    }

    if selected is None:
        return {**base, "reason": "migration-slice-not-found"}

    target = str(selected.get("target", ""))
    recipe = selected.get("recipe")
    base["slice"] = selected
    base["allowed_files"] = [target] if target and target != "." else []

    if selected.get("kind") != "compatibility":
        return {**base, "reason": "slice-kind-not-patchable"}

    if not isinstance(recipe, dict):
        return {**base, "reason": "slice-has-no-recipe"}

    recipe_id = str(recipe.get("id", ""))
    confidence = str(recipe.get("confidence", ""))
    base["recipe_id"] = recipe_id
    base["recipe_confidence"] = confidence

    if confidence != "high":
        return {**base, "reason": "recipe-confidence-not-high"}

    if recipe_id not in SUPPORTED_RECIPES:
        return {**base, "reason": "deterministic-transform-not-implemented"}

    target_path = _safe_target(root_path, target)
    if target_path is None:
        return {**base, "reason": "target-is-not-a-safe-existing-file"}

    try:
        before = target_path.read_text(encoding="utf-8", errors="strict")
    except (OSError, UnicodeError) as exc:
        return {**base, "reason": "target-read-failed", "detail": str(exc)}

    after, blocked_reason = _apply_recipe(recipe_id, before)
    if blocked_reason:
        return {**base, "reason": "transform-blocked", "detail": blocked_reason}

    if after == before:
        return {**base, "reason": "transform-produced-no-change"}

    if target_path.suffix == ".py":
        try:
            ast.parse(after, filename=target)
        except SyntaxError as exc:
            return {**base, "reason": "proposed-python-syntax-invalid", "detail": str(exc)}

    changed_lines = _changed_line_count(before, after)
    diff = _unified_diff(target, before, after)
    proposal = {
        **base,
        "status": "PROPOSED",
        "reason": "deterministic-transform-available",
        "changed_lines": changed_lines,
        "changed_files": [target],
        "diff": diff,
        "verification": list(selected.get("verification", [])),
        "rollback_triggers": list(selected.get("rollback_triggers", [])),
        "policy": {
            "one_slice_only": True,
            "max_files": 1,
            "file_allowlist_enforced": True,
            "proposal_only": True,
        },
    }

    in_scope, violations = validate_proposal_scope(proposal)
    if not in_scope:
        return {
            **proposal,
            "status": "BLOCKED",
            "reason": "file-allowlist-violation",
            "scope_violations": violations,
            "diff": "",
        }

    if changed_lines > diff_budget:
        return {
            **proposal,
            "status": "BLOCKED",
            "reason": "diff-budget-exceeded",
            "diff": "",
        }

    return proposal


def write_patch_proposal(proposal: dict[str, object], out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir) / "patch"
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "proposal.json"
    diff_path = out / "change.diff"
    json_path.write_text(json.dumps(proposal, indent=2), encoding="utf-8")
    diff_path.write_text(str(proposal.get("diff", "")), encoding="utf-8")
    return json_path, diff_path
