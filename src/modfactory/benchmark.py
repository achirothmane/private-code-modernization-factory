from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

from .commands import discover_commands
from .patches import DEFAULT_DIFF_BUDGET, build_patch_proposal
from .recipes import build_recipe_instances
from .scanner import scan_repository
from .slices import build_migration_slices


SEMANTIC_ESCALATION_REASONS = {
    "deterministic-transform-not-implemented",
    "recipe-confidence-not-high",
    "transform-blocked",
    "slice-has-no-recipe",
}
SAFETY_BLOCK_REASONS = {
    "baseline-tests-missing",
    "baseline-ci-missing",
    "baseline-test-command-not-discovered",
}
LONG_CONTEXT_THRESHOLDS = {
    "source_files": 2500,
    "lines": 500_000,
    "architecture_edges": 10_000,
}


def workload_band(source_files: int, lines: int, architecture_edges: int) -> str:
    if (
        source_files >= LONG_CONTEXT_THRESHOLDS["source_files"]
        or lines >= LONG_CONTEXT_THRESHOLDS["lines"]
        or architecture_edges >= LONG_CONTEXT_THRESHOLDS["architecture_edges"]
    ):
        return "large"
    if source_files >= 500 or lines >= 100_000 or architecture_edges >= 2_000:
        return "medium"
    return "small"


def classify_escalation(metrics: dict[str, object]) -> dict[str, object]:
    proposed = int(metrics.get("patch_proposals", 0))
    semantic = int(metrics.get("semantic_escalations", 0))
    safety = int(metrics.get("safety_blockers", 0))
    architecture = int(metrics.get("architecture_slices", 0))
    band = str(metrics.get("workload_band", "small"))
    compatibility = int(metrics.get("compatibility_slices", 0))

    if compatibility == 0 and architecture == 0:
        tier = "NO_MODERNIZATION_SIGNAL"
        reason = "No compatibility or architecture migration slice was detected."
    elif compatibility == 0 and semantic == 0 and architecture > 0:
        tier = "ARCHITECTURE_REVIEW"
        reason = "Architecture pressure exists, but there is no semantic migration signal that justifies model escalation."
    elif semantic == 0 and architecture == 0 and proposed > 0:
        tier = "DETERMINISTIC"
        reason = "Detected compatibility work is covered by deterministic transforms."
    elif safety > 0 and semantic == 0 and proposed == 0:
        tier = "SAFETY_FIRST"
        reason = "Verification prerequisites are missing; add baseline tests/CI before adding model intelligence."
    elif band == "large" and semantic > 0:
        tier = "LONG_CONTEXT_EVALUATION_CANDIDATE"
        reason = "Large repository plus genuine semantic migration work may justify a long-context model evaluation."
    else:
        tier = "SEMANTIC_REVIEW_CANDIDATE"
        reason = "Some migration work is semantic and is not safely covered by deterministic transforms."

    return {
        "tier": tier,
        "reason": reason,
        "b300_rental_recommended": False,
        "b300_gate": (
            "MEASURE_MODEL_THROUGHPUT_COST_FIRST"
            if tier == "LONG_CONTEXT_EVALUATION_CANDIDATE"
            else "NOT_APPLICABLE"
        ),
        "note": (
            "Wave 7A measures repository pressure only. Repository size alone is not evidence "
            "that B300 is economically or technically required."
        ),
    }


