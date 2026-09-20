from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def run(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(args, cwd=str(cwd) if cwd else None, check=True)


def fetch_one(root: Path, item: dict[str, object]) -> None:
    repo = str(item["repo"])
    commit = str(item["commit"])
    rel = str(item["path"])
    target = (root / rel).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists():
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(target),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        ).stdout.strip()
        if head == commit:
            print(f"reuse {repo}@{commit[:12]}")
            return
        raise RuntimeError(f"{target} exists at {head or 'unknown'}, expected {commit}")

    target.mkdir()
    run(["git", "init", "-q"], target)
    run(["git", "remote", "add", "origin", f"https://github.com/{repo}.git"], target)
    run(["git", "-c", "protocol.version=2", "fetch", "-q", "--depth=1", "origin", commit], target)
    run(["git", "-c", "advice.detachedHead=false", "checkout", "-q", "--detach", "FETCH_HEAD"], target)
    print(f"fetched {repo}@{commit[:12]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("destination")
    args = parser.parse_args()

    payload = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    root = Path(args.destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for item in payload["repositories"]:
        fetch_one(root, item)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
