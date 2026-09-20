from __future__ import annotations

import ast
import difflib
import json
import re
from pathlib import Path

from .commands import discover_commands
from .models import RepoSnapshot
from .slices import build_migration_slices


DEFAULT_DIFF_BUDGET = 80
SUPPORTED_RECIPES = {
    "python-distutils-to-setuptools",
    "python-collections-abc",
    "reactdom-render-to-createroot",
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



def _find_matching_paren(text: str, open_index: int) -> int | None:
    paren = 1
    quote: str | None = None
    escaped = False
    i = open_index + 1
    while i < len(text):
        ch = text[i]
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            i += 1
            continue
        if ch in {"'", '"'} or ord(ch) == 96:
            quote = ch
        elif ch == "(":
            paren += 1
        elif ch == ")":
            paren -= 1
            if paren == 0:
                return i
        i += 1
    return None


def _split_top_level_call_args(body: str) -> tuple[str, str] | None:
    paren = brace = bracket = 0
    quote: str | None = None
    escaped = False
    split_at: int | None = None
    for i, ch in enumerate(body):
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in {"'", '"'} or ord(ch) == 96:
            quote = ch
        elif ch == "(":
            paren += 1
        elif ch == ")":
            paren = max(0, paren - 1)
        elif ch == "{":
            brace += 1
        elif ch == "}":
            brace = max(0, brace - 1)
        elif ch == "[":
            bracket += 1
        elif ch == "]":
            bracket = max(0, bracket - 1)
        elif ch == "," and paren == brace == bracket == 0:
            if split_at is not None:
                return None
            split_at = i
    if split_at is None:
        return None
    first = body[:split_at].strip()
    second = body[split_at + 1:].strip()
    if not first or not second:
        return None
    return first, second


def _react_root_name(container: str, text: str) -> str | None:
    if not re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", container):
        return None
    root_name = f"{container}Root"
    if re.search(rf"\b{re.escape(root_name)}\b", text):
        return None
    return root_name


def _insert_reusable_root(text: str, container: str, root_name: str) -> tuple[str, str | None]:
    declaration = re.search(
        rf"(?m)^(?P<indent>\s*)(?:const|let)\s+{re.escape(container)}\s*=\s*document\.createElement\([^\n]+\)\s*$",
        text,
    )
    if not declaration:
        return text, "Named render container is not a supported document.createElement declaration."

    insert_end = declaration.end()
    following = text[insert_end:]
    class_assignment = re.match(
        rf"(?P<newline>\r?\n)(?P<line>\s*{re.escape(container)}\.className\s*=\s*[^\n]+)",
        following,
    )
    if class_assignment:
        insert_end += class_assignment.end()

    indent = declaration.group("indent")
    insertion = f"\n{indent}const {root_name} = createRoot({container})"
    return text[:insert_end] + insertion + text[insert_end:], None


def _transform_reactdom_render(text: str, target: str) -> tuple[str, str | None]:
    import_pattern = re.compile(
        r"(?m)^(?P<indent>\s*)import\s+ReactDOM\s+from\s+['\"]react-dom['\"]\s*;?\s*$"
    )
    import_match = import_pattern.search(text)
    if not import_match:
        return text, "Only a default ReactDOM import from react-dom is supported."

    call_token = "ReactDOM.render("
    call_start = text.find(call_token)
    if call_start < 0:
        return text, "No ReactDOM.render call found."
    if text.find(call_token, call_start + len(call_token)) >= 0:
        return text, "Multiple ReactDOM.render calls in one target file are blocked."

    open_index = call_start + len("ReactDOM.render")
    close_index = _find_matching_paren(text, open_index)
    if close_index is None:
        return text, "ReactDOM.render call has unbalanced parentheses."

    args = _split_top_level_call_args(text[open_index + 1:close_index])
    if args is None:
        return text, "ReactDOM.render arguments are not a supported two-argument shape."
    element_expr, container_expr = args

    updated = import_pattern.sub(
        lambda m: f"{m.group('indent')}import {{ createRoot }} from 'react-dom/client'",
        text,
        count=1,
    )

    call_start = updated.find(call_token)
    open_index = call_start + len("ReactDOM.render")
    close_index = _find_matching_paren(updated, open_index)
    if close_index is None:
        return text, "ReactDOM.render call became unbalanced after import rewrite."

    typescript = Path(target).suffix.lower() in {".ts", ".tsx"}
    if re.fullmatch(r"document\.getElementById\([^)]*\)", container_expr, flags=re.DOTALL):
        container = container_expr + ("!" if typescript else "")
        render_prefix = f"createRoot({container}).render("
    elif ".appendChild(" in container_expr:
        render_prefix = f"createRoot({container_expr}).render("
    else:
        root_name = _react_root_name(container_expr, updated)
        if root_name is None:
            return text, "Render target lifetime is not a supported deterministic pattern."
        updated, blocked = _insert_reusable_root(updated, container_expr, root_name)
        if blocked:
            return text, blocked
        call_start = updated.find(call_token)
        open_index = call_start + len("ReactDOM.render")
        close_index = _find_matching_paren(updated, open_index)
        if close_index is None:
            return text, "ReactDOM.render call became unbalanced after reusable-root insertion."
        render_prefix = f"{root_name}.render("

    replacement = render_prefix + element_expr + ")"
    updated = updated[:call_start] + replacement + updated[close_index + 1:]
    if "ReactDOM.render(" in updated:
        return text, "Legacy ReactDOM.render remains after deterministic transform."
    return updated, None


def _apply_recipe(recipe_id: str, text: str, target: str) -> tuple[str, str | None]:
    if recipe_id == "python-distutils-to-setuptools":
        return _transform_distutils(text)
    if recipe_id == "python-collections-abc":
        return _transform_collections_abc(text)
    if recipe_id == "reactdom-render-to-createroot":
        return _transform_reactdom_render(text, target)
    return text, f"Recipe {recipe_id!r} does not yet have a deterministic patch transform."


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
    snapshot_root = Path(snapshot.root).resolve()
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

    base["slice"] = selected

    if snapshot_root != root_path:
        return {**base, "reason": "snapshot-root-mismatch"}

    commands = discover_commands(root_path, snapshot)
    test_commands = [item for item in commands if item.get("kind") == "test"]
    base["baseline_evidence"] = {
        "test_files": list(snapshot.test_files),
        "ci_files": list(snapshot.ci_files),
        "test_commands": test_commands,
    }
    if not snapshot.test_files:
        return {**base, "reason": "baseline-tests-missing"}
    if not snapshot.ci_files:
        return {**base, "reason": "baseline-ci-missing"}
    if not test_commands:
        return {**base, "reason": "baseline-test-command-not-discovered"}

    target = str(selected.get("target", ""))
    recipe = selected.get("recipe")
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

    after, blocked_reason = _apply_recipe(recipe_id, before, target)
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
