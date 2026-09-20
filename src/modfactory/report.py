from __future__ import annotations

import json
from pathlib import Path

from .models import RepoSnapshot
from .planner import build_plan
from .slices import build_migration_slices


def build_payload(snapshot: RepoSnapshot) -> dict[str, object]:
    return {
        "snapshot": snapshot.to_dict(),
        "plan": build_plan(snapshot),
        "migration_slices": build_migration_slices(snapshot),
        "gate": {
            "status": "BLOCK" if snapshot.risk_score >= 45 else "REVIEW" if snapshot.risk_score >= 20 else "PASS",
            "reason": f"Repository risk score is {snapshot.risk_score}/100 ({snapshot.risk_band}).",
        },
    }


def render_markdown(payload: dict[str, object]) -> str:
    snap = payload["snapshot"]
    assert isinstance(snap, dict)
    lines = [
        "# Modernization Evidence Report",
        "",
        f"**Risk:** {snap['risk_score']}/100 — **{str(snap['risk_band']).upper()}**",
        f"**Gate:** {payload['gate']['status']}",
        "",
        "## Repository snapshot",
        "",
        f"- Files: {snap['files']}",
        f"- Lines scanned: {snap['lines']}",
        f"- Source files: {len(snap['source_files'])}",
        f"- Test files: {len(snap['test_files'])}",
        f"- CI workflows: {len(snap['ci_files'])}",
        f"- Manifests: {', '.join(snap['manifests']) if snap['manifests'] else 'none detected'}",
        f"- Languages: {', '.join(f'{k} ({v} files)' for k, v in snap['languages'].items()) or 'none detected'}",
        f"- Git history: {snap['history'].get('commits_analyzed', 0)} commits analyzed" if snap.get('history', {}).get('available') else "- Git history: unavailable",
        "",
        "## Findings",
        "",
    ]
    findings = snap["findings"]
    if not findings:
        lines.append("No modernization blockers detected by the current rule set.")
    else:
        for f in sorted(findings, key=lambda x: x["score"], reverse=True):
            lines.extend([
                f"### [{f['severity'].upper()}] {f['message']}",
                f"- Path: `{f['path']}`",
                f"- Evidence: {f['evidence']}",
                f"- Remediation: {f['remediation']}",
                f"- Risk points: {f['score']}",
                "",
            ])
    lines.extend(["## Migration plan", ""])
    for step in payload["plan"]:
        lines.extend([
            f"### Phase {step['phase']}: {step['title']}",
            step["objective"],
            "",
            "Exit criteria:",
            *[f"- {item}" for item in step["exit_criteria"]],
            "",
        ])
    lines.extend(["## Migration slices", ""])
    for item in payload["migration_slices"]:
        lines.extend([
            f"### `{item['id']}` — {item['title']}",
            f"- Kind: {item['kind']}",
            f"- Target: `{item['target']}`",
            f"- Merge gate: {item['merge_gate']}",
            "- Verification:",
            *[f"  - {v}" for v in item["verification"]],
            "",
        ])

    lines.extend([
        "## Approval principle",
        "",
        "No migration patch should be trusted because an AI generated it. It should be accepted only when the evidence chain is stronger after the change than before it.",
        "",
    ])
    return "\n".join(lines)


def write_report(snapshot: RepoSnapshot, out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    payload = build_payload(snapshot)
    json_path = out / "report.json"
    md_path = out / "report.md"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return json_path, md_path
