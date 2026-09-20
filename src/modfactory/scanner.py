from __future__ import annotations

import ast
import json
import os
import re
from collections import Counter
from pathlib import Path

from .architecture import analyze_architecture
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

COLLECTION_ABCS = {
    "Mapping",
    "MutableMapping",
    "Sequence",
    "MutableSequence",
}

NPM_DEPENDENCY_SECTIONS = (
    "dependencies",
    "devDependencies",
    "optionalDependencies",
    "peerDependencies",
)

# Intentionally narrow. "javax.*" is not equivalent to "Jakarta migration needed".
# Java SE namespaces such as javax.tools, javax.naming, javax.sql, javax.net,
# javax.security and JCache's javax.cache must not be escalated automatically.
JAKARTA_MIGRATION_PREFIXES = (
    "javax.activation.",
    "javax.annotation.security.",
    "javax.batch.",
    "javax.decorator.",
    "javax.ejb.",
    "javax.el.",
    "javax.enterprise.",
    "javax.faces.",
    "javax.inject.",
    "javax.interceptor.",
    "javax.jms.",
    "javax.json.",
    "javax.mail.",
    "javax.persistence.",
    "javax.resource.",
    "javax.security.enterprise.",
    "javax.servlet.",
    "javax.transaction.",
    "javax.validation.",
    "javax.websocket.",
    "javax.ws.rs.",
    "javax.xml.bind.",
    "javax.xml.soap.",
    "javax.xml.ws.",
)

REACTDOM_RENDER_PATTERN = re.compile(r"\bReactDOM\.render\s*\(")
JAVA_IMPORT_PATTERN = re.compile(r"(?m)^\s*import\s+(javax\.[A-Za-z0-9_$.]+)\s*;")
NPM_SOURCE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}


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


def _finding(
    *,
    path: str,
    message: str,
    evidence: str,
    remediation: str,
    score: int,
) -> Finding:
    return Finding(
        category="legacy-api",
        severity="high" if score >= 10 else "medium",
        path=path,
        message=message,
        evidence=evidence,
        remediation=remediation,
        score=score,
    )


def _python_legacy_findings(rel: str, text: str) -> list[Finding]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    detected: dict[str, tuple[str, str, int]] = {}

    def remember(message: str, evidence: str, remediation: str, score: int) -> None:
        detected.setdefault(message, (evidence, remediation, score))

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if name == "imp":
                    remember(
                        "Python imp module is removed in Python 3.12+",
                        f"Python import at line {node.lineno}: import {name}",
                        "Replace imp with importlib.",
                        12,
                    )
                if name == "distutils" or name.startswith("distutils."):
                    remember(
                        "distutils is removed from modern Python",
                        f"Python import at line {node.lineno}: import {name}",
                        "Move packaging/build logic to setuptools or another maintained build backend.",
                        10,
                    )

        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "imp":
                remember(
                    "Python imp module is removed in Python 3.12+",
                    f"Python import at line {node.lineno}: from imp import ...",
                    "Replace imp with importlib.",
                    12,
                )
            if module == "distutils" or module.startswith("distutils."):
                remember(
                    "distutils is removed from modern Python",
                    f"Python import at line {node.lineno}: from {module} import ...",
                    "Move packaging/build logic to setuptools or another maintained build backend.",
                    10,
                )
            if module == "collections":
                names = {alias.name for alias in node.names}
                legacy = sorted(names & COLLECTION_ABCS)
                if legacy:
                    remember(
                        "Legacy collections ABC import pattern",
                        f"Python import at line {node.lineno}: collections -> {', '.join(legacy)}",
                        "Use collections.abc equivalents.",
                        8,
                    )

        elif isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id == "collections"
                and node.attr in COLLECTION_ABCS
            ):
                remember(
                    "Legacy collections ABC import pattern",
                    f"Python attribute at line {node.lineno}: collections.{node.attr}",
                    "Use collections.abc equivalents.",
                    8,
                )

    return [
        _finding(
            path=rel,
            message=message,
            evidence=evidence,
            remediation=remediation,
            score=score,
        )
        for message, (evidence, remediation, score) in detected.items()
    ]


