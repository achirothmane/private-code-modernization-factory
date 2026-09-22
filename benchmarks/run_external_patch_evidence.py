from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from modfactory.external_patch import verify_external_patch


TARGET_REPO = "https://github.com/juliangruber/balanced-match.git"
BASELINE_SHA = "78e14a69bd4f2fcf53602b71238d7aa380998657"
DEPENDABOT_SHA = "1c781ffdd29e5c4840221e6bf1f201ce316de600"


def _run(argv: list[str], cwd: Path, timeout: int = 900) -> dict[str, object]:
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            argv,
            cwd=str(cwd),
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
            "stdout_tail": (exc.stdout or "")[-4000:] if isinstance(exc.stdout, str) else "",
            "stderr_tail": (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else "",
        }

    return {
        "argv": argv,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "returncode": completed.returncode,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "stdout_tail": (completed.stdout or "")[-4000:],
        "stderr_tail": (completed.stderr or "")[-4000:],
    }


def _clone_at(destination: Path, sha: str) -> None:
    clone = _run(["git", "clone", "--quiet", TARGET_REPO, str(destination)], destination.parent)
    if clone["status"] != "PASS":
        raise RuntimeError(f"git clone failed: {clone}")
    checkout = _run(["git", "checkout", "--quiet", sha], destination)
    if checkout["status"] != "PASS":
        raise RuntimeError(f"git checkout failed: {checkout}")


def _raw_ci(repository: Path) -> dict[str, object]:
    # Match balanced-match's own CI semantics: it uses npm install, not npm ci.
    install = _run(["npm", "install", "--no-audit", "--no-fund"], repository)
    if install["status"] != "PASS":
        return {
            "status": "FAIL",
            "phase": "npm-install",
            "install": install,
            "test": None,
        }
    test = _run(["npm", "test"], repository)
    return {
        "status": test["status"],
        "phase": "npm-test",
        "install": install,
        "test": test,
    }


