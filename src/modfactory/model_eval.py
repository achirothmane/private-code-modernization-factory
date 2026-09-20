from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .commands import discover_commands
from .models import RepoSnapshot
from .patches import DEFAULT_DIFF_BUDGET, build_patch_proposal
from .slices import build_migration_slices


SEMANTIC_BLOCK_REASONS = {
    "deterministic-transform-not-implemented",
    "recipe-confidence-not-high",
    "transform-blocked",
    "slice-has-no-recipe",
}
SAFETY_BLOCK_REASONS = {
    "baseline-tests-missing",
    "baseline-ci-missing",
    "baseline-test-command-not-discovered",
}

CONTEXT_FILE_CHAR_LIMIT = 120_000
CONTEXT_TASK_CHAR_LIMIT = 300_000
MAX_RELATED_TESTS = 3


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _signal_for_title(title: str) -> str:
    return {
        "Legacy React render API detected": "ReactDOM.render",
        "Python imp module is removed in Python 3.12+": "imp.",
        "distutils is removed from modern Python": "distutils",
        "Legacy collections ABC import pattern": "collections",
        "node-sass is deprecated": "node-sass",
        "request npm package is deprecated": "request",
        "Javax namespace detected": "javax.",
    }.get(title, "")


def _bounded_context(text: str, signal: str) -> tuple[str, bool]:
    if len(text) <= CONTEXT_FILE_CHAR_LIMIT:
        return text, False

    index = text.find(signal) if signal else -1
    if index < 0:
        index = len(text) // 2
    head = text[:20_000]
    start = max(20_000, index - 45_000)
    end = min(len(text), index + 45_000)
    tail = text[-10_000:]
    excerpt = (
        head
        + "\n\n/* ... ModFactory context omitted ... */\n\n"
        + text[start:end]
        + "\n\n/* ... ModFactory context omitted ... */\n\n"
        + tail
    )
    return excerpt[:CONTEXT_FILE_CHAR_LIMIT], True


def _nearest_manifest(root: Path, target: Path) -> Path | None:
    names = ("package.json", "pom.xml", "pyproject.toml", "requirements.txt")
    current = target.parent
    while True:
        for name in names:
            candidate = current / name
            if candidate.is_file():
                return candidate
        if current == root:
            return None
        try:
            current.relative_to(root)
        except ValueError:
            return None
        if current.parent == current:
            return None
        current = current.parent


def _path_distance(target: Path, candidate: Path) -> int:
    a = target.parent.parts
    b = candidate.parent.parts
    common = 0
    for left, right in zip(a, b):
        if left != right:
            break
        common += 1
    return (len(a) - common) + (len(b) - common)


def _related_tests(root: Path, snapshot: RepoSnapshot, target: Path) -> list[Path]:
    code_extensions = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt", ".go", ".rs", ".rb", ".php", ".cs", ".sh"}
    candidates = [root / rel for rel in snapshot.test_files]
    candidates = [p for p in candidates if p.is_file() and p.suffix.lower() in code_extensions]
    candidates.sort(key=lambda p: (_path_distance(target, p), len(p.as_posix())))
    return candidates[:MAX_RELATED_TESTS]



NPM_USAGE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


def _npm_usage_sites(root: Path, package: str) -> list[Path]:
    quoted = re.escape(package)
    patterns = (
        re.compile(rf"""require\s*\(\s*['"]{quoted}(?:/[^'"]+)?['"]\s*\)"""),
        re.compile(rf"""from\s+['"]{quoted}(?:/[^'"]+)?['"]"""),
        re.compile(rf"""import\s*\(\s*['"]{quoted}(?:/[^'"]+)?['"]\s*\)"""),
        re.compile(rf"""import\s+['"]{quoted}(?:/[^'"]+)?['"]"""),
    )
    found: list[Path] = []
    skip = {".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__"}
    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in skip]
        base = Path(current)
        for name in names:
            candidate = base / name
            if candidate.suffix.lower() not in NPM_USAGE_EXTENSIONS:
                continue
            text = _read_text(candidate)
            if any(pattern.search(text) for pattern in patterns):
                found.append(candidate)
    return sorted(found, key=lambda p: p.relative_to(root).as_posix())


def _semantic_usage_sites(root: Path, recipe: dict[str, object] | None) -> list[Path]:
    if not recipe:
        return []
    recipe_id = str(recipe.get("id", ""))
    if recipe_id == "npm-request-to-modern-http":
        return _npm_usage_sites(root, "request")
    if recipe_id == "node-sass-to-sass":
        return _npm_usage_sites(root, "node-sass")
    return []


def _context_file(root: Path, path: Path, role: str, signal: str = "") -> dict[str, object]:
    raw = _read_text(path)
    content, truncated = _bounded_context(raw, signal)
    return {
        "role": role,
        "path": path.relative_to(root).as_posix(),
        "characters": len(content),
        "original_characters": len(raw),
        "truncated": truncated,
        "content": content,
    }