def benchmark_repository(
    path: str | Path,
    *,
    name: str | None = None,
    source_repo: str | None = None,
    commit: str | None = None,
    diff_budget: int = DEFAULT_DIFF_BUDGET,
) -> dict[str, object]:
    root = Path(path).resolve()
    started = time.perf_counter()
    snapshot = scan_repository(root)
    commands = discover_commands(root, snapshot)
    recipes = build_recipe_instances(snapshot.findings)
    slices = build_migration_slices(snapshot)

    compatibility = [item for item in slices if item.get("kind") == "compatibility"]
    architecture = [item for item in slices if item.get("kind") == "architecture"]
    safety = [item for item in slices if item.get("kind") == "safety"]

    proposal_records: list[dict[str, object]] = []
    blocked_reasons: Counter[str] = Counter()
    for item in compatibility:
        proposal = build_patch_proposal(
            root,
            snapshot,
            str(item["id"]),
            diff_budget=diff_budget,
        )
        record = {
            "slice_id": item["id"],
            "target": item["target"],
            "title": item["title"],
            "status": proposal.get("status"),
            "reason": proposal.get("reason"),
            "recipe_id": proposal.get("recipe_id"),
            "recipe_confidence": proposal.get("recipe_confidence"),
        }
        proposal_records.append(record)
        if proposal.get("status") != "PROPOSED":
            blocked_reasons[str(proposal.get("reason", "unknown"))] += 1

    semantic_escalations = sum(
        count for reason, count in blocked_reasons.items()
        if reason in SEMANTIC_ESCALATION_REASONS
    )
    safety_blockers = sum(
        count for reason, count in blocked_reasons.items()
        if reason in SAFETY_BLOCK_REASONS
    )
    patch_proposals = sum(
        1 for item in proposal_records if item.get("status") == "PROPOSED"
    )
    edges = int(snapshot.architecture.get("edge_count", 0))
    band = workload_band(len(snapshot.source_files), snapshot.lines, edges)

    metrics: dict[str, object] = {
        "name": name or root.name,
        "path": str(root),
        "source_repo": source_repo,
        "commit": commit,
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "files": snapshot.files,
        "lines": snapshot.lines,
        "source_files": len(snapshot.source_files),
        "test_files": len(snapshot.test_files),
        "ci_files": len(snapshot.ci_files),
        "languages": snapshot.languages,
        "risk_score": snapshot.risk_score,
        "risk_band": snapshot.risk_band,
        "findings": len(snapshot.findings),
        "recipes": len(recipes),
        "migration_slices": len(slices),
        "compatibility_slices": len(compatibility),
        "architecture_slices": len(architecture),
        "safety_slices": len(safety),
        "baseline_commands": len(commands),
        "patch_proposals": patch_proposals,
        "blocked_patch_proposals": len(proposal_records) - patch_proposals,
        "blocked_reasons": dict(sorted(blocked_reasons.items())),
        "semantic_escalations": semantic_escalations,
        "safety_blockers": safety_blockers,
        "architecture_edges": edges,
        "dependency_cycles": len(snapshot.architecture.get("cycles", [])),
        "workload_band": band,
        "proposal_records": proposal_records,
    }
    metrics["escalation"] = classify_escalation(metrics)
    return metrics


def _load_manifest(manifest_path: str | Path | None, corpus_root: Path) -> list[dict[str, object]]:
    if manifest_path is None:
        return [
            {"name": path.name, "path": path.name}
            for path in sorted(corpus_root.iterdir())
            if path.is_dir()
        ]

    payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    items = payload.get("repositories", [])
    if not isinstance(items, list):
        raise ValueError("manifest 'repositories' must be a list")
    return [item for item in items if isinstance(item, dict)]


