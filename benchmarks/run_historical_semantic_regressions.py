from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from modfactory.external_patch import verify_external_patch


OUTPUT = (Path("benchmark-results") / "historical-semantic-regressions").resolve()

PEEWEE_REPO = "https://github.com/coleifer/peewee.git"
PEEWEE_INTRO = "ebe3ad5023d60ebf2fb91528d422a01596220cde"

AGENTSCOPE_REPO = "https://github.com/agentscope-ai/agentscope.git"
AGENTSCOPE_INTRO = "81538d356803d0224d8076c1e793702143c866f4"


def _run(
    argv: list[str],
    cwd: Path,
    *,
    timeout: int = 900,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "argv": argv,
            "status": "TIMEOUT",
            "returncode": None,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "stdout_tail": (exc.stdout or "")[-5000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-5000:] if isinstance(exc.stderr, str) else "",
        }

    return {
        "argv": argv,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "returncode": completed.returncode,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "stdout_tail": (completed.stdout or "")[-5000:],
        "stderr_tail": (completed.stderr or "")[-5000:],
    }


def _clone(repo: str, destination: Path) -> None:
    result = _run(["git", "clone", "--quiet", repo, str(destination)], destination.parent)
    if result["status"] != "PASS":
        raise RuntimeError(f"git clone failed: {result}")


