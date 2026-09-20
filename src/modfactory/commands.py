from __future__ import annotations

import json
import re
from pathlib import Path

from .models import RepoSnapshot


CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


def _read_text(path: Path, max_bytes: int = 500_000) -> str:
    try:
        if not path.exists() or not path.is_file() or path.stat().st_size > max_bytes:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _kind_for_command(command: str) -> str | None:
    lower = command.lower()
    if any(token in lower for token in (
        "pytest", "unittest", "npm test", "npm run test", "yarn test", "pnpm test",
        "go test", "cargo test", "mvn test", "gradle test", "gradlew test", "rake test",
        "doctest", " tox", "tox ",
    )):
        return "test"
    if any(token in lower for token in (
        " build", "npm run build", "yarn build", "pnpm build", "go build",
        "cargo build", "mvn package", "gradle build", "gradlew build",
    )):
        return "build"
    if any(token in lower for token in (
        " lint", "npm run lint", "yarn lint", "pnpm lint", "ruff", "flake8",
        "mypy", "eslint", "cargo clippy",
    )):
        return "lint"
    return None


def discover_commands(root: str | Path, snapshot: RepoSnapshot) -> list[dict[str, object]]:
    root = Path(root).resolve()
    commands: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()

    def add(kind: str, command: str, source: str, confidence: str, reason: str) -> None:
        command = " ".join(command.strip().splitlines()).strip()
        if not command or len(command) > 500:
            return
        key = (kind, command)
        if key in seen:
            return
        seen.add(key)
        commands.append({
            "kind": kind,
            "command": command,
            "source": source,
            "confidence": confidence,
            "reason": reason,
            "auto_execute": False,
            "execution_policy": "manual-or-sandbox-only",
        })

    for rel in snapshot.ci_files:
        text = _read_text(root / rel)
        for line in text.splitlines():
            match = re.match(r"\s*-\s*run:\s*(.+?)\s*$", line)
            if not match:
                continue
            command = match.group(1).strip().strip("'\"")
            kind = _kind_for_command(command)
            if kind:
                add(kind, command, rel, "high", "Command is already used by repository CI.")

    package_json = root / "package.json"
    if package_json.exists():
        try:
            payload = json.loads(_read_text(package_json))
        except (json.JSONDecodeError, TypeError):
            payload = {}
        scripts = payload.get("scripts", {}) if isinstance(payload, dict) else {}
        if isinstance(scripts, dict):
            runner = "npm"
            if (root / "pnpm-lock.yaml").exists():
                runner = "pnpm"
            elif (root / "yarn.lock").exists():
                runner = "yarn"
            for name, kind in (
                ("test", "test"), ("build", "build"), ("lint", "lint"),
                ("check", "lint"), ("typecheck", "lint"),
            ):
                if name not in scripts:
                    continue
                if runner == "npm":
                    command = "npm test" if name == "test" else f"npm run {name}"
                else:
                    command = f"{runner} {name}"
                add(kind, command, f"package.json#scripts.{name}", "high",
                    f"package.json defines the {name!r} script.")

    pyproject = _read_text(root / "pyproject.toml")
    requirements = "\n".join(
        _read_text(root / rel)
        for rel in snapshot.manifests
        if Path(rel).name.startswith("requirements")
    )
    pytest_signal = (
        (root / "pytest.ini").exists()
        or (root / "conftest.py").exists()
        or "[tool.pytest" in pyproject
        or re.search(r"(?im)^\s*pytest(?:[<>=!~\[]|\s|$)", requirements) is not None
    )
    if "Python" in snapshot.languages and snapshot.test_files:
        if pytest_signal:
            add("test", "python -m pytest -q", "python-test-layout", "high",
                "Pytest configuration/dependency and test files were detected.")
        else:
            tests_dir = root / "tests"
            command = "python -m unittest discover -s tests -v" if tests_dir.exists() else "python -m unittest discover -v"
            add("test", command, "python-test-layout", "medium",
                "Python test files were detected without a stronger pytest signal.")

    tox_ini = _read_text(root / "tox.ini")
    if tox_ini:
        add("test", "tox", "tox.ini", "high", "tox.ini defines the repository's test environments.")
        for match in re.finditer(r"(?m)^\s*commands\s*=\s*(.+?)\s*$", tox_ini):
            command = match.group(1).strip()
            kind = _kind_for_command(command) or "test"
            add(kind, command, "tox.ini#commands", "high",
                "Command is declared by tox as a test-environment command.")

    setup_py = root / "setup.py"
    if setup_py.exists():
        add("build", "python setup.py build", "setup.py", "medium",
            "Legacy Python setup.py build configuration detected.")

    if (root / "go.mod").exists():
        add("test", "go test ./...", "go.mod", "high", "Go module detected.")
        add("build", "go build ./...", "go.mod", "high", "Go module detected.")

    if (root / "Cargo.toml").exists():
        add("test", "cargo test", "Cargo.toml", "high", "Cargo manifest detected.")
        add("build", "cargo build", "Cargo.toml", "high", "Cargo manifest detected.")

    if (root / "pom.xml").exists():
        mvn = "./mvnw" if (root / "mvnw").exists() else "mvn"
        add("test", f"{mvn} test", "pom.xml", "high", "Maven project detected.")
        add("build", f"{mvn} package -DskipTests", "pom.xml", "medium", "Maven project detected.")

    gradle_manifest = (root / "build.gradle").exists() or (root / "build.gradle.kts").exists()
    if gradle_manifest:
        gradle = "./gradlew" if (root / "gradlew").exists() else "gradle"
        add("test", f"{gradle} test", "gradle-build", "high", "Gradle project detected.")
        add("build", f"{gradle} build -x test", "gradle-build", "medium", "Gradle project detected.")

    makefile = _read_text(root / "Makefile")
    if makefile:
        targets = set(re.findall(r"(?m)^([A-Za-z0-9_.-]+)\s*:(?!=)", makefile))
        for target, kind in (("test", "test"), ("check", "lint"), ("lint", "lint"), ("build", "build")):
            if target in targets:
                add(kind, f"make {target}", f"Makefile#{target}", "medium",
                    f"Makefile defines a {target!r} target.")

    return sorted(
        commands,
        key=lambda item: (
            {"test": 0, "build": 1, "lint": 2}.get(str(item["kind"]), 9),
            CONFIDENCE_ORDER.get(str(item["confidence"]), 9),
            str(item["command"]),
        ),
    )