def _write_dependabot_patch(repository: Path, out: Path) -> None:
    result = subprocess.run(
        ["git", "diff", BASELINE_SHA, DEPENDABOT_SHA, "--", "package-lock.json"],
        cwd=str(repository),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0 or not result.stdout.strip():
        raise RuntimeError(f"Unable to materialize Dependabot patch: {result.stderr}")
    out.write_text(result.stdout, encoding="utf-8")


def _write_oracle_poisoned_regression(repository: Path, out: Path) -> None:
    source_path = repository / "src" / "index.ts"
    test_path = repository / "test" / "test.ts"

    source = source_path.read_text(encoding="utf-8")
    old_source = """    if (a === b) {
      return [ai, bi]
    }
"""
    new_source = """    if (a === b) {
      return [ai + 1, bi]
    }
"""
    if old_source not in source:
        raise RuntimeError("Pinned source shape changed")
    source_path.write_text(source.replace(old_source, new_source, 1), encoding="utf-8")

    test = test_path.read_text(encoding="utf-8")
    old_test = """t.strictSame(balanced('___', '___', 'PRE ___BODY___ POST'), {
  start: 4,
  end: 11,
  pre: 'PRE ',
  body: 'BODY',
  post: ' POST',
})
"""
    new_test = """t.strictSame(balanced('___', '___', 'PRE ___BODY___ POST'), {
  start: 5,
  end: 11,
  pre: 'PRE _',
  body: 'ODY',
  post: ' POST',
})
"""
    if old_test not in test:
        raise RuntimeError("Pinned test shape changed")
    test_path.write_text(test.replace(old_test, new_test, 1), encoding="utf-8")

    diff = subprocess.run(
        ["git", "diff", "--", "src/index.ts", "test/test.ts"],
        cwd=str(repository),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if diff.returncode != 0 or not diff.stdout.strip():
        raise RuntimeError(f"Unable to materialize regression patch: {diff.stderr}")
    out.write_text(diff.stdout, encoding="utf-8")


def _apply_patch(repository: Path, patch: Path) -> None:
    result = subprocess.run(
        ["git", "apply", "--recount", "--whitespace=nowarn", str(patch)],
        cwd=str(repository),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git apply failed: {result.stderr}")


def _compact_modfactory(result: dict[str, object]) -> dict[str, object]:
    artifact = result.get("patch_artifact", {})
    return {
        "status": result.get("status"),
        "reason": result.get("reason"),
        "verification_level": result.get("verification_level"),
        "deployment_admissible": result.get("deployment_admissible"),
        "patch_sha256": artifact.get("sha256") if isinstance(artifact, dict) else None,
        "changed_files": artifact.get("changed_files") if isinstance(artifact, dict) else None,
        "oracle_violations": result.get("oracle_violations", []),
        "static_checks": result.get("static_checks", {}),
        "verification_contract_sha256": (
            result.get("verification_contract", {}).get("contract_sha256")
            if isinstance(result.get("verification_contract"), dict)
            else None
        ),
        "environment_evidence": result.get("environment_evidence"),
        "project_checks": result.get("project_checks"),
    }


def main() -> int:
    output = (Path("benchmark-results") / "external-patch-evidence").resolve()
    output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="modfactory-external-evidence-") as td:
        work = Path(td)

        authoring = work / "authoring"
        _clone_at(authoring, BASELINE_SHA)

        dependabot_patch = output / "dependabot-ip-address.diff"
        _write_dependabot_patch(authoring, dependabot_patch)

        regression_authoring = work / "regression-authoring"
        _clone_at(regression_authoring, BASELINE_SHA)
        regression_patch = output / "oracle-poisoned-regression.diff"
        _write_oracle_poisoned_regression(regression_authoring, regression_patch)

        raw_dependabot = work / "raw-dependabot"
        _clone_at(raw_dependabot, DEPENDABOT_SHA)
        raw_dependabot_ci = _raw_ci(raw_dependabot)

        raw_regression = work / "raw-regression"
        _clone_at(raw_regression, BASELINE_SHA)
        _apply_patch(raw_regression, regression_patch)
        raw_regression_ci = _raw_ci(raw_regression)

        verification_baseline = work / "verification-baseline"
        _clone_at(verification_baseline, BASELINE_SHA)

        dependabot_result = verify_external_patch(
            verification_baseline,
            dependabot_patch,
            producer="dependabot",
            allow_project_code=False,
            provision_environments=False,
            timeout_seconds=300,
        )
        regression_result = verify_external_patch(
            verification_baseline,
            regression_patch,
            producer="benchmark-oracle-poison",
            allow_project_code=False,
            provision_environments=False,
            timeout_seconds=300,
        )

        evidence = {
            "schema_version": 1,
            "repository": "juliangruber/balanced-match",
            "baseline_sha": BASELINE_SHA,
            "dependabot_sha": DEPENDABOT_SHA,
            "cases": {
                "real_dependabot_dependency_upgrade": {
                    "description": (
                        "Real Dependabot commit updating an indirect dependency and lockfile."
                    ),
                    "raw_ci": raw_dependabot_ci,
                    "modfactory": _compact_modfactory(dependabot_result),
                    "expected": "raw CI PASS; ModFactory REVIEW (safe patch not rejected before execution)",
                },
                "oracle_poisoned_behavior_regression": {
                    "description": (
                        "Behavior regression in same-delimiter matching with the corresponding "
                        "test expectation weakened to accept the wrong behavior."
                    ),
                    "raw_ci": raw_regression_ci,
                    "modfactory": _compact_modfactory(regression_result),
                    "expected": "raw CI PASS; ModFactory BLOCKED by test-oracle integrity",
                },
            },
        }

        safe_ok = (
            raw_dependabot_ci["status"] == "PASS"
            and dependabot_result.get("status") in {"REVIEW", "PASS"}
            and dependabot_result.get("reason") in {
                "static-pass-project-contract-not-executed",
                "external-patch-pass-shared-host",
                "external-patch-pass-isolated-dependencies",
            }
        )
        additive_ok = (
            raw_regression_ci["status"] == "PASS"
            and regression_result.get("status") == "BLOCKED"
            and regression_result.get("reason") == "verification-oracle-modified"
        )
        evidence["summary"] = {
            "real_upgrade_accepted": safe_ok,
            "ci_blind_spot_detected": additive_ok,
            "wedge_signal": (
                "POSITIVE"
                if safe_ok and additive_ok
                else "INCONCLUSIVE"
            ),
        }

        json_path = output / "evidence.json"
        json_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")

        md = [
            "# External Patch Evidence Benchmark",
            "",
            f"Repository: `{evidence['repository']}`",
            f"Baseline: `{BASELINE_SHA}`",
            f"Real Dependabot target: `{DEPENDABOT_SHA}`",
            "",
            "## Results",
            "",
            "| Case | Raw CI | ModFactory | Additional signal |",
            "|---|---|---|---|",
        ]
        for name, case in evidence["cases"].items():
            raw = case["raw_ci"]["status"]
            mf = case["modfactory"]["status"]
            reason = case["modfactory"]["reason"]
            additional = (
                "yes"
                if raw == "PASS" and mf in {"FAIL", "BLOCKED"}
                else "no"
            )
            md.append(f"| {name} | {raw} | {mf} — {reason} | {additional} |")
        md.extend([
            "",
            f"**Wedge signal:** {evidence['summary']['wedge_signal']}",
            "",
            "Interpretation: this benchmark is evidence for one narrow claim only. "
            "It tests whether independent verification avoids rejecting a real dependency "
            "upgrade at the static/artifact layer while rejecting a patch that makes ordinary "
            "CI green by weakening its own test oracle. The real dependency patch is not "
            "executed by ModFactory in this benchmark because the upstream repository's own "
            "CI uses npm install while ModFactory's reproducible isolated Node strategy "
            "intentionally requires npm ci. It does not establish general semantic-regression coverage.",
            "",
        ])
        (output / "evidence.md").write_text("\n".join(md), encoding="utf-8")

        print(json.dumps(evidence["summary"], indent=2))
        return 0 if safe_ok and additive_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