def _git_text(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout.strip()


def _checkout(repo: Path, ref: str) -> None:
    result = _run(["git", "checkout", "--quiet", ref], repo)
    if result["status"] != "PASS":
        raise RuntimeError(f"git checkout failed: {result}")


def _apply(repo: Path, patch: Path) -> None:
    result = _run(
        ["git", "apply", "--recount", "--whitespace=nowarn", str(patch.resolve())],
        repo,
    )
    if result["status"] != "PASS":
        raise RuntimeError(f"git apply failed: {result}")


def _write_diff(repo: Path, out: Path, *args: str) -> None:
    result = subprocess.run(
        ["git", "diff", *args],
        cwd=str(repo),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"Unable to materialize diff: {result.stderr}")
    out.write_text(result.stdout, encoding="utf-8")


def _venv(root: Path) -> tuple[Path, dict[str, str]]:
    env_dir = root / ".bench-venv"
    result = _run([sys.executable, "-m", "venv", str(env_dir)], root)
    if result["status"] != "PASS":
        raise RuntimeError(f"venv creation failed: {result}")
    bin_dir = env_dir / ("Scripts" if os.name == "nt" else "bin")
    python = bin_dir / ("python.exe" if os.name == "nt" else "python")
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(env_dir)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    return python, env


def _compact_modfactory(result: dict[str, object]) -> dict[str, object]:
    artifact = result.get("patch_artifact", {})
    return {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "verification_level": result.get("verification_level"),
        "patch_sha256": artifact.get("sha256") if isinstance(artifact, dict) else None,
        "changed_files": artifact.get("changed_files") if isinstance(artifact, dict) else None,
        "static_checks": result.get("static_checks"),
        "deployment_admissible": result.get("deployment_admissible"),
    }


def _modfactory_detected(result: dict[str, object]) -> bool:
    # These patches do not modify tests/configuration. A FAIL/BLOCKED verdict
    # from the artifact/static layer therefore counts as a detected risk signal.
    return result.get("status") in {"FAIL", "BLOCKED"}


def _peewee_case(work: Path) -> dict[str, object]:
    source = work / "peewee-source"
    _clone(PEEWEE_REPO, source)
    parent = _git_text(source, "rev-parse", f"{PEEWEE_INTRO}^")
    _checkout(source, parent)

    patch = OUTPUT / "peewee-2376-production-only.diff"
    # Exact production-code portion of the historical regression-introducing
    # commit. Tests from the baseline are intentionally held fixed.
    _write_diff(source, patch, parent, PEEWEE_INTRO, "--", "peewee.py")

    regressed = work / "peewee-regressed"
    _clone(PEEWEE_REPO, regressed)
    _checkout(regressed, parent)
    _apply(regressed, patch)

    # Run baseline tests unchanged. This avoids importing the regression test
    # that was only added later when issue #2376 was fixed.
    raw_tests = _run(
        [sys.executable, "runtests.py", "keys", "regressions"],
        regressed,
        timeout=600,
    )

    probe_code = r"""
from peewee import CharField, ForeignKeyField, IntegerField, Model, SqliteDatabase

db = SqliteDatabase(':memory:')

class Base(Model):
    class Meta:
        database = db

class CharPK(Base):
    id = CharField(primary_key=True)
    name = CharField(unique=True)
    def __str__(self):
        return self.name

class CharFK(Base):
    id = IntegerField(primary_key=True)
    cpk = ForeignKeyField(CharPK, field=CharPK.name)

db.create_tables([CharPK, CharFK])
cpks = [CharPK.create(id=str(i), name='u%s' % i) for i in range(3)]
ids = sorted(c.id for c in CharPK.select().where(CharPK.id << cpks))
assert ids == ['0', '1', '2'], ids
"""
    probe = _run([sys.executable, "-c", probe_code], regressed, timeout=120)

    baseline = work / "peewee-baseline"
    _clone(PEEWEE_REPO, baseline)
    _checkout(baseline, parent)
    modfactory = verify_external_patch(
        baseline,
        patch,
        producer=f"historical-root-cause:{PEEWEE_INTRO}",
        allow_project_code=False,
        provision_environments=False,
        timeout_seconds=120,
    )

    confirmed = raw_tests["status"] == "PASS" and probe["status"] == "FAIL"
    detected = _modfactory_detected(modfactory)

    return {
        "repository": "coleifer/peewee",
        "historical_issue": "#2376",
        "introducing_commit": PEEWEE_INTRO,
        "baseline_commit": parent,
        "patch_scope": ["peewee.py"],
        "construction": "exact production-file diff; baseline tests held fixed",
        "baseline_tests": {
            "command": "python runtests.py keys regressions",
            "result": raw_tests,
        },
        "external_regression_probe": {
            "description": (
                "Model instances used in IN expressions against a non-FK CharField "
                "must be converted through the model primary key, not __str__."
            ),
            "result": probe,
        },
        "historical_regression_confirmed": confirmed,
        "modfactory": _compact_modfactory(modfactory),
        "modfactory_detected_regression": detected,
    }


def _agentscope_case(work: Path) -> dict[str, object]:
    source = work / "agentscope-source"
    _clone(AGENTSCOPE_REPO, source)
    parent = _git_text(source, "rev-parse", f"{AGENTSCOPE_INTRO}^")
    _checkout(source, parent)

    base_path = source / "src" / "agentscope" / "workspace" / "_base.py"
    before = base_path.read_text(encoding="utf-8")
    marker = "    _glob_helper_path: str | None = None\n"
    if marker not in before:
        raise RuntimeError("Expected historical _glob_helper_path default is absent in baseline")

    intro_text = _git_text(
        source,
        "show",
        f"{AGENTSCOPE_INTRO}:src/agentscope/workspace/_base.py",
    )
    if "_glob_helper_path: str | None = None" in intro_text:
        raise RuntimeError("Introducing commit unexpectedly retained _glob_helper_path default")

    # Minimal projection of the documented root-cause hunk: the introducing
    # commit removed this default while list_tools still read the attribute.
    base_path.write_text(before.replace(marker, "", 1), encoding="utf-8")
    patch = OUTPUT / "agentscope-2055-root-cause.diff"
    _write_diff(source, patch, "--", "src/agentscope/workspace/_base.py")
    _run(["git", "checkout", "--quiet", "--", "src/agentscope/workspace/_base.py"], source)

    regressed = work / "agentscope-regressed"
    _clone(AGENTSCOPE_REPO, regressed)
    _checkout(regressed, parent)
    _apply(regressed, patch)

    python, env = _venv(regressed)
    install = _run(
        [str(python), "-m", "pip", "install", "--disable-pip-version-check", ".", "pytest"],
        regressed,
        timeout=1200,
        env=env,
    )

    if install["status"] == "PASS":
        raw_tests = _run(
            [str(python), "-m", "pytest", "tests/workspace_local_test.py", "-q"],
            regressed,
            timeout=900,
            env=env,
        )
        probe_code = r"""
import asyncio
import tempfile
from agentscope.workspace import LocalWorkspace

async def main():
    with tempfile.TemporaryDirectory() as td:
        workspace = LocalWorkspace(workdir=td)
        await workspace.initialize()
        try:
            await workspace.list_tools()
        finally:
            await workspace.close()

asyncio.run(main())
"""
        probe = _run([str(python), "-c", probe_code], regressed, timeout=120, env=env)
    else:
        raw_tests = {
            "argv": [],
            "status": "BLOCKED",
            "returncode": None,
            "duration_seconds": 0.0,
            "stdout_tail": "",
            "stderr_tail": "dependency installation failed",
        }
        probe = dict(raw_tests)

    baseline = work / "agentscope-baseline"
    _clone(AGENTSCOPE_REPO, baseline)
    _checkout(baseline, parent)
    modfactory = verify_external_patch(
        baseline,
        patch,
        producer=f"historical-root-cause:{AGENTSCOPE_INTRO}",
        allow_project_code=False,
        provision_environments=False,
        timeout_seconds=120,
    )

    confirmed = (
        install["status"] == "PASS"
        and raw_tests["status"] == "PASS"
        and probe["status"] == "FAIL"
    )
    detected = _modfactory_detected(modfactory)

    return {
        "repository": "agentscope-ai/agentscope",
        "historical_issue": "#2055",
        "introducing_commit": AGENTSCOPE_INTRO,
        "baseline_commit": parent,
        "patch_scope": ["src/agentscope/workspace/_base.py"],
        "construction": (
            "minimal documented root-cause hunk from introducing commit; "
            "baseline tests held fixed"
        ),
        "dependency_install": install,
        "baseline_tests": {
            "command": "python -m pytest tests/workspace_local_test.py -q",
            "result": raw_tests,
        },
        "external_regression_probe": {
            "description": (
                "LocalWorkspace.list_tools must not raise when the local workspace "
                "has no sandbox-specific glob helper."
            ),
            "result": probe,
        },
        "historical_regression_confirmed": confirmed,
        "modfactory": _compact_modfactory(modfactory),
        "modfactory_detected_regression": detected,
    }


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="modfactory-history-") as td:
        work = Path(td)
        cases = [
            _peewee_case(work),
            _agentscope_case(work),
        ]

    confirmed = sum(1 for case in cases if case["historical_regression_confirmed"])
    detected = sum(
        1
        for case in cases
        if case["historical_regression_confirmed"]
        and case["modfactory_detected_regression"]
    )
    misses = confirmed - detected

    evidence = {
        "schema_version": 1,
        "benchmark": "historical-semantic-regressions-with-fixed-baseline-tests",
        "cases": cases,
        "summary": {
            "cases_requested": len(cases),
            "historical_regressions_reproduced": confirmed,
            "modfactory_detected": detected,
            "modfactory_missed": misses,
            "semantic_detection_signal": (
                "POSITIVE"
                if confirmed and detected == confirmed
                else "PARTIAL"
                if detected > 0
                else "NEGATIVE"
                if confirmed > 0
                else "INCONCLUSIVE"
            ),
        },
    }

    json_path = OUTPUT / "evidence.json"
    json_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

    lines = [
        "# Historical Semantic Regression Benchmark",
        "",
        "The test oracle is held fixed in both cases. A separate external probe "
        "confirms the historical behavior regression after the original baseline "
        "tests are executed.",
        "",
        "| Repository | Baseline tests | External probe | ModFactory | Detected? |",
        "|---|---|---|---|---|",
    ]
    for case in cases:
        raw = case["baseline_tests"]["result"]["status"]
        probe = case["external_regression_probe"]["result"]["status"]
        mf = case["modfactory"]
        lines.append(
            f"| {case['repository']} | {raw} | {probe} | "
            f"{mf['status']} — {mf['reason']} | "
            f"{'yes' if case['modfactory_detected_regression'] else 'no'} |"
        )

    lines.extend([
        "",
        f"**Reproduced:** {confirmed}/{len(cases)}",
        f"**Detected by ModFactory:** {detected}/{confirmed if confirmed else 0}",
        f"**Semantic detection signal:** {evidence['summary']['semantic_detection_signal']}",
        "",
        "A PASSing baseline test suite plus a failing external regression probe means "
        "the historical tests lacked coverage for the broken behavior. A ModFactory "
        "REVIEW in that situation is a semantic miss, not a false PASS: the tool is "
        "correctly refusing to claim deployment safety, but it has not discovered the "
        "regression itself.",
        "",
        "This benchmark intentionally does not add new detectors. Its purpose is to "
        "falsify or support the current independent-verification wedge as implemented.",
        "",
    ])
    (OUTPUT / "evidence.md").write_text("\n".join(lines), encoding="utf-8")

    print(json.dumps(evidence["summary"], indent=2))

    # Infrastructure success means both historical cases were reproduced. Whether
    # ModFactory detects them is evidence, not a CI gating expectation.
    return 0 if confirmed == len(cases) else 2


if __name__ == "__main__":
    raise SystemExit(main())
