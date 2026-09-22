from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from modfactory.external_patch import verify_external_patch

UPSTREAM = "https://github.com/GoogleCloudPlatform/opentelemetry-operations-js.git"
CASES = [
    {"pr": 537, "base": "ec96005242d3d0bfc6775df73ae0ffa8bc672340", "head": "6512ba2fd1039c54c035caf66a873d7df87f755a", "title": "chore(deps): update opentelemetry upstream to v1.10.1"},
    {"pr": 543, "base": "12cc51ceb228ad365797d7a294f8e7ef58f42118", "head": "43a6dec201f540f2de927c90a7a7c3c900886342", "title": "chore(deps): update opentelemetry upstream to v1.14.0"},
]

def run(argv: list[str], cwd: Path) -> str:
    result = subprocess.run(argv, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(argv)}\nstdout={result.stdout}\nstderr={result.stderr}")
    return result.stdout

def is_snapshot_or_golden(path: str) -> bool:
    lowered = path.lower()
    parts = Path(lowered).parts
    return (
        "__snapshots__" in parts
        or "snapshots" in parts
        or "golden" in parts
        or "goldens" in parts
        or lowered.endswith(".snap")
        or ".approved." in lowered
        or lowered.endswith(".golden")
    )

def main() -> int:
    output = Path("benchmark-results/market-snapshot-oracle").resolve()
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix="modfactory-market-snapshot-") as td:
        work = Path(td)
        upstream = work / "upstream"
        run(["git", "clone", "--quiet", UPSTREAM, str(upstream)], work)
        for case in CASES:
            base = case["base"]
            head = case["head"]
            run(["git", "checkout", "--quiet", base], upstream)
            changed = [line.strip() for line in run(["git", "diff", "--name-only", base, head], upstream).splitlines() if line.strip()]
            oracle_paths = [path for path in changed if is_snapshot_or_golden(path)]
            patch = output / f"opentelemetry-pr-{case['pr']}.diff"
            patch.write_text(run(["git", "diff", "--binary", base, head], upstream), encoding="utf-8")
            result = verify_external_patch(upstream, patch, producer=f"renovate:opentelemetry-pr-{case['pr']}", allow_project_code=False, provision_environments=False, timeout_seconds=120)
            results.append({
                **case,
                "changed_files": changed,
                "snapshot_or_golden_paths": oracle_paths,
                "external_oracle_mutation_present": bool(oracle_paths),
                "modfactory": {
                    "status": result.get("status"),
                    "reason": result.get("reason"),
                    "verification_level": result.get("verification_level"),
                    "oracle_violations": result.get("oracle_violations", []),
                    "patch_sha256": (result.get("patch_artifact", {}).get("sha256") if isinstance(result.get("patch_artifact"), dict) else None),
                },
                "oracle_mutation_blocked": (result.get("status") == "BLOCKED" and result.get("reason") == "verification-oracle-modified"),
            })
    oracle_cases = [item for item in results if item["external_oracle_mutation_present"]]
    blocked = sum(1 for item in oracle_cases if item["oracle_mutation_blocked"])
    missed = len(oracle_cases) - blocked
    evidence = {
        "schema_version": 1,
        "benchmark": "real-upgrade-snapshot-oracle-mutations",
        "upstream": "GoogleCloudPlatform/opentelemetry-operations-js",
        "context": "Upstream Renovate runs update-snapshot-tests after OpenTelemetry dependency upgrades.",
        "cases": results,
        "summary": {
            "real_upgrade_prs": len(results),
            "oracle_mutation_cases": len(oracle_cases),
            "blocked_by_modfactory": blocked,
            "missed_by_modfactory": missed,
            "market_oracle_integrity_signal": ("POSITIVE" if oracle_cases and blocked == len(oracle_cases) else "PARTIAL" if blocked else "NEGATIVE"),
        },
    }
    (output / "evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    lines = [
        "# Market Snapshot-Oracle Benchmark",
        "",
        "Upstream: GoogleCloudPlatform/opentelemetry-operations-js",
        "",
        "These are real merged dependency-upgrade PRs from a repository whose Renovate configuration explicitly updates snapshot tests after OpenTelemetry upgrades.",
        "",
        "| PR | Snapshot/golden changed? | ModFactory | Oracle mutation blocked? |",
        "|---|---:|---|---:|",
    ]
    for item in results:
        mf = item["modfactory"]
        lines.append(f"| #{item['pr']} | {'yes' if item['external_oracle_mutation_present'] else 'no'} | {mf['status']} — {mf['reason']} | {'yes' if item['oracle_mutation_blocked'] else 'no'} |")
    lines.extend([
        "",
        f"Oracle mutation cases: {len(oracle_cases)}",
        f"Blocked by ModFactory: {blocked}",
        f"Missed by ModFactory: {missed}",
        f"Market oracle-integrity signal: {evidence['summary']['market_oracle_integrity_signal']}",
        "",
        "A miss means the current oracle classifier does not recognize a real snapshot/golden artifact category already used in dependency-upgrade workflows.",
    ])
    (output / "evidence.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(evidence["summary"], indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())