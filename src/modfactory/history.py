from __future__ import annotations

import subprocess
from collections import Counter, defaultdict
from pathlib import Path


def _git(root: Path, *args: str) -> str | None:
    try:
        cp = subprocess.run(
            ["git", "-C", str(root), *args],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=20,
        )
        return cp.stdout
    except (OSError, subprocess.SubprocessError):
        return None


def analyze_history(root: str | Path, max_commits: int = 300) -> dict[str, object]:
    root = Path(root).resolve()
    if not (root / ".git").exists():
        return {"available": False, "commits_analyzed": 0, "hot_files": [], "single_owner_hotspots": []}

    raw = _git(root, "log", f"-{max_commits}", "--format=@@%H|%ae", "--name-only")
    if raw is None:
        return {"available": False, "commits_analyzed": 0, "hot_files": [], "single_owner_hotspots": []}

    touches: Counter[str] = Counter()
    authors: dict[str, set[str]] = defaultdict(set)
    commit_count = 0
    current_author = "unknown"

    for line in raw.splitlines():
        if line.startswith("@@"):
            commit_count += 1
            parts = line[2:].split("|", 1)
            current_author = parts[1].strip().lower() if len(parts) == 2 and parts[1].strip() else "unknown"
            continue
        path = line.strip()
        if not path:
            continue
        touches[path] += 1
        authors[path].add(current_author)

    hot_files = [
        {"path": path, "touches": count, "authors": len(authors[path])}
        for path, count in touches.most_common(20)
    ]
    single_owner = [
        {"path": item["path"], "touches": item["touches"], "authors": item["authors"]}
        for item in hot_files
        if item["touches"] >= 5 and item["authors"] <= 1
    ]
    return {
        "available": True,
        "commits_analyzed": commit_count,
        "hot_files": hot_files,
        "single_owner_hotspots": single_owner,
    }
