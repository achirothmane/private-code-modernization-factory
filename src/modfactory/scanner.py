from __future__ import annotations

import os
import re
from collections import Counter
from pathlib import Path

from .history import analyze_history
from .models import Finding, RepoSnapshot


SKIP_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode", "node_modules", "vendor",
    ".venv", "venv", "dist", "build", "target", "coverage", ".pytest_cache",
    ".mypy_cache", "__pycache__",
}

LANG_BY_EXT = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".kt": "Kotlin", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
    ".php": "PHP", ".cs": "C#", ".cpp": "C++", ".cc": "C++",
    ".c": "C", ".h": "C/C++ Header", ".hpp": "C/C++ Header",
    ".scala": "Scala", ".swift": "Swift", ".sh": "Shell",
}

MANIFESTS = {
    "requirements.txt", "pyproject.toml", "setup.py", "Pipfile", "poetry.lock",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "pom.xml", "build.gradle", "build.gradle.kts", "go.mod", "Cargo.toml",
    "Gemfile", "composer.json", "*.csproj",
}

LEGACY_PATTERNS = [
    (re.compile(r"\bimport\s+imp\b|\bfrom\s+imp\s+import\b"), "Python imp module is removed in Python 3.12+", "Replace imp with importlib.", 12),
    (re.compile(r"\bfrom\s+distutils\b|\bimport\s+distutils\b"), "distutils is removed from modern Python", "Move packaging/build logic to setuptools or another maintained build backend.", 10),
    (re.compile(r"collections\.(MutableMapping|MutableSequence|Mapping|Sequence)|from\s+collections\s+import\s+[^\n]*(MutableMapping|MutableSequence|Mapping|Sequence)"), "Legacy collections ABC import pattern", "Use collections.abc equivalents.", 8),
    (re.compile(r"\bnode-sass\b"), "node-sass is deprecated", "Migrate to Dart Sass (sass package).", 10),
    (re.compile(r"[\"']request[\"']\s*:\s*[\"']"), "request npm package is deprecated", "Replace request with fetch, undici, axios, or another maintained HTTP client.", 8),
    (re.compile(r"ReactDOM\.render\s*\("), "Legacy React render API detected", "Migrate to createRoot before adopting newer React behavior.", 7),
    (re.compile(r"javax\."), "Javax namespace detected", "Assess Jakarta namespace migration if upgrading to newer enterprise Java stacks.", 5),
]


def _is_manifest(path: Path) -> bool:
    name = path.name
    if name in MANIFESTS:
        return True
    return name.endswith(".csproj")


def _is_test_file(rel: str, name: str) -> bool:
    lower = rel.lower()
    return (
        "/test/" in f"/{lower}/" or "/tests/" in f"/{lower}/" or
        name.startswith("test_") or name.endswith("_test.py") or
        ".test." in name or ".spec." in name
    )


def _read_text(path: Path, max_bytes: int = 1_500_000) -> str | None:
    try:
        if path.stat().st_size > max_bytes:
            return None
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return None


def scan_repository(root: str | Path) -> RepoSnapshot:
    root = Path(root).resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Repository path does not exist or is not a directory: {root}")

    files = 0
    lines = 0
    languages: Counter[str] = Counter()
    manifests: list[str] = []
    ci_files: list[str] = []
    test_files: list[str] = []
    source_files: list[str] = []
    findings: list[Finding] = []

    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        current_path = Path(current)
        for name in names:
            path = current_path / name
            rel = path.relative_to(root).as_posix()
            files += 1

            if _is_manifest(path):
                manifests.append(rel)
            if rel.startswith(".github/workflows/") and path.suffix in {".yml", ".yaml"}:
                ci_files.append(rel)
            if _is_test_file(rel, name):
                test_files.append(rel)

            lang = LANG_BY_EXT.get(path.suffix.lower())
            if lang:
                languages[lang] += 1
                source_files.append(rel)

            text = _read_text(path)
            if text is None:
                continue
            line_count = text.count("\n") + (1 if text else 0)
            lines += line_count

            if lang and line_count > 1200:
                findings.append(Finding(
                    category="maintainability", severity="high", path=rel,
                    message=f"Large source file ({line_count} lines)",
                    evidence="Large files increase migration blast radius and review difficulty.",
                    remediation="Split modernization into smaller modules before or during migration.",
                    score=8,
                ))
            elif lang and line_count > 600:
                findings.append(Finding(
                    category="maintainability", severity="medium", path=rel,
                    message=f"Large source file ({line_count} lines)",
                    evidence="Large files are harder to change safely in one migration step.",
                    remediation="Prefer staged extraction and add characterization tests first.",
                    score=4,
                ))

            for pattern, message, remediation, score in LEGACY_PATTERNS:
                match = pattern.search(text)
                if match:
                    findings.append(Finding(
                        category="legacy-api", severity="high" if score >= 10 else "medium",
                        path=rel, message=message,
                        evidence=f"Matched: {match.group(0)[:120]}",
                        remediation=remediation, score=score,
                    ))

    if source_files and not test_files:
        findings.append(Finding(
            category="verification", severity="critical", path=".",
            message="No automated test files detected",
            evidence=f"Detected {len(source_files)} source files and 0 recognizable test files.",
            remediation="Add characterization tests around current behavior before modernization.",
            score=22,
        ))

    if source_files and not ci_files:
        findings.append(Finding(
            category="delivery", severity="high", path=".github/workflows",
            message="No GitHub Actions CI workflow detected",
            evidence="Repository changes cannot be automatically verified by this analyzer.",
            remediation="Add a CI baseline that runs tests and produces machine-readable evidence.",
            score=12,
        ))

    if source_files and not manifests:
        findings.append(Finding(
            category="reproducibility", severity="medium", path=".",
            message="No recognized dependency/build manifest detected",
            evidence="Dependency graph cannot be reconstructed reliably.",
            remediation="Add or recover a canonical build/dependency manifest before migration.",
            score=8,
        ))

    history = analyze_history(root)
    for hotspot in history.get("single_owner_hotspots", []):
        findings.append(Finding(
            category="ownership", severity="medium", path=str(hotspot["path"]),
            message="High-churn file has a single recent owner",
            evidence=f"{hotspot['touches']} touches across analyzed history, {hotspot['authors']} unique author.",
            remediation="Require explicit reviewer/owner coverage and characterization tests before migrating this hotspot.",
            score=5,
        ))

    return RepoSnapshot(
        root=str(root), files=files, lines=lines, languages=dict(languages),
        manifests=sorted(manifests), ci_files=sorted(ci_files),
        test_files=sorted(test_files), source_files=sorted(source_files), findings=findings,
        history=history,
    )