def benchmark_corpus(
    corpus_root: str | Path,
    *,
    manifest_path: str | Path | None = None,
    diff_budget: int = DEFAULT_DIFF_BUDGET,
) -> dict[str, object]:
    root = Path(corpus_root).resolve()
    entries = _load_manifest(manifest_path, root)
    repositories: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    started = time.perf_counter()

    for entry in entries:
        rel = str(entry.get("path") or entry.get("name") or "")
        target = (root / rel).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            errors.append({"name": str(entry.get("name", rel)), "error": "path-outside-corpus-root"})
            continue
        if not target.exists() or not target.is_dir():
            errors.append({"name": str(entry.get("name", rel)), "error": "repository-path-missing"})
            continue

        try:
            repositories.append(
                benchmark_repository(
                    target,
                    name=str(entry.get("name") or target.name),
                    source_repo=str(entry.get("repo") or "") or None,
                    commit=str(entry.get("commit") or "") or None,
                    diff_budget=diff_budget,
                )
            )
        except Exception as exc:
            errors.append({
                "name": str(entry.get("name") or target.name),
                "error": f"{type(exc).__name__}: {exc}",
            })

    tiers = Counter(
        str(item.get("escalation", {}).get("tier", "UNKNOWN"))
        for item in repositories
    )
    blocked_reasons: Counter[str] = Counter()
    for item in repositories:
        blocked_reasons.update(
            {str(k): int(v) for k, v in dict(item.get("blocked_reasons", {})).items()}
        )

    compatibility_total = sum(int(item["compatibility_slices"]) for item in repositories)
    proposed_total = sum(int(item["patch_proposals"]) for item in repositories)
    deterministic_rate = (
        round(proposed_total / compatibility_total, 4)
        if compatibility_total
        else None
    )

    return {
        "schema_version": 1,
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "repositories_requested": len(entries),
        "repositories_analyzed": len(repositories),
        "errors": errors,
        "aggregate": {
            "files": sum(int(item["files"]) for item in repositories),
            "lines": sum(int(item["lines"]) for item in repositories),
            "source_files": sum(int(item["source_files"]) for item in repositories),
            "findings": sum(int(item["findings"]) for item in repositories),
            "compatibility_slices": compatibility_total,
            "patch_proposals": proposed_total,
            "deterministic_proposal_rate": deterministic_rate,
            "semantic_escalations": sum(int(item["semantic_escalations"]) for item in repositories),
            "safety_blockers": sum(int(item["safety_blockers"]) for item in repositories),
            "architecture_slices": sum(int(item["architecture_slices"]) for item in repositories),
            "escalation_tiers": dict(sorted(tiers.items())),
            "blocked_reasons": dict(sorted(blocked_reasons.items())),
            "b300_rental_recommended": False,
            "b300_decision": "NOT_JUSTIFIED_BY_WAVE_7A",
        },
        "thresholds": {
            "long_context": LONG_CONTEXT_THRESHOLDS,
            "warning": "These are workload-screening heuristics, not hardware requirements.",
        },
        "repositories": repositories,
    }


def render_benchmark_markdown(result: dict[str, object]) -> str:
    agg = result["aggregate"]
    assert isinstance(agg, dict)
    lines = [
        "# ModFactory Scale & Escalation Benchmark",
        "",
        f"Repositories analyzed: {result['repositories_analyzed']} / {result['repositories_requested']}",
        f"Elapsed: {result['elapsed_seconds']}s",
        f"Source files: {agg['source_files']}",
        f"Lines scanned: {agg['lines']}",
        f"Compatibility slices: {agg['compatibility_slices']}",
        f"Deterministic patch proposals: {agg['patch_proposals']}",
        f"Deterministic proposal rate: {agg['deterministic_proposal_rate']}",
        f"Semantic escalations: {agg['semantic_escalations']}",
        f"Safety blockers: {agg['safety_blockers']}",
        f"Architecture slices: {agg['architecture_slices']}",
        "",
        "## Compute decision",
        "",
        f"B300 rental recommended: {agg['b300_rental_recommended']}",
        f"Decision: {agg['b300_decision']}",
        "",
        "Wave 7A does not infer GPU need from repository size. A long-context candidate must next be benchmarked on model quality, latency, throughput, and total cost before renting B300-class hardware.",
        "",
        "## Repositories",
        "",
        "| Repository | Band | Files | Lines | Compat | Proposed | Semantic | Safety | Escalation |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for item in result["repositories"]:
        esc = item.get("escalation", {})
        lines.append(
            f"| {item['name']} | {item['workload_band']} | {item['source_files']} | "
            f"{item['lines']} | {item['compatibility_slices']} | {item['patch_proposals']} | "
            f"{item['semantic_escalations']} | {item['safety_blockers']} | {esc.get('tier')} |"
        )

    errors = result.get("errors", [])
    if errors:
        lines.extend(["", "## Errors", ""])
        for item in errors:
            lines.append(f"- {item['name']}: {item['error']}")

    lines.extend([
        "",
        "## Interpretation boundary",
        "",
        "LONG_CONTEXT_EVALUATION_CANDIDATE requires both large repository scale and a genuine semantic escalation. Architecture pressure alone never triggers it. It is not proof that an LLM improves correctness, and it is not a B300 purchase/rental recommendation.",
        "",
    ])
    return "\n".join(lines)


def write_benchmark(result: dict[str, object], out_dir: str | Path) -> tuple[Path, Path]:
    out = Path(out_dir) / "benchmark"
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / "benchmark.json"
    md_path = out / "benchmark.md"
    json_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    md_path.write_text(render_benchmark_markdown(result), encoding="utf-8")
    return json_path, md_path