def _npm_dependency_usage_observed(
    root: Path,
    package: str,
    payload: dict[str, object],
) -> str | None:
    scripts = payload.get("scripts")
    if isinstance(scripts, dict):
        for name, value in scripts.items():
            if isinstance(value, str) and re.search(
                rf"(?<![A-Za-z0-9_-]){re.escape(package)}(?![A-Za-z0-9_-])",
                value,
            ):
                return f"package.json script {name}"

    quoted = re.escape(package)
    patterns = (
        re.compile(rf"""require\s*\(\s*['"]{quoted}(?:/[^'"]+)?['"]\s*\)"""),
        re.compile(rf"""from\s+['"]{quoted}(?:/[^'"]+)?['"]"""),
        re.compile(rf"""import\s*\(\s*['"]{quoted}(?:/[^'"]+)?['"]\s*\)"""),
        re.compile(rf"""import\s+['"]{quoted}(?:/[^'"]+)?['"]"""),
    )

    for current, dirs, names in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        current_path = Path(current)
        for name in names:
            candidate = current_path / name
            if candidate.suffix.lower() not in NPM_SOURCE_EXTENSIONS:
                continue
            source = _read_text(candidate)
            if source is None:
                continue
            for pattern in patterns:
                match = pattern.search(source)
                if match:
                    line = source.count("\n", 0, match.start()) + 1
                    rel = candidate.relative_to(root).as_posix()
                    return f"{rel}:{line}"
    return None


def _npm_manifest_findings(root: Path, path: Path, rel: str, text: str) -> list[Finding]:
    if path.name != "package.json":
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []

    direct: dict[str, tuple[str, str]] = {}
    for section in NPM_DEPENDENCY_SECTIONS:
        deps = payload.get(section)
        if not isinstance(deps, dict):
            continue
        for package in ("node-sass", "request"):
            version = deps.get(package)
            if isinstance(version, str):
                direct.setdefault(package, (section, version))

    findings: list[Finding] = []
    for package, (section, version) in direct.items():
        usage = _npm_dependency_usage_observed(root, package, payload)
        if usage is None:
            findings.append(Finding(
                category="dependency-hygiene",
                severity="medium",
                path=rel,
                message=f"Deprecated direct npm dependency has no observed source usage: {package}",
                evidence=(
                    f"Direct npm dependency: {section}.{package}={version}; "
                    "no static import/require or package-script usage was observed."
                ),
                remediation=(
                    "Verify the dependency is unused, remove it, regenerate the lockfile, "
                    "and run the baseline. Do not replace an unused dependency with a new package."
                ),
                score=4,
            ))
            continue

        if package == "node-sass":
            findings.append(_finding(
                path=rel,
                message="node-sass is deprecated",
                evidence=f"Direct npm dependency: {section}.node-sass={version}; usage: {usage}",
                remediation="Migrate to Dart Sass (sass package).",
                score=10,
            ))
        elif package == "request":
            findings.append(_finding(
                path=rel,
                message="request npm package is deprecated",
                evidence=f"Direct npm dependency: {section}.request={version}; usage: {usage}",
                remediation="Replace request with fetch, undici, axios, or another maintained HTTP client.",
                score=8,
            ))
    return findings


def _nearest_package_json(root: Path, path: Path) -> tuple[Path, dict[str, object]] | None:
    current = path.parent
    while True:
        manifest = current / "package.json"
        if manifest.exists():
            text = _read_text(manifest)
            if text is not None:
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    payload = None
                if isinstance(payload, dict):
                    return manifest, payload
        if current == root:
            return None
        try:
            current.relative_to(root)
        except ValueError:
            return None
        if current.parent == current:
            return None
        current = current.parent


def _npm_dependency_version(payload: dict[str, object], package: str) -> str | None:
    for section in NPM_DEPENDENCY_SECTIONS:
        deps = payload.get(section)
        if not isinstance(deps, dict):
            continue
        version = deps.get(package)
        if isinstance(version, str):
            return version
    return None


def _semver_major(version: str) -> int | None:
    match = re.search(r"(?<!\d)(\d+)(?:\.\d+)?(?:\.\d+)?", version)
    return int(match.group(1)) if match else None


def _javascript_legacy_findings(
    root: Path,
    path: Path,
    rel: str,
    text: str,
    targets: dict[str, str],
) -> list[Finding]:
    match = REACTDOM_RENDER_PATTERN.search(text)
    if not match:
        return []

    package_info = _nearest_package_json(root, path)
    if package_info is None:
        return []

    manifest, payload = package_info
    react_dom_version = _npm_dependency_version(payload, "react-dom")
    if react_dom_version is None:
        return []

    current_major = _semver_major(react_dom_version)
    target_version = targets.get("react-dom")
    target_major = _semver_major(target_version) if target_version else None
    effective_major = target_major if target_major is not None else current_major
    if effective_major is None or effective_major < 18:
        return []

    line = text.count("\n", 0, match.start()) + 1
    manifest_rel = manifest.relative_to(root).as_posix()
    context = f"{manifest_rel} declares react-dom={react_dom_version}"
    if target_version:
        context += f"; explicit target react-dom={target_version}"
    return [_finding(
        path=rel,
        message="Legacy React render API detected",
        evidence=f"JavaScript call at line {line}: ReactDOM.render(...); {context}",
        remediation="Migrate to createRoot for React 18+ behavior.",
        score=7,
    )]


