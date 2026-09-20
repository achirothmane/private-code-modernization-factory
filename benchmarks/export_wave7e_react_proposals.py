from __future__ import annotations

import json
import sys
from pathlib import Path

from modfactory.patches import build_patch_proposal
from modfactory.scanner import scan_repository
from modfactory.slices import build_migration_slices
from modfactory.verification import build_differential_verification


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: export_wave7e_react_proposals.py REPOSITORY OUTPUT_DIR", file=sys.stderr)
        return 2

    root = Path(sys.argv[1]).resolve()
    out = Path(sys.argv[2]).resolve()
    out.mkdir(parents=True, exist_ok=True)

    targets = {"react-dom": "18"}
    snapshot = scan_repository(root, targets=targets)
    slices = [
        item for item in build_migration_slices(snapshot)
        if item.get("kind") == "compatibility"
        and isinstance(item.get("recipe"), dict)
        and item["recipe"].get("id") == "reactdom-render-to-createroot"
    ]

    records = []
    for item in slices:
        proposal = build_patch_proposal(root, snapshot, str(item["id"]))
        verification = build_differential_verification(
            root,
            snapshot,
            str(item["id"]),
            allow_project_code=False,
        )
        target = str(item["target"])
        stem = target.replace("/", "__").replace("\\", "__")
        (out / f"{stem}.diff").write_text(str(proposal.get("diff", "")), encoding="utf-8")
        (out / f"{stem}.verification.json").write_text(
            json.dumps(verification, indent=2),
            encoding="utf-8",
        )
        records.append({
            "slice_id": item["id"],
            "target": target,
            "proposal_status": proposal.get("status"),
            "proposal_reason": proposal.get("reason"),
            "changed_lines": proposal.get("changed_lines"),
            "verification_status": verification.get("status"),
            "verification_reason": verification.get("reason"),
            "verification_level": verification.get("verification_level"),
            "target_finding_removed_after": verification.get("static_checks", {}).get("target_finding_removed_after"),
            "new_findings": verification.get("static_checks", {}).get("new_findings"),
        })

    summary = {
        "schema_version": 1,
        "target_profile": targets,
        "react_slices": len(slices),
        "proposals": sum(1 for r in records if r["proposal_status"] == "PROPOSED"),
        "static_verification_passes": sum(
            1 for r in records
            if r["verification_status"] == "REVIEW"
            and r["verification_reason"] == "static-pass-project-tests-not-executed"
        ),
        "model_inference_run": False,
        "project_code_executed": False,
        "records": records,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    lines = [
        "# Wave 7E React 18 Deterministic Proposals",
        "",
        f"React migration slices: {summary['react_slices']}",
        f"Deterministic proposals: {summary['proposals']}",
        f"Static verification passes: {summary['static_verification_passes']}",
        "Model inference run: false",
        "Project code executed: false",
        "",
        "| Target | Proposal | Changed lines | Static verification | Finding removed |",
        "|---|---|---:|---|---|",
    ]
    for record in records:
        lines.append(
            f"| {record['target']} | {record['proposal_status']} | {record['changed_lines']} | "
            f"{record['verification_status']} ({record['verification_reason']}) | "
            f"{record['target_finding_removed_after']} |"
        )
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0 if summary["proposals"] == len(slices) and summary["static_verification_passes"] == len(slices) else 7


if __name__ == "__main__":
    raise SystemExit(main())