def build_model_evaluation_plan(
    root: str | Path,
    snapshot: RepoSnapshot,
    *,
    diff_budget: int = DEFAULT_DIFF_BUDGET,
) -> dict[str, object]:
    root = Path(root).resolve()
    commands = discover_commands(root, snapshot)
    slices = build_migration_slices(snapshot)
    tasks: list[dict[str, object]] = []
    blocked: list[dict[str, object]] = []

    for item in slices:
        if item.get("kind") != "compatibility":
            continue

        proposal = build_patch_proposal(
            root,
            snapshot,
            str(item["id"]),
            diff_budget=diff_budget,
        )
        reason = str(proposal.get("reason", "unknown"))
        if reason in SAFETY_BLOCK_REASONS:
            blocked.append({
                "slice_id": item["id"],
                "target": item["target"],
                "reason": reason,
            })
            continue
        if reason not in SEMANTIC_BLOCK_REASONS:
            continue

        target = (root / str(item["target"])).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            continue
        if not target.is_file():
            blocked.append({
                "slice_id": item["id"],
                "target": item["target"],
                "reason": "target-file-unavailable",
            })
            continue

        if not snapshot.test_files or not snapshot.ci_files:
            blocked.append({
                "slice_id": item["id"],
                "target": item["target"],
                "reason": "verification-prerequisites-missing",
            })
            continue

        signal = _signal_for_title(str(item["title"]))
        recipe = item.get("recipe") if isinstance(item.get("recipe"), dict) else None
        context_files = [_context_file(root, target, "target", signal)]

        manifest = _nearest_manifest(root, target)
        if manifest is not None and manifest != target:
            context_files.append(_context_file(root, manifest, "manifest"))

        usage_sites = _semantic_usage_sites(root, recipe)
        for usage_path in usage_sites:
            rel = usage_path.relative_to(root).as_posix()
            if any(f["path"] == rel for f in context_files):
                continue
            context_files.append(_context_file(root, usage_path, "usage-site", signal))

        if not usage_sites:
            for test_path in _related_tests(root, snapshot, target):
                if test_path == target or any(f["path"] == test_path.relative_to(root).as_posix() for f in context_files):
                    continue
                context_files.append(_context_file(root, test_path, "related-test"))

        context_chars = sum(int(f["characters"]) for f in context_files)
        if context_chars <= 80_000:
            context_band = "small"
        elif context_chars <= CONTEXT_TASK_CHAR_LIMIT:
            context_band = "medium"
        else:
            context_band = "large"

        allowed_changes = list(item.get("allowed_changes", []))
        if usage_sites:
            allowed_changes = [str(item["target"])] + [
                path.relative_to(root).as_posix() for path in usage_sites
            ]

        tasks.append({
            "task_id": f"model-{item['id']}",
            "slice_id": item["id"],
            "target": item["target"],
            "title": item["title"],
            "objective": item.get("objective"),
            "evidence": item.get("evidence"),
            "target_profile": snapshot.target_profile,
            "recipe": recipe,
            "allowed_changes": allowed_changes,
            "preconditions": item.get("preconditions", []),
            "acceptance_criteria": item.get("verification", []),
            "rollback_triggers": item.get("rollback_triggers", []),
            "baseline_commands": commands,
            "context_files": context_files,
            "context_characters": context_chars,
            "context_band": context_band,
            "requires_full_repository_context": context_band == "large",
            "model_instruction": (
                "Propose one minimal patch for this migration slice. Modify only the explicit allowed paths. "
                "Migrate every observed usage-site included in the context, preserve behavior, and explain any "
                "semantic assumptions. Return a unified diff plus a short verification rationale. Do not merge or deploy."
            ),
            "evaluation_dimensions": [
                "patch-applies-cleanly",
                "allowed-scope-only",
                "target-migration-signal-removed",
                "baseline-tests-pass",
                "target-stack-builds-or-typechecks",
                "no-unexplained-behavior-change",
                "reviewable-diff-size",
            ],
        })

    return {
        "schema_version": 1,
        "repository": str(root),
        "target_profile": snapshot.target_profile,
        "eligible_tasks": len(tasks),
        "blocked_tasks": len(blocked),
        "context_limits": {
            "per_file_characters": CONTEXT_FILE_CHAR_LIMIT,
            "large_task_characters": CONTEXT_TASK_CHAR_LIMIT,
            "related_tests_max": MAX_RELATED_TESTS,
        },
        "compute_policy": {
            "invoke_model": False,
            "rent_b300": False,
            "next_gate": (
                "RUN_ORDINARY_MODEL_BENCHMARK"
                if tasks
                else "NO_ELIGIBLE_SEMANTIC_TASK"
            ),
            "rule": (
                "Do not use long-context or B300-class compute unless the same evaluation tasks "
                "show a measurable quality/latency/cost limitation on smaller or ordinary models."
            ),
        },
        "tasks": tasks,
        "blocked": blocked,
    }


def write_model_evaluation_plan(plan: dict[str, object], out_dir: str | Path) -> tuple[Path, Path, Path]:
    out = Path(out_dir) / "model-eval"
    out.mkdir(parents=True, exist_ok=True)

    json_path = out / "plan.json"
    jsonl_path = out / "tasks.jsonl"
    md_path = out / "plan.md"

    json_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for task in plan.get("tasks", []):
            handle.write(json.dumps(task, ensure_ascii=False) + "\n")

    lines = [
        "# ModFactory Model Evaluation Plan",
        "",
        f"Eligible semantic tasks: {plan['eligible_tasks']}",
        f"Blocked tasks: {plan['blocked_tasks']}",
        f"Target profile: {plan['target_profile'] or '-'}",
        f"Next compute gate: {plan['compute_policy']['next_gate']}",
        "",
        "No model was invoked and no GPU rental was initiated.",
        "",
        "## Tasks",
        "",
        "| Task | Target | Context chars | Context band | Full repo required |",
        "|---|---|---:|---|---|",
    ]
    for task in plan.get("tasks", []):
        lines.append(
            f"| {task['task_id']} | {task['target']} | {task['context_characters']} | "
            f"{task['context_band']} | {task['requires_full_repository_context']} |"
        )
    if plan.get("blocked"):
        lines.extend(["", "## Blocked", ""])
        for item in plan["blocked"]:
            lines.append(f"- {item['slice_id']} — {item['target']}: {item['reason']}")

    lines.extend([
        "",
        "## Compute rule",
        "",
        str(plan["compute_policy"]["rule"]),
        "",
    ])
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return json_path, jsonl_path, md_path