def _pom_spring_boot_version(text: str) -> str | None:
    property_match = re.search(
        r"<spring-boot\\.version>\\s*([^<]+?)\\s*</spring-boot\\.version>",
        text,
        flags=re.IGNORECASE,
    )
    if property_match:
        return property_match.group(1).strip()

    parent_match = re.search(
        r"<parent>.*?<artifactId>\\s*spring-boot-starter-parent\\s*</artifactId>.*?"
        r"<version>\\s*([^<]+?)\\s*</version>.*?</parent>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if parent_match:
        return parent_match.group(1).strip()

    bom_match = re.search(
        r"<dependency>.*?<artifactId>\\s*spring-boot-dependencies\\s*</artifactId>.*?"
        r"<version>\\s*([^<]+?)\\s*</version>.*?</dependency>",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if bom_match:
        version = bom_match.group(1).strip()
        if not version.startswith("${"):
            return version
    return None


def _spring_boot_version_for_path(root: Path, path: Path) -> tuple[Path, str] | None:
    current = path.parent
    while True:
        pom = current / "pom.xml"
        if pom.exists():
            text = _read_text(pom)
            if text:
                version = _pom_spring_boot_version(text)
                if version:
                    return pom, version
        if current == root:
            return None
        try:
            current.relative_to(root)
        except ValueError:
            return None
        if current.parent == current:
            return None
        current = current.parent


def _java_legacy_findings(
    root: Path,
    path: Path,
    rel: str,
    text: str,
    targets: dict[str, str],
) -> list[Finding]:
    candidate: tuple[str, int] | None = None
    for match in JAVA_IMPORT_PATTERN.finditer(text):
        imported = match.group(1)
        if any(imported.startswith(prefix) for prefix in JAKARTA_MIGRATION_PREFIXES):
            line = text.count("\n", 0, match.start()) + 1
            candidate = (imported, line)
            break
    if candidate is None:
        return []

    explicit_target = targets.get("spring-boot")
    target_major = _semver_major(explicit_target) if explicit_target else None
    pom_context = _spring_boot_version_for_path(root, path)
    current_version = pom_context[1] if pom_context else None
    current_major = _semver_major(current_version) if current_version else None
    effective_major = target_major if target_major is not None else current_major

    # javax.* is expected in Spring Boot 2.x-era stacks. It becomes a concrete
    # Jakarta migration requirement only when the current or explicit target
    # stack is Spring Boot 3+.
    if effective_major is None or effective_major < 3:
        return []

    imported, line = candidate
    context: list[str] = []
    if pom_context:
        context.append(
            f"{pom_context[0].relative_to(root).as_posix()} declares Spring Boot {current_version}"
        )
    if explicit_target:
        context.append(f"explicit target spring-boot={explicit_target}")
    suffix = f"; {'; '.join(context)}" if context else ""
    return [_finding(
        path=rel,
        message="Javax namespace detected",
        evidence=f"Jakarta-candidate import at line {line}: {imported}{suffix}",
        remediation="Migrate affected javax imports/APIs to Jakarta equivalents for Spring Boot 3+.",
        score=5,
    )]


def _legacy_findings_for_file(
    root: Path,
    path: Path,
    rel: str,
    lang: str | None,
    text: str,
    targets: dict[str, str],
) -> list[Finding]:
    findings: list[Finding] = []

    if lang == "Python":
        findings.extend(_python_legacy_findings(rel, text))

    if path.name == "package.json":
        findings.extend(_npm_manifest_findings(root, path, rel, text))

    if lang in {"JavaScript", "TypeScript"}:
        findings.extend(_javascript_legacy_findings(root, path, rel, text, targets))

    if lang == "Java":
        findings.extend(_java_legacy_findings(root, path, rel, text, targets))

    return findings


def scan_repository(
    root: str | Path,
    *,
    targets: dict[str, str] | None = None,
) -> RepoSnapshot:
    root = Path(root).resolve()
    target_profile = dict(targets or {})
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

            findings.extend(_legacy_findings_for_file(root, path, rel, lang, text, target_profile))

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

    architecture = analyze_architecture(root, source_files)
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
        history=history, architecture=architecture, target_profile=target_profile,
    )
